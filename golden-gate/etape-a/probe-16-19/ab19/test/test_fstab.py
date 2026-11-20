import importlib.util
import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch


BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import ab
v2_spec = importlib.util.spec_from_file_location('baseline_v2', BASE.parent / 'ab18' / 'ab.py')
v2 = importlib.util.module_from_spec(v2_spec)
v2_spec.loader.exec_module(v2)


def snapshot(etc):
    return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_uid, p.stat().st_gid, p.stat().st_ino,
                     p.stat().st_mtime_ns) for p in etc.iterdir()}


class Combined(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.etc = self.root / 'private' / 'etc'
        self.etc.mkdir(parents=True)
        self.fstab = self.etc / 'fstab'

    def manage(self, action, labels=()):
        return ab.manage(self.root, action, labels)

    def test_states(self):
        for baseline in (False, True):
            for original in (None, b'', b'# user', b'# CRLF\r\nLABEL=other none auto rw\r\n'):
                with self.subTest(v2=baseline, original=original):
                    if original is not None:
                        self.fstab.write_bytes(original)
                        self.fstab.chmod(0o640)
                    original_state = snapshot(self.etc)
                    if baseline:
                        v2.manage(self.root, 'enable')
                    before = snapshot(self.etc)
                    self.manage('verify')
                    self.assertEqual(before, snapshot(self.etc))
                    self.manage('enable')
                    active = self.fstab.read_bytes()
                    self.assertEqual(active.count(ab.NTFS.rule), 1)
                    self.assertEqual(active.count(ab.EXFAT.rule), 1)
                    self.assertTrue(active.endswith(original or b''))
                    self.manage('enable')
                    self.assertIn('activă', self.manage('verify'))
                    if baseline:
                        with self.assertRaises(RuntimeError):
                            v2.manage(self.root, 'remove')
                    self.manage('remove')
                    self.manage('remove')
                    self.assertEqual(snapshot(self.etc), before)
                    if baseline:
                        v2.manage(self.root, 'verify')
                        v2.manage(self.root, 'remove')
                    self.assertEqual(snapshot(self.etc), original_state)
                    self.fstab.unlink(missing_ok=True)

    def test_edit_detected(self):
        self.manage('enable')
        with self.fstab.open('ab') as out:
            out.write(b'# edit')
        before = snapshot(self.etc)
        with self.assertRaises(RuntimeError):
            self.manage('remove')
        self.assertEqual(snapshot(self.etc), before)

    def test_v2_original_mode_changed(self):
        self.fstab.write_bytes(b'initial')
        self.fstab.chmod(0o640)
        v2.manage(self.root, 'enable')
        (self.etc / ab.V2_BACKUP).chmod(0o666)
        before = snapshot(self.etc)
        with self.assertRaisesRegex(RuntimeError, 'Permisiunile'):
            self.manage('enable')
        self.assertEqual(before, snapshot(self.etc))

    def test_v2_modified(self):
        v2.manage(self.root, 'enable')
        self.manage('enable')
        with (self.etc / ab.V2_RECEIPT).open('ab') as out:
            out.write(b' ')
        before = snapshot(self.etc)
        with self.assertRaises(RuntimeError):
            self.manage('remove')
        self.assertEqual(snapshot(self.etc), before)

    def test_interruption_after_backup(self):
        for apply in (True, False):
            for resume in ('enable', 'remove'):
                with self.subTest(v2=apply, resume=resume):
                    self.fstab.write_bytes(b'original')
                    if apply:
                        v2.manage(self.root, 'enable')
                    before = snapshot(self.etc)
                    with patch.object(ab, 'install_text', side_effect=OSError('simulated interruption')):
                        with self.assertRaises(OSError):
                            self.manage('enable')
                    self.manage(resume)
                    self.manage('remove')
                    self.assertEqual(snapshot(self.etc), before)
                    if apply:
                        v2.manage(self.root, 'remove')

    def test_manual_rule_and_alias_not_overridden(self):
        for rule in (ab.NTFS.rule, ab.EXFAT.rule, b'LABEL=My\\040Files none exfat rw'):
            self.fstab.write_bytes(rule)
            before = snapshot(self.etc)
            with self.assertRaises((ValueError, RuntimeError)):
                self.manage('enable', ('Win', 'My Files'))
            self.assertEqual(snapshot(self.etc), before)

    def test_symlink_refused(self):
        self.fstab.symlink_to('/example')
        with self.assertRaises(RuntimeError):
            self.manage('enable')


class Disks(unittest.TestCase):
    def setUp(self):
        self.tree = {'AllDisksAndPartitions': [{'DeviceIdentifier': 'disk908', 'Partitions': []}]}
        self.info = {'disk908': {'Internal': True, 'WholeDisk': True, 'VirtualOrPhysical': 'Physical'}}
        for vol, node, label in zip(ab.VOLUMES, ('disk908s3','disk908s6'), ('Windows', 'Shared')):
            self.info[node] = dict(DeviceIdentifier=node, DiskUUID=vol.gpt, VolumeUUID=vol.uuid,
                                   ParentWholeDisk='disk908', TotalSize=vol.size - 512,
                                   FilesystemType=vol.kind.lower(), VolumeName=label)
            self.tree['AllDisksAndPartitions'][0]['Partitions'].append(dict(DeviceIdentifier=node, Size=vol.size))

    def identify(self):
        with patch.object(ab, 'run', return_value=plistlib.dumps(self.tree)), patch.object(ab, 'info', side_effect=self.info.__getitem__):
            return ab.candidates()

    def test_distinct_bsd_names_and_geometry_fields(self):
        with patch('builtins.open', side_effect=AssertionError('raw access not expected')):
            self.assertEqual(self.identify(), ('Windows', 'Shared'))

    def test_gpt_missing_or_duplicate(self):
        parts = self.tree['AllDisksAndPartitions'][0]['Partitions']
        parts.pop()
        with self.assertRaises(RuntimeError):
            self.identify()
        parts.extend([dict(DeviceIdentifier='disk908s6')] * 2)
        with self.assertRaises(RuntimeError):
            self.identify()

    def test_wrong_uuid_in_list(self):
        self.tree['AllDisksAndPartitions'][0]['Partitions'][1]['VolumeUUID'] = ab.NTFS.uuid
        with self.assertRaisesRegex(RuntimeError, 'VolumeUUID'):
            self.identify()

    def test_other_parent(self):
        self.info['disk908s3']['ParentWholeDisk'] = 'disk901'
        with self.assertRaisesRegex(RuntimeError, 'părinte'):
            self.identify()

    def test_external(self):
        self.info['disk908']['Internal'] = False
        with self.assertRaisesRegex(RuntimeError, 'fizic intern'):
            self.identify()

    def test_fallback_read_signature_then_size(self):
        self.info['disk908s6']['VolumeUUID'] = ''
        sector = bytearray(4096)
        sector[3:11] = ab.EXFAT.signature
        sector[510:512] = b'\x55\xaa'
        with patch('builtins.open', mock_open(read_data=bytes(sector))) as raw:
            self.assertEqual(self.identify(), ('Windows', 'Shared'))
            raw.assert_called_once_with('/dev/rdisk908s6', 'rb', buffering=0)
        self.tree['AllDisksAndPartitions'][0]['Partitions'][1]['Size'] = 1024
        for count in (ab.EXFAT.size // 512, 999):
            values = [ab.struct.pack('=I',512), ab.struct.pack('=Q',count)]
            with patch('builtins.open', mock_open(read_data=bytes(sector))), patch.object(ab.fcntl, 'ioctl', side_effect=values):
                if count == 999:
                    with self.assertRaisesRegex(RuntimeError, 'octeți fizici'):
                        self.identify()
                else:
                    self.assertEqual(self.identify(), ('Windows', 'Shared'))
        with patch('builtins.open', mock_open(read_data=b'wrong')):
            with self.assertRaisesRegex(RuntimeError, 'exFAT'):
                self.identify()


if __name__ == '__main__':
    unittest.main()
