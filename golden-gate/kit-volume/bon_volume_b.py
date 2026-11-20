"""Verifică identitățile partițiilor din bonul privat de personalizare B."""
import json
from pathlib import Path
import runpy

preview = runpy.run_path(str(Path(__file__).with_name('Pregateste-fstab.py')))
FILESYSTEMS = ('NTFS', 'exFAT')
MODES = {'ambele': FILESYSTEMS, 'ntfs': ('NTFS',), 'exfat': ('exFAT',), 'revenire': ()}


def unique_keys(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError('Bonul conține chei duplicate.')
    return obj


def requested_rules(receipt, mode):
    data = json.loads(receipt, object_pairs_hook=unique_keys)
    if not isinstance(data, dict) or data.get('format') != 1 or data.get('status') != 'complete':
        raise ValueError('Este necesar bonul complet de personalizare B, format 1.')
    volumes = data.get('noauto')
    if not isinstance(volumes, dict) or set(volumes) != set(FILESYSTEMS):
        raise ValueError('Bonul trebuie să identifice separat NTFS și exFAT.')
    rules = {}
    for fs in FILESYSTEMS:
        value = volumes[fs]
        if not isinstance(value, str) or not value.isascii():
            raise ValueError('UUID nevalid pentru ' + fs)
        uuid = preview['volume_id'](b'UUID=' + value.encode('ascii'))
        if not uuid or uuid in rules:
            raise ValueError('UUID absent, nevalid sau duplicat pentru ' + fs)
        rules[uuid] = b'ro,auto' if fs in MODES[mode] else b'ro,noauto'
    return rules
