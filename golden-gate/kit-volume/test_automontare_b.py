"""Exerciții de revenire cu fișiere temporare și inventare simulate."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('automontare_b', Path(__file__).with_name('Automontare-B.py'))
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
volumes = {'NTFS': 'AAAA', 'exFAT': 'BBBB'}
base = b'# local\r\nUUID=aaaa none auto noauto,ro 0 0 # NTFS\r\nUUID=BBBB none auto ro,noauto 0 0\n'


class ChangingRules(unittest.TestCase):
    def test_exact_rollback_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            mount = Path(temp).resolve()
            path = mount / 'private/etc/fstab'
            path.parent.mkdir(parents=True)
            path.write_bytes(base)
            # User-owned temporary files stand in for root-owned B files.
            with mock.patch.object(boot, 'FSTAB_OWNER', os.getuid()):
                for undo in (False, False, True, True):
                    boot.apply(mount, volumes, undo)
                    self.assertEqual(path.read_bytes(), base if undo else
                                     base.replace(b'noauto,ro', b'ro,auto').replace(b'ro,noauto', b'ro,auto'))
                path.write_bytes(base + b'# edit ulterior')
                with self.assertRaisesRegex(ValueError, 'diferă'):
                    boot.apply(mount, volumes, False)
                self.assertTrue(path.read_bytes().endswith(b'edit ulterior'))

    def test_missing_and_duplicate_rules(self):
        for data in [base.splitlines(keepends=True)[-1], base + base]:
            with self.assertRaises(ValueError):
                boot.convert(data, {b'UUID=AAAA', b'UUID=BBBB'}, b'ro,noauto', b'ro,auto')
