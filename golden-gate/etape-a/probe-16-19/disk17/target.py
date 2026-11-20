from pathlib import Path, PurePosixPath
import re
import stat
import struct

CONTAINER_UUID="00000000-0000-4000-8000-000000000004"
DATA_UUID="00000000-0000-4000-8000-000000000002"
SYSTEM_UUID="00000000-0000-4000-8000-000000000009"
PARTITION_UUID="00000000-0000-4000-8000-000000000005"
EXPECTED_BUILD="26B131"

def is_x86_64(data):
    if len(data) < 32: return False
    magic = data[:4]
    if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        return struct.unpack_from("<I", data, 4)[0] == 0x01000007
    if magic in (b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"):
        return struct.unpack_from(">I", data, 4)[0] == 0x01000007
    fat = {b"\xca\xfe\xba\xbe": (">", 20), b"\xbe\xba\xfe\xca": ("<", 20),
           b"\xca\xfe\xba\xbf": (">", 32), b"\xbf\xba\xfe\xca": ("<", 32)}
    if magic not in fat: return False
    endian, step = fat[magic]
    count = struct.unpack_from(endian+"I", data, 4)[0]
    if not 0 < count <= 16 or len(data) < 8+count*step: return False
    return any(struct.unpack_from(endian+"I", data, 8+i*step)[0] == 0x01000007 for i in range(count))

def uuid_value(row):
    return str(row.get("APFSVolumeUUID", row.get("VolumeUUID", ""))).upper()

def device(value):
    value = str(value).removeprefix("/dev/")
    if not re.fullmatch(r"disk\d+(?:s\d+)*", value):
        raise RuntimeError("Identificator diskutil invalid: " + repr(value))
    return value

def identify_volumes(apfs):
    """Pure selection: UUIDs, role, and single physical store must all agree."""
    matches = []
    for row in apfs.get("Containers", []):
        volumes = row.get("Volumes", [])
        if (str(row.get("APFSContainerUUID", "")).upper() == CONTAINER_UUID
                or any(uuid_value(v) in (DATA_UUID, SYSTEM_UUID) for v in volumes)):
            matches.append(row)
    if len(matches) != 1:
        raise RuntimeError("Containerul Golden Gate nu este identificat unic (%d potriviri). "
                           "Conecteaza discul extern cu imaginea pasului 13." % len(matches))
    row = matches[0]
    if str(row.get("APFSContainerUUID", "")).upper() != CONTAINER_UUID:
        raise RuntimeError("UUID-ul containerului nu corespunde imaginii Golden Gate.")
    stores = row.get("PhysicalStores", [])
    if len(stores) != 1:
        raise RuntimeError("Containerul Golden Gate nu are un singur Physical Store.")
    result = {"container": device(row["ContainerReference"]),
              "container_uuid": CONTAINER_UUID,
              "physical_store": device(stores[0]["DeviceIdentifier"]), "volumes": {}}
    for role, expected in (("System", SYSTEM_UUID), ("Data", DATA_UUID)):
        found = [v for v in row.get("Volumes", []) if uuid_value(v) == expected]
        if len(found) != 1 or role not in found[0].get("Roles", []):
            raise RuntimeError("Volumul Golden Gate %s nu corespunde UUID-ului si rolului." % role)
        vol = found[0]
        dev = device(vol["DeviceIdentifier"])
        if not re.fullmatch(re.escape(result["container"]) + r"s\d+", dev):
            raise RuntimeError("Volum in afara containerului Golden Gate.")
        result["volumes"][role] = {"device": dev, "uuid": expected, "name": vol.get("Name")}
    return result

def safe_path(root, relative):
    """Never follow source symlinks or cross into a host filesystem."""
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Cale relativa invalida")
    root = Path(root)
    base_dev = root.stat().st_dev
    p = root
    for part in rel.parts:
        p = p / part
        s = p.lstat()
        if stat.S_ISLNK(s.st_mode):
            raise ValueError("Legatura simbolica omisa: " + str(relative))
        if s.st_dev != base_dev:
            raise ValueError("Alt sistem de fisiere omis: " + str(relative))
    return p

