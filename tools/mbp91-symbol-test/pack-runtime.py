#!/usr/bin/env python3
"""Package an existing x86_64 Python 3.12 installation for the Metal probe."""

import argparse
import gzip
import hashlib
from pathlib import Path
import tarfile
import tempfile


EXCLUDED = {
    "__pycache__", "config-3.12-darwin", "ensurepip", "idlelib", "site-packages",
    "test", "tests", "tkinter", "turtledemo", "venv",
}
PROGRAM = "metal-python/bin/python3.12"
LIB = "metal-python/lib/python3.12"


def write_archive(source, destination):
    stdlib = source / "lib/python3.12"
    files = {PROGRAM: source / "bin/python3.12", f"{LIB}/LICENSE.txt": stdlib / "LICENSE.txt"}
    for path in stdlib.rglob("*.py"):
        relative = path.relative_to(stdlib)
        if not path.is_symlink() and EXCLUDED.isdisjoint(relative.parts):
            files[f"{LIB}/{relative.as_posix()}"] = path

    with gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            # CPython uses this directory to locate its platform-dependent prefix.
            directory = tarfile.TarInfo(f"{LIB}/lib-dynload")
            directory.type = tarfile.DIRTYPE
            directory.mode = 0o755
            archive.addfile(directory)
            for name, source_path in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.mode = 0o755 if name == PROGRAM else 0o644
                entry.size = source_path.stat().st_size
                with source_path.open("rb") as stream:
                    archive.addfile(entry, stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="installed runtime prefix containing bin and lib")
    parser.add_argument("output", type=Path, help="destination .tar.gz")
    args = parser.parse_args()
    with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as candidate:
        name = Path(candidate.name)
    try:
        with name.open("wb") as stream:
            write_archive(args.source, stream)
        digest = hashlib.sha256(name.read_bytes()).hexdigest()
        name.chmod(0o644)
        name.replace(args.output)
        print(f"{digest}  {args.output}")
    finally:
        name.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
