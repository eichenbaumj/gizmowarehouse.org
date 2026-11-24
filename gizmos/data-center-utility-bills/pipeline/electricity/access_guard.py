"""What the availability processes may touch, enforced inside Python, and how they speak.

Used by the flag build (P1, write_usable_flag.py) and the audit (P2, audit_availability.py). Opens no file
at import and imports nothing from the pipeline.

Two parts.

1. A Python audit hook (PEP 578). `decide` is a pure function of an event and a Policy, so it can be tested
   without installing anything; `install` puts it in front of the process. It refuses: any open under the
   data folder that is not on the policy's lists; any write outside the policy's write list; any directory
   listing under the data folder except the one directory the policy names; glob, link, copy, remove and
   rename events under the data folder that the policy does not allow; every subprocess, exec, spawn,
   fork and system call; loading a shared library from the data folder; and importing a module the policy
   bans. It records every event that touches the gizmo folder and every refusal, wherever it is.
   The record is a list of RECORDED EVENTS. It is not proof of every access: a native library (DuckDB,
   pyarrow given a path) opens files without raising a Python event. The operating-system sandbox
   (pipeline/electricity/sandbox/) is what limits those.

2. Sealed output. `run` executes a process's main with standard error sent to /dev/null at the file
   descriptor, warnings captured and not shown, and every exception reduced to its stage and class name.
   Only a `Refusal`, whose message the process composes from fixed text and identifiers, is printed as
   written. A process prints nothing else of its own except its predetermined lines.
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field

DENIED_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
                 "pty.spawn", "os.startfile")
DATA_MUTATIONS = ("os.symlink", "os.link", "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.copytree",
                  "shutil.rmtree", "shutil.move", "os.remove", "os.rmdir", "os.truncate", "os.chmod", "os.chown",
                  "os.mkdir", "os.utime", "shutil.make_archive", "shutil.unpack_archive")
LISTINGS = ("os.listdir", "os.scandir")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


class Refusal(Exception):
    """A refusal the process words itself, from fixed text and identifiers only. Printed as written.

    `code` is the exit code: 2 by default, 3 when operating-system isolation is not in force, 4 when the
    run is not authorized in the ledger.
    """

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


PROFILE_ENV = "AVAILABILITY_PROFILE_SHA256"
PROBE_ENV = "AVAILABILITY_PROBE_CHECKED"          # set by the launcher only after it has read the probe outside the sandbox
PROBE_READ_OUTSIDE = "readable-outside"


def sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_once(path) -> tuple[str, bytes]:
    """(SHA-256, bytes) from ONE read, so what is hashed is exactly what is parsed (D-75 item 2)."""
    import hashlib
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha256(data).hexdigest(), data


def parse_pins(text: str, header: str) -> dict:
    """{"files": {relative path: sha256}, "versions": {library: version}, "interpreter": path or None} from the ONE pin
    block in a ledger entry.

    The block starts at a line that is exactly `header` and ends at the first line that is not a pin line
    ("sha256 <hex> <path>", "version <library> <version>", "interpreter <path>"; leading spaces allowed). Refused,
    in words: two blocks; a path, library or interpreter pinned twice; a pin-shaped line anywhere else in the entry,
    which could otherwise stand beside or override the approved block (D-74, from the outside read's R2).

    What this is not (D-76, G4): a Markdown parser or a validator of what a path means. It recognizes those three
    exact line shapes and nothing else. A line in any other shape (a bullet, backticks, capitals, a colon) is neither
    a pin nor a refusal; inside the block it ends the block. A path is the string that was pinned: another spelling of
    the same file is a different, unpinned path. It is sound for the block availability_pins.py prints and the paths
    in availability_codes.py, which is all it is used for.
    """
    import re
    pats = {"sha256": re.compile(r"sha256 ([0-9a-f]{64}) (\S+)"), "version": re.compile(r"version (\S+) (\S+)"),
            "interpreter": re.compile(r"interpreter (\S+)")}
    lines = [ln.strip() for ln in text.splitlines()]
    starts = [i for i, ln in enumerate(lines) if ln == header]
    out = {"files": {}, "versions": {}, "interpreter": None}
    if not starts:
        if any(p.fullmatch(ln) for ln in lines for p in pats.values()):
            raise Refusal("not authorized: the entry has pin lines but no pin block header", 4)
        return out
    if len(starts) > 1:
        raise Refusal("not authorized: the entry carries more than one pin block", 4)
    i = starts[0] + 1
    while i < len(lines):
        ln = lines[i]
        if m := pats["sha256"].fullmatch(ln):
            if m.group(2) in out["files"]:
                raise Refusal(f"not authorized: {m.group(2)} is pinned twice", 4)
            out["files"][m.group(2)] = m.group(1)
        elif m := pats["version"].fullmatch(ln):
            if m.group(1) in out["versions"]:
                raise Refusal(f"not authorized: {m.group(1)} is pinned twice", 4)
            out["versions"][m.group(1)] = m.group(2)
        elif m := pats["interpreter"].fullmatch(ln):
            if out["interpreter"] is not None:
                raise Refusal("not authorized: the interpreter is pinned twice", 4)
            out["interpreter"] = m.group(1)
        else:
            break
        i += 1
    rest = lines[:starts[0]] + lines[i:]
    if any(p.fullmatch(ln) for ln in rest for p in pats.values()):
        raise Refusal("not authorized: a pin line stands outside the pin block", 4)
    return out


def check_authorization(ledger, entry: str | None, root=None, pinned: tuple = (), header: str | None = None) -> tuple[str, dict]:
    """The run needs `--authorized-by D-NN` naming a ledger entry that exists, speaks of the availability audit, and
    pins the hash of every file this step uses (D-72 item 2). Returns (entry, the parsed pins).

    A guard against an accidental run or changed code, not a substitute for Joe's words: the entry is where his
    words are logged, and a ledger entry mentioning availability does not by itself authorize anything. The
    ledger is the one file outside data/ these processes read on purpose.

    The pins carry "entry_sha256", the hash of the entry's own text (its title line to the line before the next
    entry, trailing blank space dropped). P1's record and the sidecar store it, and each later step compares it with
    the entry as it then stands, so a change to the entry's words or pins between steps is refused, while entries
    appended elsewhere in the ledger change nothing (D-76, G8). The pin checks and the code they cover are still
    separate reads: each file is hashed here and loaded afterwards, under the no-writer agreement (D-76, G6).
    """
    import hashlib
    import re
    if not entry or not re.fullmatch(r"D-\d+", entry):
        raise Refusal("not authorized: pass --authorized-by D-NN, the ledger entry that records the authorization to run", 4)
    text = open(ledger, encoding="utf-8").read()
    m = re.search(rf"^## {re.escape(entry)}\.(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if m is None:
        raise Refusal(f"not authorized: {entry} is not an entry in docs/DECISIONS.md", 4)
    if "availability" not in m.group(1).lower():
        raise Refusal(f"not authorized: {entry} does not speak of the availability audit", 4)
    entry_sha = hashlib.sha256(m.group(0).rstrip().encode("utf-8")).hexdigest()
    if not pinned:
        return entry, {"files": {}, "versions": {}, "interpreter": None, "entry_sha256": entry_sha}
    pins = parse_pins(m.group(1), header)
    pins["entry_sha256"] = entry_sha
    if not pins["files"]:
        raise Refusal(f"not authorized: {entry} carries no pin block ('{header}')", 4)
    for rel in pinned:
        if rel not in pins["files"]:
            raise Refusal(f"not authorized: {entry} does not pin {rel}", 4)
        if sha256(os.path.join(str(root), rel)) != pins["files"][rel]:
            raise Refusal(f"not authorized: {rel} differs from the version {entry} pins", 4)
    return entry, pins


def check_interpreter(pins: dict) -> str:
    """Refuse unless this process runs on the interpreter the entry pins, by resolved path (D-74, R2)."""
    have = os.path.realpath(sys.executable)
    if not pins.get("interpreter"):
        raise Refusal("not authorized: no interpreter is pinned", 4)
    if have != pins["interpreter"]:
        raise Refusal("not authorized: this is not the pinned interpreter", 4)
    return have


def check_versions(pinned: dict, actual: dict) -> None:
    """Refuse unless every library this step uses is at the version the entry pins."""
    for lib, have in actual.items():
        if lib not in pinned:
            raise Refusal(f"not authorized: no version of {lib} is pinned", 4)
        if pinned[lib] != have:
            raise Refusal(f"not authorized: {lib} is not at the pinned version", 4)


def check_isolation(profile, probe) -> str:
    """Stop unless this process runs under the committed sandbox profile (D-70 item 6: stop, never proceed without it).

    Three tests: the launcher's record of the profile's hash matches the committed profile; the launcher read the
    probe file outside the sandbox, with the interpreter it then started (so the file exists and that binary may
    read it); and here, inside, the operating system refuses it with "operation not permitted" (EPERM), where
    ordinary file permissions and access-control lists give "permission denied" (EACCES) (D-74, R2).

    What EPERM does and does not show (D-76, G5): it separates this refusal from an ordinary permission failure. It
    does not by itself prove that the refusal came from the intended profile, because other macOS controls can also
    answer EPERM. The evidence that isolation is in force is the combination: the launcher that started this
    process under the profile, the profile pinned by hash, a probe that was readable a moment earlier by the same
    binary and is unchanged since (the checkpoint), and the operating-system tests of what the profile denies.
    """
    import errno
    want = sha256(profile)
    if os.environ.get(PROFILE_ENV) != want:
        raise Refusal("operating-system isolation is not in force (not started by run_availability.sh with the committed profile): stopped", 3)
    if os.environ.get(PROBE_ENV) != PROBE_READ_OUTSIDE:
        raise Refusal("operating-system isolation cannot be shown (the launcher did not read the probe outside the sandbox): stopped", 3)
    try:
        with open(probe, "rb"):
            pass
    except PermissionError as e:
        if e.errno == errno.EPERM:
            return want
        raise Refusal("operating-system isolation cannot be shown (the probe is refused by file permissions, not the sandbox): stopped", 3) from None
    except FileNotFoundError:
        raise Refusal("operating-system isolation cannot be shown (the probe file is missing): stopped", 3) from None
    raise Refusal("operating-system isolation is not in force (the probe file is readable): stopped", 3)


def git_commit(repo_root) -> str:
    """The checked-out commit, read from .git without starting git. 'unknown' if it cannot be read."""
    try:
        git = os.path.join(repo_root, ".git")
        head = open(os.path.join(git, "HEAD"), encoding="utf-8").read().strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        loose = os.path.join(git, ref)
        if os.path.exists(loose):
            return open(loose, encoding="utf-8").read().strip()
        for line in open(os.path.join(git, "packed-refs"), encoding="utf-8"):
            if line.strip().endswith(" " + ref):
                return line.split()[0]
    except OSError:
        pass
    return "unknown"


def write_atomically(path, write) -> None:
    """Write through `<path>.tmp` and rename, so an interrupted write leaves the old file whole."""
    tmp = str(path) + ".tmp"
    try:
        with open(tmp, "wb") as f:
            write(f)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


@dataclass
class Policy:
    root: str                                   # the gizmo folder
    reads: frozenset = frozenset()              # files under data/ that may be read
    writes: frozenset = frozenset()             # files that may be written, anywhere
    listable: frozenset = frozenset()           # directories under data/ whose names may be listed
    renames: frozenset = frozenset()            # (source, destination) pairs that may be renamed
    banned_imports: frozenset = frozenset()     # top-level module names that may not be imported
    denied_reads: tuple = ()                    # folders outside data/ that may not be read at all (D-72 item 2)
    sibling_root: str | None = None             # the warehouse's gizmos/ folder: every other gizmo's data/ is denied
    record: list = field(default_factory=list)

    @property
    def data(self) -> str:
        return os.path.join(self.root, "data")

    def denied(self, path: str | None) -> bool:
        """A folder this process may never read, outside its own data/: the access records, and other gizmos' data/."""
        if path is None:
            return False
        if any(_under(path, d) for d in self.denied_reads):
            return True
        if self.sibling_root and _under(path, self.sibling_root) and not _under(path, self.root):
            parts = os.path.relpath(path, self.sibling_root).split(os.sep)
            return len(parts) >= 2 and parts[1] == "data"
        return False


def access_records() -> str:
    """Where D-65 preserved the code agent's transcript and where the availability copies go: never read by P1 or P2."""
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", "-Users-jeichenbaum-Projects-personal-gizmo-warehouse",
                        "access-records")


def standard_policy(root, **kw) -> "Policy":
    """A Policy with the two read denies every availability process carries (D-72 item 2)."""
    root = os.path.normpath(str(root))
    return Policy(root=root, denied_reads=(os.path.normpath(access_records()),),
                  sibling_root=os.path.dirname(root), **kw)


def _path(p) -> str | None:
    if isinstance(p, int) or p is None:
        return None
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    try:
        return os.path.normpath(os.path.abspath(os.fspath(p)))
    except TypeError:
        return None


def _under(path: str | None, folder: str) -> bool:
    return path is not None and (path == folder or path.startswith(folder + os.sep))


def _is_write(mode, flags) -> bool:
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    if isinstance(flags, int):
        return bool(flags & WRITE_FLAGS)
    return False


def decide(event: str, args: tuple, policy: Policy) -> tuple[bool, dict | None]:
    """(allowed, record entry or None) for one audit event. Pure: no I/O, no events of its own."""
    def entry(path, what, allowed):
        return {"event": event, "path": path, "what": what, "allowed": allowed}

    if event in DENIED_EVENTS or event.startswith("os.exec") or event.startswith("os.spawn"):
        return False, entry(None, "child process", False)
    if event == "import":
        name = str(args[0]) if args else ""
        if any(name == b or name.startswith(b + ".") for b in policy.banned_imports):
            return False, entry(None, f"import {name}", False)
        return True, None
    if event == "open":
        path = _path(args[0] if args else None)
        if path is None:
            return True, None
        write = _is_write(args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None)
        if write:
            ok = path in policy.writes or path == os.devnull
        elif _under(path, policy.data):
            ok = path in policy.reads
        else:
            ok = not policy.denied(path)
        noted = _under(path, policy.root) or not ok
        return ok, (entry(path, "write" if write else "read", ok) if noted else None)
    if event in LISTINGS:
        path = _path(args[0] if args else ".")
        if _under(path, policy.data):
            ok = path in policy.listable
            return ok, entry(path, "list names", ok)
        if policy.denied(path):
            return False, entry(path, "list names", False)
        return True, None
    if event == "glob.glob" or event == "glob.glob/2":
        path = _path(args[0] if args else None)
        if _under(path, policy.data) or (path is not None and _under(policy.data, os.path.dirname(path))):
            return False, entry(path, "glob", False)
        return True, None
    if event in ("os.rename", "os.replace", "shutil.move"):
        src, dst = _path(args[0]), _path(args[1]) if len(args) > 1 else None
        ok = (src, dst) in policy.renames
        if ok or _under(src, policy.data) or _under(dst, policy.data):
            return ok, entry(f"{src} -> {dst}", "rename", ok)
        return False, entry(f"{src} -> {dst}", "rename", False)
    if event in DATA_MUTATIONS:
        paths = [_path(a) for a in args[:2] if isinstance(a, (str, bytes, os.PathLike))]
        if event == "os.remove" and paths and paths[0] in policy.writes:
            return True, entry(paths[0], "remove", True)
        if any(_under(p, policy.data) for p in paths):
            return False, entry(" | ".join(p for p in paths if p), event, False)
        if not any(_under(p, policy.root) for p in paths):
            return True, None                    # outside the gizmo folder: the interpreter's own housekeeping
        return False, entry(" | ".join(p for p in paths if p), event, False)
    if event == "ctypes.dlopen":
        path = _path(args[0] if args else None)
        if _under(path, policy.data):
            return False, entry(path, "load library", False)
        return True, None
    return True, None


def install(policy: Policy) -> None:
    """Put `decide` in front of every later event in this process. It cannot be removed once installed."""
    busy = threading.local()

    def hook(event, args):
        if getattr(busy, "on", False):
            return
        busy.on = True
        try:
            ok, rec = decide(event, args, policy)
            if rec is not None:
                policy.record.append(rec)
        finally:
            busy.on = False
        if not ok:
            raise PermissionError(f"refused by the availability guard: {event} {rec['path'] if rec else ''}".rstrip())

    sys.addaudithook(hook)


def run(main, name: str) -> int:
    """Run `main(stage)` sealed. `stage` is a one-item list the process updates as it goes.

    Exit codes: whatever main returns on success or on its own predetermined failures; 2 if it stopped on an
    exception (the stage and the exception's class name are printed, never its message).
    """
    import warnings

    sys.stdout.flush()
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)                    # left closed through interpreter exit: nothing reaches standard error
    os.close(devnull)
    caught: list[str] = []
    warnings.showwarning = lambda message, category, *a, **k: caught.append(category.__name__)
    stage = ["start"]
    try:
        return int(main(stage))
    except Refusal as e:
        print(f"{name} stopped at {stage[0]}: {e}")
        return e.code
    except BaseException as e:            # noqa: BLE001 - every exception is reduced to its class name
        print(f"{name} stopped at {stage[0]}: {type(e).__name__}")
        return 2
    finally:
        sys.stdout.flush()
