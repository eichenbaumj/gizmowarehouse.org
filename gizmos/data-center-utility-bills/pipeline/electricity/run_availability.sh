#!/bin/sh
# The only way to start the availability flag build (p1) or audit (p2): under the committed sandbox profile.
#   sh pipeline/electricity/run_availability.sh p1|p2 --authorized-by D-NN
# A run on research data needs Joe's separate execution instruction, logged as the ledger entry D-NN names, with
# its pin block. The process stops by itself (exit 3) if the sandbox is not in force; it never proceeds without it.
#
# Before starting the process this script: resolves python3 to its real path; reads the probe file OUTSIDE the
# sandbox with that binary (so a probe that is missing, or that this interpreter cannot read for any ordinary
# reason, stops here, exit 3, and cannot pass for isolation inside); and starts that exact binary, which the process
# checks against the pinned interpreter. Between this read and the read attempted inside, no one changes the probe
# file, what its path points to, or its permissions (the checkpoint; D-76, G8). Its own permitted output is one
# line on a stop: the usage line, or "run_availability.sh stopped: <reason>".
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
repo=$(cd "$root/../.." && pwd)
access_records="$HOME/.claude/projects/-Users-jeichenbaum-Projects-personal-gizmo-warehouse/access-records"
case "${1:-}" in
  p1) script=write_usable_flag.py ;;
  p2) script=audit_availability.py ;;
  *) echo "usage: run_availability.sh p1|p2 --authorized-by D-NN"; exit 4 ;;
esac
which=$1; shift
profile="$here/sandbox/$which.sb"
probe="$here/sandbox/denied_probe.txt"
python=$(realpath "$(command -v python3)")
if ! "$python" -I -B -c 'import sys; open(sys.argv[1], "rb").read()' "$probe" > /dev/null 2>&1; then
  echo "run_availability.sh stopped: the probe file is not readable outside the sandbox"; exit 3
fi
mkdir -p "$root/data/interim/availability"
AVAILABILITY_PROFILE_SHA256=$(shasum -a 256 "$profile" | cut -d' ' -f1)
AVAILABILITY_PROBE_CHECKED=readable-outside
export AVAILABILITY_PROFILE_SHA256 AVAILABILITY_PROBE_CHECKED
exec sandbox-exec -D ROOT="$root" -D REPO="$repo" -D ACCESS_RECORDS="$access_records" -f "$profile" "$python" -I -B "$here/$script" "$@"
