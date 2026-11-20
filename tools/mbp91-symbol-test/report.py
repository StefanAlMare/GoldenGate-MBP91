"""Verify GPU readbacks independently and write a private, offline visual report."""
import base64
import binascii
from html import escape
import json
from pathlib import Path
import re
import struct
import sys
import zlib

SIZE = 32
PIXELS = SIZE * SIZE
MODE_NAMES = {"texture-control": "Citire din textură", "framebuffer-read": "Citire din framebuffer"}
GPU_NAMES = {"intel": "Intel HD Graphics 4000", "nvidia": "NVIDIA GeForce GT 650M"}
INCOMPLETE = "NECONCLUDENT"
DARK = (24, 37, 53)
LIGHT = (244, 249, 252)
UNEXPECTED = (237, 71, 155)


def registry_id(value):
    """Accept unambiguous uint64 values in decimal or prefixed hexadecimal."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    token = str(value).strip()
    if not re.fullmatch(r"(?:0[xX][0-9a-fA-F]{1,16}|[0-9]{1,20})", token):
        return None
    number = int(token, 16 if token.lower().startswith("0x") else 10)
    return number if 0 < number < 1 << 64 else None


def mask_bits(mask):
    rows = mask.get("rows") if isinstance(mask, dict) else None
    if (not isinstance(rows, list) or len(rows) != SIZE or mask.get("size") != SIZE or
            mask.get("symbol") != "wifi" or any(not isinstance(r, str) or not re.fullmatch(r"[01]{32}", r) for r in rows)):
        raise ValueError("Masca Wi-Fi are un format neașteptat.")
    bits = [bit == "1" for row in rows for bit in row]
    if not 16 <= sum(bits) <= PIXELS - 16 or mask.get("selectedPixels") != sum(bits):
        raise ValueError("Suprafața simbolului nu corespunde măștii primite.")
    return bits


def seed_channel(channel, x, y):
    # round(255*((c+1)/8 + ((x+3*y)%4)/32)) with a half rounded up
    return (255 * (4 * (channel + 1) + (x + 3*y) % 4) + 16) // 32


def inconclusive(reason):
    return {"status": INCOMPLETE, "reason": str(reason).replace("\n", " ")[:300]}


def check_case(case, bits):
    if case.get("status") not in ("PASS", "MISMATCH"):
        result = inconclusive(case.get("reason", "Lipsește rezultatul operației Metal."))
        domain, code = case.get("nativeDomain"), case.get("nativeCode")
        if case.get("pipeline") == "fetch0" and isinstance(domain, str) and domain and type(code) is int:
            result["pipeline_error"] = True
            result["reason"] += f" ({domain}, cod {code})"
        return result
    encoded = case.get("rgbaBase64")
    if not isinstance(encoded, str) or len(encoded) != 4 * ((PIXELS * 4 + 2) // 3):
        return inconclusive("Citirea RGBA8 de 32 × 32 pixeli este incompletă.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return inconclusive("Formatul citirii RGBA8 este invalid.")
    if len(raw) != PIXELS * 4:
        return inconclusive("Dimensiunea citirii RGBA8 este invalidă.")
    shape = bytearray()
    inside = outside = largest_error = 0
    for i, selected in enumerate(bits):
        pixel = raw[4*i:4*i+4]
        seed = [seed_channel(c, i % SIZE, i // SIZE) for c in range(4)]
        # One fragment adds 1/16 in units of 255, which rounds to 16 bytes.
        idle_error = max(abs(actual - before) for actual, before in zip(pixel, seed))
        drawn_error = max(abs(actual - before - 16) for actual, before in zip(pixel, seed))
        distance = drawn_error if selected else idle_error
        largest_error = max(largest_error, distance)
        if distance <= 1:
            if selected:
                inside += 1
            else:
                outside += 1
        shape.extend(LIGHT if drawn_error <= 1 else DARK if idle_error <= 1 else UNEXPECTED)
    local_status = "PASS" if inside + outside == PIXELS else "MISMATCH"
    expected = {"status": local_status, "matched": inside + outside, "pixels": PIXELS,
                "matchedInside": inside, "matchedOutside": outside, "maxChannelError": largest_error}
    if any(case.get(k) != value for k, value in expected.items()):
        return inconclusive("Verdictul utilitarului și verificarea independentă a pixelilor diferă.")
    return {"status": local_status, "inside": inside, "outside": outside, "max_error": largest_error,
            "raw_rgb": bytes(raw[n] for n in range(len(raw)) if n % 4 != 3), "shape": bytes(shape)}


def evaluate(key, record, bits):
    record = record if isinstance(record, dict) else {}
    cases = record.get("cases")
    entries = [c for c in cases if isinstance(c, dict)] if isinstance(cases, list) else []
    error = record.get("reason") or next((c.get("reason") for c in entries if c.get("reason")), "")
    name = record.get("name")
    identity = registry_id(record.get("registryID"))
    valid = (record.get("event") == "gpu-render" and record.get("key") == key and identity
             and isinstance(name, str) and GPU_NAMES[key].casefold() in name.casefold())
    if not valid:
        reason = error or "Identitatea plăcii nu a fost confirmată."
        return None, {mode: inconclusive(reason) for mode in MODE_NAMES}
    if (record.get("width"), record.get("height"), record.get("selectedPixels")) != (SIZE, SIZE, sum(bits)):
        return identity, {mode: inconclusive("Dimensiunea suprafeței sau aria simbolului diferă.") for mode in MODE_NAMES}
    results = {}
    for mode in MODE_NAMES:
        matches = [c for c in entries if c.get("mode") == mode]
        results[mode] = check_case(matches[0], bits) if len(matches) == 1 else inconclusive("Probă absentă sau duplicată.")
    return identity, results


def interpretation(devices):
    a, b = devices["intel"], devices["nvidia"]
    if not a[0] or not b[0] or a[0] == b[0]:
        return "Comparație neconcludentă. Sunt necesare două plăci confirmate cu ID-uri distincte."
    def statuses(mode):
        return [a[1][mode]["status"], b[1][mode]["status"]]
    if statuses("texture-control") != ["PASS", "PASS"]:
        return "Comparație neconcludentă pentru citirea din framebuffer. Proba de control trebuie să treacă pe ambele plăci."
    fetch = statuses("framebuffer-read")
    if INCOMPLETE in fetch:
        for i, key in enumerate(GPU_NAMES):
            if fetch[1-i] == "PASS" and devices[key][1]["framebuffer-read"].get("pipeline_error"):
                return (f"Ambele controale au trecut. Pe {GPU_NAMES[key]}, Metal a returnat o eroare la "
                        "crearea pipeline-ului fetch0. Proba a trecut pe cealaltă placă. "
                        "Diferența apare înainte de desenarea pixelilor.")
        return "Comparație neconcludentă. Ambele controale au trecut, dar lipsește cel puțin o citire validă din framebuffer."
    if fetch == ["PASS", "MISMATCH"]:
        return "Intel a desenat corect simbolul prin citirea din framebuffer. GT 650M a returnat pixeli diferiți de referință la aceeași operație, deși controlul său a trecut. Rezultatul susține investigarea driverului Kepler pentru acest efect."
    if fetch == ["MISMATCH", "PASS"]:
        return "GT 650M a desenat corect simbolul prin citirea din framebuffer. Pe Intel au apărut diferențe de pixeli la această operație; ambele controale au trecut."
    if fetch == ["MISMATCH", "MISMATCH"]:
        return "Ambele plăci au trecut controlul și au returnat pixeli diferiți de referință la citirea din framebuffer."
    return "Ambele plăci au desenat corect simbolul prin ambele metode în condițiile acestui test."


def image_uri(rgb):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    stride = SIZE * 3
    scanlines = b"".join(b"\0" + rgb[start:start+stride] for start in range(0, len(rgb), stride))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def picture(rgb, label):
    return '<figure><img width="96" height="96" src="{}" alt="{}"><figcaption>{}</figcaption></figure>'.format(
        image_uri(rgb), escape(label, quote=True), escape(label))


def generate_report(directory, mask, devices):
    directory = Path(directory)
    bits = mask_bits(mask)
    results = {key: evaluate(key, devices.get(key), bits) for key in GPU_NAMES}
    if results["intel"][0] and results["intel"][0] == results["nvidia"][0]:
        for key in results:
            results[key] = results[key][0], {m: inconclusive("Ambele înregistrări au același ID de placă.") for m in MODE_NAMES}
    verdict = interpretation(results)
    lines = []
    table = []
    for key, name in GPU_NAMES.items():
        ident, modes = results[key]
        handle = hex(ident) if ident else "neconfirmat"
        lines.append(f"{name} · ID {handle}")
        cells = [f"<th scope='row'>{name}<br><small>{handle}</small></th>"]
        for mode, label in MODE_NAMES.items():
            c = modes[mode]
            if c["status"] == INCOMPLETE:
                detail = c["reason"]
                graphs = ""
            else:
                detail = (f"{c['inside'] + c['outside']}/{PIXELS} pixeli corecți · simbol {c['inside']}/{sum(bits)}"
                          f" · fundal {c['outside']}/{PIXELS-sum(bits)} · eroare maximă {c['max_error']}/255")
                graphs = "<div>" + picture(c["raw_rgb"], "RGB citit") + picture(c["shape"], "Operație detectată") + "</div>"
            lines.append(f"  {label} · {c['status']} · {detail}")
            cells.append(f"<td><b>{c['status']}</b><p>{escape(detail)}</p>{graphs}</td>")
        table.append("<tr>" + "".join(cells) + "</tr>")
    lines.extend(["", verdict])
    summary = "\n".join(lines)
    (directory / "raport.txt").write_text(summary + "\n", encoding="utf-8")
    mask_rgb = b"".join(bytes(LIGHT if v else DARK) for v in bits)
    title = "Randarea simbolului Wi-Fi pe HD 4000 și GT 650M"
    head = "".join(f"<th scope='col'>{v}</th>" for v in ("GPU", *MODE_NAMES.values()))
    html = f"""<!DOCTYPE html><html lang="ro"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{max-width:55rem;margin:2rem auto;padding:0 1rem;color:#192331;font:1rem/1.45 system-ui}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;vertical-align:top;padding:.8rem;border:1px solid #c9d0d5}}th{{background:#f0f3f5}}
td div{{display:flex;flex-wrap:wrap;gap:.5rem}}figure{{display:inline-block;margin:0}}img{{display:block;image-rendering:pixelated}}
figcaption,small{{font-size:.78rem;color:#4a5861}}p{{margin:.5rem 0 1rem}}@media(max-width:650px){{th,td{{padding:.35rem}}img{{width:64px;height:64px}}}}</style>
<h1>{title}</h1><p>{escape(verdict)}</p>
{picture(mask_rgb, "Masca de referință")}
<p>Masca provine din AppKit pe iMac, build {escape(str(mask.get('systemBuild', 'necunoscut')))}.
Cele {sum(bits)} de poziții din simbol sunt desenate pe fiecare GPU. Comparația include toți cei patru canali RGBA, cu toleranță de o unitate pe canal.</p>
<table><thead><tr>{head}</tr></thead><tbody>{''.join(table)}</tbody></table>
<p>În «RGB citit» se văd culorile returnate de GPU. În «Operație detectată» contrastul este amplificat:
alb pentru pixeli cu modificarea așteptată a culorii, albastru închis pentru pixeli care păstrează fundalul inițial și roz pentru alte valori.</p>
<p>Proba folosește shaderele de control și de citire din framebuffer pentru a desena conturul Wi-Fi.
Afișarea simbolului în Control Center și refuzurile de conexiune din Finder se verifică separat.</p></html>"""
    (directory / "comparatie.html").write_text(html, encoding="utf-8")
    statuses = [item["status"] for _, modes in results.values() for item in modes.values()]
    exit_code = 2 if INCOMPLETE in statuses else 1 if "MISMATCH" in statuses else 0
    return summary, exit_code


def write_report(directory, mask, devices):
    return generate_report(directory, mask, devices)[0]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Utilizare: report.py DIRECTOR_RAPORT")
    path = Path(sys.argv[1])
    mask = json.loads((path / "wifi-mask.json").read_text(encoding="utf-8"))
    records = {}
    for gpu in GPU_NAMES:
        try:
            records[gpu] = json.loads((path / (gpu + ".json")).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            records[gpu] = {"reason": str(error)}
    summary, exit_code = generate_report(path, mask, records)
    print(summary)
    sys.exit(exit_code)
