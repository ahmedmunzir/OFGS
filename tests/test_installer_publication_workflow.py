import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-installer.yml"
PACKAGE_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "package-release.yml"


class InstallerPublicationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()
        cls.package_workflow = PACKAGE_WORKFLOW.read_text()

    def test_only_reviewed_main_changes_trigger_publication(self):
        self.assertIn("  push:\n", self.workflow)
        self.assertIn("      - main", self.workflow)
        self.assertIn("      - scripts/install_packages.sh", self.workflow)
        self.assertIn(
            "      - .github/workflows/publish-installer.yml", self.workflow
        )
        self.assertNotIn("workflow_dispatch", self.workflow)
        self.assertNotIn("tags:", self.workflow)
        self.assertIn(
            "if: github.event_name == 'push' && "
            "github.ref == 'refs/heads/main'",
            self.workflow,
        )

    def test_canonical_installer_is_checked_out_and_verified_unchanged(self):
        canonical = "ofgs/scripts/install_packages.sh"
        self.assertIn("ref: ${{ github.sha }}", self.workflow)
        self.assertIn(canonical, self.workflow)
        self.assertIn("ls-files --error-unmatch", self.workflow)
        self.assertIn("bash -n \"$source_installer\"", self.workflow)
        self.assertIn('sha256=$(sha256sum "$source_installer"', self.workflow)
        self.assertIn('install -m 0644 "$SOURCE_INSTALLER" install-ofgs', self.workflow)
        self.assertIn('cmp -s "$SOURCE_INSTALLER" install-ofgs', self.workflow)
        self.assertGreaterEqual(self.workflow.count("$EXPECTED_SHA256"), 2)
        self.assertNotIn("curl ", self.workflow)
        self.assertNotIn("wget ", self.workflow)

    def test_website_checkout_uses_restricted_pat_without_persisting_it(self):
        pat = "${{ secrets.OFGS_WEBSITE_PUBLISH_TOKEN }}"
        self.assertIn("repository: ahmedmunzir/munzirahmed.dev", self.workflow)
        self.assertIn("ref: main", self.workflow)
        self.assertEqual(self.workflow.count(pat), 2)
        self.assertEqual(self.workflow.count("persist-credentials: false"), 2)
        self.assertIn("permissions:\n      contents: read", self.workflow)
        self.assertIn("GIT_ASKPASS", self.workflow)
        self.assertIn("unset OFGS_WEBSITE_TOKEN", self.workflow)
        self.assertNotIn("set -x", self.workflow)
        self.assertNotIn("--force", self.workflow)

    def test_update_is_scoped_to_root_installer_and_preserves_packages(self):
        self.assertIn("test -d packages/apt", self.workflow)
        self.assertIn("test -d packages/rpm/el9", self.workflow)
        self.assertIn("packages/keys/ofgs-repository.asc", self.workflow)
        self.assertIn("packages/keys/ofgs-repository.gpg", self.workflow)
        self.assertIn("git add -- install-ofgs", self.workflow)
        self.assertIn("':(exclude)install-ofgs'", self.workflow)
        self.assertIn("git diff --quiet -- packages", self.workflow)
        self.assertIn("git diff --cached --quiet -- packages", self.workflow)
        self.assertIn(
            'test "$(git diff --cached --name-only)" = install-ofgs', self.workflow
        )
        for forbidden in (
            "git add -A",
            "git add .",
            "packages/apt/",
            "packages/rpm/el9/",
            "git rm",
        ):
            self.assertNotIn(forbidden, self.workflow)

    def test_no_change_skips_commit_and_push(self):
        quiet = self.workflow.index("if git diff --cached --quiet; then")
        commit = self.workflow.index("git commit -m")
        self.assertLess(quiet, commit)
        self.assertIn(
            'echo "changed=false" >> "$GITHUB_OUTPUT"',
            self.workflow[quiet:commit],
        )
        self.assertIn("exit 0", self.workflow[quiet:commit])
        self.assertIn(
            "if: steps.update.outputs.changed == 'true'", self.workflow
        )
        self.assertIn("git push origin HEAD:main", self.workflow)

    def test_all_website_writers_share_non_cancelling_concurrency(self):
        concurrency = "group: ofgs-package-website-publication"
        self.assertIn(concurrency, self.workflow)
        self.assertEqual(self.package_workflow.count(concurrency), 2)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_job_has_no_package_or_signing_responsibilities(self):
        for forbidden in (
            "OFGS_REPOSITORY_GPG_PRIVATE_KEY",
            "OFGS_REPOSITORY_GPG_PASSPHRASE",
            "OFGS_REPOSITORY_GPG_FINGERPRINT",
            "apt-repository",
            "rpm-repository",
            "rpmbuild",
            "rpmsign",
            "createrepo_c",
            "gpgcheck",
            "repo_gpgcheck",
        ):
            self.assertNotIn(forbidden, self.workflow)


if __name__ == "__main__":
    unittest.main()
