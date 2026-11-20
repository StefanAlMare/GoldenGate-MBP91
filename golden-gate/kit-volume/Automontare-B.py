#!/usr/bin/python3
"""Pregătește proba NTFS/exFAT la pornire pe Golden B sau restabilește regulile."""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import runpy
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile


FSTAB_OWNER = 0

def require(state, message):
    if not state:
        raise ValueError(message)


def disk(*args):
    r = subprocess.run(['/usr/sbin/diskutil', *args], capture_output=True, check=True, timeout=15)
    return plistlib.loads(r.stdout)


def volume_data(group, offline):
    if not offline:
        model = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.model'], text=True).strip()
        build = subprocess.check_output(['/usr/bin/sw_vers', '-buildVersion'], text=True).strip()
        require((model, build) == ('MacBookPro9,1', '26B131'), 'Calculatorul sau buildul diferă de B.')
    boot = disk('info', '-plist', '/').get('APFSVolumeGroupID')
    require(bool(boot) and (boot != group if offline else boot == group), 'Grupul APFS pornit diferă de cel cerut.')
    matches = []
    live_device = None if offline else disk('info', '-plist', '/System/Volumes/Data')['DeviceIdentifier']
    for container in disk('apfs', 'list', '-plist')['Containers']:
        for vol in container['Volumes']:
            if vol.get('Roles') != ['Data'] or (live_device and vol['DeviceIdentifier'] != live_device):
                continue
            item = disk('info', '-plist', vol['DeviceIdentifier'])
            if item.get('APFSVolumeGroupID') == group and item.get('MountPoint'):
                require(item.get('DeviceIdentifier') == vol['DeviceIdentifier'], 'Identitatea Data s-a schimbat.')
                matches.append((Path(item['MountPoint']), container))
    require(len(matches) == 1, 'Este necesar un singur volum Data B montat. Verifică dacă USB-ul B este conectat.')
    mount, container = matches[0]
    require(mount == Path('/System/Volumes/Data') if not offline else mount.parent == Path('/Volumes'),
            'Punct de montare diferit de Data B.')
    stores = container['PhysicalStores']
    require(len(stores) == 1, 'Containerul B are o configurație fizică diferită.')
    part = disk('info', '-plist', stores[0]['DeviceIdentifier'])
    parent = part.get('ParentWholeDisk') or part.get('PartOfWhole')
    require(parent and re.fullmatch(r'disk[0-9]+', parent), 'Suportul USB al lui B nu a fost identificat.')
    physical = disk('info', '-plist', parent)
    external = {d['DeviceIdentifier'] for d in disk('list', '-plist', 'external', 'physical')['AllDisksAndPartitions']}
    require(parent in external and physical.get('BusProtocol') == 'USB'
            and physical.get('WholeDisk') is True and physical.get('Internal') is False,
            'Data B trebuie să fie pe un SSD USB fizic extern.')
    return mount


def convert(raw, ids, old, new):
    rows = []
    seen = set()
    for line in raw.splitlines(keepends=True):
        fields = list(re.finditer(rb'\S+', line.partition(b'#')[0]))
        parts = [f.group() for f in fields]
        if parts and parts[0].upper() in ids:
            name = parts[0].upper()
            require(name not in seen and len(parts) == 6 and parts[1:3] == [b'none', b'auto']
                    and parts[4:] == [b'0', b'0'] and sorted(parts[3].split(b',')) == sorted(old.split(b',')),
                    'Regulă duplicată sau opțiuni neașteptate în fstab.')
            seen.add(name)
            field = fields[3]
            line = line[:field.start()] + new + line[field.end():]
        rows.append(line)
    require(seen == ids, 'Lipsește cel puțin una dintre regulile verificate pe B.')
    return b''.join(rows)


def replace_file(path, content, basis, expected):
    fd, tmpname = tempfile.mkstemp(prefix='.gg-fstab-', dir=path.parent)
    os.close(fd)
    tmp = Path(tmpname)
    try:
        shutil.copy2(basis, tmp)
        with tmp.open('wb') as f:
            f.write(content)
            f.flush()
            os.fchown(f.fileno(), basis.stat().st_uid, basis.stat().st_gid)
            os.fchmod(f.fileno(), stat.S_IMODE(basis.stat().st_mode))
            os.fsync(f.fileno())
        require(tmp.read_bytes() == content, 'Verificarea copiei temporare a eșuat.')
        if expected is None:
            os.link(tmp, path)
        else:
            require(path.read_bytes() == expected, 'fstab s-a schimbat în timpul probei.')
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply(mount, volumes, undo):
    ids = {('UUID=' + value).encode('ascii').upper() for value in volumes.values()}
    path = mount / 'private/etc/fstab'
    backup = path.with_name('fstab.golden-b-inainte-de-automontare')
    require(path.resolve() == path and path.lstat().st_dev == mount.stat().st_dev
            and stat.S_ISREG(path.lstat().st_mode) and path.stat().st_uid == FSTAB_OWNER, 'Calea fstab nu corespunde volumului B.')
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = path.read_bytes()
        if os.path.lexists(backup):
            s = backup.lstat()
            require(stat.S_ISREG(s.st_mode) and s.st_uid == FSTAB_OWNER and not s.st_mode & 0o022,
                    'Copia inițială a fstab este ambiguă.')
            initial = backup.read_bytes()
        else:
            require(not undo, 'Copia pentru revenire lipsește.')
            initial = current
        enabled = convert(initial, ids, b'ro,noauto', b'ro,auto')
        require(current in (initial, enabled), 'fstab diferă de stările probei. Se păstrează modificările existente.')
        if not backup.exists():
            replace_file(backup, initial, path, None)
        wanted = initial if undo else enabled
        if current != wanted:
            replace_file(path, wanted, path, current)
        try:
            os.fsync(directory)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
        require(path.read_bytes() == wanted and backup.read_bytes() == initial, 'Recitirea fstab a eșuat.')
    finally:
        os.close(directory)
    print('GG_BOOT B', 'NTFS și exFAT: ro,noauto restabilit' if undo else 'NTFS și exFAT: ro,auto confirmat',
          '| SHA-256 fstab', hashlib.sha256(wanted).hexdigest(), flush=True)


def worker(mode, group, volumes):
    mount = volume_data(group, mode.endswith('-usb'))
    if not mode.endswith('-usb'):
        require((mount / 'private/etc/fstab').samefile('/etc/fstab'), 'fstab activ nu corespunde volumului Data.')
    if mode == 'activeaza':
        # A passive read of the kernel table cannot submit another DA request after a timeout.
        table = subprocess.check_output(['/sbin/mount'], text=True, timeout=8).splitlines()
        for line in table:
            if re.search(r'\((?:[^)]*, )?(?:exfat|ntfs)(?:,|\))', line, re.I):
                print('Tabelul curent indică NTFS/exFAT:', line.split(' on ')[0], flush=True)
    apply(mount, volumes, mode.startswith('revenire'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mod', choices=['activeaza', 'revenire', 'activeaza-usb', 'revenire-usb'])
    args = parser.parse_args()
    here = Path(__file__).resolve()
    diag = here.parents[1] / 'diagnostics'
    prep = runpy.run_path(str(diag / 'GoldenGate-Pregateste-B.command'))
    receipt = json.loads(prep['RECEIPT'].read_bytes())
    group = prep['GROUP']
    require(receipt['status'] == 'complete' and receipt['identity']['group_uuid'] == group
            and receipt['noauto'] == prep['WANTED'], 'Bonul B diferă.')
    pack = [args.mod, group, json.dumps(receipt['noauto'])]
    if args.mod.endswith('-usb'):
        cmd = ['/usr/bin/sudo', '--', '/usr/bin/python3', '-IB', '-c', here.read_text(), *pack]
    else:
        client = runpy.run_path(str(diag / 'GoldenGate-Test-Cache-A-pe-B.command'))
        remote = ['/usr/bin/sudo', '--', '/usr/local/lib/hao/python/bin/python3.12', '-IB', '-c',
                  here.read_text(), *pack]
        cmd = client['SSH'] + ['-tt', client['HOST'], shlex.join(remote)]
    return subprocess.call(cmd)


if __name__ == '__main__':
    try:
        if sys.argv[0] == '-c':
            worker(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
        else:
            sys.exit(main())
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit('GG_BOOT oprit: ' + str(exc))
