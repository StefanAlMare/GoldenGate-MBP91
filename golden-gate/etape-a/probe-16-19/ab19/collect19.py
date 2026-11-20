"""Colectează numai noua pornire Golden și starea actuală a celor două reguli."""
import datetime
import os
import plistlib
import pwd
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target import DATA_UUID, EXPECTED_BUILD, SYSTEM_UUID, safe_path
from volumes import mount, require, resolve, run

LOG = Path('private/var/log/hao-diskdiag17')
REFERENCE = {'00000000-0000-4000-8000-00000000000B', '00000000-0000-4000-8000-000000000006'}
VOLUMES = {'NTFS': '00000000-0000-4000-8000-00000000000A', 'exFAT': '00000000-0000-4000-8000-000000000003'}
SESSION = re.compile(r'native-([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})-[A-Za-z0-9]{6}')
TOP = {'STARTED.txt', 'DONE.txt', 'early-processes.log', 'early-media.log', 'events.log'}
ROUND_FILE = re.compile(r'(?:ioreg-(?:IOMedia|AppleDiskImageDevice|AppleDiskImagesController)\.txt|(?:diskimagescontroller|diskimagesiod|mbsystemadministration|fskitd|diskarbitrationd)-[0-9]+-sample\.txt)')


def utc(stamp):
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat(timespec='seconds')


def read(root, rel, limit):
    path = safe_path(root, str(rel))
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        entry = os.fstat(stream.fileno())
        require(stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1
                and entry.st_dev == root.stat().st_dev and entry.st_size <= limit,
                'Fișier neașteptat: ' + str(rel))
        data = stream.read(limit+1)
        require(len(data) == entry.st_size, 'Fișier schimbat în timpul citirii: ' + str(rel))
        return data, entry.st_mtime


def newest(root):
    try:
        base = safe_path(root, str(LOG))
    except FileNotFoundError:
        return None
    runs = []
    for item in base.iterdir():
        match = SESSION.fullmatch(item.name)
        if not match or match[1].upper() in REFERENCE:
            continue
        try:
            payload, stamp = read(root, LOG/item.name/'STARTED.txt', 16384)
        except FileNotFoundError:
            continue
        if payload:
            runs.append((stamp, item.name, match[1].upper()))
    return max(runs, default=None)


def collect(root):
    lines = ['Golden Gate ' + EXPECTED_BUILD, 'UUID Data extern ' + DATA_UUID]
    try:
        fstab, stamp = read(root, 'private/etc/fstab', 1024*1024)
        lines.append('Data modificării fstab (UTC) ' + utc(stamp))
    except FileNotFoundError:
        fstab = b''
        lines.append('fstab lipsește')
    rows = [row.split(b'#', 1)[0].split() for row in fstab.splitlines()]
    for fs, uuid in VOLUMES.items():
        fields = next((r for r in rows if r and r[0].lower() == ('uuid='+uuid).lower().encode()), [])
        active = len(fields) >= 4 and fields[1:3] == [b'none', b'auto'] and b'noauto' in fields[3].split(b',')
        lines.append(f'{fs} {uuid} — noauto în fstab la colectare: {"da" if active else "nu"}')
    try:
        setup = safe_path(root, 'private/var/db/.AppleSetupDone').lstat()
        lines.append('Marcaj .AppleSetupDone ' + (utc(setup.st_mtime) if stat.S_ISREG(setup.st_mode) else 'tip neașteptat'))
    except FileNotFoundError:
        lines.append('Marcaj .AppleSetupDone absent')
    session = newest(root)
    result = {}
    if session:
        stamp, name, uuid = session
        lines.extend(['UUID pornire ' + uuid, 'Observator pornit (UTC) ' + utc(stamp)])
        folder = LOG/name
        candidates = [folder/n for n in sorted(TOP)]
        for sub in ('round-1', 'round-2'):
            try:
                directory = safe_path(root, str(folder/sub))
            except FileNotFoundError:
                continue
            candidates.extend(folder/sub/p.name for p in sorted(directory.iterdir()) if ROUND_FILE.fullmatch(p.name))
        total = samples = 0
        for rel in candidates:
            try:
                data, _ = read(root, rel, 5*1024*1024)
            except FileNotFoundError:
                continue
            total += len(data)
            require(total <= 32*1024*1024, 'Captura depășește 32 MiB.')
            result['probe/'+str(rel.relative_to(LOG))] = data
            if rel.name.endswith('-sample.txt') and b'Call graph:' in data:
                samples += 1
        lines.append(f'Stive de procese lizibile: {samples}')
    else:
        lines.append('Observatorul nu a înregistrat încă o pornire diferită de cele două capturi cunoscute.')
    report = '\n'.join(lines) + '\n'
    result['rezultat.txt'] = report.encode()
    return result, report


def write_zip(files, desktop):
    with tempfile.NamedTemporaryFile(prefix='GoldenGate-9_1-NTFS-exFAT-', suffix='.zip',
                                     dir=desktop, delete=False) as handle:
        name = Path(handle.name)
        try:
            with zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                for entry, data in files.items():
                    archive.writestr(entry, data)
        except BaseException:
            name.unlink()
            raise
    return name


def main():
    require(sys.platform == 'darwin' and os.geteuid() == 0 and int(os.environ.get('SUDO_UID', '0')) > 0,
            'Deschide Colecteaza.command din Tahoe, din contul obișnuit.')
    user = pwd.getpwuid(int(os.environ['SUDO_UID']))
    require(run(['/usr/bin/sw_vers', '-productVersion']).startswith(b'26.'), 'Pornește în Tahoe pentru colectare.')
    selected, _ = resolve()
    nodes = selected['volumes']
    with mount(nodes['System']['device'], SYSTEM_UUID) as root:
        version, _ = read(root, 'System/Library/CoreServices/SystemVersion.plist', 1024*1024)
        require(plistlib.loads(version).get('ProductBuildVersion') == EXPECTED_BUILD, 'Build Golden diferit.')
    with mount(nodes['Data']['device'], DATA_UUID) as root:
        files, report = collect(root)
    # Create the archive on the desktop with the invoking user's permissions.
    os.initgroups(user.pw_name, user.pw_gid)
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    path = write_zip(files, Path(user.pw_dir)/'Desktop')
    print(report + 'Arhiva de pe Desktop: ' + str(path))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        sys.exit('Oprit: ' + str(exc))
