"""Reproduce the SkyLight interface unit tested on MacBookPro9,1, Golden 26B131."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


GOLDEN_SKYLIGHT_UUID = "21acabfab6cc3ec9a3cf6d4d6b637f5a"
UNIT_SHA256 = "a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f"
WINDOW_UNIT_SHA256 = "cd2a77b0e61af60abd4c23e860809aad0af4837dc81886a600831379c2546b3f"
RUNTIME_TOOLS = Path(os.environ.get("GOLDEN_GATE_RUNTIME_TOOLS", Path(__file__).parent / "outils-runtime-locaux"))
TOOL_DIGESTS = {
    "hao_ifunit.py": "895f5cf111d643ee7420ebb38751f86c3726ff647c566f42be3261f225f72499",
    "hao_fat.py": "e2cec7bf465549ad8a8e8afa4a23f4b71f0359dfeb2fe18ee4396c0d40299d41",
}


def build_unit(tools=RUNTIME_TOOLS, *, include_option=False):
    """Return the Dock unit, or its superset for testing WindowManager."""
    tools = Path(tools)
    for name, expected in TOOL_DIGESTS.items():
        if hashlib.sha256((tools / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Generatorul diferă de versiunea verificată: {name}")

    # CoreGraphics re-exports CGSInputButtonState, whose implementation in
    # SkyLight also exports SLSInputButtonState at the same address.
    # Record C zero-extends the unsigned byte returned in AL for both names.
    aliases = ("_CGSInputButtonState", "_SLSInputButtonState")
    if include_option:
        # WindowManager 26B131 calls (0, 3) and compares W0 at 0x10016bcec.
        # The Tahoe Intel implementation writes AL for that modifier key.
        aliases += ("_CGSInputModifierKeyState", "_SLSInputModifierKeyState")
    records = "".join(f"{name}\tTYPED\tC\t-\t-\t-\t-\n" for name in aliases)
    command = [sys.executable, "-I", "-B", str(tools / "hao_ifunit.py")]
    with tempfile.TemporaryDirectory(prefix="golden-skylight-") as tmp:
        unit = Path(tmp) / GOLDEN_SKYLIGHT_UUID
        subprocess.run(command + ["write", str(unit), "--uuid", GOLDEN_SKYLIGHT_UUID],
                       input=records.encode("ascii"), check=True)
        subprocess.run(command + ["check", str(unit), "--uuid", GOLDEN_SKYLIGHT_UUID],
                       stdout=subprocess.PIPE, check=True)
        decoded = subprocess.check_output(command + ["dump", str(unit)]).decode("ascii")
        if sorted(decoded.splitlines()[1:]) != sorted(records.splitlines()):
            raise ValueError("Înregistrările unității SkyLight diferă.")
        data = unit.read_bytes()
    if hashlib.sha256(data).hexdigest() != (WINDOW_UNIT_SHA256 if include_option else UNIT_SHA256):
        raise ValueError("Unitatea generată diferă de exemplarul de referință.")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=RUNTIME_TOOLS,
                        help="Directorul tools al surselor hao-runtime 1547dcb.")
    parser.add_argument("--include-option", action="store_true",
                        help="Include și cele două nume ale apelului WindowManager pentru tasta Opțiune.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", type=Path, help="Compară cu un fișier existent.")
    group.add_argument("--output-dir", type=Path, help="Creează fișierul în directorul ales.")
    args = parser.parse_args()
    result = build_unit(args.tools, include_option=args.include_option)
    if args.check and args.check.read_bytes() != result:
        parser.exit(1, "Fișierul verificat diferă.\n")
    if args.output_dir:
        output = args.output_dir / GOLDEN_SKYLIGHT_UUID
        with output.open("xb") as stream:
            stream.write(result)
    print(f"{hashlib.sha256(result).hexdigest()}  {GOLDEN_SKYLIGHT_UUID}")
