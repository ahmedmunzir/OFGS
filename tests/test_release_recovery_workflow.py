import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    PROJECT_ROOT / ".github" / "workflows" / "recover-v2.3.0-release.yml"
)


class ReleaseRecoveryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()

    def test_recovery_is_manual_and_hard_coded_to_original_release(self):
        trigger = self.workflow.split("on:\n", 1)[1].split("permissions:\n", 1)[0]
        self.assertEqual(trigger.strip(), "workflow_dispatch:")
        self.assertIn("if: github.repository == 'ahmedmunzir/OFGS'", self.workflow)
        self.assertIn("RELEASE_TAG: v2.3.0", self.workflow)
        self.assertIn("VERSION: 2.3.0", self.workflow)
        self.assertIn(
            "EXPECTED_COMMIT: 9adcdc3b88983d19496690e0819157f86c169461",
            self.workflow,
        )
        self.assertIn("SOURCE_RUN_ID: 31475548580", self.workflow)
        self.assertEqual(
            self.workflow.count("run-id: ${{ env.SOURCE_RUN_ID }}"), 2
        )
        self.assertIn("group: recover-v2.3.0-github-release", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_annotated_tag_is_dereferenced_and_exact_commit_is_required(self):
        self.assertIn(
            'git/ref/tags/$RELEASE_TAG"',
            self.workflow,
        )
        self.assertIn('test "$object_type" = tag', self.workflow)
        self.assertIn('git/tags/$object_sha"', self.workflow)
        self.assertIn('if [[ "$object_type" == commit ]]', self.workflow)
        self.assertIn('test "$object_type" = commit', self.workflow)
        self.assertIn('test "$object_sha" = "$EXPECTED_COMMIT"', self.workflow)
        self.assertIn("actions/runs/$SOURCE_RUN_ID", self.workflow)
        self.assertIn('test "$run_event" = push', self.workflow)
        self.assertIn('test "$run_conclusion" = failure', self.workflow)
        self.assertIn('test "$run_commit" = "$EXPECTED_COMMIT"', self.workflow)

    def test_only_expected_prior_run_package_artifacts_are_downloaded(self):
        self.assertEqual(self.workflow.count("actions/download-artifact@v4"), 2)
        self.assertEqual(self.workflow.count("name: debian-package"), 1)
        self.assertEqual(self.workflow.count("name: rpm-package"), 1)
        self.assertEqual(self.workflow.count("repository: ahmedmunzir/OFGS"), 2)
        self.assertEqual(self.workflow.count("github-token: ${{ github.token }}"), 2)
        self.assertNotIn("name: apt-repository", self.workflow)
        self.assertNotIn("name: rpm-repository", self.workflow)
        self.assertNotIn("merge-multiple", self.workflow)

    def test_package_metadata_and_exact_release_assets_are_validated(self):
        for metadata in (
            "dpkg-deb -f",
            "%{NAME}",
            "%{VERSION}-%{RELEASE}",
            "%{ARCH}",
        ):
            self.assertIn(metadata, self.workflow)
        self.assertIn('= "$VERSION-1"', self.workflow)
        self.assertIn('"$VERSION-1.el9"', self.workflow)
        for asset in (
            "ofgs_${VERSION}-1_all.deb",
            "ofgs-${VERSION}-1.el9.noarch.rpm",
            "ofgs-${VERSION}-SHA256SUMS",
        ):
            self.assertIn(asset, self.workflow)
        self.assertIn("test \"${#recovered_entries[@]}\" -eq 2", self.workflow)
        self.assertIn("test \"${#assets[@]}\" -eq 3", self.workflow)
        self.assertIn("sha256sum --check", self.workflow)

    def test_release_operations_are_explicit_idempotent_and_checkout_free(self):
        repository_option = '--repo "$GITHUB_REPOSITORY"'
        self.assertEqual(self.workflow.count(repository_option), 3)
        self.assertIn('gh release view "$RELEASE_TAG"', self.workflow)
        self.assertIn('gh release upload "$RELEASE_TAG"', self.workflow)
        self.assertIn('gh release create "$RELEASE_TAG"', self.workflow)
        self.assertIn("--clobber", self.workflow)
        self.assertIn("--verify-tag --generate-notes --title", self.workflow)
        self.assertNotIn("actions/checkout", self.workflow)

    def test_permissions_and_prohibited_capabilities_are_narrow(self):
        permissions = self.workflow.split("permissions:\n", 1)[1].split(
            "concurrency:\n", 1
        )[0]
        self.assertEqual(
            permissions.strip(), "actions: read\n  contents: write"
        )
        for prohibited in (
            "OFGS_WEBSITE_PUBLISH_TOKEN",
            "OFGS_REPOSITORY_GPG_PRIVATE_KEY",
            "OFGS_REPOSITORY_GPG_PASSPHRASE",
            "OFGS_REPOSITORY_GPG_FINGERPRINT",
            "munzirahmed.dev",
            "rpmbuild",
            "rpmsign",
            "createrepo_c",
            "dpkg-buildpackage",
            "apt-ftparchive",
            "git push",
            "git tag",
            "release delete",
            "--force",
        ):
            self.assertNotIn(prohibited, self.workflow)


if __name__ == "__main__":
    unittest.main()
