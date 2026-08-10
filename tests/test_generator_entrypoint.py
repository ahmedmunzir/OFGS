import contextlib
import fcntl
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import ofgs_generate
from core.dataset_parser import ScalarTimeSeriesDataset
from core.generator import write_monitor
from core.parser import parse_function_object_configurations


class GeneratorEntrypointTests(unittest.TestCase):
    def _run_in_case(self, case):
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous_directory = Path.cwd()
        try:
            os.chdir(case)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = ofgs_generate.entrypoint()
        finally:
            os.chdir(previous_directory)
        return status, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def _write_control(case, body):
        system_path = case / "system"
        system_path.mkdir(exist_ok=True)
        control = system_path / "controlDict"
        control.write_text(body)
        return control

    def test_supported_function_object_configuration_is_parsed(self):
        configurations = parse_function_object_configurations(
            "functions\n{\n"
            "  outlet\n  {\n    type surfaceFieldValue;\n  }\n"
            "  disabledLimits\n  {\n    type fieldMinMax;\n    enabled false;\n  }\n"
            "}\n"
        )

        self.assertEqual(
            configurations,
            {
                "outlet": {"type": "surfaceFieldValue", "enabled": True},
                "disabledLimits": {"type": "fieldMinMax", "enabled": False},
            },
        )

    def test_generate_prints_concise_dynamic_summary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            system_path = case / "system"
            system_path.mkdir()
            control = system_path / "controlDict"
            control.write_text("functions\n{\n}\n")
            output_path = case / "postProcessing" / "outlet" / "1"
            output_path.mkdir(parents=True)
            (output_path / "surfaceFieldValue.dat").write_text(
                "# Time pressure temperature\n0 1 300\n"
            )

            stdout = io.StringIO()
            previous_directory = Path.cwd()
            try:
                os.chdir(case)
                with contextlib.redirect_stdout(stdout):
                    ofgs_generate.main()
            finally:
                os.chdir(previous_directory)

            self.assertEqual(
                stdout.getvalue(),
                "OFGS - OpenFOAM Gnuplot Suite\n\n"
                f"Case: {case.name}\n\n"
                "Discovering datasets...\n"
                "Found 2 supported graphs.\n\n"
                "Generated:\n"
                "  monitor.gp\n"
                "  graphs/ (2 graphs)\n\n"
                "Generation complete.\n",
            )
            for removed_output in (
                "CORE POWER",
                "Function objects found",
                "Post-processing output",
                "Columns",
                "Headers",
                "First row",
                "ScalarTimeSeriesDataset",
                "source =",
            ):
                self.assertNotIn(removed_output, stdout.getvalue())

    def test_non_openfoam_directory_returns_failure_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 1)
            self.assertIn("controlDict not found", stderr)
            self.assertIn("does not appear to be an OpenFOAM case", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_missing_control_dict_returns_failure_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            (case / "system").mkdir()
            (case / "constant").mkdir()

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 1)
            self.assertIn("system/controlDict not found", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_expected_filesystem_error_returns_failure_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(
            ofgs_generate,
            "main",
            side_effect=PermissionError("generation output is not writable"),
        ):
            with contextlib.redirect_stderr(stderr):
                status = ofgs_generate.entrypoint()

        self.assertEqual(status, 1)
        self.assertEqual(stderr.getvalue(), "generation output is not writable\n")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_keyboard_interrupt_exits_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(ofgs_generate, "main", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(stderr):
                status = ofgs_generate.entrypoint()

        self.assertEqual(status, 130)
        self.assertEqual(stderr.getvalue(), "")

    def test_atomic_publication_error_exits_cleanly(self):
        stderr = io.StringIO()
        error = ofgs_generate.AtomicPublicationError(
            "OFGS error: atomic publication unavailable."
        )
        with patch.object(ofgs_generate, "main", side_effect=error):
            with contextlib.redirect_stderr(stderr):
                status = ofgs_generate.entrypoint()

        self.assertEqual(status, 1)
        self.assertEqual(
            stderr.getvalue(),
            "OFGS error: atomic publication unavailable.\n",
        )

    def test_expected_header_only_input_fails_and_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(
                case,
                "functions\n{\noutlet\n{\ntype surfaceFieldValue;\n}\n}\n",
            )
            write_monitor(
                case,
                [
                    ScalarTimeSeriesDataset("old one", (0.0,), {"value": (1.0,)}),
                    ScalarTimeSeriesDataset("old two", (0.0,), {"value": (2.0,)}),
                ],
            )
            latest = case / "postProcessing" / "outlet" / "1"
            latest.mkdir(parents=True)
            (latest / "surfaceFieldValue.dat").write_text("# Time value\n")
            previous = {
                case / "monitor.gp": (case / "monitor.gp").read_text(),
                case / "graphs" / "index.txt": (case / "graphs" / "index.txt").read_text(),
                case / "graphs" / "01.gp": (case / "graphs" / "01.gp").read_text(),
                case / "graphs" / "02.gp": (case / "graphs" / "02.gp").read_text(),
            }

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 1)
            self.assertIn("post-processing data is incomplete", stderr)
            self.assertIn("Existing generated graphs have been preserved.", stderr)
            self.assertNotIn("Traceback", stderr)
            for path, contents in previous.items():
                self.assertEqual(path.read_text(), contents)

    def test_expected_supported_file_missing_returns_clean_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(
                case,
                "functions\n{\nlimits\n{\ntype fieldMinMax;\n}\n}\n",
            )
            (case / "postProcessing" / "limits" / "1").mkdir(parents=True)

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 1)
            self.assertIn("post-processing data is incomplete", stderr)
            self.assertIn("Generation was not performed.", stderr)
            self.assertNotIn("Traceback", stderr)
            self.assertFalse((case / "monitor.gp").exists())

    def test_expected_empty_supported_file_returns_clean_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(
                case,
                "functions\n{\noutlet\n{\ntype surfaceFieldValue;\n}\n}\n",
            )
            latest = case / "postProcessing" / "outlet" / "1"
            latest.mkdir(parents=True)
            (latest / "surfaceFieldValue.dat").write_text("")

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 1)
            self.assertIn("post-processing data is incomplete", stderr)
            self.assertNotIn("Traceback", stderr)
            self.assertFalse((case / "monitor.gp").exists())

    def test_file_change_during_parsing_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(case, "functions\n{\n}\n")
            latest = case / "postProcessing" / "outlet" / "1"
            latest.mkdir(parents=True)
            source = latest / "surfaceFieldValue.dat"
            source.write_text("# Time value\n0 1\n")
            write_monitor(
                case,
                [ScalarTimeSeriesDataset("previous", (0.0,), {"value": (1.0,)})],
            )
            previous_monitor = (case / "monitor.gp").read_text()
            previous_index = (case / "graphs" / "index.txt").read_text()
            real_parse = ofgs_generate.parse_datasets

            def parse_then_change(outputs):
                datasets = real_parse(outputs)
                source.write_text("# Time value\n0 1\n1 2\n")
                return datasets

            previous_directory = Path.cwd()
            try:
                os.chdir(case)
                stderr = io.StringIO()
                stdout = io.StringIO()
                with patch.object(
                    ofgs_generate, "parse_datasets", side_effect=parse_then_change
                ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    status = ofgs_generate.entrypoint()
            finally:
                os.chdir(previous_directory)

            self.assertEqual(status, 1)
            self.assertIn("changed during generation", stderr.getvalue())
            self.assertEqual((case / "monitor.gp").read_text(), previous_monitor)
            self.assertEqual((case / "graphs" / "index.txt").read_text(), previous_index)

    def test_configuration_removal_can_publish_smaller_valid_set(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(
                case,
                "functions\n{\noutlet\n{\ntype surfaceFieldValue;\n}\n}\n",
            )
            write_monitor(
                case,
                [
                    ScalarTimeSeriesDataset("old one", (0.0,), {"value": (1.0,)}),
                    ScalarTimeSeriesDataset("old two", (0.0,), {"value": (2.0,)}),
                ],
            )
            latest = case / "postProcessing" / "outlet" / "1"
            latest.mkdir(parents=True)
            (latest / "surfaceFieldValue.dat").write_text("# Time value\n0 3\n")

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 0, stderr)
            self.assertEqual(
                (case / "graphs" / "index.txt").read_text(), "01 outlet\n"
            )
            self.assertFalse((case / "graphs" / "02.gp").exists())

    def test_first_expected_generation_with_one_sample_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(
                case,
                "functions\n{\noutlet\n{\ntype surfaceFieldValue;\n}\n}\n",
            )
            latest = case / "postProcessing" / "outlet" / "1"
            latest.mkdir(parents=True)
            (latest / "surfaceFieldValue.dat").write_text("# Time value\n0 3\n")

            status, _stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 0, stderr)
            self.assertTrue((case / "monitor.gp").is_file())
            self.assertTrue((case / "graphs" / "01.gp").is_file())

    def test_genuine_zero_supported_datasets_does_not_claim_generation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            self._write_control(case, "functions\n{\n}\n")
            latest = case / "postProcessing" / "unsupported" / "1"
            latest.mkdir(parents=True)
            (latest / "otherOutput.dat").write_text("incomplete but unsupported")

            status, stdout, stderr = self._run_in_case(case)

            self.assertEqual(status, 0, stderr)
            self.assertIn("Found 0 supported graphs.", stdout)
            self.assertIn("No supported OFGS datasets found. Nothing was generated.", stdout)
            self.assertNotIn("Generation complete.", stdout)
            self.assertFalse((case / "monitor.gp").exists())

    def test_concurrent_same_case_generation_waits_without_removing_graphs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            datasets = [
                ScalarTimeSeriesDataset(
                    f"parent quantity {number:02d}",
                    (0.0,),
                    {"value": (float(number),)},
                )
                for number in range(1, 12)
            ]
            write_monitor(case, datasets)
            requested_graph = case / "graphs" / "11.gp"

            child_code = textwrap.dedent(
                """
                import fcntl
                from pathlib import Path
                import sys

                from core.dataset_parser import ScalarTimeSeriesDataset
                from core.generator import write_monitor
                from ofgs_generate import generation_lock

                case = Path(sys.argv[1])
                with (case / ".ofgs-generation.lock").open("a") as probe:
                    try:
                        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        print("BLOCKED", flush=True)
                    else:
                        print("NOT BLOCKED", flush=True)
                        raise SystemExit(3)

                with generation_lock(case):
                    datasets = [
                        ScalarTimeSeriesDataset(
                            f"child quantity {number:02d}",
                            (0.0,),
                            {"value": (float(number),)},
                        )
                        for number in range(1, 12)
                    ]
                    write_monitor(case, datasets)
                print("PUBLISHED", flush=True)
                """
            )

            with ofgs_generate.generation_lock(case):
                child = subprocess.Popen(
                    [sys.executable, "-c", child_code, str(case)],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertEqual(child.stdout.readline().strip(), "BLOCKED")
                self.assertTrue(requested_graph.is_file())
                write_monitor(case, datasets)
                self.assertTrue(requested_graph.is_file())

            stdout, stderr = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertIn("PUBLISHED", stdout)
            self.assertTrue(requested_graph.is_file())
            indexed_ids = {
                line.split(maxsplit=1)[0]
                for line in (case / "graphs" / "index.txt").read_text().splitlines()
            }
            published_ids = {
                path.stem
                for path in (case / "graphs").glob("*.gp")
                if path.stem.isdigit()
            }
            self.assertEqual(indexed_ids, published_ids)

    def test_generation_locks_are_case_specific(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_case = root / "first"
            second_case = root / "second"
            first_case.mkdir()
            second_case.mkdir()
            child_code = textwrap.dedent(
                """
                from pathlib import Path
                import sys

                from ofgs_generate import generation_lock

                with generation_lock(Path(sys.argv[1])):
                    print("ACQUIRED")
                """
            )

            with ofgs_generate.generation_lock(first_case):
                completed = subprocess.run(
                    [sys.executable, "-c", child_code, str(second_case)],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "ACQUIRED\n")

    def test_generation_lock_is_released_when_process_exits(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            case = Path(temporary_directory)
            child_code = textwrap.dedent(
                """
                import os
                from pathlib import Path
                import sys

                from ofgs_generate import generation_lock

                with generation_lock(Path(sys.argv[1])):
                    print("ACQUIRED", flush=True)
                    os._exit(9)
                """
            )
            child = subprocess.run(
                [sys.executable, "-c", child_code, str(case)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(child.returncode, 9)
            self.assertEqual(child.stdout, "ACQUIRED\n")

            lock_path = case / ".ofgs-generation.lock"
            with lock_path.open("a") as probe:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
