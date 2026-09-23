"""プレート。**開口の数を輪郭の数で数えない**——キーの中心を 1 つずつ突いて貫通を見る。"""

import pytest
from build123d import Vector

from foundry.mech import PLATE_T, stab_offset_for
from foundry.plate import build_plate, plate_size
from foundry.project import load


@pytest.fixture(scope="module")
def left(hhkb_ref):
    p = load(hhkb_ref)
    keys = p.pieces()["left"]
    part, size, positions = build_plate(p.spec, keys, "left")
    return p, keys, part, size, positions


def _solid(part, x, y):
    return part.is_inside(Vector(x, y, PLATE_T / 2))


def test_outline_is_key_field_plus_margins(left):
    p, keys, part, (w, h), _ = left
    bb = part.bounding_box().size
    assert abs(bb.X - w) < 1e-3 and abs(bb.Y - h) < 1e-3 and abs(bb.Z - PLATE_T) < 1e-3
    assert (w, h) == plate_size(p.spec, keys)


def test_every_key_centre_is_open_and_the_web_between_keys_is_solid(left):
    _, keys, part, _, positions = left
    assert len(positions) == 27
    for (x, y), k in zip(positions, keys):
        assert not _solid(part, x, y), k.label
        assert _solid(part, x, y + 8.5), f"{k.label}: 開口と開口の間に材料が無い"


def test_stab_cutouts_are_on_the_wide_keys_only(left):
    _, keys, part, _, positions = left
    for (x, y), k in zip(positions, keys):
        s = stab_offset_for(k.w_u)
        if s is None:
            continue
        # スタビ支点の中心（ワイヤの向きによらず支点の x は ±s）が抜けていること
        assert not _solid(part, x + s, y) and not _solid(part, x - s, y), k.label


def test_mount_holes_go_through(left):
    p, _, part, _, _ = left
    assert p.spec.MOUNTS["left"]
    for mx, my in p.spec.MOUNTS["left"]:
        assert not _solid(part, mx, my), (mx, my)


def test_the_plate_is_printable(left, tmp_path):
    from foundry.verify import to_mesh

    mesh, _ = to_mesh(left[2], tmp_path / "plate.stl")
    assert mesh.is_watertight
