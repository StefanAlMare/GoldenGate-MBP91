#!/usr/bin/env python3
"""Golden Gate / MacBookPro9,1: write the verified image to the selected diskNECONFIGURAT.

Run from ~/Desktop/hao-patcher-mbp91 as the normal user:
    python3.14 -I ~/Downloads/HAO-mbp91-step13.py

The selected external physical256.1GB disk is overwritten in full-image scope.
The script checks identity/backing devices, hashes source, copies all80GiB,
flushes and reads back all bytes, relocates GPT, grows the copied APFS container,
verifies the matching Apple-layout EFI and ejects the completed disk.
No build or download is performed. A first hardware boot remains untested.
"""
from __future__ import annotations
import argparse
import codecs
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import select
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

VERSION='mbp91-step13-verified-external-write-v1'
MODEL='MacBookPro9,1'
BUILD='26B131'
TARGET='/dev/diskNECONFIGURAT'
RAW_TARGET='/dev/rdiskNECONFIGURAT'
IMAGE_BYTES=85_899_345_920
IMAGE_SHA='52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35'
ARTIFACT_REL='store/artifacts/mbp91-golden-image-26B131-step12-20261118-215319-854607'
IMAGE_REL=ARTIFACT_REL+'/GoldenGate-mbp91-26B131.img'
BUILD_RECORD_SHA='c904edb848c89f0080a3b30243f38b80224cebefe543fcc4df9858b6f68fe688'
EFI_MANIFEST_SHA='f9385a6e0a098a6570e7709fe8b3473b91998b2b62840c17502a3e231b97c184'
GROUP_UUID='00000000-0000-4000-8000-000000000002'



"""Read-only GPT validation and pure relocation plans for the completed Hao image.

The five-write relocation follows pinned Hao tools/ssdimg/gpt.py at
6bd75aab112d1078acd8e75180eb510672461365. This module performs no writes and runs
no disk commands. The caller copies/verifies the complete raw image before
applying the returned GPT writes, verifies them, then may grow the APFS slice.
"""
import re
import struct
import uuid
import zlib

GPT_SECTOR = 512
GPT_SOURCE_BYTES = 85_899_345_920
GPT_HEADER_FORMAT = '<8sIIIIQQQQ16sQIII'
GPT_HEADER_BYTES = struct.calcsize(GPT_HEADER_FORMAT)
GPT_EFI_TYPE = 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B'
GPT_APFS_TYPE = '7C3457EF-0000-11AA-AA11-00306543ECAC'


class GPTValidationError(ValueError):
    pass


def _gpt_require(condition, message):
    if not condition:
        raise GPTValidationError(message)


def _gpt_round(value, unit=GPT_SECTOR):
    return (value + unit - 1) // unit * unit


def _gpt_read(read_at, offset, length, total_bytes):
    _gpt_require(type(offset) is int and type(length) is int and offset >= 0
                 and length > 0 and offset + length <= total_bytes,
                 'GPT read extends outside the selected disk/image')
    value = read_at(offset, length)
    _gpt_require(isinstance(value, (bytes, bytearray)) and len(value) == length,
                 'Short GPT read at byte %d' % offset)
    return bytes(value)


def _gpt_header(read_at, lba, total_bytes):
    raw = _gpt_read(read_at, lba * GPT_SECTOR, GPT_SECTOR, total_bytes)
    values = struct.unpack(GPT_HEADER_FORMAT, raw[:GPT_HEADER_BYTES])
    names = ('signature', 'revision', 'header_size', 'header_crc', 'reserved',
             'my_lba', 'alternate_lba', 'first_usable', 'last_usable', 'disk_guid_raw',
             'entries_lba', 'entry_count', 'entry_size', 'entries_crc')
    row = dict(zip(names, values))
    _gpt_require(row['signature'] == b'EFI PART' and row['revision'] == 0x00010000,
                 'Invalid GPT signature/revision at LBA %d' % lba)
    _gpt_require(GPT_HEADER_BYTES <= row['header_size'] <= GPT_SECTOR and row['reserved'] == 0,
                 'Invalid GPT header size/reserved field')
    check = bytearray(raw[:row['header_size']])
    check[16:20] = bytes(4)
    _gpt_require(zlib.crc32(check) & 0xffffffff == row['header_crc'],
                 'GPT header CRC mismatch at LBA %d' % lba)
    _gpt_require(row['my_lba'] == lba, 'GPT header names another LBA')
    _gpt_require(2 <= row['entry_count'] <= 32768
                 and 128 <= row['entry_size'] <= 4096 and row['entry_size'] % 8 == 0,
                 'Invalid GPT entry array dimensions')
    count_bytes = row['entry_count'] * row['entry_size']
    _gpt_require(count_bytes <= 16 << 20, 'GPT entry array is unexpectedly large')
    padded = _gpt_round(count_bytes)
    entries_padded = _gpt_read(read_at, row['entries_lba'] * GPT_SECTOR, padded, total_bytes)
    entries = entries_padded[:count_bytes]
    _gpt_require(zlib.crc32(entries) & 0xffffffff == row['entries_crc'],
                 'GPT entry array CRC mismatch at LBA %d' % row['entries_lba'])
    row.update(raw=raw, entries=entries, entries_sectors=padded // GPT_SECTOR)
    return row


class GPTLayout:
    def __init__(self, total_bytes, mbr, primary, backup, partitions):
        self.total_bytes = total_bytes
        self.sector_size = GPT_SECTOR
        self.mbr = mbr
        self.primary = primary
        self.backup = backup
        self.partitions = partitions

    def report(self):
        return {
            'size_bytes': self.total_bytes, 'sector_size': self.sector_size,
            'disk_guid': str(uuid.UUID(bytes_le=self.primary['disk_guid_raw'])).upper(),
            'primary_header_lba': self.primary['my_lba'],
            'backup_header_lba': self.backup['my_lba'],
            'first_usable_lba': self.primary['first_usable'],
            'last_usable_lba': self.primary['last_usable'],
            'primary_header_crc32': self.primary['header_crc'],
            'backup_header_crc32': self.backup['header_crc'],
            'partition_array_crc32': self.primary['entries_crc'],
            'partition_array_bytes': len(self.primary['entries']),
            'partitions': [dict(row) for row in self.partitions],
        }


def parse_gpt_layout(read_at, total_bytes, sector_size=GPT_SECTOR):
    """Validate both GPT copies and the protective MBR through bounded reads.

    ``read_at(offset, length)`` must return exactly those bytes. This generic
    parser permits tiny fixtures; validate_source_gpt applies the real80GiB gate.
    """
    _gpt_require(type(total_bytes) is int and total_bytes >= 68 * GPT_SECTOR
                 and total_bytes % GPT_SECTOR == 0, 'Invalid GPT disk/image size')
    _gpt_require(type(sector_size) is int and sector_size == GPT_SECTOR,
                 'The image and target must both use 512-byte logical sectors')
    sectors = total_bytes // GPT_SECTOR
    mbr = _gpt_read(read_at, 0, GPT_SECTOR, total_bytes)
    _gpt_require(mbr[510:512] == b'\x55\xaa', 'Protective MBR signature missing')
    _gpt_require(mbr[450] == 0xee and struct.unpack_from('<I', mbr, 454)[0] == 1,
                 'Expected a protective MBR beginning at LBA1')
    _gpt_require(struct.unpack_from('<I', mbr, 458)[0] == min(sectors - 1, 0xffffffff),
                 'Protective MBR size differs from disk/image size')
    _gpt_require(mbr[462:510] == bytes(48), 'Unexpected hybrid MBR entries')
    primary = _gpt_header(read_at, 1, total_bytes)
    backup = _gpt_header(read_at, sectors - 1, total_bytes)
    _gpt_require(primary['alternate_lba'] == sectors - 1 and backup['alternate_lba'] == 1,
                 'Primary/backup GPT locations disagree')
    for key in ('revision', 'header_size', 'first_usable', 'last_usable',
                'disk_guid_raw', 'entry_count', 'entry_size', 'entries_crc', 'entries'):
        _gpt_require(primary[key] == backup[key], 'GPT copies disagree: ' + key)
    _gpt_require(primary['disk_guid_raw'] != bytes(16), 'GPT disk UUID is zero')
    _gpt_require(primary['entries_lba'] >= 2
                 and primary['entries_lba'] + primary['entries_sectors'] <= primary['first_usable']
                 <= primary['last_usable'] < backup['entries_lba']
                 and backup['entries_lba'] + backup['entries_sectors'] == sectors - 1,
                 'GPT usable ranges overlap header/partition tables')
    partitions = []
    guids = set()
    for index in range(primary['entry_count']):
        at = index * primary['entry_size']
        raw = primary['entries'][at:at + primary['entry_size']]
        if raw[:16] == bytes(16):
            continue
        kind, guid, first, last, attrs, name = struct.unpack('<16s16sQQQ72s', raw[:128])
        _gpt_require(guid != bytes(16) and guid not in guids, 'Invalid/duplicate GPT partition UUID')
        guids.add(guid)
        _gpt_require(primary['first_usable'] <= first <= last <= primary['last_usable'],
                     'GPT partition is outside usable disk space')
        partitions.append(dict(index=index + 1, type_guid=str(uuid.UUID(bytes_le=kind)).upper(),
            partition_guid=str(uuid.UUID(bytes_le=guid)).upper(), first_lba=first, last_lba=last,
            size_bytes=(last - first + 1) * GPT_SECTOR, attributes=attrs,
            name=name.decode('utf-16-le').split('\0', 1)[0]))
    ordered = sorted(partitions, key=lambda p: p['first_lba'])
    _gpt_require(all(a['last_lba'] < b['first_lba'] for a, b in zip(ordered, ordered[1:])),
                 'GPT partitions overlap')
    _gpt_require(len(partitions) == 2
                 and {p['type_guid'] for p in partitions} == {GPT_EFI_TYPE, GPT_APFS_TYPE},
                 'Expected exactly one EFI and one APFS partition')
    return GPTLayout(total_bytes, mbr, primary, backup, partitions)


def validate_source_gpt(read_at, source_bytes):
    _gpt_require(type(source_bytes) is int and source_bytes == GPT_SOURCE_BYTES,
                 'Expected the verified80GiB Golden Gate image')
    return parse_gpt_layout(read_at, source_bytes, GPT_SECTOR)


def validate_raw_restore(source_sha256, readback_sha256, source_bytes, readback_bytes):
    """Gate relocation on the caller's complete raw-prefix readback proof."""
    _gpt_require(isinstance(source_sha256, str)
                 and re.fullmatch('[0-9a-f]{64}', source_sha256) is not None,
                 'Invalid verified source SHA256')
    _gpt_require(type(source_bytes) is int and source_bytes == GPT_SOURCE_BYTES
                 and type(readback_bytes) is int and readback_bytes == source_bytes,
                 'Raw restore readback did not cover the complete80GiB image')
    _gpt_require(readback_sha256 == source_sha256, 'Raw disk readback SHA256 differs from source')
    return {'verified': True, 'bytes': source_bytes, 'sha256': source_sha256,
            'phase': 'complete raw image before GPT relocation or APFS growth'}


def _gpt_relocated_header(source, my_lba, alternate_lba, entries_lba, last_usable):
    # Preserve any header extensions/padding; change only the same core fields as Hao.
    raw = bytearray(source['raw'])
    struct.pack_into('<I', raw, 16, 0)
    struct.pack_into('<Q', raw, 24, my_lba)
    struct.pack_into('<Q', raw, 32, alternate_lba)
    struct.pack_into('<Q', raw, 48, last_usable)
    struct.pack_into('<Q', raw, 72, entries_lba)
    struct.pack_into('<I', raw, 16, zlib.crc32(raw[:source['header_size']]) & 0xffffffff)
    return bytes(raw)


def plan_gpt_relocation(layout, target_bytes, target_sector_size):
    """Return five(offset,bytes)writes; no file/device is opened or modified."""
    _gpt_require(isinstance(layout, GPTLayout), 'A validated source GPT is required')
    _gpt_require(type(target_sector_size) is int and target_sector_size == GPT_SECTOR,
                 'Target logical sector size differs from the512-byte image')
    _gpt_require(type(target_bytes) is int and target_bytes >= layout.total_bytes
                 and target_bytes % GPT_SECTOR == 0, 'Target is smaller than image or has partial sectors')
    total = target_bytes // GPT_SECTOR
    last = total - 1
    backup_entries = last - layout.primary['entries_sectors']
    last_usable = backup_entries - 1
    _gpt_require(max(p['last_lba'] for p in layout.partitions) <= last_usable,
                 'Image partitions do not fit the target GPT')
    entries = layout.primary['entries'].ljust(layout.primary['entries_sectors'] * GPT_SECTOR, b'\0')
    mbr = bytearray(layout.mbr)
    struct.pack_into('<I', mbr, 458, min(total - 1, 0xffffffff))
    return [
        (0, bytes(mbr)),
        (GPT_SECTOR, _gpt_relocated_header(layout.primary, 1, last,
                                         layout.primary['entries_lba'], last_usable)),
        (layout.primary['entries_lba'] * GPT_SECTOR, entries),
        (backup_entries * GPT_SECTOR, entries),
        (last * GPT_SECTOR, _gpt_relocated_header(layout.backup, last, 1,
                                                backup_entries, last_usable)),
    ]


def validate_relocated_gpt(read_at, target_bytes, source_layout):
    """Validate actual relocated bytes before APFS growth; preserve all partition IDs."""
    plan = plan_gpt_relocation(source_layout, target_bytes, GPT_SECTOR)
    for offset, expected in plan:
        _gpt_require(_gpt_read(read_at, offset, len(expected), target_bytes) == expected,
                     'Relocated GPT write differs at byte%d' % offset)
    actual = parse_gpt_layout(read_at, target_bytes)
    _gpt_require(actual.primary['entries'] == source_layout.primary['entries']
                 and actual.primary['disk_guid_raw'] == source_layout.primary['disk_guid_raw'],
                 'Relocation changed partition entries or disk UUID')
    return {'verified': True, 'gpt': actual.report(), 'partition_entries_preserved': True,
            'disk_guid_preserved': True, 'writes_verified': len(plan)}


def apfs_growth_plan(layout, whole_disk):
    """Return the exact physical-store command; never selects a synthesized disk."""
    _gpt_require(isinstance(layout, GPTLayout), 'A validated source GPT is required')
    _gpt_require(isinstance(whole_disk, str) and re.fullmatch(r'(?:/dev/)?disk[0-9]+', whole_disk),
                 'APFS growth requires an explicitly selected whole physical disk')
    disk = whole_disk.removeprefix('/dev/')
    part = next(p for p in layout.partitions if p['type_guid'] == GPT_APFS_TYPE)
    device = disk + 's' + str(part['index'])
    return {'whole_disk': disk, 'apfs_partition': device,
            'partition_guid': part['partition_guid'], 'source_container_bytes': part['size_bytes'],
            'argv': ['/usr/sbin/diskutil', 'apfs', 'resizeContainer', device, '0'],
            'requires': 'successful raw readback, relocated GPT verification, refreshed partition identity',
            'failure_scope': 'A failed grow does not undo the verified restore; report remaining capacity.'}


"""Pure validation of diskutil info/list/APFS observations before diskNECONFIGURAT writes.

No commands, filesystem access, mounting or writes. The caller supplies fresh
observations and holds its operation lock. Source mappings must cover repo+image.
"""
import hashlib
import json
import re
import uuid

DISK_TARGET_NAME = 'diskNECONFIGURAT'
EXTERNAL_BUSES = frozenset(('USB', 'Thunderbolt', 'FireWire'))
MIN_CAPACITY = 256_050_000_000
MAX_CAPACITY = 256_150_000_000
UUID_KEYS = ('DiskUUID', 'MediaUUID', 'PartitionUUID', 'APFSContainerUUID')
HARDWARE_KEYS = ('MediaName', 'DeviceTreePath', 'IORegistryEntryName', 'IORegistryEntryID',
                 'SerialNumber', 'MediaSerialNumber', 'USBSerialNumber', 'SolidState')


class DiskTargetError(RuntimeError):
    pass


def _disk_require(ok, message):
    if not ok:
        raise DiskTargetError(message)


def _disk_id(value):
    _disk_require(isinstance(value, str), 'Missing disk identifier')
    value = re.sub(r'^/dev/r?', '', value)
    _disk_require(re.fullmatch(r'disk[0-9]+(?:s[0-9]+)*', value) is not None,
                  'Invalid disk identifier: ' + value)
    return value


def _disk_whole(value):
    return re.match(r'disk[0-9]+', _disk_id(value))[0]


def _disk_size(row):
    values = [row[key] for key in ('TotalSize', 'Size') if key in row]
    _disk_require(values and all(type(v) is int and v > 0 for v in values)
                  and len(set(values)) == 1, 'Missing or inconsistent disk capacity')
    return values[0]


def _disk_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _disk_uuids(row):
    result = {}
    for key in UUID_KEYS:
        value = row.get(key)
        if value in (None, ''):
            continue
        try:
            _disk_require(isinstance(value, str), 'Invalid ' + key)
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError) as error:
            raise DiskTargetError('Invalid ' + key) from error
        _disk_require(parsed.int != 0, 'Empty ' + key)
        result[key] = str(parsed).upper()
    return result


def _disk_maps(disk_list, apfs_list):
    _disk_require(isinstance(disk_list, dict) and isinstance(apfs_list, dict), 'Invalid disk inventory')
    listed = disk_list.get('AllDisksAndPartitions')
    containers = apfs_list.get('Containers')
    _disk_require(isinstance(listed, list) and isinstance(containers, list), 'Incomplete disk/APFS inventory')
    whole = {}
    for row in listed:
        _disk_require(isinstance(row, dict), 'Invalid whole-disk row')
        name = _disk_id(row.get('DeviceIdentifier'))
        _disk_require(name == _disk_whole(name) and name not in whole, 'Ambiguous whole-disk inventory')
        whole[name] = row
    mapped = {}
    for row in containers:
        _disk_require(isinstance(row, dict), 'Invalid APFS container row')
        name = _disk_id(row.get('ContainerReference'))
        _disk_require(name == _disk_whole(name) and name not in mapped, 'Ambiguous APFS container inventory')
        stores = row.get('PhysicalStores')
        _disk_require(isinstance(stores, list) and bool(stores), 'APFS physical stores are missing')
        identifiers = [_disk_id(store.get('DeviceIdentifier')) for store in stores if isinstance(store, dict)]
        _disk_require(len(identifiers) == len(stores) == len(set(identifiers)), 'Ambiguous APFS physical stores')
        _disk_require(all(_disk_whole(store) in whole for store in identifiers), 'APFS store absent from disk inventory')
        mapped[name] = dict(record=row, stores=identifiers)
    return whole, mapped


def physical_backing_disks(info, disk_list, apfs_list):
    """Resolve APFS volumes/snapshots or direct partitions to physical whole IDs."""
    whole, containers = _disk_maps(disk_list, apfs_list)
    _disk_require(isinstance(info, dict), 'Missing source/startup disk information')
    device = _disk_id(info.get('DeviceIdentifier'))
    parent = _disk_id(info.get('ParentWholeDisk', _disk_whole(device)))
    _disk_require(parent == _disk_whole(device), 'Source/startup parent disk is inconsistent')
    reference = info.get('APFSContainerReference')
    reference = _disk_id(reference) if reference is not None else None
    candidates = set()
    for name, container in containers.items():
        if device == name or device.startswith(name + 's') or device in container['stores']:
            candidates.add(name)
    if reference is not None:
        _disk_require(reference in containers and reference in candidates,
                      'Source/startup APFS reference cannot be resolved consistently')
    _disk_require(len(candidates) <= 1, 'Ambiguous source/startup APFS container')
    if candidates:
        name = next(iter(candidates))
        stores = {_disk_whole(store) for store in containers[name]['stores']}
        _disk_require(not stores & set(containers), 'APFS backing resolves to another virtual container')
        return sorted(stores)
    _disk_require(parent in whole and parent not in containers
                  and whole[parent].get('Content') in ('GUID_partition_scheme', 'FDisk_partition_scheme', 'Apple_partition_scheme'),
                  'Source/startup physical backing is unresolved')
    return [parent]


def validate_disk_target(target_info, disk_list, apfs_list, *, root_info, source_infos,
                         expected_fingerprint=None, require_initial_layout=True,
                         expected_hardware_fingerprint=None):
    """Bind selected diskNECONFIGURAT and protect startup, repository and image source.

    The initial fingerprint includes GPT/APFS UUIDs and partition geometry. After
    restore, pass require_initial_layout=False and compare hardware_fingerprint;
    the caller must additionally verify the restored GPT and source image bytes.
    Media names alone are not unique hardware IDs; the returned evidence is exact.
    """
    _disk_require(type(require_initial_layout) is bool, 'Invalid disk layout phase')
    _disk_require(isinstance(target_info, dict), 'Target information is absent')
    info = target_info
    _disk_require(_disk_id(info.get('DeviceIdentifier')) == DISK_TARGET_NAME
                  and _disk_id(info.get('ParentWholeDisk', DISK_TARGET_NAME)) == DISK_TARGET_NAME
                  and info.get('WholeDisk') is True, 'Only whole /dev/diskNECONFIGURAT is authorized')
    if 'DeviceNode' in info:
        _disk_require(_disk_id(info['DeviceNode']) == DISK_TARGET_NAME, 'Target device node differs')
    _disk_require(info.get('VirtualOrPhysical') == 'Physical' and info.get('Internal') is False,
                  'Target must be explicitly physical and external')
    _disk_require(info.get('BusProtocol') in EXTERNAL_BUSES, 'Unsupported external disk bus')
    _disk_require(info.get('Writable') is True and info.get('ReadOnlyMedia') is not True
                  and info.get('ReadOnlyVolume') is not True, 'Target media is not explicitly writable')
    size = _disk_size(info)
    _disk_require(MIN_CAPACITY <= size < MAX_CAPACITY and size % 512 == 0,
                  'Target capacity differs from the selected 256.1 GB disk')
    _disk_require(type(info.get('DeviceBlockSize')) is int and info['DeviceBlockSize'] == 512,
                  'Target must have 512-byte logical sectors')
    whole, containers = _disk_maps(disk_list, apfs_list)
    _disk_require(DISK_TARGET_NAME in whole, 'Target is absent from the current disk list')
    listed = whole[DISK_TARGET_NAME]
    _disk_require(listed.get('Content') == 'GUID_partition_scheme' and _disk_size(listed) == size,
                  'Target list/info disagree about GPT or capacity')
    info_uuids, listed_uuids = _disk_uuids(info), _disk_uuids(listed)
    _disk_require(all(info_uuids[key] == listed_uuids[key] for key in info_uuids.keys() & listed_uuids.keys()),
                  'Target list/info UUID observations disagree')
    if 'Content' in info:
        _disk_require(info['Content'] == 'GUID_partition_scheme', 'Target info is not GPT')
    partitions = listed.get('Partitions')
    _disk_require(isinstance(partitions, list) and len(partitions) == 2
                  and all(isinstance(p, dict) for p in partitions), 'Expected exactly EFI and APFS partitions')
    partitions = sorted(partitions, key=lambda p: _disk_id(p.get('DeviceIdentifier')))
    expected = ((DISK_TARGET_NAME + 's1', 'EFI'), (DISK_TARGET_NAME + 's2', 'Apple_APFS'))
    _disk_require([(_disk_id(p.get('DeviceIdentifier')), p.get('Content')) for p in partitions] == list(expected),
                  'Target partition identities or types differ')
    partition_sizes = [_disk_size(p) for p in partitions]
    _disk_require(all(v % 512 == 0 for v in partition_sizes) and sum(partition_sizes) <= size,
                  'Target partition geometry is invalid')
    if require_initial_layout:
        _disk_require(209_650_000 <= partition_sizes[0] < 209_750_000
                      and 255_850_000_000 <= partition_sizes[1] < 255_950_000_000
                      and size - sum(partition_sizes) < 64 * 1024 ** 2,
                      'Initial EFI/APFS sizes differ from the selected disk')
    target_containers = [(name, c) for name, c in containers.items() if DISK_TARGET_NAME + 's2' in c['stores']]
    _disk_require(len(target_containers) <= 1, 'Target APFS mapping is ambiguous')
    if require_initial_layout:
        _disk_require(len(target_containers) == 1, 'Initial target APFS container is missing')
    for name, container in target_containers:
        _disk_require(container['stores'] == [DISK_TARGET_NAME + 's2'], 'Target APFS container spans other physical stores')
        reference = partitions[1].get('APFSContainerReference')
        if reference is not None:
            _disk_require(_disk_id(reference) == name, 'APFS list and partition reference disagree')
    _disk_require(isinstance(source_infos, dict) and {'repo', 'image'} <= set(source_infos),
                  'Both repository and image backing information are required')
    protected = {'startup': physical_backing_disks(root_info, disk_list, apfs_list)}
    for label, observation in source_infos.items():
        _disk_require(isinstance(label, str) and label != 'startup', 'Invalid or reserved source label')
        protected[label] = physical_backing_disks(observation, disk_list, apfs_list)
    _disk_require(all(DISK_TARGET_NAME not in disks for disks in protected.values()),
                  'Target backs the running system, repository or source image')
    hardware = dict(device=DISK_TARGET_NAME, total_size=size, logical_sector_size=512,
                    bus=info['BusProtocol'], physical=True, external=True)
    for key in HARDWARE_KEYS:
        if key in info and info[key] not in (None, ''):
            _disk_require(type(info[key]) in (str, int, bool), 'Invalid hardware identity field: ' + key)
            hardware[key] = info[key]
    hardware_fingerprint = _disk_digest(hardware)
    if expected_hardware_fingerprint is not None:
        _disk_require(expected_hardware_fingerprint == hardware_fingerprint, 'Target hardware identity changed')
    identity = dict(hardware=hardware, media_uuids=_disk_uuids(info),
                    gpt_uuids=_disk_uuids(listed),
                    partitions=[dict(device=p['DeviceIdentifier'], content=p['Content'], size=_disk_size(p),
                                     uuids=_disk_uuids(p)) for p in partitions],
                    apfs=[dict(stores=c['stores'], uuids=_disk_uuids(c['record'])) for _, c in target_containers])
    evidence = [key for key in HARDWARE_KEYS if key in hardware and key not in ('MediaName', 'SolidState')]
    uuid_evidence = bool(identity['media_uuids'] or identity['gpt_uuids']
                         or any(p['uuids'] for p in identity['partitions'])
                         or any(c['uuids'] for c in identity['apfs']))
    if require_initial_layout:
        _disk_require(uuid_evidence or evidence, 'No disk UUID or hardware identifier is available for recheck')
    fingerprint = _disk_digest(identity)
    if expected_fingerprint is not None:
        _disk_require(expected_fingerprint == fingerprint, 'Selected disk identity or initial layout changed')
    return dict(target='/dev/' + DISK_TARGET_NAME, raw_target='/dev/r' + DISK_TARGET_NAME, fingerprint=fingerprint,
                identity=identity, hardware_identity=hardware, hardware_fingerprint=hardware_fingerprint,
                hardware_identifier_fields=evidence, initial_layout_checked=require_initial_layout,
                target_containers=[name for name, _ in target_containers], protected_physical_disks=protected,
                capacity_bytes=size, logical_sector_size=512)


"""Bounded raw-image copy and verification; target selection belongs to the caller.

Darwin ioctl numbers are from Apple's xnu/bsd/sys/disk.h.  In
IOStorageFamily/IOMediaBSDClient.cpp, DKIOCSYNCHRONIZECACHE calls
IOMedia::synchronize and propagates its error.  No physical device is opened
here: the privileged caller supplies already checked, open descriptors.
"""
import errno
import fcntl
import hashlib
import os
import re
import stat
import struct
import time
from typing import Callable


DKIOCGETBLOCKSIZE = 0x40046418  # _IOR('d', 24, uint32_t)
DKIOCGETBLOCKCOUNT = 0x40086419  # _IOR('d', 25, uint64_t)
DKIOCSYNCHRONIZECACHE = 0x20006416  # _IO('d', 22)
CHUNK_SIZE = 8 * 1024 * 1024
_UNSUPPORTED = {errno.ENOTTY, errno.ENOTSUP, errno.EOPNOTSUPP}


class RawIOError(RuntimeError):
    """A copy, verification, geometry, or synchronization check failed."""


def _retry_eintr(function, *args):
    while True:
        try:
            return function(*args)
        except OSError as exc:
            if exc.errno != errno.EINTR:
                raise


def device_geometry(fd: int) -> tuple[int, int]:
    """Return (logical block size, byte capacity) from this opened Darwin fd."""
    block_buf = bytearray(4)
    count_buf = bytearray(8)
    _retry_eintr(fcntl.ioctl, fd, DKIOCGETBLOCKSIZE, block_buf, True)
    _retry_eintr(fcntl.ioctl, fd, DKIOCGETBLOCKCOUNT, count_buf, True)
    block = struct.unpack("=I", block_buf)[0]
    count = struct.unpack("=Q", count_buf)[0]
    if block < 512 or block & (block - 1) or not count:
        raise RawIOError(f"Invalid raw device geometry: block={block}, count={count}")
    capacity = block * count
    if capacity > (1 << 63) - 1:
        raise RawIOError(f"Raw device capacity cannot be addressed safely: {capacity}")
    return block, capacity


def flush_raw(fd: int) -> dict:
    """Flush the device cache, or explicitly report an fsync-only fallback.

    Only ENOTTY/ENOTSUP can select the fallback.  EIO, permission errors and
    unexpected ioctl errors propagate; a failed fsync fallback also propagates.
    A successful fsync fallback does NOT claim a physical drive-cache flush.
    """
    try:
        _retry_eintr(fcntl.ioctl, fd, DKIOCSYNCHRONIZECACHE, 0)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED:
            raise
        _retry_eintr(os.fsync, fd)
        return {
            "method": "fsync-fallback",
            "completed": True,
            "device_cache_flush_requested": False,
            "ioctl_unsupported_errno": exc.errno,
            "ioctl_unsupported_error": str(exc),
        }
    return {
        "method": "DKIOCSYNCHRONIZECACHE",
        "completed": True,
        "device_cache_flush_requested": True,
    }


def _source_identity(st) -> tuple:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _write_all(fd: int, data: bytes, offset: int, written_callback=None) -> None:
    view = memoryview(data)
    try:
        done = 0
        while done < len(view):
            part = view[done:]
            try:
                n = _retry_eintr(os.pwrite, fd, part, offset + done)
            finally:
                part.release()
            if not isinstance(n, int) or n <= 0 or n > len(view) - done:
                raise RawIOError(f"Invalid/zero write at offset {offset + done}: {n!r}")
            done += n
            if written_callback is not None:
                written_callback(n)
    finally:
        view.release()


def stream_copy_and_verify(
    source_fd: int,
    target_fd: int,
    size: int,
    expected_sha: str,
    progress_callback: Callable[[str, int, int], None],
    checkpoint_callback: Callable[[str, dict], None] | None = None,
    *,
    flush: Callable[[int], dict] = flush_raw,
    cancel_check: Callable[[], None] | None = None,
    chunk_size: int = CHUNK_SIZE,
    progress_interval: float = 10.0,
) -> dict:
    """Write EVERY source byte, flush, then hash the entire target prefix.

    The caller MUST prehash the source and authorize/check the target before
    calling.  The source digest computed during writing additionally detects
    changes since that preflight.  No GPT relocation or APFS resizing occurs.
    On failure the target may already be partly or completely overwritten.

    Memory is bounded by one chunk (8 MiB by default); a short successful read
    or write is continued, while EOF or a zero write fails.  Progress callbacks
    get (phase, done, total) at phase boundaries and every progress_interval
    seconds.  Checkpoints get (event, details).  Callback failures propagate.
    """
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        raise ValueError("expected_sha must be a SHA256 hex digest")
    expected_sha = expected_sha.lower()
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1 <= chunk_size <= CHUNK_SIZE:
        raise ValueError("chunk_size must be between 1 byte and 8 MiB")
    if progress_interval < 0:
        raise ValueError("progress_interval must be nonnegative")
    if not callable(progress_callback) or not callable(flush):
        raise TypeError("progress_callback and flush must be callable")
    if checkpoint_callback is not None and not callable(checkpoint_callback):
        raise TypeError("checkpoint_callback must be callable or None")
    if cancel_check is not None and not callable(cancel_check):
        raise TypeError("cancel_check must be callable or None")

    source_before = os.fstat(source_fd)
    target_before = os.fstat(target_fd)
    if not stat.S_ISREG(source_before.st_mode) or source_before.st_size != size:
        raise RawIOError("Source must be a regular file of exactly the declared image size")
    if (source_before.st_dev, source_before.st_ino) == (target_before.st_dev, target_before.st_ino):
        raise RawIOError("Source and target are the same file")
    if not (stat.S_ISCHR(target_before.st_mode) or stat.S_ISREG(target_before.st_mode)):
        raise RawIOError("Target must be an already checked raw character device or test file")
    if stat.S_ISREG(target_before.st_mode) and target_before.st_size < size:
        raise RawIOError("Test target is smaller than the declared image size")
    if fcntl.fcntl(source_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY:
        raise RawIOError("Source descriptor is not readable")
    if fcntl.fcntl(target_fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDWR:
        raise RawIOError("Target descriptor must be open read/write for verification")

    receipt = {
        "image_size_bytes": size,
        "expected_sha256": expected_sha,
        "bytes_written": 0,
        "bytes_verified": 0,
        "verified": False,
    }

    def checkpoint(event: str) -> None:
        if checkpoint_callback is not None:
            checkpoint_callback(event, dict(receipt))

    last_progress = 0.0

    def progress(phase: str, done: int, force: bool = False) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if force or now - last_progress >= progress_interval:
            progress_callback(phase, done, size)
            last_progress = now

    def cancel() -> None:
        if cancel_check is not None:
            cancel_check()

    def wrote(n: int) -> None:
        receipt["bytes_written"] += n

    phase = "write"
    try:
        cancel()
        checkpoint("write_started")
        progress("write", 0, True)
        source_hash = hashlib.sha256()
        while receipt["bytes_written"] < size:
            cancel()
            offset = receipt["bytes_written"]
            want = min(chunk_size, size - offset)
            data = _retry_eintr(os.pread, source_fd, want, offset)
            if not data or len(data) > want:
                raise RawIOError(f"Unexpected source EOF/read length at {offset}/{size}")
            source_hash.update(data)
            cancel()
            _write_all(target_fd, data, offset, wrote)
            del data
            progress("write", receipt["bytes_written"])
        progress("write", size, True)
        receipt["source_sha256"] = source_hash.hexdigest()
        if _source_identity(os.fstat(source_fd)) != _source_identity(source_before):
            raise RawIOError("Source identity/size/timestamps changed during writing")
        if receipt["source_sha256"] != expected_sha:
            raise RawIOError("Source SHA256 changed since preflight; do not grow or boot the target")
        checkpoint("write_complete")
        phase = "flush"
        cancel()
        receipt["flush"] = flush(target_fd)
        if not isinstance(receipt["flush"], dict) or receipt["flush"].get("completed") is not True:
            raise RawIOError("Raw device synchronization did not complete")
        checkpoint("flush_complete")

        phase = "verify"
        checkpoint("verify_started")
        progress("verify", 0, True)
        target_hash = hashlib.sha256()
        while receipt["bytes_verified"] < size:
            cancel()
            offset = receipt["bytes_verified"]
            want = min(chunk_size, size - offset)
            data = _retry_eintr(os.pread, target_fd, want, offset)
            if not data or len(data) > want:
                raise RawIOError(f"Unexpected target EOF/read length at {offset}/{size}")
            target_hash.update(data)
            receipt["bytes_verified"] += len(data)
            del data
            progress("verify", receipt["bytes_verified"])
        progress("verify", size, True)
        receipt["readback_sha256"] = target_hash.hexdigest()
        if receipt["readback_sha256"] != expected_sha:
            raise RawIOError("Full target readback SHA256 differs from the verified image")
        receipt["verified"] = True
        checkpoint("verify_complete")
        return receipt
    except BaseException as exc:
        receipt["failed_phase"] = phase
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        try:
            checkpoint("failed")
        except BaseException:
            pass  # Never replace the original copy/flush/cancel failure.
        raise


"""Pure checks for the restored Hao disk: APFS identity/growth and EFI hashes.

All dictionaries come from fresh diskutil plist reads or a read-only EFI walk.
This module never opens a device, mounts anything, or executes a command.
"""
import re
import struct
import uuid
from pathlib import PurePosixPath

RESTORED_HAO_GROUP = '00000000-0000-4000-8000-000000000002'
RESTORED_APFS_TYPE = '7C3457EF-0000-11AA-AA11-00306543ECAC'
RESTORED_ROLES = ('System', 'Data', 'Preboot', 'Recovery', 'VM')
RESTORED_ALIGNMENT_BYTES = 1 << 20
_EFI_METADATA_ROOTS = {'.fseventsd', '.spotlight-v100', '.trashes', '.temporaryitems'}


class RestoredDiskError(ValueError):
    pass


def _finish_require(condition, message):
    if not condition:
        raise RestoredDiskError(message)


def _finish_uuid(value, what):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise RestoredDiskError('Missing/invalid ' + what) from error
    _finish_require(parsed.int != 0, what + ' is zero')
    return str(parsed).upper()


def _finish_device(value, what, whole=False):
    _finish_require(isinstance(value, str), 'Missing ' + what)
    value = value.removeprefix('/dev/')
    pattern = r'disk[0-9]+' if whole else r'disk[0-9]+(?:s[0-9]+)?'
    _finish_require(re.fullmatch(pattern, value) is not None, 'Invalid ' + what)
    return value


def _finish_size(info, what):
    value = info.get('TotalSize', info.get('Size'))
    _finish_require(type(value) is int and value > 0, 'Missing/invalid ' + what + ' size')
    return value


def source_apfs_identity(read_at, layout):
    """Read container UUID from block0 of the caller-authenticated source image.

    Apple's APFS Reference nx_superblock_t places magic at32, block size/count
    at36/40 and nx_uuid at72. UUID is a byte array, not a little-endian GPT GUID.
    Full pinned-image SHA256 is the integrity proof; this adds no checksum gate.
    """
    partitions = [p for p in layout.partitions if p['type_guid'] == RESTORED_APFS_TYPE]
    _finish_require(len(partitions) == 1 and layout.sector_size == 512,
                    'Expected one source APFS partition with 512-byte GPT sectors')
    part = partitions[0]
    offset = part['first_lba'] * 512
    _finish_require(part['size_bytes'] >= 4096, 'Source APFS partition is too small')
    block = read_at(offset, 4096)
    _finish_require(isinstance(block, (bytes, bytearray)) and len(block) == 4096,
                    'Short source APFS superblock read')
    _finish_require(block[32:36] == b'NXSB', 'Source APFS NXSB magic is absent')
    block_size = struct.unpack_from('<I', block, 36)[0]
    block_count = struct.unpack_from('<Q', block, 40)[0]
    _finish_require(4096 <= block_size <= 65536 and block_size & (block_size - 1) == 0
                    and 0 < block_count * block_size <= part['size_bytes'],
                    'Source APFS block geometry is invalid')
    container_uuid = _finish_uuid(str(uuid.UUID(bytes=bytes(block[72:88]))), 'source APFS container UUID')
    return {'container_uuid': container_uuid, 'partition_guid': part['partition_guid'],
            'partition_index': part['index'], 'partition_offset_bytes': offset,
            'block_size': block_size, 'block_count': block_count,
            'container_bytes': block_count * block_size,
            'integrity_scope': 'Caller verifies the complete source image against its pinned SHA256.'}


def validate_apfs_target(part_info, apfs_listing, source_apfs_partition, whole_disk,
                         expected_group_uuid=RESTORED_HAO_GROUP):
    """Bind the restored partition and its sole container using current device IDs.

    The cloned Data volume UUID equals the image's group UUID. Require every
    essential role once; extra APFS volumes are recorded, not silently selected.
    """
    _finish_require(isinstance(part_info, dict) and isinstance(apfs_listing, dict)
                    and isinstance(source_apfs_partition, dict), 'Invalid APFS input records')
    disk = _finish_device(whole_disk, 'whole physical disk', whole=True)
    index = source_apfs_partition.get('index')
    _finish_require(type(index) is int and index > 0, 'Invalid source APFS partition index')
    _finish_require(source_apfs_partition.get('type_guid', '').upper() == RESTORED_APFS_TYPE,
                    'Source partition is not APFS')
    partition = disk + 's' + str(index)
    _finish_require(_finish_device(part_info.get('DeviceIdentifier'), 'APFS partition') == partition,
                    'diskutil reported another APFS physical partition')
    _finish_require(_finish_device(part_info.get('ParentWholeDisk', part_info.get('PartOfWhole')),
                                  'parent physical disk', whole=True) == disk,
                    'APFS partition belongs to another physical disk')
    _finish_require(part_info.get('WholeDisk') is False and part_info.get('Content') == 'Apple_APFS',
                    'Expected a physical Apple_APFS partition')
    expected_guid = _finish_uuid(source_apfs_partition.get('partition_guid'), 'source APFS partition UUID')
    actual_guid = _finish_uuid(part_info.get('DiskUUID'), 'restored APFS partition UUID')
    _finish_require(actual_guid == expected_guid, 'APFS partition UUID differs from the source GPT')
    partition_bytes = _finish_size(part_info, 'APFS partition')
    rows = apfs_listing.get('Containers')
    _finish_require(isinstance(rows, list), 'APFS container list is absent')
    matches = [row for row in rows if isinstance(row, dict) and any(
        isinstance(store, dict) and store.get('DeviceIdentifier', '').removeprefix('/dev/') == partition
        for store in row.get('PhysicalStores', []))]
    _finish_require(len(matches) == 1, 'Restored physical partition has no unique APFS container')
    container = matches[0]
    stores = container['PhysicalStores']
    _finish_require(len(stores) == 1
                    and _finish_device(stores[0].get('DeviceIdentifier'), 'APFS physical store') == partition,
                    'Restored APFS container spans another physical store')
    if 'Size' in stores[0]:
        _finish_require(type(stores[0]['Size']) is int and stores[0]['Size'] == partition_bytes,
                        'APFS list and diskutil info disagree on physical-store size')
    reference = _finish_device(container.get('ContainerReference'), 'APFS container reference', whole=True)
    if part_info.get('APFSContainerReference'):
        _finish_require(_finish_device(part_info['APFSContainerReference'], 'partition container', whole=True)
                        == reference, 'Partition and container references disagree')
    capacity = container.get('CapacityCeiling')
    _finish_require(type(capacity) is int and 0 < capacity <= partition_bytes
                    and partition_bytes - capacity < 4096,
                    'APFS capacity does not match its physical partition')
    expected_group = _finish_uuid(expected_group_uuid, 'expected volume group UUID')
    volumes = container.get('Volumes')
    _finish_require(isinstance(volumes, list), 'Restored APFS volumes are absent')
    roles = {}
    devices = set()
    volume_uuids = set()
    extras = []
    for row in volumes:
        _finish_require(isinstance(row, dict), 'Invalid APFS volume record')
        device = _finish_device(row.get('DeviceIdentifier'), 'APFS volume')
        _finish_require(re.fullmatch(re.escape(reference) + r's[0-9]+', device) is not None
                        and device not in devices, 'APFS volume is duplicated or outside its container')
        devices.add(device)
        volume_uuid = _finish_uuid(row.get('APFSVolumeUUID', row.get('VolumeUUID')), 'APFS volume UUID')
        _finish_require(volume_uuid not in volume_uuids, 'Duplicate APFS volume UUID')
        volume_uuids.add(volume_uuid)
        current_roles = row.get('Roles')
        _finish_require(isinstance(current_roles, list) and all(isinstance(v, str) for v in current_roles),
                        'APFS volume role list is invalid')
        selected = [role for role in current_roles if role in RESTORED_ROLES]
        _finish_require(len(selected) <= 1, 'One APFS volume has several essential roles')
        if not selected:
            extras.append({'device': device, 'uuid': volume_uuid, 'roles': current_roles})
            continue
        role = selected[0]
        _finish_require(role not in roles, 'Duplicate APFS role: ' + role)
        roles[role] = {'device': device, 'uuid': volume_uuid, 'name': row.get('Name')}
        if role in ('System', 'Data'):
            for key in ('APFSVolumeGroupUUID', 'APFSVolumeGroupID', 'VolumeGroupUUID'):
                if row.get(key):
                    _finish_require(_finish_uuid(row[key], key) == expected_group,
                                    role + ' volume group differs from the source image')
    _finish_require(set(roles) == set(RESTORED_ROLES), 'System/Data/Preboot/Recovery/VM roles are incomplete')
    _finish_require(roles['Data']['uuid'] == expected_group,
                    'Cloned Data volume UUID differs from the source assembly group')
    container_uuid = (_finish_uuid(container['APFSContainerUUID'], 'APFS container UUID')
                      if container.get('APFSContainerUUID') else None)
    return {'verified': True, 'whole_disk': disk, 'apfs_partition': partition,
            'partition_guid': actual_guid, 'partition_bytes': partition_bytes,
            'container': reference, 'container_uuid': container_uuid, 'capacity_bytes': capacity,
            'group_uuid': expected_group, 'roles': roles, 'extra_volumes': extras,
            'physical_stores': [partition]}


def validate_apfs_growth(before, part_info, apfs_listing, source_apfs_partition, whole_disk,
                         target_bytes, last_usable_lba, expected_group_uuid=RESTORED_HAO_GROUP):
    """Validate resizeContainer0 result against the relocated GPT's usable end."""
    _finish_require(isinstance(before, dict) and before.get('verified') is True,
                    'A verified pre-growth APFS record is required')
    after = validate_apfs_target(part_info, apfs_listing, source_apfs_partition,
                                 whole_disk, expected_group_uuid)
    for key in ('whole_disk', 'apfs_partition', 'partition_guid', 'group_uuid'):
        _finish_require(before.get(key) == after[key], 'APFS growth changed identity: ' + key)
    if before.get('container_uuid'):
        _finish_require(before['container_uuid'] == after['container_uuid'], 'APFS container UUID changed')
    _finish_require(all(before.get('roles', {}).get(role, {}).get('uuid') == after['roles'][role]['uuid']
                        for role in RESTORED_ROLES), 'APFS growth changed an essential volume UUID')
    first = source_apfs_partition.get('first_lba')
    _finish_require(type(target_bytes) is int and target_bytes > 0 and target_bytes % 512 == 0
                    and type(first) is int and type(last_usable_lba) is int
                    and 0 < first <= last_usable_lba < target_bytes // 512 - 1,
                    'Invalid physical target/GPT growth bounds')
    maximum = (last_usable_lba - first + 1) * 512
    unused = maximum - after['partition_bytes']
    _finish_require(0 <= unused <= RESTORED_ALIGNMENT_BYTES,
                    'APFS physical partition did not grow to the target capacity')
    _finish_require(after['partition_bytes'] >= before['partition_bytes'],
                    'APFS physical partition shrank during growth')
    after.update(growth_verified=True, maximum_partition_bytes=maximum,
                 unused_alignment_bytes=unused,
                 increased_by_bytes=after['partition_bytes'] - before['partition_bytes'])
    return after


def _efi_hash_index(files, what):
    _finish_require(isinstance(files, dict), what + ' EFI hashes must be an object')
    result = {}
    for path, digest in files.items():
        _finish_require(isinstance(path, str), what + ' EFI path is not a string')
        parsed = PurePosixPath(path)
        _finish_require(bool(parsed.parts) and not parsed.is_absolute() and '..' not in parsed.parts
                        and str(parsed) == path and '\\' not in path and '\0' not in path,
                        what + ' EFI path is invalid')
        folded = path.casefold()
        _finish_require(folded not in result, what + ' EFI paths collide on FAT')
        _finish_require(isinstance(digest, str) and re.fullmatch('[0-9a-fA-F]{64}', digest) is not None,
                        what + ' EFI digest is invalid')
        result[folded] = (path, digest.lower())
    return result


def _efi_metadata(path):
    parts = PurePosixPath(path).parts
    # Keep every manifest file inside EFI/ and System/ strict, including any
    # captured Finder metadata there. Only volume-root bookkeeping is exempt.
    return parts[0].casefold() in _EFI_METADATA_ROOTS or (len(parts) == 1 and parts[0].casefold() == '.ds_store')


def validate_efi_hashes(actual_files, expected_files):
    """Require all boot files and reject extra boot content; record mutable FS metadata.

    The final manifest has202files; one is the filesystem's .fseventsd UUID. Its
    changes do not weaken the strict comparison of all201 EFI/System boot files.
    """
    actual, expected = _efi_hash_index(actual_files, 'Actual'), _efi_hash_index(expected_files, 'Expected')
    wanted = {path: row for path, row in expected.items() if not _efi_metadata(row[0])}
    _finish_require(bool(wanted) and all(PurePosixPath(row[0]).parts[0].casefold() in ('efi', 'system')
                                        for row in wanted.values()), 'Unexpected boot manifest root')
    supplied = {path: row for path, row in actual.items() if not _efi_metadata(row[0])}
    _finish_require(set(supplied) == set(wanted), 'Restored EFI boot-file inventory differs from manifest')
    _finish_require(all(supplied[path][1] == row[1] for path, row in wanted.items()),
                    'Restored EFI boot-file SHA256 differs from manifest')
    for required in ('EFI/OC/OpenCore.efi', 'EFI/OC/config.plist', 'System/Library/CoreServices/boot.efi'):
        _finish_require(required.casefold() in wanted, 'Expected Apple EFI layout is incomplete: ' + required)
    changed_metadata = [row[0] for path, row in expected.items() if _efi_metadata(row[0])
                        and actual.get(path, (None, None))[1] != row[1]]
    extra_metadata = [row[0] for path, row in actual.items() if _efi_metadata(row[0]) and path not in expected]
    return {'verified': True, 'layout': 'apple', 'boot_files_verified': len(wanted),
            'expected_manifest_files': len(expected), 'actual_files_examined': len(actual),
            'changed_or_missing_filesystem_metadata': changed_metadata,
            'extra_filesystem_metadata': extra_metadata}



def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_json(path):
    value = json.loads(Path(path).read_text())
    need(isinstance(value, dict), 'Raport JSON invalid: ' + str(path))
    return value


def save_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def real_path(repo, relative, file=False):
    part = Path(relative)
    need(not part.is_absolute() and '..' not in part.parts, 'Cale relativa invalida')
    path = repo
    for name in part.parts:
        path = path / name
        need(not path.is_symlink(), 'Symlink refuzat: ' + str(path))
    need(path.resolve().is_relative_to(repo), 'Cale externa workspace-ului')
    if file:
        need(path.is_file(), 'Fisier lipsa: ' + str(path))
    return path


def source_identity(path):
    value = Path(path).lstat()
    return stat_identity(value)


def stat_identity(value):
    need(stat.S_ISREG(value.st_mode), 'Imaginea nu este un fisier obisnuit')
    return dict(device=value.st_dev, inode=value.st_ino, size=value.st_size,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def verified_source(repo, hash_image=False):
    state = load_json(real_path(repo, 'local/mbp91/step12-state.json', True))
    record = state.get('image', {})
    need(record.get('image') == IMAGE_REL and record.get('artifact') == ARTIFACT_REL,
         'Imaginea inregistrata nu este artefactul finalizat la pasul 12')
    need(record.get('sha256') == IMAGE_SHA and record.get('bytes') == IMAGE_BYTES,
         'Identitatea imaginii a fost schimbata')
    build = real_path(repo, ARTIFACT_REL + '/build.json', True)
    need(file_hash(build) == BUILD_RECORD_SHA and load_json(build) == record,
         'Raportul imaginii difera de cel verificat')
    manifest_path = real_path(repo, ARTIFACT_REL + '/boot-efi/manifest.json', True)
    need(file_hash(manifest_path) == EFI_MANIFEST_SHA, 'Manifest EFI schimbat')
    manifest = load_json(manifest_path)
    need(manifest.get('model') == MODEL and manifest.get('os_build') == BUILD,
         'Manifestul EFI apartine altei tinte')
    image = real_path(repo, IMAGE_REL, True)
    identity = source_identity(image)
    need(identity['size'] == IMAGE_BYTES, 'Dimensiunea imaginii difera')
    with image.open('rb') as stream:
        layout = validate_source_gpt(lambda off, size: os.pread(stream.fileno(), size, off), IMAGE_BYTES)
        layout.apfs_identity = source_apfs_identity(lambda off, size: os.pread(stream.fileno(), size, off), layout)
    if hash_image:
        print('    Verific SHA256 al imaginii sursa de 85,9 GB.', flush=True)
        digest = hashlib.sha256(); done = 0; pulse = time.monotonic()
        with image.open('rb') as stream:
            for block in iter(lambda: stream.read(8 << 20), b''):
                digest.update(block); done += len(block)
                if time.monotonic() - pulse >= 10:
                    print('    Sursa: %.1f%%.' % (100 * done / IMAGE_BYTES), flush=True)
                    pulse = time.monotonic()
        need(done == IMAGE_BYTES and digest.hexdigest() == IMAGE_SHA,
             'SHA256 al imaginii sursa nu corespunde; scrierea nu a inceput')
        need(source_identity(image) == identity, 'Imaginea s-a schimbat in timpul verificarii')
        print('    SHA256 sursa: OK.', flush=True)
    return image, identity, layout, manifest


class Commands:
    def __init__(self, report, save=None):
        self.report = report
        self.save = save

    def run(self, argv, *, timeout=60, check=True, live=False):
        argv = list(map(str, argv))
        start = time.monotonic()
        if live:
            print('    ' + shlex.join(argv), flush=True)
            result = subprocess.run(argv, timeout=timeout)
            output = ''
        else:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            output = result.stdout
        self.report.setdefault('commands', []).append(dict(argv=argv,
            returncode=result.returncode, elapsed_s=round(time.monotonic()-start, 2)))
        if self.save:
            self.save()
        if check and result.returncode:
            detail = '' if live else (result.stderr or result.stdout)[-2400:]
            raise RuntimeError('%s: cod %d. %s' % (argv[0], result.returncode, detail))
        return output if not live else result.returncode

    def plist(self, argv):
        value = plistlib.loads(self.run(argv).encode())
        need(isinstance(value, dict), 'Raspuns plist invalid: ' + str(argv))
        return value


def backing_info(commands, path):
    rows = commands.run(['/bin/df', '-P', str(path)]).strip().splitlines()
    need(len(rows) >= 2, 'Nu pot identifica volumul sursei')
    device = rows[-1].split()[0]
    need(re.fullmatch(r'/dev/disk\d+(?:s\d+)*', device) is not None,
         'Sursa nu se afla pe un volum local identificabil: ' + device)
    return commands.plist(['/usr/sbin/diskutil', 'info', '-plist', device])


def observe_target(commands, repo, image, *, expected=None, post=False, hardware=None):
    info = commands.plist(['/usr/sbin/diskutil', 'info', '-plist', TARGET])
    disks = commands.plist(['/usr/sbin/diskutil', 'list', '-plist'])
    apfs = commands.plist(['/usr/sbin/diskutil', 'apfs', 'list', '-plist'])
    root = commands.plist(['/usr/sbin/diskutil', 'info', '-plist', '/'])
    sources = dict(repo=backing_info(commands, repo), image=backing_info(commands, image))
    proof = validate_disk_target(info, disks, apfs, root_info=root, source_infos=sources,
        expected_fingerprint=expected, require_initial_layout=not post,
        expected_hardware_fingerprint=hardware)
    return proof


def source_detached(commands, image):
    info = commands.plist(['/usr/bin/hdiutil', 'info', '-plist'])
    need(isinstance(info.get('images'), list), 'Nu pot verifica imaginile atasate')
    for entry in info['images']:
        path = entry.get('image-path')
        if path and (Path(path).resolve() == image or
                     (Path(path).is_file() and os.path.samefile(path, image))):
            raise RuntimeError('Imaginea sursa este atasata; demonteaz-o inainte de scriere')


def target_mounts(commands, proof):
    # APFS synthesized identifiers are taken from this fresh proof, never diskNECONFIGURAT by assumption.
    devices = {'diskNECONFIGURAT'}
    for container in proof.get('target_containers', []):
        if isinstance(container, str): devices.add(container)
        elif isinstance(container, dict):
            reference = container.get('ContainerReference') or container.get('container') or container.get('container_reference')
            if reference: devices.add(reference)
            for volume in container.get('Volumes', []):
                if volume.get('DeviceIdentifier'): devices.add(volume['DeviceIdentifier'])
    # A fresh APFS list also covers all current synthesized target volumes.
    listing = commands.plist(['/usr/sbin/diskutil', 'apfs', 'list', '-plist'])
    for container in listing.get('Containers', []):
        stores = [p.get('DeviceIdentifier','') for p in container.get('PhysicalStores', [])]
        if any(s.startswith('disk10s') for s in stores):
            devices.add(container['ContainerReference'])
            devices.update(v['DeviceIdentifier'] for v in container.get('Volumes', []))
    mounted = []
    lines = commands.run(['/sbin/mount']).splitlines()
    need(bool(lines), 'Lista punctelor de montare este goala')
    for line in lines:
        need(' on ' in line and ' (' in line and line.endswith(')'), 'Lista punctelor de montare este neinterpretabila')
        dev = line.split(' on ',1)[0].rsplit('@',1)[-1].removeprefix('/dev/')
        if any(dev == d or dev.startswith(d + 's') for d in devices):
            mounted.append(line)
    return mounted


def check_cancel(path):
    if path.exists():
        raise RuntimeError('Operatia a fost intrerupta la cererea utilizatorului')


def write_gpt(fd, layout, target_bytes):
    for offset, data in plan_gpt_relocation(layout, target_bytes, 512):
        view = memoryview(data)
        while view:
            count = os.pwrite(fd, view, offset)
            need(count > 0 and count % 512 == 0, 'Scriere GPT incompleta/nealiniata')
            offset += count; view = view[count:]
    receipt = flush_raw(fd)
    checked = validate_relocated_gpt(lambda off, n: os.pread(fd, n, off), target_bytes, layout)
    checked['flush'] = receipt
    return checked


def wait_for_copied_apfs(commands, layout, report):
    partition = next(p for p in layout.partitions if p['type_guid'] == GPT_APFS_TYPE)
    growth = apfs_growth_plan(layout, TARGET)
    last_error = None
    for attempt in range(12):
        try:
            part = commands.plist(['/usr/sbin/diskutil','info','-plist',growth['apfs_partition']])
            listing = commands.plist(['/usr/sbin/diskutil','apfs','list','-plist'])
            proof = validate_apfs_target(part, listing, partition, TARGET, expected_group_uuid=GROUP_UUID)
            need(proof['container_uuid'] == layout.apfs_identity['container_uuid'],
                 'UUID-ul containerului APFS nu este cel al imaginii copiate')
            return proof, part, listing
        except (ValueError, RuntimeError, KeyError) as error:
            last_error = str(error)
            if attempt == 0:
                print('    Astept identificarea containerului APFS copiat pe discul fizic.', flush=True)
            time.sleep(1)
    report['needs_reconnect'] = True
    raise RuntimeError('Copia si GPT sunt verificate, dar macOS inca nu identifica noul container APFS. '
        'Ejecteaza si reconecteaza discul, apoi ruleaza acelasi script; va continua finalizarea. Detaliu: ' + str(last_error))


def finish_disk(commands, repo, image, layout, manifest, report, save, work, hardware):
    observe_target(commands, repo, image, post=True, hardware=hardware)
    before, part_info, listing = wait_for_copied_apfs(commands, layout, report)
    target_bytes = report['target_bytes']
    source_part = next(p for p in layout.partitions if p['type_guid'] == GPT_APFS_TYPE)
    growth = apfs_growth_plan(layout, TARGET)
    # This UUID proof is required before diskutil is permitted to grow anything.
    report['copied_apfs_identity'] = before; save()
    print('4/5 Extind containerul APFS la capacitatea discului extern.', flush=True)
    expected_last_usable = target_bytes // 512 - layout.primary['entries_sectors'] - 2
    maximum = (expected_last_usable - source_part['first_lba'] + 1) * 512
    check_cancel(work / 'cancel')
    if 0 <= maximum - before['partition_bytes'] <= (1 << 20):
        print('    APFS foloseste deja capacitatea disponibila; reutilizez extinderea.', flush=True)
        report['apfs_growth_reused'] = True
    else:
        commands.run(growth['argv'], timeout=3600, live=True)
    check_cancel(work / 'cancel')
    part_info = commands.plist(['/usr/sbin/diskutil','info','-plist',growth['apfs_partition']])
    listing = commands.plist(['/usr/sbin/diskutil','apfs','list','-plist'])
    # Read the actual grown GPT; source first-LBA and UUID must remain unchanged.
    fd = os.open(RAW_TARGET, os.O_RDONLY)
    try:
        current = parse_gpt_layout(lambda off,n: os.pread(fd,n,off), target_bytes)
    finally:
        os.close(fd)
    need(current.primary['disk_guid_raw'] == layout.primary['disk_guid_raw']
         and current.primary['last_usable'] == expected_last_usable, 'GPT apartine altei imagini sau capacitati')
    for original in layout.partitions:
        matches = [part for part in current.partitions if part['index'] == original['index']]
        need(len(matches)==1 and all(matches[0][key]==original[key] for key in
             ('type_guid','partition_guid','first_lba')), 'Extinderea a schimbat identitatea partitiei')
        if original['type_guid']==GPT_EFI_TYPE:
            need(matches[0]['last_lba']==original['last_lba'], 'Extinderea a schimbat dimensiunea EFI')
    report['apfs_growth'] = validate_apfs_growth(before, part_info, listing, source_part, TARGET,
        target_bytes, current.primary['last_usable'], expected_group_uuid=GROUP_UUID)
    report['gpt_after_growth'] = current.report(); report['apfs_grown'] = True; save()
    check_cancel(work / 'cancel')
    print('5/5 Verific EFI-ul de pe disc si pregatesc deconectarea.', flush=True)
    observe_target(commands, repo, image, post=True, hardware=hardware)
    commands.run(['/usr/sbin/diskutil','unmountDisk',TARGET])
    esp = next(p for p in layout.partitions if p['type_guid'] == GPT_EFI_TYPE)
    device = 'disk10s' + str(esp['index'])
    where = work / 'efi-readonly'; where.mkdir(exist_ok=True)
    mounted = False
    try:
        commands.run(['/usr/sbin/diskutil','mount','readOnly','-mountOptions','nobrowse',
                      '-mountPoint',str(where),device])
        mounted = True
        actual = {}
        for top in ('EFI','System'):
            tree = where / top
            need(tree.is_dir() and not tree.is_symlink(), 'Radacina EFI lipsa: ' + top)
        for path in where.rglob('*'):
            need(not path.is_symlink(), 'Symlink in EFI-ul de pe disc')
            if path.is_file(): actual[path.relative_to(where).as_posix()] = file_hash(path)
        report['efi_verification'] = validate_efi_hashes(actual, manifest['files'])
        report['efi_verified'] = True; save()
    finally:
        if mounted:
            commands.run(['/usr/sbin/diskutil','unmount',str(where)])
    check_cancel(work / 'cancel')
    commands.run(['/usr/sbin/diskutil','eject',TARGET])
    report.update(step_complete=True, disk_ejected=True, boot_validated=False,
                  finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
    save()


def worker(request_path):
    need(os.geteuid() == 0 and sys.platform == 'darwin', 'Workerul de scriere necesita sesiunea sudo macOS')
    request_path = Path(request_path).resolve(strict=True)
    uid = int(os.environ.get('SUDO_UID', '-1'))
    need(uid > 0 and request_path.stat().st_uid == uid, 'Cererea nu apartine utilizatorului autorizat')
    request = load_json(request_path)
    repo = Path(request['repo']).resolve(strict=True)
    work = request_path.parent
    need(work.parent == repo/'store/tmp' and re.fullmatch(r'mbp91-step13-\d{8}-\d{6}-\d{6}',work.name),
         'Director worker neasteptat')
    need(request_path.name == 'request.json' and request['script_sha256'] == file_hash(Path(__file__)),
         'Scriptul sau cererea s-a schimbat')
    need(request['target'] == TARGET and request['image_sha256'] == IMAGE_SHA,
         'Tinta sau imagine diferita de cele autorizate')
    result_path = work / 'worker-result.json'
    report = dict(schema=VERSION, target=TARGET, target_bytes=request['target_bytes'],
        image_sha256=IMAGE_SHA, image=IMAGE_REL, commands=[], errors=[], step_complete=False,
        raw_written=False, raw_verified=False, gpt_relocated=False, apfs_grown=False,
        efi_verified=False, disk_ejected=False, boot_validated=False,
        hardware_fingerprint=request['hardware_fingerprint'], initial_target=request['target_proof'])
    save = lambda: save_json(result_path, report)
    commands = Commands(report, save)
    caffeinate = None
    cancel = work / 'cancel'
    try:
        previous = request.get('resume')
        if previous:
            need(previous.get('raw_verified') is True and previous.get('gpt_relocated') is True
                 and previous.get('image_sha256') == IMAGE_SHA
                 and previous.get('hardware_fingerprint') == request['hardware_fingerprint'],
                 'Raport anterior invalid pentru reluare')
            report.update({k:previous[k] for k in ('raw_written','raw_verified','gpt_relocated','copy','gpt_relocation')})
            report['resumed_finalization'] = True
            save()
        image, identity, layout, manifest = verified_source(repo)
        need(identity == request['source_identity'], 'Imaginea s-a schimbat dupa verificarea SHA256')
        report['source_apfs_identity'] = layout.apfs_identity
        source_detached(commands, image)
        previous = request.get('resume')
        if previous:
            need(previous.get('raw_verified') is True and previous.get('gpt_relocated') is True
                 and previous.get('image_sha256') == IMAGE_SHA
                 and previous.get('hardware_fingerprint') == request['hardware_fingerprint'],
                 'Raportul anterior nu permite continuarea fara rescriere')
            report.update({k:previous[k] for k in ('raw_written','raw_verified','gpt_relocated','copy','gpt_relocation')})
            report['resumed_finalization'] = True
            observe_target(commands, repo, image, post=True, hardware=request['hardware_fingerprint'])
            fd = os.open(RAW_TARGET, os.O_RDONLY)
            try:
                sector, capacity = device_geometry(fd)
                need(sector == 512 and capacity == request['target_bytes'], 'Dispozitivul a fost schimbat')
                # Growth may already have happened before an interruption; validate its UUIDs and tables.
                current = parse_gpt_layout(lambda off,n:os.pread(fd,n,off), capacity)
                need(current.primary['disk_guid_raw'] == layout.primary['disk_guid_raw'], 'Discul nu contine imaginea copiata')
                for original in layout.partitions:
                    matches = [p for p in current.partitions if p['index'] == original['index']]
                    need(len(matches)==1 and all(matches[0][k]==original[k] for k in
                         ('type_guid','partition_guid','first_lba')), 'Identitatea partitiei copiate difera')
            finally:
                os.close(fd)
            save()
        else:
            proof = observe_target(commands, repo, image, expected=request['target_proof']['fingerprint'])
            commands.run(['/usr/sbin/diskutil','unmountDisk',TARGET])
            proof = observe_target(commands, repo, image, expected=request['target_proof']['fingerprint'])
            need(not target_mounts(commands, proof), 'Discul are inca volume montate; scrierea nu a inceput')
            check_cancel(cancel)
            print('2/5 Scriu imaginea verificata pe /dev/diskNECONFIGURAT (256,1 GB).', flush=True)
            caffeinate = subprocess.Popen(['/usr/bin/caffeinate','-dims','-w',str(os.getpid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            source_fd = os.open(image, os.O_RDONLY)
            target_fd = None
            try:
                target_fd = os.open(RAW_TARGET, os.O_RDWR)
                node = os.fstat(target_fd)
                need(stat.S_ISCHR(node.st_mode) and node.st_rdev == os.stat(RAW_TARGET).st_rdev,
                     'Dispozitivul raw nu corespunde tintei selectate')
                sector, capacity = device_geometry(target_fd)
                need(sector==512 and capacity==request['target_bytes'], 'Geometria dispozitivului raw difera')
                need(source_identity(image)==identity and stat_identity(os.fstat(source_fd))==identity,
                     'Fisierul deschis nu corespunde imaginii sursa verificate')
                def progress(phase, done, total):
                    label = 'Scriere' if phase=='write' else 'Recitire'
                    if phase=='verify' and done==0:
                        print('3/5 Recitesc imaginea de pe disc si compar SHA256.', flush=True)
                    print('    %s: %.1f%% (%s / 85,9 GB).' % (label,100*done/total,
                          ('%.2f' % (done/1e9)).replace('.',',')), flush=True)
                def checkpoint(event, detail):
                    report['copy_event'] = event
                    report['copy_detail'] = detail
                    if event=='write_started': report['write_started']=True
                    if event=='write_complete': report['raw_written']=True
                    save()
                copy = stream_copy_and_verify(source_fd,target_fd,IMAGE_BYTES,IMAGE_SHA,progress,
                    checkpoint, cancel_check=lambda:check_cancel(cancel))
                report['copy'] = copy
                report['raw_verified'] = True
                report['raw_written'] = True
                validate_raw_restore(IMAGE_SHA,copy['readback_sha256'],IMAGE_BYTES,copy['bytes_verified'])
                save()
                check_cancel(cancel)
                print('    Copie verificata integral. Adaptez GPT la discul de 256,1 GB.', flush=True)
                report['gpt_relocation'] = write_gpt(target_fd,layout,capacity)
                report['gpt_relocated'] = True; save()
            finally:
                if target_fd is not None: os.close(target_fd)
                os.close(source_fd)
        check_cancel(cancel)
        finish_disk(commands,repo,image,layout,manifest,report,save,work,request['hardware_fingerprint'])
    except BaseException as error:
        report['errors'].append(dict(error=str(error) or type(error).__name__,traceback=traceback.format_exc()))
        report['step_complete']=False
        print('OPRIT: ' + (str(error) or type(error).__name__), flush=True)
    finally:
        save()
        if caffeinate is not None and caffeinate.poll() is None:
            caffeinate.terminate()
    return 0 if report['step_complete'] else 1


def execute_worker(script, request, log, work):
    if subprocess.run(['/usr/bin/sudo','-n','-v'],capture_output=True).returncode:
        print('    Introdu parola contului pentru scrierea pe discul extern.',flush=True)
        need(subprocess.run(['/usr/bin/sudo','-v']).returncode==0, 'Autorizarea sudo nu a reusit')
    argv=['/usr/bin/sudo','-n',sys.executable,'-I','-B',str(script),'--worker',str(request)]
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,start_new_session=False,process_group=0)
    decoder=codecs.getincrementaldecoder('utf-8')('replace')
    pulse=time.monotonic(); cancelled=False
    while True:
        try:
            ready,_,_=select.select([process.stdout],[],[],1)
            if ready:
                data=os.read(process.stdout.fileno(),65536)
                if data:
                    text=decoder.decode(data); print(text,end='',flush=True);log.write(text);log.flush()
                    pulse=time.monotonic()
                elif process.poll() is not None: break
            elif time.monotonic()-pulse>=30:
                print('    Operatia continua; log: local/mbp91/step13-build.log',flush=True)
                pulse=time.monotonic()
            if process.poll() is not None and not ready: break
        except KeyboardInterrupt:
            if not cancelled:
                (work/'cancel').write_text('cancel\n');cancelled=True
                print('\n    Solicit oprirea controlata a scrierii; astept inchiderea dispozitivului.',flush=True)
            else:
                print('    Astept confirmarea opririi workerului.',flush=True)
    trailing=decoder.decode(b'',final=True)
    if trailing: print(trailing,end='');log.write(trailing)
    return process.wait()


def make_archive(repo, work, report_path, logpath, state_path):
    target=Path.home()/'Desktop'/'HAO-mbp91-step13.zip'
    temporary=target.with_suffix('.partial.zip')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [report_path,logpath,state_path,work/'worker-result.json',work/'request.json']:
            if path.is_file(): archive.write(path,path.relative_to(repo).as_posix())
        archive.write(Path(__file__).resolve(),Path(__file__).name)
    os.replace(temporary,target)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args();sys.dont_write_bytecode=True
    if args.worker: return worker(args.worker)
    need(sys.platform=='darwin' and platform.machine()=='x86_64' and os.geteuid()!=0,
         'Ruleaza comanda indicata pe iMac, ca utilizator normal')
    repo=args.repo.expanduser().resolve(strict=True)
    local=repo/'local/mbp91'
    need((local/'step12-state.json').is_file(),'Ruleaza din Desktop/hao-patcher-mbp91')
    os.umask(0o022)
    with (local/'step13.running.lock').open('a+') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Pasul 13 ruleaza deja')
        stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        work=repo/'store/tmp'/('mbp91-step13-'+stamp);work.mkdir()
        result=local/'step13-result.json';state=local/'step13-state.json';logpath=local/'step13-build.log'
        previous=load_json(state) if state.is_file() else {}
        for path in (result,state,logpath):
            if path.is_file(): shutil.copy2(path,work/('previous-'+path.name))
        report=dict(schema=VERSION,target=TARGET,commands=[],errors=[],step_complete=False)
        with logpath.open('w',buffering=1) as log:
            try:
                print('1/5 Verific imaginea existenta si discul extern /dev/diskNECONFIGURAT.',flush=True)
                image,identity,layout,manifest=verified_source(repo)
                commands=Commands(report)
                resume=previous.get('worker')
                resumable=bool(resume and resume.get('raw_verified') and resume.get('gpt_relocated'))
                if resume and resume.get('step_complete'):
                    print('    Acest transfer este deja finalizat; raportul este pastrat.',flush=True)
                    report.update(step_complete=True,worker=resume,reused_completed_report=True)
                else:
                    proof=observe_target(commands,repo,image,post=resumable,
                        hardware=resume.get('hardware_fingerprint') if resumable else None)
                    source_detached(commands,image)
                    if resumable:
                        print('    Copia si GPT au fost verificate anterior; continui finalizarea APFS/EFI.',flush=True)
                    else:
                        print('    Destinatie confirmata: /dev/diskNECONFIGURAT, extern fizic, 256,1 GB. Continutul va fi inlocuit.',flush=True)
                        image,identity,layout,manifest=verified_source(repo,hash_image=True)
                    request=dict(repo=str(repo),target=TARGET,target_bytes=proof['capacity_bytes'],
                        image_sha256=IMAGE_SHA,source_identity=identity,target_proof=proof,
                        hardware_fingerprint=proof['hardware_fingerprint'],script_sha256=file_hash(Path(__file__)))
                    if resumable: request['resume']=resume
                    request_path=work/'request.json';save_json(request_path,request);request_path.chmod(0o600)
                    rc=execute_worker(Path(__file__).resolve(),request_path,log,work)
                    output=work/'worker-result.json'
                    if output.is_file():
                        report['worker']=load_json(output)
                        report['step_complete']=report['worker'].get('step_complete') is True and rc==0
                    else: raise RuntimeError('Workerul nu a produs raportul; cod '+str(rc))
            except (Exception,KeyboardInterrupt) as error:
                report['errors'].append(dict(error=str(error) or type(error).__name__,traceback=traceback.format_exc()))
                log.write(traceback.format_exc());print('OPRIT: '+(str(error) or type(error).__name__),flush=True)
            finally:
                report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat()
                save_json(result,report)
                # Preserve a prior verified transfer if a resumed preflight itself fails.
                if report.get('worker'): save_json(state,report)
                archive=make_archive(repo,work,result,logpath,state)
                outcome=report.get('worker',{})
                print('\nImagine scrisa pe discul extern: '+('DA' if outcome.get('raw_written') else 'NU'))
                print('Recitire integrala si SHA256: '+('DA' if outcome.get('raw_verified') else 'NU'))
                print('GPT adaptat la capacitatea discului: '+('DA' if outcome.get('gpt_relocated') else 'NU'))
                print('APFS extins: '+('DA' if outcome.get('apfs_grown') else 'NU'))
                print('EFI de pe disc verificat: '+('DA' if outcome.get('efi_verified') else 'NU'))
                print('Pasul 13 finalizat: '+('DA' if report['step_complete'] else 'NU'))
                if outcome.get('disk_ejected'): print('Discul este ejectat si poate fi mutat la MacBookPro9,1.')
                print('Boot validat: NU; urmeaza proba pe MacBook.')
                print('Arhiva MICA de trimis: '+str(archive))
        return 0 if report['step_complete'] else 1


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print('OPRIT: '+str(error),file=sys.stderr);raise SystemExit(1)
