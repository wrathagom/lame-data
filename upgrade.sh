#!/bin/bash
# Lame Data - Upgrade Script
# Pulls latest code, runs tests, and restarts the recorder service.
#
# Safe to run without sudo (tests still run; service won't be restarted).
# The re-exec block below means any upgrade.sh changes in the pulled commit
# take effect immediately — you can change the upgrade steps themselves and
# the NEXT upgrade will already be using the new logic.

set -eu -o pipefail

# Guard against being sourced. `exec bash "$0"` below would otherwise replace
# the user's login shell — disastrous when the only way back in is SSH.
if [ "${BASH_SOURCE[0]:-$0}" != "$0" ]; then
    echo "upgrade.sh must be executed, not sourced." >&2
    return 1 2>/dev/null || exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$SCRIPT_DIR/software/raspberry-pi"
VENV_DIR="$PI_DIR/venv"

# Make any non-zero exit visually unambiguous. The systemd service is NOT
# touched until the very last step, so any failure before then leaves the
# Pi running the previous working version.
trap 'rc=$?; if [ $rc -ne 0 ]; then
        echo ""
        echo "==================================="
        echo "  Upgrade ABORTED (exit $rc)"
        echo "  Previous service is still running."
        echo "==================================="
    fi' EXIT

echo "==================================="
echo "  Lame Data - Upgrade"
echo "==================================="
echo ""

# Check for uncommitted changes before touching the working tree.
if ! git -C "$SCRIPT_DIR" diff --quiet 2>/dev/null; then
    echo "Warning: You have local changes that may be overwritten."
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Upgrade cancelled."
        exit 1
    fi
fi

# [1/4] Pull latest code FIRST so the re-exec below picks up any changes to
# this script itself.
echo "[1/4] Pulling latest code..."
git -C "$SCRIPT_DIR" pull
echo "  Done"

# Re-exec into the just-pulled version of this script so that changes to
# the upgrade flow (new steps, new gate logic) take effect on this very run,
# not just the next one. The sentinel env var breaks the loop — the child
# invocation sees UPGRADE_REEXEC=1 and skips this block.
#
# We syntax-check the new script first. A malformed upgrade.sh caught here
# leaves the running service untouched; without this check, `exec bash` on
# a broken file would error partway through and could leave us in a weird
# state.
if [ -z "${UPGRADE_REEXEC:-}" ]; then
    if ! bash -n "$0"; then
        echo "Pulled upgrade.sh has a syntax error — aborting before re-exec." >&2
        exit 1
    fi
    export UPGRADE_REEXEC=1
    exec bash "$0" "$@"
fi

# [2/4] Update dependencies.
echo ""
echo "[2/4] Updating dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$PI_DIR/requirements.txt"
"$VENV_DIR/bin/pip" install -q -r "$PI_DIR/requirements-dev.txt"
echo "  Done"

# [3/4] Run tests BEFORE touching the running service — a bad pull should
# leave the Pi on the previous working version rather than a broken one.
echo ""
echo "[3/4] Running tests..."
if ! "$VENV_DIR/bin/pytest" -x --tb=short "$PI_DIR/tests"; then
    echo ""
    echo "  Tests failed. Keeping existing service running."
    echo "  Inspect the failure above, fix, commit, and re-run upgrade.sh."
    exit 1
fi
echo "  Passed"

# [4/4] Restart services.
echo ""
echo "[4/4] Restarting services..."
if [ "$EUID" -eq 0 ]; then
    systemctl restart horse-recorder
    echo "  horse-recorder restarted"
else
    echo "  Run with sudo to restart services, or manually run:"
    echo "    sudo systemctl restart horse-recorder"
fi

echo ""
echo "==================================="
echo "  Upgrade Complete!"
echo "==================================="
echo ""
