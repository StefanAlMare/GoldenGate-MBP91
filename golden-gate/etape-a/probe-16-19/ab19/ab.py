"""Probează automontarea NTFS și exFAT în prima configurare Golden Gate."""
import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import re
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target import DATA_UUID, SYSTEM_UUID, EXPECTED_BUILD, device, safe_path
from volumes import DISKUTIL, info, mount, require, resolve, run

@dataclass(frozen=True)
class VolumeSpec:
    kind: str
    uuid: str
    gpt: str
    size: int
    signature: bytes

    @property
    def rule(self):
        return ('UUID=' + self.uuid + ' none auto ro,noauto 0 0').encode('ascii')


NTFS = VolumeSpec('NTFS', '00000000-0000-4000-8000-00000000000A',
                  '00000000-0000-4000-8000-000000000007', 213821423616, b'NTFS    ')
EXFAT = VolumeSpec('exFAT', '00000000-0000-4000-8000-000000000003',
                   '00000000-0000-4000-8000-000000000008', 409250824192, b'EXFAT   ')
VOLUMES = (NTFS, EXFAT)
# Read-only Darwin ioctls from <sys/disk.h>.
DKIOCGETBLOCKSIZE = 0x40046418
DKIOCGETBLOCKCOUNT = 0x40086419
V2_RECEIPT = '.hao-mbp91-ntfs-test-v1.json'
V2_BACKUP = '.hao-mbp91-ntfs-test-v1.original'
RECEIPT = '.hao-mbp91-ntfs-exfat-test-v1.json'
BACKUP = '.hao-mbp91-ntfs-exfat-test-v1.original'
LIMIT = 1024*1024


def regular(path, allow_links=False):
    try:
        s = path.lstat()
    except FileNotFoundError:
        return None
    require(stat.S_ISREG(s.st_mode) and s.st_dev == path.parent.stat().st_dev
            and 0 <= s.st_size <= LIMIT and (s.st_nlink == 1 or allow_links),
            'Fișier neașteptat: ' + str(path))
    return s


def body(path, links=False):
    if regular(path, links) is None:
        return None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        data = f.read(LIMIT+1)
    require(len(data) <= LIMIT, 'Fișier prea mare: ' + str(path))
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prepend(original, volumes):
    data = original or b''
    require(b'\x00' not in data, 'fstab nu este un fișier text.')
    eol = b'\r\n' if b'\r\n' in data and b'\n' not in data.replace(b'\r\n', b'') else b'\n'
    # Disk Arbitration uses the first matching map. Preserve even a missing
    # final newline in the original and put the narrowly scoped UUID first.
    result = b''.join(vol.rule + eol for vol in volumes) + data
    require(len(result) <= LIMIT, 'fstab rezultat depășește limita.')
    return result


def check_existing(data, labels):
    labels = {label.lower().encode() for label in labels if label}
    for line in (data or b'').splitlines():
        fields = line.lstrip().split()
        if not fields or fields[0].startswith(b'#'):
            continue
        key = fields[0].lower()
        if any(identifier.lower().encode() in key for vol in VOLUMES for identifier in (vol.uuid, vol.gpt)):
            raise ValueError('fstab are deja o regulă pentru identificatorul urmărit. Verifică manual.')
        if labels and key.startswith(b'label='):
            text = re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m[1], 8)]), fields[0][6:])
            require(text.lower() not in labels, 'Există deja o regulă pentru eticheta volumului.')


def meta(path):
    s = path.stat()
    return [s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)]


def write_receipt(path, record):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.hao19-', delete=False) as out:
        tmp = Path(out.name)
        try:
            out.write(json.dumps(record, sort_keys=True).encode())
            out.flush()
            os.fsync(out.fileno())
            os.link(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    fsync_dir(path.parent)


def install_text(dst, original, after, attrib):
    with tempfile.NamedTemporaryFile(dir=dst.parent, prefix='.hao19-', delete=False) as f:
        tmp = Path(f.name)
    try:
        if original is not None:
            # Darwin cp -p carries the original mode, owner, extended attributes and ACL.
            subprocess.run(['/bin/cp','-p',str(dst),str(tmp)], check=True)
        with tmp.open('wb') as f:
            f.write(after)
            if original is None:
                os.fchmod(f.fileno(), attrib[2])
            f.flush()
            os.fsync(f.fileno())
        require(body(tmp) == after and meta(tmp) == attrib, 'Copiere incompletă a conținutului sau permisiunilor.')
        require(body(dst, True) == original, 'fstab s-a schimbat în timpul testului.')
        os.replace(tmp, dst)
        fsync_dir(dst.parent)
    finally:
        tmp.unlink(missing_ok=True)


def v2_state(etc, original, original_path, labels, owners):
    marker = body(etc / V2_RECEIPT)
    saved = body(etc / V2_BACKUP)
    if marker is None:
        require(saved is None, 'Există o copie NTFS v2 fără jurnal. Verifică întâi cu pachetul v2.')
        check_existing(original, labels)
        return None

    record = json.loads(marker)
    require(isinstance(record, dict) and record.get('version') == 1 and
            record.get('volume') == NTFS.uuid and record.get('data') == DATA_UUID and
            'before' in record and record['before'] == sha(saved) and
            record.get('after') == sha(original) and original == prepend(saved, (NTFS,)),
            'Starea NTFS v2 sau copia sa sunt incomplete. Verifică întâi cu pachetul v2.')
    attributes = record.get('metadata')
    require(isinstance(attributes, list) and len(attributes) == 3 and
            all(isinstance(i, int) and i >= 0 for i in attributes), 'Permisiuni lipsă în jurnalul NTFS v2.')
    paths = [original_path] if saved is None else [original_path, etc / V2_BACKUP]
    for path in paths:
        actual = meta(path)
        require(actual == attributes if owners else actual[2] == attributes[2],
                'Permisiunile fișierelor NTFS v2 s-au schimbat. Verifică întâi cu pachetul v2.')
    check_existing(saved, labels)
    return sha(marker)


def render(original, v2):
    return prepend(original, (EXFAT,) if v2 else VOLUMES)


def transaction(etc, action, labels, owners=True):
    dst, saved, mark = etc/'fstab', etc/BACKUP, etc/RECEIPT
    marker = body(mark)
    saved_bytes = body(saved, True)
    current = body(dst, True)
    if dst.exists() and dst.stat().st_nlink != 1:
        require(marker is not None and saved_bytes is not None and saved.samefile(dst)
                and dst.stat().st_nlink == 2, 'fstab are legături nerecunoscute.')
    if marker is None:
        require(saved_bytes is None, 'Există o copie de siguranță fără jurnalul acestei probe.')
        if action == 'remove':
            return 'Testul nu este instalat.'
        v2 = v2_state(etc, current, dst, labels, owners)
        if action == 'verify':
            return ('Proba cumulativă este inactivă. NTFS v2 este activ.' if v2 else
                    'Proba cumulativă este inactivă. Activarea va adăuga ambele reguli.')
        attrib = meta(dst) if current is not None else [os.geteuid(), os.getegid(), 0o644]
        record = dict(version=1, volumes=[v.uuid for v in VOLUMES], data=DATA_UUID, v2=v2, before=sha(current),
                      after=sha(render(current, v2)), metadata=attrib)
        write_receipt(mark, record)
    else:
        record = json.loads(marker)
        require(isinstance(record, dict) and record.get('version') == 1 and record.get('volumes') == [v.uuid for v in VOLUMES]
                and 'v2' in record and 'before' in record
                and record.get('data') == DATA_UUID and re.fullmatch('[0-9a-f]{64}', str(record.get('after','')))
                and (record.get('before') is None or re.fullmatch('[0-9a-f]{64}', str(record['before'])))
                and isinstance(record.get('metadata'), list) and len(record['metadata']) == 3
                and all(isinstance(i,int) and i >= 0 for i in record['metadata']),
                'Jurnalul testului este invalid.')
    before, after, attrib = record['before'], record['after'], record['metadata']
    digest = sha(current)
    require(digest in (before, after), 'fstab a fost modificat după începerea probei. Îl păstrez și păstrez copia.')
    def metadata_ok(file):
        actual = meta(file)
        return actual == attrib if owners else actual[2] == attrib[2]
    if current is not None:
        require(metadata_ok(dst), 'Permisiunile fstab au fost modificate. Verifică manual.')
    if saved_bytes is not None:
        require(before is not None and sha(saved_bytes) == before and metadata_ok(saved)
                and (saved.stat().st_nlink == 1 or
                     (saved.stat().st_nlink == 2 and dst.exists() and saved.samefile(dst))), 'Copia originală este neconformă.')
    if digest == after and before is not None:
        require(saved_bytes is not None, 'Copia originală lipsește. Oprit.')
    original = saved_bytes if digest == after else current
    v2 = v2_state(etc, original, saved if digest == after else dst, labels, owners)
    require(v2 == record['v2'] and sha(original) == before and sha(render(original, v2)) == after, 'Starea fstab nu corespunde probei.')
    if action == 'verify':
        return 'Proba cumulativă este activă (NTFS + exFAT).' if digest == after else 'Tranzacție întreruptă. Se poate relua sau retrage.'
    if action == 'enable':
        if digest == after:
            return 'Proba cumulativă este deja activă (NTFS + exFAT).'
        if original is not None and saved_bytes is None:
            os.link(dst, saved)
            fsync_dir(etc)
        install_text(dst, original, render(original, v2), attrib)
        require(sha(body(dst)) == after, 'Verificarea scrierii a eșuat.')
        return 'Test activat. Ambele reguli sunt prezente pe volumul Data Golden.'
    if digest == after:
        if before is None:
            dst.unlink()
        else:
            os.replace(saved, dst)
        fsync_dir(etc)
    require(sha(body(dst, True)) == before, 'Restaurarea fstab nu a fost confirmată.')
    if saved.exists():
        saved.unlink()
    mark.unlink()
    fsync_dir(etc)
    return ('Test cumulativ retras. Configurația anterioară cu NTFS v2 activ a fost restaurată.' if v2 else
            'Test cumulativ retras. Configurația anterioară fără cele două reguli a fost restaurată.')


def manage(root, action, labels=(), owners=True):
    require(action in ('verify','enable','remove'), 'Acțiune necunoscută.')
    etc = safe_path(root, 'private/etc')
    require(etc.is_dir(), 'Directorul etc lipsește.')
    fd = os.open(etc, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH if action=='verify' else fcntl.LOCK_EX)
        return transaction(etc, action, labels, owners)
    finally:
        os.close(fd)


def candidates():
    tree = plistlib.loads(run([DISKUTIL, 'list', '-plist', 'internal', 'physical']))
    found = {}
    for disk in tree.get('AllDisksAndPartitions', []):
        for part in disk.get('Partitions', []):
            node = device(part['DeviceIdentifier'])
            details = info(node)
            gpt = str(details.get('DiskUUID', '')).upper()
            for vol in VOLUMES:
                if vol.gpt == gpt:
                    require(vol not in found, 'UUID GPT duplicat: ' + gpt)
                    found[vol] = (device(disk['DeviceIdentifier']), node, part, details)
    require(len(found) == len(VOLUMES), 'Cele două partiții interne urmărite nu au fost identificate.')
    whole = found[NTFS][0]
    require(found[EXFAT][0] == whole, 'Partițiile urmărite sunt pe discuri diferite.')
    d = info(whole)
    require(d.get('Internal') is True and d.get('WholeDisk') is True and not d.get('Virtual')
            and d.get('VirtualOrPhysical') != 'Virtual', 'Discul candidat nu este fizic intern.')
    return tuple(check_volume(vol, *found[vol]) for vol in VOLUMES)


def check_volume(vol, whole, node, listed, details):
    require((details.get('ParentWholeDisk') or details.get('PartOfWhole')) == whole,
            'Discul părinte al partiției nu corespunde.')
    volume = ''
    for row in (details, listed):
        reported = str(row.get('VolumeUUID') or '').upper()
        if reported:
            require(reported == vol.uuid, f'{node}: VolumeUUID {reported}, așteptat {vol.uuid}.')
            volume = reported
    list_size = listed.get('Size')
    io_size = details.get('IOKitSize')
    print(f'{node} — Size (listă GPT) = {list_size or "nepublicat"}, '
          f'IOKitSize = {io_size or "nepublicat"}, TotalSize (info) = {details.get("TotalSize") or "nepublicat"}',
          flush=True)
    fs = ' '.join(str(details.get(k) or '') for k in
            ('FilesystemType','FilesystemName','FileSystemPersonality','TypeBundleName','UserVisibleFilesystemName')).lower()
    recognized = vol.kind.lower() in fs or (vol == NTFS and 'nt file system' in fs)
    if not volume or not recognized:
        # A raw, read-only boot-sector check also works when Tahoe omits filesystem metadata.
        with open('/dev/r'+node, 'rb', buffering=0) as f:
            boot = f.read(4096)
            require(len(boot) >= 512 and boot[3:11] == vol.signature and boot[510:512] == b'\x55\xaa',
                    f'Semnătura {vol.kind} lipsește. Oprit.')
            if not volume and vol.size not in (list_size, io_size):
                block_size = struct.unpack('=I', fcntl.ioctl(f.fileno(), DKIOCGETBLOCKSIZE, bytes(4)))[0]
                block_count = struct.unpack('=Q', fcntl.ioctl(f.fileno(), DKIOCGETBLOCKCOUNT, bytes(8)))[0]
                physical_bytes = block_size * block_count
                require(physical_bytes == vol.size,
                        f'{node}: UUID-ul volumului nu este disponibil, iar partiția are '
                        f'{physical_bytes} octeți fizici (captură: {vol.size}).')
    print('Partiție confirmată:', node, 'GPT', vol.gpt, vol.kind, 'VolumeUUID', volume or '(nepublicat de Tahoe)',
          'montare:', details.get('MountPoint') or '(nemontată)')
    return str(details.get('VolumeName') or '')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='verify',choices=('verify','enable','remove'))
    action=parser.parse_args().action
    print('GoldenGate-TestNTFS-exFAT, proba cumulativă', flush=True)
    require(sys.platform == 'darwin' and run(['/usr/bin/sw_vers','-productVersion']).decode().startswith('26.'),
            'Rulează comanda din Tahoe pe MacBookPro9,1.')
    require(action == 'verify' or os.geteuid() == 0, 'Deschide comanda de activare/retragere din Finder.')
    selected, whole=resolve()
    labels = candidates() if action != 'remove' else ()
    print('SSD Golden Gate extern:', whole)
    with mount(selected['volumes']['System']['device'], SYSTEM_UUID) as root:
        version=plistlib.loads(safe_path(root,'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        require(version.get('ProductBuildVersion') == EXPECTED_BUILD, 'Build Golden Gate diferit.')
    with mount(selected['volumes']['Data']['device'], DATA_UUID, writable=action!='verify', owners=action!='verify') as root:
        owners = action != 'verify' or info(selected['volumes']['Data']['device']).get('GlobalPermissionsEnabled') is not False
        print(manage(root, action, labels, owners))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError,ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        sys.exit('Oprit: '+str(error))
