"""Kailh Choc V2（PG1353）と、そのねじ留めスタビの足跡を**図面と**突き合わせる。

自分の生成物どうしの一致は検証ではない。相手は:
  - Kailh の図面 3 枚（keyboardio/keyswitch_documentation に保存された PDF。2026-09-25 に
    450〜600dpi で描き出して読んだ **生の値**。右下の "Recommended PCB Layout (Pattern Side)"）
      CPG135301D01      PG1353 赤（標準）
      CPG1353S01D01-01  PG1353 静音 赤
      CPG1353S01D02-01  PG1353 静音 茶（タクタイル 45gf。「配1.2铝板」）
  - スタビ: 販売者が公開した図（非公式）と、サリチル酸さんの足跡（実物を測った物）。
    どちらも mech.CHOC_V2_STAB_SOURCES に生の値で書き、ここで出典の画像・ファイルと同じか見る

変換は test_choc.py の V1 と同じ手順（X 反転 → +90° → Y 反転）に、**180° 回す**を足す
（V2 の十字は 90° ごとに対称なので、端子を V1 の足跡と同じ位置に置ける向きを選んだ。
決定記録 2026-09-25-choc-v2 §2-3）。まとめると (x, y) → (y, −x)（行列式 +1 の回転・鏡映なし）。
"""

import math
import re

import pytest

from conftest import ROOT
from foundry import mech
from foundry.mech import SWITCHES

LIB = ROOT / "lib" / "keyswitch.pretty"
FP = LIB / "SW_Kailh_Choc_V2_Slot.kicad_mod"
STAB_FP = LIB / "Stab_Kailh_Choc_V2_Screw_2u.kicad_mod"
REF = ROOT / "projects" / "cckb" / "docs" / "references"
UPSTREAM = REF / "kiswitch-SW_Kailh_Choc_V2.kicad_mod"
SAL_STAB = REF / "Salicylic-Choc_v2_PCBMountStab_2u.kicad_mod"
SAL_PLATE = REF / "Salicylic-Stab_Hole_Choc_v2_PCBMount_2u.kicad_mod"

# 図の生の値（パターン側・中心を原点・Y は図の上向きが正）。位置決めは ("circle", 直径) か
# ("oval", 図の X の長さ, 図の Y の長さ)。clip = つばの下面から爪の先まで（側面図）
DRAWINGS = {
    "CPG135301D01": dict(pins={"1": (5.90, 0.0), "2": (3.80, 5.00)}, pin_d=1.20, center_d=5.00,
                         locate=((-5.15, -5.00), ("circle", 1.60)), clip=1.65, housing=13.95),
    "CPG1353S01D01-01": dict(pins={"1": (5.90, 0.0), "2": (3.80, 5.00)}, pin_d=1.20, center_d=5.00,
                             locate=((-5.15, -5.00), ("oval", 2.0, 1.5)), clip=1.35, housing=13.95),
    "CPG1353S01D02-01": dict(pins={"1": (5.90, 0.0), "2": (3.80, 5.00)}, pin_d=1.20, center_d=5.00,
                             locate=((-5.15, -5.00), ("oval", 2.0, 1.5)), clip=1.35, housing=13.95),
}
HOUSING_TOL = 0.05                     # 3 枚とも 13.95±0.05


def to_kicad(x, y):
    """パターン側の図 → KiCad（部品側・Y 下向き）。V1 の 3 手順の後に 180°。"""
    x = -x                    # (1) X 反転（半田面 → 部品側。単独では鏡映）
    x, y = -y, x              # (2) +90°
    y = -y                    # (3) Y 反転（上向き → 下向き。単独では鏡映。(1) と打ち消す）
    return (-x, -y)           # (4) 180°


def test_the_conversion_is_a_rotation_and_lands_on_the_v1_pins():
    """変換の検算。V1 の足跡の端子 (0, −5.9)・(5, −3.8) に落ちる（配線を残せる根拠）。"""
    assert to_kicad(5.90, 0.0) == (0.0, -5.9)
    assert to_kicad(3.80, 5.00) == (5.0, -3.8)
    assert to_kicad(-5.15, -5.00) == (-5.0, 5.15)
    a, b = to_kicad(1, 0), to_kicad(0, 1)
    assert a[0] * b[1] - a[1] * b[0] == 1              # 行列式 +1（鏡映なし）


def _pads(path):
    out = []
    for m in re.finditer(r"\(pad \"?([^\"\s]*)\"? (\w+) (circle|oval) \(at ([-\d.]+) ([-\d.]+)[^)]*\)"
                         r"\s*\(size ([-\d.]+) ([-\d.]+)\)\s*\(drill (?:oval )?([\d.]+)(?: ([\d.]+))?\)",
                         path.read_text()):
        num, kind, shape, x, y, sx, sy, dx, dy = m.groups()
        dx = float(dx)
        out.append(dict(num=num, kind=kind, shape=shape, x=float(x), y=float(y),
                        size=(float(sx), float(sy)), drill=(dx, float(dy) if dy else dx)))
    return out


def _in_stadium(p, c, size, eps=1e-6):
    """点 p が長円（中心 c・(X 幅, Y 幅)。短い方の幅が直径の端の丸い形）の中か。"""
    w, h = size
    r = min(w, h) / 2
    if w >= h:
        ax, ay, bx, by = c[0] - (w / 2 - r), c[1], c[0] + (w / 2 - r), c[1]
    else:
        ax, ay, bx, by = c[0], c[1] - (h / 2 - r), c[0], c[1] + (h / 2 - r)
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy) <= r + eps


def _stadium_rim(c, size, n=72):
    """長円の縁の点（含む・含まれるを点で確かめる）。"""
    w, h = size
    r = min(w, h) / 2
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ex, ey = r * math.cos(a), r * math.sin(a)
        if w >= h:
            ex += math.copysign(w / 2 - r, ex) if abs(ex) > 1e-12 else 0.0
        else:
            ey += math.copysign(h / 2 - r, ey) if abs(ey) > 1e-12 else 0.0
        pts.append((c[0] + ex, c[1] + ey))
    return pts


def _source_hole(locate):
    """図の位置決め穴を KiCad の形 (中心, (X 幅, Y 幅)) に。図の X は KiCad の Y になる。"""
    (x, y), shape = locate
    c = to_kicad(x, y)
    if shape[0] == "circle":
        return c, (shape[1], shape[1])
    return c, (shape[2], shape[1])       # (図の Y → KiCad の X, 図の X → KiCad の Y)


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_the_pins_and_centre_match_each_drawing(name):
    d = DRAWINGS[name]
    pads = _pads(FP)
    assert len(pads) == 4                                   # 端子 2・中心・位置決め（空の集合で緑にしない）
    for num, xy in d["pins"].items():
        x, y = to_kicad(*xy)
        hit = [p for p in pads if p["num"] == num and p["kind"] == "thru_hole"]
        assert len(hit) == 1, (num, pads)
        assert abs(hit[0]["x"] - x) < 0.05 and abs(hit[0]["y"] - y) < 0.05, (num, hit, (x, y))
        assert hit[0]["drill"][0] >= d["pin_d"], hit
    c = [p for p in pads if p["kind"] == "np_thru_hole" and abs(p["x"]) < 1e-9 and abs(p["y"]) < 1e-9]
    assert len(c) == 1 and min(c[0]["drill"]) >= d["center_d"], c


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_the_locating_hole_takes_each_drawings_hole(name):
    """位置決め穴は 3 枚の図の穴の**和**を含む（標準 φ1.6・静音 長円 2.0×1.5）。めっき無し。"""
    loc = [p for p in _pads(FP) if p["kind"] == "np_thru_hole" and (p["x"], p["y"]) != (0.0, 0.0)]
    assert len(loc) == 1, loc
    h = loc[0]
    assert h["size"] == h["drill"]                          # 銅の輪が無い（行のバスを近くに通せる理由）
    c, size = _source_hole(DRAWINGS[name]["locate"])
    for p in _stadium_rim(c, size):
        assert _in_stadium(p, (h["x"], h["y"]), h["drill"]), (name, p, h)


def test_the_slot_footprint_is_kiswitch_but_the_locating_hole():
    """上流（kiswitch SW_Kailh_Choc_V2・無改変の写し）との差は、名前と位置決め穴の 1 行だけ。"""
    up = UPSTREAM.read_text().splitlines()
    mine = FP.read_text().splitlines()
    assert len(up) == len(mine)
    diff = [(a, b) for a, b in zip(up, mine) if a != b]
    assert len(diff) == 4, diff
    changed_pads = [(a, b) for a, b in diff if "(pad" in a]
    assert len(changed_pads) == 1
    a, b = changed_pads[0]
    assert "thru_hole circle (at -5 5.15)" in a and "np_thru_hole oval (at -5 5.15)" in b


def test_the_switch_table_uses_the_slot_footprint_and_the_drawings_plate():
    sw = SWITCHES["choc_v2"]
    assert set(sw.fp.values()) == {FP.stem}
    assert all(abs(sw.cutout - d["housing"]) <= HOUSING_TOL for d in DRAWINGS.values())
    # プレートは 3 枚のどの爪の隙にも入る（静音 1.35 が効く）
    assert sw.plate_t <= min(d["clip"] for d in DRAWINGS.values())
    assert sw.value == "PG1353"


# --- 壊して落ちるか -----------------------------------------------------------

def _break(tmp_path, monkeypatch, old, new, target="FP", src=None):
    import test_choc_v2

    src = src or getattr(test_choc_v2, target)
    text = src.read_text()
    assert old in text, old
    fake = tmp_path / src.name
    fake.write_text(text.replace(old, new))
    monkeypatch.setattr(test_choc_v2, target, fake)


@pytest.mark.parametrize("old, new, test", [
    ("(at 5 -3.8)", "(at 5.1 -3.8)", "test_the_pins_and_centre_match_each_drawing"),       # 端子を 0.1
    ("(at 5 -3.8)", "(at -5 -3.8)", "test_the_pins_and_centre_match_each_drawing"),        # 鏡映
    ("(size 5.05 5.05) (drill 5.05)", "(size 3.45 3.45) (drill 3.45)",
     "test_the_pins_and_centre_match_each_drawing"),                                      # V1 の中心穴に戻す
    ("(at -5 5.15) (size 1.6 2)", "(at -5 5.25) (size 1.6 2)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 位置決めを y 0.1
    ("(at -5 5.15) (size 1.6 2)", "(at -5.1 5.15) (size 1.6 2)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 位置決めを x 0.1
    ("(size 1.6 2) (drill oval 1.6 2)", "(size 1.6 1.6) (drill oval 1.6 1.6)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 静音を受けない丸穴
])
def test_the_switch_checker_notices_a_break(tmp_path, monkeypatch, old, new, test):
    import test_choc_v2

    _break(tmp_path, monkeypatch, old, new)
    with pytest.raises(AssertionError):
        for name in sorted(DRAWINGS):
            getattr(test_choc_v2, test)(name)


# ---------------------------------------------------------------------------
# スタビ（遊舎工房 A050001-01-1）
# ---------------------------------------------------------------------------

def _source_shapes(src):
    """出典 1 つの穴の形を、公称の支点 12.0 から・外向き X・ワイヤ +Y で。
    [(種類, 中心, (X 幅, Y 幅))]。box は矩形、screw・claw は長円（丸は同じ幅の長円）。"""
    s = mech.CHOC_V2_STAB_SOURCES[src]
    dx = s["pivot"] - SWITCHES["choc_v2"].stab_offset[2.25]
    # 箱の穴: x は推奨の穴、y は箱そのもの（図の推奨 8.00 は、ねじの穴との橋が細るので採らない。
    # mech.CHOC_V2_STAB_HOLES のコメント）。サリチル酸さんの足跡は穴の値をそのまま
    bw, bh = s["box"]
    if "part" in s:
        bh = s["part"][1]
    out = [("box", (dx, 0.0), (bw, bh))]
    for k in ("screw", "claw"):
        cy, w, h = s[k]
        out.append((k, (dx, cy), (w, h)))
    return out


def test_the_stab_sources_are_what_the_drawing_and_salicylic_say():
    """生の値を出典と照合する。図の値は画像（chocv2-stab-guide 2026-05-16）から読んだ 24.00・8.00×6.00・
    φ3.00 を 6.20・φ4.00 を 8.50。サリチル酸さんの値は保存したファイルから読み直す。"""
    d = mech.CHOC_V2_STAB_SOURCES["drawing"]
    assert (d["pivot"] * 2, d["box"], d["screw"], d["claw"], d["part"]) == \
        (24.0, (6.00, 8.00), (-6.20, 3.00, 3.00), (8.50, 4.00, 4.00), (5.80, 7.30))
    text = SAL_STAB.read_text()
    holes = [(float(x), float(y), float(w), float(h)) for x, y, w, h in re.findall(
        r"\(at ([-\d.]+) ([-\d.]+) 180\)\s*\(size ([\d.]+) ([\d.]+)\)", text)]
    assert len(holes) == 4
    s = mech.CHOC_V2_STAB_SOURCES["salicylic"]
    # サリチル酸さんの足跡はワイヤが +y（KiCad・手前）。支点 ±11.9、ねじは −6.2、爪は +8.24
    assert {(abs(x), y, w, h) for x, y, w, h in holes} == {
        (s["pivot"], s["screw"][0], s["screw"][1], s["screw"][2]),
        (s["pivot"], s["claw"][0], s["claw"][1], s["claw"][2])}
    xs = [float(v) for v in re.findall(r"\(start ([-\d.]+) [-\d.]+\)\s*\(end [-\d.]+ [-\d.]+\)\s*"
                                         r"\(stroke\s*\(width 0\.05\)", text)]
    ys = [float(v) for v in re.findall(r"\(start [-\d.]+ ([-\d.]+)\)\s*\(end [-\d.]+ [-\d.]+\)\s*"
                                         r"\(stroke\s*\(width 0\.05\)", text)]
    right = [x for x in xs if x > 0]
    assert (round(max(right) - min(right), 3), round(max(ys) - min(ys), 3)) == s["box"]
    assert round((max(right) + min(right)) / 2, 3) == s["pivot"]


@pytest.mark.parametrize("src", sorted(mech.CHOC_V2_STAB_SOURCES))
def test_the_stab_holes_take_each_sources_part(src):
    """開ける穴（mech.CHOC_V2_STAB_HOLES）が、どちらの出典の形（支点 24.0 でも 23.8 でも）も含む。"""
    H = mech.CHOC_V2_STAB_HOLES
    for kind, c, size in _source_shapes(src):
        if kind == "box":
            x0, y0, x1, y1 = H["box"]
            w, h = size
            assert x0 <= c[0] - w / 2 + 1e-9 and c[0] + w / 2 <= x1 + 1e-9 \
                and y0 <= c[1] - h / 2 + 1e-9 and c[1] + h / 2 <= y1 + 1e-9, (src, kind, c, size)
        else:
            hc, hs = H[kind]
            for p in _stadium_rim(c, size):
                assert _in_stadium(p, hc, hs), (src, kind, p)


def test_the_stab_footprint_is_the_holes():
    """フットプリント（KiCad・Y 下向き）の非めっきの穴 4 つ = mech.CHOC_V2_STAB_HOLES を左右に、
    ワイヤを奥（KiCad の −y）に置いた物。"""
    s = SWITCHES["choc_v2"].stab_offset[2.25]
    H = mech.CHOC_V2_STAB_HOLES
    want = set()
    for side in (-1, 1):
        for k in ("screw", "claw"):
            (hx, hy), (w, h) = H[k]
            want.add((round(side * (s + hx), 3), round(-hy, 3), w, h))
    pads = _pads(STAB_FP)
    got = {(round(p["x"], 3), round(p["y"], 3), *p["drill"]) for p in pads}
    assert len(pads) == 4 and all(p["kind"] == "np_thru_hole" and p["size"] == p["drill"] for p in pads)
    assert got == want, (got, want)
    assert SWITCHES["choc_v2"].stab_fp == {s: STAB_FP.stem}


@pytest.mark.parametrize("old, new", [
    ("(at 11.9 6.2)", "(at 12.0 6.2)"),                  # ねじを 0.1
    ("(at -11.95 -8.37)", "(at -11.95 -8.27)"),          # 爪を 0.1
    ("(at -11.95 -8.37) (size 4.2 4.4) (drill oval 4.2 4.4)",
     "(at -11.95 -8.37) (size 4.1 4.4) (drill oval 4.1 4.4)"),                      # 爪の幅を 0.1
])
def test_the_stab_checker_notices_a_break(tmp_path, monkeypatch, old, new):
    import test_choc_v2

    _break(tmp_path, monkeypatch, old, new, target="STAB_FP")
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_stab_footprint_is_the_holes()


def test_the_stab_hole_checker_notices_a_hole_that_misses_a_source(monkeypatch):
    """開ける穴を 0.1 狭めると、どちらかの出典の形がはみ出して落ちる。"""
    import test_choc_v2

    for k, v in (("box", (-3.0, -3.75, 3.0, 3.75)),                # 支点 23.8 の箱の内の辺
                 ("screw", ((-0.1, -6.2), (3.1, 3.4))),
                 ("claw", ((-0.05, 8.47), (4.2, 4.4)))):
        H = dict(mech.CHOC_V2_STAB_HOLES)
        H[k] = v
        monkeypatch.setattr(mech, "CHOC_V2_STAB_HOLES", H)
        with pytest.raises(AssertionError):
            for src in sorted(mech.CHOC_V2_STAB_SOURCES):
                test_choc_v2.test_the_stab_holes_take_each_sources_part(src)


# --- プレートの開口 -----------------------------------------------------------

def _sal_plate_points():
    """サリチル酸さんのプレートの開口の縁の点（KiCad・ワイヤ +y）。直線の端と円弧の 3 点。
    スイッチの開口の部分（|x| ≦ 7.05 かつ y ≦ 6.64375）は除く（そこは機種のスイッチの開口が受け持つ）。"""
    pts = set()
    text = "".join(m.group(0) for m in re.finditer(r"\(fp_(?:line|arc)(?:(?!\(fp_).)*?Edge\.Cuts", SAL_PLATE.read_text(), re.S))
    for a, b in re.findall(r"\((?:start|mid|end) ([-\d.]+) ([-\d.]+)\)", text):
        x, y = float(a), float(b)
        if abs(x) <= 7.05 + 1e-9 and y <= 6.64375 + 1e-9:
            continue
        pts.add((x, y))
    return sorted(pts)


def _in_poly(p, poly, eps=1e-6):
    x, y = p
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):            # 縁の上も中とみなす
        if min(x1, x2) - eps <= x <= max(x1, x2) + eps and min(y1, y2) - eps <= y <= max(y1, y2) + eps:
            if abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) < eps:
                return True
    ins = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
            ins = not ins
    return ins


@pytest.mark.parametrize("shift", (0.0, 0.1))
def test_the_plate_stab_opening_contains_salicylics(shift):
    """プレートの開口（kerf 0）は、サリチル酸さんの開口（支点 11.9）と、それを支点 12.0 へ 0.1 外へ
    ずらした物を含む。**CHOC_V2_STAB_PLATE の座標は CAD でワイヤが +y**（KiCad でワイヤ +y の
    サリチル酸さんの図をそのまま使える: CAD は Y を反転し、さらにワイヤを奥へ 180° 回すので y は同じ）。"""
    from foundry.plate import choc_v2_stab_polygons

    polys = choc_v2_stab_polygons()
    pts = _sal_plate_points()
    assert len(pts) > 20
    for x, y in pts:
        p = (x + math.copysign(shift, x), y)
        assert any(_in_poly(p, poly) for poly in polys), p


def test_the_plate_checker_notices_a_shrunk_lobe(monkeypatch):
    import foundry.mech as mech_mod
    import test_choc_v2

    shrunk = tuple((14.9375 if x == 15.0375 else x, y) for x, y in mech.CHOC_V2_STAB_PLATE)
    monkeypatch.setattr(mech_mod, "CHOC_V2_STAB_PLATE", shrunk)
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_plate_stab_opening_contains_salicylics(0.1)
