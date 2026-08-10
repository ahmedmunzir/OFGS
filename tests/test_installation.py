import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = {
    "__init__.py",
    "dataset_parser.py",
    "discovery.py",
    "generator.py",
    "parser.py",
}


def run_make_install(prefix, destdir=""):
    return subprocess.run(
        ["make", "install", f"PREFIX={prefix}", f"DESTDIR={destdir}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def relocated_manual_script(source, root, project_root=None):
    manual_prefix = root / "usr" / "local"
    install_dir = manual_prefix / "share" / "ofgs"
    bin_dir = manual_prefix / "bin"
    text = source.read_text()
    if project_root is not None:
        text = text.replace(
            'project_root="$(cd "$(dirname "$0")" && pwd)"',
            f'project_root="{project_root}"',
            1,
        )
    text = (
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
    )
    if source.name == "install.sh":
        text = text.replace(
            'python3 "$project_root/scripts/install_runtime.py" --prefix /usr/local',
            'python3 "$project_root/scripts/install_runtime.py" '
            f'--prefix /usr/local --destdir "{root}"',
            1,
        )
    return text


def file_mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def tree_snapshot(root):
    snapshot = {}
    for path in root.rglob("*"):
        relative_path = path.relative_to(root)
        if path.is_file():
            snapshot[relative_path] = ("file", file_mode(path), path.read_bytes())
        elif path.is_dir():
            snapshot[relative_path] = ("directory", file_mode(path))
    return snapshot


class InstallationTests(unittest.TestCase):
    def assert_staged_layout(self, root, prefix):
        staged_prefix = root / prefix.relative_to("/")
        wrapper = staged_prefix / "bin" / "ofgs"
        runtime = staged_prefix / "share" / "ofgs"

        self.assertTrue(wrapper.is_file())
        self.assertTrue((runtime / "ofgs_generate.py").is_file())
        self.assertEqual(
            {path.name for path in runtime.iterdir()}, {"ofgs_generate.py", "core"}
        )
        self.assertEqual(
            {path.name for path in (runtime / "core").iterdir()}, CORE_FILES
        )
        self.assertFalse((runtime / "README.md").exists())

        wrapper_text = wrapper.read_text()
        installed_runtime = prefix / "share" / "ofgs"
        self.assertIn(str(installed_runtime), wrapper_text)
        self.assertNotIn(str(root), wrapper_text)
        self.assertNotIn("@OFGS_INSTALL_DIR@", wrapper_text)

        self.assertEqual(file_mode(wrapper), 0o755)
        self.assertEqual(file_mode(wrapper.parent), 0o755)
        self.assertEqual(file_mode(runtime), 0o755)
        self.assertEqual(file_mode(runtime / "core"), 0o755)
        self.assertEqual(file_mode(runtime / "ofgs_generate.py"), 0o644)
        self.assertFalse(
            (runtime / "ofgs_generate.py").read_text().startswith("#!")
        )
        for filename in CORE_FILES:
            self.assertEqual(file_mode(runtime / "core" / filename), 0o644)

    def test_make_install_stages_manual_and_package_layouts(self):
        for prefix in (Path("/usr/local"), Path("/usr")):
            with self.subTest(prefix=str(prefix)):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    completed = run_make_install(prefix, root)

                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assert_staged_layout(root, prefix)

    def test_installed_wrapper_does_not_write_bytecode_into_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            prefix = root / "prefix with spaces"
            completed = run_make_install(prefix)
            self.assertEqual(completed.returncode, 0, completed.stderr)

            wrapper = prefix / "bin" / "ofgs"
            runtime = prefix / "share" / "ofgs"
            empty_directory = root / "not-an-openfoam-case"
            empty_directory.mkdir()
            runtime_before = tree_snapshot(runtime)
            generated = subprocess.run(
                [str(wrapper), "generate"],
                cwd=empty_directory,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(generated.returncode, 0)
            self.assertIn("OFGS - OpenFOAM Gnuplot Suite", generated.stdout)
            self.assertNotIn("OFGS is not installed.", generated.stderr)
            self.assertEqual(tree_snapshot(runtime), runtime_before)

            live = subprocess.run(
                [str(wrapper), "monitor", "--live"],
                cwd=empty_directory,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(live.returncode, 0)
            self.assertEqual(tree_snapshot(runtime), runtime_before)
            self.assertFalse(any(runtime.rglob("__pycache__")))
            self.assertFalse(any(runtime.rglob("*.pyc")))

            wrapper_text = wrapper.read_text()
            self.assertIn(str(runtime), wrapper_text)
            self.assertIn(
                'python3 -B "$OFGS_INSTALL_DIR/ofgs_generate.py"',
                wrapper_text,
            )
            self.assertIn(
                'exec python3 -B "$OFGS_INSTALL_DIR/ofgs_generate.py"',
                wrapper_text,
            )

    def test_update_installs_renamed_generator_and_removes_legacy_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manual_prefix = root / "usr" / "local"
            install_dir = manual_prefix / "share" / "ofgs"
            bin_dir = manual_prefix / "bin"
            install_dir.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            legacy_generator = install_dir / "gnuplot_generate.py"
            legacy_generator.write_text("legacy generator")
            (bin_dir / "ofgs").write_text("# ofgs-wrapper\n")
            legacy_wrapper = bin_dir / "gnuplot"
            legacy_wrapper.write_text("# gnuplot-generator-wrapper\n")
            install_script = root / "install.sh"
            install_script.write_text(
                relocated_manual_script(
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
            wrapper_text = (bin_dir / "ofgs").read_text()
            self.assertIn("ofgs_generate.py", wrapper_text)
            self.assertIn("/usr/local/share/ofgs", wrapper_text)
            self.assertNotIn(str(root), wrapper_text)

    def test_install_script_delegates_to_manual_prefix(self):
        install_text = (PROJECT_ROOT / "install.sh").read_text()

        self.assertIn("--prefix /usr/local", install_text)
        self.assertNotIn("--prefix /usr ", install_text)
        self.assertIn('legacy_generator_target="$INSTALL_DIR/gnuplot_generate.py"', install_text)

    def test_uninstall_removes_only_manual_layout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manual_prefix = root / "usr" / "local"
            install_dir = manual_prefix / "share" / "ofgs"
            bin_dir = manual_prefix / "bin"
            package_runtime = root / "usr" / "share" / "ofgs"
            package_wrapper = root / "usr" / "bin" / "ofgs"

            install_dir.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            package_runtime.mkdir(parents=True)
            package_wrapper.parent.mkdir(parents=True, exist_ok=True)
            (install_dir / "ofgs_generate.py").write_text("manual generator")
            (install_dir / "gnuplot_generate.py").write_text("legacy generator")
            (bin_dir / "ofgs").write_text("# ofgs-wrapper\n")
            system_gnuplot = bin_dir / "gnuplot"
            system_gnuplot.write_text("genuine gnuplot")
            package_wrapper.write_text("# packaged ofgs-wrapper\n")
            (package_runtime / "ofgs_generate.py").write_text("package generator")

            uninstall_script = root / "uninstall.sh"
            uninstall_script.write_text(
                relocated_manual_script(PROJECT_ROOT / "uninstall.sh", root)
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
            self.assertEqual(package_wrapper.read_text(), "# packaged ofgs-wrapper\n")
            self.assertEqual(
                (package_runtime / "ofgs_generate.py").read_text(),
                "package generator",
            )


if __name__ == "__main__":
    unittest.main()
