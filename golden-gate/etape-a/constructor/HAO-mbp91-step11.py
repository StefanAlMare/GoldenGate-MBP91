#!/usr/bin/env python3
"""Hao / MacBookPro9,1: prepare a dual-GPU kernel tree, link work KCs and
build collection-specific IntelCommpage/early-VM repair candidates.

Run as the normal user on the Intel build Mac. Existing Apple inputs, the
hardware artifact and the base EFI are read, not rebuilt. A new APFS sparseimage
is used ONLY as a local kernel workspace. sudo is requested for copying files
with root ownership and for kmutil. Compilers run as the invoking user.

These are LOCAL EXPERIMENTAL artifacts, not a bootable OS image. In particular,
presence of NVIDIA/AppleMuxControl and successful linkage do not validate
Kepler rendering, GPU switching, sleep, or the incomplete Hao ABI payload.
No download, package installation, global security change or target-disk choice.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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
import zipfile

PIN = '6bd75aab112d1078acd8e75180eb510672461365'
VERSION = 'step11-dualgpu-kernel-v1'
GOLDEN, DONOR = '26B131', '25G342'
KERNEL_SHA = '3c9317518535791503970fbec322b9bba70e91f3a233536205ccd77b047ffc83'
KDK_SHA = '219f27c7e039b6ab3426496e0d5852d55a31d00b3d3984d855cba04377c5dba0'
PREPARER = 'opencore_legacy_patcher/sys_patch/utilities/kdk_intel_payload.py'
SLE = Path('System/Library/Extensions')
KC = Path('System/Library/KernelCollections')
KCB = Path('.darwin27-kc-build')
KF = 'tools/kernel-fixes/kernel-fixes'
SOURCE_DIRS = ('tools/kernel-fixes','tools/kernel-foundation','patches/darwin27-kernel',
               'patches/hao-opencore/src','pipeline/lock.py','pipeline/release-classes.json')
GPU_BUNDLES = ('AppleIntelHD4000Graphics.kext', 'AppleIntelFramebufferCapri.kext',
               'GeForce.kext', 'NVDAGK100Hal.kext', 'NVDAResman.kext', 'NVDAStartup.kext',
               'AppleGraphicsControl.kext', 'AppleMuxControl.kext')
ROWS = ('darwin27_kernel','tahoe_extensions_donors','oclp_hardware_mbp91','kdk',
        'tahoe_kmutil','tahoe_kc_builder')
HEX = re.compile(r'^[0-9a-f]{64}$')

class Stop(RuntimeError): pass

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

def fileset_ids(path):
    b=Path(path).read_bytes()
    if len(b)<32 or struct.unpack_from('<II',b)!=(0xfeedfacf,0x01000007): raise Stop('KC x86_64 asteptat')
    ftype,ncmd,nbytes=struct.unpack_from('<III',b,12)
    if ftype!=12 or ncmd>10000 or 32+nbytes>len(b): raise Stop('Header KC invalid')
    at=32; ids=[]
    for _ in range(ncmd):
        if at+8>32+nbytes: raise Stop('Comanda KC trunchiata')
        cmd,n=struct.unpack_from('<II',b,at)
        if n<8 or n%8 or at+n>32+nbytes: raise Stop('Lungime comanda KC invalida')
        if cmd==0x80000035:
            if n<32: raise Stop('LC_FILESET_ENTRY trunchiat')
            off=struct.unpack_from('<I',b,at+24)[0]
            if not 32<=off<n: raise Stop('Nume membru KC invalid')
            text=b[at+off:at+n]
            if b'\0' not in text: raise Stop('Nume membru KC neterminat')
            name=text.split(b'\0',1)[0].decode()
            if not name or name in ids: raise Stop('Membru KC gol/duplicat')
            ids.append(name)
        at+=n
    if at!=32+nbytes: raise Stop('Lungime totala comenzi KC invalida')
    return ids

def kext_inventory(root):
    """Inspect plists/binaries without executing or loading a driver."""
    root=Path(root).resolve(); result=[]
    for parent,dirs,files in os.walk(root/SLE,followlinks=False):
        dirs[:]=[x for x in dirs if not (Path(parent)/x).is_symlink()]
        p=Path(parent)
        if p.name!='Contents' or not p.parent.name.endswith('.kext') or 'Info.plist' not in files: continue
        info=p/'Info.plist'
        if info.is_symlink() and not info.resolve().is_relative_to(root): raise Stop('Info.plist extern')
        d=plistlib.loads(info.read_bytes()); name=p.parent.name
        ident=d.get('CFBundleIdentifier'); exe=d.get('CFBundleExecutable')
        item={'bundle':name,'path':p.parent.relative_to(root).as_posix(),'identifier':ident,
              'version':d.get('CFBundleVersion'),'compatible_version':d.get('OSBundleCompatibleVersion'),
              'required':d.get('OSBundleRequired'),'dependencies':d.get('OSBundleLibraries',{}),
              'personalities':d.get('IOKitPersonalities',{}),'info_sha256':sha(info)}
        if exe:
            binary=p/'MacOS'/relpath(exe)
            if not binary.resolve().is_relative_to(root): raise Stop('Executabil kext extern')
            item['executable']=binary.relative_to(root).as_posix()
            if binary.is_file():
                try:
                    slices=macho_slices(binary)
                    item.update(executable_sha256=sha(binary),slices=slices,
                                generic_x86_64=any(c==0x01000007 and s in (0,3) for c,s in slices))
                except Stop as e: item['binary_error']=str(e)
            else: item['binary_error']='executable_missing'
        result.append(item)
    return result

def gpu_report(items, config):
    result={'model':'MacBookPro9,1','required_bundles':{},'errors':[],
            'scope':'Static driver inclusion and dependency-presence checks, not GMUX/Metal runtime validation.',
            'kepler_rendering_validated':False,'gmux_switching_validated':False,'sleep_wake_validated':False}
    for name in GPU_BUNDLES:
        found=[e for e in items if e['bundle']==name]
        result['required_bundles'][name]=found
        if len(found)!=1: result['errors'].append(f'{name}: expected one bundle; found {len(found)}')
        elif found[0].get('executable') and not found[0].get('generic_x86_64'):
            result['errors'].append(name+': generic x86_64 executable missing or invalid')
    ids={e['identifier']:e for e in items if e.get('identifier')}
    todo=[e['identifier'] for v in result['required_bundles'].values() for e in v if e.get('identifier')]
    visited=set(); missing=[]
    while todo:
        name=todo.pop()
        if name in visited: continue
        visited.add(name)
        for dependency in ids.get(name,{}).get('dependencies',{}):
            if dependency.startswith('com.apple.kpi.') or dependency=='com.apple.kernel': continue
            if dependency not in ids: missing.append({'consumer':name,'missing':dependency})
            else: todo.append(dependency)
    result['missing_dependency_identifiers']=missing
    result['dependency_versions_validated']=False
    if missing: result['errors'].append('GPU/GMUX dependency identifiers missing from staged SLE')
    active=[e.get('BundlePath') for e in config.get('Kernel',{}).get('Add',[]) if e.get('Enabled')]
    result['restrict_events_enabled']='RestrictEvents.kext' in active
    result['oclp_revblock']=config.get('NVRAM',{}).get('Add',{}).get('4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102',{}).get('revblock')
    result['device_properties']=config.get('DeviceProperties',{})
    return result

def safe_copy(source,destination,anchor):
    """Copy bytes/modes/links only, as root, inside a dedicated workspace volume.
    Never copy BSD immutable/restricted flags, ACLs or source ownership.
    Existing destination symlinks are never traversed.
    """
    source,destination,anchor=map(Path,(source,destination,anchor))
    if not destination.parent.resolve().is_relative_to(anchor.resolve()): raise Stop('Destinatie externa')
    st=source.lstat()
    if destination.is_symlink(): destination.unlink()
    if stat.S_ISLNK(st.st_mode):
        if destination.exists():
            if destination.is_dir(): shutil.rmtree(destination)
            else: destination.unlink()
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.symlink_to(os.readlink(source)); os.lchown(destination,0,0); return
    if stat.S_ISDIR(st.st_mode):
        if destination.exists() and not destination.is_dir(): destination.unlink()
        destination.mkdir(parents=True,exist_ok=True); destination.chmod(0o755); os.chown(destination,0,0)
        for child in sorted(source.iterdir()): safe_copy(child,destination/child.name,anchor)
    elif stat.S_ISREG(st.st_mode):
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.is_dir(): shutil.rmtree(destination)
        shutil.copyfile(source,destination)
        os.chmod(destination,0o755 if st.st_mode & 0o111 else 0o644); os.chown(destination,0,0)
    else: raise Stop('Fisier special neacceptat: '+str(source))

def root_stage(plan_path):
    """Only privileged action exposed by this script: populate its mounted scratch root."""
    if sys.platform!='darwin' or os.geteuid()!=0: raise Stop('Copierea interna necesita macOS/root')
    plan=load(plan_path); repo=Path(plan['repo']).resolve(); anchor=inside(repo,plan['mount'])
    if not anchor.is_dir() or not os.path.ismount(anchor): raise Stop('Radacina nu este volum montat')
    if not anchor.parent.name.startswith('mbp91-step11-') or anchor.name!='System': raise Stop('Workspace nepermis')
    marker=anchor/'.hao-step11-workspace'
    if marker.read_text().strip()!=plan['token']: raise Stop('Identitatea workspace-ului difera')
    # Source paths must be within this project's store, never the booted /System.
    for operation in plan['copies']:
        src=inside(repo,operation['source']); dst=anchor/relpath(operation['destination'])
        if not src.resolve().is_relative_to(repo/'store'): raise Stop('Sursa externa store/')
        if not dst.parent.resolve().is_relative_to(anchor): raise Stop('Copiere prin symlink externa')
        if operation['mode'] not in ('merge','replace'): raise Stop('Operatie necunoscuta')
        if operation['mode']=='replace' and (dst.exists() or dst.is_symlink()):
            if dst.is_symlink() or dst.is_file(): dst.unlink()
            else: shutil.rmtree(dst)
        safe_copy(src,dst,anchor)
    for value in ('Library/Extensions','System/Library/KernelCollections',str(KCB)):
        dst=anchor/relpath(value)
        if not dst.parent.resolve().is_relative_to(anchor): raise Stop('Director extern')
        dst.mkdir(parents=True,exist_ok=True); dst.chmod(0o755); os.chown(dst,0,0)
    for p in (anchor/SLE).rglob('*'):
        if p.is_symlink() and not p.resolve().is_relative_to(anchor):
            raise Stop('Symlink extern in arborele kernel: '+str(p))
    print('Kernel workspace populated with root:wheel ownership.')

class Job:
    def __init__(self,repo):
        self.repo=repo; self.local=repo/'local/mbp91'; self.stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work=repo/'store/tmp'/('mbp91-step11-'+self.stamp); self.work.mkdir(parents=True)
        self.logpath=self.local/'step11-build.log'
        if self.logpath.exists(): shutil.copyfile(self.logpath,self.work/'previous-step11-build.log')
        self.log=self.logpath.open('w',buffering=1); self.mounts=[]; self.env=os.environ.copy()
        self.statefile=self.local/'step11-state.json'
        self.state=load(self.statefile) if self.statefile.is_file() else {}
        self.report={'schema':VERSION,'patcher_commit':PIN,'model':'MacBookPro9,1','golden_build':GOLDEN,
                     'donor_build':DONOR,'errors':[],'commands':[],'step_complete':False,
                     'kernel_collections_built':False,'repairs_built':False,'image_built':False,
                     'boot_validated':False,'kepler_rendering_validated':False,'gmux_switching_validated':False,
                     'external_hao_abi_payload_complete':False,'official_rows_modified':False}
        self.py=[sys.executable,'-I','-B']; self.result=self.local/'step11-result.json'
        self.outputs={}
    def command(self,args,capture=False,root=False,timeout=2400):
        argv=list(map(str,args))
        if root:
            probe=subprocess.run(['/usr/bin/sudo','-n','-v'],capture_output=True)
            if probe.returncode:
                print('    Autorizarea sudo trebuie reinnoita; introdu parola in Terminal.',flush=True)
                if subprocess.run(['/usr/bin/sudo','-v']).returncode: raise Stop('Autorizare refuzata')
            argv=['/usr/bin/sudo','-n']+argv
        self.log.write('\n$ '+shlex.join(argv)+'\n'); start=time.monotonic()
        text_path=self.work/f'command-{len(self.report["commands"]):03d}.log'
        with text_path.open('w') as f:
            p=subprocess.Popen(argv,cwd=self.repo,env=self.env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            pulse=start
            try:
                while p.poll() is None:
                    time.sleep(.2); now=time.monotonic()
                    if now-start>timeout: raise Stop('Timeout: '+argv[0])
                    if now-pulse>30:
                        print('    Proces in curs; log: local/mbp91/step11-build.log',flush=True); pulse=now
            except BaseException:
                with contextlib.suppress(ProcessLookupError): os.killpg(p.pid,signal.SIGTERM)
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError): os.killpg(p.pid,signal.SIGKILL)
                    p.wait()
                raise
        text=text_path.read_text(errors='replace'); self.log.write(text)
        self.report['commands'].append({'argv':argv,'returncode':p.returncode,'elapsed_s':round(time.monotonic()-start,2)})
        if p.returncode:
            print('\n'.join(text.splitlines()[-18:]),flush=True)
            raise Stop(f'Comanda a esuat ({p.returncode}): {argv[0]}; vezi step11-build.log')
        return text
    def save(self): save(self.result,self.report); save(self.statefile,self.state)
    def row(self,name):
        for d in (self.repo/'pipeline/inputs/golden'/GOLDEN,self.repo/'pipeline/inputs'/DONOR,self.repo/'pipeline/inputs/common'):
            f=d/name
            if f.is_file():
                lines=[l.partition('#')[0].strip() for l in f.read_text().splitlines()]
                lines=[l for l in lines if l]
                if len(lines)!=1: raise Stop('Intrare ambigua: '+name)
                digest,relative=lines[0].split(None,1); p=inside(self.repo,relative)
                if not HEX.fullmatch(digest): raise Stop('Intrare fara SHA256: '+name)
                got=self.L['row_hash'](str(d),name,str(p))
                if got!=digest: raise Stop('Integritate esuata: '+name)
                return p,digest
        raise Stop('Intrare lipsa: '+name)
    def setup(self):
        if self.command(['/usr/bin/git','rev-parse','HEAD'],True).strip()!=PIN: raise Stop('Commit Hao diferit de cel fixat')
        if self.command(['/usr/bin/git','diff','--name-only',PIN,'--',*SOURCE_DIRS],True).strip():
            raise Stop('Un constructor kernel upstream a fost modificat')
        prior=load(self.local/'step10-result.json')
        if not prior.get('step_complete') or prior.get('errors') or len(prior.get('artifacts',{}))!=14:
            raise Stop('Pasul 10 nu este complet')
        # Every local row keeps its independent integrity definition.
        self.L=runpy.run_path(str(self.repo/'pipeline/lock.py'))
        for row,rec in prior['artifacts'].items():
            if rec.get('status')!='prepared': raise Stop('Componenta auxiliara nepregatita: '+row)
            p=inside(self.repo,rec['path'])
            folder=next(d for d in (self.repo/'pipeline/inputs/golden'/GOLDEN,self.repo/'pipeline/inputs'/DONOR,self.repo/'pipeline/inputs/common') if (d/row).is_file())
            if self.L['row_hash'](str(folder),row,str(p))!=rec['content_sha256']:
                raise Stop('Componenta auxiliara schimbata: '+row)
        self.inputs={}; identities={}
        for row in ROWS:
            self.inputs[row],identities[row]=self.row(row)
        if identities['darwin27_kernel']!=KERNEL_SHA or identities['kdk']!=KDK_SHA: raise Stop('Versiuni Apple diferite')
        self.view=inside(self.repo,prior['root_view']); self.version=self.view/'System/Library/CoreServices/SystemVersion.plist'
        if plistlib.loads(self.version.read_bytes()).get('ProductBuildVersion')!=GOLDEN: raise Stop('SystemVersion diferit')
        r4=load(self.local/'step4-result.json'); self.oclp=inside(self.repo,r4['oclp_source']); self.efi=inside(self.repo,r4['efi_path'])
        tree=self.command(['/usr/bin/git','-C',self.oclp,'rev-parse','HEAD^{tree}'],True).strip()
        if tree!=r4['oclp_tree']: raise Stop('Arbore OCLP diferit de pasul 4')
        self.preparer=self.oclp/PREPARER
        if self.command(['/usr/bin/git','-C',self.oclp,'diff','--name-only','HEAD','--',PREPARER],True).strip() or not self.preparer.is_file():
            raise Stop('Constructorul KDK Intel lipseste sau a fost modificat')
        self.config_path=self.efi/'EFI/OC/config.plist'
        if not self.config_path.is_file():
            hits=list(self.efi.rglob('config.plist'))
            if len(hits)!=1: raise Stop('config.plist EFI ambiguu')
            self.config_path=hits[0]
        self.config=plistlib.loads(self.config_path.read_bytes())
        self.report['base_efi_config_sha256']=sha(self.config_path)
        self.env={k:v for k,v in os.environ.items() if not k.startswith(('DYLD_','PYTHON'))}
        sdk=self.command(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],True).strip()
        clang=self.command(['/usr/bin/xcrun','--find','clang'],True).strip()
        self.env['SDKROOT']=sdk; self.env['PYTHONDONTWRITEBYTECODE']='1'
        wrappers=self.work/'tools'; wrappers.mkdir()
        for name in ('clang','clang++'):
            actual=self.command(['/usr/bin/xcrun','--find',name],True).strip()
            w=wrappers/name; w.write_text('#!/bin/sh\nexec '+shlex.quote(actual)+' -isysroot '+shlex.quote(sdk)+' "$@"\n'); w.chmod(0o755)
        w=wrappers/'python3';w.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n');w.chmod(0o755)
        self.env['PATH']=str(wrappers)+':'+str(Path(sys.executable).parent)+':/usr/bin:/bin:/usr/sbin:/sbin:/opt/local/bin'
        identities.update(preparer=sha(self.preparer),sdk=sdk,clang=sha(Path(clang)),version=VERSION,
                          sources=self.command(['/usr/bin/git','rev-parse',PIN+':tools/kernel-fixes'],True).strip())
        key=fingerprint(identities)
        if self.state and self.state.get('fingerprint')!=key:
            shutil.copyfile(self.statefile,self.work/'previous-state.json'); self.state={}
        self.state.update(fingerprint=key,inputs=identities); self.report['input_identity']=identities
        if shutil.disk_usage(self.repo).free<20*(1<<30): raise Stop('Mai putin de 20 GiB liberi pentru workspace-ul kernel')
        self.save()
    def mount(self,image,name,readonly=True):
        where=self.work/name; where.mkdir()
        args=['/usr/bin/hdiutil','attach','-nobrowse','-owners','off' if readonly else 'on','-mountpoint',where]
        if readonly: args+=['-readonly']
        self.command(args+[image]); self.mounts.append(where); return where
    def authorization(self):
        print('    Solicit autorizare administrator pentru workspace si kmutil.',flush=True)
        if subprocess.run(['/usr/bin/sudo','-v']).returncode: raise Stop('Autorizarea administratorului a fost refuzata')
    def kdk(self):
        cached=self.state.get('kdk_stage')
        if cached:
            root=inside(self.repo,cached['path']); validate_files(root,cached['files']); self.kdkstage=root
            print('    KDK Intel pregatit anterior: reutilizat.',flush=True); return
        m=self.mount(self.inputs['kdk'],'KDK')
        pkgs=[p for p in m.iterdir() if p.name.endswith('.pkg')]
        if len(pkgs)!=1: raise Stop('KDK DMG: astept un singur pachet .pkg')
        expanded=self.work/'expanded-kdk'
        self.command(['/usr/sbin/pkgutil','--expand-full',pkgs[0],expanded])
        roots=[p for p in expanded.rglob('*.kdk') if (p/SLE).is_dir()]
        if len(roots)!=1: raise Stop('KDK extras ambiguu: '+str(len(roots)))
        original=roots[0]
        if DONOR not in original.name: raise Stop('KDK extras nu are buildul '+DONOR+' in nume')
        self.kdkstage=self.repo/'store/artifacts'/('mbp91-kdk-intel-step11-'+self.stamp); self.kdkstage.mkdir()
        self.command(self.py+['-c','import runpy,sys,json; print(json.dumps(runpy.run_path(sys.argv[1])["prepare"](sys.argv[2],sys.argv[3]),indent=2))',self.preparer,original/SLE,self.kdkstage/'extensions'])
        self.command(self.py+[self.repo/KF,'kdk-donors',original,self.kdkstage/'donors','--build',DONOR])
        manifest=tree_files(self.kdkstage)
        self.state['kdk_stage']={'path':str(self.kdkstage.relative_to(self.repo)),'files':manifest};self.save()
    def stage(self):
        saved=self.state.get('workspace')
        if saved and saved.get('tree_ready'):
            image=inside(self.repo,saved['image'])
        else:
            image=self.work/'kernel-workspace.sparseimage'
            self.command(['/usr/bin/hdiutil','create','-size','16g','-type','SPARSE','-fs','APFS','-volname','HaoKernelStage',image])
        self.system=self.mount(image,'System',readonly=False)
        if saved and saved.get('tree_ready'):
            got=fingerprint(tree_files(self.system/SLE))
            if got!=saved['extensions_digest'] or sha(self.system/'System/Library/Kernels/kernel')!=KERNEL_SHA:
                raise Stop('Arborele kernel reutilizabil a fost schimbat')
            print('    Arborele kernel complet: reutilizat.',flush=True)
        else:
            token=self.stamp+'-'+self.state['fingerprint']; marker=self.system/'.hao-step11-workspace'
            # hdiutil creates the new volume for the invoking user.
            tokenfile=self.work/'workspace-token.txt';tokenfile.write_text(token+'\n')
            self.command(['/usr/bin/install','-o','root','-g','wheel','-m','644',tokenfile,marker],root=True)
            stock=self.inputs['tahoe_extensions_donors']/'payload/extensions'/SLE
            if not stock.is_dir(): raise Stop('Pachetul Tahoe nu contine arborele SLE asteptat')
            copies=[{'source':str(stock.relative_to(self.repo)),'destination':str(SLE),'mode':'merge'},
                    {'source':str((self.kdkstage/'extensions').relative_to(self.repo)),'destination':str(SLE),'mode':'merge'}]
            hardware=self.inputs['oclp_hardware_mbp91']; mapping=load(hardware/'install-map.json')
            for e in mapping['entries']:
                d=relpath(e['destination'].lstrip('/'))
                if not d.is_relative_to(SLE): continue
                op=e['operation']
                if op not in ('Merge System Volume','Overwrite System Volume'): raise Stop('Operatie OCLP SLE necunoscuta: '+op)
                src=inside(hardware/'payload',e['support_package_relative_path'])
                copies.append({'source':str(src.relative_to(self.repo)),'destination':str(d),
                               'mode':'merge' if op.startswith('Merge') else 'replace','patchset':e['patch']})
            copies.extend([{'source':str(self.inputs['darwin27_kernel'].relative_to(self.repo)),
                            'destination':'System/Library/Kernels/kernel','mode':'replace'},
                           {'source':str(self.version.relative_to(self.repo)),
                            'destination':'System/Library/CoreServices/SystemVersion.plist','mode':'replace'}])
            plan={'repo':str(self.repo),'mount':str(self.system.relative_to(self.repo)),'token':token,'copies':copies}
            planfile=self.work/'copy-plan.json';save(planfile,plan)
            self.command([sys.executable,'-I',Path(__file__).resolve(),'--internal-stage',planfile],root=True)
            save(self.local/'step11-copy-plan.json',plan)
            self.state['workspace']={'image':str(image.relative_to(self.repo)),'tree_ready':True,
                                     'extensions_digest':fingerprint(tree_files(self.system/SLE))}
            self.save()
        items=kext_inventory(self.system); report=gpu_report(items,self.config)
        # JSON has bytes in some plists: retain them explicitly, rather than discarding.
        def serial(v):
            if isinstance(v,bytes):return {'plist_data_hex':v.hex()}
            if isinstance(v,dict):return {k:serial(x) for k,x in v.items()}
            if isinstance(v,(list,tuple)):return [serial(x) for x in v]
            return v
        save(self.local/'step11-kext-inventory.json',serial({'kexts':items}))
        save(self.local/'step11-gpu-gmux.json',serial(report));self.gpu=report
        self.report['gpu_gmux_static_check']=serial(report)
        if report['errors']:raise Stop('Inventar/dependente GPU/GMUX incomplet: '+'; '.join(report['errors']))
        print('    Kepler + Intel + AppleMuxControl: prezente; dependentele sunt inventariate.',flush=True)
        self.report['driver_tree_prepared']=True;self.save()
    def collections(self):
        cached=self.state.get('collections')
        if cached:
            dest=inside(self.repo,cached['path']);validate_files(dest,cached['files']);self.collections_dir=dest
            self.report['kernel_collections_built']=True
            print('    Colectiile kernel anterioare: reutilizate.',flush=True);return
        tools=self.work/'kc-tools';tools.mkdir()
        shutil.copyfile(self.inputs['tahoe_kmutil'],tools/'kmutil');(tools/'kmutil').chmod(0o755)
        shutil.copyfile(self.inputs['tahoe_kc_builder'],tools/'kcbuilder.dylib')
        self.command(['/usr/bin/codesign','-s','-','-f',tools/'kcbuilder.dylib'])
        self.command(self.py+[self.repo/'patches/darwin27-kernel/src/kmutil_builder.py',tools/'kmutil','@executable_path/kcbuilder.dylib'])
        self.command(['/usr/bin/codesign','-s','-','-f',tools/'kmutil'])
        self.command(['/usr/bin/codesign','--verify',tools/'kmutil'])
        out=self.system/KCB
        # Remove only failed collection outputs, inside our already mounted workspace.
        for filename in ('BootKernelExtensions.kc','BootKernelExtensions.kc.elides','SystemKernelExtensions.kc'):
            if (out/filename).exists():self.command(['/bin/rm','-f',out/filename],root=True)
        shared=['-a','x86_64','--allow-missing-kdk','-R',self.system,'-k',self.system/'System/Library/Kernels/kernel',
                '-V','release','-B','/'+str(KCB/'BootKernelExtensions.kc')]
        self.command([tools/'kmutil','create','-n','boot',*shared],root=True)
        boot=out/'BootKernelExtensions.kc';members=fileset_ids(boot)
        if 'com.apple.kernel' not in members or len(members)<2:raise Stop('BootKC fara kernel sau fara kexturi')
        elides=[n for n in members if n!='com.apple.kernel']
        self.command([tools/'kmutil','create','-n','sys',*shared,'-S','/'+str(KCB/'SystemKernelExtensions.kc'),
                      *[x for n in elides for x in ('--elide-identifier',n)]],root=True)
        syskc=out/'SystemKernelExtensions.kc';system_ids=fileset_ids(syskc)
        dest=self.repo/'store/artifacts'/('mbp91-kernel-collections-step11-'+self.stamp);dest.mkdir()
        shutil.copyfile(boot,dest/boot.name);shutil.copyfile(syskc,dest/syskc.name)
        (dest/'BootKernelExtensions.kc.elides').write_text(''.join(n+'\n' for n in elides))
        union=set(members)|set(system_ids)
        status={}
        for name,entries in self.gpu['required_bundles'].items():
            e=entries[0];ident=e['identifier'];status[name]={'identifier':ident,'in_boot_kc':ident in members,'in_system_kc':ident in system_ids,
                                                         'needs_early_injection_review':ident not in union}
        save(self.local/'step11-kc-members.json',{'boot':members,'system':system_ids,'gpu_gmux':status})
        self.report['gpu_gmux_collection_membership']=status
        self.report['gpu_gmux_efi_integration_pending']=any(x['needs_early_injection_review'] for x in status.values())
        self.state['collections']={'path':str(dest.relative_to(self.repo)),'files':tree_files(dest),
                                   'source_tree_sha256':self.state['workspace']['extensions_digest']}
        self.collections_dir=dest;self.report['kernel_collections_built']=True;self.save()
    def build_part(self,name,command,expected):
        prior=self.state.get(name)
        if prior:
            path=inside(self.repo,prior['path']);validate_files(path,prior['files']);return path
        path=self.repo/'store/artifacts'/('mbp91-'+name.replace('_','-')+'-step11-'+self.stamp)
        self.command([path if a=='{OUT}' else a for a in command])
        for f in expected:
            if not (path/f).is_file(): raise Stop(name+': rezultat obligatoriu lipsa '+f)
        self.state[name]={'path':str(path.relative_to(self.repo)),'files':tree_files(path)};self.save();return path
    def repairs(self):
        # Mount the already extracted Rosetta image; do not rebuild it.
        payload=load(self.local/'step10-dependencies.json')['rows']['golden_gate_userspace']['path']
        images=inside(self.repo,payload);rosetta=self.mount(images/'rosetta.dmg','Rosetta')
        cache=rosetta/'System/Library/dyld/dyld_shared_cache_x86_64'
        if not cache.is_file(): raise Stop('Cache generic Rosetta x86_64 lipsa')
        boot=self.collections_dir/'BootKernelExtensions.kc';kernel=self.inputs['darwin27_kernel'];donors=self.kdkstage/'donors'
        profile=self.build_part('kernel_profile',self.py+[self.repo/KF,'complete-profile',
             '--profile',self.repo/'tools/kernel-fixes/profiles'/GOLDEN,'--kernel',kernel,'--boot-kc',boot,
             '--dyld-cache',cache,'--donor-sandbox',donors/'Sandbox','--donor-iosurface',donors/'IOSurface','--out','{OUT}'],
             ['profile.json','early-vm.json','iosurface-layout.json','sandbox-op-layout.json'])
        commpage=self.build_part('intel_commpage',self.py+[self.repo/KF,'commpage-kext','--profile',profile,
             '--kernel',kernel,'--boot-kc',boot,'--dyld-cache',cache,'--donor-amfi',donors/'AppleMobileFileIntegrity',
             '--donor-sandbox',donors/'Sandbox','--donor-endpoint',donors/'EndpointSecurity','--out','{OUT}'],
             ['IntelCommpage.kext/Contents/MacOS/IntelCommpage','build/commpage_abi.hpp','build.json'])
        executable=commpage/'IntelCommpage.kext/Contents/MacOS/IntelCommpage'
        if (0x01000007,3) not in macho_slices(executable): raise Stop('IntelCommpage nu este x86_64 generic')
        self.command(['/usr/bin/codesign','--verify','--verbose=2',commpage/'IntelCommpage.kext'])
        repairs=self.build_part('kernel_repairs',self.py+[self.repo/KF,'build-repairs','--capture',profile/'early-vm.json',
             '--boot-kc',boot,'--commpage-artifact',commpage,'--output','{OUT}'],['EFI/OC/config.plist','build.json'])
        binding=self.build_part('kernel_binding',self.py+[self.repo/KF,'repair-binding','profile',
             '--artifact',repairs,'--boot-kc',boot,'--metadata-kc',boot,
             '--abi-header',commpage/'build/commpage_abi.hpp','--output','{OUT}'],['profile.json'])
        # Test binding to the measured reference itself; a later final collection must be checked again.
        self.build_part('kernel_binding_check',self.py+[self.repo/KF,'repair-binding','bind','--profile',binding/'profile.json',
             '--artifact',repairs,'--boot-kc',boot,'--output','{OUT}'],['EFI/OC/config.plist','build.json'])
        rows={'intel_commpage_abi':commpage/'build/commpage_abi.hpp','kernel_repair_efi':repairs,'kernel_repair_binding':binding}
        rowfolder=self.local/'step11-inputs';rowfolder.mkdir(exist_ok=True)
        for name,p in rows.items():
            lock=self.repo/'pipeline/inputs/golden'/GOLDEN
            digest=self.L['row_hash'](str(lock),name,str(p))
            annotations=[line for line in (lock/name).read_text().splitlines() if line.lstrip().startswith('# hash:')]
            text='# LOCAL EXPERIMENTAL: collection-specific MacBookPro9,1 build; no boot validation.\n'
            text+='\n'.join(annotations)+ ('\n' if annotations else '')
            text+=digest+' '+str(p.relative_to(self.repo))+'\n';(rowfolder/name).write_text(text)
            self.report.setdefault('local_inputs',{})[name]={'path':str(p.relative_to(self.repo)),'sha256':digest}
        self.report['repairs_built']=True
        self.report['remaining']=['Final System/Preboot/cryptex assembly and binding to its exact collections',
            'Kepler userland and GMUX switching/early-injection integration and hardware acceptance',
            'External Hao interface units/thunks/async provider absent in experimental payload',
            'First boot, graphics, network, sleep/wake tests']
        self.report['step_complete']=True;self.save()
    def finish(self):
        for m in reversed(self.mounts):
            try:self.command(['/usr/bin/hdiutil','detach',m],timeout=90)
            except Exception as e:self.report.setdefault('cleanup_warnings',[]).append(str(e))
        self.report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();self.save();self.log.close()
        archive=Path.home()/'Desktop/HAO-mbp91-step11.zip';tmp=archive.with_suffix('.partial.zip')
        candidates=list(self.local.glob('step11-*.json'))+list((self.local/'step11-inputs').glob('*'))+[self.logpath]
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(set(candidates)):
                if not p.is_file() or p.is_symlink():continue
                if p.stat().st_size<=5<<20:z.write(p,str(p.relative_to(self.repo)))
                else:
                    with p.open('rb') as f:f.seek(-(5<<20),2);b=f.read()
                    z.writestr(str(p.relative_to(self.repo))+'.tail.txt',b)
            for name in ('kernel_profile','intel_commpage','kernel_repairs','kernel_binding','kernel_binding_check'):
                rec=self.state.get(name)
                if rec:
                    top=inside(self.repo,rec['path'])
                    for p in top.rglob('*'):
                        if p.is_file() and p.suffix in ('.json','.hpp','.plist') and p.stat().st_size<2<<20:
                            z.write(p,'metadata/'+name+'/'+str(p.relative_to(top)))
            z.write(Path(__file__).resolve(),'HAO-mbp91-step11.py')
            z.writestr('READ-ME.txt','Kernel workspace/build reports only. No Apple drivers or KC binaries. Static checks are not boot validation.\n')
        os.replace(tmp,archive)
        print('\nArbore kernel Intel + NVIDIA/GMUX: '+('DA' if self.report.get('driver_tree_prepared') else 'NU'))
        print('Colectii kernel de lucru: '+('DA' if self.report['kernel_collections_built'] else 'NU'))
        print('IntelCommpage si reparatii legate de colectie: '+('DA' if self.report['repairs_built'] else 'NU'))
        print('NVIDIA/GMUX functional / imagine bootabila / boot validat: NU; netestate.')
        print('Arhiva MICA de trimis: '+str(archive))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--internal-stage',type=Path)
    a=p.parse_args()
    if a.internal_stage:
        root_stage(a.internal_stage);return 0
    repo=a.repo.expanduser().resolve()
    if sys.platform!='darwin' or os.geteuid()==0:
        print('OPRIT: ruleaza pe iMac ca utilizator normal, fara sudo.',file=sys.stderr);return 1
    if not (repo/'local/mbp91/step10-result.json').is_file():
        print('OPRIT: ruleaza din Desktop/hao-patcher-mbp91 dupa pasul 10.',file=sys.stderr);return 1
    os.umask(0o022)
    with (repo/'local/mbp91/step11.running.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('OPRIT: pasul 11 ruleaza deja.');return 1
        job=Job(repo)
        try:
            print('1/5 Verific intrarile existente si pregatesc KDK-ul Intel.',flush=True)
            job.setup();job.kdk();job.authorization()
            print('2/5 Construiesc arborele kernel si verific NVIDIA, Intel si AppleMuxControl.',flush=True)
            job.stage()
            print('3/5 Construiesc BootKC si SystemKC pe baza acestui arbore.',flush=True)
            job.collections()
            print('4/5 Generez profilul, IntelCommpage si reparatiile pentru colectia obtinuta.',flush=True)
            job.repairs()
            print('5/5 Salvez artefactele, legaturile locale si raportul.',flush=True)
        except (Exception,KeyboardInterrupt) as e:
            job.report['errors'].append({'error':str(e) or type(e).__name__,'traceback':traceback.format_exc()})
            job.log.write(traceback.format_exc());print('OPRIT: '+(str(e) or type(e).__name__),flush=True)
        finally:job.finish()
        return 0 if job.report['step_complete'] else 1

if __name__=='__main__':raise SystemExit(main())
