"""CCKB の要求。**HHKB 英語配列の実物の KLE と突き合わせる**（設計書 §1）。

守るもの: スペース以外の全キーの中心・幅・刻印、ピッチ、最下段の空き（左 1.5u・右 2.5u）、
スペースが 4.0〜10.0u を 3 キーで隙間なく覆うこと。
"""

import pytest

from conftest import FIXTURES
from foundry import paths
from foundry.layout import UNIT, load_layout
from foundry.project import load

HHKB = FIXTURES / "hhkb_original.json"


def _row(k):
    return round(k.y_mm / UNIT - 0.5)


def differences(ours, ref):
    """スペース以外で、HHKB と違うキーを返す（空なら準拠）。"""
    key = lambda k: (_row(k), round(k.left_u, 4))
    a = {key(k): k for k in ours if k.label != "Space"}
    b = {key(k): k for k in ref if k.label != "Space"}
    out = sorted(f"{p}: {'無い' if p not in a else ''}{'余分' if p not in b else ''}"
                 for p in set(a) ^ set(b))
    for p in set(a) & set(b):
        if (a[p].label, a[p].w_u, round(a[p].x_mm, 4), round(a[p].y_mm, 4)) != \
           (b[p].label, b[p].w_u, round(b[p].x_mm, 4), round(b[p].y_mm, 4)):
            out.append(f"{p}: {a[p]} / HHKB {b[p]}")
    return out


def test_every_key_but_space_is_where_the_hhkb_has_it():
    ours = load("cckb").keys()
    ref = load_layout(HHKB)
    assert len(ref) == 60 and len(ours) == 62            # 空どうしで緑にしない
    assert differences(ours, ref) == []


def test_the_three_space_keys_cover_the_hhkb_space_exactly():
    ref = [k for k in load_layout(HHKB) if k.label == "Space"]
    sp = sorted((k for k in load("cckb").keys() if k.label == "Space"), key=lambda k: k.x_mm)
    assert [k.w_u for k in sp] == [2.25, 1.5, 2.25]
    assert abs(sp[0].left_u - ref[0].left_u) < 1e-9 and abs(sp[-1].right_u - ref[0].right_u) < 1e-9
    assert all(abs(a.right_u - b.left_u) < 1e-9 for a, b in zip(sp, sp[1:]))   # 隙間なし
    assert len({round(k.y_mm, 4) for k in sp + ref}) == 1


def test_the_bottom_row_leaves_the_hhkb_corners_empty():
    bottom = [k for k in load("cckb").keys() if _row(k) == 4]
    assert min(k.left_u for k in bottom) == 1.5 and max(k.right_u for k in bottom) == 12.5


def test_the_checker_notices_a_moved_key(tmp_path):
    """**検査器が壊れていないか。**Q を 0.25u 動かした配列で差が出ること。"""
    import json

    raw = json.loads(HHKB.read_text())
    row = raw[2]
    row.insert(row.index("Q"), {"x": 0.25})
    f = tmp_path / "moved.json"
    f.write_text(json.dumps(raw))
    assert differences(load_layout(f), load_layout(HHKB))


def test_the_machine_uses_choc_v1():
    from foundry.mech import switch_of

    assert switch_of(load("cckb").spec).name == "choc_v1"
    assert (paths.PROJECTS / "cckb" / "layout.json").exists()


def test_the_plate_openings_are_exactly_the_empty_corners():
    from foundry.layout import centered

    p = load("cckb")
    keys = p.keys()
    positions, (kw, kh) = centered(keys)
    bottom = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 4]
    y_bottom = bottom[0][0][1]
    left_edge = min(pos[0] - k.w_mm / 2 for pos, k in bottom)
    right_edge = max(pos[0] + k.w_mm / 2 for pos, k in bottom)
    expect = [((-kw / 2 + left_edge) / 2, y_bottom, left_edge + kw / 2, UNIT),
              ((right_edge + kw / 2) / 2, y_bottom, kw / 2 - right_edge, UNIT)]
    got = p.spec.PLATE_OPENINGS["main"]
    assert len(got) == 2
    for g, e in zip(got, expect):
        assert all(abs(a - b) < 1e-6 for a, b in zip(g, e)), (g, e)


@pytest.fixture(scope="module")
def plate():
    from foundry.plate import build_plate

    p = load("cckb")
    part, size, positions = build_plate(p.spec, p.keys(), "main")
    return p, part, size, positions


def _solid(part, x, y):
    from build123d import Vector

    return part.is_inside(Vector(x, y, 0.6))


def test_the_plate_is_open_at_every_key_and_at_both_corners(plate):
    p, part, _, positions = plate
    assert len(positions) == 62
    for x, y in positions:
        assert not _solid(part, x, y)
    for cx, cy, w, h in p.spec.PLATE_OPENINGS["main"]:
        assert not _solid(part, cx, cy), (cx, cy)


def test_the_web_around_the_corner_keys_survives(plate):
    """角の開口が隣のキー（最下段の角のキー）の自分のセルの桟を削っていないこと（Review Focus 4）。

    **spec.PLATE_OPENINGS を判定に使わない。**角の開口そのものが検査対象なので、
    それを使って「ここは角の中だから見なくてよい」と判定すると、開口を広げる
    壊し方が自分自身を免除してしまう（実測で確認済み）。角に触れるキーは
    レイアウトから導く（test_the_plate_openings_are_exactly_the_empty_corners と同じ手）。
    """
    from foundry.layout import centered
    from foundry.mech import switch_of
    from foundry.plate import choc_stab_polygons

    p, part, _, positions = plate
    keys = p.keys()
    _, (kw, kh) = centered(keys)
    sw = switch_of(p.spec)
    bottom = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 4]
    left_key = min(bottom, key=lambda pk: pk[0][0])
    right_key = max(bottom, key=lambda pk: pk[0][0])
    half_cutout = sw.cutout / 2   # 6.9: スイッチ開口の縁

    def own_stab_polys(pos, k):
        s = sw.stab_offset_for(k.w_u)
        if s is None:
            return []
        return choc_stab_polygons(s, at=pos) if sw.stab_kind == "choc" else []

    def in_polygon(x, y, poly):
        # 簡易な内外判定（レイ・キャスティング）。開口はどれも軸並行に近い凸形
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xin = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
                if x < xin:
                    inside = not inside
        return inside

    for pos, k, side in ((left_key[0], left_key[1], -1), (right_key[0], right_key[1], 1)):
        x, y = pos
        half_cell = k.w_mm / 2
        stabs = own_stab_polys(pos, k)
        checked = 0
        for r in (7.2, 8.2, 9.2):
            if r >= half_cell:
                continue   # セルの外に出てしまう距離は使わない
            px = x + side * r
            for dy in (-5.0, 0.0, 5.0):
                py = y + dy
                if any(in_polygon(px, py, poly) for poly in stabs):
                    continue   # 自分のスタビ開口の中は桟ではない
                checked += 1
                assert _solid(part, px, py), (k.label, side, r, dy)
        assert checked > 0, (k.label, "probe 点が 1 つも取れなかった")


def test_the_plate_is_1_2mm_and_printable_as_a_check(plate, tmp_path):
    from foundry.verify import to_mesh

    _, part, (w, h), _ = plate
    assert abs(part.bounding_box().size.Z - 1.2) < 1e-6
    mesh, _ = to_mesh(part, tmp_path / "plate.stl")
    assert mesh.is_watertight
