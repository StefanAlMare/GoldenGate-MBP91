#!/usr/bin/env python3
"""HAO / MBP9,1 step 8 — an explicitly LIMITED bootstrap payload, built locally.

Uses the verified runtime core from step 7, the existing Golden Gate System/OS/App
images, and the generic x86_64 Rosetta cache. Invokes hao-image-payload's embedding,
identity gate, trust-list and dyld-fix code; no Apple download, make or kext rebuild.

This is NOT the author's complete desktop payload. The optional per-library
interface units, thunk-pair libraries and async provider are not fabricated. They
remain absent and are recorded as unresolved. No official input row is replaced.

The only two edits to a temporary copy of the upstream packager select its source
folder explicitly and replace its make/kext-build block with verified existing
outputs. The original checkout stays unchanged. The exact edits are recorded.

Correction v2: regular files of zero length are recreated in the private staging
view from their stat metadata, without reading the protected source (e.g. .file).
This never skips a non-empty file or follows a symlink. Directory traversal errors
are reported rather than silently hiding missing input. Compiled binaries and
upstream integrity checks are unchanged.

Run on the Intel build Mac, Python 3.14, from Desktop/hao-patcher-mbp91, without sudo.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import fcntl
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


def real_dirs(base: Path, relative: Path, replaced: list[dict] | None = None) -> Path:
    """Make a staging path without ever following an existing directory symlink."""
    current = base
    for part in safe_relative(relative.as_posix()).parts:
        current = current / part
        if current.is_symlink():
            if replaced is None:
                raise Stop('Symlink pe calea de copiere: ' + str(current))
            replaced.append({'path': str(current.relative_to(base)), 'previous_link': os.readlink(current)})
            current.unlink()
        if current.exists() and not current.is_dir():
            raise Stop('Nu este director: ' + str(current))
        current.mkdir(exist_ok=True, mode=0o755)
    return current


def walk_error(error: OSError) -> None:
    """Never silently omit an unreadable directory from the embedding inputs."""
    raise error


def tree_size(root: Path) -> dict:
    count = total = links = 0
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = [n for n in dirs if not (Path(folder) / n).is_symlink()]
        for name in files:
            st = (Path(folder) / name).lstat()
            if stat.S_ISREG(st.st_mode):
                count += 1
                total += st.st_size  # intentionally conservative: count hardlinks again
            elif stat.S_ISLNK(st.st_mode):
                links += 1
    return {'files': count, 'bytes_upper_bound': total, 'symlink_files': links}


def copy_view(src: Path, dest: Path, progress=None) -> dict:
    """Content/mode copy only: no source owners, SIP flags, ACLs or host xattrs.

    Preserve hardlinks and symlink text, but never follow source/destination links.
    This is an embedding input view, NOT a disk image or installed System tree.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        raise Stop('Root de copiere este symlink')
    hardlinks: dict[tuple[int, int], Path] = {}
    result = {'files': 0, 'bytes_copied': 0, 'symlinks': 0, 'hardlinks': 0,
              'special_skipped': [], 'empty_files_from_metadata': 0,
              'empty_file_samples': []}
    last = time.monotonic()
    for folder, dirs, files in os.walk(src, followlinks=False, onerror=walk_error):
        dirs.sort(); files.sort()
        rel = Path(folder).relative_to(src)
        outdir = dest if rel == Path('.') else real_dirs(dest, rel)
        for name in list(dirs):
            source = Path(folder) / name
            out = outdir / name
            if source.is_symlink():
                if os.path.lexists(out):
                    raise Stop('Coliziune in staging: ' + str(out))
                out.symlink_to(os.readlink(source)); result['symlinks'] += 1
                dirs.remove(name)
            else:
                real_dirs(dest, out.relative_to(dest))
        for name in files:
            source, out = Path(folder) / name, outdir / name
            if os.path.lexists(out):
                raise Stop('Coliziune in staging: ' + str(out))
            st = source.lstat()
            if stat.S_ISLNK(st.st_mode):
                out.symlink_to(os.readlink(source)); result['symlinks'] += 1
            elif stat.S_ISREG(st.st_mode):
                key = (st.st_dev, st.st_ino)
                if st.st_nlink > 1 and key in hardlinks:
                    os.link(hardlinks[key], out); result['hardlinks'] += 1
                else:
                    if st.st_size == 0:
                        # A regular, empty file has no payload bytes to read. Some
                        # read-only system images contain mode-000 placeholders.
                        # Recreate only their empty content, in this private view;
                        # the source is never chmod'ed, opened or modified.
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        flags |= getattr(os, 'O_NOFOLLOW', 0)
                        fd = os.open(out, flags, 0o600)
                        os.close(fd)
                        result['empty_files_from_metadata'] += 1
                        relative = source.relative_to(src).as_posix()
                        if len(result['empty_file_samples']) < 64:
                            result['empty_file_samples'].append({
                                'path': relative, 'source_mode': oct(stat.S_IMODE(st.st_mode)),
                                'source_bytes': 0, 'action': 'recreated-empty-in-private-view'})
                        if relative == '.file':
                            print('    .file: 0 octeti verificati; recreat gol in copia temporara, fara citirea sursei.',
                                  flush=True)
                    else:
                        # Do not suppress permissions errors on files with content.
                        shutil.copyfile(source, out, follow_symlinks=False)
                    os.chmod(out, (stat.S_IMODE(st.st_mode) & 0o777) | 0o600)
                    hardlinks[key] = out
                    result['bytes_copied'] += st.st_size
                result['files'] += 1
            else:
                result['special_skipped'].append(str(source.relative_to(src)))
        if progress and time.monotonic() - last >= 30:
            progress(result); last = time.monotonic()
    return result


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


class Job:
    def __init__(self, repo: Path, keep_root: bool):
        self.repo = repo
        self.local = repo / 'local/mbp91'
        self.local.mkdir(parents=True, exist_ok=True)
        self.run_id = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work = repo / 'store/tmp' / ('mbp91-step8-' + self.run_id)
        self.work.mkdir(parents=True, exist_ok=False)
        self.log_path = self.local / 'step8-build.log'
        if self.log_path.exists():
            shutil.copyfile(self.log_path, self.work / 'previous-step8-build.log')
        self.log = self.log_path.open('w', encoding='utf-8')
        self.keep_root = keep_root
        self.result = {'schema': 'hao-mbp91-step8-bootstrap-v1', 'run_id': self.run_id,
                       'script_revision': 'step8-fix-empty-files-v2',
                       'copy_policy': 'Recreate stat-confirmed zero-byte regular files; never suppress non-empty copy errors',
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
                        raise Stop('Limita de executie atinsa; vezi step8-build.log.')
                    if now - last > 30:
                        print('    Procesul lucreaza; log: local/mbp91/step8-build.log', flush=True)
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
            raise Stop('Comanda a esuat (cod %d): %s; vezi step8-build.log' % (p.returncode, argv[0]))
        return result

    def git(self, root, *args):
        return self.run(['/usr/bin/git', '-C', root, *args], capture=True, timeout=120).decode().strip()

    @contextlib.contextmanager
    def mounted(self, image: Path, label: str):
        point = Path(tempfile.mkdtemp(prefix='mount-' + label + '-', dir=self.work))
        self.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-owners', 'on',
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
        clang = self.run(['/usr/bin/xcrun', '--find', 'clang'], capture=True).decode().strip()
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(('DYLD_', 'HAO_')) or key in ('SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'BASH_ENV', 'ENV'):
                del self.env[key]
        self.env.update(PATH=f'{bindir}:{Path(clang).parent}:/usr/bin:/bin:/usr/sbin:/sbin',
                        PYTHONDONTWRITEBYTECODE='1', HAO_STEP8_SOURCE=str(self.source),
                        HAO_STEP8_PREBUILT=self.build_rel.as_posix())
        self.result.update(core_artifact=r['core_artifact'],
                           core_record_sha256=r['core_artifact_record_sha256'],
                           source_path=r['source_path'],
                           userspace_pin=USERSPACE_SHA,
                           upstream_packager_blob=PACKAGER_BLOB,
                           local_packager_sha256=sha(self.wrapper),
                           compilation_repeated=False, tests_repeated=False)
        self.save()

    def build_payload(self):
        with contextlib.ExitStack() as stack:
            mounts = {n: stack.enter_context(self.mounted(self.images / (n + '.dmg'), n))
                      for n in ('filesystem', 'os', 'app', 'rosetta')}
            sv = plistlib.loads((mounts['filesystem'] / 'System/Library/CoreServices/SystemVersion.plist').read_bytes())
            if sv.get('ProductBuildVersion') != GOLDEN:
                raise Stop('SystemVersion.plist nu este 26B131.')
            x86 = mounts['rosetta'] / 'System/Library/dyld'
            uuid = cache_uuid(x86 / 'dyld_shared_cache_x86_64')
            print('2/4 Pregatesc vederea offline System + OS/App pentru integrarea executabilelor.', flush=True)
            sizes = {n: tree_size(mounts[n]) for n in ('filesystem', 'os', 'app')}
            need = sum(x['bytes_upper_bound'] for x in sizes.values()) + 12 * GIB
            free = shutil.disk_usage(self.work).free
            if free < need:
                raise Stop('Spatiu insuficient pentru staging: %.1f GiB disponibili, %.1f GiB necesari (rezerva inclusa).'
                           % (free / GIB, need / GIB))
            root = self.work / 'root-view'; root.mkdir()
            self.result.update(root_view=str(root.relative_to(self.repo)), copy_requirements=sizes,
                               free_bytes_before_copy=free, x86_cache_uuid=uuid)
            self.save()
            progress = lambda s: print('    Copiere: %d fisiere, %.1f GiB.' %
                                        (s['files'], s['bytes_copied'] / GIB), flush=True)
            copies = {'filesystem': copy_view(mounts['filesystem'], root, progress)}
            replaced = []
            for name, role in (('os', 'OS'), ('app', 'App')):
                prefix = Path('System/Volumes/Preboot/Cryptexes') / role
                destination = real_dirs(root, prefix, replaced)
                copies[name] = copy_view(mounts[name], destination, progress)
            self.result.update(root_view_copies=copies, staging_placeholder_links_replaced=replaced)
            self.save()
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
            for source, name in (('embed/embed.log', 'step8-embed.log'),
                                 ('embed/identity/diff.tsv', 'step8-identity-diff.tsv'),
                                 ('embed/identity/summary.md', 'step8-identity-summary.md')):
                if (final / source).is_file():
                    shutil.copyfile(final / source, self.local / name)
            self.save()
        if not self.keep_root:
            shutil.rmtree(root)  # only the freshly created private input view
            self.result['temporary_root_view_removed'] = True
        self.save()

    def finish(self):
        self.result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save(); self.log.flush()
        # Capture failure details from the generated payload without any binaries.
        partial = getattr(self, 'partial', None)
        if partial is not None and partial.is_dir():
            for rel, name in (('embed/embed.log', 'step8-embed.log'),
                              ('embed/identity.log', 'step8-identity.log'),
                              ('embed/identity/summary.md', 'step8-identity-summary.md')):
                p = partial / rel
                if p.is_file():
                    shutil.copyfile(p, self.local / name)
        archive = Path.home() / 'Desktop/HAO-mbp91-step8-fix.zip'
        temp = archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(self.local.glob('step8-*')):
                if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.log', '.patch', '.txt', '.tsv', '.md'):
                    # Limit unexpectedly verbose logs; retain their tails and state that truncation occurred.
                    raw = p.read_bytes()
                    if len(raw) > 16 * 1024 * 1024:
                        raw = b'[Report copy truncated: last 16 MiB; full local file retained.]\n' + raw[-16*1024*1024:]
                    z.writestr(str(p.relative_to(self.repo)), raw)
            z.write(Path(__file__).resolve(), 'HAO-mbp91-step8-fix.py')
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
    parser.add_argument('--keep-root-view', action='store_true', help='retain the temporary input tree after success')
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
        job = Job(repo, args.keep_root_view)
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
