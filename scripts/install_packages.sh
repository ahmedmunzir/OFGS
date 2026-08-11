#!/usr/bin/env bash

set -euo pipefail

OS_RELEASE="/etc/os-release"
DEBIAN_KEY="/usr/share/keyrings/ofgs-repository.gpg"
DEBIAN_SOURCE="/etc/apt/sources.list.d/ofgs.list"
ROCKY_REPOSITORY="/etc/yum.repos.d/ofgs.repo"

DEBIAN_KEY_URL="https://munzirahmed.dev/packages/keys/ofgs-repository.gpg"
DEBIAN_REPOSITORY_URL="https://munzirahmed.dev/packages/apt"
ROCKY_KEY_URL="https://munzirahmed.dev/packages/keys/ofgs-repository.asc"
ROCKY_REPOSITORY_URL="https://munzirahmed.dev/packages/rpm/el9/"
temporary_key=""

die() {
    echo "OFGS installer: $*" >&2
    exit 1
}

cleanup() {
    if [[ -n "$temporary_key" ]]; then
        rm -f -- "$temporary_key"
    fi
}

check_existing_config() {
    local path="$1"
    local expected="$2"
    local existing

    if [[ -e "$path" || -L "$path" ]]; then
        [[ -f "$path" && ! -L "$path" ]] \
            || die "refusing to replace non-regular configuration: $path"
        existing="$(<"$path")"
        [[ "$existing" == "$expected" ]] \
            || die "existing OFGS configuration conflicts with $path"
    fi
}

ensure_exact_config() {
    local path="$1"
    local expected="$2"

    check_existing_config "$path" "$expected"
    if [[ ! -e "$path" ]]; then
        printf '%s\n' "$expected" > "$path"
    fi
}

download_debian_key() {
    local destination="$1"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$DEBIAN_KEY_URL" -o "$destination"
        return
    fi

    if command -v wget >/dev/null 2>&1; then
        wget -qO "$destination" "$DEBIAN_KEY_URL"
        return
    fi

    echo "Installing the required download utility..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
    command -v curl >/dev/null 2>&1 \
        || die "curl is unavailable after package installation"
    curl -fsSL "$DEBIAN_KEY_URL" -o "$destination"
}

install_debian() {
    local source_line

    source_line="deb [signed-by=$DEBIAN_KEY] $DEBIAN_REPOSITORY_URL stable main"
    check_existing_config "$DEBIAN_SOURCE" "$source_line"
    temporary_key="$(mktemp)"

    echo "Configuring the OFGS Debian repository..."
    download_debian_key "$temporary_key"
    [[ -s "$temporary_key" ]] || die "downloaded OFGS repository key is empty"

    if [[ -e "$DEBIAN_KEY" || -L "$DEBIAN_KEY" ]]; then
        [[ -f "$DEBIAN_KEY" && ! -L "$DEBIAN_KEY" ]] \
            || die "refusing to replace non-regular key file: $DEBIAN_KEY"
    fi
    if [[ ! -e "$DEBIAN_KEY" ]] || ! cmp -s "$temporary_key" "$DEBIAN_KEY"; then
        install -D -m 0644 "$temporary_key" "$DEBIAN_KEY"
    fi
    ensure_exact_config "$DEBIAN_SOURCE" "$source_line"

    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ofgs
}

install_rocky() {
    local repository_config

    repository_config="[ofgs]
name=OFGS EL9
baseurl=$ROCKY_REPOSITORY_URL
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=$ROCKY_KEY_URL"

    echo "Enabling EPEL and configuring the OFGS EL9 repository..."
    check_existing_config "$ROCKY_REPOSITORY" "$repository_config"
    if ! rpm -q --quiet epel-release; then
        dnf install -y epel-release
    fi
    ensure_exact_config "$ROCKY_REPOSITORY" "$repository_config"
    dnf install -y ofgs
}

[[ "$(id -u)" == "0" ]] \
    || die "root privileges are required; run this installer with sudo"
[[ -r "$OS_RELEASE" ]] || die "cannot read $OS_RELEASE"
trap cleanup EXIT

ID=""
VERSION_ID=""
# /etc/os-release is system-owned metadata on the supported platforms.
# shellcheck disable=SC1090
source "$OS_RELEASE"

case "${ID:-}:${VERSION_ID:-}" in
    debian:12|debian:12.*)
        install_debian
        ;;
    rocky:9|rocky:9.*)
        install_rocky
        ;;
    debian:*|rocky:*)
        die "unsupported ${ID:-unknown} version: ${VERSION_ID:-unknown}"
        ;;
    *)
        die "unsupported operating system: ${ID:-unknown} ${VERSION_ID:-unknown}"
        ;;
esac

echo "OFGS was installed successfully."
