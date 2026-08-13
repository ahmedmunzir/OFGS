#!/usr/bin/env bash

set -euo pipefail

INSTALL_DIR="/usr/local/share/ofgs"
wrapper_target="/usr/local/bin/ofgs"
completion_target="/usr/share/bash-completion/completions/ofgs"
legacy_wrapper_target="/usr/local/bin/gnuplot"
wrapper_removed=false
legacy_wrapper_removed=false
ofgs_removed=false
completion_removed=false

is_ofgs_wrapper() {
    [[ -f "$1" ]] \
        && grep -q -e "gnuplot-generator-wrapper" -e "ofgs-wrapper" "$1"
}

is_ofgs_completion() {
    [[ -f "$1" && ! -L "$1" ]] \
        && grep -q -F "# OFGS completion owner: source" "$1"
}

if is_ofgs_wrapper "$wrapper_target"; then
    rm -f "$wrapper_target"
    wrapper_removed=true
else
    echo "No installed OFGS executable found at $wrapper_target"
fi

if is_ofgs_wrapper "$legacy_wrapper_target"; then
    rm -f "$legacy_wrapper_target"
    legacy_wrapper_removed=true
fi

if is_ofgs_completion "$completion_target"; then
    rm -f -- "$completion_target"
    completion_removed=true
elif [[ -e "$completion_target" || -L "$completion_target" ]]; then
    echo "Preserved non-OFGS completion at $completion_target"
fi

if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf -- "$INSTALL_DIR"
    ofgs_removed=true
fi

if [[ "$ofgs_removed" == true ]]; then
    echo "Removed OFGS from $INSTALL_DIR"
fi
if [[ "$wrapper_removed" == true ]]; then
    echo "Removed OFGS executable from $wrapper_target"
fi
if [[ "$legacy_wrapper_removed" == true ]]; then
    echo "Removed legacy OFGS gnuplot wrapper from $legacy_wrapper_target"
fi
if [[ "$completion_removed" == true ]]; then
    echo "Removed OFGS Bash completion from $completion_target"
fi
