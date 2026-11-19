import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().with_name('Pregateste-fstab.py')
A = b'01234567-89AB-CDEF-0123-456789ABCDEF'
B = b'12345678-9ABC-DEF0-1234-56789ABCDEF0'


def rule(identifier):
    return b'UUID=' + identifier + b' none auto ro,noauto 0 0'


class PreviewTests(unittest.TestCase):
    def run_tool(self, plan, base=None, destination='stdout', language=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'plan'
            source.write_bytes(plan)
            cmd = [sys.executable, str(TOOL), '--plan', str(source)]
            if language:
                cmd += ['--lang', language]
            current = folder / 'copy'
            if base is None:
                cmd += ['--empty']
            else:
                current.write_bytes(base)
                cmd += ['--base', str(current)]
            if destination == 'stdout':
                result = subprocess.run(cmd, capture_output=True)
            else:
                with current.open('ab') as alias:
                    result = subprocess.run(cmd, stdout=alias, stderr=subprocess.PIPE)
            self.assertEqual(source.read_bytes(), plan)
            if base is not None:
                self.assertEqual(current.read_bytes(), base)
            return result

    def test_empty(self):
        p = rule(A) + b'\n' + rule(B) + b'\n'
        result = self.run_tool(p)
        self.assertEqual((result.returncode, result.stdout), (0, p))

    def test_languages(self):
        self.assertIn(b'The plan contains no UUIDs.', self.run_tool(b'').stderr)
        self.assertIn('Planul nu conține niciun UUID.'.encode(), self.run_tool(b'', language='ro').stderr)
        self.assertEqual(self.run_tool(rule(A), language='ro').stdout, self.run_tool(rule(A)).stdout)

    def test_existing_crlf(self):
        base = b'# user comment\r\n' + rule(A.lower()) + b'   # existing'
        result = self.run_tool(rule(A) + b'\n' + rule(B), base)
        self.assertEqual((result.returncode, result.stdout), (0, rule(B) + b'\r\n' + base))

    def test_unrelated_uuid(self):
        original = b'UUID=' + B + b' /share apfs ro 0 2'
        result = self.run_tool(rule(A), original)
        self.assertEqual(result.stdout, rule(A) + b'\n' + original)

    def test_conflicts(self):
        for base in (rule(A) + b'\n' + rule(A), rule(A).replace(b'ro,noauto', b'rw'),
                     b'LABEL=Foo none auto ro,noauto 0 0', b'/dev/disk0s6 /share exfat rw 0 0'):
            with self.subTest(base=base):
                r = self.run_tool(rule(A), base)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, b'')

    def test_invalid_plans(self):
        for plan in (b'', b'# only', rule(A) + b'\n' + rule(A), rule(A).replace(b'noauto', b'auto'),
                     b'UUID=broken none auto ro,noauto 0 0', b'\0'):
            with self.subTest(plan=plan):
                r = self.run_tool(plan)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, b'')

    def test_refuse_stdout_alias(self):
        r = self.run_tool(rule(A), b'# orig\n', 'alias')
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
