#!/usr/bin/env python3
"""HAO mbp91 step 5: transfer the completed workspace; obtain pinned OS inputs.

export   --repo PATH       Make a full transferable TAR, not a small report.
prepare  --repo PATH       Fetch the three Apple inputs and ipsw tool, extract
                          Golden Gate userspace and package its x86_64 kernel.

The unchanged upstream producers are used. No expected input hash is rewritten.
This script does not assemble/install a bootable operating system.
Python 3.14; preparation requires macOS. No third-party Python modules needed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

UPSTREAM = "6bd75aab112d1078acd8e75180eb510672461365"
TREE = "77b788410c4d5d73029d1c3845305eecd8d169eb"
ASSEMBLY = "mbp91-26B131"
GOLDEN = "26B131"
DONOR = "25G342"
ARCHIVE_ROOT = "hao-patcher-mbp91"
GIB = 1024 ** 3
PINS = {
    "ipsw_27_0": "233e85a09887579d47d0b195e7db72be7f204261059c6946f719acf6b300814f",
    "installer": "3d9551b7a18c1fa2f86e7002a132ec3db34d7915fa842cb1e890480b51be4ef3",
    "kdk": "219f27c7e039b6ab3426496e0d5852d55a31d00b3d3984d855cba04377c5dba0",
    "darwin27_kernel": "3c9317518535791503970fbec322b9bba70e91f3a233536205ccd77b047ffc83",
}


class Stop(RuntimeError):
    pass


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_path(repo: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute() or ".." in p.parts:
        raise Stop("Cale de proiect nepermisa: " + value)
    result = repo / p
    if not inside(repo, result):
        raise Stop("Calea iese din proiect: " + value)
    return result


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise Stop("Nu este un obiect JSON: " + str(path))
    return value


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode:
        raise Stop("Git: " + p.stderr.strip())
    return p.stdout.strip()


def pin_row(repo: Path, name: str) -> tuple[Path, str, Path]:
    folders = [repo / "pipeline/inputs/golden" / GOLDEN,
               repo / "pipeline/inputs" / DONOR, repo / "pipeline/inputs/common"]
    for folder in folders:
        row = folder / name
        if not row.is_file():
            continue
        lines = [s.partition("#")[0].strip() for s in row.read_text().splitlines()]
        lines = [s for s in lines if s]
        if len(lines) != 1:
            raise Stop("Intrare ambigua: " + str(row))
        fields = lines[0].split(None, 1)
        if len(fields) != 2:
            raise Stop("Intrare invalida: " + str(row))
        digest, relative = fields
        if digest != "-" and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Stop("SHA256 invalid in " + str(row))
        if name in PINS and digest != PINS[name]:
            raise Stop("Versiunea/hash-ul fixat difera pentru " + name)
        return row, digest, safe_path(repo, relative)
    raise Stop("Lipseste intrarea de build: " + name)


def check_previous(repo: Path) -> dict:
    """Validate existing step 4 evidence and the files that will be transferred."""
    if git(repo, "rev-parse", "HEAD") != UPSTREAM:
        raise Stop("Copia nu mai este la commitul 6bd75aa folosit in pasii 2-4.")
    result = read_json(repo / "local/mbp91/step4-result.json")
    if result.get("model") != "MacBookPro9,1":
        raise Stop("Rezultatul anterior nu este pentru MacBookPro9,1.")
    if not all(result.get(k) is True for k in
               ("sources_ready", "python_site_ready", "base_efi_built", "ocvalidate_ok")):
        raise Stop("Pasul 4 nu este complet in aceasta copie.")
    for relative, digest in result.get("written_files", {}).items():
        p = safe_path(repo, relative)
        if not p.is_file() or sha(p) != digest:
            raise Stop("Fisierul pasului 4 s-a schimbat: " + relative)
    record_path = repo / "local/mbp91/step4-base-efi-record.json"
    if sha(record_path) != result["base_efi_record_sha256"]:
        raise Stop("Metadatele EFI nu corespund pasului 4.")
    record = read_json(record_path)
    efi = safe_path(repo, result["efi_path"])
    for relative, digest in record["files"].items():
        p = safe_path(efi, relative)
        if not p.is_file() or sha(p) != digest:
            raise Stop("Lipseste/difera fisierul EFI: " + relative)
    source = safe_path(repo, result["oclp_source"])
    if git(source, "rev-parse", "HEAD^{tree}") != TREE:
        raise Stop("Arborele sursei OCLP difera.")
    if not (repo / "store/artifacts/mbp91-oclp-hardware-v1/build.json").is_file():
        raise Stop("Lipseste pachetul hardware real; o arhiva mica de raport nu este suficienta.")
    return result


def archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = Path(info.name).parts
    # Some upstream artifacts hash .DS_Store and similar files: retain them.
    # Only disposable Python caches OUTSIDE store/ are omitted.
    if "__pycache__" in parts and not (len(parts) > 1 and parts[1] == "store"):
        return None
    if "/local/mbp91/backups/" in info.name or info.name.endswith("/local/mbp91/backups"):
        return None
    # Store downloads, source checkouts, .git and actual artifacts are retained.
    if info.issym():
        link = Path(info.linkname)
        if link.is_absolute():
            raise Stop("Link absolut in proiect; transferul nu l-ar putea reproduce: " + info.name)
        depth = len(parts) - 1
        for component in link.parts:
            if component == "..":
                depth -= 1
                if depth < 1:
                    raise Stop("Link care iese din proiect: " + info.name)
            elif component != ".":
                depth += 1
    if not (info.isfile() or info.isdir() or info.issym() or info.islnk()):
        raise Stop("Tip special de fisier in proiect: " + info.name)
    return info


def export_workspace(repo: Path, output: Path) -> int:
    check_previous(repo)
    print("1/2 Verific proiectul si includ pachetele reale din store/.", flush=True)
    local_script = repo / "local/mbp91/HAO-mbp91-step5.py"
    if Path(__file__).resolve() != local_script.resolve():
        shutil.copy2(Path(__file__).resolve(), local_script)
    if inside(repo, output):
        raise Stop("Arhiva de transfer trebuie sa fie in afara proiectului.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise Stop("Arhiva exista deja: " + str(output) + ". Mut-o sau foloseste --output ALT_FISIER.")
    used = 0
    for base, dirs, files in os.walk(repo, followlinks=False):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            p = Path(base) / name
            if not p.is_symlink():
                used += p.stat().st_size
    if shutil.disk_usage(output.parent).free < used + GIB:
        raise Stop("Spatiu insuficient pentru arhiva completa.")
    temp = output.with_name(output.name + ".partial")
    if temp.exists():
        raise Stop("Exista o arhiva partiala: " + str(temp))
    print("2/2 Creez arhiva completa de transfer (nu arhiva mica pentru chat).", flush=True)
    with tarfile.open(temp, "w", format=tarfile.PAX_FORMAT, dereference=False) as t:
        t.add(repo, arcname=ARCHIVE_ROOT, filter=archive_filter)
    os.replace(temp, output)
    digest = sha(output)
    output.with_name(output.name + ".sha256").write_text(digest + "  " + output.name + "\n")
    print("\nARHIVA COMPLETA: " + str(output))
    print("Marime: %.2f GiB" % (output.stat().st_size / GIB))
    print("Copiaza arhiva si fisierul .sha256 pe iMac, in Downloads.")
    print("Nu trimite aceasta arhiva mare in chat.")
    return 0


class Work:
    def __init__(self, repo: Path):
        self.repo = repo
        self.local = repo / "local/mbp91"
        self.local.mkdir(parents=True, exist_ok=True)
        self.log_path = self.local / "step5-build.log"
        self.log = self.log_path.open("a", encoding="utf-8")
        self.result = {
            "schema": "hao-mbp91-step5-v1", "upstream_commit": UPSTREAM,
            "model": "MacBookPro9,1", "golden_build": GOLDEN, "donor_build": DONOR,
            "apple_inputs_ready": False, "userspace_ready": False, "kernel_ready": False,
            "runtime_archive_available": False, "runtime_payload_ready": False,
            "image_built": False, "final_golden_efi_ready": False, "boot_validated": False,
            "downloads": {}, "errors": [],
            "remaining": ["Tahoe donor extraction and compatibility artifacts",
                          "hao-runtime payload preparation/build from source if unpublished",
                          "Target-aware image assembly and final Hao EFI additions",
                          "Boot test on MacBookPro9,1"],
        }
        self.log.write("\n=== RUN " + stamp() + " ===\n")

    def run(self, argv: list[str | Path], *, capture: bool = False,
            timeout: int | None = None, input_data: bytes | None = None,
            check: bool = True) -> subprocess.CompletedProcess:
        cmd = [str(x) for x in argv]
        self.log.write("$ " + " ".join(cmd) + "\n"); self.log.flush()
        if capture:
            p = subprocess.run(cmd, cwd=self.repo, input=input_data,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            self.log.write(p.stdout.decode(errors="replace"))
            self.log.write(p.stderr.decode(errors="replace")); self.log.flush()
        else:
            # Keep the producer's progress visible and record it in the same log.
            with subprocess.Popen(cmd, cwd=self.repo, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1) as proc:
                assert proc.stdout is not None
                for line in proc.stdout:
                    print(line, end="", flush=True); self.log.write(line); self.log.flush()
                code = proc.wait()
            p = subprocess.CompletedProcess(cmd, code, b"", b"")
        if check and p.returncode:
            raise Stop("Comanda a esuat (cod %d): %s; vezi step5-build.log" % (p.returncode, cmd[0]))
        return p

    def verify_row(self, name: str, *, required: bool = True) -> bool:
        row, _, _ = pin_row(self.repo, name)
        p = self.run([sys.executable, "-I", "-B", "pipeline/lock.py", "path", row.parent, name],
                     capture=True, check=False)
        if p.returncode and required:
            raise Stop("Intrarea %s nu corespunde hash-ului fixat; nu modific hash-ul." % name)
        return p.returncode == 0

    def save(self) -> None:
        write_json(self.local / "step5-result.json", self.result)

    def report(self) -> Path:
        self.log.flush()
        self.save()
        archive = Path.home() / "Desktop/HAO-mbp91-step5.zip"
        names = ["local/mbp91/step5-result.json", "local/mbp91/step5-build.log",
                 "local/mbp91/step5-download-plan.json", "local/mbp91/step4-result.json",
                 "pipeline/assemblies/mbp91-26B131.json", "pipeline/targets/mbp91.json"]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for name in names:
                path = self.repo / name
                if path.is_file():
                    z.write(path, name)
        return archive


def url_allowed(url: str) -> bool:
    from urllib.parse import urlparse
    u = urlparse(url)
    return (u.scheme == "https" and not u.username and not u.password
            and u.hostname in {"github.com", "updates.cdn-apple.com", "swcdn.apple.com"})


def fetch_file(w: Work, dest: Path, url: str, expected: str, aliases: list[str] = ()) -> dict:
    if not url_allowed(url) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise Stop("Sursa/hash nevalid pentru " + dest.name)
    if dest.is_file():
        print("  Verific fisierul existent: " + dest.name, flush=True)
        if sha(dest) == expected:
            return {"path": str(dest.relative_to(w.repo)), "sha256": expected,
                    "bytes": dest.stat().st_size, "source": url, "reused": True}
        raise Stop("Fisier existent cu hash diferit: %s. Nu il inlocuiesc automat." % dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for filename in dict.fromkeys([dest.name, *aliases]):
        candidate = Path.home() / "Downloads" / filename
        if candidate.is_file() and not candidate.is_symlink() and sha(candidate) == expected:
            print("  Refolosesc din Downloads: " + filename, flush=True)
            try:
                os.link(candidate, dest)
            except OSError:
                shutil.copy2(candidate, dest)
            return {"path": str(dest.relative_to(w.repo)), "sha256": expected,
                    "bytes": dest.stat().st_size, "source": str(candidate), "reused": True}
    partial = dest.with_name(dest.name + ".partial")
    print("  Descarc (cu reluare): " + dest.name, flush=True)
    command = ["/usr/bin/curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
               "--connect-timeout", "20", "--retry", "3", "--retry-delay", "3",
               "--speed-limit", "1024", "--speed-time", "120", "--continue-at", "-",
               "--output", str(partial), url]
    # curl progress is displayed directly. The command/return code goes to the report.
    w.log.write("$ " + " ".join(command) + "\n"); w.log.flush()
    p = subprocess.run(command, cwd=w.repo)
    w.log.write("curl returncode=%d\n" % p.returncode); w.log.flush()
    if p.returncode:
        raise Stop("Descarcarea a esuat pentru %s (curl %d); fisierul partial este pastrat pentru reluare."
                   % (dest.name, p.returncode))
    print("  Verific SHA256: " + dest.name, flush=True)
    actual = sha(partial)
    if actual != expected:
        bad = partial.with_name(partial.name + ".wrong-sha256-" + stamp())
        partial.rename(bad)
        raise Stop("SHA256 gresit pentru %s; fisier pastrat separat: %s" % (dest.name, bad.name))
    os.replace(partial, dest)
    return {"path": str(dest.relative_to(w.repo)), "sha256": expected,
            "bytes": dest.stat().st_size, "source": url, "reused": False}


def artifact_parent(repo: Path, row_name: str, suffix: tuple[str, ...]) -> tuple[Path, Path]:
    _, _, output = pin_row(repo, row_name)
    if output.parts[-len(suffix):] != suffix:
        raise Stop("Structura intrarii %s nu mai este cea verificata." % row_name)
    parent = output
    for _ in suffix:
        parent = parent.parent
    if not inside(repo / "store/artifacts", parent):
        raise Stop("Artefact in afara store/artifacts: " + str(parent))
    return parent, output


def read_ipsw_identity(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        m = plistlib.loads(z.read("BuildManifest.plist"))
    if m.get("ProductBuildVersion") != GOLDEN:
        raise Stop("BuildManifest nu identifica Golden Gate " + GOLDEN)
    choices = [i for i in m["BuildIdentities"] if i["Info"].get("DeviceClass") == "j293ap"
               and i["Info"].get("Variant") == "Customer Erase Install (IPSW)"]
    if len(choices) != 1:
        raise Stop("IPSW: identitatea de extragere j293ap lipseste sau este ambigua.")
    return {"build": m["ProductBuildVersion"], "version": m.get("ProductVersion"),
            "source_board": "j293ap", "target_model": "MacBookPro9,1"}


def make_userspace(w: Work, files: dict) -> Path:
    root, payload = artifact_parent(w.repo, "golden_gate_userspace", ("payload",))
    if root.exists():
        w.verify_row("golden_gate_userspace")
        print("  Userspace existent, verificat: refolosit.", flush=True)
        return payload
    partial = root.with_name(root.name + ".partial-step5-" + stamp())
    root.parent.mkdir(parents=True, exist_ok=True)
    w.result["userspace_work"] = str(partial.relative_to(w.repo)); w.save()
    w.run([sys.executable, "-I", "-B", "patches/golden-gate-userspace/build/make",
           "--ipsw", files["ipsw_27_0"], "--board", "j293ap", "--ipsw-tool", files["ipsw_tool"],
           "--out", partial])
    metadata = read_json(partial / "build.json")
    if metadata.get("status") != "complete" or metadata.get("build") != GOLDEN:
        raise Stop("Extragerea nu a produs un userspace complet pentru " + GOLDEN)
    os.replace(partial, root)
    w.verify_row("golden_gate_userspace")
    w.result["userspace_path"] = str(payload.relative_to(w.repo))
    w.result["userspace_components"] = metadata.get("components", {})
    return payload


def make_kernel(w: Work, payload: Path) -> Path:
    root, kernel = artifact_parent(w.repo, "darwin27_kernel", ("payload", "kernel"))
    if root.exists():
        w.verify_row("darwin27_kernel")
        print("  Kernel existent, verificat: refolosit.", flush=True)
        return kernel
    partial = root.with_name(root.name + ".partial-step5-" + stamp())
    tmp_root = w.repo / "store/tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    mount = Path(tempfile.mkdtemp(prefix="mbp91-step5-system-", dir=tmp_root))
    attached = False
    try:
        p = w.run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-owners", "on",
                   "-plist", "-mountpoint", mount, payload / "filesystem.dmg"], capture=True)
        attached = True
        data = plistlib.loads(p.stdout)
        if not any(x.get("mount-point") == str(mount) for x in data.get("system-entities", [])):
            raise Stop("Imaginea System nu s-a montat in directorul alocat.")
        original = mount / "System/Library/Kernels/kernel"
        if not original.is_file() or sha(original) != PINS["darwin27_kernel"]:
            raise Stop("Kernelul extras nu corespunde celui x86_64 fixat de Hao.")
        root.parent.mkdir(parents=True, exist_ok=True)
        w.run([sys.executable, "-I", "-B", "tools/kernel-foundation/make", "kernel",
               "--kernel", original, "--out", partial])
        os.replace(partial, root)
        w.verify_row("darwin27_kernel")
        w.result["kernel_record"] = read_json(root / "build.json")
        return kernel
    finally:
        if attached:
            p = w.run(["/usr/bin/hdiutil", "detach", mount], capture=True, check=False)
            if p.returncode:
                w.result.setdefault("warnings", []).append("Nu s-a demontat imaginea read-only: " + str(mount))
        try:
            mount.rmdir()
        except OSError:
            pass


def get_runtime_archive(w: Work, classes: dict) -> None:
    runtime = classes.get("hao_runtime", {})
    url, digest = runtime.get("url"), runtime.get("source_sha256")
    if not url or not digest:
        w.result["runtime_status"] = "no_public_archive_declared"
        return
    # A bounded request checks availability; it is not a fake release.json.
    p = w.run(["/usr/bin/curl", "--silent", "--show-error", "--location", "--head",
               "--connect-timeout", "10", "--max-time", "40", "--output", "/dev/null",
               "--write-out", "%{http_code}", url], capture=True, check=False)
    status = p.stdout.decode(errors="replace").strip()
    w.result["runtime_url"] = url
    w.result["runtime_http_status"] = status
    if p.returncode or status != "200":
        w.result["runtime_status"] = "public_archive_unavailable; source build still required"
        print("  Arhiva runtime nu este accesibila (HTTP %s). Nu substitui un alt build." % status, flush=True)
        return
    from urllib.parse import urlparse, unquote
    dest = w.repo / "store/downloads/mbp91-step5" / Path(unquote(urlparse(url).path)).name
    record = fetch_file(w, dest, url, digest)
    w.result["runtime_archive_available"] = True
    w.result["runtime_archive"] = record
    w.result["runtime_status"] = "archive_verified; Apple-derived payload not generated yet"


def prepare(repo: Path) -> int:
    if sys.platform != "darwin":
        raise Stop("prepare se executa pe macOS; nu poate monta imaginile pe acest sistem.")
    check_previous(repo)
    w = Work(repo)
    lock = w.local / ".step5-running"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Stop("Exista deja marcajul unei rulari: %s. Nu pornesc doua pregatiri simultane." % lock)
    os.write(fd, (str(os.getpid()) + "\n").encode()); os.close(fd)
    exitcode = 1
    try:
        print("1/5 Pregatesc intrarile fixate pentru Golden Gate 26B131 si Tahoe 25G342.", flush=True)
        classes = read_json(repo / "pipeline/release-classes.json")["rows"]
        names = ("ipsw_27_0", "installer", "kdk", "ipsw_tool")
        plan = {}
        for name in names:
            row, digest, dest = pin_row(repo, name)
            entry = classes[name]
            if digest == "-" or entry.get("class") != "download" or not url_allowed(entry.get("url", "")):
                raise Stop("Intrare de descarcare neacceptata: " + name)
            plan[name] = {"row": str(row.relative_to(repo)), "sha256": digest,
                          "path": str(dest.relative_to(repo)), "url": entry["url"], "name": entry["name"]}
        write_json(w.local / "step5-download-plan.json", plan)
        # This is a conservative operational reserve, not a project minimum.
        if shutil.disk_usage(repo).free < 140 * GIB:
            raise Stop("Pentru aceasta extragere completa am rezervat conservator 140 GiB liberi. "
                       "Foloseste copia de pe iMac sau o locatie APFS cu acest spatiu.")
        files = {}
        print("2/5 Descarc si verific sursele Apple si utilitarul ipsw.", flush=True)
        for name in names:
            entry = plan[name]
            dest = safe_path(repo, entry["path"])
            aliases = [entry["name"]]
            if name == "installer":
                aliases.append("InstallAssistant.pkg")
            w.result["downloads"][name] = fetch_file(w, dest, entry["url"], entry["sha256"], aliases)
            w.verify_row(name)
            files[name] = dest
            w.save()
        w.result["apple_inputs_ready"] = True
        w.result["ipsw_identity"] = read_ipsw_identity(files["ipsw_27_0"])
        w.save()
        print("3/5 Extrag System, OS cryptex, App cryptex si Rosetta din Golden Gate.", flush=True)
        payload = make_userspace(w, files)
        w.result["userspace_ready"] = True; w.save()
        print("4/5 Pregatesc kernelul Darwin 27 x86_64 si verific hash-ul Hao.", flush=True)
        kernel = make_kernel(w, payload)
        w.result["kernel_path"] = str(kernel.relative_to(repo))
        w.result["kernel_ready"] = True; w.save()
        print("5/5 Verific separat arhiva publica hao-runtime, fara a o confunda cu imaginea finala.", flush=True)
        get_runtime_archive(w, classes)
        exitcode = 0
    except (Exception, KeyboardInterrupt) as error:
        w.result["errors"].append(type(error).__name__ + ": " + str(error))
        print("\nOPRIT: " + str(error), flush=True)
        w.log.write("\nERROR: " + repr(error) + "\n")
    finally:
        w.result["step_complete"] = exitcode == 0
        w.result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report = w.report()
        w.log.close()
        lock.unlink(missing_ok=True)
        print("\nSurse Apple verificate: " + ("DA" if w.result["apple_inputs_ready"] else "NU"))
        print("Userspace Golden Gate extras si verificat: " + ("DA" if w.result["userspace_ready"] else "NU"))
        print("Kernel Darwin 27 x86_64 verificat: " + ("DA" if w.result["kernel_ready"] else "NU"))
        print("Arhiva runtime disponibila: " + ("DA" if w.result["runtime_archive_available"] else "NU"))
        print("Imagine bootabila construita: NU. EFI Golden Gate final: NU.")
        print("Arhiva MICA de trimis: " + str(report))
    return exitcode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    exp = sub.add_parser("export", help="archive the complete existing workspace on the MacBook")
    exp.add_argument("--repo", type=Path, default=Path.cwd())
    exp.add_argument("--output", type=Path, default=Path.home() / "Desktop/HAO-mbp91-workspace.tar")
    prep = sub.add_parser("prepare", help="download and extract OS inputs on the iMac")
    prep.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        repo = args.repo.expanduser().resolve()
        if args.mode == "export":
            return export_workspace(repo, args.output.expanduser().resolve())
        return prepare(repo)
    except (Stop, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("OPRIT: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
