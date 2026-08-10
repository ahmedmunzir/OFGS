import os
import pty
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


WRAPPER = Path(__file__).resolve().parents[1] / "wrapper" / "ofgs"
PROJECT_ROOT = WRAPPER.parents[1]


def path_with(directory):
    environment = os.environ.copy()
    environment["PATH"] = str(directory) + os.pathsep + environment.get("PATH", "")
    return environment


def run_with_terminal_stdout(command, cwd, environment=None):
    master_fd, slave_fd = pty.openpty()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=slave_fd,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        os.close(slave_fd)
        slave_fd = -1
        chunks = []
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return process.wait(), b"".join(chunks).decode()
    finally:
        os.close(master_fd)
        if slave_fd >= 0:
            os.close(slave_fd)


class WrapperLiveTests(unittest.TestCase):
    def test_generate_invokes_renamed_entrypoint_and_propagates_status(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            install_root = root / "installed files"
            install_root.mkdir()
            marker = root / "generator-ran"
            (install_root / "ofgs_generate.py").write_text(
                "from pathlib import Path\n"
                "import sys\n"
                f"Path({str(marker)!r}).write_text('yes')\n"
                "raise SystemExit(7)\n"
            )
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(
                WRAPPER.read_text().replace(
                    'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                    f'OFGS_INSTALL_DIR="{install_root}"',
                    1,
                )
            )
            test_wrapper.chmod(0o755)

            completed = subprocess.run(
                [str(test_wrapper), "generate"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 7)
            self.assertEqual(marker.read_text(), "yes")

    def test_generate_failure_is_visible_to_shell_operators(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(
                WRAPPER.read_text().replace(
                    'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                    f'OFGS_INSTALL_DIR="{PROJECT_ROOT}"',
                    1,
                )
            )
            test_wrapper.chmod(0o755)

            direct = subprocess.run(
                [str(test_wrapper), "generate"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            with_and = subprocess.run(
                ["/bin/bash", "-c", '"$1" generate && echo success', "_", str(test_wrapper)],
                cwd=root,
                capture_output=True,
                text=True,
            )
            with_or = subprocess.run(
                ["/bin/bash", "-c", '"$1" generate || echo failed', "_", str(test_wrapper)],
                cwd=root,
                capture_output=True,
                text=True,
            )

            self.assertEqual(direct.returncode, 1)
            self.assertNotIn("Traceback", direct.stderr)
            self.assertNotEqual(with_and.returncode, 0)
            self.assertNotIn("success", with_and.stdout)
            self.assertEqual(with_or.returncode, 0)
            self.assertIn("failed", with_or.stdout)

    def test_live_commands_stop_when_generation_fails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            install_root = root / "installed"
            install_root.mkdir()
            (install_root / "ofgs_generate.py").write_text("raise SystemExit(9)\n")
            gnuplot_bin = root / "bin"
            gnuplot_bin.mkdir()
            launch_marker = root / "gnuplot-launched"
            gnuplot = gnuplot_bin / "gnuplot"
            gnuplot.write_text(
                "#!/bin/bash\n"
                f"touch {str(launch_marker)!r}\n"
            )
            gnuplot.chmod(0o755)
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(
                WRAPPER.read_text().replace(
                    'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                    f'OFGS_INSTALL_DIR="{install_root}"',
                    1,
                )
            )
            test_wrapper.chmod(0o755)
            (root / "monitor.gp").write_text("plot 1\n")
            (root / "graphs").mkdir()
            (root / "graphs" / "01.gp").write_text("plot 1\n")

            for arguments in (("monitor", "--live"), ("graph", "1", "--live")):
                with self.subTest(arguments=arguments):
                    completed = subprocess.run(
                        [str(test_wrapper), *arguments],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        env=path_with(gnuplot_bin),
                    )
                    self.assertEqual(completed.returncode, 9)
                    self.assertFalse(launch_marker.exists())

    def test_gnuplot_is_resolved_from_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            gnuplot_bin = root / "tools with spaces"
            gnuplot_bin.mkdir()
            invocation = root / "gnuplot-invocation"
            gnuplot = gnuplot_bin / "gnuplot"
            gnuplot.write_text(
                "#!/bin/bash\n"
                f"printf '%s\\n' \"$*\" > {str(invocation)!r}\n"
            )
            gnuplot.chmod(0o755)
            (root / "monitor.gp").write_text("plot 1\n")

            completed = subprocess.run(
                [str(WRAPPER), "monitor.gp"],
                cwd=root,
                capture_output=True,
                text=True,
                env=path_with(gnuplot_bin),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(invocation.read_text(), "monitor.gp\n")

    def test_missing_gnuplot_returns_clean_status_127(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            empty_path = root / "empty-path"
            empty_path.mkdir()
            (root / "monitor.gp").write_text("plot 1\n")
            environment = os.environ.copy()
            environment["PATH"] = str(empty_path)

            completed = subprocess.run(
                ["/bin/bash", str(WRAPPER), "monitor.gp"],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 127)
            self.assertEqual(
                completed.stderr,
                "OFGS error: gnuplot was not found in PATH.\n",
            )

    def test_gnuplot_path_resolving_to_ofgs_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            gnuplot_bin = root / "bin"
            gnuplot_bin.mkdir()
            (gnuplot_bin / "gnuplot").symlink_to(WRAPPER)
            (root / "monitor.gp").write_text("plot 1\n")

            completed = subprocess.run(
                ["/bin/bash", str(WRAPPER), "monitor.gp"],
                cwd=root,
                capture_output=True,
                text=True,
                env=path_with(gnuplot_bin),
            )

            self.assertEqual(completed.returncode, 127)
            self.assertIn("gnuplot was not found in PATH", completed.stderr)

    def test_doctor_uses_path_based_gnuplot_discovery(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            command_bin = root / "commands"
            command_bin.mkdir()
            (command_bin / "python3").symlink_to(Path(sys.executable))
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(
                WRAPPER.read_text().replace(
                    'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                    f'OFGS_INSTALL_DIR="{PROJECT_ROOT}"',
                    1,
                )
            )
            test_wrapper.chmod(0o755)
            (root / "system").mkdir()
            (root / "constant").mkdir()
            environment = os.environ.copy()
            environment["PATH"] = str(command_bin)

            completed = subprocess.run(
                ["/bin/bash", str(test_wrapper), "doctor"],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIn("[FAIL] GNUPlot executable not found", completed.stdout)
            self.assertIn("Doctor found errors.", completed.stdout)

    def test_live_multi_graph_regenerates_and_reloads_one_gnuplot_process(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            generator_root = root / "generator"
            generator_root.mkdir()
            generator = generator_root / "ofgs_generate.py"
            generator.write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path

                    count_path = Path("generation-count")
                    count = int(count_path.read_text()) + 1 if count_path.exists() else 1
                    count_path.write_text(str(count))
                    Path("monitor.gp").write_text("plot 1\\n")
                    Path("graphs").mkdir(exist_ok=True)
                    Path("graphs/01.gp").write_text("plot 1\\n")
                    Path("graphs/07.gp").write_text("plot 7\\n")
                    Path("graphs/index.txt").write_text("01 graph one\\n07 graph seven\\n")
                    """
                )
            )

            command_log = root / "gnuplot-commands"
            script_log = root / "multiplot-scripts"
            gnuplot_bin = root / "gnuplot tools"
            gnuplot_bin.mkdir()
            fake_gnuplot = gnuplot_bin / "gnuplot"
            fake_gnuplot.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import sys
                    from pathlib import Path

                    log_path = Path({str(command_log)!r})
                    script_log_path = Path({str(script_log)!r})
                    load_count = 0
                    for line in sys.stdin:
                        with log_path.open("a") as stream:
                            stream.write(line)
                        if line.startswith("load "):
                            script_path = Path(line.split("'", 2)[1])
                            with script_log_path.open("a") as stream:
                                stream.write(script_path.read_text())
                                stream.write("\\n--- reload ---\\n")
                            load_count += 1
                            if load_count == 2:
                                break
                    """
                )
            )
            fake_gnuplot.chmod(0o755)
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(
                WRAPPER.read_text().replace(
                    'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                    f'OFGS_INSTALL_DIR="{generator_root}"',
                    1,
                )
            )
            test_wrapper.chmod(0o755)

            completed = subprocess.run(
                [str(test_wrapper), "graph", "1,", "7", "--live"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=8,
                env=path_with(gnuplot_bin),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("Bad file descriptor", completed.stderr)
            self.assertGreaterEqual(int((root / "generation-count").read_text()), 2)
            commands = command_log.read_text()
            self.assertIn("LIVE_MODE = 1", commands)
            self.assertIn('bind all "Close" "exit gnuplot"', commands)
            self.assertEqual(commands.count("load '"), 2)
            scripts = script_log.read_text()
            self.assertIn("set multiplot layout 1,2", scripts)
            self.assertIn("'graphs/01.gp'", scripts)
            self.assertIn("'graphs/07.gp'", scripts)

    def test_multi_graph_deduplicates_and_validates_before_opening(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            graphs = root / "graphs"
            graphs.mkdir()
            for graph_number in ("01", "06", "07"):
                (graphs / f"{graph_number}.gp").write_text(f"plot {int(graph_number)}\n")

            captured_script = root / "captured-script"
            launch_marker = root / "gnuplot-launched"
            gnuplot_bin = root / "custom-bin"
            gnuplot_bin.mkdir()
            fake_gnuplot = gnuplot_bin / "gnuplot"
            fake_gnuplot.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import sys
                    from pathlib import Path

                    Path({str(launch_marker)!r}).write_text("launched")
                    Path({str(captured_script)!r}).write_text(Path(sys.argv[1]).read_text())
                    """
                )
            )
            fake_gnuplot.chmod(0o755)
            test_wrapper = root / "ofgs"
            test_wrapper.write_text(WRAPPER.read_text())
            test_wrapper.chmod(0o755)

            completed = subprocess.run(
                [str(test_wrapper), "graph", "1,", "6,", "6,", "7"],
                cwd=root,
                capture_output=True,
                text=True,
                env=path_with(gnuplot_bin),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            script = captured_script.read_text()
            self.assertIn("set multiplot layout 2,2", script)
            self.assertEqual(script.count("'graphs/01.gp'"), 1)
            self.assertEqual(script.count("'graphs/06.gp'"), 1)
            self.assertEqual(script.count("'graphs/07.gp'"), 1)

            launch_marker.unlink()
            missing = subprocess.run(
                [str(test_wrapper), "graph", "1,7,99"],
                cwd=root,
                capture_output=True,
                text=True,
                env=path_with(gnuplot_bin),
            )

            self.assertEqual(missing.returncode, 1)
            self.assertIn("Graph 99 does not exist.", missing.stderr)
            self.assertFalse(launch_marker.exists())

    def test_help_and_help_alias_match(self):
        help_output = subprocess.run(
            [str(WRAPPER), "help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        alias_output = subprocess.run(
            [str(WRAPPER), "--help"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        short_alias_output = subprocess.run(
            [str(WRAPPER), "-h"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        self.assertEqual(help_output, alias_output)
        self.assertEqual(help_output, short_alias_output)
        self.assertIn("OFGS (OpenFOAM Gnuplot Suite)", help_output)
        for heading in ("Usage", "Commands", "Options", "Examples"):
            self.assertIn(heading, help_output)
        for command in (
            "generate",
            "monitor",
            "graph",
            "list",
            "clean",
            "doctor",
            "help",
        ):
            self.assertIn(command, help_output)
        self.assertIn("ofgs help <command>", help_output)
        self.assertNotIn("\033[", help_output)

    def test_help_formatting_is_enabled_on_terminal_stdout(self):
        status, main_output = run_with_terminal_stdout(
            [str(WRAPPER), "help"],
            PROJECT_ROOT,
        )

        self.assertEqual(status, 0)
        self.assertIn("\033[34m", main_output)
        self.assertIn("\033[1mOFGS (OpenFOAM Gnuplot Suite)\033[0m", main_output)
        self.assertIn("\033[1mUsage\033[0m", main_output)

        status, graph_output = run_with_terminal_stdout(
            [str(WRAPPER), "help", "graph"],
            PROJECT_ROOT,
        )

        self.assertEqual(status, 0)
        self.assertIn("\033[1mofgs graph\033[0m", graph_output)
        self.assertIn("\033[1mArguments\033[0m", graph_output)

    def test_command_specific_help(self):
        expected_content = {
            "generate": ("monitor.gp", "graphs/index.txt", "graphs/NN.gp"),
            "monitor": ("ofgs monitor", "ofgs monitor --live", "--live"),
            "graph": (
                "ofgs graph <id>",
                "ofgs graph <id1,id2,...>",
                "ofgs graph <id> --live",
                "ofgs graph <id1,id2,...> --live",
                "Arguments",
            ),
            "list": ("ofgs list", "graph ID", "graphs/"),
            "clean": ("monitor.gp", "graphs/", "--force", "y or Y"),
            "doctor": (
                "OFGS installation files",
                "System gnuplot executable",
                "Python 3 availability",
                "never regenerates graphs or modifies files",
            ),
        }

        for command, expected_strings in expected_content.items():
            with self.subTest(command=command):
                completed = subprocess.run(
                    [str(WRAPPER), "help", command],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for expected in expected_strings:
                    self.assertIn(expected, completed.stdout)
                self.assertIn("Usage", completed.stdout)
                self.assertIn("Options", completed.stdout)
                self.assertIn("Examples", completed.stdout)
                self.assertNotIn("\033[", completed.stdout)

    def test_unknown_help_topic_shows_error_and_main_help(self):
        completed = subprocess.run(
            [str(WRAPPER), "help", "banana"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Error: unknown help topic 'banana'.", completed.stderr)
        self.assertIn("OFGS (OpenFOAM Gnuplot Suite)", completed.stdout)
        self.assertIn("Commands", completed.stdout)

    def test_clean_force_removes_only_generated_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "monitor.gp").write_text("dashboard")
            (root / "graphs").mkdir()
            (root / "graphs" / "01.gp").write_text("graph")
            protected = (
                "postProcessing",
                "processor0",
                "logs",
                "system",
                "constant",
                "0",
            )
            for name in protected:
                path = root / name
                path.mkdir()
                (path / "keep").write_text(name)

            completed = subprocess.run(
                [str(WRAPPER), "clean", "--force"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse((root / "monitor.gp").exists())
            self.assertFalse((root / "graphs").exists())
            self.assertEqual(
                completed.stdout,
                "Removed:\n\n"
                "  monitor.gp\n"
                "  graphs/\n\n"
                "OFGS generated files removed successfully.\n",
            )
            for name in protected:
                self.assertEqual((root / name / "keep").read_text(), name)

    def test_clean_reports_exact_single_target(self):
        cases = {
            "monitor.gp": (
                "Removed:\n\n"
                "  monitor.gp\n\n"
                "OFGS generated files removed successfully.\n"
            ),
            "graphs/": (
                "Removed:\n\n"
                "  graphs/\n\n"
                "OFGS generated files removed successfully.\n"
            ),
        }

        for target, expected_output in cases.items():
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if target == "monitor.gp":
                    (root / target).write_text("dashboard")
                else:
                    (root / "graphs").mkdir()

                completed = subprocess.run(
                    [str(WRAPPER), "clean", "--force"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, expected_output)

    def test_clean_confirmation_and_empty_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "monitor.gp").write_text("dashboard")
            (root / "graphs").mkdir()

            declined = subprocess.run(
                [str(WRAPPER), "clean"],
                cwd=root,
                input="n\n",
                capture_output=True,
                text=True,
            )
            self.assertEqual(declined.returncode, 1)
            self.assertTrue((root / "monitor.gp").exists())
            self.assertTrue((root / "graphs").exists())
            self.assertIn("Continue? [y/N]", declined.stdout)

            accepted = subprocess.run(
                [str(WRAPPER), "clean"],
                cwd=root,
                input="Y\n",
                capture_output=True,
                text=True,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertFalse((root / "monitor.gp").exists())
            self.assertFalse((root / "graphs").exists())

            empty = subprocess.run(
                [str(WRAPPER), "clean"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertEqual(empty.stdout, "No OFGS generated files found.\n")

    def _doctor_wrapper(self, root):
        gnuplot_bin = root / "doctor-bin"
        gnuplot_bin.mkdir()
        fake_gnuplot = gnuplot_bin / "gnuplot"
        fake_gnuplot.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake_gnuplot.chmod(0o755)
        test_wrapper = root / "ofgs"
        test_wrapper.write_text(
            WRAPPER.read_text().replace(
                'OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@',
                f'OFGS_INSTALL_DIR="{PROJECT_ROOT}"',
                1,
            )
        )
        test_wrapper.chmod(0o755)
        return test_wrapper, path_with(gnuplot_bin)

    def test_doctor_valid_case_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_wrapper, environment = self._doctor_wrapper(root)
            (root / "system").mkdir()
            (root / "constant").mkdir()
            dataset_directory = root / "postProcessing" / "outlet" / "1"
            dataset_directory.mkdir(parents=True)
            (dataset_directory / "surfaceFieldValue.dat").write_text(
                "# Time value\n0 1\n"
            )
            (root / "monitor.gp").write_text("dashboard")
            (root / "graphs").mkdir()
            (root / "graphs" / "index.txt").write_text(
                "01 first graph\n02 second graph\n"
            )
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            completed = subprocess.run(
                [str(test_wrapper), "doctor"],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
            )

            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(before, after)
            self.assertIn("[PASS] OFGS installation found", completed.stdout)
            self.assertIn("[PASS] GNUPlot executable found", completed.stdout)
            self.assertIn("[PASS] Python 3 available", completed.stdout)
            self.assertIn("[PASS] Supported datasets detected.", completed.stdout)
            self.assertIn("Generated graphs: 2", completed.stdout)
            self.assertIn("Doctor completed successfully.", completed.stdout)
            self.assertNotIn("\033[", completed.stdout)

    def test_doctor_outside_case_and_missing_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_wrapper, environment = self._doctor_wrapper(root)

            outside = subprocess.run(
                [str(test_wrapper), "doctor"],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(outside.returncode, 1)
            self.assertIn(
                "[FAIL] Current directory is not an OpenFOAM case.",
                outside.stdout,
            )
            self.assertIn("Doctor found errors.", outside.stdout)
            self.assertNotIn("\033[", outside.stdout)

            (root / "system").mkdir()
            (root / "constant").mkdir()
            valid_without_output = subprocess.run(
                [str(test_wrapper), "doctor"],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(valid_without_output.returncode, 0)
            self.assertIn(
                "[WARN] Dashboard has not been generated.",
                valid_without_output.stdout,
            )
            self.assertIn(
                "[WARN] No supported datasets detected.",
                valid_without_output.stdout,
            )
            self.assertIn("Doctor completed with warnings.", valid_without_output.stdout)
            self.assertNotIn("\033[", valid_without_output.stdout)

    def test_doctor_colours_only_status_tags_on_terminal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_wrapper, environment = self._doctor_wrapper(root)

            error_status, error_output = run_with_terminal_stdout(
                [str(test_wrapper), "doctor"],
                root,
                environment,
            )
            self.assertEqual(error_status, 1)
            self.assertIn(
                "\033[32m[PASS]\033[0m OFGS installation found",
                error_output,
            )
            self.assertIn(
                "\033[31m[FAIL]\033[0m Current directory is not an OpenFOAM case.",
                error_output,
            )

            (root / "system").mkdir()
            (root / "constant").mkdir()
            warning_status, warning_output = run_with_terminal_stdout(
                [str(test_wrapper), "doctor"],
                root,
                environment,
            )
            self.assertEqual(warning_status, 0)
            self.assertIn(
                "\033[33m[WARN]\033[0m Dashboard has not been generated.",
                warning_output,
            )


if __name__ == "__main__":
    unittest.main()
