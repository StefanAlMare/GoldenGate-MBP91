import contextlib
import importlib.util
import io
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NEW_DIR = Path(os.environ.get("AB19_KIT_DIR", str(ROOT / "ab19")))


def importer(name, directory):
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / "ab.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old = importer("old_ntfs", ROOT / "ab18")
new = importer("both_fstab", NEW_DIR)
NTFS = b"UUID=00000000-0000-4000-8000-00000000000A none auto ro,noauto 0 0"
EXFAT = b"UUID=00000000-0000-4000-8000-000000000003 none auto ro,noauto 0 0"
ERR = (OSError, ValueError, RuntimeError)


def snapshot(folder):
    result = {}
    for p in folder.iterdir():
        s = p.lstat()
        payload = p.readlink() if p.is_symlink() else p.read_bytes()
        result[p.name] = (s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_mtime_ns, s.st_nlink, payload)
    return result


class Verify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.etc = self.root / "private/etc"
        self.etc.mkdir(parents=True)
        self.f = self.etc / "fstab"
        self.external = self.root / "sentinel"
        self.external.write_bytes(b"must survive exact")
        self.labels = ("Windows", "Shared Files")

    def ab(self, action):
        return new.manage(self.root, action, self.labels)

    def ntfs(self, action):
        return old.manage(self.root, action, self.labels[0])

    def assert_roundtrip(self, baseline, initial, mode=0o640):
        if initial is not None:
            self.f.write_bytes(initial)
            self.f.chmod(mode)
            try:
                os.setxattr(self.f, "com.apple.ggfixture", b"persistent")
            except (AttributeError, OSError):
                pass
        original = snapshot(self.etc)
        if baseline:
            self.ntfs("enable")
        previous = snapshot(self.etc)
        self.ab("verify")
        self.assertEqual(previous, snapshot(self.etc))
        self.ab("enable")
        first = snapshot(self.etc)
        if baseline:
            for name in (old.RECEIPT, old.BACKUP):
                if name in previous:
                    self.assertEqual(previous[name], first[name])
        rows = self.f.read_bytes().splitlines()
        self.assertEqual(1, rows.count(NTFS))
        self.assertEqual(1, rows.count(EXFAT))
        self.assertEqual(0o644 if initial is None else mode, stat.S_IMODE(self.f.stat().st_mode))
        self.ab("enable")
        self.ab("verify")
        self.assertEqual(first, snapshot(self.etc))
        self.ab("remove")
        self.assertEqual(previous, snapshot(self.etc))
        self.ab("remove")
        self.assertEqual(previous, snapshot(self.etc))
        if baseline:
            self.ntfs("verify")
            self.ntfs("remove")
        self.assertEqual(original, snapshot(self.etc))

    def test_old_missing_fstab(self):
        self.assert_roundtrip(True, None)

    def test_old_empty_fstab(self):
        self.assert_roundtrip(True, b"")

    def test_old_CRLF(self):
        self.assert_roundtrip(True, b"# fixture\r\nLABEL=disk\\040box none auto ro,noauto 0 0")

    def test_without_old_missing_fstab(self):
        self.assert_roundtrip(False, None)

    def test_without_old_original_fstab(self):
        self.assert_roundtrip(False, b"# original\nUUID=DEAD-BEEF none auto rw")

    def test_independent_old_remove_active_new(self):
        self.ntfs("enable")
        self.ab("enable")
        initial = snapshot(self.etc)
        with self.assertRaises(ERR):
            self.ntfs("remove")
        self.assertEqual(initial, snapshot(self.etc))
        self.ab("remove")
        self.ntfs("remove")

    def test_symlink_leaves(self):
        for name in ("fstab", new.RECEIPT, new.BACKUP):
            p = self.etc / name
            with self.subTest(name=name):
                p.symlink_to(self.external)
                before = snapshot(self.etc)
                with self.assertRaises(ERR):
                    self.ab("enable")
                self.assertEqual(before, snapshot(self.etc))
                self.assertEqual(b"must survive exact", self.external.read_bytes())
                p.unlink()

    def test_hardlink_leaves(self):
        for name in ("fstab", new.RECEIPT, new.BACKUP):
            p = self.etc / name
            with self.subTest(name=name):
                os.link(self.external, p)
                before = snapshot(self.etc)
                with self.assertRaises(ERR):
                    self.ab("enable")
                self.assertEqual(before, snapshot(self.etc))
                self.assertEqual(b"must survive exact", self.external.read_bytes())
                p.unlink()

    def test_altered_after_enable_is_preserved(self):
        self.ntfs("enable")
        self.ab("enable")
        self.f.write_bytes(self.f.read_bytes() + b"# operator\n")
        before = snapshot(self.etc)
        for action in ["remove", "enable"]:
            with self.assertRaises(ERR):
                self.ab(action)
            self.assertEqual(before, snapshot(self.etc))

    def test_managed_baseline_journal_rejects_symlink(self):
        self.ntfs("enable")
        mark = self.etc / old.RECEIPT
        preserve = self.root / "elsewhere"
        mark.rename(preserve)
        mark.symlink_to(preserve)
        before = snapshot(self.etc)
        with self.assertRaises(ERR):
            self.ab("enable")
        self.assertEqual(before, snapshot(self.etc))

    def test_interruption_and_resume(self):
        for baseline in (False, True):
            for action in ("remove", "enable"):
                with self.subTest(baseline=baseline, action=action):
                    self.f.write_bytes(b"# preexisting data")
                    if baseline:
                        self.ntfs("enable")
                    previous = snapshot(self.etc)
                    with patch.object(new, "install_text", side_effect=OSError("fixture only")):
                        with self.assertRaises(OSError):
                            self.ab("enable")
                    self.ab("verify")
                    self.ab(action)
                    self.ab("remove")
                    self.assertEqual(previous, snapshot(self.etc))
                    if baseline:
                        self.ntfs("remove")
                    self.f.unlink()

    def test_interrupted_v2_refused_and_preserved(self):
        self.f.write_bytes(b"# before v2")
        with patch.object(old, "install_text", side_effect=OSError("fixture only")):
            with self.assertRaises(OSError):
                self.ntfs("enable")
        before = snapshot(self.etc)
        with self.assertRaises(ERR):
            self.ab("enable")
        self.assertEqual(before, snapshot(self.etc))
        self.ntfs("remove")

    def test_directory_symlink(self):
        real = self.root / "somewhere"
        self.etc.rename(real)
        self.etc.symlink_to(real)
        with self.assertRaises(ERR):
            self.ab("enable")
        self.assertFalse(list(real.iterdir()))

    def test_refuse_overlapping_unmanaged_rule(self):
        for rule in (EXFAT, NTFS, b"LABEL=Shared\\040Files none exfat rw 0 0"):
            with self.subTest(rule=rule):
                self.f.write_bytes(rule + b"\n")
                before = snapshot(self.etc)
                with self.assertRaises(ERR):
                    self.ab("enable")
                self.assertEqual(before, snapshot(self.etc))


class Identity(unittest.TestCase):
    def invoke(self, corrupt=None):
        # Device names and order deliberately differ from the capture.
        inf = {
            "disk908": {"DeviceIdentifier":"disk908", "Internal":True,"WholeDisk":True,"VirtualOrPhysical":"Physical"},
        }
        list_parts = []
        for (idx, gpt, uuid, kind, size, label) in [
            (5,"00000000-0000-4000-8000-000000000008","00000000-0000-4000-8000-000000000003","exfat",409250824192,"Shared Files"),
            (8,"00000000-0000-4000-8000-000000000007","00000000-0000-4000-8000-00000000000A","ntfs",213821423616,"Windows"),
        ]:
            node = f"disk8s{idx}"
            inf[node] = {"DeviceIdentifier":node,"ParentWholeDisk":"disk908","Internal":True,"WholeDisk":False,
                         "DiskUUID":gpt,"VolumeUUID":uuid,"FilesystemType":kind,"FileSystemPersonality":kind,
                         "VolumeName":label,"TotalSize":size - 512,"IOKitSize":size}
            list_parts.append({"DeviceIdentifier":node,"DiskUUID":gpt,"VolumeUUID":uuid,"Size":size})
        if corrupt:
            corrupt(inf,list_parts)
        tree = {"AllDisksAndPartitions":[{"DeviceIdentifier":"disk908", "Partitions":list_parts}]}
        def ro_read(*args, **kwargs):
            raise AssertionError(("unexpected read outside fixture",args))
        with patch.object(new,"run",return_value=plistlib.dumps(tree)), patch.object(new,"info",side_effect=inf.__getitem__), patch("builtins.open",side_effect=ro_read), contextlib.redirect_stdout(io.StringIO()):
            return new.candidates()

    def test_both_valid(self):
        self.assertEqual(set(self.invoke()),{"Windows","Shared Files"})

    def test_wrong_volume_uuid_with_matching_gpt(self):
        for node in ("disk908s5","disk908s8"):
            with self.subTest(node=node), self.assertRaises(ERR):
                self.invoke(lambda inf,parts: inf[node].update(VolumeUUID="00000000-0000-4000-8000-000000000001"))

    def test_conflicting_list_versus_detail(self):
        with self.assertRaises(ERR):
            self.invoke(lambda inf,parts: parts[0].update(VolumeUUID="00000000-0000-4000-8000-000000000001"))

    def test_wrong_gpt(self):
        def patch_both(inf,parts):
            inf["disk908s5"]["DiskUUID"] = parts[0]["DiskUUID"] = "00000000-0000-4000-8000-000000000001"
        with self.assertRaises(ERR):
            self.invoke(patch_both)

    def test_external_physical(self):
        with self.assertRaises(ERR):
            self.invoke(lambda inf,parts: inf["disk908"].update(Internal=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
