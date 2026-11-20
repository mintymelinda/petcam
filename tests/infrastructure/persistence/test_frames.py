from datetime import datetime, timezone

from petcam.infrastructure.persistence import frames


JPEG = b"\xff\xd8frame\xff\xd9"


class Response:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def read1(self, _size):
        return next(self.chunks, b"")


def test_jpeg_parser_handles_chunks_and_ignores_non_frame_bytes():
    response = Response([b"noise\xff\xd8fra", b"me\xff\xd9tail", b""])
    assert list(frames.jpeg_frames(response)) == [JPEG]


def test_capture_frame_writes_complete_jpeg_atomically(tmp_path):
    path = frames.capture_frame(
        JPEG, tmp_path, datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert path.read_bytes() == JPEG
    assert not list(tmp_path.glob("*.tmp"))


def test_capture_frame_rejects_incomplete_jpeg(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="complete JPEG"):
        frames.capture_frame(b"not-a-jpeg", tmp_path)


def test_prune_frames_enforces_retention_age(tmp_path):
    old = tmp_path / "old.jpg"
    recent = tmp_path / "recent.jpg"
    old.write_bytes(b"old")
    recent.write_bytes(b"recent")
    old.touch()
    recent.touch()
    import os
    os.utime(old, (1, 1))
    os.utime(recent, (99999, 99999))
    result = frames.prune_frames(
        {"retention_days": 1, "max_storage_mb": 1},
        tmp_path,
        now=100000,
    )
    assert not old.exists()
    assert recent.exists()
    assert result["frames"] == 1
