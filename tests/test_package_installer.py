import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "scripts" / "install_packages.sh"


class PackageInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.command_log = self.root / "commands.log"
        self.epel_marker = self.root / "epel-release-installed"
        self.os_release = self.root / "os-release"
        self.debian_key = self.root / "usr/share/keyrings/ofgs-repository.gpg"
        self.debian_source = self.root / "etc/apt/sources.list.d/ofgs.list"
        self.rocky_repository = self.root / "etc/yum.repos.d/ofgs.repo"
        self.debian_key.parent.mkdir(parents=True)
        self.debian_source.parent.mkdir(parents=True)
        self.rocky_repository.parent.mkdir(parents=True)

        installer_text = INSTALLER.read_text()
        replacements = {
            'OS_RELEASE="/etc/os-release"': f'OS_RELEASE="{self.os_release}"',
            'DEBIAN_KEY="/usr/share/keyrings/ofgs-repository.gpg"': (
                f'DEBIAN_KEY="{self.debian_key}"'
            ),
            'DEBIAN_SOURCE="/etc/apt/sources.list.d/ofgs.list"': (
                f'DEBIAN_SOURCE="{self.debian_source}"'
            ),
            'ROCKY_REPOSITORY="/etc/yum.repos.d/ofgs.repo"': (
                f'ROCKY_REPOSITORY="{self.rocky_repository}"'
            ),
        }
        for original, relocated in replacements.items():
            self.assertIn(original, installer_text)
            installer_text = installer_text.replace(original, relocated, 1)
        self.installer = self.root / "install_packages.sh"
        self.installer.write_text(installer_text)
        self.installer.chmod(0o755)

        self._write_command(
            "id",
            """
            if [[ "${1:-}" == "-u" ]]; then
                printf '%s\n' "${MOCK_UID:?}"
            fi
            """,
        )
        self._write_command(
            "curl",
            """
            printf 'curl %s\n' "$*" >> "$COMMAND_LOG"
            destination=""
            while (( $# )); do
                if [[ "$1" == "-o" ]]; then
                    destination="$2"
                    shift 2
                else
                    shift
                fi
            done
            printf 'public repository key\n' > "$destination"
            """,
        )
        self._write_command(
            "apt-get",
            'printf \'apt-get %s\\n\' "$*" >> "$COMMAND_LOG"',
        )
        self._write_command(
            "rpm",
            """
            printf 'rpm %s\n' "$*" >> "$COMMAND_LOG"
            if [[ "$*" == "-q --quiet epel-release" ]]; then
                [[ -e "$EPEL_MARKER" ]]
            else
                exit 2
            fi
            """,
        )
        self._write_command(
            "dnf",
            """
            printf 'dnf %s\n' "$*" >> "$COMMAND_LOG"
            if [[ "$*" == "install -y epel-release" ]]; then
                : > "$EPEL_MARKER"
            fi
            """,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_command(self, name, body):
        command = self.bin_dir / name
        command.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            + textwrap.dedent(body).strip()
            + "\n"
        )
        command.chmod(0o755)

    def _set_os(self, distribution, version):
        self.os_release.write_text(f'ID="{distribution}"\nVERSION_ID="{version}"\n')

    def _run(self, uid="0"):
        environment = os.environ.copy()
        environment.update(
            {
                "COMMAND_LOG": str(self.command_log),
                "EPEL_MARKER": str(self.epel_marker),
                "MOCK_UID": uid,
                "PATH": f"{self.bin_dir}:/usr/bin:/bin",
            }
        )
        return subprocess.run(
            ["bash", str(self.installer)],
            capture_output=True,
            text=True,
            env=environment,
        )

    def _commands(self):
        if not self.command_log.exists():
            return ""
        return self.command_log.read_text()

    def test_debian_12_configures_signed_repository_and_is_idempotent(self):
        self._set_os("debian", "12")

        first = self._run()
        second = self._run()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        expected_source = (
            "deb [signed-by="
            f"{self.debian_key}] https://munzirahmed.dev/packages/apt stable main\n"
        )
        self.assertEqual(self.debian_source.read_text(), expected_source)
        self.assertEqual(self.debian_source.read_text().count("deb ["), 1)
        self.assertEqual(self.debian_key.read_text(), "public repository key\n")
        commands = self._commands()
        self.assertIn(
            "https://munzirahmed.dev/packages/keys/ofgs-repository.gpg",
            commands,
        )
        self.assertEqual(commands.count("apt-get update\n"), 2)
        self.assertEqual(commands.count("apt-get install -y ofgs\n"), 2)

    def test_rocky_9_configures_verified_repository_and_is_idempotent(self):
        self._set_os("rocky", "9.6")

        first = self._run()
        second = self._run()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        repository = self.rocky_repository.read_text()
        self.assertEqual(repository.count("[ofgs]"), 1)
        self.assertIn("baseurl=https://munzirahmed.dev/packages/rpm/el9/", repository)
        self.assertIn("gpgcheck=1", repository)
        self.assertIn("repo_gpgcheck=1", repository)
        self.assertIn(
            "gpgkey=https://munzirahmed.dev/packages/keys/ofgs-repository.asc",
            repository,
        )
        commands = self._commands()
        self.assertEqual(commands.count("rpm -q --quiet epel-release\n"), 2)
        self.assertEqual(commands.count("dnf install -y epel-release\n"), 1)
        self.assertEqual(commands.count("dnf install -y ofgs\n"), 2)

    def test_rocky_does_not_upgrade_an_existing_epel_release_package(self):
        self._set_os("rocky", "9")
        self.epel_marker.touch()

        completed = self._run()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        commands = self._commands()
        self.assertEqual(commands.count("rpm -q --quiet epel-release\n"), 1)
        self.assertNotIn("dnf install -y epel-release", commands)
        self.assertIn("dnf install -y ofgs", commands)

    def test_unsupported_distribution_is_rejected_before_configuration(self):
        self._set_os("ubuntu", "24.04")

        completed = self._run()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsupported operating system", completed.stderr)
        self.assertEqual(self._commands(), "")
        self.assertFalse(self.debian_source.exists())
        self.assertFalse(self.rocky_repository.exists())

    def test_unsupported_supported_distribution_version_is_rejected(self):
        for distribution, version in (("debian", "11"), ("rocky", "8.10")):
            with self.subTest(distribution=distribution, version=version):
                self._set_os(distribution, version)
                completed = self._run()
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("unsupported", completed.stderr)
                self.assertEqual(self._commands(), "")

    def test_non_root_is_rejected_with_sudo_guidance(self):
        self._set_os("debian", "12")

        completed = self._run(uid="1000")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("root privileges are required", completed.stderr)
        self.assertIn("sudo", completed.stderr)
        self.assertEqual(self._commands(), "")

    def test_conflicting_ofgs_configuration_is_preserved_and_rejected(self):
        self._set_os("rocky", "9")
        conflicting = "[ofgs]\nbaseurl=https://example.invalid/\n"
        self.rocky_repository.write_text(conflicting)

        completed = self._run()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("conflicts", completed.stderr)
        self.assertEqual(self.rocky_repository.read_text(), conflicting)
        self.assertNotIn("dnf install -y ofgs", self._commands())

    def test_installer_contains_no_secrets_or_signature_bypasses(self):
        installer = INSTALLER.read_text()

        self.assertTrue(INSTALLER.stat().st_mode & stat.S_IXUSR)
        self.assertIn("signed-by=$DEBIAN_KEY", installer)
        self.assertIn("gpgcheck=1", installer)
        self.assertIn("repo_gpgcheck=1", installer)
        for forbidden in (
            "trusted=yes",
            "allow-unauthenticated",
            "--nogpgcheck",
            "gpgcheck=0",
            "repo_gpgcheck=0",
            "sslverify=0",
            "OFGS_REPOSITORY_GPG_PRIVATE_KEY",
            "OFGS_REPOSITORY_GPG_PASSPHRASE",
            "OFGS_WEBSITE_PUBLISH_TOKEN",
            "GITHUB_TOKEN",
        ):
            self.assertNotIn(forbidden, installer)


if __name__ == "__main__":
    unittest.main()
