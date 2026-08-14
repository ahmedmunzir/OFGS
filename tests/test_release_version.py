import re
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "release_version.py"
README = PROJECT_ROOT / "README.md"


def run_script(*arguments):
    return subprocess.run(
        ["python3", str(SCRIPT), *map(str, arguments)],
        capture_output=True,
        text=True,
    )


class ReleaseVersionTests(unittest.TestCase):
    def test_tracked_readme_presents_current_release_and_history(self):
        readme = README.read_text()
        heading = re.match(
            r"\A# OFGS \(OpenFOAM Gnuplot Suite\) v([0-9]+\.[0-9]+\.[0-9]+)\n",
            readme,
        )
        self.assertIsNotNone(heading)
        current_version = heading.group(1)

        self.assertEqual(readme.count("## Changelog\n"), 1)
        changelog = readme.split("## Changelog\n", 1)[1]
        current_marker = (
            f"<details open>\n"
            f"<summary><strong>v{current_version}</strong></summary>"
        )
        previous_marker = (
            "<details>\n"
            "<summary><strong>Previous Releases</strong></summary>"
        )
        self.assertTrue(changelog.startswith(f"\n{current_marker}\n"))
        self.assertEqual(changelog.count("<details open>"), 1)
        self.assertIn(previous_marker, changelog)

        current = changelog.index(current_marker)
        current_end = changelog.index("</details>", current)
        previous = changelog.index(previous_marker)
        self.assertLess(current, current_end)
        self.assertLess(current_end, previous)

        releases = re.findall(
            r"<summary><strong>v([0-9]+\.[0-9]+\.[0-9]+)</strong></summary>",
            changelog,
        )
        self.assertGreaterEqual(len(releases), 2)
        self.assertEqual(releases[0], current_version)
        self.assertLess(previous, changelog.index(f"<strong>v{releases[1]}</strong>"))

        release_versions = [
            tuple(map(int, release.split("."))) for release in releases
        ]
        self.assertEqual(release_versions, sorted(release_versions, reverse=True))
        self.assertEqual(len(release_versions), len(set(release_versions)))

    def test_accepts_only_strict_release_tags(self):
        accepted = run_script("v12.34.56")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout, "12.34.56\n")

        for tag in (
            "12.34.56",
            "v12.34",
            "v12.34.56-rc1",
            "v012.34.56",
            "v12.034.56",
            "v12.34.056",
            "v12.34.56\n",
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
