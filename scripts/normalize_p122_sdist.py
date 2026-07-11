#!/usr/bin/env python3
"""Canonicalize an sdist tarball so equal trees produce equal bytes."""

from __future__ import annotations

import argparse
import gzip
import io
import tarfile
from pathlib import Path, PurePosixPath

DEFAULT_EPOCH = 1_767_225_600


def normalize_sdist(source: Path, destination: Path, *, epoch: int = DEFAULT_EPOCH) -> None:
    with tarfile.open(source, "r:gz") as archive:
        members = sorted(archive.getmembers(), key=lambda item: item.name)
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as output:
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"unsafe sdist member: {member.name}")
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"unsupported sdist member type: {member.name}")
                canonical = tarfile.TarInfo(member.name)
                canonical.type = tarfile.DIRTYPE if member.isdir() else tarfile.REGTYPE
                canonical.size = 0 if member.isdir() else member.size
                canonical.mode = 0o755 if member.isdir() else 0o644
                canonical.mtime = epoch
                canonical.uid = 0
                canonical.gid = 0
                canonical.uname = ""
                canonical.gname = ""
                payload = archive.extractfile(member) if member.isfile() else None
                output.addfile(canonical, payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(gzip.compress(raw.getvalue(), compresslevel=9, mtime=epoch))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--epoch", type=int, default=DEFAULT_EPOCH)
    args = parser.parse_args()
    output = args.output or args.source
    temporary = output.with_suffix(output.suffix + ".tmp") if output == args.source else output
    normalize_sdist(args.source, temporary, epoch=args.epoch)
    if temporary != output:
        temporary.replace(output)


if __name__ == "__main__":
    main()
