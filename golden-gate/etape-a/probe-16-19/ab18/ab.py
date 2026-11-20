"""Evită automontarea unui singur volum în prima configurare Golden Gate."""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target import DATA_UUID, SYSTEM_UUID, EXPECTED_BUILD, device, safe_path
from volumes import DISKUTIL, info, mount, require, resolve, run

VOLUME = '00000000-0000-4000-8000-00000000000A'
PARTITION = '00000000-0000-4000-8000-000000000007'
PARTITION_BYTES = 213821423616
# Read-only Darwin ioctls from <sys/disk.h>.
DKIOCGETBLOCKSIZE = 0x40046418
DKIOCGETBLOCKCOUNT = 0x40086419
RULE = ('UUID=' + VOLUME + ' none auto ro,noauto 0 0').encode('ascii')
RECEIPT = '.hao-mbp91-ntfs-test-v1.json'
BACKUP = '.hao-mbp91-ntfs-test-v1.original'
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


def render(original):
    data = original or b''
    require(b'\x00' not in data, 'fstab nu este un fișier text.')
    eol = b'\r\n' if b'\r\n' in data and b'\n' not in data.replace(b'\r\n', b'') else b'\n'
    # Disk Arbitration uses the first matching map. Preserve even a missing
    # final newline in the original and put the narrowly scoped UUID first.
    result = RULE+eol+data
    require(len(result) <= LIMIT, 'fstab rezultat depășește limita.')
    return result


def check_existing(data, label):
    for line in (data or b'').splitlines():
        fields = line.lstrip().split()
        if not fields or fields[0].startswith(b'#'):
            continue
        key = fields[0].lower()
        if VOLUME.lower().encode() in key or PARTITION.lower().encode() in key:
            raise ValueError('fstab are deja o regulă pentru identificatorul urmărit. Verifică manual.')
        if label and key.startswith(b'label='):
            text = re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m[1], 8)]), fields[0][6:])
            require(text.lower() != label.encode().lower(), 'Există deja o regulă pentru eticheta volumului.')


def meta(path):
    s = path.stat()
    return [s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)]


def write_receipt(path, record):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.hao18-', delete=False) as out:
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
    with tempfile.NamedTemporaryFile(dir=dst.parent, prefix='.hao18-', delete=False) as f:
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


def transaction(etc, action, label, owners=True):
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
        check_existing(current, label)
        if action == 'verify':
            return 'Configurația permite testul. Regula de probă este inactivă.'
        attrib = meta(dst) if current is not None else [os.geteuid(), os.getegid(), 0o644]
        record = dict(version=1, volume=VOLUME, data=DATA_UUID, before=sha(current),
                      after=sha(render(current)), metadata=attrib)
        write_receipt(mark, record)
    else:
        record = json.loads(marker)
        require(isinstance(record, dict) and record.get('version') == 1 and record.get('volume') == VOLUME
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
    require(sha(original) == before and sha(render(original)) == after, 'Starea fstab nu corespunde probei.')
    if action == 'verify':
        return 'Regula de probă este activă.' if digest == after else 'Tranzacție întreruptă. Se poate relua sau retrage.'
    if action == 'enable':
        if digest == after:
            return 'Regula de probă este deja activă.'
        if original is not None and saved_bytes is None:
            os.link(dst, saved)
            fsync_dir(etc)
        install_text(dst, original, render(original), attrib)
        require(sha(body(dst)) == after, 'Verificarea scrierii a eșuat.')
        return 'Test activat. Regula a fost verificată pe volumul Data Golden.'
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
    return 'Test retras. Starea originală a fișierului fstab a fost verificată.'


def manage(root, action, label='', owners=True):
    require(action in ('verify','enable','remove'), 'Acțiune necunoscută.')
    etc = safe_path(root, 'private/etc')
    require(etc.is_dir(), 'Directorul etc lipsește.')
    fd = os.open(etc, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH if action=='verify' else fcntl.LOCK_EX)
        return transaction(etc, action, label, owners)
    finally:
        os.close(fd)


def candidate():
    tree = plistlib.loads(run([DISKUTIL, 'list', '-plist', 'internal', 'physical']))
    found = []
    for disk in tree.get('AllDisksAndPartitions', []):
        for part in disk.get('Partitions', []):
            node = device(part['DeviceIdentifier'])
            details = info(node)
            if str(details.get('DiskUUID', '')).upper() == PARTITION:
                found.append((device(disk['DeviceIdentifier']), node, part, details))
    require(len(found) == 1, 'Partiția internă urmărită nu a fost identificată unic.')
    whole, node, listed, details = found[0]
    d = info(whole)
    require(d.get('Internal') is True and d.get('WholeDisk') is True and not d.get('Virtual')
            and d.get('VirtualOrPhysical') != 'Virtual' and (details.get('ParentWholeDisk') or details.get('PartOfWhole')) == whole,
            'Discul candidat nu este fizic intern.')
    volume = ''
    for row in (details, listed):
        reported = str(row.get('VolumeUUID') or '').upper()
        if reported:
            require(reported == VOLUME, f'{node}: VolumeUUID {reported}, așteptat {VOLUME}.')
            volume = reported
    list_size = listed.get('Size')
    io_size = details.get('IOKitSize')
    print(f'{node} — Size (listă GPT) = {list_size or "nepublicat"}, '
          f'IOKitSize = {io_size or "nepublicat"}, TotalSize (info) = {details.get("TotalSize") or "nepublicat"}',
          flush=True)
    fs = ' '.join(str(details.get(k) or '') for k in
            ('FilesystemType','FilesystemName','FileSystemPersonality','TypeBundleName','UserVisibleFilesystemName')).lower()
    if not volume or ('ntfs' not in fs and 'nt file system' not in fs):
        # A raw, read-only boot-sector check also works on an unmounted NTFS volume.
        with open('/dev/r'+node, 'rb', buffering=0) as f:
            boot = f.read(4096)
            require(len(boot) >= 512 and boot[3:11] == b'NTFS    ' and boot[510:512] == b'\x55\xaa',
                    'Semnătura NTFS lipsește. Oprit.')
            if not volume and PARTITION_BYTES not in (list_size, io_size):
                block_size = struct.unpack('=I', fcntl.ioctl(f.fileno(), DKIOCGETBLOCKSIZE, bytes(4)))[0]
                block_count = struct.unpack('=Q', fcntl.ioctl(f.fileno(), DKIOCGETBLOCKCOUNT, bytes(8)))[0]
                physical_bytes = block_size * block_count
                require(physical_bytes == PARTITION_BYTES,
                        f'{node}: UUID-ul volumului nu este disponibil, iar partiția are '
                        f'{physical_bytes} octeți fizici (captură: {PARTITION_BYTES}).')
    print('Partiție confirmată:', node, 'GPT', PARTITION, 'NTFS', 'VolumeUUID', volume or '(nepublicat de Tahoe)',
          'montare:', details.get('MountPoint') or '(nemontată)')
    return str(details.get('VolumeName') or '')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='verify',choices=('verify','enable','remove'))
    action=parser.parse_args().action
    print('GoldenGate-TestNTFS v2', flush=True)
    require(sys.platform == 'darwin' and run(['/usr/bin/sw_vers','-productVersion']).decode().startswith('26.'),
            'Rulează comanda din Tahoe pe MacBookPro9,1.')
    require(action == 'verify' or os.geteuid() == 0, 'Deschide comanda de activare/retragere din Finder.')
    selected, whole=resolve()
    label = candidate() if action != 'remove' else ''
    print('SSD Golden Gate extern:', whole)
    with mount(selected['volumes']['System']['device'], SYSTEM_UUID) as root:
        version=plistlib.loads(safe_path(root,'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        require(version.get('ProductBuildVersion') == EXPECTED_BUILD, 'Build Golden Gate diferit.')
    with mount(selected['volumes']['Data']['device'], DATA_UUID, writable=action!='verify', owners=action!='verify') as root:
        owners = action != 'verify' or info(selected['volumes']['Data']['device']).get('GlobalPermissionsEnabled') is not False
        print(manage(root, action, label, owners))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError,ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        sys.exit('Oprit: '+str(error))
