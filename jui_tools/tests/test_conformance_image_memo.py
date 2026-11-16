"""image_memo: each measurement taken once per file CONTENT, and the gate's
per-face work run in parallel with its results in the faces' order.

The gate's whole output is held byte-for-byte to the pre-memo gate on a CI
run's artifacts elsewhere (the report-gate-faster change's comparison arm);
these pin the two properties that comparison cannot see on one data set:

- the key is the file's content, not its path: a file rewritten in place is
  measured again, and two paths with the same bytes share one measurement;
- per_face keeps the items' order for results and for the exception that
  surfaces, and JUI_CONFORMANCE_WORKERS=1 runs the items one after another.
"""

from __future__ import annotations

import threading
import time

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from jui_cli.conformance import baseline, control_diff, image_memo  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_memo():
    image_memo.clear()
    yield
    image_memo.clear()


def picture(path, box=None, colour=(255, 0, 0)):
    img = Image.new("RGB", (120, 200), (250, 250, 250))
    if box:
        ImageDraw.Draw(img).rectangle(box, fill=colour)
    img.save(path)
    return path


def reference_dhash(path, crop=(0, 0), transpose=False):
    """The measurement as baseline._dhash_of computed it before the memo."""
    with Image.open(path) as img:
        top, bottom = crop
        if top or bottom:
            width, height = img.size
            if height > top + bottom:
                img = img.crop((0, top, width, height - bottom))
        if transpose:
            img = img.transpose(Image.Transpose.TRANSPOSE)
        pixels = img.convert("L").resize((baseline.HASH_SIZE + 1, baseline.HASH_SIZE), Image.Resampling.LANCZOS).tobytes()
    bits = 0
    for row in range(baseline.HASH_SIZE):
        offset = row * (baseline.HASH_SIZE + 1)
        for col in range(baseline.HASH_SIZE):
            bits = (bits << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    return f"{bits:0{baseline.HASH_SIZE * baseline.HASH_SIZE // 4}x}"


def reference_ink(path, crop=(0, 0)):
    with Image.open(path) as img:
        top, bottom = crop
        if top or bottom:
            width, height = img.size
            if height > top + bottom:
                img = img.crop((0, top, width, height - bottom))
        histogram = img.convert("L").histogram()
    return sum(histogram) - max(histogram)


def test_the_measures_are_what_they_were(tmp_path):
    shot = picture(tmp_path / "a.png", (10, 30, 90, 120))
    for crop in [(0, 0), (20, 10)]:
        assert baseline.dhash_file(shot, crop) == reference_dhash(shot, crop)
        assert baseline.vdhash_file(shot, crop) == reference_dhash(shot, crop, transpose=True)
        assert baseline.ink_file(shot, crop) == reference_ink(shot, crop)


def test_a_file_rewritten_in_place_is_measured_again(tmp_path):
    shot = picture(tmp_path / "a.png", (10, 30, 90, 120))
    before = (baseline.dhash_file(shot), baseline.ink_file(shot))
    entries = image_memo.size()
    picture(shot, (40, 10, 110, 60), colour=(0, 0, 255))  # same path, new bytes
    after = (baseline.dhash_file(shot), baseline.ink_file(shot))
    assert after != before
    assert after == (reference_dhash(shot), reference_ink(shot))
    assert image_memo.size() == entries + 1


def test_the_same_bytes_at_two_paths_are_one_measurement(tmp_path):
    a = picture(tmp_path / "a.png", (10, 30, 90, 120))
    b = tmp_path / "b.png"
    b.write_bytes(a.read_bytes())
    baseline.dhash_file(a)
    entries = image_memo.size()
    assert baseline.dhash_file(b) == baseline.dhash_file(a)
    assert image_memo.size() == entries


def test_a_pixel_diff_follows_both_files_content(tmp_path):
    a = picture(tmp_path / "a.png")
    b = picture(tmp_path / "b.png", (0, 0, 9, 9))
    assert control_diff.diff_pixels(a, b) == 100
    assert control_diff.diff_pixels(a, a) == 0
    picture(b)  # b now matches a
    assert control_diff.diff_pixels(a, b) == 0
    assert control_diff.diff_pixels(a, b, ignore_bottom=0, ignore_top=0) == 0


def test_per_face_keeps_the_order_whatever_finishes_first(monkeypatch):
    monkeypatch.delenv("JUI_CONFORMANCE_WORKERS", raising=False)
    delays = {"web": 0.15, "ios": 0.0, "android": 0.05}

    def slow(face):
        time.sleep(delays[face])
        return face.upper()

    assert image_memo.per_face(slow, ["web", "ios", "android"]) == ["WEB", "IOS", "ANDROID"]


def test_per_face_raises_the_first_failure_in_order(monkeypatch):
    monkeypatch.delenv("JUI_CONFORMANCE_WORKERS", raising=False)

    def fail(face):
        if face == "android":
            raise ValueError("android")
        if face == "ios":
            time.sleep(0.05)
            raise KeyError("ios")
        return face

    with pytest.raises(KeyError):
        image_memo.per_face(fail, ["web", "ios", "android"])


def test_one_worker_runs_the_faces_one_after_another(monkeypatch):
    monkeypatch.setenv("JUI_CONFORMANCE_WORKERS", "1")
    seen = []

    def record(face):
        seen.append((face, threading.current_thread() is threading.main_thread()))
        return face

    assert image_memo.per_face(record, ["web", "ios"]) == ["web", "ios"]
    assert seen == [("web", True), ("ios", True)]
