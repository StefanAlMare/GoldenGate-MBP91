"""Inventar și probă de montare numai pentru citire pe Golden B."""
import argparse
import ctypes
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import runpy
import shlex
import subprocess
import sys
import tempfile
import time


DISK = '/usr/sbin/diskutil'
KINDS = ('NTFS', 'exFAT')
FILESYSTEM_ROOT = Path('/System/Library/Filesystems')
EXFAT_EXTENSION = Path('/System/Library/ExtensionKit/Extensions/com.apple.fskit.exfat.appex/Contents')
BASIC = {'microsoftbasicdata', 'windowsntfs', 'windowsfat32', 'windowsfat32(lba)',
         'ebd0a0a2b9e5443387c068b6b72699c7'}
READ_SAMPLE = r"""
import os, stat, sys
root = sys.argv[1]
sample = sys.argv[2] == 'da'
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
fd = os.open(root, flags)
unit = os.fstat(fd).st_dev
if unit == os.stat(os.path.dirname(root)).st_dev:
    sys.exit('Punctul nu mai este montat.')
if not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
    print('rw'); sys.exit()
if not sample:
    print('ro'); sys.exit()
remaining = 160
def read_file(directory, depth):
    global remaining
    with os.scandir(directory) as rows:
        for row in rows:
            if remaining <= 0: break
            remaining -= 1
            if row.name.startswith('.'): continue
            try:
                item = row.stat(follow_symlinks=False)
                if item.st_dev != unit: continue
                if stat.S_ISREG(item.st_mode) and item.st_size:
                    child = os.open(row.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        actual = os.fstat(child)
                        if stat.S_ISREG(actual.st_mode) and os.path.samestat(item, actual):
                            size = len(os.read(child, 4096))
                            if size: return size
                    finally: os.close(child)
                elif depth and stat.S_ISDIR(item.st_mode):
                    child = os.open(row.name, flags, dir_fd=directory)
                    try:
                        if os.path.samestat(item, os.fstat(child)):
                            size = read_file(child, depth - 1)
                            if size: return size
                    finally: os.close(child)
            except (PermissionError, FileNotFoundError, NotADirectoryError): continue
    return 0
try:
    size = read_file(fd, 2)
except OSError:
    size = 0
print('ro', size)
"""


def report(*words):
    print('GG_VOLUME', *words, flush=True)


def require(test, message):
    if not test:
        raise ValueError(message)


def plist(*args):
    proc = subprocess.run([DISK, *args], capture_output=True, timeout=12)
    require(proc.returncode == 0, 'diskutil nu a putut citi metadatele.')
    return plistlib.loads(proc.stdout)


def info(key):
    return plist('info', '-plist', key)


def content(value):
    return re.sub(r'[\s_-]', '', str(value or '').lower())


def kind(data):
    values = ' '.join(str(data.get(key, '')) for key in
                      ('FilesystemType', 'FilesystemName', 'FileSystemPersonality',
                       'TypeBundleName', 'UserVisibleFilesystemName')).lower()
    found = [name for name, pattern in [('exFAT', r'\bexfat\b'), ('NTFS', r'\b(?:ntfs(?:_3g|3g)?|nt file system|tuxera_ntfs)\b'),
                                         ('APFS', r'\bapfs\b')] if re.search(pattern, values)]
    return found[0] if len(found) == 1 else None


def identity(uuid, expected, dev, parent):
    d = info(dev)
    whole = info(parent)
    require(whole.get('WholeDisk') is True and whole.get('Internal') is True
            and whole.get('DeviceIdentifier') == parent and whole.get('Virtual') is not True
            and whole.get('VirtualOrPhysical') != 'Virtual', 'Discul fizic intern s-a schimbat.')
    require(d.get('DeviceIdentifier') == dev and d.get('WholeDisk') is False
            and (d.get('ParentWholeDisk') or d.get('PartOfWhole')) == parent
            and str(d.get('VolumeUUID', '')).upper() == uuid and kind(d) == expected
            and content(d.get('Content')) in BASIC, 'Identitatea sau formatul volumului diferă.')
    return d


def discover(volumes, selected):
    listing = plist('list', '-plist', 'physical')
    parents = listing.get('AllDisksAndPartitions')
    require(isinstance(parents, list), 'Lista discurilor fizice lipsește.')
    found = {fs: [] for fs in selected}
    for disk in parents:
        parent = disk.get('DeviceIdentifier', '')
        for part in disk.get('Partitions', []):
            if content(part.get('Content')) not in BASIC:
                continue
            dev = part.get('DeviceIdentifier', '')
            require(re.fullmatch(r'disk\d+', parent) and re.fullmatch(re.escape(parent) + r's\d+', dev),
                    'Identificator de partiție nevalid.')
            d = info(dev)
            uuid = str(d.get('VolumeUUID', '')).upper()
            for fs in selected:
                if volumes[fs] == uuid:
                    found[fs].append((uuid, fs, dev, parent))
    for fs in selected:
        require(len(found[fs]) == 1, fs + ': UUID lipsă sau duplicat pe discurile fizice.')
        found[fs] = found[fs][0]
        identity(*found[fs])
    return found


def mounted(d):
    path = d.get('MountPoint') or ''
    if not path and 'Mounted' not in d:
        # Some diskutil plists omit both fields for an unmounted filesystem.
        # Older FSKit mount records can name their block device inside a URL.
        node = d['DeviceIdentifier']
        rows = subprocess.run(['/sbin/mount'], capture_output=True, text=True, timeout=8, check=True).stdout.splitlines()
        require(rows and all(' on ' in row for row in rows), 'Tabelul montărilor este ilizibil.')
        for row in rows:
            src, _, rest = row.partition(' on ')
            if re.search(r'(?<![A-Za-z0-9])' + re.escape(node) + r'(?![A-Za-z0-9])', src):
                raise ValueError('Nucleul indică o montare pe care diskutil nu o identifică.')
            if re.search(r'\b(?:ntfs|exfat)\b', rest.rpartition(' (')[2], re.I) and not re.search(r'\bdisk\d+s\d+\b', src):
                raise ValueError('Montare NTFS/exFAT cu sursă ambiguă. Proba se oprește.')
        return ''
    require(isinstance(path, str) and
            (d.get('Mounted') is bool(path) or (path and 'Mounted' not in d)),
            'Starea montării este ambiguă.')
    if path:
        require(os.path.dirname(path) == '/Volumes', 'Volumul este montat într-un loc nestandard.')
    return path


def verify(target, sample):
    d = identity(*target)
    path = mounted(d)
    require(path and info(path).get('DeviceIdentifier') == target[2], 'Punctul de montare diferă.')
    result = subprocess.run([sys.executable, '-IB', '-c', READ_SAMPLE, path, 'da' if sample else 'nu'],
                            capture_output=True, text=True, timeout=12)
    require(result.returncode == 0, 'Verificarea punctului de montare sau citirea a eșuat.')
    flags = result.stdout.split()
    require(flags and flags[0] in ('ro', 'rw'), 'Starea read-only este necunoscută.')
    readonly = flags[0] == 'ro'
    if readonly:
        require(d.get('WritableVolume') is not True and d.get('ReadOnlyVolume') is not False,
                'diskutil și statvfs indică stări de scriere diferite.')
    count = int(flags[1]) if len(flags) == 2 else 0
    require(0 <= count <= 4096, 'Răspuns de citire nevalid.')
    return path, readonly, count


def operation(*args):
    start = time.monotonic()
    # diskutil can wait about a minute for Disk Arbitration to answer a mount.
    timeout = 75 if args[0] == 'mount' else 40
    report('cerere', *args, f'termen={timeout}s')
    proc = subprocess.run([DISK, *args], capture_output=True, timeout=timeout, env=dict(os.environ, LC_ALL='C'))
    report('răspuns', args[0], args[-1], f'cod={proc.returncode}', f'durată={time.monotonic() - start:.1f}s')
    if args[0] == 'mount' and not proc.returncode and b'already mounted' in proc.stdout.lower():
        raise ValueError('Volumul era deja montat în timpul cererii; apartenența este incertă.')
    if proc.returncode:
        # Avoid exposing volume labels, paths or user file names.
        msg = (proc.stderr or proc.stdout).decode(errors='replace')
        code = re.search(r'(?<!\d)-\d{2,9}(?!\d)|0x[0-9a-f]{4,16}\b|(?<=error )\d{2,9}\b', msg, re.I)
        report('diskutil', 'cod suplimentar=' + (code[0] if code else 'indisponibil'))
    return proc.returncode


def report_timeout(exc):
    # A metadata lookup, kernel mount listing, or read sample can also expire.
    # Report the operation without printing UUIDs, usernames or mount paths.
    cmd = exc.cmd if isinstance(exc.cmd, (list, tuple)) else [exc.cmd]
    if cmd[0] == DISK and len(cmd) > 1:
        step = 'diskutil ' + cmd[1]
        if re.fullmatch(r'disk\d+(?:s\d+)?', cmd[-1]):
            step += ' ' + cmd[-1]
    elif cmd[0] == '/sbin/mount':
        step = 'citire tabel montări'
    elif cmd[0] == sys.executable and READ_SAMPLE in cmd:
        step = 'verificare mod și citire fișier'
    else:
        step = 'comandă externă'
    report(f'expirare în {step} după {exc.timeout}s')


def trial(targets, choice):
    order = KINDS if choice in ('inventar', 'ambele') else (choice,)
    created = []
    timed_out = False
    success = True
    verified = set()
    try:
        for fs in order:
            t = targets[fs]
            path = mounted(identity(*t))
            initial = bool(path)
            report(fs, t[2], 'fizic intern', 'inițial=' + ('montat' if initial else 'nemontat'))
            if not initial:
                if choice == 'inventar':
                    continue
                rc = operation('mount', 'readOnly', t[2])
                path = mounted(identity(*t))
                if rc:
                    require(not path, fs + ': după refuz există o montare cu proprietar incert; probă oprită.')
                    success = False
                    report(fs, 'montare refuzată')
                    continue
                require(path, fs + ': diskutil a raportat succes, dar nu există un punct verificabil.')
                created.append((t, path))
            _, ro, count = verify(t, choice != 'inventar')
            report(fs, 'stare=' + ('read-only' if ro else 'read-write'),
                   ('citire=' + str(count) + ' octeți' if count else 'citire fișier neconfirmată')
                   if choice != 'inventar' else 'inventar')
            if ro:
                verified.add(fs)
            if choice != 'inventar' and not (ro and count):
                success = False
        if choice == 'ambele' and verified == set(KINDS):
            for fs in KINDS:
                require(verify(targets[fs], False)[1], fs + ': starea read-only s-a schimbat.')
            report('ambele confirmate montate read-only în aceeași fază')
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        success = False
        report_timeout(exc)
        report('Starea ultimei cereri este incertă. Rulează din nou numai inventarul.')
    except (OSError, ValueError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
        success = False
        report('oprit:', str(exc))
    finally:
        if timed_out and created:
            report('montări anterioare ale probei de verificat:', ', '.join(t[1] for t, _ in created))
        for t, path in reversed(created):
            if timed_out: break
            try:
                require(mounted(identity(*t)) == path and info(path).get('DeviceIdentifier') == t[2],
                        'Punctul sau identitatea s-a schimbat; retragere oprită.')
                require(operation('unmount', t[2]) == 0 and not mounted(identity(*t)),
                        'Demontarea normală nu a fost confirmată. Verifică inventarul.')
                report(t[1], 'demontare confirmată')
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                success = False
                report_timeout(exc)
                report(t[1], 'demontare expirată; starea este incertă. Verifică inventarul.')
            except (OSError, ValueError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
                success = False
                report(t[1], str(exc))
    return 0 if success else 3


def fstab_options(text, volumes):
    rows = [line.partition('#')[0].split() for line in text.splitlines()]
    uuid = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', re.I)
    for fs in KINDS:
        matches = [r for r in rows if r and r[0].upper() == 'UUID=' + volumes[fs].upper()]
        options = [uuid.sub('[UUID]', r[3]) if len(r) >= 4 else '[regulă incompletă]' for r in matches]
        report(fs, 'fstab', 'reguli=' + str(len(matches)), 'opțiuni=' + (' | '.join(options) or 'absente'))


def cache_status(lib, root=FILESYSTEM_ROOT):
    try:
        header = lib._dyld_get_image_header
        header.argtypes = [ctypes.c_uint32]
        header.restype = ctypes.POINTER(ctypes.c_uint32)
        main = header(0)
        if not main or main[0] != 0xfeedfacf or main[1] != 0x01000007:
            report('cache Intel neverificat: imaginea principală nu este x86_64.')
            return
        contains = lib._dyld_shared_cache_contains_path
        contains.argtypes = [ctypes.c_char_p]
        contains.restype = ctypes.c_bool
    except AttributeError:
        report('cache Intel neverificat: API dyld indisponibil.')
        return
    for fs in KINDS:
        name = fs.lower()
        path = root / (name + '.fs') / 'Contents/Resources' / ('livefiles_' + name + '.dylib')
        report(fs, 'cache dyld x86_64', str(path),
               'prezent' if contains(os.fsencode(path)) else 'absent')


def components(volumes):
    try:
        fstab_options(Path('/etc/fstab').read_text(), volumes)
    except (OSError, UnicodeError) as error:
        report('fstab indisponibil:', type(error).__name__)
    for fs in KINDS:
        p = FILESYSTEM_ROOT / (fs.lower() + '.fs') / 'Contents/Info.plist'
        try:
            bundle = plistlib.loads(p.read_bytes())
            report(fs, 'FSImplementation=' + json.dumps(bundle.get('FSImplementation'), ensure_ascii=False))
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            report(fs, 'Info.plist indisponibil:', type(error).__name__)
    try:
        bundle = plistlib.loads((EXFAT_EXTENSION / 'Info.plist').read_bytes())
        exe = bundle.get('CFBundleExecutable', '')
        present = bool(exe and Path(exe).name == exe and
                       os.access(EXFAT_EXTENSION / 'MacOS' / exe, os.X_OK))
        report('exFAT FSKit', 'id=' + str(bundle.get('CFBundleIdentifier')),
               'extensie=' + str(bundle.get('EXAppExtensionAttributes', {}).get('EXExtensionPointIdentifier')),
               'executabil=' + str(exe), 'prezent/executabil' if present else 'indisponibil')
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        report('exFAT FSKit indisponibil:', type(error).__name__)
    cache_status(ctypes.CDLL(None))
    return 0


def after_boot(volumes):
    # Observe both volumes as found. This path submits no mount or unmount requests.
    boot = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.boottime'], text=True, timeout=5).strip()
    report('ultima pornire', boot)
    fstab_options(Path('/etc/fstab').read_text(), volumes)
    targets = discover(volumes, KINDS)
    complete = True
    for fs, target in targets.items():
        if not mounted(identity(*target)):
            report(fs, target[2], 'nemontat la verificarea după login')
            complete = False
            continue
        _, readonly, count = verify(target, True)
        report(fs, target[2], 'montat', 'read-only' if readonly else 'read-write', f'citire={count} octeți')
        complete &= readonly and count > 0
    return 0 if complete else 3


def boot_journal(volumes):
    clock = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.boottime'], text=True, timeout=5)
    fields = re.search(r'\bsec\s*=\s*(\d+),\s*usec\s*=\s*(\d+)', clock)
    require(fields is not None, 'Ora pornirii nu poate fi citită.')
    sec, usec = map(int, fields.groups())
    boot_ns = sec * 10**9 + usec * 1000
    fstab = Path('/etc/fstab')
    before = fstab.stat()
    rules = fstab.read_text()
    after = fstab.stat()
    require((before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns), 'fstab s-a schimbat în timpul citirii.')
    offset = (after.st_mtime_ns - boot_ns) / 1e9
    report('ceas MacBook | pornire', datetime.fromtimestamp(sec).astimezone().isoformat(),
           '| modificare fstab', datetime.fromtimestamp(after.st_mtime).astimezone().isoformat(timespec='milliseconds'),
           f'| modificare față de pornire {offset:+.3f} s')
    fstab_options(rules, volumes)
    # Discover on the running machine. A format-only message cannot identify a physical volume.
    devices = {}
    try:
        devices = {fs: target[2] for fs, target in discover(volumes, KINDS).items()}
    except (OSError, ValueError, subprocess.SubprocessError, plistlib.InvalidFileException):
        report('identități fizice indisponibile; mesajele se citesc pe format sau serviciu')
    end = min(int(time.time()), sec + 20 * 60)
    args = ['/usr/bin/log', 'show', '--style', 'ndjson', '--info', '--debug',
            '--start', datetime.fromtimestamp(sec).strftime('%Y-%m-%d %H:%M:%S'),
            '--end', datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M:%S')]
    services = ('process IN {"diskarbitrationd","fskitd","livefs","mount_ntfs","mount_exfat"} '
                'OR process CONTAINS[c] "fskit" OR process CONTAINS[c] "livefiles" '
                'OR subsystem CONTAINS[c] "fskit" OR subsystem CONTAINS[c] "DiskArbitration"')
    needles = ['ntfs','exfat','mount','probe','timed out','timeout','noauto',*devices.values()]
    messages = ' OR '.join('eventMessage CONTAINS[c] ' + json.dumps(t) for t in needles)
    report('jurnal de la pornire', f'{end-sec} s', 'pe ceasul MacBook-ului')
    try:
        result = subprocess.run(args + ['--predicate', '(' + services + ') AND (' + messages + ')'],
                                capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        report('Citirea jurnalului a expirat după 60 s.')
        return 3
    if result.returncode:
        report('jurnal indisponibil', 'cod=' + str(result.returncode),
               result.stderr.decode(errors='replace').strip()[:240])
        return 3
    groups = {}
    boot_uuid = subprocess.run(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'],
                               capture_output=True, text=True, timeout=5).stdout.strip().upper()
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(row, dict) or not isinstance(row.get('eventMessage'), str):
            continue
        if boot_uuid and row.get('bootUUID') and str(row['bootUUID']).upper() != boot_uuid:
            continue
        msg = row['eventMessage']
        proc = Path(str(row.get('processImagePath') or row.get('process') or '?')).name
        text = (proc + ' ' + msg).lower()
        labels = [fs + ' ' + dev for fs, dev in devices.items()
                  if re.search(r'(?<![a-z0-9])r?' + re.escape(dev) + r'(?![a-z0-9])', msg.lower())]
        labels = labels or [fs + ' (format)' for fs in KINDS if fs.lower() in text]
        if not labels and not re.search(r'fail|error|timed? ?out|noauto|skipp|denied|dissent', msg, re.I):
            continue
        key = ', '.join(labels) if labels else 'serviciu, volum neidentificat'
        msg = re.sub(r'/Volumes/[^,;\n]+', '/Volumes/[volum]', msg)
        msg = re.sub(r'\b[\da-fA-F]{8}(?:-[\da-fA-F]{4}){3}-[\da-fA-F]{12}\b', '[UUID]', msg)
        when = str(row.get('timestamp', '?'))
        groups.setdefault(key, []).append((when, proc, ' '.join(msg.split())[:320]))
    for key, entries in groups.items():
        report(key, 'mesaje=' + str(len(entries)))
        keep = entries if len(entries) <= 24 else entries[:12] + entries[-12:]
        for when, proc, message in keep:
            report(key, '|', when, proc, '|', message)
    if not groups:
        report('Niciun eveniment relevant disponibil în această fereastră de jurnal.')
    return 0


def remote(choice, volumes):
    try:
        if choice == 'componente':
            return components(volumes)
        if choice == 'jurnal-boot':
            return boot_journal(volumes)
        if choice == 'dupa-boot':
            return after_boot(volumes)
        # Serialize this probe across SSH sessions using the existing executable
        # inode. The descriptor stays read-only and the lock dies with the process.
        with open(sys.executable, 'rb') as lock:
            if choice != 'inventar':
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('O altă probă de montare este deja activă.')
            selected = KINDS if choice in ('inventar', 'ambele') else (choice,)
            return trial(discover(volumes, selected), choice)
    except subprocess.TimeoutExpired as exc:
        report_timeout(exc)
        report('inventarul a expirat înainte de proba de montare')
    except (OSError, ValueError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
        report('inventar incomplet:', str(exc))
    return 3


def remote_script(source, gate, mode, volumes):
    # The account/build/APFS guard runs with its own bounded timeout.
    code = ("import subprocess,sys;sys.exit(subprocess.run(['/bin/bash','-c',"
            + repr(gate) + "],timeout=20).returncode)")
    cmd = '/usr/local/lib/hao/python/bin/python3.12'
    python = ['/usr/bin/arch', '-x86_64', cmd] if mode == 'componente' else [cmd]
    return (shlex.join([cmd, '-IB', '-c', code]) + ' || exit 2\nexec ' +
            shlex.join(python + ['-IBu', '-', mode, json.dumps(volumes)]) +
            " <<'GG_PROBE_RO'\n" + source + '\nGG_PROBE_RO\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--monteaza-ro', choices=('ntfs', 'exfat', 'ambele'),
                         help='Montează temporar numai pentru citire. Implicit doar inventar.')
    actions.add_argument('--componente', action='store_true', help='Citește fstab, modulele și catalogul dyld Intel.')
    actions.add_argument('--dupa-boot', action='store_true', help='După login: citește starea și probează citirea fișierelor deja montate.')
    actions.add_argument('--jurnal-boot', action='store_true', help='Compară fstab cu ora pornirii pe B și citește jurnalul Disk Arbitration/FSKit.')
    args = parser.parse_args()
    mode = {None: 'inventar', 'ntfs': 'NTFS', 'exfat': 'exFAT', 'ambele': 'ambele'}[args.monteaza_ro]
    if args.componente:
        mode = 'componente'
    if args.dupa_boot:
        mode = 'dupa-boot'
    if args.jurnal_boot:
        mode = 'jurnal-boot'
    here = Path(__file__).resolve()
    diag = here.parents[1] / 'diagnostics'
    prep = runpy.run_path(str(diag/'GoldenGate-Pregateste-B.command'))
    source = prep['RECEIPT'].read_bytes()
    plan = runpy.run_path(str(here.with_name('bon_volume_b.py')))
    plan['requested_rules'](source, 'revenire')
    volumes = json.loads(source)['noauto']
    volumes = {fs: v.upper() for fs, v in volumes.items()}
    require(volumes == prep['WANTED'], 'Bonul și identitățile verificate ale lui B diferă.')
    gate = runpy.run_path(str(diag/'GoldenGate-Finder-B.command'))['GATE']
    client = runpy.run_path(str(diag/'GoldenGate-Test-Cache-A-pe-B.command'))
    payload = remote_script(here.read_text(), gate, mode, volumes)
    os.umask(0o077)
    folder = Path(tempfile.mkdtemp(prefix='Golden-B-Proba-Volume-' + datetime.now().strftime('%Y%m%d-%H%M%S-'),
                                   dir=here.parents[3] / 'outputs'))
    report_path = folder / 'raport.txt'
    print('Raport pe iMac:', report_path, flush=True)
    with tempfile.TemporaryFile() as request, report_path.open('xb') as saved:
        request.write(payload.encode())
        request.seek(0)
        saved.write(f'Început iMac {datetime.now().astimezone().isoformat(timespec="seconds")} mod={mode}\n'.encode())
        with subprocess.Popen(client['SSH'] + ['-T', client['HOST'], '/bin/bash -s'], stdin=request,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as session:
            for line in session.stdout:
                saved.write(line)
                saved.flush()
                print(line.decode(errors='replace'), end='', flush=True)
            code = session.wait()
        end = f'Cod de ieșire: {code}\n'
        saved.write(end.encode())
        print(end, end='', flush=True)
        return code


if __name__ == '__main__':
    if __file__ == '<stdin>':
        sys.exit(remote(sys.argv[1], json.loads(sys.argv[2])))
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit('Oprit: ' + str(error))
