"""Kailh Choc V1 のフットプリントを**データシートと**突き合わせる。

自分の生成物どうしの一致は検証ではない。相手は Kailh の図面
CPG135001D01（keyboardio/keyswitch_documentation に保存された PDF）。
座標は KiCad（キー中心が原点・Y 下向き）。

DATASHEET: CPG135001D01-16.pdf の 1 ページ目、右下の "P.C.B Layout
(Pattern Side)" の図から 2026-09-23 に読んだ。この図はスイッチを
半田面（パターン側）から見た図で、端子②を上・端子①を下に描いた
向きになっており、KiCad の慣例（上面視）に対して 90° 回っている。
図から読んだ生の値は「行の間隔 5.00・列の間隔 2.10」で、上流の
2 つのライブラリ（kiswitch・Keebio、どちらも本フットプリントと
同じ (0, -5.9) / (5, -3.8)）が使っている値の分解（Δx=5.00・
Δy=2.10）と、軸を入れ替えただけで数値が一致する
（図: Δy=5.00・Δx=2.10 ↔ ライブラリ: Δx=5.00・Δy=2.10）。
90° の食い違いは図が Pattern Side（パターン側）視点であることで
説明がつき、大きさの矛盾ではないので、2 つの独立したライブラリが
揃えている座標系（KiCad 上面視）を採用する。中心穴 φ3.40・ボス
φ1.90・端子 φ1.20 相当（ドリル）・開口 13.80 は軸の向きに関わらず
そのまま一致する。
"""

import re

from conftest import ROOT
from foundry.mech import SWITCHES

FP = ROOT / "lib" / "keyswitch.pretty" / "SW_Kailh_Choc_V1.kicad_mod"

# CPG135001D01 の推奨 PCB 穴（図から読んだ値。読んだ日と図の番号を書く）
DATASHEET = {
    "pins": {"1": (0.0, -5.9), "2": (5.0, -3.8)},   # 端子 φ1.2 相当の穴
    "pin_drill_min": 1.2,
    "center": 3.4,                                   # 中心の穴
    "bosses": [(-5.5, 0.0), (5.5, 0.0)],
    "boss_d": 1.9,
    "plate_cutout": 13.8,
}


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
    centre = [p for p in npth if abs(p[2]) < 1e-6 and abs(p[3]) < 1e-6]
    assert centre and centre[0][4] >= DATASHEET["center"], centre
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
