"""Kailh Choc V1 のフットプリントを**データシートと**突き合わせる。

自分の生成物どうしの一致は検証ではない。相手は Kailh の図面
CPG135001D01（keyboardio/keyswitch_documentation に保存された PDF）。
座標は KiCad（キー中心が原点・Y 下向き）。

DATASHEET_RAW: CPG135001D01-16.pdf の 1 ページ目、右下の "P.C.B Layout
(Pattern Side)" の図から 2026-09-23 に読んだ**生の値**（図に描かれた
向きのまま。中心穴を原点、Y は図の上向きを正）。

図は半田面（パターン側）から見ていて Y は図の上向きが正。KiCad の
フットプリントは部品側（上から見た向き）で Y は下向きが正。
「X を反転（半田面→部品側）」と「Y を反転（上向き→下向き）」は
どちらも**単独では鏡映（実物と左右が逆になる操作）**だが、2 回続けて
かけると鏡映が打ち消し合って**普通の回転**になり、実物のハンド性
（鏡像でないこと）が保たれる。X の反転を飛ばして Y の反転だけを
かけると鏡映が 1 回だけ残り、結果は実物の**鏡像**になる
（`test_the_checker_notices_a_mirrored_footprint` が防いでいるのはこれ）。

さらに +90° 要る。これは図面のシート内の視点どうしの違いではない
（このシートの図はどれも同じ向きで描かれている）。実物のスイッチが
キーボードの中でどちらを向いて座るか、という向きの差である。
根拠: シートの上面視（1 ページ目左端の図）ではキーキャップの軸受け
スロット（3.00 × 1.20、間隔 5.70）が**縦に**並んでいるが、Choc の
キーキャップの 2 本のポストは**横に**並ぶ（実物のキャップの向き）。
kiswitch・Keebio の 2 つの独立したライブラリもどちらもボスを左右
（横）に置いている。図の並び（縦）と実物の座り方（横）の差が
+90° になる。`_to_kicad()` がこの 3 手順（X 反転→+90° 回転→Y 反転）
をそのまま実装する。この変換を手順どおりに検算すると（端子 A
(−5.90, 0)）:
  X 反転→(+5.90, 0) → +90° 回転 (−y,x)→(0, +5.90) → Y 反転→(0, −5.90)
で、フットプリントの端子 1 `(0, −5.9)` と一致する。
"""

import re

from conftest import ROOT
from foundry.mech import SWITCHES

FP = ROOT / "lib" / "keyswitch.pretty" / "SW_Kailh_Choc_V1.kicad_mod"

# 図から読んだ生の値（Pattern Side・中心穴を原点・Y は図の上向きが正）。
# CPG135001D01-16.pdf 1 ページ目 "P.C.B Layout (Pattern Side)"。2026-09-23 に読んだ。
DATASHEET_RAW = {
    "pins": {"1": (-5.90, 0.0), "2": (-3.80, -5.00)},   # 端子 φ1.2 相当の穴
    "pin_drill_min": 1.2,
    "center": (0.0, 0.0, 3.4),                            # 中心の穴 (x, y, 直径)
    "bosses": [(0.0, 5.50), (0.0, -5.50)],
    "boss_d": 1.9,
    "plate_cutout": 13.8,
}


def _to_kicad(x, y):
    """パターン側（半田面・Y 上向き）視点の図の座標 → KiCad（部品側・Y 下向き）の座標。

    手順: (1) X を反転（半田面→部品側。単独では鏡映）→
          (2) +90° 回転 (x, y) → (-y, x)（図の並びは縦だが、実物は
              キーキャップのポストが横に並ぶ向きで座る）→
          (3) Y を反転（上向き→下向き。単独では鏡映）。
    (1) と (3) はどちらも鏡映だが、2 回かけると打ち消し合って回転に
    戻る。(1) を飛ばすと鏡映が 1 回だけ残り、実物の鏡像になる。
    """
    x = -x                     # (1) X 反転
    x, y = -y, x                # (2) +90° 回転
    y = -y                      # (3) Y 反転
    return (x, y)


DATASHEET = {
    "pins": {n: _to_kicad(*xy) for n, xy in DATASHEET_RAW["pins"].items()},
    "pin_drill_min": DATASHEET_RAW["pin_drill_min"],
    "center": _to_kicad(*DATASHEET_RAW["center"][:2]) + (DATASHEET_RAW["center"][2],),
    "bosses": [_to_kicad(x, y) for x, y in DATASHEET_RAW["bosses"]],
    "boss_d": DATASHEET_RAW["boss_d"],
    "plate_cutout": DATASHEET_RAW["plate_cutout"],
}


def test_the_conversion_matches_the_known_good_footprint_by_hand():
    """変換手順そのものを検算する。**この検査が壊れたら DATASHEET も壊れている。**"""
    assert DATASHEET["pins"]["1"] == (0.0, -5.9)
    assert DATASHEET["pins"]["2"] == (5.0, -3.8)
    assert set(DATASHEET["bosses"]) == {(-5.5, 0.0), (5.5, 0.0)}
    assert DATASHEET["center"][:2] == (0.0, 0.0)


def _pads():
    out = []
    for m in re.finditer(r"\(pad \"?([^\"\s]*)\"? (\w+) circle \(at ([-\d.]+) ([-\d.]+)\)"
                         r".*?\(drill ([\d.]+)\)", FP.read_text(), re.S):
        num, kind, x, y, drill = m.groups()
        out.append((num, kind, float(x), float(y), float(drill)))
    return out


def test_the_pins_are_where_the_datasheet_puts_them():
    pads = _pads()
    assert len(pads) >= 5                                 # 空の集合で緑にしない
    for num, (x, y) in DATASHEET["pins"].items():
        hit = [p for p in pads if p[0] == num and p[1] == "thru_hole"]
        assert hit, f"端子 {num} が無い"
        assert all(abs(p[2] - x) < 0.05 and abs(p[3] - y) < 0.05 for p in hit), hit
        assert all(p[4] >= DATASHEET["pin_drill_min"] for p in hit), hit


def test_the_center_hole_and_bosses_match():
    npth = [p for p in _pads() if p[1] == "np_thru_hole"]
    cx, cy, cd = DATASHEET["center"]
    centre = [p for p in npth if abs(p[2] - cx) < 1e-6 and abs(p[3] - cy) < 1e-6]
    assert centre and centre[0][4] >= cd, centre
    for bx, by in DATASHEET["bosses"]:
        b = [p for p in npth if abs(p[2] - bx) < 0.05 and abs(p[3] - by) < 0.05]
        assert b and b[0][4] >= DATASHEET["boss_d"], (bx, by, npth)


def test_the_switch_table_uses_this_footprint_and_the_datasheet_cutout():
    sw = SWITCHES["choc_v1"]
    assert set(sw.fp.values()) == {FP.stem}
    assert sw.cutout == DATASHEET["plate_cutout"]
    assert sw.plate_t == 1.2                  # Choc スタビがプレート 1.2mm を要求（設計書 D2）


def test_the_checker_notices_a_moved_pin(tmp_path, monkeypatch):
    """**検査器が壊れていないか。**端子 2 を 0.1mm 動かした偽物で落ちること。"""
    import pytest

    import test_choc

    fake = tmp_path / FP.name
    fake.write_text(FP.read_text().replace("(at 5 -3.8)", "(at 5.1 -3.8)"))
    monkeypatch.setattr(test_choc, "FP", fake)
    with pytest.raises(AssertionError):
        test_choc.test_the_pins_are_where_the_datasheet_puts_them()


def test_the_checker_notices_a_mirrored_footprint(tmp_path, monkeypatch):
    """**ハンド性（鏡像）のズレも検出できるか。**

    鏡像を飛ばして回転だけで直すと、端子 2 は (5, -3.8) ではなく
    (-5, -3.8) になる（X の符号だけが逆）。0.1mm のズレとは別種の
    間違い方なので、専用に検査する。
    """
    import pytest

    import test_choc

    fake = tmp_path / FP.name
    fake.write_text(FP.read_text().replace("(at 5 -3.8)", "(at -5 -3.8)"))
    monkeypatch.setattr(test_choc, "FP", fake)
    with pytest.raises(AssertionError):
        test_choc.test_the_pins_are_where_the_datasheet_puts_them()


REF = ROOT / "projects" / "cckb" / "docs" / "references"


def _keebio_right_cutout():
    """Keebio の開口のうち右側（x > 8）の頂点を、Y 上向き・支点原点に直して返す。"""
    pts = set()
    for x1, y1, x2, y2 in re.findall(
            r"\(fp_line \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) \(layer Edge.Cuts\)",
            (REF / "Kailh-PG1350-Stab-Cutout.kicad_mod").read_text()):
        for x, y in ((x1, y1), (x2, y2)):
            if float(x) > 8.0:
                pts.add((round(float(x) - 12.0, 3), round(-float(y), 3)))
    return pts


def test_the_stab_half_span_is_the_drawings_wire():
    """製造図のワイヤ 24.00 と Keebio の開口の中心 12.0 が一致（2 つの出典）。"""
    sw = SWITCHES["choc_v1"]
    assert sw.stab_kind == "choc"
    for w in (2.0, 2.25):
        assert sw.stab_offset_for(w) == 24.0 / 2


def test_the_stab_outline_is_keebios():
    from foundry.mech import CHOC_STAB_OUTLINE

    ref = _keebio_right_cutout()
    assert len(ref) == 8                                   # 空の集合で緑にしない
    assert {(round(x, 3), round(y, 3)) for x, y in CHOC_STAB_OUTLINE} == ref


def test_the_outline_leaves_a_web_to_the_switch_opening():
    """スイッチの開口（13.8）とスタビの開口の間に、刷れる幅（≧ 0.4×4）の桟が残ること。"""
    from foundry.mech import CHOC_STAB_OUTLINE

    inner = 12.0 + min(x for x, _ in CHOC_STAB_OUTLINE)
    assert inner - SWITCHES["choc_v1"].cutout / 2 >= 1.6, inner


def test_the_plate_cuts_both_stab_openings():
    from foundry.plate import choc_stab_polygons

    polys = choc_stab_polygons(12.0, at=(100.0, 50.0))
    assert len(polys) == 2
    xs = sorted(sum(x for x, _ in p) / len(p) for p in polys)
    assert abs(xs[0] - 88.0) < 0.5 and abs(xs[1] - 112.0) < 0.5
