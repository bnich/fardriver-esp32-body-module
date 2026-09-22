#!/usr/bin/env bash
# tools/gate.sh -- THE gate.  Every check this repo documents, in order, each
# run bare so its own exit code is what decides, stopping at the first failure
# and naming the tool that failed.  Run from anywhere; it works in the repo
# root.  Exit 0 means every check passed and the EasyEDA project is written,
# complete, from the source as it is on disk right now.
#
# Why a script and not the list of commands it replaces:
#   * `python3 -m tools.X | tail -1` returns tail's 0, not the tool's 1.  Every
#     tool here exits non-zero on failure; nothing consumed it until this.
#   * A same-second, same-size edit (`1.25` -> `9.25`) is read by CPython as
#     the OLD constant: a .pyc is validated by 32-bit mtime + size, and `-B` /
#     PYTHONDONTWRITEBYTECODE stop WRITING one, not reading it.  Step 0 below
#     removes every __pycache__ in the tree, so every later `python3` in this
#     run -- and every bare one an agent runs afterwards -- compiles from the
#     source.  Chosen over PYTHONPYCACHEPREFIX (a per-run cache directory)
#     because that only protects THIS run's subprocesses: the stale tree cache
#     would still be read by the next bare `python3 -m tools.X`, which is the
#     workflow that produced the false results.
#   * The dependencies are checked up front, by name, so a fresh clone stops
#     at "pytest is not installed", not two minutes later in a traceback.
#
# ⛔ There is deliberately no flag to build while EasyEDA Pro is open: the
# editor holds the project the build replaces, and refusing is the safety
# property.  Close the editor and run again.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() {                       # fail NAME MESSAGE...
    local name=$1; shift
    printf 'gate: %s: %s\n' "$name" "$*" >&2
    printf 'GATE FAILED at %s\n' "$name" >&2
    exit 1
}

run() {                        # run NAME COMMAND...  -- bare, exit code by name
    local name=$1; shift
    printf '\n== %s: %s\n' "$name" "$*"
    local rc=0
    "$@" || rc=$?
    printf '== %s: exit %d\n' "$name" "$rc"
    if (( rc != 0 )); then
        printf 'GATE FAILED at %s (exit %d)\n' "$name" "$rc" >&2
        exit "$rc"
    fi
}

# --- step 0: no bytecode cache may outlive an edit -----------------------------
printf '== step 0: removing every __pycache__ under %s\n' "$PWD"
find . -name __pycache__ -prune -exec rm -rf {} +

# --- dependencies, each by name ------------------------------------------------
python3 -c 'import pytest' 2>/dev/null \
    || fail pytest "not installed; the tests need it (python3 -m pip install pytest, or the distribution's python-pytest)"
python3 -c 'import cryptography' 2>/dev/null \
    || fail cryptography "not installed; the .eprj2 output needs it (python3 -m pip install cryptography)"
LCSC_HOME=${LCSC_SEARCH_HOME:-$HOME/tools/lcsc-search}
[[ -d "$LCSC_HOME/lcsc_search" ]] \
    || fail lcsc-search "not found at $LCSC_HOME; the build binds library footprints through it (set LCSC_SEARCH_HOME)"
python3 -c 'import sys; from tools import eprj2; sys.exit(0 if eprj2.find_template() else 1)' \
    || fail eprj2-template "no editor-saved .eprj2 found; open any project in EasyEDA Pro once so it saves one, or set EASYEDA_EPRJ2_TEMPLATE"
printf '== dependencies: pytest, cryptography, lcsc-search, eprj2 template -- present\n'

# --- the documented order, every tool bare -------------------------------------
run integrity     python3 -m tools.integrity
run pytest        python3 -m pytest -q
run rules         python3 -m tools.rules
run gpio_budget   python3 -m tools.gpio_budget
run power_budget  python3 -m tools.power_budget
run soft_start    python3 -m tools.soft_start
run board_fit     python3 -m tools.board_fit

# --- the build: never while the editor holds the project it replaces ----------
if ps -eo args | grep -q '[/]opt/apps/easyeda'; then
    fail easyeda-running "EasyEDA Pro is open; close it before building (there is no override)"
fi
run build_project python3 tools/build_project.py
run jlc_bom       python3 -m tools.jlc_bom

printf '\nGATE PASSED: every check exit 0; the .eprj2 in ~/Documents/EasyEDA-Pro/projects is current (or was left alone as the owner's saved layout -- see the build line).\n'
