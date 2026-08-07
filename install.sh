#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/usr/local/share/ofgs"
wrapper_target="/usr/local/bin/ofgs"
legacy_wrapper_target="/usr/local/bin/gnuplot"
force=false
existing_installation=false
legacy_wrapper_found=false

is_ofgs_wrapper() {
    [[ -f "$1" ]] \
        && grep -q -e "gnuplot-generator-wrapper" -e "ofgs-wrapper" "$1"
}

if [[ "${1:-}" == "--force" ]]; then
    force=true
fi

if [[ -e "$wrapper_target" ]]; then
    if ! is_ofgs_wrapper "$wrapper_target"; then
        echo "Refusing to replace existing $wrapper_target" >&2
        exit 1
    fi
    existing_installation=true
fi

if is_ofgs_wrapper "$legacy_wrapper_target"; then
    existing_installation=true
    legacy_wrapper_found=true
fi

if [[ "$existing_installation" == true ]]; then
    if [[ "$force" == false ]]; then
        printf 'Existing OFGS installation detected.\n\n'
        printf 'This will update the existing installation in place.\n\n'
        if [[ "$legacy_wrapper_found" == true ]]; then
            printf 'The legacy OFGS gnuplot wrapper at %s will be removed.\n\n' \
                "$legacy_wrapper_target"
        fi
        read -r -p 'Continue? [y/N] ' response
        case "$response" in
            y|Y) ;;
            *) exit 1 ;;
        esac
    fi
fi

install -d /usr/local/bin "$INSTALL_DIR/core"
install -m 0755 "$project_root/wrapper/ofgs" "$wrapper_target"
install -m 0755 "$project_root/gnuplot_generate.py" "$INSTALL_DIR/gnuplot_generate.py"
install -m 0644 "$project_root"/core/*.py "$INSTALL_DIR/core/"
install -m 0644 "$project_root/README.md" "$INSTALL_DIR/README.md"

if [[ "$legacy_wrapper_found" == true ]]; then
    rm -f -- "$legacy_wrapper_target"
fi

echo "Installed OFGS to $INSTALL_DIR"
echo "Installed OFGS executable to $wrapper_target"
if [[ "$legacy_wrapper_found" == true ]]; then
    echo "Removed legacy OFGS gnuplot wrapper from $legacy_wrapper_target"
fi
