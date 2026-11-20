"""Completează șabloanele A/B într-o copie locală nouă, fără a executa scripturile sau sondele."""
import argparse
import json
from pathlib import Path
import re
import shutil
import uuid


HERE = Path(__file__).resolve().parent
PATTERN = re.compile(r'@@([A-Z][A-Z0-9_]+)@@')
MARK = '# GG_BEGIN_SOURCE\n'
FORMATS = {
    'BSD_NTFS': r'disk[0-9]+s[0-9]+',
    'BSD_EXFAT': r'disk[0-9]+s[0-9]+',
    'GUI_USER': r'[a-z_][a-z0-9_-]{0,30}',
    'SSH_TARGET': r'[a-z_][a-z0-9_-]{0,30}@[A-Za-z0-9][A-Za-z0-9.-]*',
    'B_IMAGE_DIRECTORY': r'[A-Za-z0-9][A-Za-z0-9._-]*',
    'STEP13_ARCHIVE': r'/[A-Za-z0-9_./ -]+',
    'HAO_STORE': r'/[A-Za-z0-9_./ -]+',
}


def validate(key, value):
    if not isinstance(value, str):
        raise ValueError(f'Valoare text necesară pentru {key}.')
    if key.startswith('UUID_'):
        parsed = uuid.UUID(value)
        if parsed.int == 0 or str(parsed).upper() != value.upper():
            raise ValueError(f'UUID nevalid pentru {key}.')
        return str(parsed).upper()
    if key not in FORMATS or not re.fullmatch(FORMATS[key], value) or '..' in Path(value).parts:
        raise ValueError(f'Valoare nevalidă pentru {key}.')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profil', type=Path, help='JSON privat cu valorile pentru calculatorul A/B')
    parser.add_argument('--destinatie', type=Path, help='Director nou care va conține golden-gate')
    args = parser.parse_args()
    sources = [p for name in ('diagnostics', 'kit-volume') for p in sorted((HERE / name).iterdir())
               if p.is_file() and not p.is_symlink() and not p.name.startswith('.')]
    templates = {p: p.read_text().split(MARK, 1)[1] for p in sources if p.name.endswith('.in')}
    names = sorted({key for content in templates.values() for key in PATTERN.findall(content)})
    if not args.profil and not args.destinatie:
        print(json.dumps(dict.fromkeys(names, ''), indent=2))
        return
    if not args.profil or not args.destinatie:
        parser.error('--profil și --destinatie se folosesc împreună.')
    supplied = json.loads(args.profil.read_text())
    if not isinstance(supplied, dict) or set(supplied) != set(names):
        raise ValueError('Cheile profilului diferă de lista afișată fără argumente.')
    values = {k: validate(k, supplied[k]) for k in names}
    uuids = [values[k] for k in names if k.startswith('UUID_')]
    if len(set(uuids)) != len(uuids) or values['BSD_NTFS'] == values['BSD_EXFAT']:
        raise ValueError('Identitățile distincte din profil trebuie completate individual.')
    dst = args.destinatie.resolve()
    dst.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for p in sources:
            target = dst / 'golden-gate' / p.relative_to(HERE)
            target.parent.mkdir(parents=True, exist_ok=True)
            if p not in templates:
                shutil.copy2(p, target)
                continue
            out = target.with_suffix('')
            if out.exists():
                raise ValueError(f'Fișier duplicat în destinație: {out.name}.')
            out.write_text(PATTERN.sub(lambda m: values[m[1]], templates[p]))
            out.chmod(0o700 if out.suffix == '.command' else 0o600)
    except BaseException:
        shutil.rmtree(dst)
        raise
    print('Sursele configurate sunt în', dst / 'golden-gate')


if __name__ == '__main__':
    main()
