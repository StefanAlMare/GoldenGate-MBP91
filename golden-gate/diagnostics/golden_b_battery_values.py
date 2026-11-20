"""Summarize one Battery pane query and the separate PowerLog debug plist on B."""
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from xml.parsers.expat import ExpatError


CACHE = Path("/private/var/db/powerlog/Library/BatteryLife/Debug/BatteryUI.plist")
LEVEL = "UISOCLevel_24hr_900"
SCREEN = "UsageTimes_24hr_3600"
SCREEN_DAYS = "UsageTimes_10d_86400"
ENERGY_DAYS = "UISOCDrain_10d_86400"
COUNT_FORMATS = {"got %lu UISoC levels": LEVEL, "Got %lu screen on times": SCREEN}
KEYS = {LEVEL, SCREEN, SCREEN_DAYS, ENERGY_DAYS, "endOfHour", "endOfDay",
        "PLBatteryUIQueryTime", "PLBatteryUIXPCVersionKey", "skipPlistWriteKey"}


def summarize(key, records):
    if not isinstance(records, list):
        return "serie indisponibilă"
    values = records
    if key == LEVEL:
        values = [pair[0] if isinstance(pair, list) and len(pair) == 2 else None for pair in records]
    elif key == ENERGY_DAYS:
        values = [row.get("PLBatteryUIEnergyKey") if isinstance(row, dict) else None for row in records]
    nums = [x for x in values if type(x) in (float, int) and math.isfinite(x)]
    usable = [x for x in nums if x >= 0]
    positive = sum(x > 0 for x in usable)
    parts = [f"intervale={len(records)}", f"negative={len(nums)-len(usable)}",
             f"zero={len(usable)-positive}", f"pozitive={positive}",
             f"ilizibile={len(records)-len(nums)}"]
    if usable:
        unit = "%" if key == LEVEL else " s" if key in (SCREEN, SCREEN_DAYS) else ""
        parts.append(f"min..max nenegative={min(usable):g}..{max(usable):g}{unit}")
    return " | ".join(parts)


def date_text(seconds):
    try:
        return datetime.fromtimestamp(seconds).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, TypeError, ValueError):
        return "indisponibil"


def cached_series(path):
    try:
        with path.open("rb") as stream:
            modified = os.fstat(stream.fileno()).st_mtime
            data = plistlib.load(stream)
        if not isinstance(data, dict):
            raise ValueError("root")
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as error:
        print(f"GG_VALORI fișier PowerLog indisponibil ({type(error).__name__}).")
        return False
    print("GG_VALORI fișier PowerLog | modificat=" + date_text(modified))
    for key in ("endOfHour", "endOfDay"):
        print(f"GG_VALORI fișier | {key}=" + date_text(data.get(key)))
    for key in (LEVEL, SCREEN, SCREEN_DAYS, ENERGY_DAYS):
        records = data.get(key)
        if key in (SCREEN, SCREEN_DAYS):
            records = records.get("PLBatteryUIGraphByBucket") if isinstance(records, dict) else None
        print(f"GG_VALORI fișier | {key} | {summarize(key, records)}")
    return True


def logged_array(message):
    # NSArray descriptions use parentheses, JSON uses brackets. Only accept
    # numeric arrays here and verify the count declared by the same thread.
    if not re.fullmatch(r'[0-9eE+.,\-()\[\]"\s]+', message):
        return None
    text = message.replace("(", "[").replace(")", "]")
    text = re.sub(r'"(-?\d+(?:\.\d+)?)"', r'\1', text)
    try:
        parsed = json.loads(re.sub(r",\s*]", "]", text))
    except ValueError:
        return None
    return parsed if isinstance(parsed, list) else None


def query_events(rows, pid):
    pending = {}
    counted, described = set(), set()
    for row in rows:
        if row.get("processID") != pid:
            continue
        msg = (row.get("eventMessage") or "").strip()
        fmt = row.get("formatString")
        thread = row.get("threadID")
        prior = pending.pop(thread, None)
        if fmt in COUNT_FORMATS or re.fullmatch(r"got \d+ (UISoC levels|screen on times)", msg, re.I):
            count = re.fullmatch(r"got (\d+) (UISoC levels|screen on times)", msg, re.I)
            if count:
                key = LEVEL if count[2].lower() == "uisoc levels" else SCREEN
                counted.add(key)
                if thread is not None:
                    pending[thread] = (key, int(count[1]))
                print(f"GG_VALORI jurnal | {key} | contor={count[1]}")
        elif fmt == " %@" and prior:
            key, count = prior
            data = logged_array(msg)
            if "<private>" in msg:
                summary = "valori mascate de sistem"
            elif data is None or len(data) != count:
                summary = "seria completă nu poate fi citită"
            else:
                summary = summarize(key, data)
            described.add(key)
            print(f"GG_VALORI jurnal | {key} | {summary}")
        elif msg.startswith("Couldn't find response key in query:"):
            key = msg.partition(":")[2].strip()
            label = key if key in KEYS else "mascată" if key == "<private>" else "neidentificată"
            print(f"GG_VALORI jurnal | cheie din răspuns fără configurație în cerere | {label}")
        elif fmt in ("setting end of day:%f", "setting end of hour:%f"):
            try:
                endpoint = float(msg.rsplit(":", 1)[-1])
            except ValueError:
                continue
            print(f"GG_VALORI jurnal | {fmt.split(':')[0]}=" + date_text(endpoint))
    for key in sorted(counted - described):
        print(f"GG_VALORI jurnal | {key} | detaliile seriei nu au fost identificate.")
    if not counted:
        print("GG_VALORI jurnal | contoarele acestei cereri sunt indisponibile.")


def archived_query(when, pid):
    stamp = "%Y-%m-%d %H:%M:%S%z"
    cmd = ["/usr/bin/log", "show", "--style", "ndjson", "--info", "--debug", "--process", str(pid),
           "--start", (when - timedelta(seconds=1)).strftime(stamp),
           "--end", (when + timedelta(seconds=2)).strftime(stamp),
           "--predicate", 'subsystem == "com.apple.batteryui" OR process == "PowerPreferences"']
    print(f"GG_VALORI jurnal | referință={when.isoformat()} | PID={pid}")
    try:
        run = subprocess.run(cmd, capture_output=True, check=True, timeout=35)
        query_events((json.loads(line) for line in run.stdout.splitlines() if line.lstrip().startswith(b"{")), pid)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"GG_VALORI jurnal indisponibil ({type(error).__name__}).")
        return False
    return True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    anchor = datetime.fromisoformat(sys.argv[1])
    history = archived_query(anchor, int(sys.argv[2]))
    cache = cached_series(CACHE)
    sys.exit(0 if history or cache else 3)
