import contextlib
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path
from target import DATA_UUID, SYSTEM_UUID, PARTITION_UUID, device, identify_volumes, uuid_value

DISKUTIL = "/usr/sbin/diskutil"

def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(cmd, timeout=30):
    p = subprocess.run(list(map(str, cmd)), capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{cmd[0]} {cmd[1]}: ' + (p.stderr or p.stdout).decode(errors='replace').strip())
    return p.stdout


def info(dev):
    return plistlib.loads(run([DISKUTIL, 'info', '-plist', dev]))


def resolve():
    selected = identify_volumes(plistlib.loads(run([DISKUTIL, 'apfs', 'list', '-plist'])))
    store = info(selected['physical_store'])
    whole = device(store.get('ParentWholeDisk') or store.get('PartOfWhole') or '')
    d = info(whole)
    require(str(store.get('DiskUUID','')).upper() == PARTITION_UUID and d.get('WholeDisk') is True and
            d.get('Internal') is False and not d.get('Virtual') and d.get('VirtualOrPhysical') != 'Virtual',
            'Discul nu corespunde SSD-ului fizic extern de la pasul 13.')
    host = info('/')
    require(host.get('APFSContainerReference') != selected['container'] and
            uuid_value(host) not in (SYSTEM_UUID, DATA_UUID) and
            str(host.get('APFSVolumeGroupID','')).upper() not in (DATA_UUID, SYSTEM_UUID),
            'Pornește în Tahoe pentru această operație.')
    return selected, whole


@contextlib.contextmanager
def mount(dev, expected=None, writable=False, owners=False):
    before = info(dev)
    if expected:
        require(uuid_value(before) == expected, 'UUID incorect înainte de montare.')
    old = before.get('MountPoint') if before.get('Mounted', bool(before.get('MountPoint'))) else None
    temp = Path(tempfile.mkdtemp(prefix='hao18-mnt-')).resolve()
    own = fixed_owners = False
    try:
        if not old:
            mode = [] if writable else ['readOnly']
            run([DISKUTIL,'mount',*mode,'-mountOptions','nobrowse,owners' if owners else 'nobrowse',
                 '-mountPoint',temp,dev], 60)
            own = True
        actual = info(dev)
        p = Path(actual.get('MountPoint') or '/')
        require(p != Path('/') and p.is_dir() and p.samefile(old or temp) and
                (not expected or uuid_value(actual) == expected), 'Punct de montare neașteptat.')
        require(not writable or (actual.get('WritableVolume') is not False and not actual.get('ReadOnlyVolume')
                and not (os.statvfs(p).f_flag & os.ST_RDONLY)), 'Volumul țintă este montat numai pentru citire: ' + str(p))
        if owners and writable and actual.get('GlobalPermissionsEnabled') is False:
            run(['/sbin/mount','-u','-o','owners',str(p)])
            fixed_owners = True
            require(info(dev).get('GlobalPermissionsEnabled') is not False,
                    'Nu s-au putut activa permisiunile UNIX pe volumul Data extern.')
        yield p
    finally:
        try:
            if own:
                run([DISKUTIL,'unmount',dev], 55)
            elif fixed_owners:
                run(['/sbin/mount','-u','-o','noowners',str(p)])
        finally:
            # Never recurse into the mountpoint, even after a diskutil timeout.
            try:
                temp.rmdir()
            except OSError:
                print('Punctul de montare a rămas disponibil: '+str(temp),file=sys.stderr)



