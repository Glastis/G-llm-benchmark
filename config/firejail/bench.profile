# Sandbox for the runs (PLAN §10.8, ARCHITECTURE §7).
# The runner (bench/runner.py, `sandboxed`) adds what is specific to each run on the command line:
#   - writable: the run's workspace and its state folder;
#   - read-only: the claude binary, $PYENV_ROOT and $NVM_DIR if set, and the copy of bench-worker.
# With these whitelists, Firejail replaces the home with an empty one: everything else, including the
# bench repository and the user's Claude Code config, is invisible.

# Hardening.
caps.drop all
nonewprivs
noroot
nogroups
seccomp
private-tmp
# Minimal /dev and a per-run /dev/shm: without it, /dev/shm is shared with the machine, and so between runs.
private-dev
# No graphical session, no D-Bus (keyring, notifications), no devices:
# a command-line agent needs none of them, and they all give access to the user's session.
# `x11 none` is incompatible with a shared network: the X cookie is removed instead (the X server
# refuses clients without a cookie) and the session sockets are hidden, including the SSH agent, gpg,
# the keyring, Wayland and PipeWire.
blacklist ${RUNUSER}
blacklist ${HOME}/.Xauthority
dbus-user none
dbus-system none
nosound
no3d
novideo
noinput
nou2f

# Network shared with the host: Strata on 127.0.0.1:8080 and the Anthropic servers must be reachable.
# Firejail does not filter by domain, an accepted limitation (PLAN §9).
