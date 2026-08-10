import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def relocated_script(source, root, project_root=None):
    install_dir = root / "share" / "ofgs"
    bin_dir = root / "bin"
    text = source.read_text()
    if project_root is not None:
        text = text.replace(
            'project_root="$(cd "$(dirname "$0")" && pwd)"',
            f'project_root="{project_root}"',
            1,
        )
    return (
        text.replace(
            'INSTALL_DIR="/usr/local/share/ofgs"',
            f'INSTALL_DIR="{install_dir}"',
            1,
        )
        .replace(
            'wrapper_target="/usr/local/bin/ofgs"',
            f'wrapper_target="{bin_dir / "ofgs"}"',
            1,
        )
        .replace(
            'legacy_wrapper_target="/usr/local/bin/gnuplot"',
            f'legacy_wrapper_target="{bin_dir / "gnuplot"}"',
            1,
        )
        .replace(
            'install -d /usr/local/bin "$INSTALL_DIR/core"',
            f'install -d "{bin_dir}" "$INSTALL_DIR/core"',
            1,
        )
    )


class InstallationTests(unittest.TestCase):
    def test_update_installs_renamed_generator_and_removes_legacy_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            install_dir = root / "share" / "ofgs"
            bin_dir = root / "bin"
            install_dir.mkdir(parents=True)
            bin_dir.mkdir()
            legacy_generator = install_dir / "gnuplot_generate.py"
            legacy_generator.write_text("legacy generator")
            (bin_dir / "ofgs").write_text("# ofgs-wrapper\n")
            legacy_wrapper = bin_dir / "gnuplot"
            legacy_wrapper.write_text("# gnuplot-generator-wrapper\n")
            install_script = root / "install.sh"
            install_script.write_text(
                relocated_script(
                    PROJECT_ROOT / "install.sh",
                    root,
                    project_root=PROJECT_ROOT,
                )
            )

            completed = subprocess.run(
                ["/bin/bash", str(install_script), "--force"],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((install_dir / "ofgs_generate.py").is_file())
            self.assertFalse(legacy_generator.exists())
            self.assertFalse(legacy_wrapper.exists())
            self.assertIn(
                "ofgs_generate.py",
                (bin_dir / "ofgs").read_text(),
            )

    def test_uninstall_removes_ofgs_layout_but_not_unknown_gnuplot(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            install_dir = root / "share" / "ofgs"
            bin_dir = root / "bin"
            install_dir.mkdir(parents=True)
            bin_dir.mkdir()
            (install_dir / "ofgs_generate.py").write_text("installed generator")
            (install_dir / "gnuplot_generate.py").write_text("legacy generator")
            (bin_dir / "ofgs").write_text("# ofgs-wrapper\n")
            system_gnuplot = bin_dir / "gnuplot"
            system_gnuplot.write_text("genuine gnuplot")
            uninstall_script = root / "uninstall.sh"
            uninstall_script.write_text(
                relocated_script(PROJECT_ROOT / "uninstall.sh", root)
            )

            completed = subprocess.run(
                ["/bin/bash", str(uninstall_script)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(install_dir.exists())
            self.assertFalse((bin_dir / "ofgs").exists())
            self.assertEqual(system_gnuplot.read_text(), "genuine gnuplot")


if __name__ == "__main__":
    unittest.main()
