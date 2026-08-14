import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEBIAN_DIR = PROJECT_ROOT / "debian"
EXPECTED_RUNTIME_FILES = {
    Path("usr/bin/ofgs"),
    Path("usr/share/bash-completion/completions/ofgs"),
    Path("usr/share/ofgs/ofgs_generate.py"),
    Path("usr/share/ofgs/core/__init__.py"),
    Path("usr/share/ofgs/core/dataset_parser.py"),
    Path("usr/share/ofgs/core/discovery.py"),
    Path("usr/share/ofgs/core/generator.py"),
    Path("usr/share/ofgs/core/parser.py"),
}


def parse_control_stanzas(text):
    stanzas = []
    current = {}
    field = None
    for line in text.splitlines() + [""]:
        if not line:
            if current:
                stanzas.append(current)
                current = {}
                field = None
            continue
        if line[0].isspace():
            if field is None:
                raise AssertionError("control continuation without a field")
            current[field] += "\n" + line[1:]
            continue
        field, value = line.split(":", 1)
        current[field] = value.strip()
    return stanzas


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class DebianPackagingTests(unittest.TestCase):
    def test_control_metadata(self):
        source, binary = parse_control_stanzas(
            (DEBIAN_DIR / "control").read_text()
        )

        self.assertEqual(source["Source"], "ofgs")
        self.assertEqual(source["Section"], "science")
        self.assertEqual(source["Priority"], "optional")
        self.assertEqual(
            source["Maintainer"], "Munzir Ahmed <ahmedmunzir.ma@gmail.com>"
        )
        self.assertIn("debhelper-compat (= 13)", source["Build-Depends"])
        self.assertIn("python3 (>= 3.9)", source["Build-Depends"])
        self.assertEqual(source["Standards-Version"], "4.7.4")
        self.assertEqual(source["Rules-Requires-Root"], "no")

        self.assertEqual(binary["Package"], "ofgs")
        self.assertEqual(binary["Architecture"], "all")
        self.assertIn("python3 (>= 3.9)", binary["Depends"])
        self.assertIn("gnuplot-qt (>= 5.4)", binary["Depends"])
        self.assertEqual(binary["Recommends"], "bash-completion")
        self.assertNotIn("openfoam", binary["Depends"].lower())

    def test_version_source_format_and_license(self):
        changelog = (DEBIAN_DIR / "changelog").read_text()
        self.assertRegex(changelog.splitlines()[0], r"^ofgs \(2\.2\.1-1\) ")
        self.assertEqual(
            (DEBIAN_DIR / "source" / "format").read_text().strip(),
            "3.0 (quilt)",
        )

        copyright_text = (DEBIAN_DIR / "copyright").read_text()
        self.assertIn("Copyright: 2026 Munzir Ahmed", copyright_text)
        self.assertIn("License: MIT", copyright_text)
        self.assertIn("Permission is hereby granted, free of charge", copyright_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', copyright_text)

    def test_rules_reuse_shared_installer_and_need_no_maintainer_scripts(self):
        rules = DEBIAN_DIR / "rules"
        rules_text = rules.read_text()

        self.assertEqual(mode(rules), 0o755)
        self.assertIn(
            "$(MAKE) install PREFIX=/usr DESTDIR=$(CURDIR)/debian/ofgs",
            rules_text,
        )
        for runtime_filename in (
            "ofgs_generate.py",
            "dataset_parser.py",
            "generator.py",
        ):
            self.assertNotIn(runtime_filename, rules_text)
        for maintainer_script in ("preinst", "postinst", "prerm", "postrm"):
            self.assertFalse((DEBIAN_DIR / maintainer_script).exists())

    def test_shared_installer_produces_exact_debian_runtime_layout(self):
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
            self.assertIn("/usr/share/ofgs", wrapper_text)
            self.assertNotIn("/usr/local/share/ofgs", wrapper_text)
            self.assertNotIn(str(root), wrapper_text)
            self.assertIn(
                'python3 -B "$OFGS_INSTALL_DIR/ofgs_generate.py"',
                wrapper_text,
            )
            self.assertIn(
                'exec python3 -B "$OFGS_INSTALL_DIR/ofgs_generate.py"',
                wrapper_text,
            )
            runtime_python_invocations = [
                line
                for line in wrapper_text.splitlines()
                if "python3" in line and "$OFGS_INSTALL_DIR" in line
            ]
            self.assertEqual(len(runtime_python_invocations), 3)
            self.assertTrue(
                all("python3 -B" in line for line in runtime_python_invocations)
            )
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", wrapper_text)

            for relative_path in EXPECTED_RUNTIME_FILES - {Path("usr/bin/ofgs")}:
                self.assertEqual(mode(root / relative_path), 0o644)
            self.assertFalse(
                (root / "usr/share/ofgs/ofgs_generate.py")
                .read_text()
                .startswith("#!")
            )
            self.assertIn(
                "# OFGS completion owner: package",
                (root / "usr/share/bash-completion/completions/ofgs").read_text(),
            )

    def test_documentation_and_runtime_manifest_are_not_duplicated(self):
        docs = (DEBIAN_DIR / "docs").read_text().splitlines()
        self.assertEqual(docs, ["README.md"])
        self.assertFalse((DEBIAN_DIR / "install").exists())

    def test_man_page_structure_and_debian_installation(self):
        man_page = PROJECT_ROOT / "docs" / "ofgs.1"
        man_page_text = man_page.read_text()
        manpages = (DEBIAN_DIR / "manpages").read_text().splitlines()

        self.assertTrue(man_page.is_file())
        self.assertEqual(manpages, ["docs/ofgs.1"])
        self.assertEqual(man_page.suffix, ".1")
        self.assertEqual(
            Path("usr/share/man/man1") / f"{man_page.name}.gz",
            Path("usr/share/man/man1/ofgs.1.gz"),
        )
        self.assertRegex(man_page_text, r'^\.TH OFGS 1 ')
        for section in (
            "NAME",
            "SYNOPSIS",
            "DESCRIPTION",
            "COMMANDS",
            "OPTIONS",
            "EXAMPLES",
            "GENERATED FILES",
            "AUTHOR",
            "COPYRIGHT",
        ):
            self.assertIn(f".SH {section}\n", man_page_text)

    def test_man_page_documents_the_current_help_commands(self):
        help_result = subprocess.run(
            ["bash", str(PROJECT_ROOT / "wrapper" / "ofgs"), "help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        help_commands = set(
            re.findall(r"^  ([a-z]+) {2,}", help_result.stdout, re.MULTILINE)
        )

        man_page_text = (PROJECT_ROOT / "docs" / "ofgs.1").read_text()
        documented_commands = set(
            re.findall(
                r"^\.B (generate|monitor|list|clean|doctor|help)$|"
                r'^\.BI "(graph) "',
                man_page_text,
                re.MULTILINE,
            )
        )
        documented_commands = {
            command
            for match in documented_commands
            for command in match
            if command
        }
        self.assertEqual(documented_commands, help_commands)

        for invocation in (
            "ofgs generate",
            "ofgs monitor",
            '"ofgs graph " id',
            '"ofgs graph " id1,id2,...',
            "ofgs list",
            "ofgs clean",
            "ofgs doctor",
            "ofgs help",
            '"ofgs help " command',
            "ofgs \\-h",
            "ofgs \\-\\-help",
        ):
            self.assertIn(invocation, man_page_text)

        self.assertIn("\\-\\-live", man_page_text)
        self.assertIn("\\-\\-force", man_page_text)


if __name__ == "__main__":
    unittest.main()
