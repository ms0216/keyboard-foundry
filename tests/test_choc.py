"""Kailh Choc V1 のフットプリントを**データシートと**突き合わせる。

自分の生成物どうしの一致は検証ではない。相手は Kailh の図面
CPG135001D01（keyboardio/keyswitch_documentation に保存された PDF）。
座標は KiCad（キー中心が原点・Y 下向き）。

DATASHEET_RAW: CPG135001D01-16.pdf の 1 ページ目、右下の "P.C.B Layout
(Pattern Side)" の図から 2026-09-23 に読んだ**生の値**（図に描かれた
向きのまま。中心穴を原点、Y は図の上向きを正）。

この図は半田面（パターン側）から見た図で、部品側（KiCad の慣例である
上面視）に直すには
  1. X を反転する（パターン側視点は部品側視点の**鏡像**であり、
     回転では戻らない。裏から見ているので左右が反転している）
  2. 図自体が用紙の上で 90° 回して描かれているので、+90°（反時計回り）
     回転する： (x, y) → (−y, x)
  3. KiCad は Y が下向きなので Y を反転する
の 3 手順が要る。`_to_kicad()` がこれをそのまま実装する。この変換を
手順どおりに検算すると（端子 A (−5.90, 0)）:
  鏡像 X→(+5.90, 0) → 回転 (−y,x)→(0, +5.90) → Y 反転 →(0, −5.90)
で、フットプリントの端子 1 `(0, −5.9)` と一致する。鏡像を飛ばして
回転だけで直すと `(0, +5.90)` の Y 反転前の符号が変わらず、
ハンド性（鏡像）が逆の値になり、実物のピンがフットプリントに刺さらない
形になる（このズレは今回の Task 2 レビューで一度実際に書きかけた。
`test_the_checker_notices_a_mirrored_footprint` がこれを検出する）。
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
    """パターン側（半田面）視点の図の座標 → KiCad（部品側・Y 下向き）の座標。

    手順: (1) X を反転（鏡像。裏から見ているため） →
          (2) +90° 回転 (x, y) → (-y, x)（図が用紙上で回して描かれている）→
          (3) Y を反転（KiCad は Y 下向き）
    """
    x = -x                    # (1) 鏡像
    x, y = -y, x               # (2) +90° 回転
    y = -y                     # (3) Y 下向きへ
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
