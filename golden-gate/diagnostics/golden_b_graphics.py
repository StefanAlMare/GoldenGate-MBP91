"""Verifică EFI din imaginea B și evidența asamblării grafice pentru 26B131."""
import hashlib
import json
import plistlib
import struct
import uuid
from pathlib import Path


# These are the bytes of B's ESP after verifying its embedded OpenCore config.
ESP_SHA = "42409d2a85dc78786278e685cbca54848304943198dea74833a6df63ce3e62ab"
CONFIG_SHA = "c9f7f622d7a7d7849007b184eb9591b876befe7f87ae853fc8f4a773f555ae0c"
GOLDEN_FRAMEWORKS = {"ImageIO.framework", "CMPhoto.framework"}


def efi_digest(image):
    with image.open("rb") as stream:
        stream.seek(512)
        header = stream.read(92)
        if header[:8] != b"EFI PART":
            raise ValueError("Tabela GPT din imagine nu este validă.")
        table_lba, count, entry_size = struct.unpack_from("<QII", header, 72)
        if table_lba != 2 or count < 2 or entry_size != 128:
            raise ValueError("Tabela de partiții a imaginii B diferă.")
        stream.seek(table_lba * 512)
        entry = stream.read(entry_size)
        first, last = struct.unpack_from("<QQ", entry, 32)
        if (uuid.UUID(bytes_le=entry[:16]) != uuid.UUID("c12a7328-f81f-11d2-ba4b-00a0c93ec93b")
                or (first, last) != (40, 409639)):
            raise ValueError("Partiția EFI diferă de cea asamblată pentru B.")
        stream.seek(first * 512)
        remaining = (last - first + 1) * 512
        digest = hashlib.sha256()
        while remaining:
            data = stream.read(min(remaining, 1024 * 1024))
            if not data:
                raise ValueError("Imaginea este trunchiată în partiția EFI.")
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def verify_graphics(image):
    work = image.parent / "work"
    config = (work / "boot-efi/payload/EFI/OC/config.plist").read_bytes()
    if (efi_digest(image) != ESP_SHA or hashlib.sha256(config).hexdigest() != CONFIG_SHA
            or plistlib.loads(config)["DeviceProperties"] != {"Add": {}, "Delete": {}}):
        raise ValueError("EFI diferă de configurația verificată fără injecții DeviceProperties.")

    installed = json.loads((work / "hardware.json").read_text())["installed"]
    recipe = image.parent / "hooks/02-golden-gate-userspace/prespecialization-26B131.json"
    providers = json.loads(recipe.read_text())["overridden"]
    if any(GOLDEN_FRAMEWORKS.intersection(Path(path).parts) for path in installed + providers):
        raise ValueError("ImageIO sau CMPhoto apare în lista înlocuirilor de sistem ori de cache.")
    for driver in ("AppleIntelHD4000Graphics.kext", "NVDAGK100Hal.kext"):
        if "/System/Library/Extensions/" + driver not in installed:
            raise ValueError("Raportul de instalare nu conține driverul " + driver)
    return {
        "efi_sha256": ESP_SHA,
        "opencore_config_sha256": CONFIG_SHA,
        "device_properties": {"Add": {}, "Delete": {}},
        "kepler_imaging_overrides_omitted": sorted(GOLDEN_FRAMEWORKS),
    }
