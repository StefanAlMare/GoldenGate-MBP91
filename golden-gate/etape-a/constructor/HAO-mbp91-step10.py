#!/usr/bin/env python3
"""MacBookPro9,1 / Hao: step 10, grouped builds of 14 auxiliary input rows.

Run on the Intel build Mac, without sudo, from Desktop/hao-patcher-mbp91:
    python3.14 -I ~/Downloads/HAO-mbp91-step10.py

Uses unmodified, pinned upstream builders. Does not run the resulting libraries,
GPU probes or Apple applications. It may fetch the separate hao-runtime source
commit explicitly required by asset-build for codeid_carrier. It does not replace
the step-7 runtime, download Apple images, or modify upstream input checksums.

An upstream checksum difference is recorded as a LOCAL EXPERIMENTAL CANDIDATE,
not ignored or called equivalent. Assembly and boot validation remain separate.
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
CODEID_PIN = '33a0a0404d3f5c3008c79e295026ea99bee563eb'
VERSION = 'step10-auxiliary-v1'
BUILD = '26B131'
DONOR = '25G342'
ASSET_TOOL = 'tools/asset-build/asset-build'
ASSET_BLOB = 'c3ffd0b9962cf14d2c3043ebb66039e2540c6659'
ROW_NAMES = (
    'display_state_shim', 'io80211_compat', 'wifip2p_compat', 'corewifi_compat',
    'windowserver_filter_shim', 'corespotlight_compat_shim', 'hd4000_planes',
    'libhelloblur', 'metalold_selectors', 'metal_framebuffer', 'metal_argbuf',
    'codeid_carrier', 'metal_compiler_compat', 'live_text_framework',
)
ASSET_ROWS = frozenset(ROW_NAMES[:7] + ('codeid_carrier',))
FILE_ROWS = frozenset(ROW_NAMES[:6] + ('libhelloblur',))
METAL_ROWS = ('hello_metallib_golden_gate', 'metallib_repairs_golden_gate', 'metal_quad_runtime_golden_gate')
SOURCE_PATHS = (
    'tools/asset-build', 'tools/display-state-shim', 'tools/live-text', 'tools/metal-argbuf',
    'patches/golden-gate-userspace/src', 'patches/golden-gate-windowserver-filter',
    'patches/golden-gate-corespotlight-compat', 'patches/golden-gate-hd4000-planes',
    'patches/golden-gate-hello/build', 'patches/metalold-selectors',
    'patches/golden-gate-metal-framebuffer', 'cache/metallib', 'pipeline/lock.py',
    'pipeline/release-classes.json',
)
ICBE = 'System/Library/Extensions/AppleIntelHD4000GraphicsGLDriver.bundle/Contents/MacOS/iCBE.dylib'
SERVICE = 'System/Library/Frameworks/Metal.framework/Versions/A/XPCServices/MTLCompilerService.xpc/Contents/MacOS/MTLCompilerService'
COMPAT = 'System/Library/PrivateFrameworks/MTLCompiler.framework/Versions/3802/Libraries/libhaoMetalCompilerCompat.dylib'
MPS = 'System/Library/Frameworks/MetalPerformanceShaders.framework/Versions/A/Frameworks/MPSNDArray.framework/Versions/A/Resources/default.metallib'
DETECTOR = 'System/Library/PrivateFrameworks/TextRecognition.framework/Versions/A/Resources/cr_td_model_v3_e5.mlmodelc.bundle'
LIBRARIES = {
    'hd4000_planes': ['libhd4000-planes.dylib'],
    'metalold_selectors': ['libmetalold-selectors.dylib'],
    'metal_framebuffer': ['libmetal-framebuffer.dylib'],
    'metal_argbuf': ['iCBE.dylib', 'iCBE-real.dylib', 'libargbuf.dylib'],
    'metal_compiler_compat': ['replace/' + COMPAT],
    'live_text_framework': [
        'replace/usr/lib/libhelloblur.dylib', 'runtime/LiveText.dylib',
        'runtime/gpu-client.dylib', 'runtime/libLiveTextConfig.dylib',
        'runtime/libLiveTextLibrary.dylib', 'runtime/libLiveTextPolicy.dylib',
        'runtime/libhao_input_coherence.dylib',
    ],
}
HEX = re.compile(r'^[0-9a-f]{64}$')

class Stop(RuntimeError):
    pass

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

def jread(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise Stop('Obiect JSON asteptat: ' + str(path))
    return obj

def jwrite(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)

def relative(value: str) -> Path:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or '\x00' in value or p == PurePosixPath('.'):
        raise Stop('Cale relativa invalida: ' + repr(value))
    return Path(*p.parts)

def inside(root: Path, value: str | Path) -> Path:
    p = root / relative(str(value))
    if not p.resolve().is_relative_to(root.resolve()):
        raise Stop('Calea iese din directorul permis: ' + str(p))
    return p

def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def git_blob(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()

def snapshot(root: Path) -> dict:
    """Local audit of every file, directory mode and symlink; never follow an escaping link."""
    if root.is_symlink():
        raise Stop('Radacina artefactului nu poate fi symlink: ' + str(root))
    if root.is_file():
        return {'.': {'type': 'file', 'sha256': sha(root), 'mode': stat.S_IMODE(root.stat().st_mode)}}
    if not root.is_dir():
        raise Stop('Artefact lipsa: ' + str(root))
    result = {}
    for p in sorted(root.rglob('*')):
        st = p.lstat(); rel = p.relative_to(root).as_posix()
        if stat.S_ISLNK(st.st_mode):
            if not p.resolve().is_relative_to(root.resolve()):
                raise Stop('Symlink extern in artefact: ' + rel)
            result[rel] = {'type': 'symlink', 'target': os.readlink(p)}
        elif stat.S_ISDIR(st.st_mode):
            result[rel] = {'type': 'directory', 'mode': stat.S_IMODE(st.st_mode)}
        elif stat.S_ISREG(st.st_mode):
            result[rel] = {'type': 'file', 'mode': stat.S_IMODE(st.st_mode), 'sha256': sha(p)}
        else:
            raise Stop('Fisier special neacceptat: ' + str(p))
    if not any(v['type'] == 'file' for v in result.values()):
        raise Stop('Artefact gol: ' + str(root))
    return result

def thin_macho(path: Path, kind: int) -> dict:
    """Structural check only. No program is executed."""
    b = path.read_bytes()
    if len(b) < 32:
        raise Stop('Mach-O trunchiat: ' + str(path))
    magic, cpu, subtype, ftype, ncmd, nbytes, flags, reserved = struct.unpack_from('<8I', b)
    if (magic, cpu, ftype) != (0xfeedfacf, 0x01000007, kind):
        raise Stop(f'Mach-O x86_64 tip {kind} asteptat: {path}')
    if ncmd > 10000 or 32 + nbytes > len(b):
        raise Stop('Comenzi Mach-O invalide: ' + str(path))
    pos = 32; minos = []; deps = []; install_name = None
    for _ in range(ncmd):
        if pos + 8 > 32 + nbytes:
            raise Stop('Comanda Mach-O trunchiata')
        cmd, size = struct.unpack_from('<II', b, pos)
        if size < 8 or size % 8 or pos + size > 32 + nbytes:
            raise Stop('Lungime comanda Mach-O invalida')
        if cmd == 0x32:
            if size < 24: raise Stop('LC_BUILD_VERSION trunchiat')
            platform, minimum = struct.unpack_from('<II', b, pos + 8)
            if platform != 1: raise Stop('Platforma Mach-O nu este macOS')
            minos.append(minimum)
        elif cmd == 0x24:
            if size < 16: raise Stop('LC_VERSION_MIN_MACOSX trunchiat')
            minos.append(struct.unpack_from('<I', b, pos + 8)[0])
        if cmd in (0xc, 0xd, 0x80000018, 0x8000001f, 0x80000023):
            if size < 24: raise Stop('Comanda dylib trunchiata')
            start = struct.unpack_from('<I', b, pos + 8)[0]
            if start < 24 or start >= size: raise Stop('Nume dylib invalid')
            raw = b[pos + start:pos + size]
            if b'\0' not in raw: raise Stop('Nume dylib neterminat')
            name = raw.split(b'\0', 1)[0].decode('utf-8', 'strict')
            if cmd == 0xd: install_name = name
            else: deps.append(name)
        pos += size
    if pos != 32 + nbytes: raise Stop('Lungimea comenzilor Mach-O difera')
    if kind in (2, 6) and (not minos or any(v > (27 << 16) for v in minos)):
        raise Stop('Deployment target lipsa sau mai nou decat macOS 27.0: ' + str(path))
    if kind == 6 and not install_name:
        raise Stop('Dylib fara LC_ID_DYLIB: ' + str(path))
    # Paths into the build machine are not usable in the installed image.
    for dep in deps + ([install_name] if install_name else []):
        if dep.startswith(('/Users/', '/private/tmp/', '/tmp/')):
            raise Stop('Dependenta legata de calculatorul de build: ' + dep)
    return {'architecture': 'x86_64', 'filetype': kind,
            'minimum_versions': ['%d.%d.%d' % (v >> 16, v >> 8 & 255, v & 255) for v in minos],
            'install_name': install_name, 'dependencies': deps, 'sha256': sha(path)}

def acceptable_asset_exit(rc: int, text: str, row: str, actual: str, wanted: str) -> bool:
    """A nonzero exit is tolerated ONLY for the documented final checksum comparison."""
    if rc == 0:
        return actual == wanted
    if rc != 1 or actual == wanted or not HEX.fullmatch(actual) or not HEX.fullmatch(wanted):
        return False
    lines = text.splitlines()
    return (f'{actual} {row}' in lines and
            f'asset-build: {row} is {actual}, the row says {wanted}' in lines and
            not any(s in text for s in ('Traceback (most recent call last)', 'CalledProcessError', 'SyntaxError:')))

def stop_process(p):
    if p.poll() is not None: return
    try:
        os.killpg(p.pid, signal.SIGTERM); p.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        with contextlib.suppress(OSError): os.killpg(p.pid, signal.SIGKILL)
        p.wait()

class Job:
    def __init__(self, repo: Path):
        self.repo = repo.resolve(); self.local = repo / 'local/mbp91'
        self.rid = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work = repo / ('store/tmp/mbp91-step10-' + self.rid)
        self.work.mkdir(parents=True)
        self.states = self.local / 'step10-state'; self.states.mkdir(exist_ok=True)
        self.rowsdir = self.local / 'step10-inputs'; self.rowsdir.mkdir(exist_ok=True)
        self.metadata = self.local / 'step10-metadata'; self.metadata.mkdir(exist_ok=True)
        for n in ('step10-result.json', 'step10-build.log', 'step10-dependencies.json', 'step10-tool-failures.log', 'step10-live-text-build.json'):
            p = self.local / n
            if p.exists():
                dst = self.local / 'backups' / ('step10-' + self.rid) / n
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)
        self.logpath = self.local / 'step10-build.log'; self.log = self.logpath.open('w', buffering=1)
        (self.local / 'step10-tool-failures.log').write_text('')
        (self.local / 'step10-live-text-build.json').unlink(missing_ok=True)
        self.env = dict(os.environ); self.lock = None
        self.report = {'schema': 'hao-mbp91-step10', 'revision': VERSION, 'run_id': self.rid,
                       'patcher_commit': PIN, 'golden_build': BUILD, 'model': 'MacBookPro9,1',
                       'artifacts': {}, 'errors': [], 'commands': [], 'step_complete': False,
                       'official_rows_modified': False, 'core_runtime_rebuilt': False,
                       'metal_step9_rebuilt': False, 'boot_validated': False, 'image_built': False,
                       'compatibility_complete': False, 'kernel_repairs_built': False,
                       'note': 'Compilation and structural checks only; no GPU or system boot tests.'}
        self.root = self.hardware = self.quad = None
        self.tc = {}; self.previous = {}; self.codeid = None

    def run(self, argv, *, timeout=3600, cwd=None, allow_nonzero=False, live=False):
        argv = list(map(str, argv)); start = time.monotonic()
        rec = {'argv': argv, 'returncode': None}
        self.report['commands'].append(rec)
        cap = self.work / ('command-%03d.log' % len(self.report['commands']))
        self.log.write('$ ' + shlex.join(argv) + '\n'); copied = 0
        try:
            with cap.open('wb') as f:
                p = subprocess.Popen(argv, cwd=cwd or self.repo, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
                next_notice = start + 60
                try:
                    while p.poll() is None:
                        with cap.open('rb') as r:
                            r.seek(copied); chunk = r.read(); copied += len(chunk)
                        if chunk: self.log.write(chunk.decode(errors='replace'))
                        now = time.monotonic()
                        if now - start > timeout: raise Stop('Limita de executie depasita: ' + shlex.join(argv[:3]))
                        if live and now >= next_notice:
                            print('    Constructie in curs; log: local/mbp91/step10-build.log', flush=True)
                            next_notice = now + 60
                        time.sleep(.2)
                except BaseException:
                    stop_process(p); raise
                rec['returncode'] = p.returncode
        finally:
            rec['elapsed_s'] = round(time.monotonic() - start, 2)
            text = cap.read_text(errors='replace') if cap.exists() else ''
            if cap.exists():
                self.log.write(cap.read_bytes()[copied:].decode(errors='replace'))
            self.log.write('\n')
        if rec['returncode'] != 0 and not allow_nonzero:
            raise Stop('Comanda esuata (%s): %s\n%s' % (rec['returncode'], shlex.join(argv[:4]), '\n'.join(text.splitlines()[-14:])))
        return (rec['returncode'], text) if allow_nonzero else text.strip()

    def official(self, row):
        for f in (self.repo / f'pipeline/inputs/golden/{BUILD}', self.repo / f'pipeline/inputs/{DONOR}', self.repo / 'pipeline/inputs/common'):
            if (f / row).is_file():
                wanted, p = self.lock['rows'](str(f))[row]
                return f, wanted, Path(p)
        raise Stop('Lipseste definitia upstream: ' + row)

    def checked(self, row):
        f, _, _ = self.official(row)
        try: return Path(self.lock['path'](str(f), row))
        except SystemExit as e: raise Stop(f'Intrare neverificata {row}: {e}') from e

    def setup(self):
        if sys.platform != 'darwin' or os.geteuid() == 0:
            raise Stop('Ruleaza pe iMac, in macOS, fara sudo.')
        if self.run(['/usr/bin/git', 'rev-parse', 'HEAD']) != PIN:
            raise Stop('Commit Hao diferit; asteptat 6bd75aa. Nu actualizez automat sursele.')
        diff = self.run(['/usr/bin/git', 'status', '--porcelain', '--', *SOURCE_PATHS])
        if diff: raise Stop('Constructori cu modificari locale:\n' + diff)
        if git_blob(self.repo / ASSET_TOOL) != ASSET_BLOB:
            raise Stop('Constructorul asset-build difera de versiunea inspectata.')
        self.lock = runpy.run_path(str(self.repo / 'pipeline/lock.py'))
        self.previous = jread(self.local / 'step9-result.json')
        if not self.previous.get('step_complete') or self.previous.get('errors'):
            raise Stop('Pasul 9 nu este inregistrat complet.')
        for r in METAL_ROWS:
            a = self.previous['artifacts'][r]; p = inside(self.repo, a['path'])
            f, _, _ = self.official(r)
            got = self.lock['row_hash'](str(f), r, str(p))
            if got != a['content_sha256'] or sha(p / 'build.json') != a['build_record_sha256']:
                raise Stop('Artefactul pasului 9 a fost modificat: ' + r)
            self.report.setdefault('reused_metal', {})[r] = {'path': a['path'], 'sha256': got}
        self.quad = inside(self.repo, self.previous['artifacts']['metal_quad_runtime_golden_gate']['path'])
        self.root = inside(self.repo, self.previous['root_view'])
        version = plistlib.loads((self.root / 'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        if version.get('ProductBuildVersion') != BUILD: raise Stop('System nu este 26B131.')
        p8 = jread(self.local / 'step8-result.json')
        payload = inside(self.repo, p8['bootstrap_artifact'])
        if not p8.get('bootstrap_payload_ready') or sha(payload / 'payload-manifest.json') != p8['payload_manifest_sha256']:
            raise Stop('Payload-ul pasului 8 nu corespunde raportului sau.')
        self.report['bootstrap_input'] = {'path': p8['bootstrap_artifact'], 'manifest_sha256': p8['payload_manifest_sha256'],
                                          'scope': 'experimental; no external interface units/thunks/async provider'}
        self.hardware = self.checked('oclp_hardware_mbp91')
        self.report['root_view'] = str(self.root.relative_to(self.repo))
        self.report['hardware_sha256'] = self.official('oclp_hardware_mbp91')[1]
        for r in ROW_NAMES: self.official(r)
        dev = self.run(['/usr/bin/xcode-select', '-p'])
        sdk = self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'])
        sdkver = self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'])
        tools = {}
        for n in ('clang', 'clang++', 'metal', 'metallib', 'metal-as', 'metal-objdump'):
            p = Path(self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--find', n]))
            if not p.is_file() or not os.access(p, os.X_OK): raise Stop('Unealta absenta: ' + n)
            tools[n] = {'path': str(p), 'sha256': sha(p)}
        bindir = self.work / 'bin'; bindir.mkdir()
        for n in ('python3', 'python3.14'):
            p = bindir / n; p.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' -I -B "$@"\n'); p.chmod(0o755)
        # Keep compiler errors even when a producer captures stderr and only raises
        # CalledProcessError. The proxy returns stdout, stderr and status unchanged.
        proxy = bindir / 'tool-proxy.py'
        proxy.write_text("""import json,os,subprocess,sys,shlex
from pathlib import Path
m=json.loads(Path(sys.argv[1]).read_text()); tool=m['tools'][sys.argv[2]]
cmd=[tool['path'],*tool.get('prefix',[]),*sys.argv[3:]]
r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
sys.stdout.buffer.write(r.stdout); sys.stderr.buffer.write(r.stderr)
if r.returncode:
    msg=('\\n$ '+shlex.join(cmd)+'\\nexit='+str(r.returncode)+'\\n').encode()+r.stdout[-32768:]+r.stderr[-131072:]+b'\\n'
    fd=os.open(m['failure_log'],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try: os.write(fd,msg)
    finally: os.close(fd)
sys.exit(r.returncode if r.returncode>=0 else 128-r.returncode)
""")
        mapping = bindir / 'tool-proxy.json'
        jwrite(mapping, {'tools': {
            'clang': {'path': tools['clang']['path'], 'prefix': ['-isysroot', sdk]},
            'clang++': {'path': tools['clang++']['path'], 'prefix': ['-isysroot', sdk]},
            'xcrun': {'path': '/usr/bin/xcrun'}, 'codesign': {'path': '/usr/bin/codesign'}},
            'failure_log': str(self.local / 'step10-tool-failures.log')})
        for n in ('clang', 'clang++', 'xcrun', 'codesign'):
            p = bindir / n
            p.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, '-I', '-B', str(proxy), str(mapping), n]) + ' "$@"\n')
            p.chmod(0o755)
        for k in tuple(self.env):
            if k.startswith(('DYLD_', 'MAKE')) or k in ('PYTHONPATH','PYTHONHOME','SDKROOT','MACOSX_DEPLOYMENT_TARGET',
                 'HAO_METAL_LLVM','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','CC','CXX','CFLAGS','CXXFLAGS','LDFLAGS',
                 'METAL_FRAMEBUFFER_LLVM','HELLOBLUR_SDK','B','MACOS_MIN','TEST_SWITCHES','LD_PRELOAD'):
                self.env.pop(k, None)
        self.env.update(DEVELOPER_DIR=dev, SDKROOT=sdk, HELLOBLUR_SDK=sdk, PYTHONDONTWRITEBYTECODE='1',
                        PATH=str(bindir)+':/usr/bin:/bin:/usr/sbin:/sbin:/opt/local/bin')
        self.tc = {'developer': dev, 'sdk': sdk, 'sdk_version': sdkver, 'tools': tools}
        self.report['toolchain'] = self.tc
        # Probe the shared toolchain once, before all builders. Never execute the output.
        src = self.work / 'toolchain-check.c'; src.write_text('int hao_step10_check(void) { return 10; }\n')
        out = self.work / 'toolchain-check.dylib'
        self.run(['clang', '-arch', 'x86_64', '-mmacosx-version-min=13.0', '-dynamiclib', src,
                  '-install_name', '/usr/lib/hao-step10-check.dylib', '-o', out])
        self.run(['/usr/bin/codesign','-f','-s','-',out]); self.check_dylib(out)
        print('    SDK '+sdkver+' explicit; proba compilare/linkare/semnatura: OK.', flush=True)
        print('    Metal, payload si pachet hardware existente: reutilizate.', flush=True)

    def codeid_source(self):
        if self.codeid is not None: return self.codeid
        base = self.repo / 'store/sources'; base.mkdir(parents=True, exist_ok=True)
        dest = base / ('hao-runtime-codeid-' + CODEID_PIN[:12])
        if not dest.exists():
            print('    Obtin sursa separata codeid '+CODEID_PIN[:12]+' fixata de Hao; runtime-ul pasului 7 ramane neschimbat.', flush=True)
            new = base / (dest.name + '.partial-' + self.rid); new.mkdir()
            self.run(['/usr/bin/git','init',new])
            self.run(['/usr/bin/git','-C',new,'remote','add','origin','https://github.com/lythka/hao-runtime.git'])
            self.run(['/usr/bin/git','-C',new,'-c','http.lowSpeedLimit=1024','-c','http.lowSpeedTime=120',
                      'fetch','--depth=1','--no-tags','origin',CODEID_PIN], timeout=1200, live=True)
            self.run(['/usr/bin/git','-C',new,'-c','core.hooksPath=/dev/null','checkout','--detach',CODEID_PIN])
            if self.run(['/usr/bin/git','-C',new,'rev-parse','HEAD']) != CODEID_PIN: raise Stop('Commit codeid incorect')
            new.rename(dest)
        if dest.is_symlink() or self.run(['/usr/bin/git','-C',dest,'rev-parse','HEAD']) != CODEID_PIN:
            raise Stop('Checkout codeid necorespunzator')
        if self.run(['/usr/bin/git','-C',dest,'status','--porcelain','--untracked-files=no']):
            raise Stop('Sursele codeid au modificari locale.')
        self.report['codeid_source'] = {'path': str(dest.relative_to(self.repo)), 'commit': CODEID_PIN,
                                       'separate_from_core_runtime': True}
        self.codeid = dest
        return dest

    def check_dylib(self, path):
        result = thin_macho(path, 6)
        self.run(['/usr/bin/codesign','--verify','--verbose=2',path], timeout=60)
        result['code_signature_verified'] = True
        return result

    def validate(self, row, path):
        result = {'kind': 'structural-and-signature', 'execution_tested': False}
        if row in FILE_ROWS:
            result['machos'] = {path.name: self.check_dylib(path)}
        elif row == 'codeid_carrier':
            result['object'] = thin_macho(path/'carrier.o', 1)
            archive = path/'libhao_codeid.a'
            with archive.open('rb') as f:
                if f.read(8) != b'!<arch>\n': raise Stop('Arhiva statica codeid invalida')
            archs = self.run(['/usr/bin/lipo','-archs',archive], timeout=60).split()
            if archs != ['x86_64']: raise Stop('libhao_codeid.a nu este exclusiv x86_64')
            members = self.run(['/usr/bin/ar','-t',archive], timeout=60).splitlines()
            if not any('code_identity' in x for x in members) or not any('idlist' in x for x in members):
                raise Stop('Arhiva codeid nu contine obiectele cerute')
            rec = jread(path/'build.json')
            if rec.get('hao_runtime',{}).get('commit') != CODEID_PIN: raise Stop('Provenienta codeid incorecta')
            if rec.get('carrier_o') != sha(path/'carrier.o') or rec['hao_runtime']['libhao_codeid_a'] != sha(archive):
                raise Stop('Hash-uri codeid necorespunzatoare')
            result['archive_members'] = members; result['cache_link_plan_tested'] = False
        else:
            result['machos'] = {n: self.check_dylib(inside(path,n)) for n in LIBRARIES[row]}
            if row == 'metal_argbuf':
                if sha(path/'iCBE-real.dylib') != sha(self.quad/ICBE): raise Stop('iCBE-real difera de rezultatul pasului 9')
                want = '/System/Library/Extensions/AppleIntelHD4000GraphicsGLDriver.bundle/Contents/MacOS/iCBE-real.dylib'
                if want not in result['machos']['iCBE.dylib']['dependencies']: raise Stop('Reexport iCBE-real lipsa')
            if row == 'metal_compiler_compat':
                rec = jread(path/'build.json')
                for rel, wanted in rec['files'].items():
                    if sha(inside(path,'replace/'+rel)) != wanted: raise Stop('Hash compiler-service diferit: '+rel)
                result['service'] = thin_macho(path/'replace'/SERVICE, 2)
                # The legacy bundle envelope requires upstream's explicit special-slot check,
                # not a strict verification of the extracted executable as a bare file.
                if [m['bundle_slots'] for m in rec['original_signature']] != [m['bundle_slots'] for m in rec['new_signature']]:
                    raise Stop('Legaturile semnaturii cu Info.plist/CodeResources s-au schimbat')
                result['service_resource_verification'] = rec['resource_validation']
        return result

    def spec(self, row, extra=None):
        folder, wanted, _ = self.official(row)
        return {'revision': VERSION, 'row': row, 'patcher_commit': PIN, 'toolchain': self.tc,
                'row_definition_sha256': sha(folder/row), 'official_expected': wanted,
                'codeid_commit': CODEID_PIN if row == 'codeid_carrier' else None,
                'input': extra or {}}

    def prepare_saved(self, row, spec):
        p = self.states/(row+'.json')
        if not p.is_file(): return None
        saved = jread(p)
        if saved.get('fingerprint') != fingerprint(spec): return None
        out = inside(self.repo, saved['path'])
        if snapshot(out) != saved['files']:
            raise Stop('Artefact local modificat; nu il suprascriu: '+str(out))
        folder, _, _ = self.official(row)
        if self.lock['row_hash'](str(folder), row, str(out)) != saved['content_sha256']:
            raise Stop('Hash local invalid la reluare: '+row)
        checks = self.validate(row,out)
        saved.update(status='prepared', reused=True, validation=checks)
        self.report['artifacts'][row] = saved
        self.write_row(row,saved); self.save()
        print('    '+row+': reutilizat dupa verificare, fara reconstructie.', flush=True)
        return out

    def write_row(self, row, state):
        folder, expected, _ = self.official(row)
        directives = [s for s in (folder/row).read_text().splitlines() if s.lstrip().startswith(('# hash:', '# check:'))]
        text = ['# Local experimental artifact; does not replace the upstream row.',
                '# Compiled and structurally verified; not a boot or functional compatibility proof.',
                '# Official expected: '+expected, '# Upstream byte match: '+str(state['matches_upstream']).lower(),
                *directives, state['content_sha256']+' '+state['path']]
        (self.rowsdir/row).write_text('\n'.join(text)+'\n')

    def register(self, row, out, spec, validation=None):
        checks = validation or self.validate(row,out)
        folder, wanted, _ = self.official(row)
        actual = self.lock['row_hash'](str(folder), row, str(out))
        state = {'status':'prepared','path':str(out.relative_to(self.repo)), 'content_sha256':actual,
                 'official_expected_sha256':wanted,'matches_upstream':actual==wanted,
                 'classification':'upstream-byte-match' if actual==wanted else 'local-experimental-candidate',
                 'fingerprint':fingerprint(spec),'inputs':spec,'files':snapshot(out),'validation':checks,
                 'reused':False,'boot_validated':False}
        jwrite(self.states/(row+'.json'),state)
        self.report['artifacts'][row]=state; self.write_row(row,state)
        folderout = out if out.is_dir() else out.parent
        for fname in ('build.json','SHA256SUMS','SOURCES'):
            f = folderout/fname
            if f.is_file():
                dst = self.metadata/row/fname; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(f,dst)
        print('    '+row+': construit; structura verificata; upstream: '+('IDENTIC' if actual==wanted else 'DIFERIT - candidat local'),flush=True)
        self.save()
        return out

    def build_one(self,row):
        extra = {'icbe_sha256':sha(self.quad/ICBE)} if row=='metal_argbuf' else {}
        spec=self.spec(row,extra)
        old=self.prepare_saved(row,spec)
        if old is not None: return old
        # A failed attempt must not leave an earlier input row active for this run.
        (self.rowsdir/row).unlink(missing_ok=True)
        dest=self.repo/('store/artifacts/mbp91-'+row.replace('_','-')+'-step10-'+self.rid)
        self.report['artifacts'][row]={'status':'building','path':str(dest.relative_to(self.repo))}; self.save()
        py=[sys.executable,'-I','-B']
        _,wanted,official=self.official(row)
        if row in ASSET_ROWS:
            args=py+[self.repo/ASSET_TOOL,row,dest]
            if row=='codeid_carrier': args+=['--hao-runtime',self.codeid_source()]
            rc,text=self.run(args,allow_nonzero=True,live=True,timeout=3600)
            out=dest/official.name if row in FILE_ROWS else dest
            if not out.exists(): raise Stop('Constructorul nu a produs '+str(out)+'\n'+'\n'.join(text.splitlines()[-12:]))
            folder,_,_=self.official(row)
            actual=self.lock['row_hash'](str(folder),row,str(out))
            if not acceptable_asset_exit(rc,text,row,actual,wanted):
                raise Stop('Constructor asset-build esuat (nu doar diferenta de checksum): '+row+'\n'+'\n'.join(text.splitlines()[-16:]))
        elif row=='libhelloblur':
            self.run(['/bin/sh',self.repo/'patches/golden-gate-hello/build/make.sh',dest],live=True)
            out=dest/'libhelloblur.dylib'
        elif row=='metalold_selectors':
            parent=self.work/'selectors'; parent.mkdir()
            self.run(py+[self.repo/'patches/metalold-selectors/build/make',parent],live=True)
            dirs=list(parent.glob('metalold-selectors-*'))
            if len(dirs)!=1: raise Stop('Rezultat selectors ambiguu')
            dirs[0].rename(dest); out=dest
        elif row=='metal_framebuffer':
            self.run(py+[self.repo/'patches/golden-gate-metal-framebuffer/build/metal-framebuffer','build',dest],live=True)
            out=dest
        elif row=='metal_argbuf':
            self.run(['/bin/bash',self.repo/'tools/metal-argbuf/make',dest,'--icbe',self.quad/ICBE],live=True)
            out=dest
        else: raise Stop('Constructor neimplementat: '+row)
        return self.register(row,out,spec)

    def live_text(self):
        rows=('metal_compiler_compat','live_text_framework')
        dep=self.report['artifacts'].get('libhelloblur',{})
        if dep.get('status')!='prepared': raise Stop('Live Text necesita libhelloblur construit si verificat.')
        hello=inside(self.repo,dep['path'])
        # Hash only the actual source inputs read by this producer, not an unrelated host SDK tree.
        extra={'libhelloblur':sha(hello),'MPSNDArray':sha(self.root/MPS),
               'detector':fingerprint(snapshot(self.root/DETECTOR)),
               'oclp_hardware_sha256':self.report['hardware_sha256']}
        specs={r:self.spec(r,extra) for r in rows}
        old={r:self.prepare_saved(r,specs[r]) for r in rows}
        if all(old.values()): return
        for r in rows:
            if old[r] is None: (self.rowsdir/r).unlink(missing_ok=True)
        inputs=self.work/'live-text-inputs'
        out=self.repo/('store/artifacts/mbp91-live-text-step10-'+self.rid)
        tool=self.repo/'tools/live-text/live-text'; py=[sys.executable,'-I','-B']
        self.run(py+[tool,'inputs','--system',self.root,'--oclp-hardware',self.hardware,'--output',inputs],live=True)
        self.run(py+[tool,'build','--inputs',inputs,'--startup-library',hello,'--output',out],live=True,timeout=4*3600)
        record=jread(out/'build.json')
        if record.get('system_build')!=BUILD or record.get('operation')!='build': raise Stop('Manifest Live Text invalid')
        for row,sub in zip(rows,('compiler-service','framework')):
            folder=out/sub
            files={p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
            if files!=record['outputs'][sub]: raise Stop('Live Text difera de manifest: '+sub)
            # Preserve a previously verified component if only its sibling needed rebuilding.
            if old[row] is None: self.register(row,folder,specs[row])
        shutil.copyfile(out/'build.json',self.local/'step10-live-text-build.json')

    def fail(self, rows, e):
        if isinstance(rows,str): rows=[rows]
        detail=str(e) or type(e).__name__
        for row in rows:
            if self.report['artifacts'].get(row,{}).get('status')=='prepared': continue
            self.report['artifacts'][row]={'status':'failed','error':detail}
            self.report['errors'].append({'row':row,'error':detail})
            (self.rowsdir/row).unlink(missing_ok=True)
        self.log.write(traceback.format_exc()+'\n')
        print('    OPRIT pentru '+', '.join(rows)+': '+detail,flush=True); self.save()

    def dependencies(self):
        prev=jread(self.local/'step9-dependencies.json')
        remaining=[]; rows={}
        for name,record in prev['rows'].items():
            new=self.report['artifacts'].get(name)
            if new and new.get('status')=='prepared':
                rows[name]={'state':'local_candidate_prepared','path':new['path'],
                            'matches_upstream':new['matches_upstream'],'execution_tested':False}
            else:
                rows[name]=dict(record)
                if new: rows[name].update(state='failed',error=new.get('error'))
                if record.get('state','').startswith('missing') or new and new.get('status')!='prepared': remaining.append(name)
        result={'assembly':prev['assembly'],'rows':rows,'remaining_missing_rows':remaining,
                'note':'Only declared recipe inputs. Kernel building, installation hooks, compatibility and boot are not validated here.',
                'local_inputs':'local/mbp91/step10-inputs','official_rows_modified':False}
        jwrite(self.local/'step10-dependencies.json',result)
        self.report['remaining_missing_rows']=remaining

    def save(self): jwrite(self.local/'step10-result.json',self.report)

    def finish(self):
        self.report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat(); self.save(); self.log.close()
        archive=Path.home()/'Desktop/HAO-mbp91-step10.zip'; tmp=archive.with_suffix('.partial.zip')
        names=[self.local/n for n in ('step10-result.json','step10-build.log','step10-dependencies.json','step10-live-text-build.json','step10-tool-failures.log')]
        names+=list(self.states.glob('*.json'))+list(self.rowsdir.glob('*'))
        names+=list(self.metadata.rglob('*.json'))+list(self.metadata.rglob('SHA256SUMS'))+list(self.metadata.rglob('SOURCES'))
        limit=3<<20
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(set(names)):
                if not p.is_file() or p.is_symlink(): continue
                rel=p.relative_to(self.repo).as_posix()
                if p.stat().st_size<=limit: z.write(p,rel)
                else:
                    with p.open('rb') as f: f.seek(-limit,2); tail=f.read()
                    z.writestr(rel+'.tail.txt',b'[Last 3 MiB only; full log remains on the build Mac.]\n'+tail)
            z.write(Path(__file__).resolve(),'HAO-mbp91-step10.py')
            z.writestr('READ-ME.txt','Metadata and build logs only; no Apple images, drivers, source checkouts or compiled libraries.\n')
        os.replace(tmp,archive)
        count=sum(self.report['artifacts'].get(r,{}).get('status')=='prepared' for r in ROW_NAMES)
        print(f'\nIntrari auxiliare construite si verificate structural: {count}/{len(ROW_NAMES)}')
        print('Pasul 10 incheiat: '+('DA' if self.report['step_complete'] else 'NU, vezi erorile din raport'))
        print('Variantele locale: local/mbp91/step10-inputs/; randurile upstream nu sunt rescrise.')
        print('Kernel / asamblare imagine / compatibilitate completa / boot validat: NU.')
        print('Arhiva MICA de trimis: '+str(archive))
        return archive

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path.cwd()); args=p.parse_args()
    repo=args.repo.expanduser().resolve()
    if not (repo/'pipeline/lock.py').is_file() or not (repo/'local/mbp91/step9-result.json').is_file():
        print('OPRIT: ruleaza din Desktop/hao-patcher-mbp91, cu pasul 9 finalizat.',file=sys.stderr); return 1
    if sys.platform!='darwin' or os.geteuid()==0:
        print('OPRIT: ruleaza pe macOS ca utilizator normal, fara sudo.',file=sys.stderr); return 1
    os.umask(0o022)
    with (repo/'local/mbp91/step10.running.lock').open('a+') as guard:
        try: fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('OPRIT: pasul 10 ruleaza deja in acest proiect.',file=sys.stderr); return 1
        job=Job(repo)
        try:
            print('1/4 Reutilizez rezultatele anterioare si pregatesc toolchain-ul explicit.',flush=True)
            job.setup()
            print('2/4 Construiesc intr-un lot cele 12 intrari auxiliare independente.',flush=True)
            for row in ROW_NAMES[:12]:
                print('  '+row,flush=True)
                try: job.build_one(row)
                except Exception as e: job.fail(row,e)
            print('3/4 Construiesc componentele Live Text si Metal compiler compatibility.',flush=True)
            try: job.live_text()
            except Exception as e: job.fail(ROW_NAMES[12:],e)
            print('4/4 Salvez intrarile locale si dependentele ramase.',flush=True)
            job.dependencies()
            job.report['step_complete']=not job.report['errors'] and all(job.report['artifacts'].get(r,{}).get('status')=='prepared' for r in ROW_NAMES)
        except (Exception,KeyboardInterrupt) as e:
            job.report['errors'].append({'stage':'setup_or_interrupted','error':str(e) or type(e).__name__})
            job.log.write(traceback.format_exc()); print('OPRIT: '+(str(e) or type(e).__name__),flush=True)
        finally: job.finish()
        return 0 if job.report['step_complete'] else 1

if __name__=='__main__': raise SystemExit(main())
