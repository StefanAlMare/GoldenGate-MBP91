import contextlib
import io
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

path = Path(__file__).with_name('Probeaza-volume-B.py')
spec = importlib.util.spec_from_file_location('probe', path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
targets = {fs: (fs + '-uuid', fs, dev, 'disk4') for fs, dev in zip(probe.KINDS, ('disk4s3', 'disk4s6'))}


class Trial(unittest.TestCase):
    def simulate(self, mode, initial=(), fail=None, timeout=None, no_file=False):
        mounted = set(initial)
        actions = []
        def op(action, *args):
            node = args[-1]
            fs = next(k for k, t in targets.items() if t[2] == node)
            actions.append((action, fs))
            if (action, fs) == timeout:
                raise subprocess.TimeoutExpired('diskutil', 40)
            if (action, fs) == fail: return 1
            if action == 'mount':
                self.assertEqual(args, ('readOnly', node))
                mounted.add(fs)
            else:
                mounted.remove(fs)
            return 0
        def status(_uuid, fs, node, _parent):
            return {'DeviceIdentifier': node, 'Mounted': fs in mounted,
                    'MountPoint': '/Volumes/' + fs if fs in mounted else None}
        def mounted_info(path):
            return {'DeviceIdentifier': targets[path.split('/')[-1]][2]}
        def verify(target, sample):
            self.assertIn(target[1], mounted)
            return '/Volumes/' + target[1], True, 0 if no_file or not sample else 120
        log = io.StringIO()
        with patch.object(probe, 'identity', side_effect=status), patch.object(probe, 'operation', side_effect=op), \
             patch.object(probe, 'verify', side_effect=verify), patch.object(probe, 'info', side_effect=mounted_info), \
             contextlib.redirect_stdout(log):
            code = probe.trial(targets, mode)
        return code, actions, mounted, log.getvalue()

    def test_coexist_then_reverse_cleanup(self):
        code, actions, left, log = self.simulate('ambele')
        self.assertEqual((code, left), (0, set()))
        self.assertEqual(actions, [('mount','NTFS'),('mount','exFAT'),('unmount','exFAT'),('unmount','NTFS')])
        self.assertIn('ambele confirmate', log)

    def test_postboot_only_reads_existing_mounts(self):
        with patch.object(probe.subprocess, 'check_output', return_value='boot'), \
             patch.object(Path, 'read_text', return_value=''), \
             patch.object(probe, 'fstab_options'), patch.object(probe, 'discover', return_value=targets), \
             patch.object(probe, 'identity'), patch.object(probe, 'mounted', side_effect=['', '/Volumes/Test']), \
             patch.object(probe, 'verify', return_value=('/Volumes/Test', True, 4096)) as read, \
             patch.object(probe, 'operation') as mutate, contextlib.redirect_stdout(io.StringIO()) as log:
            self.assertEqual(probe.after_boot({}), 3)
            read.assert_called_once_with(targets['exFAT'], True)
            mutate.assert_not_called()
            self.assertIn('nemontat', log.getvalue())
            self.assertIn('citire=4096', log.getvalue())

    def test_journal_uses_macbook_clock_and_limits_attribution(self):
        import json
        from types import SimpleNamespace
        fsstat = SimpleNamespace(st_ino=7, st_mtime=98.0, st_mtime_ns=98000000000)
        entries = [{'timestamp':'t', 'eventMessage':msg, 'bootUUID':bid, 'process':'diskarbitrationd'}
                   for msg,bid in [('exfat: probe skipped', 'B'), ('mount disk4s3 failed', 'B'),
                                   ('probe failed disk4s30', 'B'), ('another boot', 'X')]]
        events = b'\n'.join(json.dumps(e).encode() for e in entries)
        replies = [SimpleNamespace(returncode=0, stdout=events), SimpleNamespace(stdout='B')]
        uuids = {fs: t[0] for fs, t in targets.items()}
        with patch.object(probe.subprocess, 'check_output', return_value='{ sec = 100, usec = 125000 }'), \
             patch.object(probe.time, 'time', return_value=500), patch.object(Path, 'stat', return_value=fsstat), \
             patch.object(Path, 'read_text', return_value=''), patch.object(probe, 'discover', return_value=targets), \
             patch.object(probe.subprocess, 'run', side_effect=replies) as run, \
             patch.object(probe, 'operation') as mutate, contextlib.redirect_stdout(io.StringIO()) as log:
            self.assertEqual(probe.boot_journal(uuids), 0)
            self.assertEqual(run.call_args_list[0].args[0][:2], ['/usr/bin/log', 'show'])
            mutate.assert_not_called()
            lines = log.getvalue()
            for fragment in ('-2.125 s', 'NTFS disk4s3 | t', 'exFAT (format) | t', 'serviciu, volum neidentificat | t'):
                self.assertIn(fragment, lines)
            self.assertNotIn('another boot', lines)

    def test_preserve_initial_and_inspection(self):
        self.assertEqual(self.simulate('inventar', ['exFAT'])[:3], (0, [], {'exFAT'}))
        self.assertEqual(self.simulate('ambele', ['exFAT'])[:3],
                         (0, [('mount','NTFS'),('unmount','NTFS')], {'exFAT'}))

    def test_partial_failure(self):
        code, actions, left, log = self.simulate('ambele', fail=('mount','exFAT'))
        self.assertEqual((code,left), (3,set()))
        self.assertEqual(actions[-1], ('unmount','NTFS'))
        self.assertNotIn('ambele confirmate', log)
        self.assertEqual(self.simulate('ambele', no_file=True)[0], 3)

    def test_timeout_stops_new_operations(self):
        code, actions, left, log = self.simulate('ambele', timeout=('mount','exFAT'))
        self.assertEqual((code, actions, left), (3, [('mount', 'NTFS'), ('mount', 'exFAT')], {'NTFS'}))
        self.assertIn('incert', log)

    def test_mount_response_and_timeout_stage(self):
        log = io.StringIO()
        error = b'Error mounting /Volumes/PrivateLabel (com.apple.DiskManagement.disenter error 49218.)'
        with contextlib.redirect_stdout(log), patch.object(probe.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, b'', error)
            self.assertEqual(probe.operation('mount', 'readOnly', 'disk4s6'), 1)
            timeout = run.call_args.kwargs['timeout']
            self.assertIn('readOnly', run.call_args.args[0])
            probe.report_timeout(subprocess.TimeoutExpired([probe.DISK, 'mount', 'readOnly', 'disk4s6'], timeout))
            probe.report_timeout(subprocess.TimeoutExpired([probe.DISK, 'info', '-plist', '/Volumes/PrivateLabel'], 8))
        text = log.getvalue()
        for fragment in ('cerere mount readOnly disk4s6', 'răspuns mount disk4s6 cod=1',
                         'durată=', 'cod suplimentar=49218', f'expirare în diskutil mount disk4s6 după {timeout}s',
                         'expirare în diskutil info după 8s'):
            self.assertIn(fragment, text)
        self.assertNotIn('PrivateLabel', text)

    def test_conflicting_or_external_partitions(self):
        parent = dict(Internal=False, WholeDisk=True, DeviceIdentifier='disk4')
        child = dict(DeviceIdentifier='disk4s3', WholeDisk=False, ParentWholeDisk='disk4',
                     VolumeUUID='A', Content='Microsoft Basic Data', FilesystemType='ntfs')
        with patch.object(probe, 'info', side_effect=[child, parent]):
            with self.assertRaises(ValueError): probe.identity('A','NTFS','disk4s3','disk4')
        parent['Internal'] = True
        child['FilesystemName'] = 'exFAT'
        with patch.object(probe, 'info', side_effect=[child, parent]):
            with self.assertRaises(ValueError): probe.identity('A','NTFS','disk4s3','disk4')

    def test_launcher_payload_without_connecting(self):
        import os
        import sys
        args = {'exFAT': "test'1", 'NTFS': 'test-2'}
        script = probe.remote_script("import sys,json; print(sys.argv[1], sorted(json.loads(sys.argv[2])))",
                                     'exit 0', 'ambele', args)
        # Run only the synthetic gate and receiver. No diskutil or SSH is called.
        script = script.replace('/usr/local/lib/hao/python/bin/python3.12', sys.executable)
        p = subprocess.run(['/bin/bash','-s'], input=script.encode(), capture_output=True, check=True)
        self.assertIn(b"ambele ['NTFS', 'exFAT']", p.stdout)
        sample = probe.READ_SAMPLE
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            data = b'X' * 10000
            (folder/'original').write_bytes(data)
            (folder/'link').symlink_to(folder/'original')
            # Replace only filesystem identity/readonly queries so a temp folder
            # represents the test mount. The actual safe file open/read still runs.
            sample = sample.replace("unit == os.stat(os.path.dirname(root)).st_dev", 'False')
            sample = sample.replace('not os.fstatvfs(fd).f_flag & os.ST_RDONLY', 'False')
            args = [sys.executable,'-IB','-c',sample,root,'da']
            self.assertEqual(subprocess.check_output(args).strip(), b'ro 4096')
            (folder/'original').rename(folder/'.hidden')
            (folder/'link').unlink()
            (folder/'link').symlink_to(folder/'.hidden')
            self.assertEqual(subprocess.check_output(args).strip(), b'ro 0')

    def test_passive_components(self):
        import ctypes
        ids = {'NTFS': '11111111-2222-3333-4444-555555555555',
               'exFAT': 'AAAAAAAA-0000-0000-0000-BBBBBBBBBBBB'}
        text = (f"UUID={ids['NTFS']} none auto noauto,ro 0 0\n"
                f"uuid={ids['exFAT'].lower()} none auto ro,auto 0 0\n"
                "# commentaire\nLABEL=other none auto rw 0 0\n")
        lib = MagicMock()
        lib._dyld_get_image_header.return_value = (ctypes.c_uint32 * 2)(0xfeedfacf, 0x01000007)
        lib._dyld_shared_cache_contains_path.side_effect = [True, False]
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            probe.fstab_options(text, ids)
            probe.cache_status(lib)
            probe.cache_status(object())
        lines = log.getvalue()
        for uuid in ids.values(): self.assertNotIn(uuid, lines.upper())
        for fragment in ('NTFS fstab reguli=1 opțiuni=noauto,ro','exFAT fstab reguli=1 opțiuni=ro,auto',
                         'livefiles_ntfs.dylib prezent', 'livefiles_exfat.dylib absent','API dyld indisponibil'):
            self.assertIn(fragment, lines)
        contains = lib._dyld_shared_cache_contains_path
        self.assertEqual(contains.argtypes, [ctypes.c_char_p])
        self.assertIs(contains.restype, ctypes.c_bool)
        self.assertEqual([c.args[0] for c in contains.call_args_list], [
            f'/System/Library/Filesystems/{name}.fs/Contents/Resources/livefiles_{name}.dylib'.encode()
            for name in ('ntfs', 'exfat')])
        with patch.object(probe, 'components', return_value=0), patch.object(probe, 'discover') as discover, \
             patch.object(probe, 'operation') as operation:
            self.assertEqual(probe.remote('componente', ids), 0)
            discover.assert_not_called()
            operation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
