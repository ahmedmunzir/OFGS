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

import gnuplot_generate
from core.dataset_parser import ScalarTimeSeriesDataset
from core.generator import write_monitor


class GeneratorEntrypointTests(unittest.TestCase):
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
                    gnuplot_generate.main()
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

    def test_keyboard_interrupt_exits_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(gnuplot_generate, "main", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(stderr):
                status = gnuplot_generate.entrypoint()

        self.assertEqual(status, 130)
        self.assertEqual(stderr.getvalue(), "")

    def test_atomic_publication_error_exits_cleanly(self):
        stderr = io.StringIO()
        error = gnuplot_generate.AtomicPublicationError(
            "OFGS error: atomic publication unavailable."
        )
        with patch.object(gnuplot_generate, "main", side_effect=error):
            with contextlib.redirect_stderr(stderr):
                status = gnuplot_generate.entrypoint()

        self.assertEqual(status, 1)
        self.assertEqual(
            stderr.getvalue(),
            "OFGS error: atomic publication unavailable.\n",
        )

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
                from gnuplot_generate import generation_lock

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

            with gnuplot_generate.generation_lock(case):
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

                from gnuplot_generate import generation_lock

                with generation_lock(Path(sys.argv[1])):
                    print("ACQUIRED")
                """
            )

            with gnuplot_generate.generation_lock(first_case):
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

                from gnuplot_generate import generation_lock

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
