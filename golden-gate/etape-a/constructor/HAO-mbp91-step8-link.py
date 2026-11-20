#!/usr/bin/env python3
"""HAO MBP9,1 step 8: resume embedding with an explicit Xcode macOS SDK.

Reads the existing step8-result.json before writing a new report. Reuses ONLY a
completed root-view recorded by the preceding run, never recopies System/OS/App.
Mounts only the verified Rosetta image, read-only. Uses a private clang launcher
with -isysroot and SDKROOT, and tests linking plus launchd/xpcproxy embedding
before running the full upstream packager. Does not run the target programs,
rebuild the runtime, download files, or request administrator privileges.

The output is experimental: no external interface units, thunks or async provider.
File/identity checks are retained; no official pinned hash is replaced.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import fcntl
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import runpy
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

PATCHER = '6bd75aab112d1078acd8e75180eb510672461365'
RUNTIME = '1547dcb4e19a2ab0843086e3288223f998507a4c'
RTREE = '16170db522a965b863650459083a4593dba5b493'
PACKAGER_BLOB = '0ec57e91ac33e04dae9592bee13f211a489fd991'
USERSPACE_SHA = '060bd378064461f4778fb3c312dffc7f181a1a0d3f534bdf76fefb4ba7798038'
GOLDEN = '26B131'
GIB = 1024 ** 3
REQUIRED = {'sbin/launchd', 'usr/libexec/xpcproxy'}
RUNTIME_NAMES = ('hao', 'hao-stub', 'libhao.dylib', 'libhao_identity.dylib',
                 'front/stub.o', 'libhaocore.a', 'libhao_codeid.a')
H_LINE = 'H=$(cd "$(dirname "$0")/.." && pwd)'
BUILD_BLOCK = '''if [ -n "$MIN" ]; then
    [[ "$MIN" =~ ^[0-9]+\\.[0-9]+(\\.[0-9]+)?$ ]] || { echo "hao-image-payload: bad --macos-min $MIN" >&2; exit 2; }
    BDIR=build/macos-$MIN
    make -C "$H" B="$BDIR" MACOS_MIN="$MIN" >/dev/null
else
    BDIR=build
    make -C "$H" >/dev/null
fi
B=$H/$BDIR
KEXT_MIN=13.0
"$H/kext/build.sh" "$B" "$KEXT_MIN" >/dev/null
KEXT=$B/HaoExec.kext'''
REUSE_BLOCK = '''# Local wrapper: all these inputs were hash-checked before this process.
[ "$MIN" = 27.0 ] || { echo "local packager requires --macos-min 27.0" >&2; exit 2; }
BDIR=${HAO_STEP8_PREBUILT:?missing verified build directory}
B=$H/$BDIR
KEXT_MIN=13.0
KEXT=$B/HaoExec.kext
[ -f "$B/hao" ] && [ -f "$B/front/stub.o" ] && [ -d "$KEXT" ] || exit 1'''


class Stop(RuntimeError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise Stop('Nu este un obiect JSON: ' + str(path))
    return value


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def safe_relative(text: str) -> Path:
    p = PurePosixPath(text)
    if not text or p.is_absolute() or '..' in p.parts or '\\' in text or '\x00' in text:
        raise Stop('Cale relativa invalida: ' + repr(text))
    return Path(*p.parts)


def inside(base: Path, value: str | Path) -> Path:
    p = base / safe_relative(str(value))
    try:
        p.resolve().relative_to(base.resolve())
    except ValueError:
        raise Stop('Calea iese din directorul permis: ' + str(p)) from None
    return p


def verify_file(path: Path, expected: str, size: int | None = None) -> None:
    if not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
        raise Stop('SHA256 lipsa/invalid pentru ' + str(path))
    if path.is_symlink() or not path.is_file():
        raise Stop('Fisier lipsa sau symlink neasteptat: ' + str(path))
    if size is not None and path.stat().st_size != size:
        raise Stop('Dimensiune diferita: ' + str(path))
    if sha(path) != expected:
        raise Stop('SHA256 diferit: ' + str(path))


def verify_inventory(root: Path, entries: dict) -> None:
    if not entries:
        raise Stop('Inventar gol')
    for name, info in entries.items():
        if not isinstance(info, dict) or 'sha256' not in info:
            raise Stop('Intrare de inventar neasteptata: ' + name)
        verify_file(inside(root, name), info['sha256'], info.get('bytes'))


def packager_wrapper(text: str) -> tuple[str, str]:
    """Two exact replacements, not a permissive regex that could skip checks."""
    if text.count(H_LINE) != 1 or text.count(BUILD_BLOCK) != 1:
        raise Stop('Constructorul upstream nu are blocurile exacte analizate; nu il modific automat.')
    new = text.replace(H_LINE, 'H=${HAO_STEP8_SOURCE:?missing verified source directory}', 1)
    new = new.replace(BUILD_BLOCK, REUSE_BLOCK, 1)
    diff = ''.join(difflib.unified_diff(text.splitlines(True), new.splitlines(True),
                                      'upstream/hao-image-payload', 'local/hao-image-payload-reuse'))
    return new, diff


def cache_uuid(path: Path) -> str:
    with path.open('rb') as f:
        header = f.read(104)
    if (len(header) < 104 or not header[:16].startswith(b'dyld_v') or
            b'x86_64' not in header[:16] or b'x86_64h' in header[:16]):
        raise Stop('Este necesar cache-ul generic x86_64, nu x86_64h.')
    uuid = header[88:104].hex()
    if uuid == '0' * 32:
        raise Stop('UUID de cache nul')
    return uuid


def check_candidate(payload: Path, expected_uuid: str, expected_core: dict) -> dict:
    """Structural/file checks. Does NOT assert runtime compatibility or boot."""
    m = read_json(payload / 'payload-manifest.json')
    b = read_json(payload / 'build.json')
    embed = read_json(payload / 'embed/manifest.json')
    if m.get('commit') != RUNTIME or m.get('os_build') != GOLDEN or m.get('layout_version') != 1:
        raise Stop('Identitatea payload-ului nu corespunde surselor fixate.')
    if m.get('clean') is not True:
        raise Stop('Generatorul a raportat surse modificate; nu pretind un build curat.')
    if str(m.get('cache_uuid', '')).replace('-', '').lower() != expected_uuid.lower():
        raise Stop('UUID-ul cache-ului din payload nu corespunde cache-ului Rosetta folosit.')
    if m.get('units_version') is not None or m.get('units_sha256') is not None or b.get('interface_units') is not None:
        raise Stop('Acest pas este bootstrap fara unitati externe; date de interfata neasteptate.')
    for rel in ('root/usr/lib/hao/if', 'root/usr/lib/hao/libhao_async_contract.dylib',
                'root/usr/lib/hao/async-contract.json'):
        if os.path.lexists(payload / rel):
            raise Stop('Componenta externa neasteptata: ' + rel)
    entries = embed.get('files')
    if not isinstance(entries, list) or not entries:
        raise Stop('Lista executabilelor integrate este goala/invalida.')
    paths = [str(x['path']) for x in entries]
    if len(paths) != len(set(paths)):
        raise Stop('Executabile duplicate in manifest.')
    for p in paths:
        safe_relative(p)
    if not REQUIRED <= set(paths) or not REQUIRED <= set(embed.get('required', [])):
        raise Stop('launchd sau xpcproxy lipsesc din integrarea obligatorie.')
    if b.get('stub_identity', {}).get('diff') != 0:
        raise Stop('Verificarea identitatii stubs nu raporteaza zero diferente nepermise.')
    if b.get('dyld_fix') not in ('fixed', 'not affected'):
        raise Stop('Corectia dyld pentru Golden Gate nu a fost validata.')
    mapped = {'hao': 'root/usr/libexec/hao', 'libhao.dylib': 'root/usr/lib/hao/libhao.dylib',
              'libhao_identity.dylib': 'root/usr/lib/hao/libhao_identity.dylib'}
    for source, destination in mapped.items():
        verify_file(payload / destination, expected_core[source]['sha256'], expected_core[source].get('bytes'))
    listed = m.get('files')
    if not isinstance(listed, dict) or not listed:
        raise Stop('Manifestul nu listeaza fisiere.')
    for rel, digest in listed.items():
        verify_file(inside(payload, rel), digest)
    actual = set()
    for folder, dirs, files in os.walk(payload, followlinks=False):
        if any((Path(folder) / d).is_symlink() for d in dirs):
            raise Stop('Symlink de director neasteptat in payload.')
        actual.update(str((Path(folder) / name).relative_to(payload)) for name in files)
    if actual - {'payload-manifest.json'} != set(listed):
        raise Stop('Fisiere lipsa sau nelistate in payload.')
    return {'embedded_programs': len(entries), 'required': sorted(REQUIRED),
            'dyld_fix': b['dyld_fix'], 'stub_identity': b['stub_identity'],
            'trusted_cdhashes': b.get('trusted_cdhashes'), 'stub_identities': b.get('stub_identities'),
            'file_hashes_checked': len(listed), 'external_interface_units': 0,
            'external_async_provider': False, 'compatibility_complete': False}


def clang_launcher(clang: Path, sdk: Path) -> str:
    """The absolute compiler path avoids recursively invoking this launcher."""
    if not clang.is_absolute() or not sdk.is_absolute():
        raise Stop('Compilatorul si SDK-ul trebuie sa aiba cai absolute.')
    return '#!/bin/sh\nexec %s -isysroot %s "$@"\n' % (shlex.quote(str(clang)), shlex.quote(str(sdk)))


def selected_environment(base: dict, bindir: Path, clang: Path, sdk: Path,
                         developer: str, source: Path, build_rel: Path) -> dict:
    env = dict(base)
    for key in list(env):
        if key.startswith(('DYLD_', 'HAO_')) or key in (
                'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'BASH_ENV', 'ENV',
                'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LD_LIBRARY_PATH'):
            env.pop(key, None)
    env.update(PATH=f'{bindir}:{clang.parent}:/usr/bin:/bin:/usr/sbin:/sbin',
               SDKROOT=str(sdk), DEVELOPER_DIR=developer,
               PYTHONDONTWRITEBYTECODE='1',
               HAO_STEP8_SOURCE=str(source), HAO_STEP8_PREBUILT=build_rel.as_posix())
    return env


def checkpoint_root(repo: Path, previous: dict) -> Path:
    """Accept a recorded completed copy, never infer success from a folder alone."""
    if (previous.get('patcher_commit') != PATCHER or previous.get('runtime_commit') != RUNTIME
            or previous.get('golden_build') != GOLDEN or previous.get('model') != 'MacBookPro9,1'):
        raise Stop('Raportul anterior nu corespunde commiturilor si tintei acestui proiect.')
    copies = previous.get('root_view_copies')
    if not isinstance(copies, dict) or set(copies) != {'filesystem', 'os', 'app'}:
        raise Stop('Raportul anterior nu confirma toate cele trei copii. Nu recopiaza automat.')
    for name, data in copies.items():
        if (not isinstance(data, dict) or not isinstance(data.get('files'), int)
                or data['files'] <= 0 or data.get('special_skipped')):
            raise Stop('Copie incompleta sau intrari omise pentru ' + name)
    root = inside(repo, previous.get('root_view', ''))
    tmp = (repo / 'store/tmp').resolve()
    if (root.is_symlink() or not root.is_dir() or root.name != 'root-view'
            or root.parent.parent.resolve() != tmp or not root.parent.name.startswith('mbp91-step8-')):
        raise Stop('Root-view anterior lipseste sau are o cale neasteptata; nu incep alta copiere.')
    # Reject symlink ancestors and writable-by-other-user work directories.
    if root != root.resolve():
        raise Stop('Root-view trece printr-o legatura simbolica; nu il reutilizez.')
    for p in (root.parent, root):
        st = p.stat()
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o022:
            raise Stop('Directorul de lucru nu apartine exclusiv utilizatorului: ' + str(p))
    for rel in ('System/Volumes/Preboot/Cryptexes/OS', 'System/Volumes/Preboot/Cryptexes/App'):
        p = inside(root, rel)
        if not p.is_dir() or p.is_symlink() or p != p.resolve():
            raise Stop('Lipseste copia reala a cryptex-ului: ' + rel)
    sv_path = inside(root, 'System/Library/CoreServices/SystemVersion.plist')
    with sv_path.open('rb') as stream:
        sv = plistlib.load(stream)
    if sv.get('ProductBuildVersion') != GOLDEN:
        raise Stop('Root-view nu contine SystemVersion pentru ' + GOLDEN)
    for rel in sorted(REQUIRED | {'usr/lib/dyld'}):
        p = inside(root, rel)
        if p.is_symlink() or not p.is_file():
            raise Stop('Fisier obligatoriu lipsa sau symlink: ' + rel)
    return root


def verify_probe_manifest(probe: Path, root: Path, uuid: str) -> dict:
    m = read_json(probe / 'manifest.json')
    entries = m.get('files', [])
    if not isinstance(entries, list) or len(entries) != 2:
        raise Stop('Proba nu a produs exact cele doua stubs obligatorii.')
    if set(m.get('required', [])) != REQUIRED or {x.get('path') for x in entries} != REQUIRED:
        raise Stop('Proba nu include launchd si xpcproxy.')
    if str(m.get('x86_cache_uuid', '')).replace('-', '').lower() != uuid.lower():
        raise Stop('Proba a folosit alt cache decat cel Rosetta verificat.')
    for e in entries:
        verify_file(inside(probe, e['stub']), e['stub_sha256'])
        verify_file(inside(root, e['path']), e['source_sha256'])
        for binding in e.get('bound', []):
            if binding.get('file'):
                verify_file(inside(root, binding['file']), binding['sha256'])
    return {'required': sorted(REQUIRED), 'embedded': 2,
            'manifest_sha256': sha(probe / 'manifest.json'), 'programs_executed': False}


class Job:
    def __init__(self, repo: Path, keep_root: bool):
        self.repo = repo
        self.local = repo / 'local/mbp91'
        self.local.mkdir(parents=True, exist_ok=True)
        self.previous = read_json(self.local / 'step8-result.json')
        self.resume_root = checkpoint_root(repo, self.previous)
        self.run_id = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work = repo / 'store/tmp' / ('mbp91-step8-' + self.run_id)
        self.work.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(self.work, 0o700)
        self.log_path = self.local / 'step8-link-build.log'
        if self.log_path.exists():
            shutil.copyfile(self.log_path, self.work / 'previous-step8-link-build.log')
        self.log = self.log_path.open('w', encoding='utf-8')
        self.keep_root = keep_root
        self.result = {'schema': 'hao-mbp91-step8-bootstrap-v1', 'run_id': self.run_id,
                       'script_revision': 'step8-link-resume-v4',
                       'copy_policy': 'Reuse completed root-view; NO copying, downloads or sudo',
                       'patcher_commit': PATCHER, 'runtime_commit': RUNTIME, 'golden_build': GOLDEN,
                       'model': 'MacBookPro9,1', 'variant': 'local-bootstrap-without-external-compatibility',
                       'step_complete': False, 'bootstrap_payload_ready': False,
                       'runtime_payload_complete': False, 'published_payload_reproduced': False,
                       'image_built': False, 'boot_validated': False, 'commands': [], 'errors': [],
                       'remaining': ['26B131 external interface units and matching thunk libraries',
                                     'Matching optional async provider for full compatibility',
                                     'Golden Gate graphics/kernel compatibility artifacts and final assembly',
                                     'HaoExec stamping against final BootKC and real MacBookPro9,1 boot']}
        old = self.local / 'step8-result.json'
        if old.exists():
            shutil.copyfile(old, self.work / 'previous-step8-result.json')
        self.result.update(root_view=str(self.resume_root.relative_to(repo)),
                           root_view_copies=self.previous['root_view_copies'],
                           previous_run_id=self.previous.get('run_id'),
                           root_view_reused=True, recopy_performed=False,
                           x86_cache_uuid=self.previous.get('x86_cache_uuid'),
                           userspace_pin=self.previous.get('userspace_pin'))
        self.save()

    def save(self):
        write_json(self.local / 'step8-result.json', self.result)

    def run(self, argv, *, capture=False, env=None, cwd=None, timeout=7200):
        argv = [str(x) for x in argv]
        self.log.write('$ ' + shlex.join(argv) + '\n'); self.log.flush()
        start = time.monotonic()
        row = {'argv': argv, 'cwd': str(cwd or self.repo)}
        self.result['commands'].append(row)
        if capture:
            p = subprocess.run(argv, cwd=cwd or self.repo, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            self.log.write(p.stdout.decode(errors='replace') + p.stderr.decode(errors='replace'))
            result = p.stdout
        else:
            p = subprocess.Popen(argv, cwd=cwd or self.repo, env=env, stdin=subprocess.DEVNULL,
                                 stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
            last = start
            try:
                while p.poll() is None:
                    now = time.monotonic()
                    if now - start > timeout:
                        raise Stop('Limita de executie atinsa; vezi step8-link-build.log.')
                    if now - last > 30:
                        print('    Procesul lucreaza; log: local/mbp91/step8-link-build.log', flush=True)
                        last = now
                    time.sleep(0.4)
            except BaseException:
                if p.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(p.pid, signal.SIGKILL)
                        p.wait()
                raise
            result = b''
        row.update(returncode=p.returncode, elapsed_s=round(time.monotonic() - start, 2))
        self.log.flush(); self.save()
        if p.returncode:
            raise Stop('Comanda a esuat (cod %d): %s; vezi step8-link-build.log' % (p.returncode, argv[0]))
        return result

    def git(self, root, *args):
        return self.run(['/usr/bin/git', '-C', root, *args], capture=True, timeout=120).decode().strip()

    @contextlib.contextmanager
    def mounted(self, image: Path, label: str):
        point = Path(tempfile.mkdtemp(prefix='mount-' + label + '-', dir=self.work))
        self.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-owners', 'off',
                  '-mountpoint', point, image], capture=True, timeout=300)
        try:
            yield point
        finally:
            try:
                self.run(['/usr/bin/hdiutil', 'detach', point], capture=True, timeout=120)
                point.rmdir()
            except Exception as e:
                self.result.setdefault('cleanup_warnings', []).append(str(e))
                print('  Nota: detasarea a raportat o problema; vezi raportul.', flush=True)
                self.save()

    def prerequisites(self):
        print('1/4 Reutilizez runtime-ul verificat si imaginile Golden Gate existente.', flush=True)
        if self.git(self.repo, 'rev-parse', 'HEAD') != PATCHER:
            raise Stop('Copia Hao nu este la commitul fixat.')
        guarded = ('pipeline/lock.py', 'tools/hao-contract')
        if self.git(self.repo, 'status', '--porcelain', '--', *guarded):
            raise Stop('Uneltele upstream de validare au modificari locale.')
        r = read_json(self.local / 'step7-result.json')
        if r.get('runtime_commit') != RUNTIME or not all(r.get(k) is True for k in
                ('step_complete', 'target_runtime_built', 'unstamped_kext_built', 'host_tests_passed')):
            raise Stop('Pasul 7 corectat nu este complet/verificat.')
        if r.get('errors'):
            raise Stop('Raportul pasului 7 contine erori nerezolvate.')
        self.source = inside(self.repo, r['source_path'])
        if (self.git(self.source, 'rev-parse', 'HEAD') != RUNTIME or
                self.git(self.source, 'rev-parse', 'HEAD^{tree}') != RTREE or
                self.git(self.source, 'status', '--porcelain')):
            raise Stop('Sursa runtime nu este copia curata verificata.')
        core = inside(self.repo, r['core_artifact'])
        verify_file(core / 'build.json', r['core_artifact_record_sha256'])
        core_record = read_json(core / 'build.json')
        verify_inventory(core, core_record['files'])
        self.build_rel = safe_relative(r['build_directories']['target'])
        self.build = inside(self.source, self.build_rel)
        self.expected_core = r['target_runtime_files']
        for name in RUNTIME_NAMES:
            info = self.expected_core[name]
            verify_file(inside(self.build, name), info['sha256'], info.get('bytes'))
        for rel, info in core_record['files'].items():
            if rel.startswith('HaoExec.kext/'):
                verify_file(inside(self.build, rel), info['sha256'], info.get('bytes'))
        self.run(['/usr/bin/codesign', '--verify', '--verbose=2', self.build / 'HaoExec.kext'], capture=True)
        row = self.repo / 'pipeline/inputs/golden/26B131/golden_gate_userspace'
        lines = [s.partition('#')[0].strip() for s in row.read_text().splitlines()]
        lines = [s for s in lines if s]
        if len(lines) != 1 or lines[0].split(None, 1)[0] != USERSPACE_SHA:
            raise Stop('Intrarea userspace nu corespunde pinului Hao.')
        payload = self.run([sys.executable, '-I', '-B', self.repo / 'pipeline/lock.py', 'path',
                            row.parent, row.name], capture=True).decode().strip()
        self.images = Path(payload).resolve()
        try:
            self.images.relative_to((self.repo / 'store').resolve())
        except ValueError:
            raise Stop('Imaginile trebuie sa fie in store/ pentru acest pas.') from None
        for name in ('filesystem', 'os', 'app', 'rosetta'):
            if not (self.images / (name + '.dmg')).is_file():
                raise Stop('Lipseste imaginea ' + name)
        raw = (self.source / 'tools/hao-image-payload').read_bytes()
        if git_blob(raw) != PACKAGER_BLOB:
            raise Stop('Constructorul runtime nu este versiunea inspectata.')
        wrapper, diff = packager_wrapper(raw.decode())
        self.wrapper = self.work / 'hao-image-payload-reuse.sh'
        self.wrapper.write_text(wrapper, encoding='utf-8')
        (self.local / 'step8-packager.patch').write_text(diff, encoding='utf-8')
        self.run(['/bin/bash', '-n', self.wrapper], capture=True)
        bindir = self.work / 'bin'; bindir.mkdir()
        for name in ('python3', 'python3.14'):
            (bindir / name).symlink_to(Path(sys.executable).resolve())
        query_env = dict(os.environ)
        for key in list(query_env):
            if key.startswith(('DYLD_', 'HAO_')) or key in (
                    'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'BASH_ENV', 'ENV', 'DEVELOPER_DIR'):
                query_env.pop(key, None)
        query_env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        developer = self.run(['/usr/bin/xcode-select', '-p'], capture=True,
                             env=query_env).decode().strip()
        # Honour the system-selected Xcode, not a stale inherited DEVELOPER_DIR.
        query_env['DEVELOPER_DIR'] = developer
        clang = Path(self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--find', 'clang'],
                              capture=True, env=query_env).decode().strip()).resolve()
        sdk = Path(self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'],
                            capture=True, env=query_env).decode().strip()).resolve()
        sdk_version = self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'],
                               capture=True, env=query_env).decode().strip()
        if not clang.is_file() or not sdk.is_dir() or sdk == Path('/'):
            raise Stop('Xcode nu a furnizat un compilator si un SDK valide.')
        system_tbd = sdk / 'usr/lib/libSystem.tbd'
        if not system_tbd.is_file():
            raise Stop('SDK-ul selectat nu contine usr/lib/libSystem.tbd: ' + str(sdk))
        # The upstream embedder invokes "clang", not xcrun. Make its SDK explicit.
        launcher = bindir / 'clang'
        launcher.write_text(clang_launcher(clang, sdk), encoding='utf-8')
        launcher.chmod(0o700)
        self.env = selected_environment(os.environ, bindir, clang, sdk, developer,
                                        self.source, self.build_rel)
        self.run(['/bin/sh', '-n', launcher], capture=True, env=self.env)
        self.result['toolchain'] = dict(clang=str(clang), sdk=str(sdk), sdk_version=sdk_version,
                                        developer=developer, sdk_libSystem_tbd_sha256=sha(system_tbd),
                                        clang_launcher_sha256=sha(launcher), deployment_target='27.0')
        print('    SDK explicit: macOS %s; -isysroot si SDKROOT sunt setate local.' % sdk_version,
              flush=True)
        self.result.update(core_artifact=r['core_artifact'],
                           core_record_sha256=r['core_artifact_record_sha256'],
                           source_path=r['source_path'],
                           userspace_pin=USERSPACE_SHA,
                           upstream_packager_blob=PACKAGER_BLOB,
                           local_packager_sha256=sha(self.wrapper),
                           compilation_repeated=False, tests_repeated=False)
        self.save()


    def link_preflight(self, root: Path, x86: Path, uuid: str):
        print('2/4 Verific linkarea si integrarea launchd/xpcproxy, inaintea lotului complet.', flush=True)
        trial = self.work / 'stub-link-probe'
        # Only relink an existing object. Do not execute it or recompile the runtime.
        command = [self.work / 'bin/clang', '-arch', 'x86_64', '-mmacosx-version-min=27.0',
                   self.build / 'front/stub.o', '-L' + str(self.build), '-lhao', '-lhao_identity',
                   '-Wl,-rpath,/usr/lib/hao', '-Wl,-no_adhoc_codesign', '-o', trial]
        self.run(command, env=self.env, timeout=120)
        self.result['link_probe'] = dict(passed=True, binary_sha256=sha(trial), executed=False)
        probes = self.work / 'probe-embed'
        commands = [sys.executable, '-I', '-B', self.source / 'tools/hao-embed',
                    '--stub', self.build / 'hao-stub', '--stubs', probes,
                    '--root', root, '--x86-cache', x86]
        for rel in sorted(REQUIRED):
            commands += ['--require', rel]
        commands += [root / rel for rel in sorted(REQUIRED)]
        self.run(commands, env=self.env, timeout=600)
        info = verify_probe_manifest(probes, root, uuid)
        identity = self.work / 'probe-identity'
        self.run([sys.executable, '-I', '-B', self.source / 'tools/stub_identity_gate.py',
                  '--stubs', probes, '--root', root, '--x86-cache', x86, '--out', identity],
                 env=self.env, timeout=600)
        info['identity_gate_passed'] = True
        self.result['embed_probe'] = info
        for p, name in ((probes / 'manifest.json', 'step8-link-probe-manifest.json'),
                        (identity / 'summary.md', 'step8-link-probe-identity.md'),
                        (identity / 'diff.tsv', 'step8-link-probe-identity-diff.tsv')):
            if p.is_file():
                shutil.copyfile(p, self.local / name)
        self.save()
        print('    Linkare: OK. launchd + xpcproxy: OK. Verificarea identitatii: OK.', flush=True)

    def build_payload(self):
        root = self.resume_root
        if self.previous.get('userspace_pin') != USERSPACE_SHA:
            raise Stop('Copia anterioara nu declara imaginile Golden Gate fixate.')
        print('    Reutilizez System + OS/App: ' + str(root.relative_to(self.repo)), flush=True)
        with self.mounted(self.images / 'rosetta.dmg', 'rosetta') as rosetta:
            x86 = rosetta / 'System/Library/dyld'
            uuid = cache_uuid(x86 / 'dyld_shared_cache_x86_64')
            if uuid.lower() != str(self.previous.get('x86_cache_uuid', '')).replace('-', '').lower():
                raise Stop('Cache-ul Rosetta nu corespunde celui folosit la copia anterioara.')
            self.result.update(root_view=str(root.relative_to(self.repo)), x86_cache_uuid=uuid,
                               mount_policy='Rosetta only: read-only, owners off')
            self.save()
            self.link_preflight(root, x86, uuid)
            print('3/4 Generez stubs, listele de incredere, corectia dyld si manifestul payload-ului.', flush=True)
            self.partial = self.repo / 'store/artifacts' / ('mbp91-hao-bootstrap-26B131-' + self.run_id + '.partial')
            self.partial.parent.mkdir(parents=True, exist_ok=True)
            self.result['partial_payload'] = str(self.partial.relative_to(self.repo)); self.save()
            self.run(['/bin/bash', self.wrapper, '--macos-min', '27.0', '--require-dyld-fix',
                      '--x86-cache', x86, self.partial, root], env=self.env)
            print('4/4 Validez candidatul local si inregistrez explicit componentele absente.', flush=True)
            summary = check_candidate(self.partial, uuid, self.expected_core)
            verify_file(self.partial / 'HaoExec.kext/Contents/MacOS/HaoExec',
                        read_json(self.local / 'step7-result.json')['kext']['binary']['sha256'])
            self.run(['/usr/bin/codesign', '--verify', '--verbose=2', self.partial / 'HaoExec.kext'], capture=True)
            scope = {'variant': 'local-bootstrap-without-external-compatibility',
                     'purpose': 'Packaging and future first-boot experiment; NOT a proven desktop payload',
                     'runtime_commit': RUNTIME, 'core_record_sha256': self.result['core_record_sha256'],
                     'upstream_packager_blob': PACKAGER_BLOB, 'wrapper_sha256': sha(self.wrapper),
                     'source_tree_clean': True, 'reused_compiled_core': True,
                     'linker_toolchain': self.result['toolchain'], 'root_view_reused': True,
                     'external_interface_units': False, 'external_thunk_libraries': False,
                     'async_provider': False, 'aot_caches_generated': False,
                     'compatibility_complete': False, 'boot_validated': False,
                     'note': 'The upstream optional inputs were omitted, not replaced by empty/fake data.'}
            write_json(self.partial / 'LOCAL-SCOPE.json', scope)
            b = read_json(self.partial / 'build.json')
            b['local_scope'] = scope
            write_json(self.partial / 'build.json', b)
            m = read_json(self.partial / 'payload-manifest.json')
            m['version'] = GOLDEN + '-' + RUNTIME[:12] + '-mbp91-bootstrap-' + self.result['core_record_sha256'][:12]
            m['local_variant'] = scope['variant']
            m['compatibility_complete'] = False
            m['files']['build.json'] = sha(self.partial / 'build.json')
            m['files']['LOCAL-SCOPE.json'] = sha(self.partial / 'LOCAL-SCOPE.json')
            write_json(self.partial / 'payload-manifest.json', m)
            summary = check_candidate(self.partial, uuid, self.expected_core)
            checker = runpy.run_path(str(self.repo / 'tools/hao-contract/hao_contract.py'))
            errors = checker['check_payload'](self.repo, {'manifest': str(self.partial / 'payload-manifest.json'),
                                                       'os_build': GOLDEN, 'layout_version': 1})
            if errors:
                raise Stop('Contractul Hao respinge payload-ul: ' + '; '.join(errors[:20]))
            final = self.partial.with_name(self.partial.name.removesuffix('.partial'))
            if final.exists():
                raise Stop('Directorul final exista deja; nu il suprascriu.')
            self.partial.rename(final)
            relative = str(final.relative_to(self.repo))
            # Separate local receipt. Do not rewrite the official hao_runtime input.
            lock = runpy.run_path(str(self.repo / 'pipeline/lock.py'))
            payload_sha = lock['content_sha256'](str(final))
            receipt = '# Local bootstrap ONLY; no external interfaces/thunks/async provider.\n'
            receipt += '# check: payload os_build=26B131 layout_version=1\n'
            receipt += payload_sha + ' ' + relative + '\n'
            (self.local / 'step8-bootstrap-input.txt').write_text(receipt)
            self.result.update(step_complete=True, bootstrap_payload_ready=True,
                               bootstrap_artifact=relative, payload_content_sha256=payload_sha,
                               payload_manifest_sha256=sha(final / 'payload-manifest.json'),
                               validation=summary, upstream_contract_passed=True,
                               official_runtime_row_unchanged=True)
            for name in ('build.json', 'payload-manifest.json', 'LOCAL-SCOPE.json'):
                shutil.copyfile(final / name, self.local / ('step8-' + name))
            for source, name in (('embed/embed.log', 'step8-link-embed.log'),
                                 ('embed/identity/diff.tsv', 'step8-link-identity-diff.tsv'),
                                 ('embed/identity/summary.md', 'step8-link-identity-summary.md')):
                if (final / source).is_file():
                    shutil.copyfile(final / source, self.local / name)
            self.save()
        self.result['temporary_root_view_removed'] = False
        self.save()

    def finish(self):
        self.result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save(); self.log.flush()
        # Capture failure details from the generated payload without any binaries.
        partial = getattr(self, 'partial', None)
        if partial is not None and partial.is_dir():
            for rel, name in (('embed/embed.log', 'step8-link-embed.log'),
                              ('embed/identity.log', 'step8-link-identity.log'),
                              ('embed/identity/summary.md', 'step8-link-identity-summary.md')):
                p = partial / rel
                if p.is_file():
                    shutil.copyfile(p, self.local / name)
        if self.result.get('errors'):
            for p in (self.local / 'step8-link-embed.log', self.log_path):
                if p.is_file():
                    tail = p.read_text(errors='replace').splitlines()[-12:]
                    print('\nUltimele mesaje din ' + p.name + ':', flush=True)
                    for line in tail:
                        print(line[:1600], flush=True)
        archive = Path.home() / 'Desktop/HAO-mbp91-step8-link.zip'

        temp = archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
            current_names = {'step8-result.json', 'step8-packager.patch', 'step8-bootstrap-input.txt',
                             'step8-build.json', 'step8-payload-manifest.json', 'step8-LOCAL-SCOPE.json'}
            for p in sorted(self.local.glob('step8-*')):
                if (p.name.startswith('step8-link-') or p.name in current_names) and p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.log', '.patch', '.txt', '.tsv', '.md'):
                    # Limit unexpectedly verbose logs; retain their tails and state that truncation occurred.
                    raw = p.read_bytes()
                    if len(raw) > 16 * 1024 * 1024:
                        raw = b'[Report copy truncated: last 16 MiB; full local file retained.]\n' + raw[-16*1024*1024:]
                    z.writestr(str(p.relative_to(self.repo)), raw)
            z.write(Path(__file__).resolve(), 'HAO-mbp91-step8-link.py')
            z.writestr('READ-ME.txt', 'Metadata only. Experimental bootstrap payload, not the complete validated Hao desktop payload.\n')
        os.replace(temp, archive)
        self.log.close()
        print('\nPayload experimental de bootstrap pregatit: ' + ('DA' if self.result['bootstrap_payload_ready'] else 'NU'))
        if self.result.get('bootstrap_payload_ready'):
            print('Executabile integrate: ' + str(self.result['validation']['embedded_programs']))
            print('Contract de fisiere Hao: DA')
            print('Artefact: ' + str(self.repo / self.result['bootstrap_artifact']))
        print('Interfete externe / thunks / provider async: ABSENTE, nu simulate.')
        print('Payload complet de compatibilitate: NU. Imagine bootabila / boot validat: NU.')
        print('Arhiva MICA de trimis: ' + str(archive))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise Stop('Acest pas necesita macOS pe calculatorul Intel de construire.')
    if sys.version_info < (3, 14):
        raise Stop('Ruleaza cu python3.14.')
    if os.geteuid() == 0:
        raise Stop('Ruleaza fara sudo, din contul folosit pentru pasul 7.')
    if not (repo / 'local/mbp91/step7-result.json').is_file():
        raise Stop('Nu gasesc proiectul cu pasul 7; foloseste Desktop/hao-patcher-mbp91.')
    local = repo / 'local/mbp91'
    with (local / 'step8.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('Pasul 8 ruleaza deja in aceasta copie.') from None
        current = read_json(local / 'step8-result.json')
        if current.get('bootstrap_payload_ready') is True:
            print('Payload-ul este deja inregistrat ca pregatit; nu il reconstruiesc.')
            return 0
        job = Job(repo, True)
        rc = 0
        try:
            job.prerequisites()
            job.build_payload()
        except (Exception, KeyboardInterrupt) as e:
            rc = 1
            message = str(e) or 'Intrerupt de utilizator.'
            print('\nOPRIT: ' + message, flush=True)
            job.result['errors'].append(message)
            traceback.print_exc(file=job.log)
        finally:
            job.finish()
        return rc


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Stop as e:
        print('OPRIT: ' + str(e), file=sys.stderr)
        raise SystemExit(1)
