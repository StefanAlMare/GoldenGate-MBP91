#!/usr/bin/env python3
"""Preview fstab using a volume plan for one computer."""
import argparse
import os
from pathlib import Path
import re
import stat
import sys

UUID = re.compile(rb'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', re.I)
RULE = [b'none', b'auto', b'ro,noauto', b'0', b'0']
MAX_BYTES = 2 * 1024 * 1024


ROMANIAN = {
    'Expected a regular file: {path}':
        'Este necesar un fișier obișnuit: {path}',
    'The output points to an input file.':
        'Ieșirea indică unul dintre fișierele de intrare.',
    'File too large or contains NUL bytes: {path}':
        'Fișierul este prea mare sau conține octeți NUL: {path}',
    'Unrecognized plan rule on line {line_no}.':
        'Planul conține o regulă nerecunoscută la linia {line_no}.',
    'Duplicate UUID on plan line {line_no}.':
        'UUID repetat în plan la linia {line_no}.',
    'The plan contains no UUIDs.':
        'Planul nu conține niciun UUID.',
    'The fstab copy uses a non-UUID identifier on line {line_no}. Check whether it refers to a selected volume.':
        'Linia {line_no} din copia fstab folosește un identificator diferit de UUID. Verifică manual dacă indică unul dintre volume.',
    'Duplicate or conflicting rule for a selected UUID on line {line_no} of the fstab copy.':
        'Regulă dublă sau diferită pentru un UUID selectat la linia {line_no} din copia fstab.',
    'The plan and the fstab copy point to the same file.':
        'Planul și copia fstab indică același fișier.',
    'Preview fstab using a volume plan for one computer.':
        'Pregătește o previzualizare fstab din planul de volume al unui calculator.',
    'output language (default: en)':
        'limba mesajelor (implicit en)',
    'file produced by Inventar.command --plan':
        'fișier produs de Inventar.command --plan',
    'fstab copy from the target Golden image':
        'copia fstab din imaginea Golden țintă',
    'the target image has no fstab':
        'imaginea țintă nu are fstab',
    'Stopped':
        'Oprit',
}


def input_copy(path, message=str):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode):
            raise ValueError(message('Expected a regular file: {path}').format(path=path))
        if os.path.samestat(meta, os.fstat(sys.stdout.fileno())):
            raise ValueError(message('The output points to an input file.'))
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or b'\0' in data:
        raise ValueError(message('File too large or contains NUL bytes: {path}').format(path=path))
    return data


def entries(data):
    for line_no, line in enumerate(data.splitlines(), 1):
        fields = line.partition(b'#')[0].split()
        if fields:
            yield line_no, fields


def volume_id(field):
    prefix, sep, value = field.partition(b'=')
    if sep and prefix.upper() == b'UUID' and UUID.fullmatch(value):
        return value.upper()
    return None


def preview(plan, base, message=str):
    requested = {}
    for line_no, fields in entries(plan):
        uuid = volume_id(fields[0])
        if not uuid or fields[1:] != RULE:
            raise ValueError(message('Unrecognized plan rule on line {line_no}.').format(line_no=line_no))
        if uuid in requested:
            raise ValueError(message('Duplicate UUID on plan line {line_no}.').format(line_no=line_no))
        requested[uuid] = False
    if not requested:
        raise ValueError(message('The plan contains no UUIDs.'))

    for line_no, fields in entries(base):
        uuid = volume_id(fields[0])
        if not uuid:
            raise ValueError(message('The fstab copy uses a non-UUID identifier on line {line_no}. Check whether it refers to a selected volume.').format(line_no=line_no))
        if uuid in requested:
            if requested[uuid] or fields[1:] != RULE:
                raise ValueError(message('Duplicate or conflicting rule for a selected UUID on line {line_no} of the fstab copy.').format(line_no=line_no))
            requested[uuid] = True

    eol = b'\r\n' if b'\r\n' in base and b'\n' not in base.replace(b'\r\n', b'') else b'\n'
    missing = [b' '.join([b'UUID=' + uuid] + RULE) + eol
               for uuid, present in requested.items() if not present]
    return b''.join(missing) + base


def main():
    language = argparse.ArgumentParser(add_help=False)
    language.add_argument('--lang', choices=('en', 'ro'), default='en')
    lang = language.parse_known_args()[0].lang

    def message(text):
        return ROMANIAN[text] if lang == 'ro' else text

    parser = argparse.ArgumentParser(description=message(__doc__))
    parser.add_argument('--lang', choices=('en', 'ro'), default='en', help=message('output language (default: en)'))
    parser.add_argument('--plan', type=Path, required=True, help=message('file produced by Inventar.command --plan'))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--base', type=Path, help=message('fstab copy from the target Golden image'))
    group.add_argument('--empty', action='store_true', help=message('the target image has no fstab'))
    args = parser.parse_args()
    try:
        plan = input_copy(args.plan, message)
        if args.base is not None and args.base.samefile(args.plan):
            raise ValueError(message('The plan and the fstab copy point to the same file.'))
        base = input_copy(args.base, message) if args.base is not None else b''
        sys.stdout.buffer.write(preview(plan, base, message))
    except (OSError, ValueError) as error:
        parser.exit(1, f'{message("Stopped")}: {error}\n')


if __name__ == '__main__':
    main()
