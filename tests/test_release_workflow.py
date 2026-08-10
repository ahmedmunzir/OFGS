import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "package-release.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()

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


if __name__ == "__main__":
    unittest.main()
