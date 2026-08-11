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

    def last_job(self, name):
        return self.workflow.split(f"  {name}:\n", 1)[1]

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
        self.assertNotIn("munzirahmed.dev", repository_job)
        self.assertNotIn("gh release", repository_job)
        self.assertNotIn("git push", repository_job)

        publish_job = self.job("publish", "publish_apt")
        self.assertIn("needs: [validate, debian, rpm]", publish_job)
        self.assertIn("needs.validate.outputs.publish == 'true'", publish_job)
        self.assertIn("github.event_name == 'push'", publish_job)

    def test_github_release_publication_explicitly_targets_ofgs_repository(self):
        publish_job = self.job("publish", "publish_apt")
        repository_option = '--repo "$GITHUB_REPOSITORY"'
        self.assertEqual(publish_job.count(repository_option), 3)
        self.assertIn(
            'gh release view "$RELEASE_TAG" \\\n'
            '            --repo "$GITHUB_REPOSITORY"',
            publish_job,
        )
        self.assertIn(
            'gh release upload "$RELEASE_TAG" "${assets[@]}" --clobber \\\n'
            '              --repo "$GITHUB_REPOSITORY"',
            publish_job,
        )
        self.assertIn(
            'gh release create "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY"',
            publish_job,
        )
        self.assertNotIn("actions/checkout", publish_job)
        self.assertIn("GH_TOKEN: ${{ github.token }}", publish_job)
        self.assertIn("permissions:\n      contents: write", publish_job)
        self.assertIn("--verify-tag --generate-notes --title", publish_job)

    def test_website_publication_has_complete_release_gating_and_concurrency(self):
        website_job = self.job("publish_apt", "publish_rpm")
        self.assertIn(
            "needs: [validate, debian, rpm, apt_repository, apt_acceptance]",
            website_job,
        )
        self.assertIn("needs.validate.outputs.publish == 'true'", website_job)
        self.assertIn("github.event_name == 'push'", website_job)
        self.assertIn("startsWith(github.ref, 'refs/tags/')", website_job)
        self.assertIn("group: ofgs-package-website-publication", website_job)
        self.assertIn("cancel-in-progress: false", website_job)
        self.assertIn("permissions:\n      contents: read", website_job)

    def test_website_publication_uses_only_restricted_pat_for_target_repo(self):
        website_job = self.job("publish_apt", "publish_rpm")
        pat_expression = "${{ secrets.OFGS_WEBSITE_PUBLISH_TOKEN }}"
        self.assertEqual(website_job.count(pat_expression), 2)
        self.assertIn("repository: ahmedmunzir/munzirahmed.dev", website_job)
        self.assertIn("ref: main", website_job)
        self.assertIn("persist-credentials: false", website_job)
        self.assertIn("git push origin HEAD:main", website_job)
        self.assertNotIn("--force", website_job)
        self.assertNotIn("github.token", website_job)
        self.assertNotIn(
            "${{ secrets.OFGS_REPOSITORY_GPG_PRIVATE_KEY }}", website_job
        )
        self.assertNotIn(
            "${{ secrets.OFGS_REPOSITORY_GPG_PASSPHRASE }}", website_job
        )
        self.assertNotIn(
            "${{ vars.OFGS_REPOSITORY_GPG_FINGERPRINT }}", website_job
        )
        self.assertNotIn("set -x", website_job)
        self.assertNotIn("https://x-access-token", website_job)

    def test_website_publication_transfers_only_validated_apt_artifact(self):
        website_job = self.job("publish_apt", "publish_rpm")
        self.assertIn("name: apt-repository", website_job)
        self.assertIn("actions/download-artifact@v4", website_job)
        self.assertNotIn("dpkg-scanpackages", website_job)
        self.assertNotIn("apt-ftparchive", website_job)
        self.assertNotIn("dpkg-buildpackage", website_job)
        self.assertNotIn("--clearsign", website_job)
        self.assertNotIn("--detach-sign", website_job)
        for path in (
            "dists/stable/InRelease",
            "dists/stable/Release",
            "dists/stable/Release.gpg",
            "dists/stable/main/binary-all/Packages",
            "dists/stable/main/binary-all/Packages.gz",
            'pool/main/o/ofgs/ofgs_${VERSION}-1_all.deb',
        ):
            self.assertIn(path, website_job)
        self.assertIn("find . -type f", website_job)
        self.assertIn("! -type d ! -type f", website_job)
        self.assertIn("PRIVATE KEY", website_job)

    def test_website_update_is_scoped_and_preserves_keys_and_other_content(self):
        website_job = self.job("publish_apt", "publish_rpm")
        self.assertIn("git rm -r --ignore-unmatch -- packages/apt", website_job)
        self.assertIn('cp -a "$APT_ARTIFACT"/. packages/apt/', website_job)
        self.assertIn('diff -qr "$APT_ARTIFACT" packages/apt', website_job)
        self.assertIn("packages/keys/ofgs-repository.asc", website_job)
        self.assertIn("packages/keys/ofgs-repository.gpg", website_job)
        self.assertIn('test "$keys_after" = "$keys_before"', website_job)
        self.assertIn("git add --all -- packages/apt", website_job)
        self.assertIn("':(exclude)packages/apt/**'", website_job)
        self.assertIn('[[ "$changed_path" == packages/apt/* ]]', website_job)

    def test_website_no_change_path_skips_commit_and_push(self):
        website_job = self.job("publish_apt", "publish_rpm")
        quiet = website_job.index("if git diff --cached --quiet; then")
        commit = website_job.index("git commit -m")
        self.assertLess(quiet, commit)
        self.assertIn('echo "changed=false" >> "$GITHUB_OUTPUT"', website_job)
        self.assertIn("exit 0", website_job[quiet:commit])
        self.assertIn("if: steps.update.outputs.changed == 'true'", website_job)
        self.assertIn('git config user.name "OFGS release automation"', website_job)
        self.assertIn("git config user.email", website_job)

    def test_rpm_repository_consumes_tested_artifact_without_rebuilding(self):
        repository_job = self.job("rpm_repository", "rpm_acceptance")
        self.assertIn("needs: [validate, rpm]", repository_job)
        self.assertIn("name: rpm-package", repository_job)
        self.assertIn("actions/download-artifact@v4", repository_job)
        self.assertIn('cp "$source_rpm" rpm/Packages/', repository_job)
        self.assertIn("createrepo_c", repository_job)
        self.assertNotIn("rpmbuild", repository_job)
        self.assertNotIn("ofgs.spec", repository_job)
        self.assertIn(
            'rpm/Packages/ofgs-${VERSION}-1.el9.noarch.rpm', repository_job
        )
        self.assertIn("rpm/repodata/repomd.xml", repository_job)
        self.assertIn("${repomd}.asc", repository_job)
        self.assertIn("name: rpm-repository", repository_job)
        self.assertIn("actions/upload-artifact@v4", repository_job)

    def test_rpm_repository_signing_is_isolated_verified_and_noninteractive(self):
        repository_job = self.job("rpm_repository", "rpm_acceptance")
        private_key = "${{ secrets.OFGS_REPOSITORY_GPG_PRIVATE_KEY }}"
        passphrase = "${{ secrets.OFGS_REPOSITORY_GPG_PASSPHRASE }}"
        fingerprint = "${{ vars.OFGS_REPOSITORY_GPG_FINGERPRINT }}"
        self.assertEqual(repository_job.count(private_key), 1)
        self.assertEqual(repository_job.count(passphrase), 1)
        self.assertEqual(repository_job.count(fingerprint), 1)
        self.assertIn('GNUPGHOME="$(mktemp -d ', repository_job)
        self.assertIn("export GNUPGHOME", repository_job)
        self.assertIn("unset OFGS_PRIVATE_KEY", repository_job)
        self.assertIn("unset OFGS_PASSPHRASE", repository_job)
        self.assertIn("--list-secret-keys --fingerprint", repository_job)
        comparison = 'test "$actual_fingerprint" = "$expected_fingerprint"'
        self.assertIn(comparison, repository_job)
        self.assertLess(repository_job.index(comparison), repository_job.index("rpmsign"))
        self.assertIn("rpmsign --addsign", repository_job)
        self.assertIn('--define "_gpg_name $actual_fingerprint"', repository_job)
        self.assertIn('--define "_gpg_path $GNUPGHOME"', repository_job)
        self.assertIn('--local-user "$actual_fingerprint"', repository_job)
        self.assertIn("allow-preset-passphrase", repository_job)
        self.assertIn("--with-keygrip", repository_job)
        self.assertIn("/usr/libexec/gpg-preset-passphrase", repository_job)
        self.assertIn('"$preset_passphrase" --preset "$keygrip"', repository_job)
        self.assertLess(
            repository_job.index('"$preset_passphrase" --preset "$keygrip"'),
            repository_job.index("rpmsign --addsign"),
        )
        rpm_signing = repository_job[
            repository_job.index("rpmsign --addsign") :
            repository_job.index('createrepo_c "$GITHUB_WORKSPACE/rpm"')
        ]
        self.assertIn("--batch --no-tty", rpm_signing)
        self.assertNotIn("OFGS_PASSPHRASE", rpm_signing)
        self.assertNotIn("--passphrase", rpm_signing)
        self.assertNotIn("--pinentry-mode", rpm_signing)
        self.assertIn("gpgconf --homedir", repository_job)
        self.assertIn("--kill gpg-agent", repository_job)
        self.assertIn("trap cleanup_signing_home EXIT", repository_job)
        self.assertIn('rm -rf -- "$GNUPGHOME"', repository_job)
        self.assertGreaterEqual(
            repository_job.count('printf \'%s\' "$OFGS_PASSPHRASE" |'), 2
        )
        self.assertNotIn("--passphrase $OFGS_PASSPHRASE", repository_job)
        self.assertNotIn("set -x", repository_job)
        self.assertNotIn("OFGS_WEBSITE_PUBLISH_TOKEN", repository_job)

    def test_rpm_repository_validates_package_metadata_and_signatures(self):
        repository_job = self.job("rpm_repository", "rpm_acceptance")
        for query in ("%{NAME}", "%{VERSION}-%{RELEASE}", "%{ARCH}"):
            self.assertIn(query, repository_job)
        binary_export = 'gpg2 --batch --export "$actual_fingerprint"'
        armored_export = 'gpg2 --batch --armor --export "$actual_fingerprint"'
        self.assertIn(binary_export, repository_job)
        self.assertIn(armored_export, repository_job)
        self.assertIn("rpm-public-key/ofgs-repository.gpg", repository_job)
        self.assertIn("rpm-public-key/ofgs-repository.asc", repository_job)
        self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", repository_job)
        self.assertIn(
            'gpgv2 --homedir "$verification_home" --keyring "$gpgv_key"',
            repository_job,
        )
        self.assertIn(
            'rpm --dbpath "$rpm_database" --import "$rpm_key"', repository_job
        )
        self.assertLess(
            repository_job.index('rpm --dbpath "$rpm_database" --import "$rpm_key"'),
            repository_job.index("rpmkeys --dbpath"),
        )
        self.assertIn("rpmkeys --dbpath", repository_job)
        self.assertIn("--checksig", repository_job)
        self.assertIn("digests signatures OK", repository_job)
        self.assertIn("PRIVATE KEY", repository_job)
        self.assertIn("! -type d ! -type f", repository_job)

    def test_rpm_acceptance_uses_signed_repository_without_private_secrets(self):
        acceptance_job = self.job("rpm_acceptance", "publish")
        self.assertIn("needs: [validate, rpm_repository]", acceptance_job)
        self.assertIn("container: rockylinux:9", acceptance_job)
        self.assertIn("name: rpm-repository", acceptance_job)
        self.assertIn("name: rpm-repository-public-key", acceptance_job)
        self.assertIn("rpm-public-key/ofgs-repository.asc", acceptance_job)
        self.assertNotIn(
            "gpgkey=file://${GITHUB_WORKSPACE}/rpm-public-key/ofgs-repository.gpg",
            acceptance_job,
        )
        self.assertIn("gpgcheck=1", acceptance_job)
        self.assertIn("repo_gpgcheck=1", acceptance_job)
        for bypass in ("gpgcheck=0", "repo_gpgcheck=0", "--nogpgcheck"):
            self.assertNotIn(bypass, acceptance_job)
        self.assertNotIn("OFGS_REPOSITORY_GPG_PRIVATE_KEY", acceptance_job)
        self.assertNotIn("OFGS_REPOSITORY_GPG_PASSPHRASE", acceptance_job)
        self.assertNotIn("OFGS_WEBSITE_PUBLISH_TOKEN", acceptance_job)
        self.assertNotIn("createrepo_c", acceptance_job)
        self.assertNotIn("rpmsign", acceptance_job)

    def test_rpm_acceptance_installs_exact_repository_package_and_removes_it(self):
        acceptance_job = self.job("rpm_acceptance", "publish")
        makecache = acceptance_job.index("makecache")
        installation = acceptance_job.index(
            "repository-packages ofgs install ofgs"
        )
        self.assertLess(makecache, installation)
        self.assertIn("--disablerepo='*' --enablerepo=ofgs repoquery", acceptance_job)
        self.assertIn("--location ofgs", acceptance_job)
        self.assertIn('"ofgs|${VERSION}-1.el9|noarch"', acceptance_job)
        self.assertIn("repository-packages ofgs install ofgs", acceptance_job)
        self.assertIn("--enablerepo=epel", acceptance_job)
        self.assertIn("--enablerepo=ofgs", acceptance_job)
        self.assertIn("$VERSION-1.el9", acceptance_job)
        self.assertIn('test "$(command -v ofgs)" = /usr/bin/ofgs', acceptance_job)
        self.assertIn("ofgs --help", acceptance_job)
        self.assertIn("generation_status", acceptance_job)
        self.assertIn("__pycache__", acceptance_job)
        self.assertIn("'*.pyc'", acceptance_job)
        self.assertIn("dnf remove -y ofgs", acceptance_job)
        self.assertIn("test ! -e /usr/bin/ofgs", acceptance_job)
        self.assertIn("test ! -e /usr/share/ofgs", acceptance_job)

    def test_existing_publication_gates_are_unchanged_by_rpm_repository_jobs(self):
        release_job = self.job("publish", "publish_apt")
        apt_publish_job = self.job("publish_apt", "publish_rpm")
        rpm_publish_job = self.last_job("publish_rpm")
        self.assertIn("needs: [validate, debian, rpm]", release_job)
        self.assertIn(
            "needs: [validate, debian, rpm, apt_repository, apt_acceptance]",
            apt_publish_job,
        )
        for job in (release_job, apt_publish_job, rpm_publish_job):
            self.assertIn("needs.validate.outputs.publish == 'true'", job)
            self.assertIn("github.event_name == 'push'", job)
            self.assertIn("startsWith(github.ref, 'refs/tags/')", job)

    def test_rpm_website_publication_is_fully_gated_after_acceptance(self):
        website_job = self.last_job("publish_rpm")
        self.assertIn(
            "needs: [validate, debian, rpm, apt_repository, apt_acceptance, "
            "rpm_repository, rpm_acceptance]",
            website_job,
        )
        self.assertIn("needs.validate.outputs.publish == 'true'", website_job)
        self.assertIn("github.event_name == 'push'", website_job)
        self.assertIn("startsWith(github.ref, 'refs/tags/')", website_job)
        self.assertIn("permissions:\n      contents: read", website_job)

    def test_rpm_website_publication_transfers_only_accepted_artifact(self):
        website_job = self.last_job("publish_rpm")
        self.assertIn("name: rpm-repository", website_job)
        self.assertIn("actions/download-artifact@v4", website_job)
        self.assertLess(
            website_job.index("Validate accepted EL9 RPM repository artifact"),
            website_job.index("Check out current website main"),
        )
        for forbidden in ("rpmbuild", "rpmsign", "createrepo_c", "gpg2"):
            self.assertNotIn(forbidden, website_job)
        self.assertNotIn("--detach-sign", website_job)
        self.assertNotIn("--addsign", website_job)

    def test_rpm_website_artifact_validation_is_defensive(self):
        website_job = self.last_job("publish_rpm")
        for expected in (
            'Packages/ofgs-${VERSION}-1.el9.noarch.rpm',
            "repodata/repomd.xml",
            "${repomd}.asc",
            "%{NAME}",
            "%{VERSION}-%{RELEASE}",
            "%{ARCH}",
            "! -type d ! -type f",
            "PRIVATE KEY",
            "private-keys-v1.d",
            "top_level_entries",
            "= Packages",
            "= repodata",
            "-name .git",
        ):
            self.assertIn(expected, website_job)
        self.assertIn("find \"$RPM_ARTIFACT/repodata\" -type f", website_job)
        self.assertIn("-type f -empty", website_job)

    def test_rpm_website_update_is_el9_scoped_and_preserves_other_content(self):
        website_job = self.last_job("publish_rpm")
        self.assertIn("repository: ahmedmunzir/munzirahmed.dev", website_job)
        self.assertIn("ref: main", website_job)
        self.assertIn("persist-credentials: false", website_job)
        self.assertIn("git rm -r --ignore-unmatch -- packages/rpm/el9", website_job)
        self.assertIn('cp -a "$RPM_ARTIFACT"/. packages/rpm/el9/', website_job)
        self.assertIn('diff -qr "$RPM_ARTIFACT" packages/rpm/el9', website_job)
        self.assertIn("git add --all -- packages/rpm/el9", website_job)
        self.assertNotIn("git add -A", website_job)
        self.assertNotIn("git add .", website_job)
        self.assertNotIn("git rm -r --ignore-unmatch -- packages/apt", website_job)
        self.assertNotIn('cp -a "$RPM_ARTIFACT"/. packages/apt/', website_job)
        self.assertIn("packages/keys/ofgs-repository.asc", website_job)
        self.assertIn("packages/keys/ofgs-repository.gpg", website_job)
        self.assertIn('test "$keys_after" = "$keys_before"', website_job)
        self.assertIn("git diff --quiet -- packages/apt packages/keys", website_job)
        self.assertIn("':(exclude)packages/rpm/el9/**'", website_job)
        self.assertIn('[[ "$changed_path" == packages/rpm/el9/* ]]', website_job)

    def test_rpm_website_publication_uses_pat_without_signing_secrets(self):
        website_job = self.last_job("publish_rpm")
        pat_expression = "${{ secrets.OFGS_WEBSITE_PUBLISH_TOKEN }}"
        self.assertEqual(website_job.count(pat_expression), 2)
        self.assertNotIn(
            "${{ secrets.OFGS_REPOSITORY_GPG_PRIVATE_KEY }}", website_job
        )
        self.assertNotIn(
            "${{ secrets.OFGS_REPOSITORY_GPG_PASSPHRASE }}", website_job
        )
        self.assertNotIn(
            "${{ vars.OFGS_REPOSITORY_GPG_FINGERPRINT }}", website_job
        )
        self.assertIn("GIT_ASKPASS", website_job)
        self.assertIn("persist-credentials: false", website_job)
        self.assertIn("git push origin HEAD:main", website_job)
        self.assertNotIn("--force", website_job)
        self.assertNotIn("set -x", website_job)

    def test_rpm_website_no_change_and_shared_concurrency_are_safe(self):
        apt_job = self.job("publish_apt", "publish_rpm")
        rpm_job = self.last_job("publish_rpm")
        concurrency = "group: ofgs-package-website-publication"
        self.assertIn(concurrency, apt_job)
        self.assertIn(concurrency, rpm_job)
        self.assertIn("cancel-in-progress: false", apt_job)
        self.assertIn("cancel-in-progress: false", rpm_job)
        quiet = rpm_job.index("if git diff --cached --quiet; then")
        commit = rpm_job.index("git commit -m")
        self.assertLess(quiet, commit)
        self.assertIn('echo "changed=false" >> "$GITHUB_OUTPUT"', rpm_job)
        self.assertIn("exit 0", rpm_job[quiet:commit])
        self.assertIn("if: steps.update.outputs.changed == 'true'", rpm_job)


if __name__ == "__main__":
    unittest.main()
