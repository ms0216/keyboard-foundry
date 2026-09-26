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
FP = LIB / "SW_Kailh_Choc_V2_Common.kicad_mod"
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


# JLC の丸穴の公差（非めっき。JLC のブログ npth-design-guide「±0.08」・能力表の穴の公差 +0.13/−0.08 の小さい側）と
# 穴の位置の公差（能力表「Hole Position Tolerance ±0.05」）。2026-09-26 に読んだ
JLC_HOLE_MINUS = 0.08
JLC_HOLE_POS = 0.05


def _locator():
    loc = [p for p in _pads(FP) if p["kind"] == "np_thru_hole" and (p["x"], p["y"]) != (0.0, 0.0)]
    assert len(loc) == 1, loc
    return loc[0]


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_the_locating_hole_takes_each_drawings_hole(name):
    """位置決め穴は 3 枚の図の推奨の穴の**和**を含む（標準 φ1.6・静音 長円 2.0×1.5）。**JLC の公差で最も小さく
    開いても**（径 −0.08）。めっき無し。"""
    h = _locator()
    assert h["size"] == h["drill"]                          # 銅の輪が無い（行のバスを近くに通せる理由）
    c, size = _source_hole(DRAWINGS[name]["locate"])
    small = tuple(d - JLC_HOLE_MINUS for d in h["drill"])
    for p in _stadium_rim(c, size):
        assert _in_stadium(p, (h["x"], h["y"]), small), (name, p, h)


def test_the_locating_hole_is_round():
    """JLC は長円を「長さ ≧ 幅 × 2」でしか作らない（能力表）。1.6 × 2.0 の長円（比 1.25）はやめた（2026-09-26）。"""
    h = _locator()
    assert h["shape"] == "circle" and h["drill"][0] == h["drill"][1], h


def test_the_nubs_under_the_switch_fit_the_worst_hole():
    """底面図の突起（mech.CHOC_V2_LOCATOR_NUBS・画素で読んだ）の角が、JLC の公差で最も小さく・最もずれて開いた穴の中。"""
    h = _locator()
    r = (h["drill"][0] - JLC_HOLE_MINUS) / 2 - JLC_HOLE_POS
    far = max(math.hypot(x - h["x"], y - h["y"]) for x0, y0, x1, y1 in mech.CHOC_V2_LOCATOR_NUBS
              for x in (x0, x1) for y in (y0, y1))
    assert 0.7 < far and far + 0.1 <= r, (far, r)                 # 0.1 = 画素の読みの幅


def test_the_footprint_is_kiswitch_but_the_locating_hole():
    """上流（kiswitch SW_Kailh_Choc_V2・無改変の写し）との差は、名前と位置決め穴の 1 行だけ。"""
    up = UPSTREAM.read_text().splitlines()
    mine = FP.read_text().splitlines()
    assert len(up) == len(mine)
    diff = [(a, b) for a, b in zip(up, mine) if a != b]
    assert len(diff) == 4, diff
    changed_pads = [(a, b) for a, b in diff if "(pad" in a]
    assert len(changed_pads) == 1
    a, b = changed_pads[0]
    assert "thru_hole circle (at -5 5.15)" in a and "np_thru_hole circle (at -5 5.15)" in b


def test_the_switch_table_uses_the_footprint_and_the_drawings_plate():
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
    ("(at -5 5.15) (size 2.1 2.1)", "(at -5 5.25) (size 2.1 2.1)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 位置決めを y 0.1
    ("(at -5 5.15) (size 2.1 2.1)", "(at -5.1 5.15) (size 2.1 2.1)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 位置決めを x 0.1
    ("(size 2.1 2.1) (drill 2.1)", "(size 2.0 2.0) (drill 2.0)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # φ2.0（公差 −0.08 で静音の端を割る）
    ("(size 2.1 2.1) (drill 2.1)", "(size 1.6 1.6) (drill 1.6)",
     "test_the_locating_hole_takes_each_drawings_hole"),                                   # 標準の φ1.6 だけ
])
def test_the_switch_checker_notices_a_break(tmp_path, monkeypatch, old, new, test):
    import test_choc_v2

    _break(tmp_path, monkeypatch, old, new)
    with pytest.raises(AssertionError):
        for name in sorted(DRAWINGS):
            getattr(test_choc_v2, test)(name)


def test_the_round_check_notices_the_first_boards_slot(tmp_path, monkeypatch):
    """1 回目の板の長円 1.6 × 2.0 に戻すと落ちる。"""
    import test_choc_v2

    _break(tmp_path, monkeypatch, "np_thru_hole circle (at -5 5.15) (size 2.1 2.1) (drill 2.1)",
           "np_thru_hole oval (at -5 5.15) (size 1.6 2) (drill oval 1.6 2)")
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_locating_hole_is_round()


def test_the_nub_check_notices_a_small_hole(tmp_path, monkeypatch):
    """標準の推奨の φ1.6 に JLC の公差を足すと、突起の角（中心から約 0.79）が穴の縁に掛かる。"""
    import test_choc_v2

    _break(tmp_path, monkeypatch, "(size 2.1 2.1) (drill 2.1)", "(size 1.6 1.6) (drill 1.6)")
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_nubs_under_the_switch_fit_the_worst_hole()


# ---------------------------------------------------------------------------
# スタビ（遊舎工房 A050001-01-1）
# ---------------------------------------------------------------------------

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


def stab_hole_problems(H=None, pivot=None):
    """開ける穴（mech.CHOC_V2_STAB_HOLES・支点 mech.CHOC_V2_STAB_PIVOT）が、2026-09-26 に利用者と決めた形か。
    **正は販売者の足跡（実物の実測）**、図は参照。穴は**きつい側**（発注後に広げられる）:
      支点 = 足跡の 11.9。ねじ・爪の中心 y = 足跡（−6.2・+8.24）。どちらも**丸**（JLC の長円の比を満たさない長円を開けない）。
      ねじ φ = 図の φ3.00。足跡の長円 3.2 × 3.4 の短い幅より小さい（ゆるい側に倒さない）。ナットの胴（spec.STAB_NUT_D）が
      JLC の丸穴の公差の最悪（−0.08）でも入る。
      爪 φ = 図の φ4.00 = 足跡の長円 3.0 × 4.0 の長い幅。
      箱の穴 x = 足跡の 6.0（支点 ± 3.0）・y = 図の推奨 8.00（±4.0）。図の箱 5.80 × 7.30 を含む。"""
    from foundry.project import load

    H = mech.CHOC_V2_STAB_HOLES if H is None else H
    pivot = mech.CHOC_V2_STAB_PIVOT if pivot is None else pivot
    sal, drw = mech.CHOC_V2_STAB_SOURCES["salicylic"], mech.CHOC_V2_STAB_SOURCES["drawing"]
    nut = load("cckb").spec.STAB_NUT_D
    out = []
    if pivot != sal["pivot"] or SWITCHES["choc_v2"].stab_offset[2.25] != pivot:
        out.append(f"支点 {pivot}（足跡 {sal['pivot']}）")
    for k in ("screw", "claw"):
        c, d = H[k]
        if not isinstance(d, (int, float)):
            out.append(f"{k} が丸でない {d}")
            return out
        if c != (0.0, sal[k][0]):
            out.append(f"{k} の中心 {c}（足跡 (0, {sal[k][0]})）")
        if d != drw[k][1] or drw[k][1] != drw[k][2]:
            out.append(f"{k} の径 {d}（図 φ{drw[k][1]}）")
    if H["screw"][1] >= min(sal["screw"][1:]):
        out.append(f"ねじの穴 φ{H['screw'][1]} が足跡の長円の幅 {min(sal['screw'][1:])} 以上（ゆるい側）")
    if H["screw"][1] - 0.08 < nut + 0.1:
        out.append(f"ねじの穴 φ{H['screw'][1]} の最悪 −0.08 にナットの胴 φ{nut} が片側 0.05 で入らない")
    if H["claw"][1] != max(sal["claw"][1:]):
        out.append(f"爪の穴 φ{H['claw'][1]} が足跡の長円の長い幅 {max(sal['claw'][1:])} と違う")
    x0, y0, x1, y1 = H["box"]
    if (x1 - x0, -x0, x1) != (sal["box"][0], sal["box"][0] / 2, sal["box"][0] / 2):
        out.append(f"箱の穴の x {x0}〜{x1}（足跡 ±{sal['box'][0] / 2}）")
    if (y1 - y0, -y0, y1) != (drw["box"][1], drw["box"][1] / 2, drw["box"][1] / 2):
        out.append(f"箱の穴の y {y0}〜{y1}（図 ±{drw['box'][1] / 2}）")
    pw, pd = drw["part"]
    if not (x0 < -pw / 2 and pw / 2 < x1 and y0 < -pd / 2 and pd / 2 < y1):
        out.append(f"箱の穴が箱 {drw['part']} を含まない")
    return out


def test_the_stab_holes_are_what_we_decided():
    assert stab_hole_problems() == []


@pytest.mark.parametrize("key, value", [
    ("pivot", 12.0),                                       # 図の支点に戻す
    ("screw", ((0.0, -6.2), (3.2, 3.4))),                  # 足跡の長円（前の板）
    ("screw", ((0.0, -6.2), 3.2)),                         # ゆるい側の丸
    ("screw", ((0.0, -6.2), 2.9)),                         # ナットの胴が公差の最悪で入らない
    ("claw", ((0.0, 8.37), 4.0)),                          # 前の板の爪の位置
    ("claw", ((0.0, 8.24), 4.4)),                          # ゆるい側
    ("box", (-3.1, -4.0, 3.0, 4.0)),                       # 前の板の箱の穴（支点 24.0 も含めた和）
    ("box", (-3.0, -3.75, 3.0, 3.75)),                     # 足跡の y 7.5
])
def test_the_stab_hole_check_notices_a_break(key, value):
    if key == "pivot":
        assert stab_hole_problems(pivot=value)
    else:
        H = dict(mech.CHOC_V2_STAB_HOLES)
        H[key] = value
        assert stab_hole_problems(H), (key, value)


def test_the_stab_footprint_is_the_holes():
    """フットプリント（KiCad・Y 下向き）の非めっきの丸穴 4 つ = mech.CHOC_V2_STAB_HOLES を左右に、
    ワイヤを奥（KiCad の −y）に置いた物。"""
    s = SWITCHES["choc_v2"].stab_offset[2.25]
    H = mech.CHOC_V2_STAB_HOLES
    want = set()
    for side in (-1, 1):
        for k in ("screw", "claw"):
            (hx, hy), d = H[k]
            want.add((round(side * (s + hx), 3), round(-hy, 3), d, d))
    pads = _pads(STAB_FP)
    got = {(round(p["x"], 3), round(p["y"], 3), *p["drill"]) for p in pads}
    assert len(pads) == 4 and all(p["kind"] == "np_thru_hole" and p["shape"] == "circle"
                                  and p["size"] == p["drill"] for p in pads), pads
    assert got == want, (got, want)
    assert SWITCHES["choc_v2"].stab_fp == {s: STAB_FP.stem}


@pytest.mark.parametrize("old, new", [
    ("(at 11.9 6.2)", "(at 12.0 6.2)"),                  # ねじを 0.1
    ("(at -11.9 -8.24)", "(at -11.9 -8.14)"),            # 爪を 0.1
    ("(size 4 4) (drill 4)", "(size 4.2 4.2) (drill 4.2)"),                     # 爪の径を 0.2
    ("np_thru_hole circle (at 11.9 6.2) (size 3 3) (drill 3)",
     "np_thru_hole oval (at 11.9 6.2) (size 3.2 3.4) (drill oval 3.2 3.4)"),     # 前の長円
])
def test_the_stab_checker_notices_a_break(tmp_path, monkeypatch, old, new):
    import test_choc_v2

    _break(tmp_path, monkeypatch, old, new, target="STAB_FP")
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_stab_footprint_is_the_holes()


# 基板の下の爪の先（支点の y で、キーの中心から奥へ）。mech の CHOC_V2_STAB_PLATE のコメントの読み: 上面図の 10.95 まで
# の 0.70 は、基板の穴を通って基板の下で開く爪の先（**読み**。見本で確かめる V9）
STAB_CLAW_TIP_Y = 10.95
COURTYARD_MARGIN = 0.25          # F.CrtYd と同じ（本体 ＋ 0.25）


def _courtyard(path, layer):
    """その層のコートヤードの線の端点から、左右（x の符号）ごとの外接矩形 (x0, y0, x1, y1)（KiCad・Y 下向き）。"""
    pts = [(float(a), float(b)) for m in re.finditer(rf"\(fp_line \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)"
                                                     rf" \(layer {re.escape(layer)}\)", path.read_text())
           for a, b in (m.group(1, 2), m.group(3, 4))]
    out = {}
    for s in (-1, 1):
        q = [p for p in pts if p[0] * s > 0]
        if q:
            out[s] = (min(x for x, _ in q), min(y for _, y in q), max(x for x, _ in q), max(y for _, y in q))
    return out


def test_the_stab_footprint_has_a_bottom_courtyard():
    """B.CrtYd（基板の下に出る物）が、左右それぞれ箱（図の 5.80 × 7.30）・ねじの頭（spec.STAB_SCREW_HEAD_D。
    ねじの穴の真下）・爪（爪の穴 φ4.0 と、下で開く先 STAB_CLAW_TIP_Y）を COURTYARD_MARGIN 以上で包む
    （2026-09-26 の 2 回目の V2 監査 B-3。前は表の F.CrtYd だけで、裏の部品との重なりを DRC が見なかった）。"""
    from foundry.project import load

    spec = load("cckb").spec
    s = SWITCHES["choc_v2"].stab_offset[2.25]
    bw, bh = mech.CHOC_V2_STAB_SOURCES["drawing"]["part"]
    (_, sy), _ = mech.CHOC_V2_STAB_HOLES["screw"]
    (_, cy), cd = mech.CHOC_V2_STAB_HOLES["claw"]
    cy_ = _courtyard(STAB_FP, "B.CrtYd")
    assert set(cy_) == {-1, 1}, cy_
    m = COURTYARD_MARGIN - 1e-9
    for side, (x0, y0, x1, y1) in cy_.items():
        px = side * s
        need = [(px - bw / 2, -bh / 2, px + bw / 2, bh / 2),                                  # 箱（KiCad の y は −y が奥）
                (px - spec.STAB_SCREW_HEAD_D / 2, -sy - spec.STAB_SCREW_HEAD_D / 2,
                 px + spec.STAB_SCREW_HEAD_D / 2, -sy + spec.STAB_SCREW_HEAD_D / 2),            # ねじの頭（手前 +y）
                (px - cd / 2, -STAB_CLAW_TIP_Y, px + cd / 2, -cy + cd / 2)]                      # 爪（奥 −y）
        for a0, b0, a1, b1 in need:
            assert x0 <= a0 - m and y0 <= b0 - m and x1 >= a1 + m and y1 >= b1 + m, (side, (x0, y0, x1, y1), (a0, b0, a1, b1))


def test_the_bottom_courtyard_check_notices_it_missing(tmp_path, monkeypatch):
    """B.CrtYd を B.Fab に書き換えた（コートヤードが無い）足跡で落ちる。ねじの頭の側を 0.5 縮めても落ちる。"""
    import test_choc_v2

    _break(tmp_path, monkeypatch, "(layer B.CrtYd)", "(layer B.Fab)", target="STAB_FP")
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_stab_footprint_has_a_bottom_courtyard()
    monkeypatch.undo()
    _break(tmp_path, monkeypatch, " 8.375)", " 7.875)", target="STAB_FP")      # 手前の辺（ねじの頭の側）だけ
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_stab_footprint_has_a_bottom_courtyard()


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


def test_the_plate_stab_opening_contains_salicylics():
    """プレートの開口（kerf 0）は、サリチル酸さんの開口（支点 11.90625）を含む。**CHOC_V2_STAB_PLATE の座標は CAD で
    ワイヤが +y**（KiCad でワイヤ +y のサリチル酸さんの図をそのまま使える: CAD は Y を反転し、さらにワイヤを奥へ
    180° 回すので y は同じ）。"""
    from foundry.plate import choc_v2_stab_polygons

    polys = choc_v2_stab_polygons()
    pts = _sal_plate_points()
    assert len(pts) > 20
    trimmed = 0
    for x, y in pts:
        # **ただ 1 つの例外: 羽の奥の端**（10.85 → mech.CHOC_V2_STAB_PLATE_BACK 10.72）。1 段奥の開口との帯を
        # PLATE_MIN_WEB に保つために 0.13 詰めた。詰めてよい根拠は下の test_the_plate_stab_back_clears_the_drawing
        y = min(y, mech.CHOC_V2_STAB_PLATE_BACK) if y > mech.CHOC_V2_STAB_PLATE_BACK else y
        trimmed += y == mech.CHOC_V2_STAB_PLATE_BACK
        assert any(_in_poly((x, y), poly) for poly in polys), (x, y)
    assert 0 < trimmed and 10.85 - mech.CHOC_V2_STAB_PLATE_BACK <= 0.13 + 1e-9


def plate_extent_problems(poly=None):
    """開口（kerf 0）の羽が**サリチル酸さんの開口の値のまま**か（外接する矩形の辺）。足跡から変えてよいのは
    奥の端（CHOC_V2_STAB_PLATE_BACK）と、穴が大きくなる向きの丸め（左右の和・円弧 → 矩形）だけ。
    前は支点 24.0 のために羽の外の辺を +0.1 広げていた（15.0375）。"""
    poly = mech.CHOC_V2_STAB_PLATE if poly is None else poly
    outer = max(abs(x) for x, _ in _sal_plate_points())   # 14.9375（右）/ 14.93375（左）
    wing_x = sorted({x for x, _ in poly if x > 8.8})
    ys = [y for _, y in poly]
    out = []
    if abs(max(wing_x) - outer) > 1e-9:
        out.append(f"羽の外の辺 {max(wing_x)}（足跡 {outer}）")
    if abs(min(wing_x) - 8.87125) > 1e-9:
        out.append(f"羽の内の辺 {min(wing_x)}（足跡の左右の和 8.87125）")
    if abs(min(ys) + 9.45) > 1e-9 or abs(max(ys) - mech.CHOC_V2_STAB_PLATE_BACK) > 1e-9:
        out.append(f"羽の y {min(ys)}〜{max(ys)}")
    if (8.375, 9.85) not in poly:
        out.append("ワイヤの帯（|x| < 8.375・y 9.85 まで）")
    return out


def test_the_plate_stab_opening_is_salicylics_but_the_listed_changes():
    assert plate_extent_problems() == []


def test_the_plate_extent_check_notices_the_old_widening():
    old = tuple((15.0375 if x == 14.9375 else x, y) for x, y in mech.CHOC_V2_STAB_PLATE)
    assert plate_extent_problems(old)


def test_the_plate_stab_back_clears_the_drawing():
    """羽の奥の端（kerf 0）は、スタビの図のプレートの高さで奥にいちばん出る所（爪の輪の端 = 8.50 + φ3.50/2 = 10.25）
    より 0.4 以上奥。手前の端も図のねじの側の端（全長 18.75 − 10.25 = 8.50）より 0.4 以上手前。
    0.4 = 支点の位置のずれ（箱 7.30 と穴 7.5 の y の遊び 0.1 ＋ JLC の外形 ±0.2）とプレートのずれ（開口 13.95 と胴 ±0.05・
    突起 φ4.8 と穴 φ5.05 の 0.125）の和に近い値。刷った穴の縮みは STAB_KERF が別に受け持つ。"""
    d = mech.CHOC_V2_STAB_SOURCES["drawing"]
    back = d["claw"][0] + d["ring"] / 2
    front = d["length"] - back
    ys = [y for x, y in mech.CHOC_V2_STAB_PLATE if x > 8.8]
    assert abs(back - 10.25) < 1e-9 and abs(front - 8.50) < 1e-9
    assert max(ys) - back >= 0.4 and -min(ys) - front >= 0.4, (max(ys), min(ys))


def test_the_back_check_notices_a_back_edge_at_the_ring(monkeypatch):
    import test_choc_v2

    moved = tuple((x, 10.5 if y == mech.CHOC_V2_STAB_PLATE_BACK else y) for x, y in mech.CHOC_V2_STAB_PLATE)
    monkeypatch.setattr(mech, "CHOC_V2_STAB_PLATE", moved)
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_plate_stab_back_clears_the_drawing()


def test_the_plate_checker_notices_a_shrunk_lobe(monkeypatch):
    import foundry.mech as mech_mod
    import test_choc_v2

    shrunk = tuple((14.8375 if x == 14.9375 else x, y) for x, y in mech.CHOC_V2_STAB_PLATE)
    monkeypatch.setattr(mech_mod, "CHOC_V2_STAB_PLATE", shrunk)
    with pytest.raises(AssertionError):
        test_choc_v2.test_the_plate_stab_opening_contains_salicylics()
