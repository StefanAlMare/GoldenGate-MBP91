#!/usr/bin/env python3
"""Finalize the existing completed Golden Gate image for MacBookPro9,1.

Run as the normal Intel build-Mac user from the project directory:
    python3.14 -I ~/Downloads/HAO-mbp91-step12-finalize.py

This finalizer validates the recorded completed image, its actual EFI and kernel
collections, then publishes those same bytes with SHA256 and an EFI archive.
It contains no image assembly, APFS probe, repartition, or cleanup operation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
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

VERSION='step12-finalize-existing-image-v1'
MODEL, BUILD, BOARD='MacBookPro9,1','26B131','Mac-4B7AC7E43945597E'
GOLDEN, DONOR='26B131','25G342'
ARCHIVE_NAME='HAO-mbp91-step12-finalize.zip'
HEX=re.compile(r'^[0-9a-f]{64}$')
ROW_NAME=re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$')
SCOPE=dict(experimental_bootstrap=True,external_hao_abi_payload_complete=False,
           compatibility_complete=False,boot_validated=False,
           kepler_rendering_validated=False,gmux_switching_validated=False)
LAYERS=('layout','golden-system','group-volumes','golden-finalize','boot-and-esp',
        'hardware','recipes','snapshot','posts','efi-bundle')
GPU_IDS=frozenset(('com.apple.driver.AppleIntelHD4000Graphics',
    'com.apple.driver.AppleIntelFramebufferCapri','com.apple.GeForce',
    'com.apple.nvidia.driver.NVDAGK100Hal','com.apple.nvidia.driver.NVDAResman',
    'com.apple.nvidia.NVDAStartup','com.apple.driver.AppleGraphicsControl',
    'com.apple.driver.AppleMuxControl','com.apple.iokit.IOGraphicsFamily'))
REPAIR_COMMENTS=('Initialize early VM range before reservation',
    'Pass early kernel-map reservation bounds in ascending order',
    'Preserve bootstrap physical-page aliases: code',
    'Preserve bootstrap physical-page aliases: registration')
EXPECTED_FINGERPRINT='1253699343f2b09fc62afa2c00ba74f73b5d0ce063308ae22fd26a1707db20a6'
ATTEMPT='store/tmp/mbp91-image-step12-20261118-210034-843198'
KIT='store/artifacts/mbp91-assembly-kit-26B131-step12-20261118-200221-114333'
PINNED={
    'kit_manifest':'0122be45cfbd8cdabbdcacd28cb9a9f747a1f4469e6de410ca4f762ec8497a83',
    'kit_json':'89baf44265c81769dfb013b06411ea75180bb98ab4a8d04304454557c34d63b4',
    'assembly_json':'48ef9fc41aa5fdcacf32c42f6cb2e38f5355586d66488aa1885bb4bbde15cd43',
    'kit_build':'6dcf922fa2a865c434f0c0b08f7f745385398eab0c57423d794ec09345ed80a5',
    'base_record':'a7d0df10a88051625868cd193fd534532c200002ee670844f66c26ea0252c64a',
    'base_result':'78f0258d9e576e7702d2332c1c89ee3762f780c0b683f14d5d89f6f04a51e155',
    'build':'20294743d1500d1ad9364cba594e97c1f3920de046b983ba32f2a091e38d896a',
    'efi_manifest':'f9385a6e0a098a6570e7709fe8b3473b91998b2b62840c17502a3e231b97c184',
    'binding':'e86fe048eac28e2935230ffb5883c2f8040fbc801706ad01b728ad633a481869',
}


"""Validate supported OCLP bootstrap layouts using already verified file hashes.

The caller verifies the actual payload against its manifest and authenticates the
base manifest before passing these mappings. Config bytes may legitimately differ
after Hao's image-specific additions; bootstrap and OpenCore bytes may not.
"""
import re

_EFI_CORE = 'EFI/OC/OpenCore.efi'
_EFI_CONFIG = 'EFI/OC/config.plist'
_EFI_APPLE = 'System/Library/CoreServices/boot.efi'
_EFI_FALLBACK = 'EFI/BOOT/BOOTx64.efi'


def validate_bootstrap_layout(actual_files, base_files=None):
    """Return layout proof; reject missing, ambiguous, or changed boot binaries.

    FAT path comparisons are case-insensitive. An Apple-layout bootstrap needs a
    matching entry in the verified base manifest. With any base manifest supplied,
    every recognized actual bootstrap and OpenCore must match the same base path
    and digest. The config is required but is not required to equal the base.
    """
    def require(ok, message):
        if not ok:
            raise ValueError('EFI bootstrap: ' + message)

    relevant = {p.casefold() for p in (_EFI_CORE, _EFI_CONFIG, _EFI_APPLE, _EFI_FALLBACK)}

    def index(files, label):
        require(isinstance(files, dict), label + ' file hashes must be an object')
        result = {}
        for path, digest in files.items():
            require(isinstance(path, str), label + ' file path is not a string')
            folded = path.casefold()
            if folded not in relevant:
                continue
            require(folded not in result, label + ' has ambiguous FAT path: ' + path)
            require(isinstance(digest, str) and re.fullmatch('[0-9a-fA-F]{64}', digest) is not None,
                    label + ' has an invalid SHA256: ' + path)
            result[folded] = (path, digest.lower())
        return result

    actual = index(actual_files, 'actual')
    for common in (_EFI_CORE, _EFI_CONFIG):
        require(common.casefold() in actual, 'missing required file: ' + common)
    boot = [actual[path.casefold()] for path in (_EFI_FALLBACK, _EFI_APPLE)
            if path.casefold() in actual]
    require(bool(boot), 'missing supported UEFI or Apple bootstrap')
    has_apple = _EFI_APPLE.casefold() in actual
    has_fallback = _EFI_FALLBACK.casefold() in actual
    require(not has_apple or base_files is not None,
            'Apple-layout bootstrap needs the verified base manifest')
    if base_files is not None:
        base = index(base_files, 'base')
        for path, digest in boot + [actual[_EFI_CORE.casefold()]]:
            require(path.casefold() in base, 'file absent from verified base: ' + path)
            require(digest == base[path.casefold()][1], 'file differs from verified base: ' + path)
    layout = ('apple-and-uefi-fallback' if has_apple and has_fallback
              else 'apple' if has_apple else 'uefi-fallback')
    return {
        'layout': layout,
        'bootstrap_paths': [path for path, _ in boot],
        'bootstrap_sha256': {path: digest for path, digest in boot},
        'opencore_sha256': actual[_EFI_CORE.casefold()][1],
        'base_boot_binaries_preserved': base_files is not None,
    }


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

def fingerprint(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

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

def validate_build_metadata(record, kitrecipe, expectedimagepath, *, actual_image_path=None):
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
    output_image = Path(actual_image_path) if actual_image_path is not None else image
    require(output_image.is_file() and not output_image.is_symlink() and output_image.stat().st_size == config['size_bytes'],
            'Output image missing, linked, or wrong size')
    return dict(image=str(output_image), image_built=True, boot_validated=False, group_uuid=record['group_uuid'])

def validate_final_efi(efi_root, manifest, base_config=None, *, boot_kc, system_kc, binding_report, base_files=None):
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
    bootstrap = validate_bootstrap_layout(actual, base_files)
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
    if base_config is not None:
        for guid, values in base_config.get('NVRAM', {}).get('Add', {}).items():
            base_rev = values.get('revblock', '')
            if isinstance(base_rev, str) and 'gmux' in base_rev.split(','):
                final_rev = config.get('NVRAM', {}).get('Add', {}).get(guid, {}).get('revblock', '')
                require(isinstance(final_rev, str) and 'gmux' in final_rev.split(','),
                        'GMUX revblock from the verified base is missing')
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
    return dict(final_efi_prepared=True, bootstrap=bootstrap, files=len(actual), boot_kc_sha256=kc_hash, binding_mode=binding['mode'],
                gpu_gmux_members=sorted(GPU_IDS), boot_members=len(boot), system_members=len(system),
                boot_validated=False, kepler_rendering_validated=False, gmux_switching_validated=False)

"""Checkpoint and publish one completed image without copying its contents.

The caller validates assembly/EFI, prepares small exports, and hashes the selected
image before commit. save_state() must atomically persist the supplied state dict.
"""
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


class ImagePublicationError(RuntimeError):
    pass


def _publication_require(ok, message):
    if not ok:
        raise ImagePublicationError(message)


def _publication_path(repo, value):
    path = Path(value)
    _publication_require('..' not in path.parts, 'Publication path contains traversal')
    if not path.is_absolute():
        path = repo / path
    _publication_require(path.is_relative_to(repo), 'Publication path leaves the repository')
    for item in (path, *path.parents):
        _publication_require(not item.is_symlink(), 'Publication path contains a symlink: ' + str(item))
        if item == repo:
            break
    _publication_require(path.resolve() == path, 'Publication path is not canonical')
    return path


def _publication_paths(repo, source_image, artifact_root):
    repo = Path(repo)
    _publication_require(repo.is_absolute() and repo.is_dir() and repo.resolve() == repo,
                         'Publication repository must be a real absolute directory')
    source = _publication_path(repo, source_image)
    artifact = _publication_path(repo, artifact_root)
    _publication_require(source.name == 'target.img'
                         and source.parent.parent == repo / 'store/tmp'
                         and re.fullmatch(r'mbp91-image-step12-\d{8}-\d{6}-\d{6}', source.parent.name),
                         'Unexpected completed-image source path')
    _publication_require(artifact.parent == repo / 'store/artifacts'
                         and re.fullmatch(r'mbp91-golden-image-26B131-step12-\d{8}-\d{6}-\d{6}', artifact.name),
                         'Unexpected image artifact path')
    _publication_require(source.parent.is_dir() and artifact.is_dir(), 'Image publication directories are absent')
    destination = _publication_path(repo, artifact / 'GoldenGate-mbp91-26B131.img')
    _publication_require(source.parent.stat().st_dev == artifact.stat().st_dev,
                         'Image publication must stay on the same filesystem')
    return repo, source, artifact, destination


def _publication_record_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _publication_identity(path):
    value = path.lstat()
    _publication_require(stat.S_ISREG(value.st_mode), 'Image publication target is not a regular file')
    return dict(device=value.st_dev, inode=value.st_ino, bytes=value.st_size,
                mtime_ns=value.st_mtime_ns, mode=stat.S_IMODE(value.st_mode))


def _publication_selection(repo, source, artifact, destination, record):
    _publication_require(isinstance(record, dict)
                         and record.get('image') == str(destination.relative_to(repo))
                         and record.get('artifact') == str(artifact.relative_to(repo)),
                         'Image record names another destination')
    _publication_require(isinstance(record.get('image_sha256'), str)
                         and re.fullmatch(r'[0-9a-f]{64}', record['image_sha256']) is not None,
                         'Image record has no verified SHA256')
    size = record.get('image_size_bytes')
    _publication_require(type(size) is int and size > 0, 'Image record size is invalid')
    existing = [path for path in (source, destination) if os.path.lexists(path)]
    _publication_require(len(existing) == 1, 'Expected exactly one source or published image')
    selected = existing[0]
    identity = _publication_identity(selected)
    _publication_require(identity['bytes'] == size and identity['device'] == artifact.stat().st_dev,
                         'Image size or filesystem differs from its publication record')
    return selected, identity


def pending_image_publication(state, repo):
    """Return the one image to rehash on a retry; never moves or writes anything."""
    _publication_require(not state.get('image'), 'Pending image publication conflicts with a committed image')
    pending = state.get('pending_image_publication')
    _publication_require(isinstance(pending, dict) and pending.get('schema') == 1,
                         'Image publication checkpoint is absent or invalid')
    repo, source, artifact, destination = _publication_paths(repo, pending['source'], pending['artifact'])
    record = pending['record']
    digest = _publication_record_digest(record)
    _publication_require(digest == pending.get('record_sha256'), 'Pending image record was changed')
    _publication_require(state.get('assembly_attempt') == str(source.parent.relative_to(repo)),
                         'Pending publication belongs to another assembly attempt')
    selected, identity = _publication_selection(repo, source, artifact, destination, record)
    _publication_require(identity == pending.get('file_identity'), 'Pending image identity or bytes changed')
    return dict(path=selected, record=copy.deepcopy(record), record_sha256=digest,
                source=source, destination=destination, artifact=artifact)


def prepare_image_publication(state, save_state, repo, source_image, artifact_root, record):
    """Persist the source/destination/record checkpoint before any rename.

    An existing checkpoint must agree exactly. A new checkpoint starts only from
    the source; destination-only is accepted exclusively through a saved checkpoint.
    """
    repo, source, artifact, destination = _publication_paths(repo, source_image, artifact_root)
    selected, identity = _publication_selection(repo, source, artifact, destination, record)
    candidate = dict(schema=1, source=str(source.relative_to(repo)), artifact=str(artifact.relative_to(repo)),
                     record=copy.deepcopy(record), record_sha256=_publication_record_digest(record),
                     file_identity=identity)
    _publication_require(not state.get('image'), 'A completed image is already recorded')
    _publication_require(state.get('assembly_attempt') == str(source.parent.relative_to(repo)),
                         'Image publication belongs to another assembly attempt')
    old = state.get('pending_image_publication')
    if old is not None:
        _publication_require(old == candidate, 'Another image publication is pending')
        return pending_image_publication(state, repo)
    _publication_require(selected == source, 'Uncheckpointed destination image cannot be adopted')
    state['pending_image_publication'] = candidate
    try:
        save_state()
    except BaseException:
        state.pop('pending_image_publication', None)
        raise
    return pending_image_publication(state, repo)


def _publication_rename_exclusive(source, destination):
    """Atomic no-replacement rename; unsupported platforms fail without mutation."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        # Apple XNU bsd/sys/stdio.h: RENAME_EXCL = 0x00000004.
        function = getattr(libc, 'renamex_np', None)
        _publication_require(function is not None, 'Exclusive image rename is unavailable')
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(os.fsencode(source), os.fsencode(destination), 0x00000004)
    elif sys.platform.startswith('linux'):
        # Linux fixture execution; RENAME_NOREPLACE = 1, AT_FDCWD = -100.
        function = getattr(libc, 'renameat2', None)
        _publication_require(function is not None, 'Exclusive image rename is unavailable')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise ImagePublicationError('Exclusive image rename is unavailable')
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))


def commit_image_publication(state, save_state, repo, verified_record_sha256):
    """Publish only after the caller revalidated/hashed this exact record's image."""
    selected = pending_image_publication(state, repo)
    _publication_require(verified_record_sha256 == selected['record_sha256'],
                         'Caller has not verified this exact pending image record')
    before = copy.deepcopy(state)
    if selected['path'] == selected['source']:
        _publication_rename_exclusive(selected['source'], selected['destination'])
    after = pending_image_publication(state, repo)
    _publication_require(after['path'] == selected['destination'], 'Image rename was not completed')
    state['image'] = copy.deepcopy(selected['record'])
    state.pop('assembly_attempt', None)
    state.pop('pending_image_publication', None)
    try:
        save_state()
    except BaseException:
        state.clear(); state.update(before)
        raise
    return copy.deepcopy(selected['record'])



def checked_path(repo, relative, *, regular=False):
    """Confine every component to this workspace; reject symlinks before use."""
    relative = relpath(relative)
    current = Path(repo)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise Stop('Symlink neasteptat: ' + str(current))
    if not current.resolve().is_relative_to(Path(repo).resolve()):
        raise Stop('Cale externa: ' + str(current))
    if regular and not current.is_file():
        raise Stop('Fisier lipsa: ' + str(current))
    return current


def check_pinned(path, expected):
    if not path.is_file() or path.is_symlink() or sha(path) != expected:
        raise Stop('Fisier diferit de raportul verificat: ' + str(path))


def file_identity(path):
    st = Path(path).lstat()
    if not stat.S_ISREG(st.st_mode):
        raise Stop('Imaginea nu este un fisier obisnuit: ' + str(path))
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def image_hash(path):
    before = file_identity(path)
    total = before[2]
    digest = hashlib.sha256()
    done = 0
    pulse = time.monotonic()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(16 << 20), b''):
            digest.update(data)
            done += len(data)
            now = time.monotonic()
            if now - pulse >= 10:
                print('    SHA256 imagine: %.1f%% (%s din %s).' %
                      (100 * done / total, space_gb(done), space_gb(total)), flush=True)
                pulse = now
    if done != total or file_identity(path) != before:
        raise Stop('Imaginea s-a schimbat in timpul citirii SHA256')
    print('    SHA256 imagine: 100%; citire integrala incheiata.', flush=True)
    return dict(sha256=digest.hexdigest(), bytes=done), before


def mount_paths(text):
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if ' on ' not in line or ' (' not in line or not line.endswith(')'):
            raise Stop('Lista punctelor de montare nu poate fi interpretata')
        path = line.split(' on ', 1)[1].rsplit(' (', 1)[0]
        path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), path)
        if not path.startswith('/'):
            raise Stop('Punct de montare neasteptat')
        result.append(Path(path).resolve())
    if not result:
        raise Stop('Lista punctelor de montare este goala')
    return result


class Job:
    def __init__(self, repo):
        self.repo = repo
        self.local = repo / 'local/mbp91'
        self.stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.work = repo / 'store/tmp' / ('mbp91-step12-finalize-' + self.stamp)
        self.work.mkdir(parents=True)
        self.statefile = self.local / 'step12-state.json'
        self.result = self.local / 'step12-result.json'
        self.logpath = self.local / 'step12-build.log'
        self.state = load(self.statefile)
        for path in (self.statefile, self.result, self.logpath):
            if path.is_file():
                shutil.copy2(path, self.work / ('previous-' + path.name))
        self.log = self.logpath.open('w', buffering=1)
        self.report = dict(schema=VERSION, model=MODEL, golden_build=GOLDEN,
            donor_build=DONOR, mode='finalize', commands=[], errors=[],
            kit_prepared=False, image_built=False, final_efi_prepared=False,
            step_complete=False, image_rebuilt=False, **SCOPE)
        self.attempt = checked_path(repo, ATTEMPT)
        self.image_local = self.attempt
        self.kit = checked_path(repo, KIT)
        self.output = None

    def save_state(self, state=None):
        save(self.statefile, self.state if state is None else state)

    def save(self):
        save(self.result, self.report)
        self.save_state(self.state)

    def command(self, args, timeout=60):
        args = list(map(str, args))
        self.log.write('\n$ ' + shlex.join(args) + '\n')
        start = time.monotonic()
        result = subprocess.run(args, cwd=self.repo, capture_output=True,
                                text=True, timeout=timeout)
        self.log.write(result.stdout)
        self.log.write(result.stderr)
        self.report['commands'].append(dict(argv=args, returncode=result.returncode,
            elapsed_s=round(time.monotonic() - start, 2)))
        if result.returncode:
            raise Stop('%s: cod %d; %s' % (args[0], result.returncode,
                       (result.stderr or result.stdout)[-1800:]))
        return result.stdout

    def setup(self):
        if self.state.get('fingerprint') != EXPECTED_FINGERPRINT:
            raise Stop('Starea locala nu corespunde imaginii verificate in arhiva trimisa')
        old = self.state.get('kit', {})
        if old.get('path') != KIT or old.get('manifest_sha256') != PINNED['kit_manifest']:
            raise Stop('Kitul inregistrat nu corespunde imaginii asamblate')
        for name, pin in (('step12-manifest.json', 'kit_manifest'), ('kit.json', 'kit_json'),
                          ('assembly.json', 'assembly_json'), ('step12-build.json', 'kit_build')):
            check_pinned(checked_path(self.repo, KIT + '/' + name, regular=True), PINNED[pin])
        self.recipe = load(self.kit / 'assembly.json')
        if self.recipe != old.get('recipe'):
            raise Stop('Reteta kitului difera de cea inregistrata')
        check_pinned(self.local / 'step4-result.json', PINNED['base_result'])
        check_pinned(self.local / 'step4-base-efi-record.json', PINNED['base_record'])
        r4 = load(self.local / 'step4-result.json')
        self.base_record = load(self.local / 'step4-base-efi-record.json')
        self.base = checked_path(self.repo, r4['efi_path'])
        for relative, expected in self.base_record['files'].items():
            check_pinned(checked_path(self.repo, r4['efi_path'] + '/' + relative, regular=True), expected)
        self.base_config = plistlib.loads((self.base / 'EFI/OC/config.plist').read_bytes())
        self.report.update(kit_prepared=True, kit=old, fingerprint=EXPECTED_FINGERPRINT,
            assembly_work=ATTEMPT, script_sha256=sha(Path(__file__)),
            base_efi_record_sha256=PINNED['base_record'], kit_verified_from_existing_receipt=True)
        self.save()

    def assert_detached(self, image):
        attached = plistlib.loads(self.command(['/usr/bin/hdiutil', 'info', '-plist']).encode())
        if not isinstance(attached, dict) or not isinstance(attached.get('images'), list):
            raise Stop('Starea imaginilor atasate nu poate fi verificata')
        scopes = [self.attempt]
        if self.output is not None:
            scopes.append(self.output)
        def scoped(path):
            path = Path(path).resolve()
            return any(path == root or path.is_relative_to(root) for root in scopes)
        for entry in attached['images']:
            source = entry.get('image-path')
            if source and (scoped(source) or
                    (Path(source).exists() and image.exists() and os.path.samefile(source, image))):
                raise Stop('Imaginea este inca atasata: ' + source)
            for entity in entry.get('system-entities', []):
                point = entity.get('mount-point')
                if point and scoped(point):
                    raise Stop('Un volum al imaginii este inca montat: ' + point)
        if any(scoped(p) for p in mount_paths(self.command(['/sbin/mount']))):
            raise Stop('Exista un volum montat in directorul imaginii')
        self.report['live_detached_check'] = True

    def validate_completed(self, image):
        root = self.attempt / 'work'
        for relative, pin in (('build.json', 'build'), ('boot-efi/manifest.json', 'efi_manifest'),
                              ('post/hao-opencore/kc-binder.json', 'binding')):
            check_pinned(checked_path(self.repo, ATTEMPT + '/work/' + relative, regular=True), PINNED[pin])
        build = load(root / 'build.json')
        self.report['image_structure'] = validate_build_metadata(
            build, self.recipe, self.attempt / 'target.img', actual_image_path=image)
        self.report.update(image_built=True, assembler_status=build['status'],
            assembly_steps=build['steps'], group_uuid=build['group_uuid'])
        self.assert_detached(image)
        self.manifest = load(root / 'boot-efi/manifest.json')
        self.binding = load(root / 'post/hao-opencore/kc-binder.json')
        for rel in ('boot-efi/payload', 'kc/BootKernelExtensions.kc', 'kc/SystemKernelExtensions.kc'):
            checked_path(self.repo, ATTEMPT + '/work/' + rel)
        self.efi_checks = validate_final_efi(root / 'boot-efi', self.manifest, self.base_config,
            base_files=self.base_record['files'], boot_kc=root / 'kc/BootKernelExtensions.kc',
            system_kc=root / 'kc/SystemKernelExtensions.kc', binding_report=self.binding)
        self.report['final_efi_checks'] = self.efi_checks
        print('    EFI Apple: System/Library/CoreServices/boot.efi; identic cu baza verificata.', flush=True)
        print('    Intel + NVIDIA + AppleMuxControl: prezente in colectii; legatura KC/EFI verificata.', flush=True)
        self.save()

    def ocvalidate(self):
        selected = []
        for folder in (self.repo / 'pipeline/inputs/golden' / GOLDEN,
                       self.repo / 'pipeline/inputs' / DONOR,
                       self.repo / 'pipeline/inputs/common'):
            path = folder / 'opencore_release'
            if path.is_file():
                selected.append(path)
        if len(selected) != 1:
            raise Stop('Intrarea opencore_release lipseste sau este ambigua')
        checksum, archive, _ = parse_row(selected[0].read_text(), self.repo, 'opencore_release')
        if checksum != self.base_record['opencore_archive_sha256']:
            raise Stop('Arhiva OpenCore difera de versiunea verificata la pasul 4')
        check_pinned(archive, checksum)
        with zipfile.ZipFile(archive) as source:
            names = [n for n in source.namelist() if n.endswith('Utilities/ocvalidate/ocvalidate')]
            if len(names) != 1:
                raise Stop('ocvalidate macOS lipseste sau este ambiguu')
            tool = self.work / 'ocvalidate'
            tool.write_bytes(source.read(names[0]))
            tool.chmod(0o755)
        self.command([tool, self.attempt / 'work/boot-efi/payload/EFI/OC/config.plist'])
        self.report.update(ocvalidate_ok=True, final_efi_prepared=True)
        print('    ocvalidate: OK.', flush=True)
        self.save()

    def check_export(self, record):
        if record.get('image_sha256') != record.get('sha256') or record.get('image_size_bytes') != record.get('bytes'):
            raise Stop('Campuri SHA256 sau dimensiune contradictorii in artefact')
        output = checked_path(self.repo, record['artifact'])
        self.output = output
        if Path(record['image']) != Path(record['artifact']) / 'GoldenGate-mbp91-26B131.img':
            raise Stop('Calea imaginii finale difera de artefact')
        for relative, key in (('boot-efi.zip', 'efi_zip_sha256'),
                              ('boot-efi/manifest.json', 'manifest_sha256'),
                              ('kc-binder.json', 'binding_sha256'),
                              ('assembly-build.json', 'assembly_record_sha256')):
            check_pinned(checked_path(self.repo, record['artifact'] + '/' + relative, regular=True), record[key])
        for key, pin in (('manifest_sha256','efi_manifest'), ('binding_sha256','binding'),
                         ('assembly_record_sha256','build')):
            if record[key] != PINNED[pin]:
                raise Stop('Metadatele publicate apartin altei asamblari')
        manifest = load(output / 'boot-efi/manifest.json')
        payload = checked_path(self.repo, record['artifact'] + '/boot-efi/payload')
        paths = list(payload.rglob('*'))
        if any(p.is_symlink() for p in paths):
            raise Stop('Symlink in EFI-ul publicat')
        actual = {p.relative_to(payload).as_posix(): sha(p) for p in paths if p.is_file()}
        if actual != manifest['files']:
            raise Stop('EFI-ul publicat difera de manifest')
        validate_bootstrap_layout(actual, self.base_record['files'])
        if load(output / 'build.json') != record:
            raise Stop('Inregistrarea artefactului difera de checkpoint')
        if record.get('scope') != SCOPE or record.get('final_efi_checks') != self.efi_checks:
            raise Stop('Validarile sau domeniul artefactului au fost schimbate')

    def publish(self, image, hashed):
        root = self.attempt / 'work'
        output = self.repo / 'store/artifacts' / ('mbp91-golden-image-26B131-step12-' + self.stamp)
        # Only the small EFI and JSON files are copied. The raw image is renamed once.
        byte_count = sum(p.stat().st_size for p in (root / 'boot-efi').rglob('*') if p.is_file())
        needed = 2 * byte_count + (64 << 20)
        if shutil.disk_usage(output.parent).free < needed:
            raise Stop('Spatiu insuficient pentru exportul EFI: ' + space_gb(needed))
        output.mkdir()
        self.output = output
        shutil.copytree(root / 'boot-efi', output / 'boot-efi', symlinks=False)
        for source, name in ((root / 'build.json', 'assembly-build.json'),
                             (root / 'post/hao-opencore/kc-binder.json', 'kc-binder.json'),
                             (self.kit / 'kit.json', 'kit.json')):
            shutil.copy2(source, output / name)
        save(output / 'LOCAL-SCOPE.json', dict(SCOPE, image_built=True, final_efi_prepared=True,
             built_from_kit=KIT, source_attempt=ATTEMPT,
             validation='Static assembly, collection binding, EFI validation and complete image SHA256'))
        archive = output / 'boot-efi.zip'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as target:
            for path in sorted((output / 'boot-efi').rglob('*')):
                if path.is_file():
                    target.write(path, path.relative_to(output / 'boot-efi').as_posix())
        destination = output / 'GoldenGate-mbp91-26B131.img'
        record = dict(hashed, image_sha256=hashed['sha256'], image_size_bytes=hashed['bytes'],
            image=str(destination.relative_to(self.repo)),
            artifact=str(output.relative_to(self.repo)), efi_zip_sha256=sha(archive),
            manifest_sha256=sha(output / 'boot-efi/manifest.json'),
            binding_sha256=sha(output / 'kc-binder.json'),
            assembly_record_sha256=sha(output / 'assembly-build.json'),
            final_efi_checks=self.efi_checks, scope=dict(SCOPE), source_attempt=ATTEMPT)
        save(output / 'build.json', record)
        self.check_export(record)
        self.assert_detached(image)
        if file_identity(image) != self.hashed_identity:
            raise Stop('Imaginea a fost schimbata dupa calculul SHA256')
        prepared = prepare_image_publication(self.state, self.save_state, self.repo, image, output, record)
        result = commit_image_publication(self.state, self.save_state, self.repo, prepared['record_sha256'])
        self.completed(result if isinstance(result, dict) and 'image' in result else record)

    def completed(self, record):
        self.report.update(image=record, step_complete=True, image_built=True,
                           final_efi_prepared=True, image_artifact=record['artifact'])
        self.save()

    def run(self):
        print('1/4 Verific inregistrarea imaginii asamblate si EFI-ul de baza.', flush=True)
        self.setup()
        pending = self.state.get('pending_image_publication')
        existing = self.state.get('image')
        if pending and existing:
            raise Stop('Stare ambigua: imagine publicata si finalizare in asteptare')
        selection = pending_image_publication(self.state, self.repo) if pending else None
        if selection:
            image = Path(selection['path'])
            record = selection['record']
            self.output = checked_path(self.repo, record['artifact'])
            print('    Reiau finalizarea inregistrata dupa o intrerupere.', flush=True)
        elif existing:
            record = existing
            image = checked_path(self.repo, record['image'], regular=True)
            self.output = checked_path(self.repo, record['artifact'])
            print('    Imagine deja finalizata: verific rezultatul existent.', flush=True)
        else:
            if self.state.get('assembly_attempt') != ATTEMPT:
                raise Stop('Incercarea inregistrata nu este imaginea finalizata din arhiva trimisa')
            image = checked_path(self.repo, ATTEMPT + '/target.img', regular=True)
            record = None
        print('2/4 Verific structura Apple a EFI-ului, colectiile kernel si ocvalidate.', flush=True)
        self.validate_completed(image)
        self.ocvalidate()
        if record:
            self.check_export(record)
        print('3/4 Calculez SHA256 pentru imaginea existenta de 80 GiB; progresul apare la 10 secunde.', flush=True)
        hashed, self.hashed_identity = image_hash(image)
        if record and (hashed['sha256'] != record['sha256'] or hashed['bytes'] != record['bytes']):
            raise Stop('Imaginea difera de SHA256 inregistrat la finalizare')
        print('4/4 Salvez imaginea, EFI-ul exportat si rapoartele finale.', flush=True)
        if selection:
            self.assert_detached(image)
            if file_identity(image) != self.hashed_identity:
                raise Stop('Imaginea s-a schimbat dupa verificare')
            commit_image_publication(self.state, self.save_state, self.repo, selection['record_sha256'])
            self.completed(record)
        elif record:
            self.report['image_reused'] = True
            self.completed(record)
        else:
            self.publish(image, hashed)

    def finish(self):
        self.report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save()
        self.log.close()
        archive = Path.home() / 'Desktop' / ARCHIVE_NAME
        temporary = archive.with_suffix('.partial.zip')
        candidates = [self.result, self.statefile, self.logpath,
            self.attempt / 'work/build.json', self.attempt / 'work/boot-efi/manifest.json',
            self.attempt / 'work/boot-efi/payload/EFI/OC/config.plist',
            self.attempt / 'work/post/hao-opencore/kc-binder.json']
        if self.output:
            candidates += [self.output / name for name in ('build.json','assembly-build.json',
                'kc-binder.json','LOCAL-SCOPE.json','boot-efi/manifest.json','boot-efi/payload/EFI/OC/config.plist')]
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as target:
            for path in candidates:
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= (8 << 20):
                    target.write(path, path.relative_to(self.repo).as_posix())
            target.write(Path(__file__).resolve(), Path(__file__).name)
            target.writestr('READ-ME.txt', 'Finalization receipts only. The raw image, Apple drivers and EFI binaries are not included.\n')
        os.replace(temporary, archive)
        print('\nKit Intel pentru MacBookPro9,1: ' + ('DA' if self.report['kit_prepared'] else 'NU'))
        print('Imagine Golden Gate asamblata: ' + ('DA' if self.report['image_built'] else 'NU'))
        print('EFI final legat si verificat: ' + ('DA' if self.report['final_efi_prepared'] else 'NU'))
        print('Pasul 12 finalizat: ' + ('DA' if self.report['step_complete'] else 'NU'))
        if self.report.get('image'):
            record = self.report['image']
            print('Imagine: ' + str(self.repo / record['image']))
            print('EFI exportat: ' + str(self.repo / record['artifact'] / 'boot-efi.zip'))
            print('SHA256 imagine: ' + record['sha256'])
        print('Payload Hao complet / NVIDIA-GMUX functional / boot validat: NU; netestate sau incomplete.')
        print('Arhiva MICA de trimis: ' + str(archive))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    if sys.platform != 'darwin' or platform.machine() != 'x86_64' or os.geteuid() == 0:
        print('OPRIT: ruleaza pe iMac-ul Intel ca utilizator normal, cu comanda indicata.'); return 1
    repo = args.repo.expanduser().resolve()
    if not (repo / 'local/mbp91/step12-state.json').is_file():
        print('OPRIT: ruleaza din Desktop/hao-patcher-mbp91, unde se afla imaginea asamblata.'); return 1
    os.umask(0o022)
    with (repo / 'local/mbp91/step12.running.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('OPRIT: pasul 12 ruleaza deja.'); return 1
        job = Job(repo)
        try:
            job.run()
        except (Exception, SystemExit, KeyboardInterrupt) as error:
            message = str(error) or type(error).__name__
            job.report['errors'].append(dict(error=message, traceback=traceback.format_exc()))
            job.report['step_complete'] = False
            job.log.write(traceback.format_exc())
            print('OPRIT: ' + message, flush=True)
        finally:
            job.finish()
        return 0 if job.report['step_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
