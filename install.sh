#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/usr/local/share/ofgs"
wrapper_target="/usr/local/bin/ofgs"
completion_target="/usr/share/bash-completion/completions/ofgs"
legacy_wrapper_target="/usr/local/bin/gnuplot"
legacy_generator_target="$INSTALL_DIR/gnuplot_generate.py"
force=false
existing_installation=false
legacy_wrapper_found=false

is_ofgs_wrapper() {
    [[ -f "$1" ]] \
        && grep -q -e "gnuplot-generator-wrapper" -e "ofgs-wrapper" "$1"
}

is_ofgs_completion() {
    [[ -f "$1" && ! -L "$1" ]] \
        && grep -q -F "# OFGS completion owner: source" "$1"
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

if [[ -e "$completion_target" || -L "$completion_target" ]]; then
    if ! is_ofgs_completion "$completion_target"; then
        echo "Refusing to replace existing $completion_target" >&2
        exit 1
    fi
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

python3 "$project_root/scripts/install_runtime.py" \
    --prefix /usr/local \
    --bash-completion-dir /usr/share/bash-completion/completions

if [[ -e "$legacy_generator_target" || -L "$legacy_generator_target" ]]; then
    rm -f -- "$legacy_generator_target"
fi

if [[ "$legacy_wrapper_found" == true ]]; then
    rm -f -- "$legacy_wrapper_target"
fi

echo "Installed OFGS to $INSTALL_DIR"
echo "Installed OFGS executable to $wrapper_target"
echo "Installed OFGS Bash completion to $completion_target"
if [[ "$legacy_wrapper_found" == true ]]; then
    echo "Removed legacy OFGS gnuplot wrapper from $legacy_wrapper_target"
fi
