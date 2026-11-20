"""Apply a single pinned compatibility file to the running Golden B."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


HAO = "/usr/local/bin/hao"
UNIT = "21acabfab6cc3ec9a3cf6d4d6b637f5a"
MANIFEST_SHA = "48d856cbf9418d480d16f216aed31bf53a9561e1e82294f1c15de119a989a105"
MANIFEST_HASHES = {
    "dock": MANIFEST_SHA,
    "baterie": "4419fa973cc672d6bf0c7e15a10e24fcab6191f624963b5e314126b678a0e5b9",
    "ferestre": "1a8ea56f687b71bc5b60caaca999dde6b1c18ab5a31fcfbc65a7af2730c500a8",
    "finder": "1fc5f88d3352a722fb9c30a87b4c96a2216219423cf3f397449c74092516da1e",
}
PRIOR_SKYLIGHT = "a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f"
PRIOR_FINDER_AGENT = "cf1e92d68dcc75d290ad6ea693d04fc0d7a96d5b4be8d1ded6228751fa55bf82"
FINDER_REQUIREMENT = '=anchor apple and identifier "com.apple.iconservicesagent"'
PACK = "mbp91-dock-skylight"
REL = "usr/lib/hao/if/" + UNIT


def checked_data(encoded, digest):
    data = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Conținutul pachetului diferă de exemplarul testat.")
    return data


def stage_agent(source, destination, digest):
    if not os.path.isabs(source):
        raise ValueError("Calea agentului Tahoe trebuie să fie absolută.")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size != 243536:
            raise ValueError("Fișierul donator nu corespunde exemplarului Tahoe 25G422.")
        data = stream.read(st.st_size + 1)
    if len(data) != st.st_size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Amprenta agentului diferă de exemplarul care a reparat Finder.")
    destination.write_bytes(data)
    destination.chmod(0o755)
    # Verify the exact private staged copy that HAO will consume.
    description = subprocess.check_output(["/usr/bin/file", "-b", str(destination)])
    if b"Mach-O 64-bit executable x86_64" not in description:
        raise ValueError("Lipsește felia Intel a executabilului Tahoe.")
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "--architecture", "x86_64",
                    "-R", FINDER_REQUIREMENT, str(destination)], check=True)


def verify_plan(output, pack=PACK, rel=REL, operation="new"):
    lines = output.splitlines()
    events = [json.loads(line) for line in lines if line.startswith("{")]
    rows = [line.split() for line in lines if line.strip() and not line.startswith("{")]
    if len(events) != 1 or rows != [[operation, pack, rel]]:
        raise ValueError("Planul HAO diferă de operația aprobată pentru unitatea testată.")
    plan = events[0]
    if (plan.get("ev") != "plan" or plan.get("write") != 1 or plan.get("attrs") != 0
            or plan.get("same") != 0 or plan.get("needs_recovery") != []
            or plan.get("needs_recovery_files") != []):
        raise ValueError("Planul HAO conține alte operații.")


def apply(manifest64, payload, verifier, kind="dock"):
    if os.geteuid() != 0:
        raise ValueError("Aplicarea necesită administrator.")
    os.umask(0o077)
    os.environ["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    if kind not in MANIFEST_HASHES:
        raise ValueError("Pachet HAO necunoscut.")
    manifest = checked_data(manifest64, MANIFEST_HASHES[kind])
    spec = json.loads(manifest)
    (relative_path,) = spec["files"]
    digest = spec["files"][relative_path]["sha256"]
    unit = None if kind == "finder" else checked_data(payload, digest)
    check = [sys.executable, "-IB", "-c", verifier]
    rc = subprocess.run(check + ["--check-pending", kind]).returncode
    if rc != 10:  # Already installed (0), or an unexpected snapshot / incomplete record.
        return rc
    with tempfile.TemporaryDirectory(prefix="gg-interface-b-", dir="/private/tmp") as work:
        pack = Path(work) / "overlay"
        file = pack / "files" / relative_path
        file.parent.mkdir(parents=True)
        if unit is None:
            stage_agent(payload, file, digest)
        else:
            file.write_bytes(unit)
        (pack / "manifest.json").write_bytes(manifest)
        target = Path("/") / relative_path
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError("Destinația unității conține o legătură simbolică.")
        if kind == "finder":
            st = target.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0
                    or stat.S_IMODE(st.st_mode) != 0o755 or st.st_flags != 0x80000
                    or hashlib.sha256(target.read_bytes()).hexdigest() != PRIOR_FINDER_AGENT):
                raise ValueError("Agentul Golden sau atributele sale diferă de baza testată pe 26B131.")
        elif kind == "ferestre":
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != PRIOR_SKYLIGHT:
                raise ValueError("Unitatea existentă nu este unitatea Dock validată.")
        elif target.exists():
            raise ValueError("Destinația pentru unitatea nouă s-a schimbat.")
        command = [HAO, "patch", str(pack), "--live"]
        preview = subprocess.run(command + ["--dry-run", "--log", "json"],
                                 stdout=subprocess.PIPE, text=True)
        print(preview.stdout, end="", flush=True)
        if preview.returncode:
            return preview.returncode
        verify_plan(preview.stdout, spec["pack"], relative_path, "write" if kind in ("ferestre", "finder") else "new")
        print(f"GG_APLICARE HAO aplică {spec['pack']} pe Golden B.", flush=True)
        rc = subprocess.run(command + ["--i-have-a-backup", "--log", "json"]).returncode
        if rc:
            print(f"GG_APLICARE HAO a ieșit cu codul {rc}. Păstrează sesiunea deschisă.", flush=True)
            return rc
        return subprocess.run(check + ["--after", kind]).returncode


if __name__ == "__main__":
    try:
        sys.exit(apply(*sys.argv[1:]))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"GG_APLICARE {error}")
