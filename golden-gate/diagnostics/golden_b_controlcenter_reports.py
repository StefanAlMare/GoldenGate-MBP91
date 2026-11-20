"""Read existing Golden B menu and Battery incident reports. No UI activation."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys


NAMES = ("ControlCenter", "ControlCenterHelper", "MenuBarAgent", "SystemUIServer",
         "WindowServer", "PowerPreferences", "System Settings", "MTLCompilerService")
TAG = "GG_INCIDENT"
SWIFTUI_CALLBACK_UUID = "3825DDEC-7201-3B96-8FE9-AB77C58742CF"
SWIFTUI_CALLBACK_RETURN = 0x756FB8  # hao-runtime 256dd30, src/native_callback.c
SWIFTCORE_GOLDEN_UUID = "54F671EE-B22D-3F02-930C-2CC027116E14"


def decode_report(text):
    decoder = json.JSONDecoder()
    first, end = decoder.raw_decode(text.lstrip())
    rest = text.lstrip()[end:].strip()
    return (first, json.loads(rest)) if rest else ({}, first)


def report_time(stamp):
    # Apple IPS timestamps may have four fractional digits and a space before the UTC offset.
    stamp = re.sub(r"\s+(?=[+-]\d\d:?\d\d$)", "", stamp.strip()).replace("T", " ")
    pattern = "%Y-%m-%d %H:%M:%S" + (".%f" if "." in stamp else "") + "%z"
    return datetime.strptime(stamp, pattern)


def stack(frames, images):
    names = []
    for frame in frames[:30]:
        index = frame.get("imageIndex")
        img = images[index] if isinstance(index, int) and 0 <= index < len(images) else {}
        offset = frame.get("imageOffset")
        symbol = frame.get("symbol")
        location = f"+0x{offset:x}" if isinstance(offset, int) else ""
        name = img.get("name") or Path(img.get("path", "?")).name
        names.append(f"{name}{location}" + (f" ({str(symbol)[:135]})" if symbol else ""))
    return " > ".join(names)


def controlcenter_details(pid, thread, data):
    images = data.get("usedImages") or []
    frames = thread.get("frames") or []
    label = f"GG_DETALIU PID={pid}"
    exc = data.get("exception") or {}
    subtype = str(exc.get("subtype") or "").strip() or "nespecificat"
    print(label, "subtip=" + subtype.split()[0], f"cadre={len(frames)}")
    found_core = False
    app_frames = 0
    for index, img in enumerate(images):
        name = img.get("name") or Path(img.get("path") or "?").name
        if name not in ("SwiftUICore", "libswiftCore.dylib", "ControlCenter", "ControlCenterUI", "libhao.dylib"):
            continue
        uuid = str(img.get("uuid") or "?").upper()
        arch = img.get("arch") or "?"
        print(label, name, f"arch={arch} UUID={uuid}")
        matched = [(i, f) for i, f in enumerate(frames) if f.get("imageIndex") == index]
        if name == "libswiftCore.dylib" and uuid == SWIFTCORE_GOLDEN_UUID:
            if any(i == 0 and f.get("imageOffset") == 0x24175c for i, f in matched):
                print(label, "referință Intel 26B131 confirmată la cadrul #0: swift_setAtWritableKeyPath + 28")
        if name == "SwiftUICore":
            found_core = True
            if uuid == SWIFTUI_CALLBACK_UUID:
                # Some IPS frames identify the call by its immediately preceding byte.
                site = [f"#{i}=0x{f['imageOffset']:x}" for i, f in matched
                        if f.get("imageOffset") in (SWIFTUI_CALLBACK_RETURN, SWIFTUI_CALLBACK_RETURN - 1)]
                print(label, "256dd30 UUID=coincide", "retur/retur-1=" + (",".join(site) or "absent din stivă"))
            else:
                print(label, "256dd30 imagine=" + ("neidentificată" if uuid == "?" else "diferită"))
        if name in ("ControlCenter", "ControlCenterUI"):
            app_frames += len(matched)
        for i, f in matched[:3]:
            offset = f.get("imageOffset")
            if isinstance(offset, int):
                position = f.get("symbolLocation")
                symbol = str(f.get("symbol") or "simbol indisponibil")[:180]
                within = f"+0x{position:x}" if isinstance(position, int) else ""
                print(label, f"#{i} {name}+0x{offset:x}", symbol + within)
    if not found_core:
        print(label, "256dd30 imagine=SwiftUICore absentă din inventarul IPS")
    print(label, f"cadre ControlCenter/ControlCenterUI={app_frames}")


def ips_reports(roots, start, end, details=False):
    seen, incidents = set(), []
    for root in roots:
        for folder in (root, root / "Retired"):
            try:
                paths = list(folder.iterdir())
            except FileNotFoundError:
                continue
            except OSError as error:
                print(TAG, "dosar de rapoarte inaccesibil", folder.name, type(error).__name__)
                continue
            for path in paths:
                if path.suffix != ".ips" or not path.name.startswith("ControlCenter" if details else NAMES):
                    continue
                try:
                    if path.stat().st_mtime < start.timestamp() - 10:
                        continue
                    header, data = decode_report(path.read_text(encoding="utf-8"))
                    name = data.get("procName") or header.get("app_name")
                    if name not in NAMES or (details and name != "ControlCenter"):
                        continue
                    stamp = data.get("captureTime") or header.get("timestamp")
                    when = report_time(stamp)
                    pid = int(data["pid"])
                    key = data.get("incident") or header.get("incident_id") or (name, pid, stamp)
                    if key in seen or not start <= when <= end:
                        continue
                    seen.add(key)
                    incidents.append((when, name, pid, path.name, data))
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                    print(TAG, "raport necitit", path.name, type(error).__name__)
    incidents.sort(key=lambda item: item[0], reverse=True)
    printed, counts = set(), {}
    for when, name, pid, filename, data in incidents:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 3:
            continue
        printed.add((name, pid))
        exc = data.get("exception") or {}
        term = data.get("termination") or {}
        print(TAG, when.isoformat(timespec="seconds"), name, f"PID={pid}", filename,
              exc.get("type", ""), exc.get("signal", ""), term.get("namespace", ""), term.get("code", ""))
        threads = data.get("threads") or []
        index = data.get("faultingThread")
        thread = (threads[index] if isinstance(index, int) and 0 <= index < len(threads)
                  else next((t for t in threads if t.get("triggered")), {}))
        if details:
            controlcenter_details(pid, thread, data)
            continue
        images = data.get("usedImages") or []
        for label, frames in (("stivă", thread.get("frames")), ("excepție ObjC", data.get("lastExceptionBacktrace"))):
            if frames:
                print(TAG, label, stack(frames, images))
    print(TAG, "rapoarte IPS distincte în interval:", len(incidents), counts or "")
    return printed


def hao_offsets(directory, incidents):
    if not incidents:
        return
    found = set()
    for path in (directory / "console.log.0", directory / "console.log"):
        try:
            with path.open("rb") as stream:
                # Only inspect the tail of each runtime log and report image-relative locations.
                size = os.fstat(stream.fileno()).st_size
                if size > 8 * 1024 * 1024:
                    stream.seek(-8 * 1024 * 1024, 2)
                    stream.readline()
                for line in stream:
                    match = re.match(rb"hao\[([^]:]+):(\d+)\]:[^\n]*(?:guest brk|guest fault|unsupported insn)", line, re.I)
                    if not match:
                        continue
                    who = (match[1].decode(errors="replace"), int(match[2]))
                    if who not in incidents:
                        continue
                    sites = re.findall(rb"\(([\w.$ -]+\+0x[0-9a-fA-F]+)(?:,|\))", line)
                    if sites:
                        found.add((who, " > ".join(s.decode("ascii") for s in sites[:4])))
        except FileNotFoundError:
            continue
        except OSError as error:
            print(TAG, "jurnal HAO inaccesibil", path.name, type(error).__name__)
    for (name, pid), sites in sorted(found):
        print(TAG, "HAO același nume/PID", name, pid, sites)


def lifecycle(start, end):
    targets = " OR ".join(f'eventMessage CONTAINS[c] "{name}"' for name in NAMES)
    terms = ("exited", "termination reported", "crashed", "spawned", "saved crash report")
    events = " OR ".join(f'eventMessage CONTAINS[c] "{term}"' for term in terms)
    predicate = f'process IN {{"launchd","runningboardd","ReportCrash"}} AND ({targets}) AND ({events})'
    cmd = ["/usr/bin/log", "show", "--style", "ndjson", "--info", "--predicate", predicate,
           "--start", start.strftime("%Y-%m-%d %H:%M:%S%z"), "--end", end.strftime("%Y-%m-%d %H:%M:%S%z")]
    try:
        run = subprocess.run(cmd, capture_output=True, timeout=40, check=True)
        messages = []
        for line in run.stdout.splitlines():
            if not line.lstrip().startswith(b"{"):
                continue
            row = json.loads(line)
            msg = " ".join((row.get("eventMessage") or "").split())
            if msg and any(x in msg.lower() for x in terms) and any(n.lower() in msg.lower() for n in NAMES):
                msg = re.sub(r"/Users/[^/\s]+", "/Users/…", msg)
                messages.append(f"{row.get('timestamp', '')} | {msg[:320]}")
        print(TAG, "evenimente în jurnal:", len(messages), "(ultimele 30)")
        for msg in messages[-30:]:
            print(TAG, msg)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(TAG, "citire incompletă a jurnalului de procese:", type(error).__name__)


def current_processes():
    try:
        run = subprocess.run(["/bin/ps", "-axo", "pid=,lstart=,comm="], capture_output=True, text=True,
                             env={**os.environ, "LC_ALL": "C"}, check=True, timeout=10)
        for line in run.stdout.splitlines():
            fields = line.split(None, 6)
            if len(fields) == 7 and Path(fields[6]).name in NAMES:
                print(TAG, "activ acum", Path(fields[6]).name, f"PID={fields[0]}", "pornit", " ".join(fields[1:6]))
    except (OSError, subprocess.SubprocessError) as error:
        print(TAG, "lista proceselor inaccesibilă:", type(error).__name__)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    start = datetime.fromisoformat(sys.argv[1])
    details = sys.argv[2:] == ["--detalii-centru-control"]
    duration = timedelta(minutes=2) if details else timedelta(hours=2)
    end = min(datetime.now().astimezone(), start + duration)
    if start > end:
        sys.exit("Începutul intervalului este în viitor pe Golden B.")
    print(TAG, "interval", start.isoformat(timespec="seconds"), "–", end.isoformat(timespec="seconds"))
    roots = [Path.home() / "Library/Logs/DiagnosticReports", Path("/Library/Logs/DiagnosticReports")]
    if details:
        if not ips_reports(roots, start, end, details=True):
            sys.exit("Niciun incident ControlCenter lizibil în cele două minute selectate.")
        return
    current_processes()
    incidents = ips_reports(roots, start, end)
    hao_offsets(Path("/private/var/log/hao/user") / str(os.getuid()), incidents)
    lifecycle(start, end)


if __name__ == "__main__":
    main()
