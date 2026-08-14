# OFGS bash completion
# OFGS completion owner: @OFGS_COMPLETION_OWNER@

_ofgs_completion() {
    local command_path current
    COMPREPLY=()
    current="${COMP_WORDS[COMP_CWORD]}"

    if (( COMP_CWORD == 1 )) && [[ "$current" == */* ]]; then
        mapfile -t COMPREPLY < <(compgen -f -- "$current")
        return 0
    fi

    command_path="$(type -P -- "${COMP_WORDS[0]}" 2>/dev/null)" || return 0
    mapfile -t COMPREPLY < <(
        _OFGS_COMPLETE=bash "$command_path" \
            "${COMP_WORDS[@]:1:$COMP_CWORD}" 2>/dev/null
    )
}

complete -F _ofgs_completion ofgs
