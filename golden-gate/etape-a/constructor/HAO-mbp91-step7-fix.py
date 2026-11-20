#!/usr/bin/env python3
"""Finish step 7 using its existing outputs. No download, make, test rerun or kext load.

Fix: ld64 may omit version load commands for MH_KEXT_BUNDLE. This is not an
incorrect deployment target. An absent version is recorded as unknown, never
invented as 13.0. User-space binaries still require an exact minimum version.
The requested kext target is checked separately in the previous build command.

Run with python3.14 -I from ~/Desktop/hao-patcher-mbp91, without sudo.
The previous result is saved before publishing a corrected result. The eight
prior test results are reused only if their binary hashes still match.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import struct
import sys
import traceback
import zipfile

ORIGINAL_SHA256 = '24cb2f7e9bf59ff7ab96a82b310609043026aeb6a7568bcdf224cf95c96b6c2a'
PATCHER = '6bd75aab112d1078acd8e75180eb510672461365'
RUNTIME = '1547dcb4e19a2ab0843086e3288223f998507a4c'
SOURCE = 'store/sources/hao-runtime-1547dcb4e19a'
# Apple's linker makes version load commands opt-in for kext bundles:
# apple-oss-distributions/ld64, f60a74eaa2c99585de1dc0f2820e7a9f8aaf522c,
# src/ld/Options.cpp: switch below "default to adding version load command".


class FixError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_original(repo: Path):
    path = repo / 'local/mbp91/HAO-mbp91-step7.py'
    if not path.is_file() or path.is_symlink() or digest(path) != ORIGINAL_SHA256:
        raise FixError('Scriptul local al pasului 7 nu corespunde versiunii analizate. Nu il execut.')
    spec = importlib.util.spec_from_file_location('hao_mbp91_step7_original', path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def ver(number: int) -> str:
    return '%d.%d.%d' % (number >> 16, (number >> 8) & 255, number & 255)


def macho_info(path: Path, expected_type: int, requested_minimum: str) -> dict:
    """Strict thin-x86_64 header parsing; only a kext may omit a version command."""
    total = path.stat().st_size
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise FixError('Header Mach-O incomplet: ' + str(path))
        magic, cpu, subtype, kind, ncmds, size, flags, reserved = struct.unpack('<8I', header)
        if magic != 0xfeedfacf or cpu != 0x01000007 or kind != expected_type:
            raise FixError('Arhitectura/tip Mach-O neasteptat: ' + str(path))
        if not 0 < ncmds <= 65536 or size > 16 * 1024 * 1024 or size < ncmds * 8:
            raise FixError('Numar/lungime de load commands invalide: ' + str(path))
        commands = stream.read(size)
    if len(commands) != size:
        raise FixError('Load commands trunchiate: ' + str(path))
    versions, uuids, command_ids, segments = [], [], [], []
    pos = 0
    for _ in range(ncmds):
        if pos + 8 > size:
            raise FixError('Load command lipsa')
        cmd, length = struct.unpack_from('<II', commands, pos)
        if length < 8 or length % 8 or pos + length > size:
            raise FixError('Lungime/aliniere load command invalida')
        command_ids.append('0x%08x' % cmd)
        if cmd == 0x32:
            if length < 24:
                raise FixError('LC_BUILD_VERSION trunchiat')
            plat, minimum, sdk, ntools = struct.unpack_from('<4I', commands, pos + 8)
            if plat != 1 or length != 24 + 8 * ntools:
                raise FixError('LC_BUILD_VERSION: platforma sau lungime incorecta')
            versions.append((ver(minimum), ver(sdk)))
        elif cmd == 0x24:
            if length != 16:
                raise FixError('LC_VERSION_MIN_MACOSX invalid')
            minimum, sdk = struct.unpack_from('<II', commands, pos + 8)
            versions.append((ver(minimum), ver(sdk)))
        elif cmd in (0x25, 0x2f, 0x30):
            raise FixError('Load command pentru alta platforma decat macOS')
        elif cmd == 0x1b:
            if length != 24:
                raise FixError('LC_UUID invalid')
            uuids.append(commands[pos + 8:pos + 24].hex())
        elif cmd == 0x19:
            if length < 72:
                raise FixError('LC_SEGMENT_64 trunchiat')
            rawname = commands[pos + 8:pos + 24]
            vmaddr, vmsize, offset, filesize, maxprot, initprot, nsects, sflags = struct.unpack_from(
                '<4Q4I', commands, pos + 24)
            if length != 72 + nsects * 80 or offset > total or filesize > total - offset:
                raise FixError('LC_SEGMENT_64: limite invalide')
            segments.append({'name': rawname.split(b'\0', 1)[0].decode('ascii', errors='replace'),
                             'filesize': filesize, 'vmsize': vmsize, 'initprot': initprot})
        elif cmd == 0x1d:
            if length != 16:
                raise FixError('LC_CODE_SIGNATURE invalid')
            offset, count = struct.unpack_from('<II', commands, pos + 8)
            if count == 0 or offset < 32 + size or offset > total or count > total - offset:
                raise FixError('Semnatura Mach-O in afara fisierului')
        pos += length
    if pos != size:
        raise FixError('sizeofcmds nu corespunde comenzilor')
    want = tuple(int(x) for x in requested_minimum.split('.'))
    want = (want + (0, 0, 0))[:3]
    missing_allowed = kind == 11 and not versions
    if not missing_allowed and (len(versions) != 1 or tuple(map(int, versions[0][0].split('.'))) != want):
        raise FixError('Versiune Mach-O incorecta: %r; asteptat %s' % (versions, requested_minimum))
    if kind == 11 and not any(s['name'] in ('__TEXT', '__TEXT_EXEC') and s['filesize'] > 0
                              and s['initprot'] & 4 for s in segments):
        raise FixError('Kext fara segment executabil __TEXT/__TEXT_EXEC')
    return {'architecture': 'x86_64', 'cpu_subtype': subtype, 'filetype': kind,
            'minimum_macos': versions[0][0] if versions else None,
            'sdk': versions[0][1] if versions else None,
            'version_command_status': 'absent_allowed_for_MH_KEXT_BUNDLE' if missing_allowed else 'exact_match',
            'requested_build_minimum': requested_minimum, 'uuids': uuids,
            'load_commands': command_ids, 'segments': segments,
            'bytes': total, 'sha256': digest(path)}


def check_previous(previous: dict, module) -> None:
    if previous.get('patcher_commit') != PATCHER or previous.get('runtime_commit') != RUNTIME:
        raise FixError('Raportul este pentru alte surse.')
    if previous.get('source_path') != SOURCE:
        raise FixError('Calea sursei runtime difera de cea analizata.')
    if not previous.get('target_runtime_built') or not previous.get('host_tests_passed'):
        raise FixError('Raportul nu confirma runtime-ul compilat si testele trecute.')
    for error in previous.get('errors', []):
        if error.get('stage') != 'HaoExec.kext' or 'Deployment target incorect' not in error.get('error', ''):
            raise FixError('Exista alta eroare, care nu este acoperita de aceasta corectie: ' + str(error))
    paths = previous.get('build_directories', {})
    target, host = paths.get('target', ''), paths.get('host_tests', '')
    if not re.fullmatch(r'build/mbp91-step7-[a-f0-9]{16}/macos-27\.0', target):
        raise FixError('Director build neasteptat: ' + target)
    if host != target.removesuffix('27.0') + '26.0':
        raise FixError('Directorul testelor nu corespunde buildului.')
    expected = {name for name, _ in module.HOST_TESTS}
    if set(previous.get('tests', {})) != expected:
        raise FixError('Lista testelor din raport difera.')
    if not all(previous['tests'][n].get('passed') and previous['tests'][n].get('returncode') == 0 for n in expected):
        raise FixError('Nu toate testele au trecut.')
    if not any(c.get('argv') == ['/bin/bash', 'kext/build.sh', target, '13.0']
               and c.get('returncode') == 0 and not c.get('timed_out')
               for c in previous.get('commands', [])):
        raise FixError('Lipseste dovada compilarii reusite a kextului cu parametrul 13.0.')


def reuse_runtime_and_tests(w, old: dict, module) -> None:
    if w.git(w.repo, 'rev-parse', 'HEAD') != PATCHER:
        raise FixError('Commitul hao-patcher a fost schimbat.')
    module.verify_source(w, w.source)
    generated = module.generated_inputs(w.source)
    module.write_json(w.run_dir / 'step7-generated-inputs.json', generated)
    w.result['compile_time_tables_verified'] = len(generated['files'])
    base = module.safe_path(w.source, w.target_build)
    expected = set(module.CORE_FILES) | set(module.STATIC_FILES)
    if set(old.get('target_runtime_files', {})) != expected:
        raise FixError('Lista componentelor runtime difera.')
    for name in sorted(expected):
        path = module.safe_path(base, name)
        record = old['target_runtime_files'][name]
        if not path.is_file() or digest(path) != record.get('sha256'):
            raise FixError('Binar runtime lipsa sau schimbat: ' + name)
        if name in module.CORE_FILES:
            info = macho_info(path, module.CORE_FILES[name], '27.0')
            w.result['target_runtime_files'][name].update(info)
    for name in module.SIGNED_FILES:
        w.run(['/usr/bin/codesign', '--verify', '--verbose=2', base / name], quiet=True)
    host = module.safe_path(w.source, w.host_build)
    for name, _ in module.HOST_TESTS:
        binary = module.safe_path(host, name)
        old_test = old['tests'][name]
        if not binary.is_file() or digest(binary) != old_test['binary']['sha256']:
            raise FixError('Binarul unui test a fost schimbat; rezultatul nu poate fi reutilizat: ' + name)
        macho_info(binary, 2, '26.0')
        w.result['tests'][name]['reused_after_hash_verification'] = True
    w.result['host_tests_reused_from_run'] = old['run_id']
    w.result['target_runtime_built'] = True
    w.result['host_tests_passed'] = True
    w.save()


def verify_existing_kext(w, module) -> None:
    base = module.safe_path(w.source, w.target_build)
    bundle = base / 'HaoExec.kext'
    binary = bundle / 'Contents/MacOS/HaoExec'
    info = macho_info(binary, 11, '13.0')
    plistpath = bundle / 'Contents/Info.plist'
    if plistpath.read_bytes() != (w.source / 'kext/HaoExec/Info.plist').read_bytes():
        raise FixError('Info.plist nu mai corespunde sursei fixate.')
    pl = plistlib.loads(plistpath.read_bytes())
    if pl.get('CFBundleExecutable') != 'HaoExec' or pl.get('CFBundlePackageType') != 'KEXT':
        raise FixError('Identitate de bundle HaoExec incorecta.')
    # Preserve raw evidence without changing or re-signing the binary.
    _, details = w.run(['/usr/bin/otool', '-hv', '-l', binary], quiet=True)
    (w.run_dir / 'HaoExec-load-commands.txt').write_text(details, encoding='utf-8')
    w.run(['/usr/bin/codesign', '--verify', '--verbose=2', bundle], quiet=True)
    if digest(binary) != info['sha256']:
        raise FixError('Binarul HaoExec s-a schimbat in timpul verificarii.')
    w.result['kext'] = {'binary': info, 'bundle_identifier': pl.get('CFBundleIdentifier'),
                        'info_plist_sha256': digest(plistpath), 'signature_verified': True,
                        'kernel_identity_stamped': False, 'recompiled': False,
                        'requested_minimum_evidence': 'Previous successful kext/build.sh invocation with 13.0',
                        'note': 'Missing version command allowed only for MH_KEXT_BUNDLE. Not loaded or boot-tested.'}
    w.result['unstamped_kext_built'] = True
    w.save()


def publish_core(w, module) -> None:
    if not all(w.result.get(k) for k in ('target_runtime_built', 'host_tests_passed', 'unstamped_kext_built')):
        raise FixError('Nu sunt complete verificarile necesare publicarii artefactului local.')
    artifacts = w.repo / 'store/artifacts'
    artifacts.mkdir(parents=True, exist_ok=True)
    dest = artifacts / ('mbp91-hao-runtime-core-' + RUNTIME[:12] + '-local-fix-' + w.run_id)
    partial = dest.with_name(dest.name + '.partial')
    partial.mkdir(mode=0o755)
    base = module.safe_path(w.source, w.target_build)
    for name in tuple(module.CORE_FILES) + module.STATIC_FILES:
        out = partial / 'runtime-build' / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / name, out)
        if digest(out) != w.result['target_runtime_files'][name]['sha256']:
            raise FixError('Copie runtime diferita: ' + name)
    shutil.copytree(base / 'HaoExec.kext', partial / 'HaoExec.kext', symlinks=True)
    copied_binary = partial / 'HaoExec.kext/Contents/MacOS/HaoExec'
    if digest(copied_binary) != w.result['kext']['binary']['sha256']:
        raise FixError('Copie kext diferita.')
    w.run(['/usr/bin/codesign', '--verify', '--verbose=2', partial / 'HaoExec.kext'], quiet=True)
    for name in ('LICENSE', 'NOTICE.md'):
        if (w.source / name).is_file():
            shutil.copy2(w.source / name, partial / name)
    (partial / 'SCOPE.txt').write_text(
        'LOCAL EXPERIMENTAL RUNTIME CORE. NOT AN INSTALLABLE HAO PAYLOAD.\n'
        'Runtime source: ' + RUNTIME + '\n'
        'Runtime: x86_64, Mach-O minimum macOS 27.0.\n'
        'HaoExec: x86_64 MH_KEXT_BUNDLE, unstamped. Build requested 13.0.\n'
        'The kext minimum OS is unknown if its Mach-O omits a version command.\n'
        'Eight prior Tahoe unit tests reused after verifying the same binary hashes.\n'
        'No download, rebuild, test rerun, kernel loading, image build or boot proof.\n'
        'No official hao_runtime hash or input row is replaced.\n'
        'Remaining payload work:\n- ' + '\n- '.join(module.MISSING_PAYLOAD) + '\n', encoding='utf-8')
    files = module.file_manifest(partial)
    record = {'schema': 2, 'operation': 'local-hao-runtime-core-finalize',
              'runtime_commit': RUNTIME, 'source_tree': module.RUNTIME_TREE,
              'patcher_commit': PATCHER, 'toolchain': w.result['toolchain'],
              'target_runtime_files': w.result['target_runtime_files'], 'kext': w.result['kext'],
              'host_tests_passed': True, 'host_tests_reused_from_run': w.result['host_tests_reused_from_run'],
              'host_tests': w.result['tests'], 'runtime_payload_ready': False,
              'published_payload_reproduced': False, 'remaining_payload_work': list(module.MISSING_PAYLOAD),
              'correction': w.result['correction'], 'files': files}
    module.write_json(partial / 'build.json', record)
    for rel, item in files.items():
        if digest(module.safe_path(partial, rel)) != item['sha256']:
            raise FixError('Hash diferit in artefact: ' + rel)
    os.replace(partial, dest)
    w.result['core_artifact'] = dest.relative_to(w.repo).as_posix()
    w.result['core_artifact_record_sha256'] = digest(dest / 'build.json')
    w.result['step_complete'] = True
    w.save()


def report_zip(w, module) -> Path:
    w.result['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    w.save()
    w.log.flush()
    destination = Path.home() / 'Desktop/HAO-mbp91-step7-fix.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + '.tmp')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(w.run_dir / 'result.json', 'local/mbp91/step7-result.json')
        archive.write(w.log_path, 'local/mbp91/step7-fix.log')
        for name in ('step7-previous-result.json', 'step7-previous-build.log',
                     'step7-generated-inputs.json', 'HaoExec-load-commands.txt'):
            path = w.run_dir / name
            if path.is_file():
                archive.write(path, 'local/mbp91/' + name)
        archive.write(Path(__file__).resolve(), 'local/mbp91/HAO-mbp91-step7-fix.py')
        if w.result.get('step_complete') and w.result.get('core_artifact'):
            rel = w.result['core_artifact'] + '/build.json'
            archive.write(module.safe_path(w.repo, rel), rel)
    os.replace(temp, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    w = None
    code = 1
    try:
        if platform.system() != 'Darwin' or platform.machine() != 'x86_64' or os.geteuid() == 0:
            raise FixError('Ruleaza pe iMac Intel, in macOS, fara sudo.')
        module = load_original(repo)
        local = repo / 'local/mbp91'
        with (local / '.step7.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            prior_path = local / 'step7-result.json'
            prior_raw = prior_path.read_bytes()
            previous = json.loads(prior_raw)
            check_previous(previous, module)
            old_log = local / 'step7-runs' / previous['run_id'] / 'build.log'
            old_log_bytes = old_log.read_bytes() if old_log.is_file() else None
            # Keep the user's prior result intact unless all corrected checks pass.
            class RepairWork(module.Work):
                def save(self):
                    module.write_json(self.run_dir / 'result.json', self.result)
            w = RepairWork(repo)
            (w.run_dir / 'step7-previous-result.json').write_bytes(prior_raw)
            if old_log_bytes is not None:
                (w.run_dir / 'step7-previous-build.log').write_bytes(old_log_bytes)
            w.result = copy.deepcopy(previous)
            w.result.update(schema='hao-mbp91-step7-v2', run_id=w.run_id, errors=[],
                            step_complete=False, unstamped_kext_built=False,
                            target_runtime_built=False, host_tests_passed=False,
                            runtime_payload_ready=False, published_payload_reproduced=False,
                            image_built=False, boot_validated=False)
            w.result.pop('core_artifact', None)
            w.result.pop('core_artifact_record_sha256', None)
            w.result['correction'] = {
                'kind': 'MH_KEXT_BUNDLE version load commands are optional',
                'previous_run_id': previous['run_id'],
                'previous_result_sha256': hashlib.sha256(prior_raw).hexdigest(),
                'fix_script_sha256': digest(Path(__file__).resolve()),
                'compilation_rerun': False, 'tests_rerun': False,
                'new_commands_start': len(w.result.get('commands', [])),
            }
            w.target_build = previous['build_directories']['target']
            w.host_build = previous['build_directories']['host_tests']
            w.source = module.safe_path(repo, SOURCE)
            tc = previous['toolchain']
            w.env = module.build_environment(tc['sdk_path'], str(Path(tc['clang']).parent))
            w.save()
            try:
                print('1/3 Reutilizez runtime-ul si cele opt teste; verific hash-urile.', flush=True)
                reuse_runtime_and_tests(w, previous, module)
                print('2/3 Verific HaoExec.kext cu regula corecta pentru MH_KEXT_BUNDLE.', flush=True)
                verify_existing_kext(w, module)
                print('3/3 Finalizez artefactul local, fara recompilare.', flush=True)
                publish_core(w, module)
                code = 0
            except (Exception, KeyboardInterrupt) as exc:
                w.result['step_complete'] = False
                w.result['errors'].append({'stage': 'step7-fix', 'error': type(exc).__name__ + ': ' + str(exc)})
                w.log.write('\n' + traceback.format_exc())
                print('OPRIT: ' + str(exc), flush=True)
            finally:
                archive = report_zip(w, module)
                if w.result.get('step_complete'):
                    module.write_json(local / 'step7-result.json', w.result)
                print('\nRuntime x86_64 reutilizat si verificat: ' + ('DA' if w.result['target_runtime_built'] else 'NU'))
                print('HaoExec.kext verificat, nestampilat: ' + ('DA' if w.result['unstamped_kext_built'] else 'NU'))
                print('Teste Intel/Tahoe: ' + ('8/8, rezultate reutilizate dupa verificarea binarelor' if w.result['host_tests_passed'] else 'neconfirmate'))
                print('Artefact local completat: ' + ('DA' if w.result['step_complete'] else 'NU'))
                if w.result.get('core_artifact'):
                    print('Artefact: ' + str(repo / w.result['core_artifact']))
                print('Payload Hao complet: NU. Boot validat: NU.')
                print('Arhiva de trimis: ' + str(archive))
    except (Exception, KeyboardInterrupt) as exc:
        print('OPRIT: ' + str(exc), file=sys.stderr)
        if w is None:
            try:
                path = Path.home() / 'Desktop/HAO-mbp91-step7-fix.zip'
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('step7-fix-error.txt', str(exc) + '\n')
                print('Raport: ' + str(path), file=sys.stderr)
            except OSError:
                pass
    finally:
        if w is not None:
            w.log.close()
    return code


if __name__ == '__main__':
    raise SystemExit(main())
