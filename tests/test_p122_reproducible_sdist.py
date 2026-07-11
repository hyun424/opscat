from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

from scripts.normalize_p122_sdist import normalize_sdist


def _archive(path: Path, *, mtime: int, uid: int) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo("opscat-0.2.0/example.txt")
        payload = b"same content\n"
        info.size = len(payload)
        info.mtime = mtime
        info.uid = uid
        archive.addfile(info, io.BytesIO(payload))
    path.write_bytes(gzip.compress(raw.getvalue(), mtime=mtime))


def test_sdist_normalization_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _archive(first, mtime=100, uid=501)
    _archive(second, mtime=200, uid=1000)
    normalize_sdist(first, first, epoch=123)
    normalize_sdist(second, second, epoch=123)
    assert first.read_bytes() == second.read_bytes()
