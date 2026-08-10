import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "packaging" / "rpm" / "ofgs.spec"
EXPECTED_RUNTIME_FILES = {
    Path("usr/bin/ofgs"),
    Path("usr/share/ofgs/ofgs_generate.py"),
    Path("usr/share/ofgs/core/__init__.py"),
    Path("usr/share/ofgs/core/dataset_parser.py"),
    Path("usr/share/ofgs/core/discovery.py"),
    Path("usr/share/ofgs/core/generator.py"),
    Path("usr/share/ofgs/core/parser.py"),
}


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def spec_preamble(text):
    return text.split("%description", 1)[0]


def spec_fields(text, field):
    pattern = rf"^{re.escape(field)}:\s*(.*?)\s*$"
    return re.findall(pattern, spec_preamble(text), re.MULTILINE)


def spec_section(text, name, following_name):
    match = re.search(
        rf"^%{name}\s*$\n(.*?)(?=^%{following_name}\s*$)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing %{name} section")
    return match.group(1)


class RpmPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = SPEC_PATH.read_text()

    def test_package_metadata(self):
        expected_fields = {
            "Name": ["ofgs"],
            "Version": ["%{upstream_version}"],
            "Release": ["1%{?dist}"],
            "Summary": ["OpenFOAM graph generation and monitoring suite"],
            "License": ["MIT"],
            "URL": ["https://github.com/ahmedmunzir/OFGS"],
            "BuildArch": ["noarch"],
        }
        for field, expected in expected_fields.items():
            self.assertEqual(spec_fields(self.spec, field), expected)

        self.assertIn(
            "%{!?upstream_version:%global upstream_version 2.2.1}",
            self.spec,
        )

        self.assertEqual(
            spec_fields(self.spec, "Source0"),
            [
                "%{url}/archive/refs/tags/v%{version}.tar.gz"
                "#/%{name}-%{version}.tar.gz"
            ],
        )

    def test_build_and_runtime_dependencies(self):
        build_requires = spec_fields(self.spec, "BuildRequires")
        requires = spec_fields(self.spec, "Requires")

        for dependency in ("bash", "coreutils", "make", "python3 >= 3.9"):
            self.assertIn(dependency, build_requires)
        for dependency in (
            "bash",
            "coreutils",
            "gnuplot >= 5.4",
            "python3 >= 3.9",
            "sed",
        ):
            self.assertIn(dependency, requires)

        dependency_text = "\n".join(requires).lower()
        self.assertNotIn("gnuplot-qt", dependency_text)
        self.assertNotIn("openfoam", dependency_text)

    def test_install_reuses_shared_staging_architecture(self):
        install_section = spec_section(self.spec, "install", "check")

        self.assertIn(
            "%{__make} install PREFIX=%{_prefix} DESTDIR=%{buildroot}",
            install_section,
        )
        self.assertEqual(install_section.count("%{__make} install"), 1)
        for runtime_filename in (
            "ofgs_generate.py",
            "dataset_parser.py",
            "discovery.py",
            "generator.py",
            "parser.py",
        ):
            self.assertNotIn(runtime_filename, install_section)
        self.assertNotIn("/usr/local", install_section)

    def test_runtime_payload_and_documentation(self):
        files_section = spec_section(self.spec, "files", "changelog")

        self.assertIn("%{_bindir}/ofgs", files_section)
        self.assertIn("%{_datadir}/ofgs/", files_section)
        self.assertIn("%{_mandir}/man1/ofgs.1*", files_section)
        self.assertIn("%license LICENSE", files_section)
        self.assertIn("%doc README.md", files_section)
        self.assertIn(
            "install -Dpm 0644 docs/ofgs.1 "
            "%{buildroot}%{_mandir}/man1/ofgs.1",
            spec_section(self.spec, "install", "check"),
        )

        for excluded in (
            "tests/",
            "install.sh",
            "uninstall.sh",
            "scripts/install_runtime.py",
            "Makefile",
            "wrapper/ofgs",
        ):
            self.assertNotIn(excluded, files_section)
        self.assertNotIn("/usr/local", files_section)

    def test_no_package_lifecycle_scriptlets(self):
        for scriptlet in ("pre", "post", "preun", "postun"):
            self.assertNotRegex(self.spec, rf"(?m)^%{scriptlet}(?:\s|$)")

    def test_shared_installer_stages_exact_rpm_runtime(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            completed = subprocess.run(
                ["make", "install", "PREFIX=/usr", f"DESTDIR={root}"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            installed_files = {
                path.relative_to(root) for path in root.rglob("*") if path.is_file()
            }
            self.assertEqual(installed_files, EXPECTED_RUNTIME_FILES)
            self.assertFalse((root / "usr" / "local").exists())

            wrapper = root / "usr" / "bin" / "ofgs"
            wrapper_text = wrapper.read_text()
            self.assertEqual(mode(wrapper), 0o755)
            self.assertIn('OFGS_INSTALL_DIR=/usr/share/ofgs', wrapper_text)
            self.assertNotIn("/usr/local/share/ofgs", wrapper_text)
            self.assertNotIn(str(root), wrapper_text)

            runtime_python_invocations = [
                line
                for line in wrapper_text.splitlines()
                if "python3" in line and "$OFGS_INSTALL_DIR" in line
            ]
            self.assertEqual(len(runtime_python_invocations), 3)
            self.assertTrue(
                all("python3 -B" in line for line in runtime_python_invocations)
            )

            for relative_path in EXPECTED_RUNTIME_FILES - {Path("usr/bin/ofgs")}:
                self.assertEqual(mode(root / relative_path), 0o644)
            self.assertFalse(
                (root / "usr/share/ofgs/ofgs_generate.py")
                .read_text()
                .startswith("#!")
            )

    def test_man_page_source_and_debian_packaging_remain_present(self):
        man_page = PROJECT_ROOT / "docs" / "ofgs.1"

        self.assertTrue(man_page.is_file())
        self.assertRegex(man_page.read_text(), r"^\.TH OFGS 1 ")
        self.assertEqual(
            (PROJECT_ROOT / "debian" / "manpages").read_text().splitlines(),
            ["docs/ofgs.1"],
        )
        self.assertIn(
            "$(MAKE) install PREFIX=/usr DESTDIR=$(CURDIR)/debian/ofgs",
            (PROJECT_ROOT / "debian" / "rules").read_text(),
        )


if __name__ == "__main__":
    unittest.main()
