#!/usr/bin/env python3
"""HAO MBP9,1 / step 7: compile the pinned runtime core on an Intel macOS host.

This is a LOCAL SOURCE BUILD, not a reproduction of the unpublished public payload.
It builds x86_64 runtime binaries with deployment target 27.0 and the unstamped
HaoExec.kext. Eight independent upstream tests are compiled for 26.0 and run on
Tahoe. No ARM-native oracle, system installation or kernel loading is attempted.

The full image payload additionally needs the 26B131 interface units/thunks and
async provider. Upstream tools/hao-runtime-from-source takes these from the
published archive; compiling `make all` does not produce them. This script never
writes the pipeline's hao_runtime input or claims that payload is ready.

Run in ~/Desktop/hao-patcher-mbp91 with python3.14 -I, without sudo.
Only the pinned source checkout is downloaded. Existing Apple inputs are not read
or downloaded again. A small report ZIP is written even on a compilation error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import traceback
import zipfile

PATCHER_COMMIT = '6bd75aab112d1078acd8e75180eb510672461365'
RUNTIME_COMMIT = '1547dcb4e19a2ab0843086e3288223f998507a4c'
RUNTIME_TREE = '16170db522a965b863650459083a4593dba5b493'
RUNTIME_URL = 'https://github.com/lythka/hao-runtime.git'
GOLDEN = '26B131'
TARGET_BUILD = 'build/macos-27.0'
HOST_BUILD = 'build/macos-26.0'
CORE_FILES = {
    'hao': 2,
    'hao-stub': 2,
    'libhao.dylib': 6,
    'libhao_identity.dylib': 6,
    'front/stub.o': 1,
}
STATIC_FILES = ('libhaocore.a', 'libhao_codeid.a')
SIGNED_FILES = ('hao', 'libhao.dylib', 'libhao_identity.dylib')
# These targets do not execute ARM-native programs or require the unpublished
# compatibility archive. Timeouts are execution limits, not completion estimates.
HOST_TESTS = (
    ('test_imm_cond', 60), ('opts_test', 60), ('test_abi_layout', 60),
    ('test_gmap', 150), ('test_x86args', 60), ('test_round16', 150),
    ('test_helper_descriptor', 120), ('test_jit_vector', 300),
)
MISSING_PAYLOAD = [
    '26B131 interface-unit set and matching thunk-pair libraries',
    'Matching async provider: libhao_async_contract.dylib + async-contract.json',
    'System/OS/App executable embedding, dyld repair and complete payload manifest',
    'HaoExec identity stamping against the final BootKernelExtensions.kc',
]


class Stop(RuntimeError):
    pass


def stamp() -> str:
    return dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise Stop('Nu este un obiect JSON: ' + str(path))
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.tmp')
    partial.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(partial, path)


def safe_path(root: Path, relative: str) -> Path:
    p = Path(relative)
    if not relative or p.is_absolute() or '..' in p.parts:
        raise Stop('Cale relativa nepermisa: ' + str(relative))
    out = root / p
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        raise Stop('Cale care iese din director: ' + str(relative)) from None
    return out


def version_string(raw: int) -> str:
    return '%d.%d.%d' % (raw >> 16, (raw >> 8) & 255, raw & 255)


def macho_info(path: Path, filetype: int, minimum: str) -> dict:
    """Check a thin x86_64 Mach-O, its file type and declared minimum macOS."""
    with path.open('rb') as f:
        header = f.read(32)
        if len(header) != 32:
            raise Stop('Header Mach-O incomplet: ' + str(path))
        magic, cpu, subtype, actual_type, ncmds, size, _, _ = struct.unpack('<8I', header)
        if magic != 0xfeedfacf or cpu != 0x01000007:
            raise Stop('Nu este Mach-O thin x86_64: ' + str(path))
        if actual_type != filetype:
            raise Stop('Tip Mach-O neasteptat pentru %s: %s' % (path, actual_type))
        if not 0 < ncmds <= 65536 or size > 16 * 1024 * 1024:
            raise Stop('Load commands Mach-O nevalide: ' + str(path))
        commands = f.read(size)
    if len(commands) != size:
        raise Stop('Load commands Mach-O trunchiate: ' + str(path))
    pos, versions, uuids = 0, [], []
    for _ in range(ncmds):
        if pos + 8 > size:
            raise Stop('Mach-O: comanda lipsa: ' + str(path))
        cmd, length = struct.unpack_from('<II', commands, pos)
        if length < 8 or pos + length > size:
            raise Stop('Mach-O: lungime de comanda nevalida: ' + str(path))
        if cmd == 0x32:  # LC_BUILD_VERSION
            if length < 24:
                raise Stop('LC_BUILD_VERSION trunchiat')
            plat, minos, sdk = struct.unpack_from('<III', commands, pos + 8)
            if plat != 1:
                raise Stop('Platforma Mach-O nu este macOS')
            versions.append((version_string(minos), version_string(sdk)))
        elif cmd == 0x24:  # LC_VERSION_MIN_MACOSX
            if length < 16:
                raise Stop('LC_VERSION_MIN_MACOSX trunchiat')
            minos, sdk = struct.unpack_from('<II', commands, pos + 8)
            versions.append((version_string(minos), version_string(sdk)))
        elif cmd == 0x1b and length >= 24:
            uuids.append(commands[pos + 8:pos + 24].hex())
        pos += length
    if pos != size:
        raise Stop('Mach-O: sizeofcmds nu corespunde comenzilor')
    want = tuple(int(x) for x in minimum.split('.'))
    want = (want + (0, 0, 0))[:3]
    if len(versions) != 1 or tuple(map(int, versions[0][0].split('.'))) != want:
        raise Stop('Deployment target incorect pentru %s: %r, asteptat %s' % (path, versions, minimum))
    return {'architecture': 'x86_64', 'cpu_subtype': subtype, 'filetype': filetype,
            'minimum_macos': versions[0][0], 'sdk': versions[0][1], 'uuids': uuids,
            'bytes': path.stat().st_size, 'sha256': sha(path)}


def generated_inputs(source: Path) -> dict:
    lock = read_json(source / 'generated.lock')
    if lock.get('lock_version') != 1 or not isinstance(lock.get('files'), list) or not lock['files']:
        raise Stop('generated.lock nu are formatul asteptat')
    checked = {}
    for item in lock['files']:
        rel, want = item['path'], item['sha256']
        if rel in checked or not re.fullmatch(r'[0-9a-f]{64}', want):
            raise Stop('generated.lock: intrare invalida sau duplicata: ' + rel)
        p = safe_path(source, rel)
        if not p.is_file() or sha(p) != want:
            raise Stop('Date generate lipsa sau modificate: ' + rel)
        if item.get('os_build') not in (None, GOLDEN):
            raise Stop('Date generate pentru alt build: ' + rel)
        checked[rel] = want
    return {'lock_sha256': sha(source / 'generated.lock'), 'files': checked,
            'note': 'Compile-time tables only; not the complete image interface-unit set.'}


def make_command(clang: str, build: str, minimum: str, jobs: int, targets: list[str]) -> list[str]:
    if any(c.isspace() for c in clang):
        raise Stop('Calea compilatorului contine spatii; wrapperul make necesita adaptare explicita.')
    return ['/usr/bin/make', '-j%d' % jobs, 'CC=' + clang, 'B=' + build,
            'MACOS_MIN=' + minimum, *targets]


def build_environment(sdk: str, toolchain: str) -> dict:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('DYLD_', 'HAO_', 'GIT_CONFIG_')) or key in {
            'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET', 'CPATH', 'C_INCLUDE_PATH',
            'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH', 'MAKEFLAGS', 'MFLAGS', 'CC', 'CXX',
            'CFLAGS', 'CPPFLAGS', 'CXXFLAGS', 'LDFLAGS', 'BASH_ENV', 'ENV',
            'TEST_SWITCHES', 'ZERO_AR_DATE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
            'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
        }:
            env.pop(key, None)
    env.update(SDKROOT=sdk, ZERO_AR_DATE='1', LC_ALL='C', GIT_TERMINAL_PROMPT='0',
               PATH=toolchain + ':/usr/bin:/bin:/usr/sbin:/sbin:/opt/local/bin')
    return env


def file_manifest(root: Path) -> dict:
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise Stop('Legatura simbolica neasteptata in artefact: ' + str(p))
        if p.is_file() and p.name != 'build.json':
            result[p.relative_to(root).as_posix()] = {
                'sha256': sha(p), 'bytes': p.stat().st_size, 'mode': p.stat().st_mode & 0o777,
            }
    return result


class Work:
    def __init__(self, repo: Path):
        self.repo = repo
        self.local = repo / 'local/mbp91'
        self.run_id = stamp()
        self.run_dir = self.local / ('step7-runs/' + self.run_id)
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.log_path = self.run_dir / 'build.log'
        self.log = self.log_path.open('w', encoding='utf-8')
        self.target_build = TARGET_BUILD
        self.host_build = HOST_BUILD
        self.env = os.environ.copy()
        self.env.update(GIT_TERMINAL_PROMPT='0')
        self.result = {
            'schema': 'hao-mbp91-step7-v1', 'run_id': self.run_id,
            'model': 'MacBookPro9,1', 'patcher_commit': PATCHER_COMMIT,
            'runtime_commit': RUNTIME_COMMIT, 'runtime_tree': RUNTIME_TREE,
            'golden_build': GOLDEN, 'scope': 'LOCAL source-build of runtime core + unstamped HaoExec',
            'target_runtime_built': False, 'unstamped_kext_built': False,
            'host_tests_passed': False, 'step_complete': False,
            'runtime_payload_ready': False, 'published_payload_reproduced': False,
            'image_built': False, 'boot_validated': False,
            'remaining_payload_work': list(MISSING_PAYLOAD),
            'commands': [], 'tests': {}, 'errors': [], 'warnings': [],
        }
        self.source = repo / ('store/sources/hao-runtime-' + RUNTIME_COMMIT[:12])
        self.save()

    def save(self) -> None:
        write_json(self.run_dir / 'result.json', self.result)
        write_json(self.local / 'step7-result.json', self.result)

    def run(self, argv, *, cwd=None, timeout=600, check=True, quiet=False, env=None) -> tuple[int, str]:
        argv = list(map(str, argv)); cwd = Path(cwd or self.repo)
        line = shlex.join(argv)
        self.log.write('\n$ ' + line + '\n'); self.log.flush()
        if not quiet:
            print('  > ' + line, flush=True)
        start = time.monotonic()
        proc = subprocess.Popen(argv, cwd=cwd, env=env or self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace', bufsize=1,
                                start_new_session=True)
        q = queue.Queue()
        def pump():
            try:
                for text in proc.stdout:
                    q.put(text)
            finally:
                q.put(None)
        threading.Thread(target=pump, daemon=True).start()
        parts, done, expired, ping = [], False, False, start
        try:
            while not done:
                now = time.monotonic()
                if now - start > timeout:
                    expired = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                    break
                try:
                    text = q.get(timeout=0.2)
                except queue.Empty:
                    if not quiet and now - ping >= 30:
                        print('    Proces activ; log: ' + str(self.log_path.relative_to(self.repo)), flush=True)
                        ping = now
                    continue
                if text is None:
                    done = True
                else:
                    parts.append(text); self.log.write(text); self.log.flush()
                    if not quiet:
                        print(text, end='', flush=True)
            proc.wait(timeout=10)
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            raise
        rc = 124 if expired else proc.returncode
        output = ''.join(parts)
        self.result['commands'].append({'argv': argv, 'cwd': str(cwd), 'returncode': rc,
                                       'elapsed_s': round(time.monotonic() - start, 1), 'timed_out': expired})
        self.save()
        if check and rc:
            tail = '\n'.join(output.splitlines()[-12:])
            raise Stop('Comanda a esuat (cod %d): %s\n%s' % (rc, line, tail))
        return rc, output

    def git(self, source: Path, *args: str) -> str:
        return self.run(['/usr/bin/git', '-C', source, *args], quiet=True)[1].strip()

    def attempt(self, name: str, fn) -> bool:
        try:
            fn()
            return True
        except (Stop, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            self.result['errors'].append({'stage': name, 'error': str(e)})
            self.log.write('\n' + traceback.format_exc()); self.log.flush()
            print('\n  OPRIT in %s: %s\n' % (name, e), flush=True)
            self.save()
            return False

    def report(self) -> Path:
        self.result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save(); self.log.flush()
        dest = Path.home() / 'Desktop/HAO-mbp91-step7.zip'
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + '.tmp')
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('local/mbp91/step7-result.json', json.dumps(self.result, indent=2) + '\n')
            # Only logs and metadata. No compiled binaries, source trees or Apple files.
            z.write(self.log_path, 'local/mbp91/step7-build.log')
            for p in self.run_dir.glob('*.json'):
                if p.name != 'result.json':
                    z.write(p, 'local/mbp91/' + p.name)
            for rel in ('local/mbp91/step6-result.json', 'local/mbp91/HAO-mbp91-step7.py'):
                p = safe_path(self.repo, rel)
                if p.is_file():
                    z.write(p, rel)
            artifact = self.result.get('core_artifact')
            if artifact:
                p = safe_path(self.repo, artifact) / 'build.json'
                if p.is_file():
                    z.write(p, artifact + '/build.json')
        os.replace(partial, dest)
        return dest


def preflight(w: Work) -> tuple[str, int]:
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise Stop('Acest pas se executa pe iMac-ul Intel in macOS.')
    if os.geteuid() == 0:
        raise Stop('Ruleaza fara sudo; compilarea nu necesita root.')
    if w.git(w.repo, 'rev-parse', 'HEAD') != PATCHER_COMMIT:
        raise Stop('Copia Hao nu este la commitul de referinta 6bd75aab. Nu fac reset automat.')
    record = read_json(w.local / 'step6-result.json')
    if not (record.get('step_complete') and record.get('donors_ready') and record.get('kernel_tools_ready')):
        raise Stop('Raportul pasului 6 nu confirma finalizarea.')
    w.result['step6_record_sha256'] = sha(w.local / 'step6-result.json')
    if shutil.disk_usage(w.repo).free < 4 * 1024**3:
        raise Stop('Rezerva operationala pentru aceasta compilare: 4 GiB liberi.')
    _, sdk = w.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], quiet=True)
    _, sdk_ver = w.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'], quiet=True)
    _, clang = w.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--find', 'clang'], quiet=True)
    sdk, clang, sdk_ver = sdk.strip(), clang.strip(), sdk_ver.strip()
    if not Path(sdk).is_dir() or not Path(clang).is_file():
        raise Stop('SDK-ul sau compilatorul selectat nu exista.')
    _, compiler = w.run([clang, '--version'], quiet=True)
    _, xcode = w.run(['/usr/bin/xcodebuild', '-version'], quiet=True)
    w.result['toolchain'] = {'sdk_path': sdk, 'sdk_version': sdk_ver, 'clang': clang,
                             'compiler': compiler.strip(), 'xcode': xcode.strip(),
                             'requested_runtime_minimum': '27.0', 'requested_kext_minimum': '13.0',
                             'host_test_minimum': '26.0'}
    build_key = hashlib.sha256(json.dumps(w.result['toolchain'], sort_keys=True).encode()).hexdigest()[:16]
    w.target_build = 'build/mbp91-step7-' + build_key + '/macos-27.0'
    w.host_build = 'build/mbp91-step7-' + build_key + '/macos-26.0'
    w.result['build_directories'] = {'target': w.target_build, 'host_tests': w.host_build}
    w.env = build_environment(sdk, str(Path(clang).parent))
    if int(sdk_ver.split('.')[0]) < 27:
        warning = ('SDK %s este mai vechi decat deployment target 27.0. Incerc compilarea fara schimbarea '
                   'sursei sau a tintei; rezultatul nu reproduce byte-for-byte release-ul Xcode 27.2.' % sdk_ver)
        print('  NOTA: ' + warning, flush=True)
        w.result['warnings'].append(warning)
    jobs = min(8, max(1, os.cpu_count() or 1))
    w.result['parallel_jobs'] = jobs; w.save()
    return clang, jobs


def prepare_source(w: Work) -> None:
    source = w.source
    if source.exists():
        if source.is_symlink() or not (source / '.git').is_dir():
            raise Stop('Directorul sursei exista, dar nu este checkout-ul asteptat: ' + str(source))
        print('  Reutilizez sursa locala fixata.', flush=True)
    else:
        source.parent.mkdir(parents=True, exist_ok=True)
        temp = source.with_name(source.name + '.partial-' + w.run_id)
        temp.mkdir(mode=0o755)
        w.run(['/usr/bin/git', 'init', temp], quiet=True)
        w.git(temp, 'remote', 'add', 'origin', RUNTIME_URL)
        w.run(['/usr/bin/git', '-C', temp, '-c', 'http.lowSpeedLimit=1024',
               '-c', 'http.lowSpeedTime=120', 'fetch', '--depth=1', '--no-tags', 'origin', RUNTIME_COMMIT], timeout=900)
        w.git(temp, 'checkout', '--detach', 'FETCH_HEAD')
        verify_source(w, temp)
        os.replace(temp, source)
    verify_source(w, source)
    generated = generated_inputs(source)
    write_json(w.run_dir / 'step7-generated-inputs.json', generated)
    w.result['compile_time_tables_verified'] = len(generated['files'])
    w.result['source_path'] = source.relative_to(w.repo).as_posix()
    w.save()


def verify_source(w: Work, source: Path) -> None:
    if w.git(source, 'rev-parse', 'HEAD') != RUNTIME_COMMIT:
        raise Stop('Sursa runtime are alt commit; nu schimb automat o copie existenta.')
    if w.git(source, 'rev-parse', 'HEAD^{tree}') != RUNTIME_TREE:
        raise Stop('Arborele Git al sursei runtime difera.')
    if w.git(source, 'status', '--porcelain', '--untracked-files=no'):
        raise Stop('Sursa runtime are modificari urmarite de Git.')
    untracked = w.git(source, 'ls-files', '--others', '--exclude-standard').splitlines()
    if any(not x.startswith('build/') for x in untracked):
        raise Stop('Fisiere suplimentare in sursa runtime: ' + ', '.join(untracked[:8]))


def compile_runtime(w: Work, clang: str, jobs: int) -> None:
    base = safe_path(w.source, w.target_build)
    w.run(make_command(clang, w.target_build, '27.0', jobs, ['all']), cwd=w.source, timeout=1800)
    verified = {name: macho_info(base / name, kind, '27.0') for name, kind in CORE_FILES.items()}
    for name in STATIC_FILES:
        p = base / name
        with p.open('rb') as f:
            if f.read(8) != b'!<arch>\n':
                raise Stop('Arhiva statica invalida: ' + name)
        _, archs = w.run(['/usr/bin/lipo', '-archs', p], quiet=True)
        if archs.strip().split() != ['x86_64']:
            raise Stop('Arhiva statica nu este exclusiv x86_64: ' + name)
        verified[name] = {'architecture': archs.strip(), 'sha256': sha(p), 'bytes': p.stat().st_size}
    for name in SIGNED_FILES:
        w.run(['/usr/bin/codesign', '--verify', '--verbose=2', base / name], quiet=True)
        verified[name]['signature_verified'] = True
    # hao-stub is intentionally unsigned upstream; it is signed per embedded program.
    verified['hao-stub']['signature_note'] = 'Intentionally unsigned upstream; signed during embedding.'
    w.result['target_runtime_files'] = verified
    w.result['target_runtime_built'] = True; w.save()


def compile_kext(w: Work) -> None:
    safe_path(w.source, w.target_build)
    w.run(['/bin/bash', 'kext/build.sh', w.target_build, '13.0'], cwd=w.source, timeout=600)
    bundle = w.source / w.target_build / 'HaoExec.kext'
    binary = bundle / 'Contents/MacOS/HaoExec'
    info = macho_info(binary, 11, '13.0')
    import plistlib
    pl = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    if pl.get('CFBundleExecutable') != 'HaoExec':
        raise Stop('HaoExec Info.plist nu numeste executabilul asteptat')
    w.run(['/usr/bin/codesign', '--verify', '--verbose=2', bundle], quiet=True)
    w.result['kext'] = {'binary': info, 'bundle_identifier': pl.get('CFBundleIdentifier'),
                        'signature_verified': True, 'kernel_identity_stamped': False,
                        'note': 'Not loaded. Final BootKC identity is not available yet.'}
    w.result['unstamped_kext_built'] = True; w.save()


def run_host_tests(w: Work, clang: str, jobs: int) -> None:
    safe_path(w.source, w.host_build)
    targets = [w.host_build + '/' + name for name, _ in HOST_TESTS]
    w.run(make_command(clang, w.host_build, '26.0', jobs, targets), cwd=w.source, timeout=1800)
    for name, limit in HOST_TESTS:
        binary = w.source / w.host_build / name
        try:
            info = macho_info(binary, 2, '26.0')
            print('  Test Intel/Tahoe: ' + name, flush=True)
            rc, out = w.run([binary], cwd=w.source, timeout=limit, check=False)
            passed = rc == 0
            w.result['tests'][name] = {'passed': passed, 'returncode': rc, 'binary': info,
                                       'output_tail': '\n'.join(out.splitlines()[-12:])}
        except (Stop, OSError, ValueError) as e:
            w.result['tests'][name] = {'passed': False, 'error': str(e)}
        w.save()
    failed = [n for n, _ in HOST_TESTS if not w.result['tests'].get(n, {}).get('passed')]
    if failed:
        raise Stop('Teste care nu au trecut: ' + ', '.join(failed))
    w.result['host_tests_passed'] = True; w.save()


def publish_core(w: Work) -> None:
    if not all(w.result[k] for k in ('target_runtime_built', 'unstamped_kext_built', 'host_tests_passed')):
        return
    verify_source(w, w.source)
    generated_inputs(w.source)
    artifacts = w.repo / 'store/artifacts'; artifacts.mkdir(parents=True, exist_ok=True)
    dest = artifacts / ('mbp91-hao-runtime-core-' + RUNTIME_COMMIT[:12] + '-local-' + w.run_id)
    partial = dest.with_name(dest.name + '.partial')
    partial.mkdir(mode=0o755)
    base = w.source / w.target_build
    for name in tuple(CORE_FILES) + STATIC_FILES:
        p = partial / 'runtime-build' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / name, p)
    shutil.copytree(base / 'HaoExec.kext', partial / 'HaoExec.kext')
    for name in ('LICENSE', 'NOTICE.md'):
        if (w.source / name).is_file():
            shutil.copy2(w.source / name, partial / name)
    (partial / 'SCOPE.txt').write_text(
        'LOCAL EXPERIMENTAL RUNTIME CORE. NOT AN INSTALLABLE HAO PAYLOAD.\n'
        'Source: lythka/hao-runtime at ' + RUNTIME_COMMIT + '\n'
        'Runtime: x86_64, minimum macOS 27.0; HaoExec: x86_64, minimum macOS 13.0, unstamped.\n'
        'Host unit tests: separate minimum macOS 26.0 build; not a Golden Gate boot test.\n'
        'The published archive hash is NOT reproduced or replaced. No hao_runtime input row is changed.\n'
        'Missing for a complete payload:\n- ' + '\n- '.join(MISSING_PAYLOAD) + '\n', encoding='utf-8')
    files = file_manifest(partial)
    record = {'schema': 1, 'operation': 'local-hao-runtime-core-build', 'runtime_commit': RUNTIME_COMMIT,
              'source_tree': RUNTIME_TREE, 'source_tracked_clean': True,
              'patcher_commit': PATCHER_COMMIT, 'toolchain': w.result['toolchain'],
              'target_runtime_files': w.result['target_runtime_files'], 'kext': w.result['kext'],
              'host_tests_passed': True, 'host_test_names': [n for n, _ in HOST_TESTS],
              'runtime_payload_ready': False, 'published_payload_reproduced': False,
              'remaining_payload_work': list(MISSING_PAYLOAD), 'files': files}
    write_json(partial / 'build.json', record)
    for rel, value in files.items():
        if sha(safe_path(partial, rel)) != value['sha256']:
            raise Stop('Copie de artefact diferita: ' + rel)
    os.replace(partial, dest)
    w.result['core_artifact'] = dest.relative_to(w.repo).as_posix()
    w.result['core_artifact_record_sha256'] = sha(dest / 'build.json')
    w.result['step_complete'] = True; w.save()


def execute(w: Work) -> int:
    print('1/4 Pregatesc sursa hao-runtime fixata. Nu redescarc fisierele Apple.', flush=True)
    clang, jobs = preflight(w)
    prepare_source(w)
    print('2/4 Compilez nucleul runtime pentru macOS 27 si HaoExec.kext.', flush=True)
    w.attempt('runtime-core', lambda: compile_runtime(w, clang, jobs))
    w.attempt('HaoExec.kext', lambda: compile_kext(w))
    print('3/4 Rulez opt teste upstream x86_64, intr-un build separat pentru Tahoe.', flush=True)
    w.attempt('host-unit-tests', lambda: run_host_tests(w, clang, jobs))
    print('4/4 Verific si salvez artefactul local si raportul.', flush=True)
    w.attempt('publish-core', lambda: publish_core(w))
    return 0 if w.result['step_complete'] else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path.cwd())
    a = p.parse_args()
    repo = a.repo.expanduser().resolve()
    w, code = None, 1
    try:
        if not (repo / '.git').is_dir() or not (repo / 'local/mbp91/step6-result.json').is_file():
            raise Stop('Ruleaza din ~/Desktop/hao-patcher-mbp91, copia cu pasul 6 incheiat.')
        with (repo / 'local/mbp91/.step7.lock').open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop('Pasul 7 ruleaza deja in aceasta copie.') from None
            w = Work(repo)
            try:
                saved_script = w.local / 'HAO-mbp91-step7.py'
                if Path(__file__).resolve() != saved_script.resolve():
                    shutil.copy2(__file__, saved_script)
                code = execute(w)
            except (Exception, KeyboardInterrupt) as e:
                w.result['errors'].append({'stage': 'execution', 'error': type(e).__name__ + ': ' + str(e)})
                w.result['step_complete'] = False
                w.log.write('\n' + traceback.format_exc()); w.log.flush()
                print('\nOPRIT: ' + str(e), flush=True)
            finally:
                report = w.report()
                print('\nRuntime x86_64 compilat pentru macOS 27: ' + ('DA' if w.result['target_runtime_built'] else 'NU'))
                print('HaoExec.kext compilat, nestampilat: ' + ('DA' if w.result['unstamped_kext_built'] else 'NU'))
                count = sum(bool(v.get('passed')) for v in w.result['tests'].values())
                print('Teste Intel/Tahoe trecute: %d/%d' % (count, len(HOST_TESTS)))
                if w.result.get('core_artifact'):
                    print('Artefact local: ' + str(repo / w.result['core_artifact']))
                print('Payload Hao complet pentru imagine: NU (interfete, thunks si provider de integrat).')
                print('Imagine bootabila / boot validat: NU.')
                print('Arhiva MICA de trimis: ' + str(report))
    except (Stop, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print('OPRIT: ' + str(e), file=sys.stderr)
        code = 1
        if w is None:
            try:
                dest = Path.home() / 'Desktop/HAO-mbp91-step7.zip'
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('step7-early-error.txt', str(e) + '\n')
                print('Raport eroare: ' + str(dest), file=sys.stderr)
            except OSError:
                pass
    finally:
        if w is not None:
            w.log.close()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
