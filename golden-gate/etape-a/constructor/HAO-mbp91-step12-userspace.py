#!/usr/bin/env python3
"""Golden Gate / MacBookPro9,1: stage verified local inputs and attempt a raw image.

Run as the ordinary user on the Intel build Mac:
    python3.14 -I HAO-mbp91-step12-userspace.py

Default mode 'build' prepares a local Intel kit, then assembles a NEW raw image.
'prepare' stops after the verified kit; 'assemble' reuses a verified prior kit.
There is no physical-disk target argument. No downloads are performed.

The bootstrap is experimental: external Hao interfaces, thunks and async
provider are absent. An assembled image is not full compatibility or a boot
test. Original row hashes are preserved; local variants have their own rows.
The final image links its own collections and runs Hao's actual KC binder.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import math
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import runpy
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time
import traceback
import tarfile
import zipfile

PIN = '6bd75aab112d1078acd8e75180eb510672461365'
VERSION = 'step12-local-intel-image-v1'
MODEL, BOARD = 'MacBookPro9,1', 'Mac-4B7AC7E43945597E'
GOLDEN, DONOR = '26B131', '25G342'
ARCHIVE_NAME = 'HAO-mbp91-step12-userspace.zip'
HEX = re.compile(r'^[0-9a-f]{64}$')
ROW_NAME = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$')
INPUTS_SHA = '92a370bdad712ea081b83ca61f21f0ae0f4937a2440b3ffeb572b60e863025d9'
FL_C_SHA = '94372cc0ab331c766f3bbaefb308a22a793d137e5f993208aa2c9cc1523d788c'
FL_ENT_SHA = '0e9552e2ab1a0283c2f7f2a04137d6b1c0dc8f40d3c9f0146ab35ecd51b992fa'
FL_LAYOUT_SHA = 'd1ea37335bb01c9c6dcc8db5e32537aeb2f793cfd52816d01da3447955ab6ef9'
OCLP_TREE = '77b788410c4d5d73029d1c3845305eecd8d169eb'
KDK_SHA = '219f27c7e039b6ab3426496e0d5852d55a31d00b3d3984d855cba04377c5dba0'
PYTHON_SHA = '0d6a4a299908123f00bc844df737603f047ff9eba14fda6cad83f3cf3cb3a2af'
DETECT_RULES = 'tools/hao/data/detect-rules.json'
DETECT_RULES_SHA = '6dcde9ee78d82beb9fee370fc7310ebe310c4fe6a863254181afa416ad055c58'
METAL_ROWS = ('metallib_repairs_golden_gate','metal_quad_runtime_golden_gate','hello_metallib_golden_gate')
AUX_ROWS = ('display_state_shim','io80211_compat','wifip2p_compat','corewifi_compat',
            'windowserver_filter_shim','corespotlight_compat_shim','hd4000_planes','libhelloblur',
            'metalold_selectors','metal_framebuffer','metal_argbuf','codeid_carrier',
            'metal_compiler_compat','live_text_framework')
KERNEL_ROWS = ('intel_commpage_abi','kernel_repair_efi','kernel_repair_binding')
BASE_ROLES = ('native','extensions','boot','driverkit','recovery','hardware')
HELPERS = ('golden-image.py','golden-layout.py','golden-pristine.sh','golden-workspace.py',
           'recovery-tools.py','copy-hooks.py','golden-assemble.sh')
SOURCE_PATHS = ('pipeline/lock.py','pipeline/patches.py','pipeline/golden-run','pipeline/kit.py',
                'pipeline/prelinked_kc.py','pipeline/diskguard.py','pipeline/release-classes.json',
                'pipeline/order.txt','pipeline/stages/inputs.sh','pipeline/stages/weaken-dylibs.py',
                'pipeline/unpack/pristine-tools/fl.c','pipeline/unpack/pristine-tools/ent.plist',
                'tools/tahoe-donors','tools/kc-binder','tools/audiomxd-fix','tools/metal-fixes',
                'tools/hao','tools/hao-contract')
SCOPE = dict(experimental_bootstrap=True, external_hao_abi_payload_complete=False,
             compatibility_complete=False, boot_validated=False,
             kepler_rendering_validated=False, gmux_switching_validated=False)

class Stop(RuntimeError):
    pass


def space_gb(byte_count, digits=2):
    """Romanian display only; keep all byte counts and arithmetic unchanged."""
    number=f'{byte_count/1_000_000_000:.{digits}f}'
    if '.' in number:number=number.rstrip('0').rstrip('.')
    return number.replace('.',',')+' GB'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

def load(p):
    v=json.loads(Path(p).read_text())
    if not isinstance(v,dict): raise Stop('Obiect JSON asteptat: '+str(p))
    return v

def save(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+'.tmp-'+str(os.getpid()))
    t.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n'); os.replace(t,p)

def relpath(s):
    p=PurePosixPath(str(s))
    if not p.parts or p.is_absolute() or '..' in p.parts or '\\' in str(s) or '\0' in str(s):
        raise Stop('Cale relativa invalida: '+str(s))
    return Path(*p.parts)

def inside(root,s):
    root=Path(root).resolve(); p=root/relpath(s)
    if not p.resolve().is_relative_to(root): raise Stop('Cale externa refuzata: '+str(p))
    return p

def blob(p):
    b=Path(p).read_bytes(); return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def fingerprint(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def tree_files(root):
    """Content manifest, including links; never traverse symlink directories."""
    root=Path(root); out={}
    if root.is_symlink(): raise Stop('Radacina manifestului este symlink')
    for parent,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(set(dirs+files)):
            p=Path(parent)/name; r=p.relative_to(root).as_posix(); st=p.lstat()
            if stat.S_ISLNK(st.st_mode): out[r]={'link':os.readlink(p)}
            elif stat.S_ISREG(st.st_mode): out[r]={'sha256':sha(p),'bytes':st.st_size}
            elif not stat.S_ISDIR(st.st_mode): raise Stop('Fisier special: '+str(p))
        dirs[:]=sorted(d for d in dirs if not (Path(parent)/d).is_symlink())
    return out

def validate_files(root, manifest):
    if tree_files(root)!=manifest: raise Stop('Continutul artefactului a fost schimbat: '+str(root))

def macho_slices(path):
    """Return CPU type/subtype pairs after bounded thin/FAT header validation."""
    p=Path(path); size=p.stat().st_size
    with p.open('rb') as f: b=f.read(min(size,4096))
    if len(b)<8: raise Stop('Mach-O trunchiat: '+str(p))
    be=struct.unpack_from('>I',b)[0]
    if be in (0xcafebabe,0xcafebabf):
        n=struct.unpack_from('>I',b,4)[0]; width=32 if be==0xcafebabf else 20
        if not 0<n<=32 or 8+n*width>len(b): raise Stop('Tabel FAT invalid')
        out=[]
        for i in range(n):
            at=8+i*width; cpu,sub=struct.unpack_from('>II',b,at)
            off,num=struct.unpack_from('>QQ' if width==32 else '>II',b,at+8)
            if num<28 or off<8+n*width or off+num>size: raise Stop('Slice FAT invalid')
            with p.open('rb') as f: f.seek(off); header=f.read(12)
            if len(header)<12 or struct.unpack_from('<I',header)[0] not in (0xfeedface,0xfeedfacf):
                raise Stop('Slice FAT fara antet Mach-O')
            if struct.unpack_from('<II',header,4)!=(cpu,sub): raise Stop('Identitate FAT neconcordanta')
            out.append((cpu,sub & 0xffffff))
        return out
    if struct.unpack_from('<I',b)[0] not in (0xfeedfacf,0xfeedface) or len(b)<28:
        raise Stop('Nu este Mach-O: '+str(p))
    return [(struct.unpack_from('<I',b,4)[0],struct.unpack_from('<I',b,8)[0]&0xffffff)]


def parse_row(text, repo, name):
    """Keep comments (especially hash scopes and contract checks) separate from data."""
    if not ROW_NAME.fullmatch(name):
        raise Stop('Nume de intrare invalid: '+name)
    data = [line.split('#',1)[0].split() for line in text.splitlines()
            if not line.lstrip().startswith('#')]
    data = [line for line in data if line]
    if len(data)!=1 or len(data[0])!=2:
        raise Stop('Intrare ambigua: '+name)
    checksum, value = data[0]
    if checksum!='-' and not HEX.fullmatch(checksum):
        raise Stop('SHA256 invalid: '+name)
    p = Path(value).expanduser()
    p = p if p.is_absolute() else Path(repo)/relpath(value)
    # All inputs of this local project must remain inside the supplied workspace.
    if not p.resolve().is_relative_to(Path(repo).resolve()):
        raise Stop('Intrare externa workspace-ului: '+name)
    if any(c.isspace() for c in str(p)):
        raise Stop('Formatul Hao pentru intrari nu accepta spatii in cale: '+str(p))
    comments = [line for line in text.splitlines() if line.lstrip().startswith('#')]
    return checksum,p,'\n'.join(comments)

def row_text(checksum, path, comments=''):
    if not HEX.fullmatch(checksum):
        raise Stop('Intrarea locala trebuie sa aiba un SHA256 concret')
    return (comments+'\n' if comments else '')+checksum+' '+str(path)+'\n'

def patched_stager(source):
    changes = [
        ('HERE=${0:A:h}; TOP=${HERE:h:h}; L=(python3 -I $TOP/pipeline/lock.py)',
         'HERE=${HAO_STEP12_STAGES:?}; TOP=${HERE:h:h}; L=(python3 -I $TOP/pipeline/lock.py)'),
        ('for arch dir in arm64 py x86_64 py-x86_64; do',
         'for arch dir in x86_64 py-x86_64; do'),
        ('KDK=$($L kdk-name $KDKDMG); K=$CACHE/kdk-${${KDK:r}##*_}',
         'KDK=$($L kdk-name $KDKDMG); K=${HAO_STEP12_KDK_ROOT:?}')
    ]
    for before,after in changes:
        if source.count(before)!=1:
            raise Stop('Forma constructorului inputs.sh s-a schimbat')
        source=source.replace(before,after)
    return source,[{'before':a,'after':b} for a,b in changes]

def assert_prior_result(report, number):
    if report.get('patcher_commit', report.get('upstream_commit'))!=PIN or report.get('model')!=MODEL:
        raise Stop('Identitate neasteptata in raportul pasului '+str(number))
    if report.get('errors') or report.get('error'):
        raise Stop('Pasul '+str(number)+' contine erori')
    if number==4:
        if not report.get('base_efi_built') or not report.get('ocvalidate_ok'):
            raise Stop('EFI de baza nu a fost validat')
    elif not report.get('step_complete'):
        raise Stop('Pasul '+str(number)+' nu este complet')

def required_plan(plan):
    hooks=('darwin27-kernel','golden-gate-userspace','golden-gate-wifi-compat','hao-runtime',
        'golden-gate-dyld-internal','golden-gate-launchd-warm','golden-gate-av1-encoder-x86',
        'golden-gate-metal-libraries','golden-gate-hello','golden-gate-windowserver-filter',
        'golden-gate-corespotlight-compat','metalold-selectors','golden-gate-metal-framebuffer',
        'golden-gate-metal-argbuf','golden-gate-hd4000-planes','metal-compiler-compat',
        'golden-gate-live-text-shared','golden-gate-native-identities')
    posts=('hao-opencore','golden-gate-live-text-service','hao-command')
    expected=[('oclp-hook',n) for n in hooks]+[('post',n) for n in posts]
    if [(stage,name) for stage,name,_ in plan]!=expected:
        raise Stop('Planul local difera de cele 18 hooks + 3 posts revizuite')
    return set(name for _,_,rows in plan for name in rows)

def mode_manifest(root, without=()):
    root=Path(root); out={}
    for directory,dirs,files in os.walk(root, followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in ('__pycache__',))
        for name in sorted(set(dirs+files)):
            p=Path(directory)/name; rel=p.relative_to(root).as_posix()
            if any(rel==x or rel.startswith(x.rstrip('/')+'/') for x in without):
                continue
            st=p.lstat(); entry={'mode':stat.S_IMODE(st.st_mode)}
            if stat.S_ISLNK(st.st_mode): entry['link']=os.readlink(p)
            elif stat.S_ISREG(st.st_mode): entry.update(sha256=sha(p),bytes=st.st_size)
            elif stat.S_ISDIR(st.st_mode): entry['directory']=True
            else: raise Stop('Fisier special in kit: '+str(p))
            out[rel]=entry
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()
                 and not any((Path(directory)/d).relative_to(root).as_posix()==x for x in without)]
    return out

def verify_kit_worker(plan_file):
    plan=load(plan_file); repo=Path(plan['repo']).resolve(); share=inside(repo,plan['kit'])
    L=runpy.run_path(str(repo/'pipeline/lock.py'))
    checked=[]
    for item in plan['rows']:
        folder=inside(repo,item['lock']); path=share/relpath(item['staged'])
        if not path.exists(): raise Stop('Lipseste din kit: '+item['staged'])
        got=L['row_hash'](str(folder),item['name'],str(path))
        if got!=item['sha256']: raise Stop('Integritate kit esuata: '+item['name'])
        problems=L['check_row'](str(folder),item['name'],str(path))
        if problems: raise Stop('; '.join(problems))
        checked.append({'name':item['name'],'staged':item['staged'],'sha256':got})
    manifest=mode_manifest(share, without=('step12-manifest.json','step12-build.json'))
    old=plan.get('expected_manifest')
    if old:
        expected=load(inside(repo,old))
        if manifest!=expected['files']:
            raise Stop('Kitul salvat a fost modificat; nu este reutilizat')
    output=inside(repo,plan['output'])
    save(output, {'schema':1,'files':manifest,'verified_rows':checked})
    print(json.dumps({'files':len(manifest),'row_copies':len(checked),'manifest_sha256':sha(output)}))


"""A host capability probe in a newly created disk image; no Golden layout claim."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import uuid


def group_probe_pair(layout, image, system_root, container, system, data):
    """Use Hao's pinned group primitive; Data stays unmounted during grouping."""
    before = layout['topology'](image, system_root, data)
    if before['container'] != container or before['system'] != system:
        raise RuntimeError('Probe container or System identity changed before grouping')
    volumes = before['volumes']
    if set(volumes) != {system, data} or volumes[system]['role'] != 'System' or volumes[data]['role'] != 'Data':
        raise RuntimeError('Grouping requires exactly the probe System/Data pair')
    if any(row['group'] for row in volumes.values()):
        raise RuntimeError('Probe volumes must be ungrouped before grouping')
    indices = []
    for device in (system, data):
        match = re.fullmatch(re.escape(container) + r's([0-9]+)', device)
        if not match or not 1 <= int(match[1]) <= 127:
            raise RuntimeError('Probe volume index is outside its verified container')
        indices.append(int(match[1]))
    expected = str(uuid.UUID(volumes[data]['uuid'])).upper()
    returned = layout['group_add'](container, indices)
    if returned != expected:
        raise RuntimeError('APFS grouping returned a UUID different from the probe Data volume')
    after = layout['topology'](image, system_root, data)
    wanted = json.loads(json.dumps(before))
    for row in wanted['volumes'].values():
        row['group'] = expected
    if after != wanted:
        raise RuntimeError('Probe group/volume readback differs from the expected Data UUID')
    return dict(method='Hao APFSContainerVolumeGroupAdd', group_uuid=expected,
                indices=indices, before=before, after=after)


def run_firmlink_probe(work: Path, fl: Path, layout_helper: Path) -> dict:
    """Require root/macOS; record and detach the new image on both success and failure.

    Grouping follows Hao's production golden-image.py and golden-layout.py;
    the entitled set/get test follows its recovery spike. The clear check compares
    with the same anchor's original no-firmlink state. No input image is used.
    """
    if sys.platform != 'darwin' or os.geteuid() != 0:
        raise RuntimeError('The firmlink probe requires a macOS root worker')
    work, fl = Path(work), Path(fl)
    if work.is_symlink() or fl.is_symlink():
        raise RuntimeError('Probe work and fl must not be symlinks')
    work, fl = work.resolve(strict=True), fl.resolve(strict=True)
    if work == Path('/') or not work.is_dir():
        raise RuntimeError('Probe work must be an existing private job directory')
    if not stat.S_ISREG(fl.stat().st_mode) or not os.access(fl, os.X_OK):
        raise RuntimeError('fl must be a regular executable')
    layout_helper = Path(layout_helper)
    if layout_helper.is_symlink() or sha(layout_helper) != FL_LAYOUT_SHA:
        raise RuntimeError('Hao APFS layout helper differs from the pinned source')
    layout = runpy.run_path(str(layout_helper))
    probe = Path(tempfile.mkdtemp(prefix='firmlink-probe-', dir=work))
    probe.chmod(0o755)  # The unprivileged caller must be able to read the retained diagnostic report.
    image = probe / 'probe.sparseimage'
    report = probe / 'probe-result.json'
    tool_sha = hashlib.sha256(fl.read_bytes()).hexdigest()
    result = dict(passed=False, image=str(image), report=str(report),
                  fl=str(fl), fl_sha256=tool_sha, commands=[], detached=False,
                  scope='Grouped scratch APFS firmlink set/get/clear metadata roundtrip only')
    failure = None

    def run(*args, check=True, timeout=90):
        args = list(map(str, args))
        row = dict(argv=args)
        result['commands'].append(row)
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except BaseException as error:
            row['error'] = str(error)
            raise
        row.update(returncode=p.returncode, stdout=p.stdout[-16384:], stderr=p.stderr[-16384:])
        if check and p.returncode:
            raise RuntimeError('%s returned %d: %s' % (args[0], p.returncode, (p.stderr or p.stdout)[-2000:]))
        return p

    def plist(*args, timeout=90):
        return plistlib.loads(run(*args, timeout=timeout).stdout.encode())

    def attachment(required=True):
        rows = [r for r in plist('/usr/bin/hdiutil', 'info', '-plist', timeout=15)['images']
                if Path(r['image-path']).resolve() == image]
        if not rows and not required:
            return None
        if len(rows) != 1 or not rows[0].get('writeable'):
            raise RuntimeError('Probe image is not attached writable exactly once')
        return rows[0]

    def bound():
        row = attachment()
        entities = {e.get('dev-entry', '').removeprefix('/dev/') for e in row['system-entities']}
        matches = [c for c in plist('/usr/sbin/diskutil', 'apfs', 'list', '-plist')['Containers']
                   if c['ContainerReference'] in entities and len(c['PhysicalStores']) == 1
                   and c['PhysicalStores'][0]['DeviceIdentifier'] in entities]
        if len(matches) != 1:
            raise RuntimeError('Cannot bind exactly one APFS container to the new image')
        info = matches[0]
        running = plist('/usr/sbin/diskutil', 'info', '-plist', '/')
        if info['ContainerReference'] == running.get('APFSContainerReference'):
            raise RuntimeError('Refusing the running APFS container')
        return info

    def add(name, role, *extra):
        before = bound()
        old = {v['DeviceIdentifier'] for v in before['Volumes']}
        run('/usr/sbin/diskutil', 'apfs', 'addVolume', before['ContainerReference'],
            'APFS', name, '-role', role, *extra, '-nomount')
        added = [v for v in bound()['Volumes'] if v['DeviceIdentifier'] not in old]
        expected = {'S': ['System'], 'D': ['Data']}[role]
        if len(added) != 1 or added[0].get('Roles') != expected:
            raise RuntimeError('APFS role creation did not produce exactly the requested volume')
        return added[0]['DeviceIdentifier']

    def mount(device, name):
        if device not in {v['DeviceIdentifier'] for v in bound()['Volumes']}:
            raise RuntimeError('Mount device is outside the probe image')
        folder = probe / name
        folder.mkdir(mode=0o755)
        run('/usr/sbin/diskutil', 'mount', '-mountOptions', 'nobrowse', '-mountPoint', folder, device)
        mounted = plist('/usr/sbin/diskutil', 'info', '-plist', device)
        if mounted.get('MountPoint') != str(folder) or mounted.get('APFSSnapshot'):
            raise RuntimeError('Unexpected probe mount point or snapshot')
        run('/usr/sbin/diskutil', 'enableOwnership', folder)
        return folder

    def get(anchor):
        p = run(fl, 'get', anchor, check=False)
        prefix = 'get %s ' % anchor
        if not p.stdout.startswith(prefix):
            raise RuntimeError('fl get did not return its expected output')
        match = re.fullmatch(r"rc=(-?\d+) errno=(\d+)\([^\n]*\) target='([^'\n]*)' op=(\d+) flags=(\d+)\n?", p.stdout[len(prefix):])
        if not match:
            raise RuntimeError('Unrecognized fl get result')
        rc, err, target, op, flags = match.groups()
        return dict(returncode=p.returncode, rc=int(rc), errno=int(err), target=target,
                    op=int(op), flags=int(flags))

    try:
        run('/usr/bin/codesign', '--verify', '--strict', '--verbose=2', fl)
        ent = plistlib.loads(run('/usr/bin/codesign', '-d', '--entitlements', ':-', fl).stdout.encode())
        if ent.get('com.apple.private.apfs.set-firmlink') is not True:
            raise RuntimeError('fl lacks the required APFS firmlink entitlement')
        run('/usr/bin/hdiutil', 'create', '-size', '3072m', '-type', 'SPARSE', '-layout', 'GPTSPUD',
            '-fs', 'APFS', '-volname', 'HAO-FL-Placeholder', image)
        plist('/usr/bin/hdiutil', 'attach', '-plist', '-nomount', '-nobrowse', '-readwrite', image)
        initial = bound()
        if len(initial['Volumes']) != 1:
            raise RuntimeError('New probe image must contain one placeholder volume')
        placeholder = initial['Volumes'][0]['DeviceIdentifier']
        if plist('/usr/sbin/diskutil', 'info', '-plist', placeholder).get('MountPoint'):
            run('/usr/sbin/diskutil', 'unmount', placeholder)
        system = add('HAO-FL-System', 'S')
        if placeholder not in {v['DeviceIdentifier'] for v in bound()['Volumes']}:
            raise RuntimeError('Placeholder no longer belongs to the probe image')
        run('/usr/sbin/diskutil', 'apfs', 'deleteVolume', placeholder)
        sysroot = mount(system, 'system')
        data = add('HAO-FL-Data', 'D')
        # Match the image builder: create Data first, then group the explicit pair.
        result['grouping'] = group_probe_pair(layout, image, sysroot,
                                             bound()['ContainerReference'], system, data)
        result['grouping_source_sha256'] = FL_LAYOUT_SHA
        infos = [plist('/usr/sbin/diskutil', 'info', '-plist', d) for d in (system, data)]
        groups = {i.get('APFSVolumeGroupID') for i in infos}
        if len(groups) != 1 or None in groups or not next(iter(groups)):
            raise RuntimeError('System and Data do not share one nonempty volume group')
        uuid.UUID(next(iter(groups)))
        grouped = bound()
        if {v['DeviceIdentifier']: v.get('Roles') for v in grouped['Volumes']} != {
                system: ['System'], data: ['Data']}:
            raise RuntimeError('Probe image no longer contains exactly the System/Data role pair')
        if any(i.get('APFSContainerReference') != grouped['ContainerReference'] for i in infos):
            raise RuntimeError('Grouped volumes no longer belong to the probe container')
        dataroot = mount(data, 'data')
        anchor = sysroot / 'HAOFirmlinkProbe'
        anchor.mkdir(mode=0o755)
        (dataroot / anchor.name).mkdir(mode=0o755)
        baseline = get(anchor)
        ordinary = (baseline['returncode'], baseline['rc'], baseline['errno'])
        if baseline['target'] or ordinary not in ((0, 0, 0), (1, -1, 93)):
            raise RuntimeError('Unexpected ordinary-directory baseline: %r' % baseline)
        run(fl, 'set', anchor, anchor.name)
        linked = get(anchor)
        if (linked['returncode'], linked['rc'], linked['errno'], linked['target']) != (0, 0, 0, anchor.name):
            raise RuntimeError('Firmlink target readback differs from the requested relative path')
        run(fl, 'clear', anchor)
        cleared = get(anchor)
        if cleared != baseline:
            raise RuntimeError('Firmlink clear did not restore the original no-link metadata')
        if hashlib.sha256(fl.read_bytes()).hexdigest() != tool_sha:
            raise RuntimeError('fl changed during the probe')
        result.update(group_uuid=next(iter(groups)), system_device=system, data_device=data,
                      before=baseline, linked=linked, cleared=cleared, roundtrip=True)
    except BaseException as error:
        failure = error
        result['error'] = str(error)
    finally:
        try:
            # Rebind each time; at most three 15s queries and two 30s detach calls.
            # Never detach a remembered bare disk number.
            for force in (False, True):
                attached = attachment(required=False)
                if attached is None:
                    result['detached'] = True
                    break
                whole = [e['dev-entry'] for e in attached['system-entities']
                         if e.get('content-hint') == 'GUID_partition_scheme'
                         and re.fullmatch(r'/dev/disk\d+', e.get('dev-entry', ''))]
                if len(whole) != 1:
                    raise RuntimeError('Cannot bind cleanup to one disk-image whole device')
                run('/usr/bin/hdiutil', 'detach', *(['-force'] if force else []), whole[0],
                    check=False, timeout=30)
            result['detached'] = attachment(required=False) is None
            if not result['detached']:
                raise RuntimeError('Probe image remains attached after bounded cleanup')
        except BaseException as error:
            result['cleanup_error'] = str(error)
            if failure is None:
                failure = error
        result['passed'] = failure is None and result.get('roundtrip', False) and result['detached']
        report.write_text(json.dumps(result, indent=2) + '\n')
        report.chmod(0o644)
    if failure is not None:
        raise RuntimeError('Firmlink probe failed; inspect %s: %s' % (report, failure)) from failure
    return result


"""Read-only checks of a local mbp91 Golden Gate image build; never proves boot."""
import hashlib
import json
import plistlib
import struct
from pathlib import Path, PurePosixPath

MODEL, BUILD, BOARD = 'MacBookPro9,1', '26B131', 'Mac-4B7AC7E43945597E'
LAYERS = ('layout', 'golden-system', 'group-volumes', 'golden-finalize', 'boot-and-esp',
          'hardware', 'recipes', 'snapshot', 'posts', 'efi-bundle')
GPU_IDS = frozenset(('com.apple.driver.AppleIntelHD4000Graphics',
    'com.apple.driver.AppleIntelFramebufferCapri', 'com.apple.GeForce',
    'com.apple.nvidia.driver.NVDAGK100Hal', 'com.apple.nvidia.driver.NVDAResman',
    'com.apple.nvidia.NVDAStartup', 'com.apple.driver.AppleGraphicsControl',
    'com.apple.driver.AppleMuxControl', 'com.apple.iokit.IOGraphicsFamily'))
REPAIR_COMMENTS = ('Initialize early VM range before reservation',
    'Pass early kernel-map reservation bounds in ascending order',
    'Preserve bootstrap physical-page aliases: code',
    'Preserve bootstrap physical-page aliases: registration')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fileset_ids(path):
    """Parse only bounded Mach-O load commands of a thin x86_64 kernel fileset."""
    path = Path(path)
    with path.open('rb') as stream:
        header = stream.read(32)
        require(len(header) == 32, 'Truncated kernel collection header')
        require(struct.unpack_from('<II', header) == (0xfeedfacf, 0x01000007), 'KC must be x86_64')
        kind, count, size = struct.unpack_from('<III', header, 12)
        require(kind == 12 and 0 < count <= 10000 and size <= 64 << 20
                and 32 + size <= path.stat().st_size, 'Invalid kernel fileset header')
        commands = stream.read(size)
    require(len(commands) == size, 'Truncated kernel load commands')
    at, ids = 0, []
    for _ in range(count):
        require(at + 8 <= size, 'Truncated KC load command')
        command, length = struct.unpack_from('<II', commands, at)
        require(length >= 8 and length % 8 == 0 and at + length <= size, 'Invalid KC command size')
        if command == 0x80000035:
            require(length >= 32, 'Truncated LC_FILESET_ENTRY')
            offset = struct.unpack_from('<I', commands, at + 24)[0]
            require(32 <= offset < length, 'Invalid fileset identifier offset')
            raw = commands[at + offset:at + length]
            require(b'\0' in raw, 'Unterminated fileset identifier')
            name = raw.split(b'\0', 1)[0].decode('utf-8')
            require(name and name not in ids, 'Empty or duplicate fileset identifier')
            ids.append(name)
        at += length
    require(at == size and ids, 'Invalid KC command extent or empty fileset')
    return ids


def validate_build_metadata(record, kitrecipe, expectedimagepath):
    """kitrecipe is the assembly recipe, not kit.json; check actual image and build.json."""
    image = Path(expectedimagepath)
    require(kitrecipe.get('target') == 'mbp91' and kitrecipe.get('golden_build') == BUILD,
            'Unexpected assembly target/build')
    require(record.get('unit') == 'pipeline' and record.get('operation') == 'golden-first-image'
            and record.get('status') == 'assembled', 'Image assembler did not finish')
    require('attached_device' in record and record['attached_device'] is None
            and not record.get('cleanup_errors') and not record.get('error'), 'Build did not detach cleanly')
    config = record['configuration']
    require('disk' not in config and Path(config['image']).resolve() == image.resolve(), 'Unexpected image target')
    require(config['size_bytes'] == kitrecipe['size_bytes'] and config['name'] == kitrecipe['name'],
            'Image configuration differs from selected recipe')
    require(config['environment'].get('HAO_TARGET_MODEL') == MODEL, 'Wrong model in assembly environment')
    actual = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    require(actual == record.get('configuration_sha256'), 'Build configuration digest differs')
    steps = record.get('steps', [])
    require([s['name'] for s in steps if s['name'] in LAYERS] == list(LAYERS)
            and all(s.get('complete') is True for s in steps), 'Incomplete or reordered assembly layers')
    for field, prefix in (('hooks', 'recipe '), ('posts', 'post ')):
        expected = [prefix + row['name'] for row in config[field]]
        require([s['name'] for s in steps if s['name'].startswith(prefix)] == expected,
                'Incomplete or reordered ' + field)
    require({'system', 'data', 'preboot', 'recovery', 'vm', 'esp'} <= set(record.get('volumes', {}))
            and record.get('group_uuid'), 'Missing APFS volume/group metadata')
    require(image.is_file() and not image.is_symlink() and image.stat().st_size == config['size_bytes'],
            'Output image missing, linked, or wrong size')
    return dict(image=str(image), image_built=True, boot_validated=False, group_uuid=record['group_uuid'])


def validate_final_efi(efi_root, manifest, base_config=None, *, boot_kc, system_kc, binding_report):
    """Read exported boot-efi/ or its payload/; manifests/reports/config arguments are parsed dictionaries."""
    root = Path(efi_root)
    root = root / 'payload' if (root / 'payload').is_dir() else root
    require(not root.is_symlink() and root.is_dir(), 'EFI payload is not a regular directory')
    require(manifest.get('schema') == 1 and manifest.get('kind') == 'hao-prepared-efi'
            and manifest.get('model') == MODEL and manifest.get('os_build') == BUILD
            and manifest.get('kernel_repairs_applied') is True, 'Unexpected final EFI manifest/scope')
    expected = manifest.get('files', {})
    require(expected and all(isinstance(n, str) and not PurePosixPath(n).is_absolute()
            and '..' not in PurePosixPath(n).parts and str(PurePosixPath(n)) == n for n in expected),
            'Invalid EFI manifest paths')
    paths = list(root.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'Symlink found in FAT EFI payload')
    actual = {p.relative_to(root).as_posix(): sha256(p) for p in paths if p.is_file()}
    require(actual == expected, 'EFI payload differs from manifest file list or hashes')
    require({'EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi', 'EFI/OC/config.plist'} <= actual.keys(),
            'Missing required EFI boot files')
    config = plistlib.loads((root / 'EFI/OC/config.plist').read_bytes())
    revision = {k: v for k, v in config.get('#Revision', {}).items() if isinstance(v, (str, int, bool))}
    require(revision.get('Original-Model') == MODEL and revision == manifest.get('opencore_revision'),
            'EFI revision/model differs from manifest')
    platform = config['PlatformInfo']
    require(platform.get('DataHub', {}).get('BoardProduct') == BOARD, 'Wrong MacBookPro9,1 board')
    require(all(platform.get(section, {}).get('SystemProductName', '') in ('', MODEL)
                for section in ('DataHub', 'Generic', 'SMBIOS')), 'Unexpected platform model override')
    if base_config is not None:
        require(platform == base_config['PlatformInfo'], 'Base EFI platform identity was changed')
        for key in ('Original-Model', 'Spoofed-Model', 'Hardware-Wifi'):
            require(config['#Revision'].get(key) == base_config['#Revision'].get(key), 'Base EFI changed ' + key)
    adds, indices = config['Kernel']['Add'], {}
    for name in ('Lilu', 'IntelCommpage', 'HaoExec'):
        rows = [(i, r) for i, r in enumerate(adds) if r.get('BundlePath') == name + '.kext']
        require(len(rows) == 1, 'Missing/duplicate Kernel.Add for ' + name)
        index, entry = rows[0]
        require(entry.get('Enabled') is True and entry.get('Arch') in ('Any', 'x86_64'), 'Inactive kext: ' + name)
        require(entry.get('ExecutablePath') == 'Contents/MacOS/' + name
                and entry.get('PlistPath') == 'Contents/Info.plist', 'Wrong kext paths: ' + name)
        version = lambda value: tuple(map(int, value.split('.')))
        require((not entry.get('MinKernel') or version(entry['MinKernel']) <= (27, 2, 0))
                and (not entry.get('MaxKernel') or version(entry['MaxKernel']) >= (27, 2, 0)),
                'Kext excludes Darwin 27.2: ' + name)
        if name != 'Lilu':
            require(entry.get('Arch') == 'x86_64' and entry.get('MinKernel') == '27.0.0'
                    and entry.get('MaxKernel') == '27.99.99', 'Wrong Darwin range: ' + name)
        bundle = 'EFI/OC/Kexts/' + name + '.kext/'
        require(bundle + entry['ExecutablePath'] in actual and bundle + entry['PlistPath'] in actual,
                'Kext points to absent files: ' + name)
        info = plistlib.loads((root / bundle / entry['PlistPath']).read_bytes())
        require(info.get('CFBundleExecutable') == name, 'Kext executable identity differs: ' + name)
        indices[name] = index
    require(indices['Lilu'] < indices['IntelCommpage'] and indices['Lilu'] < indices['HaoExec'], 'Lilu order is wrong')
    kc_hash = sha256(boot_kc)
    require(kc_hash == manifest.get('kernel_collection_sha256'), 'Final EFI names another BootKC')
    boot, system = set(fileset_ids(boot_kc)), set(fileset_ids(system_kc))
    require('com.apple.kernel' in boot and GPU_IDS <= boot | system,
            'Missing Intel/NVIDIA/GMUX KC members: ' + ', '.join(sorted(GPU_IDS - (boot | system))))
    binding = binding_report
    require(binding.get('unit') == 'patches/hao-opencore' and binding.get('operation') == 'kc-bind'
            and binding.get('mode') in ('binder', 'binder-only', 'row') and binding.get('boot_kc_sha256') == kc_hash,
            'Missing or mismatched kernel-binding record')
    require(binding.get('row_bound') is (binding['mode'] != 'binder-only'), 'Inconsistent kernel-binding mode')
    if binding['mode'] == 'row':
        require(binding.get('reason', '').startswith('MISSING'), 'Unexpected row-binding fallback')
    repaired = binding.get('files', {})
    intel = {n: h for n, h in repaired.items() if n.startswith('EFI/OC/Kexts/IntelCommpage.kext/')}
    require(len(intel) >= 2 and all(actual.get(n) == h for n, h in intel.items()), 'Installed IntelCommpage differs from binding')
    repairs = [p for p in config['Kernel']['Patch'] if p.get('Comment') in REPAIR_COMMENTS]
    require(tuple(p['Comment'] for p in repairs) == REPAIR_COMMENTS and all(p.get('Enabled') is True for p in repairs),
            'Required kernel repair entries missing or reordered')
    partial = dict(Kernel=dict(Patch=repairs, Add=[adds[indices['IntelCommpage']]]))
    require(hashlib.sha256(plistlib.dumps(partial)).hexdigest() == repaired.get('EFI/OC/config.plist'),
            'Installed kernel repairs differ from binding artifact')
    if binding['mode'] != 'row':
        table = binding['commpage_table']
        require(table['kext_binary_sha256']['installed'] == actual['EFI/OC/Kexts/IntelCommpage.kext/Contents/MacOS/IntelCommpage'],
                'Bound IntelCommpage table binary differs')
        require(isinstance(binding.get('points'), dict) and {'site', 'range_call', 'pv_hook', 'pv_cave'} <= binding['points'].keys(),
                'Incomplete kc-binder point report')
    return dict(final_efi_prepared=True, files=len(actual), boot_kc_sha256=kc_hash, binding_mode=binding['mode'],
                gpu_gmux_members=sorted(GPU_IDS), boot_members=len(boot), system_members=len(system),
                boot_validated=False, kepler_rendering_validated=False, gmux_switching_validated=False)


"""Measured planning budgets for the two local step12 phases.

These are conservative byte accounts, not guaranteed APFS allocation bounds.
All cp -c inputs are charged as full copies; actual free space is read again
after kit staging. The caller applies its independent host-space reserve.
"""
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import stat
import subprocess
import tarfile

BUDGET_VERSION = 'step12-measured-two-phase-v1'
_BUDGET_BLOCK = 4096
_BUDGET_GB = 1_000_000_000
_BUDGET_IMAGE_BYTES = 85_899_345_920


def _budget_image_size(record, label):
    size = record.get('size_bytes') if isinstance(record, dict) else None
    if type(size) is not int or size != _BUDGET_IMAGE_BYTES:
        raise ValueError(label + ' must declare exactly 85899345920 integer size_bytes (80GiB)')
    return size


def _budget_round(value):
    value = int(value)
    if value < 0:
        raise ValueError('Negative size in space inventory')
    return (value + _BUDGET_BLOCK - 1) // _BUDGET_BLOCK * _BUDGET_BLOCK


def _budget_record(source, kind, data, logical, allocated, files, dirs, links):
    entries = files + dirs + links
    metadata = entries * _BUDGET_BLOCK
    return dict(source=str(source), kind=kind, bytes=int(data + metadata),
                data_bytes=int(data), logical_bytes=int(logical),
                allocated_bytes=int(allocated), metadata_bytes=metadata,
                files=files, directories=dirs, symlinks=links, entries=entries)


def budget_tree(path, exclude=()):
    """Inventory only this path; never follow symlinks or silently skip errors.

    Each regular file is charged max(4KiB-rounded logical size, allocated size).
    Hardlinked names are charged separately because a later copy may split them.
    Exclusions are literal relative paths and exclude their descendants too.
    """
    path = Path(path)
    omitted = set()
    for item in exclude:
        rel = PurePosixPath(str(item))
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise ValueError('Invalid space-inventory exclusion: ' + str(item))
        omitted.add(rel.as_posix())
    totals = dict(data=0, logical=0, allocated=0, files=0, dirs=0, links=0)
    stack = [(path, '')]
    while stack:
        node, relative = stack.pop()
        if relative and any(relative == x or relative.startswith(x + '/') for x in omitted):
            continue
        info = node.lstat()
        allocated = max(0, int(getattr(info, 'st_blocks', 0))) * 512
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(node)
            size = len(os.fsencode(target))
            totals['links'] += 1
            totals['logical'] += size
            totals['allocated'] += allocated
            totals['data'] += max(_budget_round(size), allocated)
        elif stat.S_ISDIR(info.st_mode):
            totals['dirs'] += 1
            # Opening the directory, rather than ignoring walk errors, is intentional.
            with os.scandir(node) as children:
                names = [child.name for child in children]
            for name in names:
                stack.append((node / name, relative + '/' + name if relative else name))
        elif stat.S_ISREG(info.st_mode):
            with node.open('rb'):
                pass  # Check readability without reading large payloads.
            totals['files'] += 1
            totals['logical'] += info.st_size
            totals['allocated'] += allocated
            totals['data'] += max(_budget_round(info.st_size), allocated)
        else:
            raise ValueError('Unsupported special file in space inventory: ' + str(node))
    result = _budget_record(path, 'filesystem', **totals)
    result['exclude'] = sorted(omitted)
    return result


def budget_tar(path):
    """Read archive headers to budget expansion, without extracting files.

    Hardlinks are charged as full target-sized files, including forward links.
    Implicit directories are included. The whole archive is charged even where
    the staging copy uses only its python/ subtree.
    """
    path = Path(path)
    records, directories = {}, {''}
    with tarfile.open(path, mode='r|*') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe archive member in space budget: ' + member.name)
            key = name.as_posix()
            if key in ('', '.'):
                continue
            for parent in name.parents:
                directories.add('' if str(parent) == '.' else parent.as_posix())
            if member.isdir():
                directories.add(key)
            elif member.isfile():
                if key in records:
                    raise ValueError('Repeated archive file cannot be budgeted safely: ' + key)
                records[key] = ('file', int(member.size))
            elif member.islnk():
                if key in records:
                    raise ValueError('Repeated archive file cannot be budgeted safely: ' + key)
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or '..' in target.parts:
                    raise ValueError('Unsafe archive hardlink: ' + member.linkname)
                records[key] = ('hardlink', target.as_posix())
            elif member.issym():
                if key in records:
                    raise ValueError('Repeated archive file cannot be budgeted safely: ' + key)
                records[key] = ('symlink', len(os.fsencode(member.linkname)))
            else:
                raise ValueError('Unsupported archive member: ' + member.name)
    def size_of(key, seen=()):
        if key in seen or key not in records:
            raise ValueError('Unresolved or cyclic archive hardlink: ' + key)
        kind, value = records[key]
        if kind == 'hardlink':
            return size_of(value, seen + (key,))
        if kind != 'file':
            raise ValueError('Archive hardlink does not target a regular file: ' + key)
        return value
    data = logical = files = links = 0
    for key, (kind, value) in records.items():
        if kind == 'symlink':
            links += 1
            size = value
        else:
            files += 1
            size = size_of(key)
        logical += size
        data += _budget_round(size)
    return _budget_record(path, 'archive-expanded', data, logical, 0, files, len(directories), links)


def budget_git(repo, revision):
    """Budget a tracked git archive without counting checkout/.git storage."""
    repo = Path(repo)
    completed = subprocess.run(['git', '-C', str(repo), 'ls-tree', '-rlz', str(revision)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    data = logical = files = links = 0
    directories = {''}
    for record in completed.stdout.split(b'\0'):
        if not record:
            continue
        header, name = record.split(b'\t', 1)
        mode, kind, oid, raw_size = header.split()
        relative = PurePosixPath(os.fsdecode(name))
        for parent in relative.parents:
            directories.add('' if str(parent) == '.' else parent.as_posix())
        if mode == b'160000' and kind == b'commit':
            # git archive records an empty submodule directory, not its checkout.
            directories.add(relative.as_posix())
            continue
        if kind != b'blob':
            raise ValueError('Non-blob entry in exported source tree: ' + os.fsdecode(name))
        size = int(raw_size)
        if mode == b'120000':
            links += 1
        elif mode in (b'100644', b'100755'):
            files += 1
        else:
            raise ValueError('Unsupported source-tree mode: ' + mode.decode())
        logical += size
        data += _budget_round(size)
    result = _budget_record(repo, 'git-export', data, logical, 0, files, len(directories), links)
    result['revision'] = str(revision)
    return result


class _MeasuredBudget:
    def __init__(self, phase):
        self.phase, self.cache, self.components = phase, {}, []

    def measure(self, path, kind='tree', exclude=(), revision=None):
        path = Path(path).absolute()
        key = (kind, str(path), tuple(sorted(map(str, exclude))), revision)
        if key not in self.cache:
            self.cache[key] = (budget_tree(path, exclude) if kind == 'tree' else
                               budget_tar(path) if kind == 'tar' else budget_git(path, revision))
        return self.cache[key]

    def add(self, name, path, copies=1, kind='tree', exclude=(), revision=None):
        record = self.measure(path, kind, exclude, revision)
        entry = dict(name=name, label=name, bytes=record['bytes'] * copies, copies=copies,
                     source=record['source'], measurement=record)
        self.components.append(entry)
        return entry['bytes']

    def fixed(self, name, amount, basis):
        self.components.append(dict(name=name, label=name, bytes=int(amount), copies=0, basis=basis))

    def total(self):
        return sum(row['bytes'] for row in self.components)

    def finish(self):
        return dict(version=BUDGET_VERSION, phase=self.phase,
                    method='Estimated upper planning account; not a guaranteed APFS allocation bound.',
                    clone_discount=False, reserve_included=False,
                    components=self.components, bytes=self.total(), projected_bytes=self.total(),
                    inputcounts=dict(unique_measurements=len(self.cache),
                                     copy_occurrences=sum(r['copies'] for r in self.components)),
                    block_bytes=_BUDGET_BLOCK, metadata_allowance_per_entry=_BUDGET_BLOCK)


def staging_space_budget(job):
    """Call after catalog(); only NEW kit/cache allocations are charged here."""
    b = _MeasuredBudget('kit-staging')
    _budget_image_size(job.recipe, 'Assembly recipe')
    repo = Path(job.repo)
    row = lambda name: Path(job.rows[name]['path'])
    b.add('OCLP tracked export', job.oclp, kind='git', revision=job.oclp_revision)
    b.add('PatcherSupportPkg DMG', row('psp_2.0.5'))
    b.add('Full expanded KDK copy', job.kdk)
    b.add('Python expanded cache and kit', row('python_x86_64'), copies=2, kind='tar')
    b.add('Python site packages', row('python_site'))
    b.add('Firmlink tool in pristine and assembly source', row('fl'), copies=2)
    b.add('Copy-hooks staging helper', repo / 'pipeline/stages/copy-hooks.py')
    for stage, name, inputs in job.plan:
        recipe = Path(job.P['directory'](name, str(repo / 'patches')))
        b.add('Recipe source: ' + name, recipe / 'src' if stage == 'oclp-hook' else recipe)
        for name_ in inputs:
            # cp -Rpc may fall back to ordinary copies: charge full bytes.
            b.add('Recipe input: ' + name + '/' + name_, row(name_))
        if not (recipe / 'make.sh').is_file():
            continue
        if name == 'golden-gate-userspace':
            for unit in ('audiomxd-fix', 'metal-fixes'):
                b.add('Host make source: ' + unit, repo / 'tools' / unit)
        elif name == 'hao-opencore':
            module = runpy.run_path(str(repo / 'tools/kc-binder/src/stage.py'))
            for relative in module['closure'](repo):
                b.add('Binder source: ' + relative, repo / relative)
        elif name == 'hao-command':
            # Whole on-disk tools/hao is conservative, including transient tests.
            b.add('Installed hao source including archive transient', repo / 'tools/hao')
            b.add('Installed hao notice', repo / 'NOTICE.md')
        else:
            raise ValueError('Unbudgeted host make recipe: ' + name)
    for role, name in job.recipe['inputs'].items():
        b.add('Assembly input: ' + role, row(name))
    for helper in ('golden-image.py', 'golden-layout.py', 'golden-pristine.sh',
                   'golden-workspace.py', 'recovery-tools.py', 'copy-hooks.py', 'golden-assemble.sh'):
        b.add('Assembly helper: ' + helper, repo / 'pipeline/stages' / helper)
    b.add('Assembly kit renderer', repo / 'pipeline/kit.py')
    commands = repo / 'pipeline/stages' / ('recovery-commands-' + job.recipe['donor_build'] + '.txt')
    if commands.exists():
        b.add('Recovery command declaration', commands)
    b.add('KDK preparation helper', Path(job.oclp) / 'opencore_legacy_patcher/sys_patch/utilities/kdk_intel_payload.py')
    b.add('Tahoe donor assembly tools', repo / 'tools/tahoe-donors')
    b.add('Hardware installation tools', row(job.recipe['inputs']['hardware']) / 'install-tools')
    b.add('Assembly base EFI', job.base)
    b.add('Local input lock snapshot', Path(job.work) / 'inputs')
    measured = b.total()
    b.fixed('Measured-copy headroom', (measured + 9) // 10, '10% of measured staging copies')
    b.fixed('Generated metadata and tool output allowance', 2 * _BUDGET_GB,
            'Generated JSON, logs, manifests and small host-tool output; not source payload copies')
    result = b.finish()
    result['measured_copy_bytes'] = measured
    result['probe_accounting'] = 'Probe precedes this guard; its retained allocation is already reflected in current free space.'
    return result


def remaining_staging_space_budget(job):
    """Only copies after the completed inputs.sh boundary; no bulk restaging."""
    _budget_image_size(job.recipe, 'Assembly recipe')
    b = _MeasuredBudget('kit-staging-remaining')
    row = lambda name: Path(job.rows[name]['path'])
    for role, name in job.recipe['inputs'].items():
        b.add('Remaining assembly input: ' + role, row(name))
    for helper in HELPERS:
        b.add('Remaining assembly helper: ' + helper, job.repo / 'pipeline/stages' / helper)
    b.add('Remaining kit renderer', job.repo / 'pipeline/kit.py')
    commands = job.repo / 'pipeline/stages' / ('recovery-commands-' + job.recipe['donor_build'] + '.txt')
    if commands.exists(): b.add('Remaining Recovery command declaration', commands)
    b.add('Remaining KDK preparation helper', Path(job.oclp) / 'opencore_legacy_patcher/sys_patch/utilities/kdk_intel_payload.py')
    b.add('Remaining firmlink tool copy', job.kit / 'pristine/fl')
    b.add('Remaining Tahoe donor tools', job.repo / 'tools/tahoe-donors')
    b.add('Remaining hardware installation tools', row(job.recipe['inputs']['hardware']) / 'install-tools')
    b.add('Remaining base EFI', job.base)
    b.add('Remaining local input lock snapshot', job.work / 'inputs')
    measured = b.total()
    b.fixed('Remaining-copy headroom', (measured + 9) // 10, '10% of remaining measured copies')
    b.fixed('Generated metadata and tool output allowance', 2 * _BUDGET_GB,
            'Generated JSON, logs and manifests; existing staged inputs are retained')
    result = b.finish(); result['measured_copy_bytes'] = measured
    return result


def assembly_space_budget(job):
    """Measure actual KIT after staging; target contents are counted only once."""
    b = _MeasuredBudget('image-assembly')
    kit, repo = Path(job.kit), Path(job.repo)
    image_size = _budget_image_size(job.recipe, 'Assembly recipe')
    kit_record = json.loads((kit / 'kit.json').read_text())
    if not isinstance(kit_record, dict):
        raise ValueError('kit.json must contain an object')
    _budget_image_size(kit_record.get('config'), 'Staged kit configuration')
    exclusions = []
    for declaration in (kit / 'hooks').glob('*/read-from-share.txt'):
        for line in declaration.read_text().splitlines():
            name = line.split('#', 1)[0].strip()
            if name:
                relative = PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Invalid shared-input declaration: ' + name)
                exclusions.append(declaration.parent.name + '/inputs/' + name)
    for relative in ('assembly-source', 'py-x86_64', 'site', 'post'):
        b.add('Local bootstrap: ' + relative, kit / relative)
    b.add('Local bootstrap: hooks excluding shared rows', kit / 'hooks', exclude=exclusions)
    local_copies = b.total()
    b.add('Conservative Intel KDK temporary tree', kit / 'kdk')
    # The collections are already verified prior artifacts, not the old mounted workspace.
    kc = Path(job.s11['collections']['path'])
    if not kc.is_absolute():
        kc = repo / kc
    prior_kc = b.measure(kc)['bytes']
    possible = 4 * prior_kc
    margin_inputs = [dict(name='Four prior collection-sized host copies', bytes=4 * prior_kc)]
    # Count full payloads for conservative new binding/export work, once per row
    # identity, irrespective of the row's several staged occurrences.
    for name, copies in (('hao_runtime', 2), ('kernel_repair_binding', 2),
                         ('kernel_repair_efi', 3), ('intel_commpage_abi', 3)):
        matches = sorted((kit / 'hooks').glob('*/inputs/' + name))
        matches += sorted((kit / 'post').glob('*/inputs/' + name))
        if not matches:
            raise ValueError('Required staged margin input missing: ' + name)
        amount = copies * b.measure(matches[0])['bytes']
        possible += amount
        margin_inputs.append(dict(name=name, copies=copies, bytes=amount, source=str(matches[0])))
    efi = 3 * b.measure(kit / 'assembly-source/esp')['bytes']
    possible += efi
    margin_inputs.append(dict(name='EFI staging, artifact and ZIP allowance', copies=3, bytes=efi))
    b.fixed('KC, binding, EFI exports and logs allowance', max(4 * _BUDGET_GB, possible),
            'Maximum of 4GB and measured collection/payload/export planning account')
    host = b.total()
    b.fixed('Host-copy headroom', (host + 9) // 10, '10% of host copies and host working allowance, excluding raw target')
    b.fixed('Filesystem and image-container allowance', 2 * _BUDGET_GB, 'Additional host filesystem/container planning allowance')
    b.fixed('Full raw image capacity', image_size, '80GiB target, including all target volumes, cryptex and target contents')
    result = b.finish()
    result.update(local_bootstrap_bytes=local_copies, host_copy_and_work_bytes=host,
                  shared_input_exclusions=sorted(exclusions), margin_inputs=margin_inputs)
    return result


DONOR_REPAIR_ROLES = {
    'tahoe_native_donors': 'native',
    'tahoe_extensions_donors': 'extensions',
    'tahoe_driverkit_donors': 'driverkit',
    'tahoe_boot_donors': 'boot',
    'tahoe_recovery_donors': 'recovery',
}
DONOR_RAW_PINS = {
    'report.json': 'c41c38629db6122be8e33c909090a8c44a6f28ea246409f23de6c91f5a1f5288',
    'recipe.json': '690dae2da24e07de40c96bae1dc04f502404befc30934bcef96f678dd43e4f91',
    'lists/sys.tsv': 'e73c88671a34a8c9c9e67c887f74291e96fb4437247587ceb085ac463df0adfb',
    'zip/AssetData/payloadv2/links.txt': '16fcd7b9d02f30032d9d8d1142a67cc2e35831dfd5e5d268673e47deefd2366f',
}
DONOR_ORIGINAL_MANIFEST = '8e61cbec24bfedaf12584e878346d2042830775bbdce15b1c052e2d616a2f3b1'


def donor_difference(before, after):
    """Describe the difference from a rebuilt tree whose original row hash passed."""
    def entries(root):
        records = {}
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in sorted(dirs + files):
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                if relative == 'build.json':
                    continue
                st = path.lstat()
                item = {'mode': stat.S_IMODE(st.st_mode)}
                if stat.S_ISLNK(st.st_mode):
                    item.update(kind='symlink', target=os.readlink(path))
                elif stat.S_ISDIR(st.st_mode):
                    item.update(kind='directory')
                elif stat.S_ISREG(st.st_mode):
                    item.update(kind='file', sha256=sha(path), size=st.st_size)
                else:
                    item.update(kind='special')
                records[relative] = item
        return records
    old, new = entries(before), entries(after)
    changed = [p for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)]
    return dict(count=len(changed), entries=[dict(path=p, old=old.get(p), restored=new.get(p))
                                           for p in changed[:60]], truncated=len(changed) > 60)


def publish_repaired_donor(old, rebuilt, backup, expected, hash_tree):
    """Only a tree matching the existing upstream row may replace the old artifact."""
    if rebuilt.is_symlink() or not rebuilt.is_dir():
        raise Stop('Donorul refacut nu este un director obisnuit.')
    if backup.exists() or backup.is_symlink():
        raise Stop('Destinatia de pastrare a donorului exista deja: ' + str(backup))
    if hash_tree(rebuilt) != expected:
        raise Stop('Donorul reconstruit nu corespunde hash-ului original; este pastrat separat.')
    if old.is_symlink() or not old.is_dir():
        raise Stop('Donorul original nu mai este directorul asteptat.')
    old.rename(backup)
    try:
        rebuilt.rename(old)
    except BaseException:
        if not old.exists() and not old.is_symlink():
            backup.rename(old)
        raise


def repair_assembly_donors(job):
    """Recheck selected assembly donors before staging; rebuild mismatches from step6."""
    library = runpy.run_path(str(job.repo / 'pipeline/lock.py'))
    checks, changed = [], []
    print('    Verific pachetele pentru asamblare inaintea copiilor.', flush=True)
    for name in dict.fromkeys(job.recipe['inputs'].values()):
        _, lock = job.original_row(name)
        expected, path, _ = parse_row(lock.read_text(), job.repo, name)
        if not path.is_dir() or path.is_symlink():
            raise Stop('Pachet de asamblare absent sau neasteptat: ' + name)
        actual = library['row_hash'](str(lock.parent), name, str(path))
        row = dict(name=name, path=str(path.relative_to(job.repo)), expected=expected, actual=actual)
        checks.append(row)
        if actual != expected:
            changed.append((name, lock, path, expected, actual))
        else:
            problems = library['check_row'](str(lock.parent), name, str(path))
            if problems:
                raise Stop('; '.join(problems))
    job.report['assembly_donor_checks'] = checks
    job.save()
    if not changed:
        print('    Pachetele de asamblare corespund hash-urilor fixate.', flush=True)
        return
    unknown = [name for name, *_ in changed if name not in DONOR_REPAIR_ROLES]
    if unknown:
        raise Stop('Pachetul necesita o reparatie distincta: ' + ', '.join(unknown))
    previous = load(job.local / 'step6-result.json')
    if (previous.get('upstream_commit') != PIN or previous.get('model') != MODEL
            or previous.get('donor_build') != DONOR or not previous.get('donors_ready')
            or previous.get('errors')):
        raise Stop('Raportul pasului 6 nu confirma donatorii originali.')
    raw = inside(job.repo, 'store/tmp/mbp91-step6/donor-inputs')
    for relative, digest in DONOR_RAW_PINS.items():
        path = inside(raw, relative)
        if not path.is_file() or sha(path) != digest:
            raise Stop('Intrarea pastrata de la pasul 6 lipseste sau difera: ' + relative)
    if not (raw / 'tree').is_dir():
        raise Stop('Arborele de extragere din pasul 6 lipseste.')
    cache = inside(job.repo, 'store/inputs/25G342/os-cryptex-x86_64h')
    if any(DONOR_REPAIR_ROLES[name] == 'native' for name, *_ in changed):
        expected_cache = previous['rows']['tahoe_os_cache_x86_64h']['sha256']
        main_cache = cache / 'dyld_shared_cache_x86_64h'
        if not main_cache.is_file() or sha(main_cache) != expected_cache:
            raise Stop('Cache-ul Tahoe necesar refacerii donorului nativ difera.')
    amount = sum(budget_tree(path)['bytes'] for _, _, path, _, _ in changed)
    need = 2_000_000_000 + 3 * amount
    job.measured_space('refacere donori Tahoe', dict(projected_bytes=need, components=[
        dict(label='Pachete refacute si intermediari, pe baza dimensiunilor existente', bytes=3 * amount),
        dict(label='Rezerva de lucru pentru constructorul de donori', bytes=2_000_000_000)]))
    for name, lock, path, expected, observed in changed:
        prior = previous['rows'].get(name, {})
        if prior.get('sha256') != expected or prior.get('path') != str(path.relative_to(job.repo)) or not prior.get('verified'):
            raise Stop('Raportul pasului 6 nu confirma exact intrarea: ' + name)
        role = DONOR_REPAIR_ROLES[name]
        output = path.with_name(path.name + '.step12-rebuild-' + job.stamp)
        backup = path.with_name(path.name + '.before-step12-' + job.stamp)
        if output.exists() or output.is_symlink():
            raise Stop('Destinatia refacerii exista deja: ' + str(output))
        common = ['--tree', raw / 'tree', '--metadata', raw / 'lists/sys.tsv',
                  '--links', raw / 'zip/AssetData/payloadv2/links.txt']
        layouts = ['--tree', raw / 'tree', '--unpack', raw, '--map', raw / 'preboot-recovery-map.tsv']
        options = {'native': common + ['--cache', cache], 'extensions': common,
                   'driverkit': ['--source', raw / 'out/driverkit', '--metadata', raw / 'out/driverkit/metadata.tsv'],
                   'boot': layouts, 'recovery': layouts}[role]
        print('    Refac din sursele pastrate: ' + name, flush=True)
        job.command(job.py + [job.repo / 'tools/tahoe-donors/make', role, *options,
                              '--recipe', raw / 'recipe.json', '--output', output], timeout=7200)
        def tree_hash(candidate):
            return library['row_hash'](str(lock.parent), name, str(candidate))
        got = tree_hash(output)
        if got != expected:
            job.report.setdefault('donor_repair_failures', []).append(dict(name=name,
                expected=expected, actual=got, candidate=str(output.relative_to(job.repo))))
            job.save()
            raise Stop('Donorul refacut nu corespunde hash-ului original Hao: ' + name)
        problems = library['check_row'](str(lock.parent), name, str(output))
        if problems:
            raise Stop('; '.join(problems))
        if tree_hash(path) != observed:
            raise Stop('Donorul existent a fost modificat in timpul refacerii: ' + name)
        difference = donor_difference(path, output)
        original_manifest = (sha(path / 'manifest.json') == DONOR_ORIGINAL_MANIFEST
                             if name == 'tahoe_native_donors' and (path / 'manifest.json').is_file() else None)
        publish_repaired_donor(path, output, backup, expected, tree_hash)
        record = dict(name=name, previous_sha256=observed, restored_sha256=expected,
                      backup=str(backup.relative_to(job.repo)), path=str(path.relative_to(job.repo)),
                      previous_native_manifest_matches_step6=original_manifest, differences=difference)
        job.report.setdefault('donor_repairs', []).append(record)
        job.save()
        print('    Hash original restabilit: ' + name + '; diferente: ' + str(difference['count']), flush=True)



"""Validate a MBP9,1 prespecialization variant generated by pinned Hao code.

Pure helpers only: the caller mounts pristine Rosetta read-only, runs the real
generator twice (original overrides, then original plus the two observed NVIDIA
overrides), and owns all publication/backup operations. No cache bytes are edited
here. No research Swift catalog is installed by the selected userspace recipe.
"""
import copy
import hashlib
import re
from pathlib import Path

PRESPECIALIZATION_MAIN = 'dyld_shared_cache_x86_64'
PRESPECIALIZATION_SIX = PRESPECIALIZATION_MAIN + '.06'
PRESPECIALIZATION_EXTRA = (
    '/System/Library/Frameworks/ImageIO.framework/Versions/A/ImageIO',
    '/System/Library/PrivateFrameworks/CMPhoto.framework/Versions/A/CMPhoto',
)
PRESPECIALIZATION_FILES = (PRESPECIALIZATION_MAIN, PRESPECIALIZATION_SIX)
PRESPECIALIZATION_SPECS = {
    'cache-main.json': PRESPECIALIZATION_MAIN,
    'cache-06.json': PRESPECIALIZATION_SIX,
}
PRESPECIALIZATION_CACHE_PREFIX = 'System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/'


def _prespec_require(ok, message):
    if not ok:
        raise ValueError('prespecialization variant: ' + message)


def _prespec_edits(edits, name):
    _prespec_require(isinstance(edits, list) and bool(edits), name + ': edits absent')
    spans = []
    for edit in edits:
        _prespec_require(isinstance(edit, dict), name + ': edit is not an object')
        at = edit.get('at')
        _prespec_require(type(at) is int and at >= 0, name + ': invalid offset')
        for key in ('id', 'address', 'reason', 'before', 'after'):
            _prespec_require(isinstance(edit.get(key), str) and bool(edit[key]),
                             name + ': missing edit ' + key)
        try:
            before, after = bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
        except ValueError as error:
            raise ValueError(name + ': invalid edit bytes') from error
        _prespec_require(bool(before) and len(before) == len(after) and before != after,
                         name + ': edit must change equal-length bytes')
        spans.append((at, at + len(before)))
    spans.sort()
    _prespec_require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])),
                     name + ': overlapping edit ranges')


def _prespec_generated_files(generated):
    _prespec_require(isinstance(generated, dict) and generated.get('schema') == 1
                     and generated.get('kind') == 'prespecialization-overrides',
                     'unexpected generator schema/kind')
    _prespec_require(generated.get('catalog_keys') == 0,
                     'expected pristine Apple cache with no added research catalog')
    _prespec_require(generated.get('conformance_removed') is None
                     and generated.get('conformance_kept_mixed') == [],
                     '--conformance must remain disabled')
    _prespec_require('outputs' not in generated, '--apply must remain disabled')
    rows = generated.get('files')
    _prespec_require(isinstance(rows, list), 'generator files must be a list')
    files = {}
    for row in rows:
        _prespec_require(isinstance(row, dict), 'invalid generator file record')
        suffix = row.get('file')
        _prespec_require(suffix in ('main', '.06'), 'unexpected edited cache file')
        name = PRESPECIALIZATION_MAIN if suffix == 'main' else PRESPECIALIZATION_SIX
        _prespec_require(name not in files and Path(row.get('path', '')).name == name,
                         'duplicate/mismatched generator file path')
        _prespec_require(isinstance(row.get('sha256'), str)
                         and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None,
                         name + ': invalid input digest')
        _prespec_edits(row.get('edits'), name)
        files[name] = {'sha256': row['sha256'], 'edits': copy.deepcopy(row['edits'])}
    _prespec_require(set(files) == set(PRESPECIALIZATION_FILES),
                     'expected main and .06 edit declarations')
    return files


def prespecialization_variant(original, baseline, candidate, cache_directory=None):
    """Return installer-format JSON after proving baseline and expanded plans.

    ``baseline`` and ``candidate`` must be successful outputs of the pinned real
    generator, without --catalog-keys/--conformance/--apply. The external research
    catalog is absent from this image; zero checked catalog keys is recorded
    explicitly rather than copying the upstream research count of 1282.
    If ``cache_directory`` is supplied, also verify input SHA256, UUID and every
    before-byte range against the pristine mounted cache.
    """
    _prespec_require(isinstance(original, dict) and original.get('schema') == 1,
                     'unsupported original recipe')
    base_files = _prespec_generated_files(baseline)
    new_files = _prespec_generated_files(candidate)
    old_paths = original.get('overridden')
    _prespec_require(isinstance(old_paths, list) and old_paths == sorted(set(old_paths))
                     and len(old_paths) == 10, 'unexpected original override census')
    _prespec_require(not set(PRESPECIALIZATION_EXTRA) & set(old_paths),
                     'observed NVIDIA additions already present in original recipe')
    expected_paths = sorted(set(old_paths) | set(PRESPECIALIZATION_EXTRA))
    for key in ('cache_uuid', 'apple_entries', 'overridden',
                'descriptor_slots_dropped', 'conformance_site'):
        _prespec_require(baseline.get(key) == original.get(key),
                         'baseline differs from pinned recipe: ' + key)
    _prespec_require(base_files == original.get('files'),
                     'baseline edits/hashes differ from pinned recipe')
    _prespec_require(candidate.get('overridden') == expected_paths,
                     'candidate override census is not original plus measured ImageIO/CMPhoto')
    for key in ('cache_uuid', 'apple_entries', 'conformance_site'):
        _prespec_require(candidate.get(key) == original.get(key),
                         'candidate changed immutable metadata: ' + key)
    _prespec_require(type(candidate.get('apple_entries')) is int
                     and candidate['apple_entries'] == 2762,
                     'unexpected count of checked Apple pointer entries')
    _prespec_require(new_files[PRESPECIALIZATION_MAIN] == base_files[PRESPECIALIZATION_MAIN],
                     'candidate changed the two existing libswiftCore call edits')
    for name in PRESPECIALIZATION_FILES:
        old, new = base_files[name], new_files[name]
        _prespec_require(new['sha256'] == old['sha256'], name + ': pristine cache hash changed')
        by_offset = {e['at']: e for e in new['edits']}
        _prespec_require(all(by_offset.get(e['at']) == e for e in old['edits']),
                         name + ': an existing descriptor/call edit was lost or changed')
    dropped = candidate.get('descriptor_slots_dropped')
    _prespec_require(isinstance(dropped, dict) and set(dropped) <= set(expected_paths),
                     'invalid descriptor owner census')
    _prespec_require(all(type(v) is int and v > 0 for v in dropped.values()),
                     'invalid dropped descriptor count')
    _prespec_require(sum(dropped.values()) == len(new_files[PRESPECIALIZATION_SIX]['edits']),
                     'descriptor counts differ from emitted edits')
    for owner, count in original['descriptor_slots_dropped'].items():
        _prespec_require(dropped.get(owner) == count, 'existing descriptor owner count changed')
    _prespec_require(set(dropped) - set(original['descriptor_slots_dropped'])
                     <= set(PRESPECIALIZATION_EXTRA), 'unexpected new descriptor owner')
    for edit in new_files[PRESPECIALIZATION_SIX]['edits']:
        before, after = bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
        _prespec_require(edit['id'] == 'descriptor-map-overridden' and len(before) == 8
                         and after[:5] == bytes(5) and after[5:] == before[5:]
                         and before[:5] != bytes(5), 'descriptor edit changed chain delta')
    result = {key: copy.deepcopy(candidate[key]) for key in
              ('schema', 'cache_uuid', 'apple_entries', 'catalog_keys', 'overridden',
               'descriptor_slots_dropped', 'conformance_site')}
    result.update(generator='shared-cache generator: make prespecialization-overrides CACHE_MAIN --overridden LIST',
                  blocked={'apple_entries': 0, 'catalog_keys': 0}, files=new_files)
    result['local_scope'] = {
        'model': 'MacBookPro9,1', 'build': '26B131',
        'catalog': 'No research catalog is installed; catalog_keys=0 means none supplied or checked.',
        'gate': 'Pinned generator completed after checking every actual Apple pointer-keyed entry.',
        'observed_additions': list(PRESPECIALIZATION_EXTRA),
    }
    if cache_directory is not None:
        validate_prespecialization_cache(result, cache_directory)
    return result


def validate_prespecialization_cache(recipe, cache_directory):
    """Read-only validation of the real input cache and all planned byte edits."""
    root = Path(cache_directory)
    with (root / PRESPECIALIZATION_MAIN).open('rb') as stream:
        stream.seek(0x58)
        _prespec_require(stream.read(16).hex().upper() == recipe['cache_uuid'], 'cache UUID differs')
    for name, row in recipe['files'].items():
        _prespec_require(name in PRESPECIALIZATION_FILES, 'unexpected cache filename')
        path = root / name
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(16 << 20), b''):
                digest.update(chunk)
            _prespec_require(digest.hexdigest() == row['sha256'], name + ': SHA256 differs')
            for edit in row['edits']:
                before = bytes.fromhex(edit['before'])
                stream.seek(edit['at'])
                _prespec_require(stream.read(len(before)) == before, name + ': before bytes differ')


def prespecialization_edit_specs(original_specs, original_recipe, new_recipe):
    """Copy both upstream cache specs; replace only prespecialization matcher rows."""
    _prespec_require(set(original_specs) == set(PRESPECIALIZATION_SPECS), 'expected two cache specs')
    result = copy.deepcopy(original_specs)
    for spec_name, cache_name in PRESPECIALIZATION_SPECS.items():
        spec = result[spec_name]
        _prespec_require(spec.get('path') == PRESPECIALIZATION_CACHE_PREFIX + cache_name,
                         'cache declaration path differs')
        entries = [e for e in spec.get('edits', []) if e.get('id') == 'prespecialization-overrides']
        _prespec_require(len(entries) == 1 and entries[0].get('kind') == 'matcher',
                         'prespecialization matcher missing/duplicated')
        old = original_recipe['files'][cache_name]
        old_rows = [{k: e[k] for k in ('at', 'before', 'after', 'reason')} for e in old['edits']]
        _prespec_require(entries[0].get('resolved') == {old['sha256']: old_rows},
                         'original byte declaration differs from pinned recipe')
        new = new_recipe['files'][cache_name]
        # The unchanged Swift/code-identity repairs share this same input file.
        # A new descriptor slot must not overlap any of their declared writes.
        other_spans = []
        for entry in spec.get('edits', []):
            if entry.get('id') == 'prespecialization-overrides':
                continue
            for edit in entry.get('resolved', {}).get(old['sha256'], []):
                at = edit.get('at')
                _prespec_require(type(at) is int and at >= 0,
                                 'invalid offset in an unchanged cache matcher')
                before = bytes.fromhex(edit['before'])
                other_spans.append((at, at + len(before)))
        for edit in new['edits']:
            lo, hi = edit['at'], edit['at'] + len(bytes.fromhex(edit['before']))
            _prespec_require(not any(lo < end and start < hi for start, end in other_spans),
                             cache_name + ': new prespecialization edit overlaps another cache repair')
        entries[0]['resolved'] = {
            new['sha256']: [{k: e[k] for k in ('at', 'before', 'after', 'reason')} for e in new['edits']]
        }
    return result


def validate_prespecialization_declared(declared):
    """declared.json inventories output paths only: it must stay unchanged."""
    _prespec_require(isinstance(declared, dict), 'declared.json must be an object')
    _prespec_require(not any('shared-cache' in name for name in declared),
                     'a shared-cache/catalog recipe would invalidate the no-catalog scope')
    entry = declared.get('golden-gate-userspace', {})
    paths = entry.get('files')
    _prespec_require(isinstance(paths, list) and all(isinstance(p, str) for p in paths),
                     'userspace declared-file inventory missing')
    _prespec_require({PRESPECIALIZATION_CACHE_PREFIX + name for name in PRESPECIALIZATION_FILES}
                     <= set(paths), 'declared.json lacks the existing main/.06 cache paths')
    return {'unchanged': True, 'cache_paths': [PRESPECIALIZATION_CACHE_PREFIX + name
                                             for name in PRESPECIALIZATION_FILES]}


"""Remove one proven failed userspace image after fresh attachment checks.

Proof keys: attempt, build_sha256, failure_log, failure_log_sha256.
Paths are relative to job.repo. All reports, source and temporary files remain.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat

_USERSPACE_CLEANUP_IMAGE_BYTES = 80 * 1024 ** 3
_USERSPACE_FAILURE_MARKER = 'prespecialization: the image overrides other cache images than the edits were made for'


class UserspaceCleanupError(RuntimeError):
    pass


def _userspace_cleanup_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _userspace_cleanup_path(repo, relative):
    relative = PurePosixPath(str(relative))
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise UserspaceCleanupError('Cale relativa de curatare invalida')
    path = repo.joinpath(*relative.parts)
    for item in (path, *path.parents):
        if item.is_symlink():
            raise UserspaceCleanupError('Cale redirectionata prin symlink: ' + str(item))
        if item == repo:
            break
    if not path.resolve().is_relative_to(repo):
        raise UserspaceCleanupError('Cale de curatare externa proiectului')
    return path


def _userspace_cleanup_proof(repo, proof):
    attempt = _userspace_cleanup_path(repo, proof['attempt'])
    if (attempt.parent != repo / 'store/tmp' or not attempt.is_dir()
            or not re.fullmatch(r'mbp91-image-step12-\d{8}-\d{6}-\d{6}', attempt.name)):
        raise UserspaceCleanupError('Nu este incercarea de imagine step12 identificata')
    build_path = _userspace_cleanup_path(repo, str(attempt.relative_to(repo) / 'work/build.json'))
    log_path = _userspace_cleanup_path(repo, proof['failure_log'])
    for path, key in ((build_path, 'build_sha256'), (log_path, 'failure_log_sha256')):
        expected = proof.get(key, '')
        if not re.fullmatch(r'[0-9a-f]{64}', expected) or _userspace_cleanup_hash(path) != expected:
            raise UserspaceCleanupError('Dovada esecului a fost schimbata: ' + str(path))
    build = json.loads(build_path.read_text())
    image = attempt / 'target.img'
    config = build.get('configuration', {})
    if (build.get('status') != 'failed' or config.get('image') != str(image)
            or config.get('work') != str(attempt / 'work')
            or type(config.get('size_bytes')) is not int or config['size_bytes'] != _USERSPACE_CLEANUP_IMAGE_BYTES
            or 'attached_device' not in build or build['attached_device'] is not None
            or build.get('cleanup_errors')):
        raise UserspaceCleanupError('Imaginea sau demontarea nu corespunde esecului verificat')
    expected_steps = ['layout', 'golden-system', 'group-volumes', 'golden-finalize',
                      'boot-and-esp', 'hardware', 'recipes', 'recipe darwin27-kernel',
                      'recipe golden-gate-userspace']
    steps = build.get('steps', [])
    if ([step.get('name') for step in steps] != expected_steps
            or any(step.get('complete') is not True for step in steps[:6] + steps[7:8])
            or steps[6].get('complete') or steps[8].get('complete')):
        raise UserspaceCleanupError('Punctul de esec nu este inceputul retetei userspace')
    hook = str(attempt / 'hooks/02-golden-gate-userspace/kc-hook.sh')
    failed = ['sh', '-eu', hook, str(attempt / 'work/mnt/system')]
    matches = [row for row in build.get('commands', []) if row.get('command') == failed]
    log = log_path.read_text(errors='replace')
    if (len(matches) != 1 or matches[0].get('returncode') != 1 or hook not in build.get('error', '')
            or _USERSPACE_FAILURE_MARKER not in log or hook not in log):
        raise UserspaceCleanupError('Lipseste dovada exacta a esecului prespecialization userspace')
    image = _userspace_cleanup_path(repo, str(image.relative_to(repo)))
    info = image.lstat() if os.path.lexists(image) else None
    if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_size != _USERSPACE_CLEANUP_IMAGE_BYTES):
        raise UserspaceCleanupError('Tinta nu este fisierul obisnuit de imagine de 80 GiB')
    return attempt, image, info


def _userspace_cleanup_mounts(text):
    paths = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if ' on ' not in line or ' (' not in line or not line.endswith(')'):
            raise UserspaceCleanupError('Lista punctelor de montare este neinterpretabila')
        mounted = line.split(' on ', 1)[1].rsplit(' (', 1)[0]
        if ' on ' in mounted or not mounted.startswith('/'):
            raise UserspaceCleanupError('Punct de montare ambiguu')
        mounted = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), mounted)
        paths.append(Path(mounted).resolve())
    if not paths:
        raise UserspaceCleanupError('Lista punctelor de montare este goala')
    return paths


def cleanup_failed_userspace_image(job, proof, delete_image=None):
    """Verify, freshly check mounts, then remove only attempt/target.img.

    delete_image(image) optionally supplies an internal privileged unlink action.
    The default uses the existing job.command privilege handling for one file.
    """
    repo = Path(job.repo).resolve()
    attempt, image, before = _userspace_cleanup_proof(repo, proof)
    attached = plistlib.loads(job.command(['/usr/bin/hdiutil', 'info', '-plist'], capture=True, timeout=30).encode())
    if not isinstance(attached, dict) or not isinstance(attached.get('images'), list):
        raise UserspaceCleanupError('Starea imaginilor atasate nu a putut fi verificata')
    def protected(path):
        path = Path(path).resolve()
        return path == attempt or path.is_relative_to(attempt)
    for row in attached['images']:
        source = row.get('image-path')
        if source and (protected(source) or (image.exists() and Path(source).exists() and os.path.samefile(image, source))):
            raise UserspaceCleanupError('Imaginea incercarii este inca atasata')
        for entity in row.get('system-entities', []):
            if entity.get('mount-point') and protected(entity['mount-point']):
                raise UserspaceCleanupError('Exista un volum de imagine montat sub incercarea esuata')
    mounted = _userspace_cleanup_mounts(job.command(['/sbin/mount'], capture=True, timeout=30))
    if any(protected(path) for path in mounted):
        raise UserspaceCleanupError('Exista un volum montat sub incercarea esuata')
    _userspace_cleanup_path(repo, str(image.relative_to(repo)))
    current = image.lstat() if os.path.lexists(image) else None
    identity = lambda value: None if value is None else (value.st_dev, value.st_ino, value.st_size,
                                                        value.st_mtime_ns, value.st_ctime_ns, value.st_mode)
    if identity(current) != identity(before):
        raise UserspaceCleanupError('Imaginea s-a schimbat in timpul verificarii; este pastrata')
    result = dict(attempt=str(attempt.relative_to(repo)), image=str(image.relative_to(repo)),
                  removed=False, already_absent=current is None, build_sha256=proof['build_sha256'],
                  failure_log_sha256=proof['failure_log_sha256'], live_attachment_checks=True,
                  allocated_bytes_before=(max(0, getattr(current, 'st_blocks', 0)) * 512 if current else 0))
    if current is not None:
        print('    Elimin imaginea esuata verificata; pastrez rapoartele si sursele incercarii.', flush=True)
        if delete_image is None:
            job.command(['/bin/rm', '--', str(image)], root=True, timeout=30)
        else:
            delete_image(image)
        if os.path.lexists(image):
            raise UserspaceCleanupError('Stergerea imaginii nu a fost confirmata')
        result['removed'] = True
    job.report['failed_userspace_image_cleanup'] = result
    job.save()
    return result


USERSPACE_RECIPE = 'hooks/02-golden-gate-userspace/prespecialization-26B131.json'
USERSPACE_VARIANT = 'local-prespecialization-mbp91'
USERSPACE_PATCH_ID = 'mbp91-kepler-prespecialization-v1'


def userspace_origin(job):
    """Anchor the observed NVIDIA-specific failure before replacing any reports."""
    proof = job.state.get('userspace_fix_origin')
    if proof is None:
        attempt = job.state.get('assembly_attempt')
        if not attempt:
            raise Stop('Lipseste incercarea de imagine care a identificat diferentele NVIDIA.')
        previous = load(job.work / 'previous-step12-result.json')
        old_kit = previous.get('kit', {})
        if (not previous.get('kit_prepared') or previous.get('image_built')
                or old_kit.get('path') != str(job.kit.relative_to(job.repo))
                or old_kit.get('manifest_sha256') != job.state['kit']['manifest_sha256']
                or previous.get('assembly_work') != attempt):
            raise Stop('Raportul precedent nu confirma kitul si imaginea esuata curenta.')
        log = job.work / 'previous-step12-build.log'
        build = inside(job.repo, attempt) / 'work/build.json'
        proof = dict(attempt=attempt, build_sha256=sha(build),
                     failure_log=str(log.relative_to(job.repo)), failure_log_sha256=sha(log),
                     kit=str(job.kit.relative_to(job.repo)),
                     original_kit_manifest_sha256=job.state['kit']['manifest_sha256'])
    if proof.get('kit') != str(job.kit.relative_to(job.repo)):
        raise Stop('Dovada NVIDIA apartine altui kit.')
    _userspace_cleanup_proof(job.repo, proof)
    log = inside(job.repo, proof['failure_log']).read_text(errors='replace')
    exact = 'new: ' + repr(list(PRESPECIALIZATION_EXTRA)) + '; gone: none;'
    matches = [line for line in log.splitlines() if line.startswith(_USERSPACE_FAILURE_MARKER)]
    if len(matches) != 1 or exact not in matches[0]:
        raise Stop('Diferentele Swift observate nu sunt exact ImageIO si CMPhoto.')
    job.state['userspace_fix_origin'] = proof
    job.report['userspace_fix_origin'] = proof
    job.save()
    return proof


def internal_userspace_plan(request_path):
    """Generate metadata against a read-only pristine image, before rebuilding."""
    request_path = Path(request_path).resolve(strict=True)
    request = load(request_path)
    work = request_path.parent
    if (work.parent.name != 'tmp' or work.parent.parent.name != 'store'
            or not work.name.startswith('mbp91-step12-')):
        raise Stop('Workspace de generatie userspace neasteptat.')
    repo = work.parent.parent.parent
    source = inside(repo, request['source'])
    output = inside(repo, request['output'])
    dmg = inside(repo, request['rosetta'])
    if source.parent != work or output.parent != work or output.exists():
        raise Stop('Cale de generatie userspace neasteptata.')
    if sha(dmg) != request['rosetta_sha256']:
        raise Stop('Imaginea Rosetta din kit difera de intrarea verificata.')
    make = source / 'tools/shared-cache/make'
    if sha(make) != request['generator_make_sha256']:
        raise Stop('Generatorul Swift fixat difera.')
    original_path = source / 'patches/golden-gate-userspace/src/prespecialization-26B131.json'
    original = load(original_path)
    if sha(original_path) != request['original_recipe_sha256']:
        raise Stop('Reteta Swift originala difera.')
    output.mkdir(mode=0o755)
    original_list = output / 'original-overrides.txt'
    expanded_list = output / 'mbp91-overrides.txt'
    original_list.write_text('\n'.join(original['overridden']) + '\n')
    expanded_list.write_text('\n'.join(sorted(set(original['overridden']) | set(PRESPECIALIZATION_EXTRA))) + '\n')
    mount = work / 'prespecialization-rosetta-readonly'
    mount.mkdir(mode=0o755)
    command = ['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-owners', 'on',
               '-mountpoint', str(mount), '-plist', str(dmg)]
    print('    Montez Rosetta original numai pentru citire.', flush=True)
    attached = plistlib.loads(subprocess.check_output(command))
    entities = attached.get('system-entities', [])
    whole = [r['dev-entry'] for r in entities if r.get('content-hint') == 'GUID_partition_scheme'
             and re.fullmatch(r'/dev/disk[0-9]+', r.get('dev-entry', ''))]
    device = whole[0] if len(whole) == 1 else (entities[0]['dev-entry'] if entities else None)
    if not device:
        raise Stop('hdiutil nu a identificat dispozitivul Rosetta atasat.')
    result = None
    try:
        if not any(Path(r.get('mount-point', '/')).resolve() == mount for r in entities):
            raise Stop('Rosetta nu este montata la calea ceruta.')
        cache = mount / 'System/Library/dyld'
        main = cache / PRESPECIALIZATION_MAIN
        if not main.is_file():
            raise Stop('Cache-ul x86_64 original lipseste din Rosetta.')
        for label, listing, destination in (
                ('profilul original', original_list, output / 'baseline-generator.json'),
                ('profilul MacBookPro9,1 cu NVIDIA', expanded_list, output / 'mbp91-generator.json')):
            print('    Generez si verific ' + label + '.', flush=True)
            if destination.exists():
                raise Stop('Rezultatul generatorului trebuie sa fie nou.')
            subprocess.run([sys.executable, '-I', '-B', str(make), 'prespecialization-overrides', str(main),
                            '--overridden', str(listing), '--output', str(destination)], check=True)
        baseline = load(output / 'baseline-generator.json')
        expanded = load(output / 'mbp91-generator.json')
        candidate = prespecialization_variant(original, baseline, expanded, cache_directory=cache)
        # Exercise the unchanged installer's actual cache planner as a separate reader.
        hook = inside(repo, request['hook'])
        if sha(hook / 'prespecialization.py') != request['runtime_gate_sha256']:
            raise Stop('Validatorul Swift al kitului difera.')
        module = runpy.run_path(str(hook / 'prespecialization.py'))
        planned = module['plan_cache_family'](cache, data=candidate)
        if sum(len(edits) for edits in planned.values()) != sum(len(r['edits']) for r in candidate['files'].values()):
            raise Stop('Planificatorul runtime nu reproduce toate editarile generate.')
        specs = {name: load(source / 'patches/golden-gate-userspace/edits' / name)
                 for name in PRESPECIALIZATION_SPECS}
        changed = prespecialization_edit_specs(specs, original, candidate)
        save(output / 'prespecialization-26B131.json', candidate)
        for name, value in changed.items():
            save(output / name, value)
        result = dict(patch_id=USERSPACE_PATCH_ID, original_recipe_sha256=sha(original_path),
                      new_recipe_sha256=sha(output / 'prespecialization-26B131.json'),
                      cache_uuid=candidate['cache_uuid'], apple_entries_checked=candidate['apple_entries'],
                      catalog_keys_checked=candidate['catalog_keys'],
                      overridden=candidate['overridden'], descriptor_slots_dropped=candidate['descriptor_slots_dropped'],
                      baseline_exact=True, pinned_generator_completed=True, original_cache_bytes_checked=True,
                      runtime_planner_passed=True, source_manifest_sha256=request['source_manifest_sha256'],
                      rosetta_sha256=request['rosetta_sha256'],
                      files={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    finally:
        subprocess.run(['/usr/bin/hdiutil', 'detach', device], check=True)
    result['source_detached'] = True
    save(output / 'generation-result.json', result)
    print('    Corectia Swift pentru NVIDIA a trecut generatorul, hash-urile si verificarea octetilor.', flush=True)


def publish_userspace_variant(job, generated, proof):
    """Commit only the generated recipe and audited sidecar with a new kit seal."""
    kit = job.kit
    old_state = copy.deepcopy(job.state['kit'])
    manifest_path = kit / 'step12-manifest.json'
    if sha(manifest_path) != old_state['manifest_sha256']:
        raise Stop('Manifestul kitului s-a schimbat inaintea corectiei Swift.')
    old_manifest = load(manifest_path)
    recipe = kit / USERSPACE_RECIPE
    old_recipe = recipe.read_bytes()
    if sha(recipe) != old_manifest['files'][USERSPACE_RECIPE]['sha256']:
        raise Stop('Reteta kitului s-a schimbat dupa verificare.')
    new_recipe = (generated / 'prespecialization-26B131.json').read_bytes()
    generation = load(generated / 'generation-result.json')
    if (generation.get('patch_id') != USERSPACE_PATCH_ID or not generation.get('baseline_exact')
            or not generation.get('source_detached') or not generation.get('runtime_planner_passed')
            or not generation.get('pinned_generator_completed') or not generation.get('original_cache_bytes_checked')
            or generation.get('original_recipe_sha256') != hashlib.sha256(old_recipe).hexdigest()):
        raise Stop('Generarea Swift nu este completa si verificata.')
    for name, digest in generation['files'].items():
        if '/' in name or sha(generated / name) != digest:
            raise Stop('Rezultat generat schimbat: ' + name)
    if hashlib.sha256(new_recipe).hexdigest() != generation['new_recipe_sha256']:
        raise Stop('Reteta Swift generata difera de raport.')
    sidecar = kit / USERSPACE_VARIANT
    if sidecar.exists() or sidecar.is_symlink():
        raise Stop('Varianta Swift locala exista fara un raport valid de publicare.')
    backup = job.work / 'userspace-kit-backup'
    backup.mkdir()
    for path in (recipe, manifest_path, kit / 'step12-build.json'):
        shutil.copy2(path, backup / path.name)
    save(backup / 'kit-state.json', old_state)
    proof_record = dict(patch_id=USERSPACE_PATCH_ID, model=MODEL, build=GOLDEN,
                        generator_commit=PIN,
                        original_kit_manifest_sha256=old_state['manifest_sha256'],
                        original_recipe_sha256=hashlib.sha256(old_recipe).hexdigest(),
                        generation=generation, failure=proof,
                        scope='Only generated prespecialization JSON; runtime guards and all input rows retained.')
    report_keys = ('kit', 'kit_manifest_entries', 'prespecialization_variant')
    previous_report = {key: copy.deepcopy(job.report[key]) for key in report_keys if key in job.report}
    temporary = recipe.with_name(recipe.name + '.mbp91-new')
    try:
        shutil.copytree(generated, sidecar)
        save(sidecar / 'variant.json', proof_record)
        with temporary.open('xb') as stream:
            stream.write(new_recipe)
        temporary.chmod(stat.S_IMODE(recipe.stat().st_mode))
        os.replace(temporary, recipe)
        # All unchanged entries retain the seal verified by reuse_kit().
        manifest = copy.deepcopy(old_manifest)
        manifest['files'][USERSPACE_RECIPE].update(sha256=sha(recipe), bytes=recipe.stat().st_size)
        manifest['files'][USERSPACE_VARIANT] = dict(mode=stat.S_IMODE(sidecar.stat().st_mode), directory=True)
        for relative, entry in mode_manifest(sidecar).items():
            manifest['files'][USERSPACE_VARIANT + '/' + relative] = entry
        save(manifest_path, manifest)
        state = copy.deepcopy(old_state)
        state['manifest_sha256'] = sha(manifest_path)
        build = load(kit / 'step12-build.json')
        build.update(kit=state, local_prespecialization=dict(path=USERSPACE_VARIANT,
                     record_sha256=sha(sidecar / 'variant.json')))
        save(kit / 'step12-build.json', build)
        job.state['kit'] = state
        job.report['kit'] = state
        job.report['kit_manifest_entries'] = len(manifest['files'])
        job.report['prespecialization_variant'] = proof_record
        job.save()
    except BaseException:
        if temporary.is_file() and not temporary.is_symlink():
            temporary.unlink()
        recipe.write_bytes(old_recipe)
        shutil.copy2(backup / 'step12-manifest.json', manifest_path)
        shutil.copy2(backup / 'step12-build.json', kit / 'step12-build.json')
        if sidecar.is_dir() and not sidecar.is_symlink():
            shutil.rmtree(sidecar)
        job.state['kit'] = old_state
        for key in report_keys:
            if key in previous_report:
                job.report[key] = previous_report[key]
            else:
                job.report.pop(key, None)
        job.save()
        raise
    print('    Kit actualizat cu reteta Swift pentru 9,1; intrarile voluminoase sunt reutilizate.', flush=True)


def prepare_userspace_variant(job):
    proof = userspace_origin(job)
    sidecar = job.kit / USERSPACE_VARIANT
    if sidecar.is_dir() and not sidecar.is_symlink():
        record = load(sidecar / 'variant.json')
        if (record.get('patch_id') != USERSPACE_PATCH_ID or record.get('model') != MODEL
                or record.get('build') != GOLDEN or record.get('failure') != proof
                or sha(job.kit / USERSPACE_RECIPE) != record.get('generation', {}).get('new_recipe_sha256')):
            raise Stop('Varianta Swift salvata nu corespunde acestei corectii.')
        job.report['prespecialization_variant'] = record
        job.save()
        print('    Corectia Swift pentru 9,1: reutilizata dupa verificarea kitului.', flush=True)
        return proof
    validate_prespecialization_declared(load(job.kit / 'declared.json'))
    source = job.work / 'userspace-pinned-source'
    archive = job.work / 'userspace-pinned-source.tar'
    paths = ['tools/shared-cache', 'patches/golden-gate-userspace/src/prespecialization-26B131.json',
             'patches/golden-gate-userspace/edits/cache-main.json',
             'patches/golden-gate-userspace/edits/cache-06.json']
    job.command(['/usr/bin/git', 'archive', '--format=tar', '--output', archive, PIN, *paths], timeout=120)
    source.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(source, filter='data')
    source_manifest = job.work / 'userspace-source-manifest.json'
    save(source_manifest, dict(commit=PIN, files=mode_manifest(source)))
    original = source / paths[1]
    if sha(job.kit / USERSPACE_RECIPE) != sha(original):
        raise Stop('Reteta Swift din kit nu este originalul fixat si nu are o varianta locala recunoscuta.')
    hook = job.kit / 'hooks/02-golden-gate-userspace'
    rosetta = hook / 'inputs/golden_gate_userspace/rosetta.dmg'
    manifest = load(job.kit / 'step12-manifest.json')
    expected = manifest['files'][str(rosetta.relative_to(job.kit))]['sha256']
    output = job.work / 'userspace-generated'
    request = job.work / 'userspace-request.json'
    save(request, dict(source=str(source.relative_to(job.repo)), output=str(output.relative_to(job.repo)),
                       hook=str(hook.relative_to(job.repo)), rosetta=str(rosetta.relative_to(job.repo)),
                       rosetta_sha256=expected, generator_make_sha256=sha(source / 'tools/shared-cache/make'),
                       original_recipe_sha256=sha(original), runtime_gate_sha256=sha(hook / 'prespecialization.py'),
                       source_manifest_sha256=sha(source_manifest)))
    print('    Pregatesc corectia Swift pentru ImageIO si CMPhoto din profilul NVIDIA.', flush=True)
    job.command(job.py + [Path(__file__).resolve(), '--internal-userspace-plan', request], root=True, timeout=7200,
                cleanup_signal=signal.SIGINT, cleanup_grace=180)
    publish_userspace_variant(job, output, proof)
    return proof



class Job:
    def __init__(self,repo,mode):
        self.repo=repo; self.mode=mode; self.local=repo/'local/mbp91'
        self.stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work=repo/'store/tmp'/('mbp91-step12-'+self.stamp); self.work.mkdir(parents=True)
        self.logpath=self.local/'step12-build.log'; self.result=self.local/'step12-result.json'
        self.statefile=self.local/'step12-state.json'
        self.state=load(self.statefile) if self.statefile.is_file() else {}
        for p in (self.logpath,self.result,self.statefile):
            if p.is_file(): shutil.copy2(p,self.work/('previous-'+p.name))
        self.log=self.logpath.open('w',buffering=1)
        self.env={k:v for k,v in os.environ.items() if not k.startswith(('DYLD_','PYTHON'))}
        for k in ('KIT_ON_DRIVE','GOLDEN_LOCK','OCLP_REPO','OCLP_TAR','CACHE','SKIP_OPTIONAL','GOLDEN_CRYPTEX_CACHE'):
            self.env.pop(k,None)
        self.env['GOLDEN_CRYPTEX_CACHE']=''
        self.space_monitor_floor=None
        self.py=[sys.executable,'-I','-B']; self.mounts=[]
        self.report=dict(schema=VERSION,patcher_commit=PIN,model=MODEL,golden_build=GOLDEN,donor_build=DONOR,
            mode=mode,commands=[],errors=[],step_complete=False,kit_prepared=False,image_built=False,
            final_efi_prepared=False,official_rows_modified=False,**SCOPE)
        self.rows={};self.row_copies=[];self.official={};self.kit=None;self.image_local=None

    def command(self,args,capture=False,root=False,timeout=3600,allowed=(0,),cleanup_grace=5,
                cleanup_signal=signal.SIGTERM):
        argv=list(map(str,args))
        if root:
            if subprocess.run(['/usr/bin/sudo','-n','-v'],capture_output=True).returncode:
                print('    Solicit acces administrator; introdu parola in Terminal.',flush=True)
                if subprocess.run(['/usr/bin/sudo','-v']).returncode: raise Stop('Autorizare refuzata')
            argv=['/usr/bin/sudo','-n']+argv
        self.log.write('\n$ '+shlex.join(argv)+'\n');start=time.monotonic()
        path=self.work/f'command-{len(self.report["commands"]):03d}.log'
        launch={'start_new_session':True}
        if root:launch={'start_new_session':False,'process_group':0,'stdin':subprocess.DEVNULL}
        with path.open('w') as sink:
            p=subprocess.Popen(argv,cwd=self.repo,env=self.env,stdout=sink,stderr=subprocess.STDOUT,**launch)
            with path.open(errors='replace') as reader:
                pulse=start
                try:
                    while p.poll() is None:
                        self.log.write(reader.read())
                        time.sleep(.2);now=time.monotonic()
                        if now-start>timeout:raise Stop('Timeout: '+argv[0])
                        if now-pulse>=30 and self.space_monitor_floor is not None:
                            free=shutil.disk_usage(self.repo/'store').free
                            if free<self.space_monitor_floor:
                                raise Stop(f'Spatiul liber a coborat la {space_gb(free)} in timpul lucrului; opresc cu demontarea imaginii pentru a pastra rezerva.')
                        if now-pulse>=30:
                            print('    Proces in curs; log: local/mbp91/step12-build.log',flush=True);pulse=now
                    self.log.write(reader.read())
                except BaseException:
                    for sig in (cleanup_signal,signal.SIGKILL):
                        try:os.killpg(p.pid,sig)
                        except ProcessLookupError:pass
                        except OSError as e:self.report.setdefault('cleanup_warnings',[]).append(str(e))
                        deadline=time.monotonic()+(cleanup_grace if sig!=signal.SIGKILL else 5)
                        cleanup_pulse=time.monotonic()
                        while p.poll() is None and time.monotonic()<deadline:
                            self.log.write(reader.read());time.sleep(.2)
                            if time.monotonic()-cleanup_pulse>=30:
                                print('    Astept demontarea imaginii temporare si inchiderea procesului.',flush=True)
                                cleanup_pulse=time.monotonic()
                        if p.poll() is not None:break
                        if sig==signal.SIGKILL:
                            self.report.setdefault('cleanup_warnings',[]).append('Proces fara terminare confirmata: '+str(p.pid))
                    self.log.write(reader.read());raise
        text=path.read_text(errors='replace')
        entry=dict(argv=argv,returncode=p.returncode,elapsed_s=round(time.monotonic()-start,2))
        if root:entry['launch_mode']='same-session-separate-process-group'
        self.report['commands'].append(entry)
        if p.returncode not in allowed:
            print('\n'.join(text.splitlines()[-20:]),flush=True)
            raise Stop(f'Comanda a esuat ({p.returncode}): {argv[0]}; vezi step12-build.log')
        return text

    def save(self):
        save(self.result,self.report);save(self.statefile,self.state)

    def setup(self):
        if any(c.isspace() for c in str(self.repo)):
            raise Stop('Constructorul Hao pentru intrari necesita o cale fara spatii')
        if self.command(['/usr/bin/git','rev-parse','HEAD'],True).strip()!=PIN:
            raise Stop('Commit Hao diferit de cel fixat')
        self.prior={n:load(self.local/f'step{n}-result.json') for n in (4,8,9,10,11)}
        for n,r in self.prior.items():assert_prior_result(r,n)
        if not self.prior[8].get('bootstrap_payload_ready') or self.prior[8].get('runtime_payload_complete'):
            raise Stop('Raportul payload-ului nu descrie candidatul experimental revizuit')
        if not all(self.prior[11].get(k) for k in ('driver_tree_prepared','kernel_collections_built','repairs_built')):
            raise Stop('Rezultatele kernelului de la pasul 11 sunt incomplete')
        self.s11=load(self.local/'step11-state.json')
        self.target=self.repo/'pipeline/targets/mbp91.json';target=load(self.target)
        if target.get('model')!=MODEL or target.get('board_id')!=BOARD:
            raise Stop('Tinta hardware a fost schimbata')
        self.profile=self.repo/'pipeline/profiles/mbp91-26B131.json'
        if load(self.profile).get('target')!='mbp91':raise Stop('Profil pentru alt model')
        self.recipe=load(self.repo/'pipeline/assemblies/mbp91-26B131.json')
        if (self.recipe.get('target'),self.recipe.get('golden_build'),self.recipe.get('donor_build'))!=('mbp91',GOLDEN,DONOR):
            raise Stop('Identitatea asamblarii a fost schimbata')
        if set(self.recipe.get('inputs',{}))!=set(BASE_ROLES) or self.recipe['inputs']['hardware']!='oclp_hardware_mbp91':
            raise Stop('Roluri de asamblare sau pachet hardware incorecte')
        self.L=runpy.run_path(str(self.repo/'pipeline/lock.py'))
        self.P=runpy.run_path(str(self.repo/'pipeline/patches.py'))
        optional={}
        self.plan=self.P['plan'](str(self.profile),str(self.target),GOLDEN+'/'+DONOR,
                                skip=('caches',),record=optional)
        self.recipe_rows=required_plan(self.plan)
        self.report['plan']=[{'stage':s,'name':n,'inputs':r} for s,n,r in self.plan]
        self.report['optional']=optional
        paths=list(SOURCE_PATHS)+['pipeline/stages/'+p for p in HELPERS]
        paths += [str(Path(self.P['directory'](n,str(self.repo/'patches'))).relative_to(self.repo)) for _,n,_ in self.plan]
        changes=self.command(['/usr/bin/git','diff','--name-only',PIN,'--',*paths],True).splitlines()
        if sha(self.repo/DETECT_RULES)!=DETECT_RULES_SHA:
            raise Stop('Regulile hardware locale difera de extensia 9,1 verificata la pasul 3')
        unexpected=[path for path in changes if path!=DETECT_RULES]
        if unexpected:raise Stop('Surse de asamblare schimbate fata de commitul fixat: '+', '.join(unexpected))
        self.report['local_detection_rules_sha256']=DETECT_RULES_SHA
        tracked=self.command(['/usr/bin/git','ls-tree','-r',PIN,'--',*paths],True)
        self.report['source_tree_listing_sha256']=hashlib.sha256(tracked.encode()).hexdigest()
        (self.local/'step12-source-tree.txt').write_text(tracked)
        for path,want in [('pipeline/stages/inputs.sh',INPUTS_SHA),
                          ('pipeline/unpack/pristine-tools/fl.c',FL_C_SHA),
                          ('pipeline/unpack/pristine-tools/ent.plist',FL_ENT_SHA)]:
            if sha(self.repo/path)!=want:raise Stop('Sursa fixata difera: '+path)
        self.G=runpy.run_path(str(self.repo/'pipeline/golden-run'))
        self.K=runpy.run_path(str(self.repo/'pipeline/kit.py'))
        r4=self.prior[4];self.oclp=inside(self.repo,r4['oclp_source']);self.base=inside(self.repo,r4['efi_path'])
        self.oclp_revision=self.command(['/usr/bin/git','-C',self.oclp,'rev-parse','HEAD'],True).strip()
        if self.command(['/usr/bin/git','-C',self.oclp,'rev-parse','HEAD^{tree}'],True).strip()!=OCLP_TREE:
            raise Stop('Arbore OCLP diferit')
        if self.command(['/usr/bin/git','-C',self.oclp,'diff','--name-only','HEAD'],True).strip():
            raise Stop('Sursele OCLP locale au fost modificate')
        if self.oclp_revision!=r4['oclp_reconstructed_commit']:raise Stop('Revizia OCLP locala difera')
        efi_record=self.local/'step4-base-efi-record.json'
        if sha(efi_record)!=r4['base_efi_record_sha256']:raise Stop('Raport EFI schimbat')
        self.base_record=load(efi_record)
        if self.base_record['target_sha256']!=sha(self.target):raise Stop('Tinta difera de cea folosita pentru EFI')
        for rel,want in self.base_record['files'].items():
            if sha(inside(self.base,rel))!=want:raise Stop('Fisier EFI de baza schimbat: '+rel)
        self.base_config=plistlib.loads((self.base/'EFI/OC/config.plist').read_bytes())
        if self.base_config.get('#Revision',{}).get('Original-Model')!=MODEL:
            raise Stop('EFI-ul de baza apartine altui model')
        self.recipe['oclp_upstream_equivalent']=self.recipe['oclp']
        self.recipe['oclp']=self.oclp_revision
        self.recipe['skip_optional']=['caches'];self.recipe['experimental_scope']=dict(SCOPE)
        self.sdk=self.command(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],True).strip()
        self.clang=self.command(['/usr/bin/xcrun','--find','clang'],True).strip()
        self.env.update(SDKROOT=self.sdk,PYTHONDONTWRITEBYTECODE='1',MACOSX_DEPLOYMENT_TARGET='26.0')
        wrappers=self.work/'tools';wrappers.mkdir()
        for name,content in [('python3','#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -B "$@"\n'),
                             ('cc','#!/bin/sh\nexec '+shlex.quote(self.clang)+' -isysroot '+shlex.quote(self.sdk)+' "$@"\n')]:
            w=wrappers/name;w.write_text(content);w.chmod(0o755)
        self.env['PATH']=str(wrappers)+':'+str(Path(sys.executable).parent)+':/usr/bin:/bin:/usr/sbin:/sbin:/opt/local/bin'
        host=self.command(['/usr/bin/sw_vers','-productVersion'],True).strip()
        if not host.startswith('26.'):raise Stop('Acest constructor local este pregatit pentru gazda Tahoe 26.x')
        self.report['host']=dict(os_version=host,architecture=platform.machine(),sdk=self.sdk)
        self.kdk_expansion=self.s11.get('kdk_expansion',{})
        if self.kdk_expansion.get('source_sha256')!=KDK_SHA:raise Stop('Provenienta KDK nu corespunde')
        self.kdk=inside(self.repo,self.kdk_expansion['root']);kid=self.kdk_expansion['identity']
        v=self.kdk/'System/Library/CoreServices/SystemVersion.plist'
        if sha(v)!=kid['system_version_sha256'] or plistlib.loads(v.read_bytes()).get('ProductBuildVersion')!=DONOR:
            raise Stop('KDK/SystemVersion schimbat')
        for name,rec in kid['donors'].items():
            if sha(inside(self.kdk,rec['path']))!=rec['sha256']:raise Stop('Donor KDK schimbat: '+name)
        self.report['kdk_reused']=dict(path=str(self.kdk.relative_to(self.repo)),identity=kid,
            source_dmg_sha256=KDK_SHA,expanded_tree_compared_to_source=False)
        for tool in ('/sbin/mount_msdos','/usr/sbin/bless','/usr/bin/hdiutil','/usr/sbin/diskutil',
            '/System/Library/Filesystems/apfs.fs/Contents/Resources/newfs_apfs',
            '/System/Library/Filesystems/apfs.fs/Contents/Resources/apfs_prepare_cryptex'):
            if not os.access(tool,os.X_OK):raise Stop('Utilitar de asamblare lipsa: '+tool)
        identity=dict(version=VERSION,reports={str(n):sha(self.local/f'step{n}-result.json') for n in self.prior},
            step11_state=sha(self.local/'step11-state.json'),target=sha(self.target),profile=sha(self.profile),
            recipe=self.recipe,sources=self.report['source_tree_listing_sha256'],local_detection=DETECT_RULES_SHA,
            clang=sha(self.clang),sdk=self.sdk,host_os=host)
        self.report['script_sha256']=sha(Path(__file__))
        self.identity=fingerprint(identity);self.report['identity']=identity;self.report['fingerprint']=self.identity
        if self.state.get('fingerprint')!=self.identity:self.state={}
        self.state['fingerprint']=self.identity
        self.report['warnings']=['KextExcludeList absent in step11 work collections; final layout/boot remains to assess.']
        self.save()

    def original_row(self,name):
        for group,folder in [('golden',self.repo/'pipeline/inputs/golden'/GOLDEN),
                             ('donor',self.repo/'pipeline/inputs'/DONOR),
                             ('common',self.repo/'pipeline/inputs/common')]:
            f=folder/name
            if f.is_file():
                self.official[str(f.relative_to(self.repo))]=sha(f)
                return group,f
        raise Stop('Intrare Hao lipsa: '+name)

    def catalog(self):
        catalog=self.work/'inputs'
        folders={'golden':catalog/'golden'/GOLDEN,'donor':catalog/DONOR,'common':catalog/'common'}
        for folder in folders.values():folder.mkdir(parents=True)
        expected={}
        for n,names in [(9,METAL_ROWS),(10,AUX_ROWS)]:
            records=self.prior[n].get('artifacts',{})
            if set(records)!=set(names):raise Stop('Lista de pachete difera la pasul '+str(n))
            for name in names:
                r=records[name]
                if r.get('status')!='prepared':raise Stop('Pachet nepregatit: '+name)
                expected[name]=(self.local/f'step{n}-inputs'/name,r['path'],r['content_sha256'])
        for name in KERNEL_ROWS:
            r=self.prior[11]['local_inputs'][name]
            expected[name]=(self.local/'step11-inputs'/name,r['path'],r['sha256'])
        r8=self.prior[8]
        expected['hao_runtime']=(self.local/'step8-bootstrap-input.txt',r8['bootstrap_artifact'],r8['payload_content_sha256'])
        needed=self.recipe_rows | set(self.recipe['inputs'].values()) | {'kdk','fl','python_x86_64','python_site','psp_2.0.5'}
        for name in sorted(needed):
            group,official=self.original_row(name)
            source=expected[name][0] if name in expected else official
            digest,path,comments=parse_row(source.read_text(),self.repo,name)
            if name in expected:
                _,relative,want=expected[name]
                if digest!=want or path.resolve()!=inside(self.repo,relative).resolve():
                    raise Stop('Intrarea locala nu corespunde raportului: '+name)
                group='golden'
            if name=='python_site':
                path=inside(self.repo,self.prior[4]['python_site']);digest=self.prior[4]['python_site_sha256'];comments='# Local verified Python site from step4.'
                group='common'
            if name=='fl':
                path=self.fl;digest=sha(path);comments='# Local x86_64 Tahoe firmlink tool, not upstream byte identity.';group='common'
            if digest=='-':
                relative=str(path.relative_to(self.repo))
                want=self.command(['/usr/bin/git','rev-parse',PIN+':'+relative],True).strip()
                if blob(path)!=want:raise Stop('Sursa fara hash a fost schimbata: '+name)
                digest=sha(path)
                comments+='\n# Repository source pinned by '+PIN+'; concretely hashed for this local kit.'
            if not path.exists():raise Stop('Fisier sau pachet lipsa: '+name+' -> '+str(path))
            folder=folders[group];f=folder/name
            f.write_text(row_text(digest,path,comments))
            self.rows[name]=dict(name=name,sha256=digest,path=str(path),lock=str(folder.relative_to(self.repo)),
                                 origin=str(source.relative_to(self.repo)),group=group)
        if self.rows['kdk']['sha256']!=KDK_SHA or self.rows['python_x86_64']['sha256']!=PYTHON_SHA:
            raise Stop('Versiuni KDK/Python neasteptate')
        self.folders=folders
        save(self.local/'step12-inputs.json',self.rows)
        self.report['input_rows']=self.rows;self.report['official_row_hashes']=self.official
        self.save()

    def measured_space(self,phase,budget):
        try:floor_gb=float(os.environ.get('HAO_DISK_FLOOR_GB','40'))
        except (TypeError,ValueError):raise Stop('Prag de rezerva invalid')
        if not math.isfinite(floor_gb) or floor_gb<0:
            raise Stop('Prag de rezerva invalid')
        floor=int(floor_gb*1_000_000_000)
        need=budget.get('projected_bytes')
        if type(need) is not int or need<0:
            raise Stop('Necesarul calculat trebuie sa fie un numar intreg nenegativ de octeti')
        free=shutil.disk_usage(self.repo/'store').free
        row=dict(phase=phase,free_bytes=free,projected_additional_bytes=need,
                 reserve_bytes=floor,minimum_free_bytes=need+floor,budget=budget,
                 basis='Actual selected inputs and actual staged kit; planning allowance, not a prediction of exact APFS allocation')
        self.report.setdefault('measured_space_checks',[]).append(row)
        self.report['space_policy']='measured-local-v1'
        self.report['disk_budget_gb']=need/1_000_000_000
        self.save()
        print(f'    Spatiu [{phase}]: liber {space_gb(free)}; scrieri bugetate {space_gb(need)}; rezerva {space_gb(floor)}.',flush=True)
        components=sorted(budget.get('components',[]),key=lambda c:c['bytes'],reverse=True)
        for component in components[:12]:
            print(f"      {component['label']}: {space_gb(component['bytes'],3)}",flush=True)
        if len(components)>12:
            other=sum(c['bytes'] for c in components[12:])
            print(f'      Alte componente masurate ({len(components)-12}): {space_gb(other,3)}',flush=True)
        external=os.environ.get('HAO_DISK_CHECK','').strip()
        if external:
            # An explicitly configured host-wide guard remains authoritative.
            guard=runpy.run_path(str(self.repo/'pipeline/diskguard.py'))
            guard['check'](need/1e9,'mbp91-step12-sized',phase,str(self.repo/'store'))
        if free < need+floor:
            kept='Kitul verificat ramane reutilizabil.' if self.state.get('kit') else 'Intrarile existente raman disponibile.'
            raise Stop(f'Spatiul masurat pentru {phase} necesita {space_gb(need+floor)}; disponibili {space_gb(free)}. '+kept+' Este necesar mai mult spatiu liber pentru aceasta etapa.')
        self.space_monitor_floor=floor
        print(f'    Rezerva estimata dupa aceasta etapa: {space_gb(free-need)}.',flush=True)

    def fl_environment_failure(self,error):
        failed=dict(self.report['commands'][-1]) if self.report['commands'] else {}
        killed=failed.get('argv')==[str(self.fl)] and failed.get('returncode')==-9
        probe=self.work/'probe-result.json'
        if probe.is_file():
            result=load(probe)
            killed=killed or any(c.get('argv',[])[:1]==[str(self.fl)] and c.get('returncode')==-9
                                 for c in result.get('commands',[]))
        if not killed:raise error
        evidence=dict(error=str(error),failed_command=failed,fl_sigkill=bool(killed),checks={})
        print('    Verific mediul curent pentru entitlementul privat APFS:',flush=True)
        for name,args in (('sip_status',['/usr/bin/csrutil','status']),
                          ('active_bootargs',['/usr/sbin/sysctl','-n','kern.bootargs'])):
            try:
                output=self.command(args,capture=True,timeout=10)
                evidence['checks'][name]=dict(argv=args,output=output)
                print('      '+name+': '+(output.strip() or '(gol)'),flush=True)
            except Stop as diagnostic_error:
                evidence['checks'][name]=dict(argv=args,error=str(diagnostic_error))
                print('      '+name+': '+str(diagnostic_error),flush=True)
        self.report['fl_host_failure']=evidence;self.save()
        reason='fl a fost terminat prin SIGKILL (semnal 9), compatibil cu refuzul AMFI al entitlementului privat. '
        raise Stop(reason+'Mediul de construire documentat de Hao foloseste SIP dezactivat si argumentul de boot activ '
                   'amfi_get_out_of_my_way=1. sudo singur nu asigura acest mediu; starea curenta este afisata mai sus.') from error

    def fl_tool(self):
        reuse=self.state.get('fl')
        if reuse:
            p=inside(self.repo,reuse['path'])
            if sha(p)!=reuse['sha256']:raise Stop('Utilitarul APFS local a fost schimbat')
            self.fl=p;folder=p.parent
            print('    Utilitar APFS local: binar reutilizat; reverific executia si firmlink-ul in sesiunea curenta.',flush=True)
        else:
            folder=self.repo/'store/artifacts'/('mbp91-fl-tahoe-step12-'+self.stamp);folder.mkdir()
            self.fl=folder/'fl';src=self.repo/'pipeline/unpack/pristine-tools'
            compile_=[self.clang,'-O2','-Wall','-arch','x86_64','-isysroot',self.sdk,'-mmacosx-version-min=26.0',
                      str(src/'fl.c'),'-o',self.fl]
            self.env['MACOSX_DEPLOYMENT_TARGET']='26.0'
            self.command(compile_)
            self.command(['/usr/bin/codesign','--force','--sign','-','--entitlements',src/'ent.plist',self.fl])
        self.command(['/usr/bin/codesign','--verify','--strict',self.fl])
        if macho_slices(self.fl)!=[(16777223,3)]:raise Stop('Utilitarul APFS nu este x86_64 generic')
        try:
            self.command([self.fl],allowed=(2,))
            self.command(['/usr/bin/true'],root=True,timeout=30)
            probe=self.work/'apfs-probe';probe.mkdir()
            request=self.work/'probe-request.json'
            save(request,dict(work=str(probe),fl=str(self.fl),fl_sha256=sha(self.fl),output=str(self.work/'probe-result.json')))
            self.command(self.py+[Path(__file__).resolve(),'--internal-fl-probe',request],root=True,timeout=900,cleanup_grace=140)
            result=load(self.work/'probe-result.json')
            if not result.get('passed'):raise Stop('Proba reala de firmlink APFS a esuat')
        except Stop as error:
            self.fl_environment_failure(error)
        record=dict(path=str(self.fl.relative_to(self.repo)),sha256=sha(self.fl),minimum_os='26.0',
            architecture='x86_64',source_sha256=FL_C_SHA,entitlements_sha256=FL_ENT_SHA,
            functional_probe=result,upstream_match=False)
        save(folder/'build.json',record);self.state['fl']=record;self.report['fl']=record;self.save()
        print('    Utilitar APFS Tahoe: semnatura si proba reala de firmlink verificate in sesiunea curenta.',flush=True)

    def prepare_assembly_donors(self):
        repair_assembly_donors(self)

    def preserve_partial_provenance(self):
        """Keep the completed stager receipt across failed resume attempts."""
        partial=self.state.get('partial_kit')
        if not partial or self.state.get('kit'):return
        origin=self.state.get('partial_kit_origin')
        if origin is None:
            result=self.work/'previous-step12-result.json'
            state=self.work/'previous-step12-state.json'
            if not result.is_file() or not state.is_file():
                raise Stop('Lipseste provenienta kitului partial; copiile existente sunt pastrate.')
            previous=load(result);saved=load(state)
            if (saved.get('partial_kit')!=partial or saved.get('fingerprint')!=self.state.get('fingerprint')
                    or previous.get('fingerprint')!=self.state.get('fingerprint')):
                raise Stop('Provenienta initiala a kitului partial difera de starea salvata.')
            origin=dict(kit=partial,result=str(result.relative_to(self.repo)),state=str(state.relative_to(self.repo)),
                        result_sha256=sha(result),state_sha256=sha(state))
            self.state['partial_kit_origin']=origin
        if not isinstance(origin,dict) or origin.get('kit')!=partial:
            raise Stop('Referinta de reluare nu corespunde kitului partial.')
        for role in ('result','state'):
            path=inside(self.repo,origin[role])
            if (path.is_symlink() or not path.is_file() or path.parent.parent!=self.repo/'store/tmp'
                    or not path.parent.name.startswith('mbp91-step12-') or sha(path)!=origin.get(role+'_sha256')):
                raise Stop('Raportul initial pastrat pentru reluare lipseste sau difera: '+role)
        self.report['partial_kit_origin']=origin
        self.save()

    def resume_partial_kit(self):
        partial=self.state.get('partial_kit')
        if not partial:return False
        origin=self.state.get('partial_kit_origin')
        result_path=inside(self.repo,origin['result']) if origin else self.work/'previous-step12-result.json'
        state_path=inside(self.repo,origin['state']) if origin else self.work/'previous-step12-state.json'
        old=load(result_path)
        old_state=load(state_path)
        if (old.get('fingerprint')!=self.identity or old_state.get('fingerprint')!=self.identity
                or old_state.get('partial_kit')!=partial or old.get('kit_prepared') or old.get('image_built')):
            raise Stop('Kitul partial nu apartine exact intrarilor curente si limitei de reluare.')
        kit=inside(self.repo,partial)
        if kit.is_symlink() or not kit.is_dir() or kit.parent!=self.repo/'store/artifacts':
            raise Stop('Calea kitului partial este neasteptata.')
        staging,changes=patched_stager((self.repo/'pipeline/stages/inputs.sh').read_text())
        expected_stager=dict(upstream_sha256=INPUTS_SHA,local_sha256=hashlib.sha256(staging.encode()).hexdigest(),changes=changes)
        if old.get('stager')!=expected_stager:raise Stop('Constructorul care a copiat kitul partial difera.')
        calls=[c for c in old.get('commands',[]) if c.get('argv',[])[:1]==['/bin/zsh']]
        if len(calls)!=1 or calls[0].get('returncode')!=0:
            raise Stop('Nu exista o singura copiere inputs.sh incheiata cu succes pentru reluare.')
        argv=calls[0]['argv']
        if len(argv)!=9:raise Stop('Argumente inputs.sh neasteptate in raportul anterior.')
        try:old_script=inside(self.repo,Path(argv[1]).relative_to(self.repo).as_posix())
        except ValueError:raise Stop('Constructorul anterior nu este in proiect.')
        old_work=old_script.parent
        expected_argv=['/bin/zsh',str(old_work/'inputs-local.sh'),str(kit),str(self.target),
            str(old_work/'inputs'/DONOR),str(old_work/'inputs/common'),self.oclp_revision,str(self.profile),'golden-first']
        if (argv!=expected_argv or old_work.parent!=self.repo/'store/tmp'
                or not old_work.name.startswith('mbp91-step12-') or sha(old_script)!=expected_stager['local_sha256']):
            raise Stop('Copia terminata nu corespunde kitului, surselor sau intrarilor curente.')
        after=old['commands'][old['commands'].index(calls[0])+1:]
        first=self.recipe['inputs']['native']; old_native=old.get('input_rows',{}).get(first,{})
        expected_tail=self.py+[self.repo/'pipeline/lock.py','path',inside(self.repo,old_native.get('lock','')),first]
        if (len(after)!=1 or after[0].get('returncode')!=1
                or after[0].get('argv')!=list(map(str,expected_tail))):
            raise Stop('Kitul partial nu s-a oprit inaintea primei copii de donori pentru asamblare.')
        for name in ('assembly-source','kit.json','input-locks','step12-manifest.json','step12-build.json'):
            if os.path.lexists(kit/name):raise Stop('Kitul partial a depasit limita de reluare: '+name)
        extras=kit/'assembly-inputs'
        if os.path.lexists(extras) and (extras.is_symlink() or not extras.is_dir() or any(extras.iterdir())):
            raise Stop('assembly-inputs trebuie sa lipseasca sau sa fie gol la reluare.')
        expected_plan=[[s,n,*rows] for s,n,rows in self.plan]
        if [line.split() for line in (kit/'patches.txt').read_text().splitlines() if line.strip()]!=expected_plan:
            raise Stop('Planul complet al kitului partial, inclusiv intrarile, difera.')
        if load(kit/'optional.json')!=dict(self.report['optional'],skip_optional=['caches']):
            raise Stop('Selectia componentelor optionale difera in kitul partial.')
        if load(kit/'profile.json')!=load(self.target)['oclp_hardware_profile']:
            raise Stop('Profilul hardware copiat in kitul partial difera.')
        actual=self.G['set_order'](kit)
        verified=[]
        print('    Verific toate intrarile deja copiate in kitul partial.',flush=True)
        def check_input(name,path):
            row=self.rows[name]; prior=old.get('input_rows',{}).get(name,{})
            if row['sha256']!=prior.get('sha256'):
                raise Stop('Intrarea copiata si-a schimbat identitatea: '+name)
            lock=inside(self.repo,row['lock']); prior_lock=inside(self.repo,prior['lock'])
            old_digest,old_path,old_comments=parse_row((prior_lock/name).read_text(),self.repo,name)
            new_digest,new_path,new_comments=parse_row((lock/name).read_text(),self.repo,name)
            if old_digest!=row['sha256'] or new_digest!=row['sha256'] or old_comments!=new_comments:
                raise Stop('Regulile de verificare ale intrarii copiate au fost schimbate: '+name)
            if name!='fl' and old_path.resolve()!=new_path.resolve():
                raise Stop('Sursa intrarii copiate a fost schimbata: '+name)
            if not path.exists() or path.is_symlink():raise Stop('Intrare copiata absenta sau symlink: '+name)
            if self.L['row_hash'](str(lock),name,str(path))!=row['sha256']:
                raise Stop('Continutul deja copiat difera de intrarea verificata: '+name)
            problems=self.L['check_row'](str(lock),name,str(path))
            if problems:raise Stop('; '.join(problems))
            verified.append(dict(name=name,path=str(path.relative_to(kit)),sha256=row['sha256']))
        for stage,name,folder in actual:
            destination=kit/('hooks' if stage=='oclp-hook' else 'post')/folder
            recipe=Path(self.P['directory'](name,str(self.repo/'patches')))
            original=recipe/'src' if stage=='oclp-hook' else recipe
            if mode_manifest(destination,without=('inputs','build'))!=mode_manifest(original,without=('inputs','build')):
                raise Stop('Sursele copiate ale retetei difera: '+name)
            rows=next(rows for s,n,rows in self.plan if (s,n)==(stage,name))
            for name_ in rows:check_input(name_,destination/'inputs'/name_)
        check_input('fl',kit/'pristine/fl');check_input('python_site',kit/'site')
        if sha(kit/'pristine/fl')!=sha(self.fl):raise Stop('Kitul partial contine alt utilitar APFS.')
        if sha(kit/'copy-hooks.py')!=sha(self.repo/'pipeline/stages/copy-hooks.py'):
            raise Stop('copy-hooks.py a fost schimbat in kitul partial.')
        if sha(kit/'oclp/Universal-Binaries.dmg')!=self.rows['psp_2.0.5']['sha256']:
            raise Stop('PSP copiat in kitul partial difera.')
        tracked=self.command(['/usr/bin/git','-C',self.oclp,'ls-tree','-rz',self.oclp_revision],capture=True)
        oclp_files=set()
        for item in tracked.split('\0'):
            if not item:continue
            header,name=item.split('\t',1);mode,kind,oid=header.split()
            if kind=='commit' and mode=='160000':continue
            if kind!='blob' or mode not in ('100644','100755','120000'):
                raise Stop('Tip neasteptat in sursa OCLP fixata: '+name)
            copied=inside(kit/'oclp',name);oclp_files.add(name)
            if mode=='120000':
                if not copied.is_symlink():raise Stop('Link OCLP copiat incorect: '+name)
                body=os.fsencode(os.readlink(copied))
                got=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
            else:
                if copied.is_symlink() or not copied.is_file() or bool(copied.stat().st_mode&0o111)!=(mode=='100755'):
                    raise Stop('Fisier OCLP copiat incorect: '+name)
                got=blob(copied)
            if got!=oid:raise Stop('Sursa OCLP din kitul partial a fost schimbata: '+name)
        if set(tree_files(kit/'oclp'))!=oclp_files|{'Universal-Binaries.dmg'}:
            raise Stop('Lista fisierelor OCLP din kitul partial difera de sursa fixata.')
        kdk_name=self.L['kdk_name'](self.rows['kdk']['path'])
        if sorted(p.name for p in (kit/'kdk').iterdir())!=[kdk_name]:
            raise Stop('Arborele KDK al kitului partial este ambiguu.')
        if self.L['row_sha256'](str(kit/'kdk'/kdk_name))!=self.L['row_sha256'](str(self.kdk)):
            raise Stop('Copia KDK a kitului partial difera de sursa verificata.')
        revisions=' '.join('%s r%d'%(name,self.P['revision'](name)) for _,name,_ in self.plan)
        manifest=(f'oclp {self.oclp_revision} ({self.oclp_revision}), PatcherSupportPkg {self.L["psp"](str(kit/"oclp"))}\n'
                  f'kdk {kdk_name} ({KDK_SHA[:16]})\nset {self.profile.stem}: {revisions}\nfoundation golden-first\n')
        if (kit/'MANIFEST.txt').read_text()!=manifest:raise Stop('Manifestul inputs.sh al kitului partial difera.')
        self.kit=kit;self.report['stager']=old['stager']
        self.report['partial_kit_resume']=dict(path=partial,previous_report_sha256=sha(result_path),
            completed_stager=calls[0],verified_staged_rows=verified,remaining_boundary='before assembly-inputs copies')
        self.save()
        print('    Kit partial verificat: reutilizez copiile existente si continui cu donorii de asamblare.',flush=True)
        return True

    def stage(self,resume=False):
        if not resume:
            self.kit=self.repo/'store/artifacts'/('mbp91-assembly-kit-26B131-step12-'+self.stamp)
            self.kit.mkdir();self.state['partial_kit']=str(self.kit.relative_to(self.repo));self.save()
            staging,changes=patched_stager((self.repo/'pipeline/stages/inputs.sh').read_text())
            script=self.work/'inputs-local.sh';script.write_text(staging);script.chmod(0o755)
            self.report['stager']=dict(upstream_sha256=INPUTS_SHA,local_sha256=sha(script),changes=changes)
            self.env.update(GOLDEN_LOCK=str(self.folders['golden']),SKIP_OPTIONAL='caches',CACHE=str(self.work/'cache'),
                OCLP_REPO=str(self.oclp),HAO_STEP12_STAGES=str(self.repo/'pipeline/stages'),HAO_STEP12_KDK_ROOT=str(self.kdk))
            self.command(['/bin/zsh',script,self.kit,self.target,self.folders['donor'],self.folders['common'],
                self.oclp_revision,self.profile,'golden-first'],timeout=21600)
        actual=self.G['set_order'](self.kit)
        if [(s,n) for s,n,_ in actual]!=[(s,n) for s,n,_ in self.plan]:
            raise Stop('Planul copiat difera de planul verificat')
        for stage,name,folder in actual:
            if name=='hao-command':
                # make.sh archives committed CLI code; carry the reviewed local hardware data too.
                destination=self.kit/'post'/folder/'build/hao'/DETECT_RULES
                if not destination.parent.is_dir():raise Stop('Structura hao-command copiata incorect')
                shutil.copy2(self.repo/DETECT_RULES,destination)
            rows=next(r for s,n,r in self.plan if n==name)
            for row in rows:self.add_copy(row,('hooks' if stage=='oclp-hook' else 'post')+'/'+folder+'/inputs/'+row)
        extras=self.kit/'assembly-inputs';extras.mkdir(exist_ok=resume)
        for role,row in self.recipe['inputs'].items():
            r=self.rows[row]
            self.command(self.py+[self.repo/'pipeline/lock.py','path',inside(self.repo,r['lock']),row],timeout=7200)
            self.command(['/usr/bin/ditto',r['path'],extras/role],timeout=7200)
            self.add_copy(row,'assembly-inputs/'+role)
        source=self.kit/'assembly-source';source.mkdir()
        for name in HELPERS:shutil.copy2(self.repo/'pipeline/stages'/name,source/name)
        shutil.copy2(self.repo/'pipeline/kit.py',source/'kit.py')
        commands=self.repo/'pipeline/stages'/('recovery-commands-'+DONOR+'.txt')
        if commands.is_file():shutil.copy2(commands,source/'recovery-commands.txt')
        preparer=Path('opencore_legacy_patcher/sys_patch/utilities/kdk_intel_payload.py')
        if sha(self.kit/'oclp'/preparer)!=sha(self.oclp/preparer):raise Stop('Constructor KDK OCLP copiat incorect')
        shutil.copy2(self.kit/'oclp'/preparer,source/'kdk_intel_payload.py')
        shutil.copy2(self.kit/'pristine/fl',source/'fl')
        self.command(['/usr/bin/ditto',self.repo/'tools/tahoe-donors',source/'tahoe-donors'])
        self.command(['/usr/bin/ditto',extras/'hardware/install-tools',source/'hardware'])
        self.command(['/usr/bin/ditto',self.base,source/'esp'])
        for rel,want in self.base_record['files'].items():
            if sha(inside(source/'esp',rel))!=want:raise Stop('Copie EFI de baza diferita: '+rel)
        self.G['stage_target'](self.recipe,self.kit)
        save(self.kit/'declared.json',self.G['declared_files'](self.kit))
        virtual_local='/private/var/hao-mbp91-step12-job'
        config=self.G['guest_config'](self.recipe,self.kit,virtual_local,kit_root=str(self.kit),cryptex_cache=False)
        kit_json=self.K['template'](config,'mbp91-26B131-local-step12',str(self.kit),virtual_local)
        kit_json['supported_architectures']=['x86_64'];kit_json['python_dirs']={'x86_64':'py-x86_64'}
        kit_json['local_scope']=dict(SCOPE)
        save(self.kit/'kit.json',kit_json);save(self.kit/'assembly.json',self.recipe)
        save(self.kit/'LOCAL-SCOPE.json',dict(SCOPE,notes=[
            'Uses the experimental step8 bootstrap, not a complete Hao ABI payload.',
            'No prelinked collections are copied from the kernel work volume.',
            'Fresh final collections and exact-image kernel repair binding are required.',
            'This kit is prepared for a full Intel Tahoe host, not certified as a USB Recovery installer.']))
        self.add_copy('fl','assembly-source/fl');self.add_copy('python_site','site')
        for p in (self.kit/'hooks').glob('*/prelinked'):
            if p.exists():raise Stop('Colectii prelinked neasteptate in kit')
        self.report['staged_recipes']=len(actual);self.report['base_efi_reused']=True
        self.report['prelinked_collections_used']=False
        self.report['staged_configuration']=kit_json
        shutil.copytree(self.work/'inputs',self.kit/'input-locks')
        for entry in self.row_copies:
            suffix=inside(self.repo,entry['lock']).relative_to(self.work/'inputs')
            entry['lock']=str((self.kit/'input-locks'/suffix).relative_to(self.repo))
        self.save()

    def add_copy(self,name,relative):
        r=self.rows[name]
        self.row_copies.append(dict(name=name,sha256=r['sha256'],lock=r['lock'],staged=relative))

    def verify_kit(self,reuse=False):
        request=self.work/'verify-kit.json'
        output=self.work/'kit-manifest.json'
        task=dict(repo=str(self.repo),kit=str(self.kit.relative_to(self.repo)),rows=self.row_copies,
                  output=str(output.relative_to(self.repo)))
        if reuse:task['expected_manifest']=str((self.kit/'step12-manifest.json').relative_to(self.repo))
        save(request,task)
        self.command(self.py+[Path(__file__).resolve(),'--internal-verify-kit',request],timeout=21600)
        if not reuse:shutil.copy2(output,self.kit/'step12-manifest.json')
        manifest=load(output)
        config=load(self.kit/'kit.json')
        rendered=self.K['render'](config,self.kit,self.work/'render-only',cryptex_cache=False)
        if 'disk' in rendered or rendered['environment'].get('HAO_TARGET_MODEL')!=MODEL:
            raise Stop('Configuratie de asamblare neasteptata')
        if not config.get('local_scope',{}).get('experimental_bootstrap'):
            raise Stop('Kit fara eticheta experimentala')
        self.command([self.kit/'py-x86_64/bin/python3.12','-I','-B','-c',
            'import platform,sys; assert platform.machine()=="x86_64"; assert sys.version_info[:2]==(3,12); print(sys.version)'])
        for rel,want in self.official.items():
            if sha(self.repo/rel)!=want:raise Stop('O intrare oficiala a fost schimbata in timpul pregatirii: '+rel)
        state=dict(path=str(self.kit.relative_to(self.repo)),manifest_sha256=sha(self.kit/'step12-manifest.json'),
                   rows=self.row_copies,recipe=self.recipe,official_rows=self.official)
        save(self.kit/'step12-build.json',dict(schema=VERSION,kit=state,scope=SCOPE,
            source_tree_listing_sha256=self.report['source_tree_listing_sha256'],base_efi_record_sha256=sha(self.local/'step4-base-efi-record.json')))
        self.state['kit']=state;self.state.pop('partial_kit',None);self.state.pop('partial_kit_origin',None)
        self.report.update(kit_prepared=True,kit=state,kit_reused=reuse,kit_manifest_entries=len(manifest['files']))
        self.save()

    def reuse_kit(self):
        old=self.state.get('kit')
        if not old:return False
        self.kit=inside(self.repo,old['path'])
        if sha(self.kit/'step12-manifest.json')!=old['manifest_sha256']:
            raise Stop('Manifestul kitului a fost schimbat')
        self.row_copies=old['rows'];self.official=old['official_rows'];self.recipe=old['recipe']
        for row in self.row_copies:
            if not inside(self.repo,row['lock']).is_dir():raise Stop('Snapshot de intrari lipsa pentru kit')
        self.verify_kit(reuse=True)
        print('    Kit Intel complet: reutilizat dupa verificarea continutului.',flush=True)
        return True


    def assemble_image(self):
        if self.reuse_image():return
        cleanup_failed_userspace_image(self,self.state['userspace_fix_origin'])
        print('    Calculez scrierile ramase din kitul efectiv, inclusiv imaginea de 80 GiB.',flush=True)
        self.measured_space('asamblare imagine',assembly_space_budget(self))
        self.image_local=self.repo/'store/tmp'/('mbp91-image-step12-'+self.stamp)
        self.image_local.mkdir()
        self.state['assembly_attempt']=str(self.image_local.relative_to(self.repo));self.save()
        # Render and check the actual destination before any privileged assembly.
        config=self.K['render'](load(self.kit/'kit.json'),self.kit,self.image_local,cryptex_cache=False)
        if 'disk' in config or Path(config['image'])!=self.image_local/'target.img':
            raise Stop('Se accepta numai o imagine noua in workspace-ul acestei rulari')
        save(self.local/'step12-assembly-config.json',config)
        self.report['assembly_work']=str(self.image_local.relative_to(self.repo));self.save()
        print('    Construiesc imaginea APFS de 80 GiB virtuali; kernelul si EFI-ul se leaga de aceasta imagine.',flush=True)
        self.command(['/bin/sh',self.kit/'assembly-source/golden-assemble.sh',self.kit,self.image_local,
                      '--owner','root:wheel','--no-cryptex-cache'],root=True,timeout=43200,
                      cleanup_signal=signal.SIGINT,cleanup_grace=180)
        self.report['image_built']=True;self.save()
        root=self.image_local/'work';build=load(root/'build.json')
        self.report['image_structure']=validate_build_metadata(build,self.recipe,self.image_local/'target.img')
        binding=load(root/'post/hao-opencore/kc-binder.json')
        manifest=load(root/'boot-efi/manifest.json')
        efi_checks=validate_final_efi(root/'boot-efi',manifest,self.base_config,
            boot_kc=root/'kc/BootKernelExtensions.kc',system_kc=root/'kc/SystemKernelExtensions.kc',binding_report=binding)
        self.report['final_efi_checks']=efi_checks
        # Reuse ocvalidate from the exact pinned OpenCore archive; verify its bytes before execution.
        _,oc_row=self.original_row('opencore_release')
        oc_sha,oc,_=parse_row(oc_row.read_text(),self.repo,'opencore_release')
        if sha(oc)!=oc_sha:raise Stop('Arhiva OpenCore de validare a fost schimbata')
        with zipfile.ZipFile(oc) as z:
            names=[n for n in z.namelist() if n.endswith('Utilities/ocvalidate/ocvalidate')]
            if len(names)!=1:raise Stop('ocvalidate macOS ambiguu in arhiva fixata')
            tool=self.work/'ocvalidate';tool.write_bytes(z.read(names[0]));tool.chmod(0o755)
        self.command([tool,root/'boot-efi/payload/EFI/OC/config.plist'])
        self.report['final_efi_prepared']=True;self.report['ocvalidate_ok']=True
        output=self.repo/'store/artifacts'/('mbp91-golden-image-26B131-step12-'+self.stamp)
        output.mkdir();self.report['image_artifact']=str(output.relative_to(self.repo));self.save()
        # Moving the completed image within this store does not duplicate its 80 GiB logical size.
        image=output/'GoldenGate-mbp91-26B131.img'
        os.replace(self.image_local/'target.img',image)
        shutil.copytree(root/'boot-efi',output/'boot-efi',symlinks=True)
        for source,name in [(root/'build.json','assembly-build.json'),
            (root/'post/hao-opencore/kc-binder.json','kc-binder.json'),
            (self.kit/'kit.json','kit.json')]:shutil.copy2(source,output/name)
        save(output/'LOCAL-SCOPE.json',dict(SCOPE,image_built=True,final_efi_prepared=True,
             built_from_kit=str(self.kit.relative_to(self.repo)),validation='Static assembly, collection binding and EFI validation only'))
        archive=output/'boot-efi.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted((output/'boot-efi').rglob('*')):
                if p.is_file():z.write(p,str(p.relative_to(output/'boot-efi')))
        receipt=self.work/'image-file-manifest.json'
        self.command(self.py+[Path(__file__).resolve(),'--internal-hash-image',image,'--hash-output',receipt],timeout=10800)
        image_record=load(receipt)
        image_record.update(image=str(image.relative_to(self.repo)),artifact=str(output.relative_to(self.repo)),
                            efi_zip_sha256=sha(archive),manifest_sha256=sha(output/'boot-efi/manifest.json'),
                            binding_sha256=sha(output/'kc-binder.json'),assembly_record_sha256=sha(output/'assembly-build.json'),
                            final_efi_checks=efi_checks,scope=dict(SCOPE))
        save(output/'build.json',image_record)
        self.state['image']=image_record;self.state.pop('assembly_attempt',None)
        self.report['image']=image_record;self.report['step_complete']=True;self.save()

    def reuse_image(self):
        record=self.state.get('image')
        if not record:return False
        image=inside(self.repo,record['image']);output=inside(self.repo,record['artifact'])
        receipt=self.work/'reused-image-hash.json'
        self.command(self.py+[Path(__file__).resolve(),'--internal-hash-image',image,'--hash-output',receipt],timeout=10800)
        actual=load(receipt)
        if actual['sha256']!=record['sha256'] or actual['bytes']!=record['bytes']:
            raise Stop('Imaginea salvata a fost schimbata')
        checks=[('boot-efi.zip','efi_zip_sha256'),('boot-efi/manifest.json','manifest_sha256'),
                ('kc-binder.json','binding_sha256'),('assembly-build.json','assembly_record_sha256')]
        if any(sha(output/p)!=record[key] for p,key in checks):raise Stop('Metadatele imaginii salvate au fost schimbate')
        # The independent EFI payload stays available for inspection; its exported hashes must still match.
        manifest=load(output/'boot-efi/manifest.json')
        if any(p.is_symlink() for p in (output/'boot-efi/payload').rglob('*')):
            raise Stop('Symlink neasteptat in payload-ul EFI salvat')
        actual_files={p.relative_to(output/'boot-efi/payload').as_posix():sha(p)
                      for p in (output/'boot-efi/payload').rglob('*') if p.is_file() and not p.is_symlink()}
        if actual_files!=manifest['files']:raise Stop('Payload EFI schimbat dupa asamblare')
        self.report.update(image_built=True,final_efi_prepared=True,image_reused=True,image=record,step_complete=True)
        self.save();print('    Imaginea finala existenta: reutilizata dupa verificarea SHA256.',flush=True)
        return True

    def finish(self):
        # Retain the assembler's exact failure layer and attachment state, even if it stopped before export.
        if self.image_local and (self.image_local/'work/build.json').is_file():
            summary=load(self.image_local/'work/build.json')
            self.report['assembler_status']=summary.get('status')
            self.report['assembler_error']=summary.get('error')
            self.report['attached_device']=summary.get('attached_device')
            self.report['assembly_steps']=summary.get('steps',[])
            if summary.get('cleanup_errors'):self.report['cleanup_warnings']=summary['cleanup_errors']
            shutil.copy2(self.image_local/'work/build.json',self.local/'step12-assembler-result.json')
        self.report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        self.save();self.log.close()
        archive=Path.home()/'Desktop'/ARCHIVE_NAME;temp=archive.with_suffix('.partial.zip')
        candidates=list(self.local.glob('step12-*.json'))+list(self.local.glob('step12-*.txt'))+[self.logpath]
        if self.image_local:
            root=self.image_local/'work'
            candidates += list((root/'post').rglob('*.json')) if (root/'post').exists() else []
            candidates += [root/'boot-efi/manifest.json',root/'boot-efi/payload/EFI/OC/config.plist']
        if self.report.get('partial_kit_origin'):
            candidates += [inside(self.repo,self.report['partial_kit_origin'][role]) for role in ('result','state')]
        if self.report.get('userspace_fix_origin'):
            origin=self.report['userspace_fix_origin']
            candidates += [inside(self.repo,origin['failure_log']),inside(self.repo,origin['attempt'])/'work/build.json']
        if self.kit and (self.kit/USERSPACE_VARIANT).is_dir():
            candidates += list((self.kit/USERSPACE_VARIANT).glob('*.json'))
        candidates += list(self.work.glob('userspace-*.json'))
        candidates += list(self.work.glob('*probe*.json'))
        candidates += list((self.work/'apfs-probe').rglob('probe-result.json')) if (self.work/'apfs-probe').exists() else []
        if self.kit:
            candidates += [self.kit/x for x in ('kit.json','assembly.json','LOCAL-SCOPE.json','step12-build.json',
                                              'optional.json','patches.txt','MANIFEST.txt','target-data.json')]
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(set(candidates)):
                if not p.is_file() or p.is_symlink():continue
                relative=p.relative_to(self.repo).as_posix()
                if p.stat().st_size<=5<<20:z.write(p,relative)
                else:
                    with p.open('rb') as f:f.seek(-(5<<20),2);tail=f.read()
                    z.writestr(relative+'.tail.txt',tail)
            z.write(Path(__file__).resolve(),Path(__file__).name)
            z.writestr('READ-ME.txt','Local Intel kit/image reports only. Apple images, drivers, Python and EFI binaries are not included.\n')
        os.replace(temp,archive)
        print('\nKit Intel pentru MacBookPro9,1: '+('DA' if self.report['kit_prepared'] else 'NU'))
        print('Imagine Golden Gate asamblata: '+('DA' if self.report['image_built'] else 'NU'))
        print('EFI final legat si verificat: '+('DA' if self.report['final_efi_prepared'] else 'NU'))
        if self.report.get('image'):print('Imagine: '+str(self.repo/self.report['image']['image']))
        elif self.kit:print('Kit: '+str(self.kit))
        print('Payload Hao complet / NVIDIA-GMUX functional / boot validat: NU; netestate sau incomplete.')
        print('Arhiva MICA de trimis: '+str(archive))


def internal_fl_probe(request):
    request=Path(request).resolve(strict=True);r=load(request)
    job=request.parent
    if not job.name.startswith('mbp91-step12-') or job.parent.name!='tmp' or job.parent.parent.name!='store':
        raise Stop('Proba APFS necesita un workspace step12 explicit')
    repo=job.parent.parent.parent
    work=Path(r['work']).resolve(strict=True);fl=Path(r['fl']).resolve(strict=True)
    output=Path(r['output']).resolve()
    if work!=job/'apfs-probe' or output!=job/'probe-result.json' or not fl.is_relative_to(repo/'store/artifacts'):
        raise Stop('Cai neasteptate pentru proba APFS')
    if sha(fl)!=r['fl_sha256']:raise Stop('Binar APFS diferit de cel compilat')
    def cancelled(signum,frame):
        # Enter the probe's finally block, instead of terminating while its image is attached.
        raise RuntimeError('Proba APFS intrerupta prin semnalul '+str(signum))
    signal.signal(signal.SIGTERM,cancelled)
    signal.signal(signal.SIGINT,cancelled)
    try:
        result=run_firmlink_probe(work,fl,inside(repo,'pipeline/stages/golden-layout.py'))
        save(output,result)
        print(json.dumps({'passed':result['passed'],'detached':result['detached']}))
    except BaseException:
        reports=sorted(work.glob('firmlink-probe-*/probe-result.json'))
        if reports:shutil.copyfile(reports[-1],output)
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('mode',nargs='?',choices=('build','prepare','assemble'),default='build')
    p.add_argument('--repo',type=Path,default=Path.cwd())
    p.add_argument('--internal-fl-probe',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--internal-userspace-plan',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--internal-verify-kit',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--internal-hash-image',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--hash-output',type=Path,help=argparse.SUPPRESS)
    a=p.parse_args();sys.dont_write_bytecode=True
    if a.internal_userspace_plan:internal_userspace_plan(a.internal_userspace_plan);return 0
    if a.internal_fl_probe:internal_fl_probe(a.internal_fl_probe);return 0
    if a.internal_verify_kit:verify_kit_worker(a.internal_verify_kit);return 0
    if a.internal_hash_image:
        image=a.internal_hash_image
        if not a.hash_output or not image.is_file() or image.is_symlink():raise Stop('Imagine sau destinatie hash invalida')
        save(a.hash_output,dict(sha256=sha(image),bytes=image.stat().st_size));return 0
    repo=a.repo.expanduser().resolve()
    if sys.platform!='darwin' or platform.machine()!='x86_64' or os.geteuid()==0:
        print('OPRIT: ruleaza pe iMac-ul Intel, ca utilizator normal, fara sudo.',file=sys.stderr);return 1
    if sys.version_info<(3,11):print('OPRIT: foloseste Python 3.14 din comanda indicata.');return 1
    if not (repo/'local/mbp91/step11-result.json').is_file():
        print('OPRIT: ruleaza din Desktop/hao-patcher-mbp91 dupa pasul 11 incheiat.');return 1
    os.umask(0o022)
    with (repo/'local/mbp91/step12.running.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('OPRIT: pasul 12 ruleaza deja.');return 1
        job=Job(repo,a.mode)
        try:
            print('1/6 Verific rezultatele anterioare, tinta 9,1 si sursele de asamblare.',flush=True)
            job.preserve_partial_provenance()
            job.setup()
            if a.mode=='assemble' and not job.state.get('kit'):
                raise Stop('Nu exista un kit verificat pentru aceste intrari; ruleaza modul build sau prepare')
            job.measured_space('proba APFS',dict(projected_bytes=4_000_000_000,
                components=[dict(label='Proba APFS de 3 GiB, compilare si metadate',bytes=4_000_000_000)]))
            print('2/6 Pregatesc utilitarul APFS pentru Tahoe si verific proba de firmlink.',flush=True)
            job.fl_tool()
            print('3/6 Reunesc intrarile locale si EFI-ul de baza in kitul Intel.',flush=True)
            reused=job.reuse_kit()
            if not reused:
                job.prepare_assembly_donors()
                job.catalog()
                partial=job.resume_partial_kit()
                print('    Calculez copiile ramase ale kitului.' if partial else
                      '    Calculez copiile numai din intrarile selectate ale kitului.',flush=True)
                job.measured_space('completare kit' if partial else 'pregatire kit',
                    remaining_staging_space_budget(job) if partial else staging_space_budget(job))
                job.stage(resume=partial)
            print('4/6 Verific pachetele copiate, configuratia si integritatea kitului.',flush=True)
            if not reused:job.verify_kit()
            prepare_userspace_variant(job)
            print('5/6 '+('Kit pregatit; modul prepare se opreste inaintea asamblarii.' if a.mode=='prepare'
                          else 'Asamblez imaginea si verific legatura kernel/EFI.'),flush=True)
            if a.mode=='prepare':job.report['step_complete']=True;job.save()
            else:job.assemble_image()
            print('6/6 Salvez artefactele si raportul mic de verificare.',flush=True)
        except (Exception,SystemExit,KeyboardInterrupt) as error:
            message=str(error) or type(error).__name__
            job.report['errors'].append({'error':message,'traceback':traceback.format_exc()})
            job.report['step_complete']=False;job.log.write(traceback.format_exc())
            print('OPRIT: '+message,flush=True)
        finally:
            job.finish()
        return 0 if job.report['step_complete'] else 1

if __name__=='__main__':
    raise SystemExit(main())
