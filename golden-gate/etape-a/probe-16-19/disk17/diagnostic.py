#!/usr/bin/env python3
"""Observator offline pentru SSD-ul Golden Gate 26B131 pe MacBookPro9,1."""
import argparse
import contextlib
import hashlib
import json
import os
import plistlib
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from target import (CONTAINER_UUID, DATA_UUID, EXPECTED_BUILD, PARTITION_UUID, SYSTEM_UUID,
                    device, identify_volumes, is_x86_64, safe_path, uuid_value)

BUNDLE = 'Library/Application Support/HAO-DiskDiag17'
LOG = 'private/var/log/hao-diskdiag17'
LABEL = 'org.goldengate.hao-diskimages17'
JOB = 'Library/LaunchDaemons/' + LABEL + '.plist'
PROGRAM = '/' + BUNDLE + '/bin/hao-observer'
DISKUTIL = '/usr/sbin/diskutil'
HERE = Path(__file__).resolve().parent


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


def sha(body):
    return hashlib.sha256(body).hexdigest()


def secure_dir(root, rel, mode=0o755):
    parent = root
    for part in Path(rel).parts:
        require(part not in ('.', '..', '/'), 'Director invalid.')
        parent = parent / part
        try:
            parent.mkdir(mode=mode if parent == root / rel else 0o755)
        except FileExistsError:
            pass
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_dev == root.stat().st_dev,
                f'Director nesigur: {parent}')
    return parent


def read_owned(root, rel):
    try:
        path = safe_path(root, rel)
    except FileNotFoundError:
        return None
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 8*1024*1024,
            'Fișier neașteptat: ' + rel)
    return path.read_bytes()


def atomic(root, rel, body, mode):
    dest = root / rel
    parent = secure_dir(root, str(Path(rel).parent))
    read_owned(root, rel)
    with tempfile.NamedTemporaryFile(dir=parent, prefix='.hao17-', delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(body)
            f.flush()
            os.fchown(f.fileno(), 0, 0)
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink()
            raise
    try:
        os.replace(tmp, dest)
        s = dest.stat()
        require(s.st_uid == 0 and s.st_gid == 0 and stat.S_IMODE(s.st_mode) == mode and
                read_owned(root, rel) == body, 'Verificarea scrierii a eșuat: ' + rel)
    finally:
        tmp.unlink(missing_ok=True)


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
    temp = Path(tempfile.mkdtemp(prefix='hao17-mnt-')).resolve()
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



def plist_data():
    return plistlib.dumps({'Label':LABEL,'ProgramArguments':[PROGRAM], 'RunAtLoad':True,
            'StandardOutPath':'/'+LOG+'/launchd-out.log','StandardErrorPath':'/'+LOG+'/launchd-err.log',
            'UserName':'root','GroupName':'wheel','KeepAlive':False}, sort_keys=True)


def installation_files():
    files = {JOB:(plist_data(),0o644)}
    for name, digest in {'hao-observer': 'dcd8b3cb21549e9dedff11660765e1264d32d2e722137468b17f2ef2c80ca458', 'media-watch': 'c7e6ff5bb5159ea2a59c3efd14e876fcd60e7c09a43babd8e994f64f3286a2e3'}.items():
        local = HERE / name
        body = local.read_bytes()
        require(is_x86_64(body) and sha(body) == digest,'Binar diferit de versiunea verificată: '+name)
        run(['/usr/bin/codesign','--verify','--strict',local])
        files[BUNDLE+'/bin/'+name] = (body,0o755)
    for tool, path in [('sample','/usr/bin/sample'),('ioreg','/usr/sbin/ioreg'),('launchctl','/bin/launchctl')]:
        source = Path(path)
        st = source.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and not (st.st_mode & 0o022)
                and st.st_size <= 8*1024*1024, 'Utilitar de sistem neașteptat: '+path)
        binary = source.read_bytes()
        require(is_x86_64(binary), 'Utilitarul Tahoe nu conține x86_64: '+path)
        files[BUNDLE+'/bin/'+tool] = (binary,0o755)
    return files


RECEIPT = BUNDLE+'/receipt.json'
ALLOWED = {BUNDLE+'/bin/'+t for t in ('sample','ioreg','launchctl','hao-observer','media-watch')} | {JOB}


def receipt(root):
    raw = read_owned(root, RECEIPT)
    if raw is None:
        return None
    r = json.loads(raw)
    require(r.get('data') == DATA_UUID and r.get('label') == LABEL and set(r['files']) == ALLOWED and
            all(re.fullmatch('[0-9a-f]{64}', s) for s in r['files'].values()), 'Receipt invalid.')
    return r


def install(root):
    files = installation_files()
    old = receipt(root)
    signatures = {rel:sha(body) for rel,(body,_mode) in files.items()}
    for rel in files:
        found = read_owned(root,rel)
        require(found is None or sha(found) in (signatures[rel],(old or {}).get('files',{}).get(rel)),
                'Fișier existent nerecunoscut: '+rel)
    logs = secure_dir(root, LOG, 0o700)
    os.chown(logs,0,0); os.chmod(logs,0o700)
    for name in ('launchd-out.log','launchd-err.log'):
        read_owned(root, LOG+'/'+name)
    secure_dir(root, BUNDLE)
    manifest = {'label':LABEL,'data':DATA_UUID,'files':signatures}
    atomic(root,RECEIPT,json.dumps(manifest,sort_keys=True).encode(),0o600)
    for rel, (body, mode) in files.items():
        if rel != JOB: atomic(root, rel, body, mode)
    atomic(root, JOB, *files[JOB])
    check = plistlib.loads(read_owned(root,JOB))
    require(check['ProgramArguments']==[PROGRAM] and check['RunAtLoad'], 'Plist incorect.')
    print('Observator instalat și verificat. Pornește SSD-ul Golden Gate pe MacBook și lasă-l 6 minute după apariția barei. Revino în Tahoe și deschide din nou GoldenGate.command.')


def remove(root):
    old = receipt(root)
    found = read_owned(root,JOB)
    require(not found or (old and sha(found)==old['files'][JOB]), 'Plist modificat; îl păstrez.')
    if found is not None:
        safe_path(root, JOB).unlink()
    if old:
        for rel, sig in old['files'].items():
            if rel==JOB: continue
            current = read_owned(root,rel)
            if current is not None and sha(current)==sig: safe_path(root,rel).unlink()
        # Keep evidence and version hashes to support audit and reinstallation.
    print('Observator retras. Capturile deja făcute rămân pe SSD.')


def collect(root, out_dir, uid, gid):
    def assess(body):
        text=body.decode('utf-8','replace')
        return 'Analysis of sampling' in text and ('Call graph:' in text or 'Call graph' in text)
    fd, filename = tempfile.mkstemp(prefix='GoldenGate-9_1-DiskImages2-',suffix='.zip',dir=out_dir)
    os.close(fd)
    zip_path=Path(filename)
    try:
        count = valid = size = 0
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            try:
                base=safe_path(root,LOG)
            except FileNotFoundError:
                base=None
            if base:
                for directory, dirs, names in os.walk(base, followlinks=False):
                    d=Path(directory)
                    dirs[:]=[n for n in dirs if not (d/n).is_symlink() and (d/n).stat().st_dev==base.stat().st_dev]
                    for n in names:
                        try:
                            p=safe_path(root,str((d/n).relative_to(root)))
                            s=p.lstat()
                        except (ValueError, OSError):
                            continue
                        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>48*1024*1024 or size+s.st_size>192*1024*1024: continue
                        body=p.read_bytes()
                        z.writestr('probe/'+str(p.relative_to(base)),body)
                        size+=len(body)
                        if n=='STARTED.txt' and body: count+=1
                        if n.endswith('-sample.txt') and assess(body): valid+=1
            z.writestr('rezultat.txt',f'Porniri observate: {count}\nStive DiskImages cu antet și call graph: {valid}\n')
        os.chown(zip_path,uid,gid)
        print(f'Porniri observate: {count}. Stive lizibile: {valid}.\nArhivă: {zip_path}')
        if not valid: print('Nu s-au găsit stive lizibile. Arhiva include indiciile disponibile despre lansare. Observatorul rămâne instalat.')
        return 0 if valid else 3
    except BaseException:
        zip_path.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',nargs='?',default='auto',choices=['auto','install','collect','remove']); action=parser.parse_args().action
    require(sys.platform=='darwin' and os.geteuid()==0,'Rulează GoldenGate.command din Tahoe.'); uid=int(os.environ.get('SUDO_UID','0'))
    require(uid>0,'Deschide GoldenGate.command din contul tău obișnuit.'); user=pwd.getpwuid(uid)
    require(run(['/usr/bin/sw_vers','-productVersion']).decode().strip().startswith('26.'),'Pornește în Tahoe.'); os.umask(0o077)
    target, whole=resolve(); print(f'SSD extern identificat: {whole}. Golden Gate 26B131.',flush=True)
    system=target['volumes']['System']['device']; data=target['volumes']['Data']['device']
    with mount(system,SYSTEM_UUID) as root:
        ver=plistlib.loads(safe_path(root,'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        require(ver.get('ProductBuildVersion')==EXPECTED_BUILD,'Build Golden Gate diferit.')
    if action in ('auto','collect'):
        with mount(data,DATA_UUID) as root:
            if action=='collect' or (receipt(root) and read_owned(root,JOB) is not None):
                return collect(root,Path(user.pw_dir)/'Desktop',uid,user.pw_gid)
        action='install'
    with mount(data,DATA_UUID,writable=True,owners=True) as root:
        if action=='install': install(root)
        else: remove(root)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print('Oprit: '+str(exc), file=sys.stderr); sys.exit(1)
