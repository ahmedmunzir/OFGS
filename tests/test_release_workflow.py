import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "package-release.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()

    def job(self, name, following_name):
        return self.workflow.split(f"  {name}:\n", 1)[1].split(
            f"  {following_name}:\n", 1
        )[0]

    def test_trigger_and_publication_are_independently_guarded(self):
        self.assertIn('      - "v*"', self.workflow)
        self.assertIn("  workflow_dispatch:\n", self.workflow)
        self.assertIn("publish=false", self.workflow)
        self.assertIn("needs.validate.outputs.publish == 'true'", self.workflow)
        self.assertIn("github.event_name == 'push'", self.workflow)
        self.assertIn("startsWith(github.ref, 'refs/tags/')", self.workflow)
        self.assertIn("contents: write", self.workflow)

    def test_acceptance_targets_and_release_artifacts_are_explicit(self):
        self.assertIn("container: debian:12", self.workflow)
        self.assertIn("container: rockylinux:9", self.workflow)
        self.assertIn("dnf install -y epel-release", self.workflow)
        self.assertIn('ofgs_${VERSION}-1_all.deb', self.workflow)
        self.assertIn('ofgs-${VERSION}-1.el9.noarch.rpm', self.workflow)
        self.assertIn('ofgs-${VERSION}-SHA256SUMS', self.workflow)

    def test_packages_are_created_from_the_validated_archived_commit(self):
        self.assertGreaterEqual(
            self.workflow.count(
                'git archive --format=tar --prefix="ofgs-$VERSION/" '
                '"$SOURCE_COMMIT"'
            )
            + self.workflow.count(
                'git archive --format=tar --prefix="OFGS-$VERSION/" '
                '"$SOURCE_COMMIT"'
            ),
            2,
        )
        self.assertIn("test \"$(git rev-parse HEAD)\" = \"$SOURCE_COMMIT\"", self.workflow)

    def test_container_jobs_trust_only_the_checked_out_workspace(self):
        safe_directory_command = (
            'git config --global --add safe.directory "$GITHUB_WORKSPACE"'
        )
        self.assertEqual(self.workflow.count(safe_directory_command), 2)
        self.assertNotIn("safe.directory '*'", self.workflow)
        self.assertNotIn('safe.directory "*"', self.workflow)

        for job_name in ("debian", "rpm"):
            job = self.workflow.split(f"  {job_name}:\n", 1)[1]
            if job_name == "debian":
                job = job.split("  rpm:\n", 1)[0]
            else:
                job = job.split("  publish:\n", 1)[0]
            self.assertLess(
                job.index(safe_directory_command),
                job.index("git rev-parse HEAD"),
            )

    def test_rocky_bootstrap_keeps_the_minimal_coreutils_package(self):
        rpm_job = self.workflow.split("  rpm:\n", 1)[1].split("  publish:\n", 1)[0]
        bootstrap = rpm_job.split("- name: Install EL9 build tools", 1)[1].split(
            "- name: Check out the validated revision", 1
        )[0]
        self.assertNotIn("coreutils", bootstrap)
        self.assertNotIn("--allowerasing", bootstrap)

    def test_apt_repository_consumes_tested_debian_artifact_without_rebuild(self):
        repository_job = self.job("apt_repository", "apt_acceptance")
        self.assertIn("needs: [validate, debian]", repository_job)
        self.assertIn("name: debian-package", repository_job)
        self.assertIn("actions/download-artifact@v4", repository_job)
        self.assertNotIn("dpkg-buildpackage", repository_job)
        self.assertNotIn("make install", repository_job)
        self.assertIn("dpkg-scanpackages --arch all pool", repository_job)
        self.assertIn("apt-ftparchive", repository_job)
        for release_field in (
            "Origin=OFGS",
            "Label=OFGS",
            "Suite=stable",
            "Codename=stable",
            "Architectures=all",
            "Components=main",
        ):
            self.assertIn(release_field, repository_job)

        for path in (
            "dists/stable/main/binary-all/Packages",
            "dists/stable/main/binary-all/Packages.gz",
            "dists/stable/Release",
            "dists/stable/InRelease",
            "dists/stable/Release.gpg",
            "pool/main/o/ofgs/ofgs_${VERSION}-1_all.deb",
        ):
            self.assertIn(path, repository_job)

    def test_apt_signing_uses_isolated_verified_actions_secret(self):
        repository_job = self.job("apt_repository", "apt_acceptance")
        private_key_expression = (
            "${{ secrets.OFGS_REPOSITORY_GPG_PRIVATE_KEY }}"
        )
        passphrase_expression = (
            "${{ secrets.OFGS_REPOSITORY_GPG_PASSPHRASE }}"
        )
        fingerprint_expression = (
            "${{ vars.OFGS_REPOSITORY_GPG_FINGERPRINT }}"
        )
        self.assertEqual(repository_job.count(private_key_expression), 1)
        self.assertEqual(repository_job.count(passphrase_expression), 1)
        self.assertEqual(repository_job.count(fingerprint_expression), 1)
        self.assertIn('GNUPGHOME="$(mktemp -d ', repository_job)
        self.assertIn("export GNUPGHOME", repository_job)
        self.assertIn("unset OFGS_PRIVATE_KEY", repository_job)
        self.assertIn("--list-secret-keys --fingerprint", repository_job)
        self.assertIn(
            'test "$actual_fingerprint" = "$expected_fingerprint"',
            repository_job,
        )
        self.assertLess(
            repository_job.index(
                'test "$actual_fingerprint" = "$expected_fingerprint"'
            ),
            repository_job.index("--clearsign"),
        )
        self.assertEqual(
            repository_job.count('--local-user "$actual_fingerprint"'), 2
        )
        self.assertIn("--clearsign", repository_job)
        self.assertIn("--armor --detach-sign", repository_job)
        self.assertEqual(repository_job.count("--pinentry-mode loopback"), 2)
        self.assertEqual(repository_job.count("--passphrase-fd 0"), 2)
        self.assertEqual(
            repository_job.count('printf \'%s\' "$OFGS_PASSPHRASE" |'), 2
        )
        self.assertIn("unset OFGS_PASSPHRASE", repository_job)
        self.assertLess(
            repository_job.rindex("--detach-sign"),
            repository_job.index("unset OFGS_PASSPHRASE"),
        )
        self.assertNotIn('echo "$OFGS_PASSPHRASE"', repository_job)
        self.assertNotIn('--passphrase "$OFGS_PASSPHRASE"', repository_job)
        self.assertIn(
            'printf \'%s\' "$OFGS_PRIVATE_KEY" | gpg --batch --quiet --import',
            repository_job,
        )
        self.assertNotIn('"$OFGS_PRIVATE_KEY" >', repository_job)
        self.assertIn("trap 'rm -rf -- \"$GNUPGHOME\"' EXIT", repository_job)
        self.assertNotIn("set -x", repository_job)
        self.assertNotIn("~/ofgs-signing-backup", self.workflow)

    def test_apt_acceptance_requires_signature_and_installs_through_apt(self):
        acceptance_job = self.job("apt_acceptance", "rpm")
        self.assertIn("container: debian:12", acceptance_job)
        self.assertIn("needs: [validate, apt_repository]", acceptance_job)
        self.assertIn("name: apt-repository", acceptance_job)
        self.assertIn("name: apt-repository-public-key", acceptance_job)
        self.assertIn("signed-by=/usr/share/keyrings/ofgs-repository.gpg", acceptance_job)
        self.assertNotIn("apt-key", acceptance_job)
        for bypass in ("trusted=yes", "allow-insecure", "allow-unauthenticated"):
            self.assertNotIn(bypass, acceptance_job.lower())

        update = acceptance_job.index("apt-get update")
        install = acceptance_job.index("apt-get install -y ofgs")
        self.assertLess(update, install)
        self.assertNotIn('apt-get install -y "$deb"', acceptance_job)
        self.assertIn("apt-cache policy ofgs", acceptance_job)
        self.assertIn('test "$(command -v ofgs)" = /usr/bin/ofgs', acceptance_job)
        self.assertIn("ofgs --help", acceptance_job)
        self.assertIn("generation_status", acceptance_job)
        self.assertIn("__pycache__", acceptance_job)
        self.assertIn("'*.pyc'", acceptance_job)
        self.assertIn("apt-get remove -y ofgs", acceptance_job)
        self.assertIn("test ! -e /usr/bin/ofgs", acceptance_job)
        self.assertIn("test ! -e /usr/share/ofgs", acceptance_job)

    def test_apt_repository_is_artifact_only_and_does_not_change_publication(self):
        repository_job = self.job("apt_repository", "apt_acceptance")
        self.assertIn("actions/upload-artifact@v4", repository_job)
        self.assertIn("name: apt-repository", repository_job)
        self.assertNotIn("munzirahmed.dev", self.workflow)
        self.assertNotIn("gh release", repository_job)
        self.assertNotIn("git push", repository_job)

        publish_job = self.workflow.split("  publish:\n", 1)[1]
        self.assertIn("needs: [validate, debian, rpm]", publish_job)
        self.assertIn("needs.validate.outputs.publish == 'true'", publish_job)
        self.assertIn("github.event_name == 'push'", publish_job)


if __name__ == "__main__":
    unittest.main()
