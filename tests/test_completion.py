import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SOURCE = PROJECT_ROOT / "wrapper" / "ofgs"
COMPLETION_SOURCE = PROJECT_ROOT / "completions" / "ofgs.bash"
PUBLIC_COMMANDS = {
    "generate",
    "monitor",
    "graph",
    "list",
    "clean",
    "doctor",
    "help",
}


def tree_snapshot(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class BashCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.invocation_log = self.root / "invocations.log"

        self.wrapper = self.bin_dir / "ofgs"
        self.wrapper.write_text(
            WRAPPER_SOURCE.read_text().replace(
                "OFGS_INSTALL_DIR=@OFGS_INSTALL_DIR@",
                f'OFGS_INSTALL_DIR="{PROJECT_ROOT}"',
                1,
            )
        )
        self.wrapper.chmod(0o755)
        for name in ("python3", "gnuplot"):
            executable = self.bin_dir / name
            executable.write_text(
                "#!/usr/bin/env bash\n"
                f'printf \'%s\\n\' "{name} $*" >> "{self.invocation_log}"\n'
                "exit 99\n"
            )
            executable.chmod(0o755)

        self.environment = os.environ.copy()
        self.environment["PATH"] = f"{self.bin_dir}:/usr/bin:/bin"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def complete(self, words, cword=None, cwd=None):
        if cword is None:
            cword = len(words) - 1
        script = r'''
source "$1"
cword="$2"
shift 2
COMP_CWORD="$cword"
COMP_WORDS=("$@")
_ofgs_completion
for reply in "${COMPREPLY[@]}"; do
    printf '%s\n' "$reply"
done
'''
        completed = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-c",
                script,
                "bash",
                str(COMPLETION_SOURCE),
                str(cword),
                *words,
            ],
            cwd=cwd or self.root,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        return completed.stdout.splitlines()

    def test_top_level_commands_and_partial_commands(self):
        self.assertEqual(set(self.complete(["ofgs", ""])), PUBLIC_COMMANDS)
        self.assertEqual(self.complete(["ofgs", "mon"]), ["monitor"])
        self.assertEqual(self.complete(["ofgs", "gen"]), ["generate"])

    def test_global_and_command_options(self):
        self.assertEqual(set(self.complete(["ofgs", "-"])), {"-h", "--help"})
        self.assertEqual(self.complete(["ofgs", "--"]), ["--help"])
        self.assertEqual(self.complete(["ofgs", "monitor", "--l"]), ["--live"])
        self.assertEqual(self.complete(["ofgs", "clean", "--f"]), ["--force"])
        self.assertEqual(self.complete(["ofgs", "graph", "1", "--l"]), ["--live"])

    def test_help_topics_come_from_the_public_command_set(self):
        self.assertEqual(
            set(self.complete(["ofgs", "help", ""])), PUBLIC_COMMANDS
        )
        self.assertEqual(self.complete(["ofgs", "help", "mon"]), ["monitor"])

    def test_terminal_states_and_argument_free_commands_suppress_files(self):
        for words in (
            ["ofgs", "generate", ""],
            ["ofgs", "list", ""],
            ["ofgs", "doctor", ""],
            ["ofgs", "monitor", "--live", ""],
            ["ofgs", "clean", "--force", ""],
            ["ofgs", "help", "monitor", ""],
            ["ofgs", "graph", "1", "--live", ""],
        ):
            with self.subTest(words=words):
                self.assertEqual(self.complete(words), [])

    def test_graph_ids_are_not_completed_or_read(self):
        graphs = self.root / "graphs"
        graphs.mkdir()
        index = graphs / "index.txt"
        os.mkfifo(index)
        (graphs / "91.gp").write_text("generated graph")

        self.assertEqual(self.complete(["ofgs", "graph", ""]), [])
        self.assertEqual(self.complete(["ofgs", "graph", "9"]), [])
        self.assertEqual(self.complete(["ofgs", "graph", "1,"]), [])
        self.assertNotIn("index.txt", COMPLETION_SOURCE.read_text())

    def test_graph_live_is_only_offered_after_valid_ids(self):
        self.assertEqual(self.complete(["ofgs", "graph", "",]), [])
        self.assertEqual(self.complete(["ofgs", "graph", "--"]), [])
        self.assertEqual(self.complete(["ofgs", "graph", "banana", ""]), [])
        self.assertEqual(self.complete(["ofgs", "graph", "1", ""]), ["--live"])
        self.assertEqual(
            self.complete(["ofgs", "graph", "1,2", "--"]), ["--live"]
        )

    def test_top_level_does_not_fall_back_to_files_but_explicit_paths_do(self):
        (self.root / "arbitrary-file").write_text("not a command")
        plots = self.root / "plots"
        plots.mkdir()
        (plots / "custom.gp").write_text("plot")

        self.assertEqual(set(self.complete(["ofgs", ""])), PUBLIC_COMMANDS)
        self.assertEqual(
            self.complete(["ofgs", "./plots/cu"]), ["./plots/custom.gp"]
        )

    def test_completion_is_read_only_and_invokes_no_programs(self):
        case = self.root / "case"
        case.mkdir()
        (case / "system").mkdir()
        (case / "constant").mkdir()
        graphs = case / "graphs"
        graphs.mkdir()
        (graphs / "index.txt").write_text("07 graph\n")
        before = tree_snapshot(case)

        for words in (
            ["ofgs", ""],
            ["ofgs", "monitor", "--"],
            ["ofgs", "graph", "7", ""],
            ["ofgs", "help", ""],
        ):
            self.complete(words, cwd=case)

        self.assertEqual(tree_snapshot(case), before)
        self.assertFalse((case / ".ofgs-generation.lock").exists())
        self.assertFalse((case / "monitor.gp").exists())
        self.assertFalse(self.invocation_log.exists())

    def test_completion_commands_match_cli_help(self):
        completed = subprocess.run(
            [str(self.wrapper), "help"],
            env=self.environment,
            capture_output=True,
            text=True,
            check=True,
        )
        help_commands = set(
            re.findall(r"^  ([a-z]+) {2,}", completed.stdout, re.MULTILINE)
        )
        self.assertEqual(help_commands, PUBLIC_COMMANDS)
        self.assertEqual(set(self.complete(["ofgs", ""])), help_commands)

    def test_private_completion_path_precedes_gnuplot_resolution(self):
        wrapper_text = WRAPPER_SOURCE.read_text()
        completion_dispatch = wrapper_text.index(
            'if [[ "${_OFGS_COMPLETE:-}" == bash ]]'
        )
        gnuplot_resolution = wrapper_text.index('REAL_GNUPLOT="$(resolve_gnuplot')
        self.assertLess(completion_dispatch, gnuplot_resolution)

    def test_normal_passthrough_is_unchanged(self):
        completed = subprocess.run(
            [str(self.wrapper), "custom.gp"],
            env=self.environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 99)
        self.assertEqual(self.invocation_log.read_text(), "gnuplot custom.gp\n")


if __name__ == "__main__":
    unittest.main()
