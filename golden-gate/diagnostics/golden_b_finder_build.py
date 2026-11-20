"""Import the tested Apple GUI agent and the tested SkyLight unit into the local MBP91 builder."""
import argparse
import base64
import fcntl
import hashlib
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
BUILDER = WORK / ".work/mbp91-constructor-git"
AGENT = Path("System/Library/CoreServices/iconservicesagent")
SIGNATURE = '=anchor apple and identifier "com.apple.iconservicesagent"'
PREFIX = "GG_FINDER_BUILD_PAYLOAD "
MAX_BYTES = 16 * 1024**2
UNIT = runpy.run_path(str(HERE / "golden_b_skylight_unit.py"))
UNIT_PATH = Path("usr/lib/hao/if") / UNIT["GOLDEN_SKYLIGHT_UUID"]
AGENT_SHA256 = "0c34b609f914b0f1e1e263268528e04715ce59d4de34770cba3af1d40d752de8"
DOCK_ONLY_TREE = "725eac8c823cf3c910d34c4350b56310ed65d7aeca2410c983e3d4873b85c0a6"
DESKTOP_TREE = "59eb5b9895a988a4ac472be21e511d900a47219961f782a09c01e7132447b9fd"


def capture_command():
    """The validated, read-only internal Tahoe mount used by the GUI agent trial."""
    gate = runpy.run_path(str(HERE / "GoldenGate-Client-Intel-B.command"))["GATE"]
    donor = shlex.quote((HERE / "icon_tahoe_donor.pl").read_text())
    return gate + f"""
agent=$(/usr/bin/perl -e {donor}) || exit 3
build=$(/usr/bin/plutil -extract ProductBuildVersion raw -o - "${{agent%/*}}/SystemVersion.plist") || exit 3
[[ $build == 25G422 ]] || {{ echo "GG_FINDER_BUILD Versiunea donatorului diferă de 25G422."; exit 3; }}
sha=$(/usr/bin/shasum -a 256 "$agent") || exit 3
encoded=$(/usr/bin/base64 -i "$agent") || exit 3
/usr/bin/printf '{PREFIX}%s %s ' "$build" "${{sha%% *}}"
printf '%s' "$encoded" | /usr/bin/tr -d '\\r\\n'
printf '\\n'
"""


def artifact_path(digest):
    return Path("store/artifacts") / ("mbp91-desktop-26B131-25G422-" + digest)


def row_bytes(digest):
    return f"{digest} {artifact_path(digest)}\n".encode("ascii")


def write_row(row):
    """Advance only B's known Dock-only row; concurrent imports publish the same complete row."""
    expected = row_bytes(DESKTOP_TREE)
    directory = os.open(row.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if row.is_symlink():
            raise ValueError("Intrarea mbp91_desktop este o legătură simbolică.")
        if row.exists():
            current = row.read_bytes()
            if current == expected:
                return
            if current != row_bytes(DOCK_ONLY_TREE):
                raise ValueError("Există deja altă intrare mbp91_desktop în constructor.")
        with tempfile.TemporaryDirectory(dir=row.parent) as tmp:
            staged = Path(tmp) / row.name
            staged.write_bytes(expected)
            staged.chmod(0o644)
            os.replace(staged, row)
    finally:
        os.close(directory)


def accept_payload(line, builder=BUILDER):
    """Return a short receipt safe to print instead of the transport line."""
    if not line.startswith(PREFIX) or len(line) > 4 * ((MAX_BYTES + 2) // 3) + 128:
        raise ValueError("Captura iconservicesagent este absentă sau depășește limita.")
    version, sha, encoded = line[len(PREFIX):].strip().split()
    data = base64.b64decode(encoded, validate=True)
    if (version != "25G422" or not 0 < len(data) <= MAX_BYTES
            or sha != AGENT_SHA256 or hashlib.sha256(data).hexdigest() != sha):
        raise ValueError("Versiunea sau amprenta transferului iconservicesagent diferă.")
    rows = builder / "pipeline/inputs/golden/26B131"
    row = rows / "mbp91_desktop"
    store = builder / "store/artifacts"
    store.mkdir(parents=True, exist_ok=True)
    hash_tree = runpy.run_path(str(builder / "pipeline/lock.py"))["content_sha256"]
    with tempfile.TemporaryDirectory(prefix=".mbp91-desktop-", dir=store) as tmp:
        staged = Path(tmp) / "payload"
        agent = staged / "root" / AGENT
        agent.parent.mkdir(parents=True)
        agent.write_bytes(data)
        agent.chmod(0o755)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "--architecture", "x86_64",
                        "-R", SIGNATURE, str(agent)], check=True)
        subprocess.run(["/usr/bin/lipo", str(agent), "-verify_arch", "x86_64"], check=True)
        if b"libhao" in data.lower():
            raise ValueError("Donatorul conține o referință libhao.")
        unit = staged / "root" / UNIT_PATH
        unit.parent.mkdir(parents=True)
        unit.write_bytes(UNIT["build_unit"](include_option=True))
        unit.chmod(0o644)
        # lock.py hashes every directory mode. The interactive launcher and
        # the stand-alone importer can run with different user umasks.
        for path in staged.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
        digest = hash_tree(str(staged))
        if digest != DESKTOP_TREE:
            raise ValueError("Intrarea Finder și Dock/ferestre diferă de exemplarul Golden B.")
        rel = artifact_path(digest)
        destination = builder / rel
        try:
            staged.rename(destination)
        except OSError:
            if not destination.is_dir() or destination.is_symlink() or hash_tree(str(destination)) != digest:
                raise
        write_row(row)
    return f"GG_FINDER_BUILD Tahoe 25G422, agent Apple x86_64 SHA256={sha}, intrare mbp91_desktop={digest}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", type=Path, default=BUILDER)
    args = parser.parse_args()
    reference = runpy.run_path(str(HERE / "GoldenGate-Client-Intel-B.command"))
    ssh = runpy.run_path(str(HERE / "GoldenGate-Test-Cache-A-pe-B.command"))["SSH"]
    cmd = ssh + ["-T", reference["HOST"], "/bin/bash -c " + shlex.quote(capture_command())]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as child:
        saved = False
        for line in child.stdout:
            if line.startswith(PREFIX):
                print(accept_payload(line, args.builder.resolve()), flush=True)
                saved = True
            else:
                print(line, end="", flush=True)
        return child.wait() or (0 if saved else 3)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit(f"GG_FINDER_BUILD {exc}")
