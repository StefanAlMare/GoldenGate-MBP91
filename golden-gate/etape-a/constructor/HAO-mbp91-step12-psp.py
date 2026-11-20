#!/usr/bin/env python3
"""Restore the pinned PSP input at Hao's expected path, then continue step 12.

Run as the ordinary user from ~/Desktop/hao-patcher-mbp91. The already
downloaded HAO-mbp91-step12-apfs.py must remain beside this script.
"""
from __future__ import annotations
import errno
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

PSP_SHA = '1c290781bc726759ff37a110ffcb7182a6c6fd3d8ebce112d134d482c8de52a3'
PSP_SIZE = 853_972_480
PSP_URL = 'https://github.com/dortania/PatcherSupportPkg/releases/download/2.0.5/Universal-Binaries.dmg'
PSP_TARGET = 'store/inputs/psp-2.0.5/Universal-Binaries.dmg'
PSP_PRIOR = 'store/downloads/mbp91/Universal-Binaries-2.0.5.dmg'
BUILDER_NAME = 'HAO-mbp91-step12-apfs.py'
BUILDER_SHA = 'fdbef02ea1df3f2a0ae26b9215761a71fb63c309d4a280d82d4fb5691a4911ff'


class Stop(RuntimeError):
    pass


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def inside(repo, relative):
    path = repo / relative
    if not path.resolve().is_relative_to(repo.resolve()):
        raise Stop('Cale in afara proiectului: ' + relative)
    return path


def verify_psp(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise Stop('Pachetul PSP trebuie sa fie un fisier obisnuit: ' + str(path))
    if info.st_size != PSP_SIZE or sha(path) != PSP_SHA:
        raise Stop('Pachetul PSP nu corespunde dimensiunii si SHA256 fixate: ' + str(path))


def download_psp(destination):
    subprocess.run(['/usr/bin/curl', '--fail', '--location', '--retry', '3',
                    '--connect-timeout', '20', '--proto', '=https',
                    '--proto-redir', '=https', '--output', str(destination), PSP_URL], check=True)


def publish_verified(source, destination):
    """Create the canonical name atomically without overwriting an existing file."""
    try:
        os.link(source, destination)
    except FileExistsError:
        verify_psp(destination)


def ensure_psp(repo, fetch=None):
    repo = Path(repo).resolve()
    row = inside(repo, 'pipeline/inputs/common/psp_2.0.5')
    lines = [line.strip() for line in row.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or lines[0].split() != [PSP_SHA, PSP_TARGET]:
        raise Stop('Intrarea Hao psp_2.0.5 difera de versiunea fixata.')
    target = inside(repo, PSP_TARGET)
    if os.path.lexists(target):
        verify_psp(target)
        return dict(method='existing', path=target, source=target)
    target.parent.mkdir(parents=True, exist_ok=True)
    prior = inside(repo, PSP_PRIOR)
    if os.path.lexists(prior):
        print('    Verific SHA256 al DMG-ului descarcat la pasul 3.', flush=True)
        verify_psp(prior)
        try:
            publish_verified(prior, target)
            return dict(method='hardlink', path=target, source=prior)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
    else:
        print('    Copia din pasul 3 lipseste; descarc exact PSP 2.0.5 (0,85 GB).', flush=True)
    if shutil.disk_usage(target.parent).free < PSP_SIZE + 1_000_000_000:
        raise Stop('Spatiu insuficient pentru copierea sau descarcarea PSP.')
    descriptor, temporary = tempfile.mkstemp(prefix='psp-2.0.5-', suffix='.partial', dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        if prior.is_file():
            shutil.copyfile(prior, temporary)
            method = 'copy'
        else:
            (fetch or download_psp)(temporary)
            method = 'download'
        verify_psp(temporary)
        publish_verified(temporary, target)
        return dict(method=method, path=target, source=prior if method == 'copy' else PSP_URL)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    if sys.platform != 'darwin' or os.geteuid() == 0:
        raise Stop('Ruleaza cu python3.14 ca utilizator normal, pe iMac.')
    repo = Path.cwd().resolve()
    if not (repo / 'local/mbp91/step12-state.json').is_file():
        raise Stop('Intra mai intai in ~/Desktop/hao-patcher-mbp91.')
    builder = Path(__file__).resolve().parent / BUILDER_NAME
    if not builder.is_file() or sha(builder) != BUILDER_SHA:
        raise Stop('Constructorul APFS verificat trebuie sa fie alaturi de acest script: ' + BUILDER_NAME)
    print('1/2 Restabilesc intrarea PSP 2.0.5 folosita de constructor.', flush=True)
    record = ensure_psp(repo)
    messages = {'existing': 'Intrarea exista deja; integritate verificata.',
                'hardlink': 'DMG reutilizat prin hard link; datele nu sunt duplicate.',
                'copy': 'DMG copiat si verificat.',
                'download': 'PSP 2.0.5 descarcat si verificat.'}
    print('    ' + messages[record['method']], flush=True)
    print('    Calea pregatita: ' + PSP_TARGET, flush=True)
    print('2/2 Continui automat pasul 12 cu constructorul APFS verificat.', flush=True)
    os.execv(sys.executable, [sys.executable, '-I', str(builder)])


if __name__ == '__main__':
    try:
        main()
    except (Stop, OSError, subprocess.CalledProcessError) as error:
        print('OPRIT: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
