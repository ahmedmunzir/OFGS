import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "release_version.py"
README = PROJECT_ROOT / "README.md"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"


def run_script(*arguments):
    return subprocess.run(
        ["python3", str(SCRIPT), *map(str, arguments)],
        capture_output=True,
        text=True,
    )


class ReleaseVersionTests(unittest.TestCase):
    def test_tracked_docs_present_v230_as_current_release(self):
        readme = README.read_text()
        self.assertTrue(
            readme.startswith("# OFGS (OpenFOAM Gnuplot Suite) v2.3.0\n")
        )
        self.assertNotIn("# Changelog", readme)
        changelog = CHANGELOG.read_text()
        self.assertTrue(changelog.startswith("# Changelog\n\n<details open>\n"))
        self.assertIn(
            "<details>\n<summary><strong>Previous Releases</strong></summary>",
            changelog,
        )
        current = changelog.index("<strong>v2.3.0</strong>")
        previous = changelog.index("<strong>Previous Releases</strong>")
        v221 = changelog.index("<strong>v2.2.1</strong>")
        v220 = changelog.index("<strong>v2.2.0</strong>")
        self.assertLess(current, previous)
        self.assertLess(previous, v221)
        self.assertLess(v221, v220)

    def test_accepts_only_strict_release_tags(self):
        accepted = run_script("v2.3.0")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout, "2.3.0\n")

        for tag in (
            "2.3.0",
            "v2.3",
            "v2.3.0-rc1",
            "v02.3.0",
            "v2.03.0",
            "v2.3.00",
            "v2.3.0\n",
        ):
            with self.subTest(tag=tag):
                rejected = run_script(tag)
                self.assertEqual(rejected.returncode, 1)
                self.assertIn("expected vMAJOR.MINOR.PATCH", rejected.stderr)

    def test_prepares_debian_generated_tree_without_touching_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            tree = Path(temporary_directory)
            (tree / "debian").mkdir()
            (tree / "docs").mkdir()
            (tree / "README.md").write_text(
                "# OFGS (OpenFOAM Gnuplot Suite) v2.2.1\n"
                "\n<summary><strong>v2.2.1</strong></summary>\n"
            )
            (tree / "docs" / "ofgs.1").write_text(
                '.TH OFGS 1 "August 2026" "OFGS 2.2.1" "User Commands"\n'
            )
            (tree / "debian" / "changelog").write_text(
                "ofgs (2.2.1-1) unstable; urgency=medium\n"
                "\n  * Initial Debian package.\n"
            )

            completed = run_script(
                "v2.3.0", "--prepare-tree", tree, "--format", "debian"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("v2.3.0", (tree / "README.md").read_text().splitlines()[0])
            self.assertIn(
                "<strong>v2.2.1</strong>", (tree / "README.md").read_text()
            )
            self.assertIn("OFGS 2.3.0", (tree / "docs" / "ofgs.1").read_text())
            self.assertTrue(
                (tree / "debian" / "changelog")
                .read_text()
                .startswith("ofgs (2.3.0-1) ")
            )

    def test_rpm_tree_keeps_debian_metadata_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            tree = Path(temporary_directory)
            (tree / "debian").mkdir()
            (tree / "docs").mkdir()
            (tree / "README.md").write_text(
                "# OFGS (OpenFOAM Gnuplot Suite) v2.2.1\n"
            )
            (tree / "docs" / "ofgs.1").write_text(
                '.TH OFGS 1 "August 2026" "OFGS 2.2.1" "User Commands"\n'
            )
            changelog = tree / "debian" / "changelog"
            changelog.write_text("ofgs (2.2.1-1) unstable; urgency=medium\n")

            completed = run_script(
                "v3.0.0", "--prepare-tree", tree, "--format", "rpm"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                changelog.read_text(),
                "ofgs (2.2.1-1) unstable; urgency=medium\n",
            )


if __name__ == "__main__":
    unittest.main()
