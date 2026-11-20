#!/usr/bin/env python3
"""HAO / MacBookPro9,1 — step 6: prepare Tahoe donors on the Intel build Mac.

Uses the existing 25G342 installer/KDK and 26B131 userspace from step 5.
Runs the pinned upstream extraction/build tools; publishes a result only if its
original input-row hash matches. No network, package installation, root patch,
disk formatting, kernel linking or boot is performed by this wrapper.

Run from ~/Desktop/hao-patcher-mbp91 with Python 3.14, without sudo.
All Apple payloads stay local. The report ZIP includes metadata and text logs only.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import queue
import re
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass

UPSTREAM = '6bd75aab112d1078acd8e75180eb510672461365'
GOLDEN, DONOR, MODEL = '26B131', '25G342', 'MacBookPro9,1'
GIB = 1024 ** 3
PINS = {
    'installer': '3d9551b7a18c1fa2f86e7002a132ec3db34d7915fa842cb1e890480b51be4ef3',
    'kdk': '219f27c7e039b6ab3426496e0d5852d55a31d00b3d3984d855cba04377c5dba0',
    'golden_gate_userspace': '060bd378064461f4778fb3c312dffc7f181a1a0d3f534bdf76fefb4ba7798038',
    'darwin27_kernel': '3c9317518535791503970fbec322b9bba70e91f3a233536205ccd77b047ffc83',
}
ROLES = (
    ('native', 'tahoe_native_donors'),
    ('extensions', 'tahoe_extensions_donors'),
    ('driverkit', 'tahoe_driverkit_donors'),
    ('boot', 'tahoe_boot_donors'),
    ('recovery', 'tahoe_recovery_donors'),
)
AUX_ROWS = ('tahoe_kmutil', 'tahoe_basesystem', 'tahoe_os_cache_x86_64h', 'tahoe_kc_builder')
OUTPUT_ROWS = tuple(row for _, row in ROLES) + AUX_ROWS
GUARDED = ('pipeline/lock.py', 'pipeline/source_commit.py', 'pipeline/unpack',
           'tools/tahoe-donors', 'tools/cache-dylib')


class Stop(RuntimeError):
    pass


def stamp() -> str:
    return dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def data(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise Stop('Nu este un obiect JSON: ' + str(path))
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_path(repo: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise Stop('Cale relativa nepermisa: ' + relative)
    out = repo / p
    if not inside(repo, out):
        raise Stop('Calea iese din proiect: ' + relative)
    return out


@dataclass(frozen=True)
class Row:
    name: str
    lock: Path
    digest: str
    path: Path


def row_for(repo: Path, name: str) -> Row:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise Stop('Nume de intrare invalid: ' + name)
    for folder in (repo / 'pipeline/inputs/golden' / GOLDEN,
                   repo / 'pipeline/inputs' / DONOR, repo / 'pipeline/inputs/common'):
        p = folder / name
        if not p.is_file():
            continue
        lines = [x.partition('#')[0].strip() for x in p.read_text().splitlines()]
        lines = [x for x in lines if x]
        if len(lines) != 1 or len(lines[0].split(None, 1)) != 2:
            raise Stop('Intrare ambigua: ' + str(p))
        digest, relative = lines[0].split(None, 1)
        if not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise Stop('Intrarea nu are un SHA256 fixat: ' + name)
        if name in PINS and PINS[name] != digest:
            raise Stop('Versiunea fixata s-a schimbat: ' + name)
        path = safe_path(repo, relative)
        if not inside(repo / 'store', path):
            raise Stop('Intrarea nu este in store/: ' + name)
        return Row(name, p, digest, path)
    raise Stop('Lipseste intrarea: ' + name)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    if p.returncode:
        raise Stop('Git: ' + p.stderr.strip())
    return p.stdout.strip()


def donor_commands(repo: Path, raw: Path, cache: Path, outputs: dict[str, Path]) -> list[tuple[str, list[str]]]:
    """The five argument lists used by upstream pipeline/make-on-mac."""
    common = ['--tree', str(raw / 'tree'), '--metadata', str(raw / 'lists/sys.tsv'),
              '--links', str(raw / 'zip/AssetData/payloadv2/links.txt')]
    layout = ['--tree', str(raw / 'tree'), '--unpack', str(raw),
              '--map', str(raw / 'preboot-recovery-map.tsv')]
    args = {
        'native': common + ['--cache', str(cache)],
        'extensions': common,
        'driverkit': ['--source', str(raw / 'out/driverkit'), '--metadata', str(raw / 'out/driverkit/metadata.tsv')],
        'boot': layout, 'recovery': layout,
    }
    return [(name, [sys.executable, '-I', '-B', str(repo / 'tools/tahoe-donors/make'), role,
                    *args[role], '--recipe', str(raw / 'recipe.json'), '--output', str(outputs[name])])
            for role, name in ROLES]


class Work:
    def __init__(self, repo: Path):
        self.repo = repo
        self.local = repo / 'local/mbp91'
        self.local.mkdir(parents=True, exist_ok=True)
        self.work = repo / 'store/tmp/mbp91-step6'
        self.work.mkdir(parents=True, exist_ok=True)
        self.log_path = self.local / 'step6-build.log'
        self.log = self.log_path.open('a', encoding='utf-8')
        self.log.write('\n=== RUN ' + stamp() + ' ===\n'); self.log.flush()
        self.log_offset = self.log.tell()
        self.locklib = runpy.run_path(str(repo / 'pipeline/lock.py'))
        self.rows = {name: row_for(repo, name) for name in (*PINS, *OUTPUT_ROWS)}
        self.valid: set[str] = set()
        self.result = {
            'schema': 'hao-mbp91-step6-v1', 'model': MODEL, 'upstream_commit': UPSTREAM,
            'golden_build': GOLDEN, 'donor_build': DONOR,
            'donors_ready': False, 'kernel_tools_ready': False, 'rows': {}, 'commands': [],
            'raw_extraction_ready': False, 'runtime_payload_ready': False,
            'image_built': False, 'boot_validated': False, 'final_golden_efi_ready': False,
            'errors': [], 'warnings': [],
            'remaining': ['hao-runtime complete payload and compatibility interfaces',
                          'Golden Gate compatibility/graphics artifacts',
                          'KDK Intel overlay, kernel collections, cryptex, image assembly and final EFI',
                          'MacBookPro9,1 boot validation'],
        }
        self.report_paths: set[Path] = set()

    def save(self) -> None:
        write_json(self.local / 'step6-result.json', self.result)

    def run(self, argv, *, capture=False, check=True, timeout=4 * 60 * 60, input_data=None):
        argv = [str(x) for x in argv]
        print('  > ' + ' '.join(argv[:4]) + (' ...' if len(argv) > 4 else ''), flush=True)
        self.log.write('$ ' + ' '.join(argv) + '\n'); self.log.flush()
        env = dict(os.environ)
        # Use the pinned vendored library extractor, not a host override.
        env.pop('CACHE_DYLIB', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        start = time.monotonic()
        if capture:
            p = subprocess.run(argv, cwd=self.repo, env=env, input=input_data,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            self.log.write(p.stdout.decode(errors='replace')); self.log.write(p.stderr.decode(errors='replace'))
        else:
            chunks: queue.Queue = queue.Queue()
            proc = subprocess.Popen(argv, cwd=self.repo, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            assert proc.stdout is not None
            def reader():
                try:
                    for line in iter(proc.stdout.readline, b''):
                        chunks.put(line)
                finally:
                    chunks.put(None)
            thread = threading.Thread(target=reader, daemon=True); thread.start()
            last = start
            try:
                while True:
                    if time.monotonic() - start > timeout:
                        raise Stop('Limita de executie depasita: ' + Path(argv[0]).name)
                    try:
                        line = chunks.get(timeout=1)
                    except queue.Empty:
                        if time.monotonic() - last >= 30:
                            print('    Procesul lucreaza; log: local/mbp91/step6-build.log', flush=True)
                            last = time.monotonic()
                        continue
                    if line is None:
                        break
                    text = line.decode(errors='replace')
                    print(text, end='', flush=True)
                    self.log.write(text); self.log.flush(); last = time.monotonic()
                rc = proc.wait(timeout=30)
                p = subprocess.CompletedProcess(argv, rc, b'', b'')
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                raise
            finally:
                proc.stdout.close()
                thread.join(timeout=2)
        self.log.write('\nreturncode=%d\n' % p.returncode); self.log.flush()
        self.result['commands'].append({'argv': argv, 'returncode': p.returncode,
                                        'elapsed_s': round(time.monotonic() - start, 1)})
        self.save()
        if check and p.returncode:
            tail = p.stderr.decode(errors='replace')[-1500:] if capture else ''
            raise Stop('Comanda a esuat (cod %d): %s%s' %
                       (p.returncode, ' '.join(argv[:4]), ('\n' + tail) if tail else ''))
        return p

    def matches(self, row: Row, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            actual = self.locklib['row_hash'](str(row.lock.parent), row.name, str(path))
        except (SystemExit, OSError, ValueError) as e:
            raise Stop('Verificare %s: %s' % (row.name, e)) from e
        if actual != row.digest:
            self.result.setdefault('hash_mismatches', []).append({
                'row': row.name, 'path': str(path.relative_to(self.repo)),
                'expected': row.digest, 'actual': actual})
            self.save()
            return False
        return True

    def verify(self, name: str) -> Path:
        row = self.rows[name]
        if name not in self.valid:
            print('  SHA256: ' + name, flush=True)
            if not self.matches(row, row.path):
                raise Stop('Intrare absenta sau cu hash diferit: %s. Hash-ul original ramane neschimbat.' % name)
            self.valid.add(name)
            self.result['rows'][name] = {'path': str(row.path.relative_to(self.repo)),
                                         'sha256': row.digest, 'verified': True}
            self.save()
        return row.path

    def reuse(self, name: str) -> bool:
        if self.rows[name].path.exists():
            self.verify(name)
            print('  Refolosesc: ' + name, flush=True)
            return True
        return False

    def partial(self, final: Path) -> Path:
        if not inside(self.repo / 'store', final) or final == self.repo / 'store':
            raise Stop('Destinatie de lucru invalida: ' + str(final))
        if final.exists() or final.is_symlink():
            raise Stop('Destinatia exista deja: ' + str(final))
        final.parent.mkdir(parents=True, exist_ok=True)
        return final.with_name(final.name + '.partial-step6-' + stamp())

    def publish(self, name: str, partial_root: Path, final_root: Path, suffix=()) -> None:
        row = self.rows[name]
        if row.path != final_root.joinpath(*suffix):
            raise Stop('Structura neasteptata pentru ' + name)
        made = partial_root.joinpath(*suffix)
        print('  Verific rezultatul: ' + name, flush=True)
        if not self.matches(row, made):
            raise Stop('Rezultatul %s nu corespunde hash-ului Hao. Pastrat pentru analiza: %s' % (name, partial_root))
        if final_root.exists() or final_root.is_symlink():
            raise Stop('Destinatia a aparut in timpul construirii: ' + str(final_root))
        os.replace(partial_root, final_root)
        self.valid.add(name)
        self.result['rows'][name] = {'path': str(row.path.relative_to(self.repo)),
                                     'sha256': row.digest, 'verified': True, 'made_here': True}
        if (final_root / 'build.json').is_file():
            self.report_paths.add(final_root / 'build.json')
        self.save()

    @contextlib.contextmanager
    def mounted(self, image: Path, label: str):
        point = Path(tempfile.mkdtemp(prefix='mount-' + label + '-', dir=self.work))
        attached = False
        try:
            p = self.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-owners', 'on',
                          '-plist', '-mountpoint', point, image], capture=True, timeout=180)
            attached = True
            info = plistlib.loads(p.stdout)
            if not any(x.get('mount-point') == str(point) for x in info.get('system-entities', [])):
                raise Stop('Montarea nu a folosit directorul rezervat: ' + str(point))
            yield point
        finally:
            if attached:
                p = self.run(['/usr/bin/hdiutil', 'detach', point], capture=True, check=False, timeout=120)
                if p.returncode:
                    self.result['warnings'].append('Imagine read-only ramasa montata: ' + str(point))
            try:
                point.rmdir()
            except OSError:
                pass

    def report(self) -> Path:
        self.log.flush(); self.save()
        archive = Path.home() / 'Desktop/HAO-mbp91-step6.zip'
        names = {self.local / x for x in ('step6-result.json', 'step6-extraction.json',
                                        'step5-result.json', 'step5-download-plan.json')}
        names.update(self.report_paths)
        raw = self.work / 'donor-inputs'
        names.update(raw / x for x in ('report.json', 'report.txt', 'recipe.json'))
        names.add(self.work / 'cache-images.txt')
        names.update(row.lock for row in self.rows.values())
        names.add(self.repo / 'pipeline/assemblies/mbp91-26B131.json')
        temp = archive.with_name(archive.name + '.tmp')
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(names):
                if p.is_file() and inside(self.repo, p) and p.stat().st_size <= 16 << 20:
                    z.write(p, str(p.relative_to(self.repo)))
            with self.log_path.open('rb') as f:
                size = self.log_path.stat().st_size
                if size > 16 << 20:
                    f.seek(size - (16 << 20))
                    z.writestr('local/mbp91/step6-build.log', b'[Ultimii 16 MiB din log]\n' + f.read())
                else:
                    z.writestr('local/mbp91/step6-build.log', f.read())
        os.replace(temp, archive)
        return archive


def check_preconditions(repo: Path) -> None:
    if sys.platform != 'darwin' or os.uname().machine != 'x86_64':
        raise Stop('Ruleaza pe iMac-ul Intel, in macOS.')
    if os.geteuid() == 0:
        raise Stop('Ruleaza fara sudo, cu contul normal.')
    if sys.version_info[:2] != (3, 14):
        raise Stop('Foloseste python3.14 pentru aceasta etapa.')
    if git(repo, 'rev-parse', 'HEAD') != UPSTREAM:
        raise Stop('Copia nu este la commitul 6bd75aa folosit in etapele anterioare.')
    changed = git(repo, 'diff', '--name-only', 'HEAD', '--', *GUARDED)
    if changed:
        raise Stop('Producatori modificati fata de versiunea verificata:\n' + changed)
    extra = git(repo, 'ls-files', '--others', '--exclude-standard', '--', *GUARDED)
    if extra:
        raise Stop('Fisiere suplimentare in directoarele producatorilor:\n' + extra)
    previous = data(repo / 'local/mbp91/step5-result.json')
    if previous.get('model') != MODEL or any(previous.get(k) is not True for k in
                       ('apple_inputs_ready', 'userspace_ready', 'kernel_ready', 'step_complete')):
        raise Stop('Aceasta copie nu contine un pas 5 incheiat pentru MacBookPro9,1.')
    target = data(repo / 'pipeline/assemblies/mbp91-26B131.json')
    if (target.get('target'), target.get('golden_build'), target.get('donor_build')) != ('mbp91', GOLDEN, DONOR):
        raise Stop('Reteta mbp91 nu corespunde versiunilor fixate.')
    for prog in ('/usr/bin/hdiutil', '/usr/bin/cc', '/usr/bin/aa', '/usr/bin/codesign', '/bin/cp'):
        if not os.access(prog, os.X_OK):
            raise Stop('Lipseste utilitarul macOS: ' + prog)


def extraction_identity(w: Work) -> dict:
    return {'upstream_commit': UPSTREAM, 'golden_build': GOLDEN, 'donor_build': DONOR,
            'inputs': {n: w.rows[n].digest for n in PINS},
            'requirements_sha256': sha(w.repo / 'tools/tahoe-donors/recipes/intel-donors.json')}


def check_raw(raw: Path) -> dict:
    report = data(raw / 'report.json')
    recipe = data(raw / 'recipe.json')
    if report.get('build') != DONOR or recipe.get('origin', {}).get('build') != DONOR:
        raise Stop('Donatorii nu provin din ' + DONOR)
    if recipe.get('origin', {}).get('installer_sha256') != PINS['installer']:
        raise Stop('Instalator diferit in reteta donatorilor.')
    missing = [x for x in report.get('report', []) if x.get('status') == 'MISSING' and x.get('required')]
    if missing:
        raise Stop('Donatorii au cerinte obligatorii lipsa: ' + ', '.join(x.get('item', '?') for x in missing))
    required = ('tree', 'tree/usr/bin/kmutil', 'lists/sys.tsv', 'zip/AssetData/payloadv2/links.txt',
                'out/BaseSystem-x86_64.dmg', 'out/driverkit/metadata.tsv',
                'out/os-cache/dyld_shared_cache_x86_64h', 'preboot-recovery-map.tsv')
    for rel in required:
        if not (raw / rel).exists():
            raise Stop('Extragere incompleta: ' + rel)
    return report


def extract(w: Work) -> Path:
    raw = w.work / 'donor-inputs'
    receipt = w.local / 'step6-extraction.json'
    identity = extraction_identity(w)
    if raw.exists():
        if receipt.is_file() and (raw / 'report.json').is_file() and (raw / 'recipe.json').is_file():
            rec = data(receipt)
            if rec.get('identity') == identity and rec.get('report_sha256') == sha(raw / 'report.json'):
                check_raw(raw)
                if rec.get('recipe_sha256') != sha(raw / 'recipe.json'):
                    raise Stop('Reteta extragerii pastrate a fost schimbata.')
                print('  Refolosesc extragerea Tahoe incheiata anterior.', flush=True)
                w.result['raw_extraction_ready'] = True; w.save()
                return raw
        # An interrupted extraction is preserved, never mistaken for a completed one.
        old = raw.with_name(raw.name + '.incomplete-' + stamp())
        raw.rename(old)
        w.result['warnings'].append('Extragere incompleta pastrata in ' + str(old.relative_to(w.repo)))
    payload = w.rows['golden_gate_userspace'].path
    with w.mounted(payload / 'filesystem.dmg', 'system') as system, \
         w.mounted(payload / 'rosetta.dmg', 'rosetta') as rosetta:
        cache = rosetta / 'System/Library/dyld/dyld_shared_cache_x86_64'
        if not cache.is_file():
            raise Stop('Lipseste cache-ul generic x86_64 din Rosetta.')
        images = w.work / 'cache-images.txt'
        w.run([sys.executable, '-I', '-B', 'pipeline/unpack/cache-images', 'list', cache, images])
        w.run([sys.executable, '-I', '-B', 'pipeline/unpack/donor-inputs', w.rows['installer'].path, raw,
               '--requirements', 'tools/tahoe-donors/recipes/intel-donors.json',
               '--kdk', w.rows['kdk'].path, '--target-system', system, '--target-cache-images', images])
        # Deliberately no --ripatch: the upstream fallback compiles its own C source with /usr/bin/cc.
    report = check_raw(raw)
    write_json(receipt, {'identity': identity, 'report_sha256': sha(raw / 'report.json'),
                         'recipe_sha256': sha(raw / 'recipe.json'), 'complete': True})
    w.result['raw_extraction_ready'] = True
    w.result['root_choices'] = report.get('root_choices', [])
    w.result['optional_missing'] = [x for x in report.get('report', [])
                                    if x.get('status') == 'MISSING' and not x.get('required')]
    w.save()
    return raw


def copy_aux(w: Work, raw: Path) -> None:
    for name, src in (('tahoe_kmutil', raw / 'tree/usr/bin/kmutil'),
                      ('tahoe_basesystem', raw / 'out/BaseSystem-x86_64.dmg')):
        if w.reuse(name):
            continue
        final = w.rows[name].path; partial = w.partial(final)
        w.run(['/bin/cp', '-c', src, partial])
        w.publish(name, partial, final)
    name = 'tahoe_os_cache_x86_64h'
    if not w.reuse(name):
        row = w.rows[name]
        if row.path.name != 'dyld_shared_cache_x86_64h':
            raise Stop('Calea cache-ului Tahoe are un format neasteptat.')
        final = row.path.parent; partial = w.partial(final)
        w.run(['/bin/cp', '-c', '-R', raw / 'out/os-cache', partial])
        # Verify every copied subcache that the extraction itself recorded, not only the main row.
        rep = data(raw / 'report.json')
        for rel, expected in rep.get('outputs', {}).items():
            if rel.startswith('out/os-cache/'):
                p = safe_path(partial, rel[len('out/os-cache/'):])
                if not p.is_file() or sha(p) != expected:
                    raise Stop('Copie incompleta/diferita de subcache: ' + rel)
        w.publish(name, partial, final, (row.path.name,))


def build_donors(w: Work, raw: Path) -> None:
    for role, name in ROLES:
        if w.reuse(name):
            continue
        final = w.rows[name].path; partial = w.partial(final)
        outputs = {n: w.rows[n].path for _, n in ROLES}
        outputs[name] = partial
        cmd = dict(donor_commands(w.repo, raw, w.rows['tahoe_os_cache_x86_64h'].path.parent, outputs))[name]
        print('  Pachet: ' + role, flush=True)
        w.run(cmd)
        w.publish(name, partial, final)
    w.result['donors_ready'] = all(n in w.valid for _, n in ROLES); w.save()


def build_kc(w: Work) -> None:
    name = 'tahoe_kc_builder'
    if w.reuse(name):
        return
    row = w.rows[name]
    if row.path.name != 'libKernelCollectionBuilder.dylib':
        raise Stop('Calea kc-builder nu este fisierul asteptat.')
    final = row.path.parent; partial = w.partial(final)
    w.run([sys.executable, '-I', '-B', 'pipeline/unpack/kc-builder', partial,
           '--inputs', w.rows['tahoe_os_cache_x86_64h'].lock.parent])
    w.publish(name, partial, final, (row.path.name,))


def execute(w: Work) -> int:
    print('1/5 Verific sursele pasului 5. Nu descarc din nou IPSW, instalatorul sau KDK-ul.', flush=True)
    for name in PINS:
        w.verify(name)
    missing = [n for n in OUTPUT_ROWS if not w.reuse(n)]
    if missing and shutil.disk_usage(w.repo).free < 70 * GIB:
        raise Stop('Extragerea foloseste spatiu temporar. Rezerva operationala a scriptului: 70 GiB liberi; '
                   'nu este o cerinta oficiala Hao. Nu incep extragerea cu mai putin.')
    needs_raw = any(n not in w.valid for n in OUTPUT_ROWS if n != 'tahoe_kc_builder')
    raw = None
    print('2/5 Extrag componentele Intel Tahoe in functie de continutul Golden Gate.', flush=True)
    if needs_raw:
        raw = extract(w)
        copy_aux(w, raw)
    print('3/5 Construiesc cele cinci pachete: native, extensions, DriverKit, boot, Recovery.', flush=True)
    if raw is not None:
        build_donors(w, raw)
    w.result['donors_ready'] = all(n in w.valid for _, n in ROLES)
    print('4/5 Pregatesc kmutil si biblioteca Tahoe pentru construirea colectiilor kernel.', flush=True)
    build_kc(w)
    w.result['kernel_tools_ready'] = all(n in w.valid for n in AUX_ROWS)
    print('5/5 Inregistrez rezultatele verificate si raportul de transfer.', flush=True)
    for name in OUTPUT_ROWS:
        w.verify(name)
    w.result['step_complete'] = True
    w.result['runtime_status'] = ('Arhiva oficiala a raspuns 404 la pasul 5; acest pas nu construieste '
                                   'hao-runtime si nu substituie un alt build.')
    w.save()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path.cwd())
    a = p.parse_args()
    repo = a.repo.expanduser().resolve()
    w = None
    code = 1
    try:
        check_preconditions(repo)
        local = repo / 'local/mbp91'
        with (local / '.step6.lock').open('a+') as lockfile:
            try:
                fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop('Pasul 6 ruleaza deja in aceasta copie.') from None
            w = Work(repo)
            try:
                local_script = local / 'HAO-mbp91-step6.py'
                if Path(__file__).resolve() != local_script.resolve():
                    shutil.copy2(__file__, local_script)
                code = execute(w)
            except (Exception, KeyboardInterrupt) as e:
                w.result['errors'].append(type(e).__name__ + ': ' + str(e))
                w.result['step_complete'] = False
                w.log.write('\n' + traceback.format_exc()); w.log.flush()
                print('\nOPRIT: ' + str(e), flush=True)
            finally:
                w.result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                try:
                    report = w.report()
                    print('\nPachete donatoare Tahoe construite si verificate: ' + ('DA' if w.result['donors_ready'] else 'NU'))
                    print('Unelte Tahoe pentru kernel pregatite: ' + ('DA' if w.result['kernel_tools_ready'] else 'NU'))
                    print('Runtime complet / imagine bootabila / boot validat: NU.')
                    print('Arhiva MICA de trimis: ' + str(report))
                    print('Pachetele reale si extragerea reutilizabila raman in store/.')
                finally:
                    w.log.close()
    except (Stop, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        code = 1
        print('OPRIT: ' + str(e), file=sys.stderr)
        if w is None:
            # Even an early failure yields a small report when the repository can be identified.
            try:
                dest = Path.home() / 'Desktop/HAO-mbp91-step6.zip'
                with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('step6-early-error.txt', str(e) + '\n')
                print('Raport eroare: ' + str(dest), file=sys.stderr)
            except OSError:
                pass
    return code


if __name__ == '__main__':
    raise SystemExit(main())
