"""Run the local icon shader fixture once per explicitly selected remote Metal device."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
PYTHON = "/usr/bin/python3"
MODES = ("intel", "nvidia")
SHADER_SHA = "faebda663e14aceaef91f9eb51c9a34ce3320b89690e46227d2e2bbb909c380f"
RUNTIME_SHA = "989daf7d002118391328c0caebd5a5baa708454e61ad4c81e0af81eae5fb15f9"
NATIVE = "native-x86_64-ctypes"
JXA = "osascript-JXA"
SSH = ["/usr/bin/ssh", "-T", "-F", "/dev/null", "-o", "StrictHostKeyChecking=yes",
       "-o", "UpdateHostKeys=no", "-o", "ClearAllForwardings=yes",
       "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-o", "ConnectTimeout=10",
       "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]

REMOTE = r"""
set -eu -o pipefail
umask 077
export LC_ALL=C
model=$(/usr/sbin/sysctl -n hw.model)
build=$(/usr/bin/sw_vers -buildVersion)
printf 'TARGET\t%s\t%s\n' "$model" "$build"
if [[ "$model" != MacBookPro9,1 || "$build" != 26B131 ]]; then
    echo 'Oprit. Testul este pentru MacBookPro9,1 cu Golden 26B131.' >&2
    exit 2
fi
folder=$(/usr/bin/mktemp -d /private/tmp/GoldenGate-WiFi-Metal.XXXXXXXX)
trap '/bin/rm -rf "$folder"' EXIT
trap 'exit 130' HUP INT TERM
/usr/bin/tar -C "$folder" -xzf -
cd "$folder"
sum=$(/usr/bin/shasum -a 256 probe.metallib)
[[ ${sum%% *} == __SHADER_SHA__ ]] || { echo 'Shaderul primit nu corespunde.' >&2; exit 2; }
sum=$(/usr/bin/shasum -a 256 metal-python.tar.gz)
[[ ${sum%% *} == __RUNTIME_SHA__ ]] || { echo 'Arhiva Python primită nu corespunde.' >&2; exit 2; }
/usr/bin/tar -xzf metal-python.tar.gz

limit() {
    /usr/bin/perl -e 'alarm shift; exec {$ARGV[0]} @ARGV or die "exec: $!"' "$@"
}
field64() {
    /usr/bin/head -c "$2" "$1" | /usr/bin/base64 | /usr/bin/tr -d '\r\n'
}
bridge_status=0
python="$folder/metal-python/bin/python3.12"
limit 20 "$python" -I -S -B native-metal.py --bridge-test >preflight.txt 2>&1 || bridge_status=$?
if (( bridge_status == 0 )); then
    backend=native-x86_64-ctypes
    runner=("$python" -I -S -B native-metal.py)
else
    backend=osascript-JXA
    runner=(/usr/bin/osascript -l JavaScript metal-render.js)
fi
printf 'BRIDGE\t%s\t%s\t' "$bridge_status" "$backend"
field64 preflight.txt 1600
printf '\n'
echo "MacBook: verificare interfață nativă: $bridge_status; motor de test: $backend." >&2
for gpu in intel nvidia; do
    echo "MacBook: test Metal pe $gpu..." >&2
    status=0
    limit 85 "${runner[@]}" "$gpu" "$folder/probe.metallib" \
        "$folder/wifi-mask.json" >"$gpu.json" 2>"$gpu.err" || status=$?
    printf 'GPU\t%s\t%s\t' "$gpu" "$status"
    field64 "$gpu.json" 250000
    printf '\t'
    field64 "$gpu.err" 1600
    printf '\n'
done
echo DONE
""".replace("__SHADER_SHA__", SHADER_SHA).replace("__RUNTIME_SHA__", RUNTIME_SHA)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def reference_mask():
    result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript",
                             str(HERE / "wifi-mask.js"), "32"],
                            timeout=25, check=True, capture_output=True, text=True)
    mask = json.loads(result.stdout)
    rows = mask.get("rows", [])
    if len(rows) != 32 or any(not isinstance(row, str) or not re.fullmatch("[01]{32}", row) for row in rows):
        raise ValueError("Contur Wi-Fi invalid.")
    count = sum(row.count("1") for row in rows)
    if (mask.get("size") != 32 or mask.get("symbol") != "wifi" or mask.get("selectedPixels") != count
            or not 32 <= count <= 920 or not mask.get("systemBuild")):
        raise ValueError("Date de referință Wi-Fi incomplete.")
    return mask


def check_runtime_locally(runtime):
    # The pinned private archive contains only normal files and directories.
    with tarfile.open(fileobj=io.BytesIO(runtime), mode="r:gz") as contents:
        executable = "metal-python/bin/python3.12"
        members = contents.getmembers()
        names = set()
        for member in members:
            path = Path(member.name)
            if (not path.parts or path.parts[0] != "metal-python" or ".." in path.parts
                    or not (member.isfile() or member.isdir()) or path in names):
                raise ValueError("Arhiva Python conține un membru neașteptat.")
            names.add(path)
        if Path(executable) not in names or not contents.getmember(executable).isfile():
            raise ValueError("Arhiva Python nu conține executabilul x86_64.")
        if not contents.getmember(executable).mode & 0o100:
            raise ValueError("Executabilul Python din arhivă nu are drept de execuție.")
        with tempfile.TemporaryDirectory(prefix="golden-gate-metal-check-") as scratch:
            contents.extractall(scratch)
            result = subprocess.run([str(Path(scratch) / executable), "-I", "-S", "-B",
                                     str(HERE / "native-metal.py"), "--bridge-test"],
                                    timeout=30, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Interfața nativă locală a eșuat ({result.returncode}): "
                             + (result.stderr or result.stdout).strip()[:1200])
        print("Interfața nativă pe iMac:", result.stdout.strip(), flush=True)


def prepare(check=False):
    shader = (HERE / "probe.metallib").read_bytes()
    if hashlib.sha256(shader).hexdigest() != SHADER_SHA:
        raise ValueError("Biblioteca Metal precompilată are o amprentă neașteptată.")
    runtime = (HERE / "metal-python.tar.gz").read_bytes()
    if hashlib.sha256(runtime).hexdigest() != RUNTIME_SHA:
        raise ValueError("Runtime-ul Python precompilat are o amprentă neașteptată.")
    if check:
        check_runtime_locally(runtime)
    mask = reference_mask()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz", compresslevel=1) as bundle:
        for name, data in [("metal-render.js", (HERE / "metal-render.js").read_bytes()),
                           ("native-metal.py", (HERE / "native-metal.py").read_bytes()),
                           ("metal-python.tar.gz", runtime),
                           ("probe.metallib", shader), ("wifi-mask.json", json.dumps(mask).encode())]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o600
            bundle.addfile(member, io.BytesIO(data))
    return mask, archive.getvalue()


def unavailable(gpu, reason):
    return {"event": "gpu-render", "key": gpu, "reason": reason, "cases": []}


def decode_case(gpu, status, stdout, stderr):
    details = base64.b64decode(stderr, validate=True).decode("utf-8", "replace").strip()
    if status:
        issue = "timp depășit (85 s)" if status == 142 else f"proces încheiat cu status {status}"
        return unavailable(gpu, issue + (f" — {details}" if details else ""))
    raw = base64.b64decode(stdout, validate=True)
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get("event") != "gpu-render" or record.get("key") != gpu:
        raise ValueError("Identitate de rezultat neașteptată.")
    return record


def parse_output(output, ssh_status):
    records = {}
    identity = None
    bridge = None
    backend = None
    bridge_invalid = False
    finished = False
    errors = []
    seen = set()
    for line in output.decode("utf-8", "replace").splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[0] == "TARGET":
            if identity is not None:
                errors.append("Antet SSH duplicat.")
            identity = fields[1:]
        elif fields[0] == "BRIDGE":
            try:
                if len(fields) != 4 or bridge is not None:
                    raise ValueError()
                code = int(fields[1])
                expected = NATIVE if code == 0 else JXA
                if not 0 <= code <= 255 or fields[2] != expected:
                    raise ValueError()
                diagnostic = base64.b64decode(fields[3], validate=True).decode("utf-8", "replace").strip()
                bridge = {"exitStatus": code, "diagnostic": diagnostic}
                backend = expected
            except (ValueError, TypeError):
                bridge_invalid = True
        elif len(fields) == 5 and fields[0] == "GPU" and fields[1] in MODES:
            gpu = fields[1]
            if gpu in seen:
                records[gpu] = unavailable(gpu, "Două rezultate pentru același GPU.")
                errors.append("Rezultat duplicat.")
                continue
            seen.add(gpu)
            try:
                records[gpu] = decode_case(gpu, int(fields[2]), fields[3], fields[4])
            except (ValueError, TypeError, UnicodeError) as exc:
                records[gpu] = unavailable(gpu, f"Răspuns JSON invalid: {exc}")
        elif line == "DONE":
            finished = True
    if ssh_status:
        errors.append(f"Sesiunea SSH s-a încheiat cu status {ssh_status}.")
    if identity != ["MacBookPro9,1", "26B131"]:
        errors.append("Identitatea țintei Golden 26B131 lipsește sau diferă.")
        records = {}
    if bridge_invalid or bridge is None:
        errors.append("Verificarea interfeței native și alegerea motorului lipsesc sau sunt nevalide.")
        records = {}
        backend = None
    if not finished:
        errors.append("Lipsește marcajul final al sesiunii.")
    missing = " ".join(errors) or "Lipsește rezultatul GPU din sesiune."
    for gpu in MODES:
        records.setdefault(gpu, unavailable(gpu, missing))
    return records, {"target": identity, "nativePreflight": bridge, "backend": backend,
                     "finished": finished, "sshStatus": ssh_status, "issues": errors}


def target_arg(args):
    if len(args) > 1:
        raise ValueError("Utilizare: Test-Randare.command [utilizator@gazdă | --check]")
    name = args[0] if args else os.environ.get("GOLDEN_GATE_SSH", "")
    if not name and (HERE / "target.txt").is_file():
        name = (HERE / "target.txt").read_text().strip()
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*@[a-zA-Z0-9][a-zA-Z0-9.\-]*", name):
        raise ValueError("Indică utilizator@gazdă pentru conexiunea SSH către MacBook.")
    return name


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    target = None if args == ["--check"] else target_arg(args)
    mask, archive = prepare(check=target is None)
    if target is None:
        subprocess.run(["/bin/bash", "-n"], input=REMOTE.encode(), check=True)
        if not (HERE / "report.py").is_file():
            raise FileNotFoundError("Lipsește report.py")
        print(f"Pregătit. Simbol Wi-Fi AppKit {mask['systemBuild']}, "
              f"{mask['selectedPixels']}/1024 pixeli activi. Shader și runtime x86_64 verificate. Fără conexiune SSH.")
        return 0

    directory = Path(tempfile.mkdtemp(prefix="GoldenGate-Randare-WiFi-", dir=HERE.parent))
    write_json(directory / "wifi-mask.json", mask)
    print("Raport pe iMac:", directory, flush=True)
    command = shlex.join(("/bin/bash", "-c", REMOTE))
    try:
        run = subprocess.run(SSH + [target, command], input=archive,
                             stdout=subprocess.PIPE, timeout=300)
        records, transport = parse_output(run.stdout, run.returncode)
    except subprocess.TimeoutExpired as exc:
        records, transport = parse_output(exc.stdout or b"", 124)
    except OSError as exc:
        records, transport = parse_output(b"", 255)
        transport["issues"].append(str(exc))
    for gpu in MODES:
        write_json(directory / f"{gpu}.json", records[gpu])
    transport["shaderSHA256"] = SHADER_SHA
    transport["runtimeSHA256"] = RUNTIME_SHA
    write_json(directory / "sesiune.json", transport)
    if transport["backend"]:
        preflight = transport["nativePreflight"]
        print(f"Interfață nativă: {preflight['exitStatus']} {preflight['diagnostic']}; "
              f"motor pentru ambele plăci: {transport['backend']}.", flush=True)
    for issue in transport["issues"]:
        print(issue, file=sys.stderr)
    report = subprocess.run([PYTHON, "-I", "-B", str(HERE / "report.py"), str(directory)])
    print("Raport pe iMac:", directory, flush=True)
    if report.returncode:
        return report.returncode
    if transport["issues"] or any(not records[gpu].get("cases") for gpu in MODES):
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Testul nu a putut porni: {exc}")
