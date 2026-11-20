"""Compare the original and pre-transformed fetch0 shaders on an explicit GT 650M."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
base = runpy.run_path(str(HERE / "run-test.py"))
report = runpy.run_path(str(HERE / "report.py"))
MODES = {"texture-control": "Control prin textură", "framebuffer-read": "fetch0 original",
         "lowered-fetch0": "fetch0 adaptat"}
MASK_HASH = "3728ce0a2f2a27ed56456a6473b2eabe3f251a571e8eb4a25bc9138bd4e8bced"
PINS = {"probe.metallib": base["SHADER_SHA"], "metal-python.tar.gz": base["RUNTIME_SHA"],
        "lowered-single.metallib": "a993e3c2691da18b8da9460a61a16a59f3b19c86fc726c69dc9a4a33b07f1b2f",
        "lowered-single.bindings.json": "0857d5115fdf65fb4914e19603a0a782c574a81ed8b5b1098a5a868562dd16a4"}
REMOTE = r"""
set -eu -o pipefail
umask 077
export LC_ALL=C
model=$(/usr/sbin/sysctl -n hw.model)
build=$(/usr/bin/sw_vers -buildVersion)
printf 'TARGET\t%s\t%s\n' "$model" "$build"
[[ "$model" == MacBookPro9,1 && "$build" == 26B131 ]] || { echo 'Ținta diferă de MacBookPro9,1 Golden 26B131.' >&2; exit 2; }
folder=$(/usr/bin/mktemp -d /private/tmp/GoldenGate-Kepler-Fetch.XXXXXXXX)
trap '/bin/rm -rf "$folder"' EXIT
trap 'exit 130' HUP INT TERM
cd "$folder"
/usr/bin/tar -xzf -
/usr/bin/shasum -a 256 -c manifest.sha256 >&2
/usr/bin/tar -xzf metal-python.tar.gz
python="$folder/metal-python/bin/python3.12"
limit() { /usr/bin/perl -e 'alarm shift; exec {$ARGV[0]} @ARGV or die "exec: $!"' "$@"; }
field64() { /usr/bin/head -c "$2" "$1" | /usr/bin/base64 | /usr/bin/tr -d '\r\n'; }
status=0
limit 25 "$python" -I -S -B lowered-metal.py --bridge-test >bridge.log 2>&1 || status=$?
printf 'BRIDGE\t%s\t' "$status"
field64 bridge.log 3500
printf '\n'
[[ "$status" == 0 ]] || exit 2
for mode in texture-control framebuffer-read lowered-fetch0; do
    echo "GT 650M · $mode" >&2
    status=0
    limit 85 "$python" -I -S -B lowered-metal.py "$mode" >result.json 2>error.log || status=$?
    printf 'CASE\t%s\t%s\t' "$mode" "$status"
    field64 result.json 18000
    printf '\t'
    field64 error.log 2000
    printf '\n'
done
echo DONE
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(check):
    files = {name: (HERE / name).read_bytes() for name in (*PINS, "native-metal.py", "lowered-metal.py")}
    for name, expected in PINS.items():
        if digest(files[name]) != expected:
            raise ValueError("SHA-256 diferă pentru " + name)
    mask = base["reference_mask"]()
    if digest("".join(mask["rows"]).encode("ascii")) != MASK_HASH:
        raise ValueError("Conturul Wi-Fi generat diferă de cele două probe de referință.")
    if check:
        base["check_runtime_locally"](files["metal-python.tar.gz"])
        subprocess.run(["/bin/bash", "-n"], input=REMOTE.encode(), check=True)
    files["wifi-mask.json"] = json.dumps(mask).encode()
    files["manifest.sha256"] = "".join(f"{digest(data)}  {name}\n" for name, data in files.items()).encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", compresslevel=1) as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o600, len(data)
            archive.addfile(info, io.BytesIO(data))
    return mask, stream.getvalue()


def collect(raw, ssh_status):
    target, bridge, cases, errors, finished = None, None, {}, [], False
    for line in raw.decode("utf-8", "replace").splitlines():
        fields = line.split("\t")
        try:
            if fields[0] == "TARGET" and target is None and len(fields) == 3:
                target = fields[1:]
            elif fields[0] == "BRIDGE" and bridge is None and len(fields) == 3:
                diagnostic = base64.b64decode(fields[2], validate=True).decode("utf-8", "replace")
                bridge = {"status": int(fields[1]), "output": diagnostic}
                if bridge["status"] == 0:
                    info = json.loads(diagnostic)
                    if not isinstance(info, dict) or info.get("status") != "PASS" or info.get("processArchitecture") != "x86_64":
                        errors.append("Verificarea interfeței x86_64 este incompletă.")
            elif fields[0] == "CASE" and len(fields) == 5 and fields[1] in MODES and fields[1] not in cases:
                cases[fields[1]] = base["decode_case"]("nvidia", int(fields[2]), fields[3], fields[4])
            elif line == "DONE" and not finished:
                finished = True
            else:
                errors.append("Înregistrare necunoscută sau duplicată în sesiune.")
        except (ValueError, TypeError):
            errors.append("Înregistrare invalidă pentru " + fields[0][:20])
    if target != ["MacBookPro9,1", "26B131"]:
        errors.append("Identitatea țintei diferă sau lipsește.")
    if bridge is None or bridge.get("status") != 0:
        reason = (bridge or {}).get("output", "").strip()
        errors.append("Verificarea interfeței x86_64 a eșuat. " + reason[:400])
    if not finished or ssh_status:
        errors.append(f"Sesiune neterminată sau eroare SSH (status {ssh_status}).")
    return {"target": target, "preflight": bridge, "sshStatus": ssh_status, "finished": finished,
            "issues": errors, "cases": cases}


def verified(mode, record, bits):
    error = report["inconclusive"]
    record = record if isinstance(record, dict) else {}
    cases = record.get("cases")
    if not isinstance(cases, list) or len(cases) != 1 or not isinstance(cases[0], dict):
        return None, error(record.get("reason", "Lipsește proba."))
    case = cases[0]
    identity = report["registry_id"](record.get("registryID"))
    if (record.get("event") != "gpu-render" or record.get("key") != "nvidia" or not identity or
            record.get("name") != report["GPU_NAMES"]["nvidia"] or case.get("mode") != mode):
        return None, error(case.get("reason") or "Identitatea GPU sau a probei este neconfirmată.")
    if (record.get("width"), record.get("height"), record.get("selectedPixels"), record.get("pixelFormat")) != (
            32, 32, sum(bits), "RGBA8Unorm"):
        return identity, error("Formatul sau masca de pixeli diferă.")
    value = report["check_case"](case, bits)
    if mode == "lowered-fetch0" and value["status"] in ("PASS", "MISMATCH"):
        slot = case.get("reflectedTextureIndex")
        if (type(slot) is not int or not 0 <= slot < 128 or case.get("declaredTextureIndex") != 127
                or case.get("reflectedTextureName") != "__fbcompat_fb_attachment_0"
                or case.get("reflectedTextureType") not in ("texture", 2)
                or case.get("distinctTextures") is not True or case.get("destinationSentinel") != 205):
            return identity, error("Legarea texturii declarate sau inițializarea distinctă a destinației nu s-a confirmat.")
        value["actualSlot"] = slot
    if value.get("pipeline_error"):
        value["status"] = "RESPINS LA CREAREA PIPELINE-ULUI"
        value["airRejection"] = (case.get("nativeDomain") == "CompilerError" and case.get("nativeCode") == 2
                                 and "air.render_target" in str(case.get("reason")))
    return identity, value


def summarize(session, mask):
    bits = report["mask_bits"](mask)
    results = {mode: verified(mode, session["cases"].get(mode), bits) for mode in MODES}
    ids = [identity for identity, _ in results.values()]
    same_gpu = bool(ids[0] and all(i == ids[0] for i in ids))
    lines = ["NVIDIA GeForce GT 650M · ID " + (hex(ids[0]) if same_gpu else "neconfirmat pentru toate probele")]
    for mode, (identity, result) in results.items():
        if "inside" in result:
            inside, outside = result["inside"], result["outside"]
            detail = (f"{inside+outside}/1024 pixeli · simbol {inside}/{sum(bits)} · fundal {outside}/{1024-sum(bits)}"
                      f" · eroare maximă {result['max_error']}/255")
            if mode == "lowered-fetch0":
                detail += f" · textură distinctă, index declarat 127, index raportat de Metal {result['actualSlot']}"
        else:
            detail = result["reason"]
        lines.append(f"  {MODES[mode]} · {result['status']} · {detail}")
    control = results["texture-control"][1]["status"]
    direct = results["framebuffer-read"][1]
    lowered = results["lowered-fetch0"][1]["status"]
    errors = session["issues"]
    code = 2
    if errors or not same_gpu or control != "PASS":
        verdict = "Comparație incompletă. Sunt necesare o sesiune validă, același GPU confirmat și un control corect."
    elif not direct.get("airRejection"):
        verdict = "În această sesiune lipsește reproducerea refuzului inițial pentru air.render_target."
    elif lowered == "PASS":
        verdict = ("GT 650M a refuzat fetch0 original și a desenat corect forma Wi-Fi cu fetch0 adaptat, "
                   "citind o copie separată a culorilor inițiale. Integrarea în Finder rămâne de verificat.")
        code = 0
    elif lowered == "MISMATCH":
        verdict = "Varianta adaptată a rulat, dar pixelii întorși diferă de referință."
        code = 1
    elif lowered == "RESPINS LA CREAREA PIPELINE-ULUI":
        verdict = "Driverul a refuzat și pipeline-ul adaptat. Detaliile Metal sunt păstrate pentru ambele variante."
        code = 1
    else:
        verdict = "Refuzul inițial s-a reprodus. Varianta adaptată nu a furnizat o măsurătoare verificabilă."
    return "\n".join([*lines, "", *errors, verdict]), code


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    check = args == ["--check"]
    target = None if check else base["target_arg"](args)
    mask, archive = prepare(check)
    if check:
        print("Pregătit. Biblioteci Metal și manifest verificate. Contur identic cu ambele rulări fizice.")
        return 0
    directory = Path(tempfile.mkdtemp(prefix="GoldenGate-Kepler-Fetch-", dir=HERE.parent))
    print("Raport pe iMac:", directory, flush=True)
    command = shlex.join(("/bin/bash", "-c", REMOTE))
    try:
        run = subprocess.run(base["SSH"] + [target, command], input=archive, stdout=subprocess.PIPE, timeout=340)
        session = collect(run.stdout, run.returncode)
    except subprocess.TimeoutExpired as exc:
        session = collect(exc.stdout or b"", 124)
    except OSError as exc:
        session = collect(b"", 255)
        session["issues"].append(str(exc))
    session.update(inputsSHA256=PINS, maskRowsSHA256=MASK_HASH, mask=mask)
    base["write_json"](directory / "rezultat.json", session)
    summary, code = summarize(session, mask)
    (directory / "raport.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary, flush=True)
    print("Raport pe iMac:", directory, flush=True)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Testul nu a putut porni: {exc}")
