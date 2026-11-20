#!/usr/bin/env python3
"""HAO / MacBookPro9,1, step 9: build the three HD4000 Metal inputs.

Run on the Intel build Mac, in ~/Desktop/hao-patcher-mbp91:
    python3.14 -I ~/Downloads/HAO-mbp91-step9.py

Uses the pinned upstream producers and the already prepared inputs. No downloads,
no sudo, no disk installation and no runtime recompilation. Official input rows
are never rewritten. Non-identical results remain separately labelled LOCAL
CANDIDATES, not upstream-equivalent files or proof of working graphics.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
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
import subprocess
import sys
import time
import traceback
import zipfile

PIN = '6bd75aab112d1078acd8e75180eb510672461365'
BUILD = '26B131'
DONOR = '25G342'
REVISION = 'step9-metal-v1'
HEX = re.compile(r'^[0-9a-f]{64}$')
ROW_NAMES = ('hello_metallib_golden_gate', 'metallib_repairs_golden_gate',
             'metal_quad_runtime_golden_gate')
PROFILES = {
    ROW_NAMES[0]: 'cache/metallib/profiles/hello-golden-gate.txt',
    ROW_NAMES[1]: 'cache/metallib/profiles/metallib-repairs-golden-gate.txt',
}
SPLIT_REL = 'System/Library/Extensions/AppleIntelGraphicsShared.bundle/Contents/Resources/runtime.igil64.split'
ICBE_REL = 'System/Library/Extensions/AppleIntelHD4000GraphicsGLDriver.bundle/Contents/MacOS/iCBE.dylib'
HW_SPLIT = 'payload/11.7.10/' + SPLIT_REL
HW_ICBE = 'payload/11.7.10/' + ICBE_REL
HW_LLVM = 'payload/13.2.1-25/System/Library/PrivateFrameworks/GPUCompiler.framework/Versions/3802/Libraries/libLLVM.dylib'


class Stop(RuntimeError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise Stop(f'Obiect JSON asteptat: {path}')
    return data


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def relative(value: str) -> Path:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or '\x00' in value or p == PurePosixPath('.'):
        raise Stop(f'Cale relativa invalida: {value!r}')
    return Path(*p.parts)


def inside(root: Path, value: str | Path) -> Path:
    p = root / relative(str(value))
    if not p.resolve().is_relative_to(root.resolve()):
        raise Stop(f'Calea iese din directorul permis: {p}')
    return p


def regular(root: Path, rel: str) -> Path:
    p = inside(root, rel)
    if not p.is_file():
        raise Stop(f'Fisier necesar lipsa: {p}')
    return p


def parse_profile(path: Path) -> list[tuple[str, str]]:
    result = []
    for no, line in enumerate(path.read_text().splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        fields = s.split(None, 1)
        if len(fields) != 2 or fields[0] not in ('golden-gate', 'rewrite'):
            raise Stop(f'Reteta neasteptata in {path.name}:{no}: {s}')
        rel = relative(fields[1]).as_posix()
        if not rel.endswith('.metallib') or rel in {r for _, r in result}:
            raise Stop(f'Intrare metallib invalida sau duplicata: {rel}')
        result.append((fields[0], rel))
    if not result:
        raise Stop(f'Profil gol: {path}')
    return result


def sums(path: Path) -> dict[str, str]:
    result = {}
    for no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split(None, 1)
        if len(fields) != 2 or not HEX.fullmatch(fields[0]):
            raise Stop(f'Checksum invalid: {path.name}:{no}')
        rel = relative(fields[1]).as_posix()
        if rel in result:
            raise Stop(f'Checksum duplicat: {rel}')
        result[rel] = fields[0]
    if not result:
        raise Stop(f'Lista SHA256 goala: {path}')
    return result


def verify_sums(root: Path, name: str = 'SHA256SUMS') -> dict[str, str]:
    entries = sums(root / name)
    for rel, expected in entries.items():
        if sha(regular(root, rel)) != expected:
            raise Stop(f'SHA256 diferit pentru {root / rel}')
    return entries


def compare_mtlb(original: bytes, output: bytes, checker) -> int:
    """Check original exports, function metadata and trailing resources, not pixels."""
    a, b = checker(original), checker(output)
    if [f['name'] for f in a['fns']] != [f['name'] for f in b['fns']]:
        raise Stop('Lista sau ordinea functiilor exportate s-a schimbat')
    for fa, fb in zip(a['fns'], b['fns']):
        if set(fa['tags']) != set(fb['tags']):
            raise Stop('Tagurile unei functii metallib s-au schimbat')
        for tag in set(fa['tags']) - {b'OFFT', b'MDSZ', b'HASH'}:
            oa, na = fa['tags'][tag]
            ob, nb = fb['tags'][tag]
            if original[oa:oa + na] != output[ob:ob + nb]:
                raise Stop('Metadate de functie schimbate: ' + fa['name'])
    for offset_index, size_index in ((3, 4), (5, 6)):
        oa, na = a['hdr'][offset_index], a['hdr'][size_index]
        ob, nb = b['hdr'][offset_index], b['hdr'][size_index]
        if original[oa:oa + na] != output[ob:ob + nb]:
            raise Stop('Metadatele publice/private metallib difera')
    ta = {x['tag']: original[x['offset']:x['offset'] + x['size']] for x in a['trailers']}
    tb = {x['tag']: output[x['offset']:x['offset'] + x['size']] for x in b['trailers']}
    if ta != tb:
        raise Stop('Resursele finale metallib difera')
    if (b'UUID' in a['global_tags']) != (b'UUID' in b['global_tags']):
        raise Stop('Tag UUID metallib diferit')
    if b'UUID' in a['global_tags']:
        oa, na = a['global_tags'][b'UUID']; ob, nb = b['global_tags'][b'UUID']
        if original[oa:oa + na] != output[ob:ob + nb]:
            raise Stop('UUID metallib schimbat')
    return len(a['fns'])


def preserved_split(original: dict, rebuilt: dict, recorded_added: list[str]) -> dict:
    if not original or any(rebuilt.get(k) != v for k, v in original.items()):
        raise Stop('Runtime-ul shader a pierdut sau modificat un helper original')
    added = sorted(set(rebuilt) - set(original))
    if not added or added != sorted(recorded_added):
        raise Stop('Lista helperelor noi difera de raportul constructorului')
    return {'original_helpers_preserved': len(original), 'added_helpers': added}


def metadata_fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def terminate_group(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait()


class Job:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self.local = self.repo / 'local/mbp91'
        self.local.mkdir(parents=True, exist_ok=True)
        self.rid = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work = self.repo / ('store/tmp/mbp91-step9-' + self.rid)
        self.work.mkdir(parents=True, exist_ok=False)
        self.state_dir = self.local / 'step9-state'
        self.state_dir.mkdir(exist_ok=True)
        self.lock_dir = self.local / 'step9-inputs'
        self.lock_dir.mkdir(exist_ok=True)
        self.logpath = self.local / 'step9-build.log'
        for name in ('step9-result.json', 'step9-build.log', 'step9-dependencies.json'):
            p = self.local / name
            if p.exists():
                backup = self.local / 'backups' / ('step9-' + self.rid) / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, backup)
        self.log = self.logpath.open('w', buffering=1)
        self.report = {
            'schema': 'hao-mbp91-step9-metal-v1', 'revision': REVISION, 'run_id': self.rid,
            'patcher_commit': PIN, 'model': 'MacBookPro9,1', 'golden_build': BUILD,
            'step_complete': False, 'official_input_rows_modified': False,
            'downloaded': False, 'runtime_rebuilt': False, 'runtime_payload_complete': False,
            'graphics_boot_validated': False, 'image_built': False, 'boot_validated': False,
            'artifacts': {}, 'errors': [], 'commands': [],
        }
        self.env = dict(os.environ)
        self.extra_reports: list[Path] = []
        self.lock = None

    def run(self, argv: list, *, timeout: int = 3600, live: bool = False) -> str:
        argv = [str(x) for x in argv]
        self.log.write('$ ' + shlex.join(argv) + '\n')
        start = time.monotonic()
        rec = {'argv': argv, 'returncode': None}
        self.report['commands'].append(rec)
        capture = self.work / ('command-%03d.txt' % len(self.report['commands']))
        try:
            with capture.open('wb') as out:
                p = subprocess.Popen(argv, cwd=self.repo, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
                until_notice = time.monotonic() + 45
                copied = 0
                try:
                    while p.poll() is None:
                        with capture.open('rb') as partial_log:
                            partial_log.seek(copied)
                            delta = partial_log.read()
                            copied += len(delta)
                        if delta:
                            self.log.write(delta.decode(errors='replace'))
                        elapsed = time.monotonic() - start
                        if elapsed > timeout:
                            terminate_group(p)
                            raise Stop(f'Limita de executie depasita: {Path(argv[0]).name}; vezi step9-build.log')
                        if live and time.monotonic() > until_notice:
                            print('    Constructorul lucreaza; log: local/mbp91/step9-build.log', flush=True)
                            # Copy only new output below, without interrupting the process.
                            until_notice += 45
                        time.sleep(0.25)
                except BaseException:
                    terminate_group(p)
                    raise
                rec['returncode'] = p.returncode
        finally:
            rec['elapsed_s'] = round(time.monotonic() - start, 2)
            if capture.exists():
                text = capture.read_text(errors='replace')
                raw = capture.read_bytes()
                self.log.write(raw[locals().get('copied', 0):].decode(errors='replace'))
                if text and not text.endswith('\n'):
                    self.log.write('\n')
        if rec['returncode'] != 0:
            detail = '\n'.join(text.splitlines()[-18:])
            if detail:
                print(detail, flush=True)
            raise Stop(f'Comanda a esuat ({rec["returncode"]}): {Path(argv[0]).name}; vezi step9-build.log')
        return text.strip()

    def official_row(self, name: str) -> tuple[Path, str, Path]:
        for folder in (self.repo / f'pipeline/inputs/golden/{BUILD}',
                       self.repo / f'pipeline/inputs/{DONOR}', self.repo / 'pipeline/inputs/common'):
            rowfile = folder / name
            if rowfile.is_file():
                entries = self.lock['rows'](str(folder))
                wanted, p = entries[name]
                return folder, wanted, Path(p)
        raise Stop('Intrare de build lipsa: ' + name)

    def checked_row(self, name: str) -> Path:
        folder, _, _ = self.official_row(name)
        try:
            return Path(self.lock['path'](str(folder), name))
        except SystemExit as e:
            raise Stop(f'Verificare intrare {name}: {e}') from e

    def setup(self) -> tuple[Path, Path, dict]:
        if sys.platform != 'darwin' or os.geteuid() == 0:
            raise Stop('Ruleaza pe macOS, ca utilizator normal, fara sudo.')
        if self.run(['/usr/bin/git', 'rev-parse', 'HEAD']) != PIN:
            raise Stop('Copia Hao nu este la commitul 6bd75aa; nu schimb automat versiunea.')
        changed = self.run(['/usr/bin/git', 'status', '--porcelain', '--', 'cache/metallib', 'pipeline/lock.py'])
        if changed:
            raise Stop('Sursele Metal sau lock.py au modificari locale: ' + changed)
        previous = read_json(self.local / 'step8-result.json')
        if not previous.get('bootstrap_payload_ready') or previous.get('errors') or previous.get('golden_build') != BUILD:
            raise Stop('Raportul local nu confirma succesul pasului 8 pentru 26B131.')
        payload = inside(self.repo, previous['bootstrap_artifact'])
        pm = payload / 'payload-manifest.json'
        if sha(pm) != previous['payload_manifest_sha256']:
            raise Stop('Manifestul payload-ului s-a schimbat dupa pasul 8.')
        manifest = read_json(pm)
        if sha(payload / 'build.json') != manifest['files']['build.json']:
            raise Stop('build.json nu mai corespunde manifestului pasului 8.')
        self.report['bootstrap_input'] = {
            'path': previous['bootstrap_artifact'], 'manifest_sha256': sha(pm),
            'embedded_programs': previous.get('validation', {}).get('embedded_programs'),
            'reused': True,
        }
        root = inside(self.repo, previous['root_view'])
        ver = plistlib.loads(regular(root, 'System/Library/CoreServices/SystemVersion.plist').read_bytes())
        if ver.get('ProductBuildVersion') != BUILD:
            raise Stop('Copia System nu este 26B131.')
        self.report['root_view'] = str(root.relative_to(self.repo))
        self.lock = runpy.run_path(str(self.repo / 'pipeline/lock.py'))
        assembly = read_json(self.repo / 'pipeline/assemblies/mbp91-26B131.json')
        if assembly.get('target') != 'mbp91' or assembly.get('inputs', {}).get('hardware') != 'oclp_hardware_mbp91':
            raise Stop('Reteta nu selecteaza hardware-ul mbp91.')
        hardware = self.checked_row('oclp_hardware_mbp91')
        _, pin, _ = self.official_row('oclp_hardware_mbp91')
        self.report['hardware'] = {'path': str(hardware.relative_to(self.repo)), 'sha256': pin}
        dev = self.run(['/usr/bin/xcode-select', '-p'])
        sdk = self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'])
        sdkver = self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'])
        tools = {}
        for name in ('clang', 'metal', 'metallib', 'metal-as', 'metal-objdump'):
            path = Path(self.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--find', name]))
            if not path.is_file() or not os.access(path, os.X_OK):
                raise Stop('Unealta lipsa: ' + name)
            tools[name] = {'path': str(path), 'sha256': sha(path)}
        bindir = self.work / 'bin'; bindir.mkdir()
        for name in ('python3', 'python3.14'):
            p = bindir / name
            p.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' -I -B "$@"\n')
            p.chmod(0o755)
        clang = bindir / 'clang'
        clang.write_text('#!/bin/sh\nexec ' + shlex.quote(tools['clang']['path']) +
                         ' -isysroot ' + shlex.quote(sdk) + ' "$@"\n')
        clang.chmod(0o755)
        for k in tuple(self.env):
            if k.startswith('DYLD_') or k in ('PYTHONPATH', 'PYTHONHOME', 'SDKROOT', 'MACOSX_DEPLOYMENT_TARGET',
                                             'HAO_METAL_LLVM', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                                             'LIBRARY_PATH', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS'):
                self.env.pop(k, None)
        self.env.update(DEVELOPER_DIR=dev, SDKROOT=sdk, PYTHONDONTWRITEBYTECODE='1',
                        PATH=str(bindir) + ':/usr/bin:/bin:/usr/sbin:/sbin:/opt/local/bin')
        self.report['toolchain'] = dict(developer=dev, sdk=sdk, sdk_version=sdkver, tools=tools)
        print(f'    SDK {sdkver}; Metal assembler si disassembler prezente. Folosesc copia System existenta.', flush=True)
        return root, hardware, assembly

    def validate_libraries(self, output: Path, root: Path, profile: list) -> dict:
        expected = {p for _, p in profile}
        hashes, sources = verify_sums(output), sums(output / 'SOURCES')
        if set(hashes) != expected or set(sources) != expected:
            raise Stop('Fisierele rezultate nu coincid exact cu profilul Metal.')
        record = read_json(output / 'build.json')
        if record.get('system_build') != BUILD:
            raise Stop('Pachetul Metal nu declara buildul 26B131.')
        checker = runpy.run_path(str(self.repo / 'cache/metallib/lib/mtlb.py'))['check']
        functions = {}
        for rel in sorted(expected):
            original = regular(root, rel)
            if sha(original) != sources[rel]:
                raise Stop('Biblioteca originala nu corespunde SOURCES: ' + rel)
            functions[rel] = compare_mtlb(original.read_bytes(), regular(output, rel).read_bytes(), checker)
        return {'library_count': len(expected), 'exported_function_count': sum(functions.values()),
                'exports_and_metadata_preserved': True, 'functions_per_library': functions,
                'output_hashes': hashes, 'source_hashes': sources, 'gpu_execution_tested': False}

    def validate_runtime(self, output: Path, hw: Path) -> dict:
        hashes = verify_sums(output)
        if set(hashes) != {SPLIT_REL, ICBE_REL}:
            raise Stop('Pachetul runtime shader nu contine exact split runtime + iCBE.')
        record = read_json(output / 'build.json')
        decode = runpy.run_path(str(self.repo / 'cache/metallib/shader-runtime-helpers/build.py'))['decode']
        checks = preserved_split(decode(regular(hw, HW_SPLIT).read_bytes()),
                                 decode(regular(output, SPLIT_REL).read_bytes()), record.get('added_symbols', []))
        if not record.get('compiler_repair'):
            raise Stop('Raportul nu confirma repararea emitatorului iCBE.')
        self.run(['/usr/bin/codesign', '--verify', '--verbose=2', regular(output, ICBE_REL)])
        return {**checks, 'icbe_signature_checked': True, 'output_hashes': hashes,
                'gpu_execution_tested': False}

    def build_row(self, row: str, root: Path, hw: Path) -> None:
        folder, expected_hash, _ = self.official_row(row)
        profile = parse_profile(self.repo / PROFILES[row]) if row in PROFILES else None
        if profile is not None:
            src = {p: sha(regular(root, p)) for _, p in profile}
            spec = {'profile_sha256': sha(self.repo / PROFILES[row]), 'sources': src}
        else:
            spec = {'sources': {p: sha(regular(hw, p)) for p in (HW_SPLIT, HW_LLVM, HW_ICBE)}}
        identity = metadata_fingerprint({'revision': REVISION, 'upstream': PIN, 'row': row,
                                         'toolchain': self.report['toolchain'], 'inputs': spec})
        saved = self.state_dir / (row + '.json')
        validate = lambda p: (self.validate_libraries(p, root, profile) if profile is not None
                              else self.validate_runtime(p, hw))
        reused = False
        if saved.is_file():
            state = read_json(saved)
            candidate = inside(self.repo, state['path'])
            if state.get('input_fingerprint') == identity and candidate.is_dir():
                print('    Reutilizez pachetul existent: ' + row, flush=True)
                checks = validate(candidate)
                actual = self.lock['row_hash'](str(folder), row, str(candidate))
                if actual != state['content_sha256']:
                    raise Stop('Pachet local modificat dupa verificare: ' + row)
                if sha(candidate / 'build.json') != state.get('build_record_sha256'):
                    raise Stop('Metadatele pachetului local s-au schimbat: ' + row)
                output = candidate
                reused = True
        if not reused:
            output = self.repo / ('store/artifacts/mbp91-' + row.replace('_', '-') + '-' + self.rid)
            partial = output.with_name(output.name + '.partial')
            args = [sys.executable, '-I', '-B', self.repo / 'cache/metallib/make']
            if profile is not None:
                args += [root, partial, '--work', self.work / ('work-' + row), '--paths', self.repo / PROFILES[row]]
            else:
                args += ['runtime-build', regular(hw, HW_SPLIT), partial,
                         '--llvm', regular(hw, HW_LLVM), '--compiler', regular(hw, HW_ICBE)]
            self.report['artifacts'][row] = {'status': 'building', 'partial': str(partial.relative_to(self.repo))}
            self.save()
            self.run(args, timeout=4 * 3600, live=True)
            checks = validate(partial)
            actual = self.lock['row_hash'](str(folder), row, str(partial))
            partial.rename(output)
        exact = actual == expected_hash
        state = {'path': str(output.relative_to(self.repo)), 'content_sha256': actual,
                 'input_fingerprint': identity, 'build_record_sha256': sha(output / 'build.json'),
                 'inputs': spec, 'official_expected_sha256': expected_hash, 'matches_upstream': exact,
                 'reused': reused, 'validation': checks,
                 'classification': 'upstream-byte-match' if exact else 'local-candidate-not-upstream-byte-match',
                 'gpu_execution_tested': False}
        write_json(saved, state)
        # A separate local row. Carry forward the upstream hashing exclusions and
        # payload scope, but NEVER replace the actual upstream checksum file.
        comments = [l for l in (folder / row).read_text().splitlines()
                    if l.lstrip().startswith('# hash:') or l.lstrip().startswith('# check:')]
        body = ['# Local Metal candidate, independently hashed; NOT an upstream checksum substitution.',
                '# Official expected: ' + expected_hash, '# Upstream byte match: ' + str(exact).lower(),
                *comments, actual + ' ' + state['path']]
        (self.lock_dir / row).write_text('\n'.join(body) + '\n')
        self.report['artifacts'][row] = dict(status='prepared', **state)
        for filename in ('build.json', 'SHA256SUMS', 'SOURCES', 'build/commands.json'):
            p = output / filename
            if p.is_file():
                dst = self.local / 'step9-metadata' / row / filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dst)
                self.extra_reports.append(dst)
        print('    ' + row + ': construit si verificat; comparatie upstream: ' +
              ('IDENTIC' if exact else 'DIFERIT - candidat local separat'), flush=True)
        self.save()

    def dependencies(self, assembly: dict) -> None:
        """Inventory of the actual assembly's input rows, not a new hardware diagnostic."""
        cmd = [sys.executable, '-I', '-B', 'pipeline/patches.py', 'plan',
               'pipeline/profiles/mbp91-26B131.json', 'pipeline/targets/mbp91.json',
               BUILD + '/' + DONOR, '--skip-optional', 'caches']
        text = self.run(cmd, timeout=120)
        path = self.local / 'step9-plan.txt'; path.write_text(text + '\n'); self.extra_reports.append(path)
        required = set(assembly.get('inputs', {}).values())
        for line in text.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in ('oclp-hook', 'post', 'recovery'):
                required.update(fields[2:])
        out = {}
        for row in sorted(required):
            if row in self.report['artifacts'] and self.report['artifacts'][row].get('status') == 'prepared':
                a = self.report['artifacts'][row]
                out[row] = {'state': 'local_candidate_prepared', 'path': a['path'],
                            'matches_upstream': a['matches_upstream']}
            elif row == 'hao_runtime':
                out[row] = {'state': 'bootstrap_candidate_only', **self.report['bootstrap_input']}
            else:
                try:
                    folder, want, p = self.official_row(row)
                    out[row] = {'state': 'present_not_rehashed_here' if p.exists() else 'missing',
                                'row': str((folder / row).relative_to(self.repo)),
                                'path': str(p.relative_to(self.repo)) if p.is_relative_to(self.repo) else str(p),
                                'expected_sha256': want}
                except Stop as e:
                    out[row] = {'state': 'missing_row', 'error': str(e)}
        record = {'assembly': 'mbp91-26B131', 'note': 'Presence is not validation. Local candidates are NOT yet wired into the official rows.',
                  'rows': out, 'missing': [k for k, v in out.items() if v['state'].startswith('missing')]}
        write_json(self.local / 'step9-dependencies.json', record)
        self.report['remaining_missing_rows'] = record['missing']

    def save(self) -> None:
        write_json(self.local / 'step9-result.json', self.report)

    def finish(self) -> Path:
        self.report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save()
        self.log.close()
        archive = Path.home() / 'Desktop/HAO-mbp91-step9.zip'
        archive.parent.mkdir(exist_ok=True, parents=True)
        small = [self.local / n for n in ('step9-result.json', 'step9-build.log', 'step9-plan.txt', 'step9-dependencies.json')]
        small += list(self.state_dir.glob('*.json')) + list(self.lock_dir.glob('*')) + self.extra_reports
        for row in ROW_NAMES:
            for name in ('build.json', 'SHA256SUMS', 'SOURCES', 'build/commands.json'):
                small.append(self.local / 'step9-metadata' / row / name)
        limit = 3 << 20
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(set(small)):
                if not p.is_file() or p.is_symlink():
                    continue
                rel = str(p.relative_to(self.repo))
                if p.stat().st_size <= limit:
                    z.write(p, rel)
                else:
                    with p.open('rb') as f:
                        f.seek(-limit, 2); tail = f.read()
                    z.writestr(rel + '.tail.txt', b'[Only the last 3 MiB; complete file stays on the build Mac.]\n' + tail)
            z.write(Path(__file__).resolve(), 'HAO-mbp91-step9.py')
            z.writestr('READ-ME.txt', 'Metadata and logs only. No Apple libraries or disk images.\n')
        print('\nPachete Metal HD4000 pregatite: ' + ('DA' if self.report['step_complete'] else 'NU, vezi raportul'))
        print('Shader-ele originale/exporturile si hash-urile: verificate numai pentru pachetele marcate prepared.')
        print('Randurile oficiale Hao: neschimbate. Variantele locale sunt in local/mbp91/step9-inputs/.')
        print('Compatibilitate completa / imagine bootabila / boot validat: NU.')
        print('Arhiva MICA de trimis: ' + str(archive))
        return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    if not (repo / 'pipeline/lock.py').is_file() or not (repo / 'local/mbp91/step8-result.json').is_file():
        print('OPRIT: ruleaza din copia iMac Desktop/hao-patcher-mbp91 cu pasul 8 finalizat.', file=sys.stderr)
        return 1
    os.umask(0o022)
    job = Job(repo)
    try:
        print('1/4 Reutilizez payload-ul si pregatesc constructorii Metal existenti.', flush=True)
        root, hw, assembly = job.setup()
        # Validate all small prerequisites before beginning the expensive producers.
        for row, rel in PROFILES.items():
            for _, p in parse_profile(repo / rel):
                regular(root, p)
        for p in (HW_SPLIT, HW_LLVM, HW_ICBE):
            regular(hw, p)
        for row in ROW_NAMES:
            job.official_row(row)
        print('2/4 Construiesc biblioteca Hello si bibliotecile grafice Golden Gate.', flush=True)
        for row in ROW_NAMES[:2]:
            try:
                job.build_row(row, root, hw)
            except (Stop, OSError, ValueError, KeyError) as e:
                job.report['errors'].append({'row': row, 'error': str(e)})
                job.report['artifacts'].setdefault(row, {})['status'] = 'failed'
                job.log.write(traceback.format_exc())
                print('    OPRIT pentru ' + row + ': ' + str(e), flush=True)
                # The two library producers are independent: retain the exact error
                # and still attempt the other recipe and the Intel runtime.
        print('3/4 Construiesc runtime-ul shader Intel extins si corectia iCBE.', flush=True)
        try:
            job.build_row(ROW_NAMES[2], root, hw)
        except (Stop, OSError, ValueError, KeyError) as e:
            job.report['errors'].append({'row': ROW_NAMES[2], 'error': str(e)})
            job.report['artifacts'].setdefault(ROW_NAMES[2], {})['status'] = 'failed'
            job.log.write(traceback.format_exc())
            print('    OPRIT pentru runtime-ul shader: ' + str(e), flush=True)
        print('4/4 Salvez pachetele locale si lista exacta a intrarilor ramase pentru asamblare.', flush=True)
        try:
            job.dependencies(assembly)
        except (Stop, OSError, ValueError, KeyError) as e:
            job.report['errors'].append({'stage': 'dependency_plan', 'error': str(e)})
        job.report['step_complete'] = (not job.report['errors'] and all(
            job.report['artifacts'].get(r, {}).get('status') == 'prepared' for r in ROW_NAMES))
    except (Exception, KeyboardInterrupt) as e:
        job.report['errors'].append({'stage': 'setup_or_interrupted', 'error': str(e) or type(e).__name__})
        job.log.write(traceback.format_exc())
        print('OPRIT: ' + (str(e) or type(e).__name__), flush=True)
    finally:
        job.finish()
    return 0 if job.report['step_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
