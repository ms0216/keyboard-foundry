"""CAD の自己検証の道具（foundry.verify）そのものが働くこと。

**このファイルが通らない限り CAD の判断に使わない。**HHKB では検査器の戻り値
（タプル）を辞書として扱い、全比較を黙って飛ばして「当たらない」と出たことがある。
答えの分かっている形で、当たる・当たらないの両方を確かめる。
"""

import math

from build123d import Box, BuildPart, Cylinder, Mode

from foundry.verify import intersection_volume, render_outline_2d, to_mesh


def _cube_with_hole():
    with BuildPart() as p:
        Box(20, 20, 20)
        Cylinder(5, 20, mode=Mode.SUBTRACT)
    return p.part


def test_volume_and_watertight_on_a_known_shape(tmp_path):
    part = _cube_with_hole()
    assert abs(part.volume - (8000 - math.pi * 25 * 20)) < 1.0
    mesh, stl = to_mesh(part, tmp_path / "c.stl")
    assert mesh.is_watertight and stl.exists()


def test_interference_is_detected_and_clearance_is_not():
    part = _cube_with_hole()
    with BuildPart() as pin:                              # 穴に収まる（当たらない）
        Cylinder(4.9, 30)
    with BuildPart() as fat:                              # 穴より太い（当たる）
        Cylinder(5.5, 30)
    assert intersection_volume(part, pin.part) < 1e-3
    assert intersection_volume(part, fat.part) > 10.0


def test_the_outline_drawing_is_actually_drawn(tmp_path):
    png = tmp_path / "o.png"
    render_outline_2d(_cube_with_hole(), png, title="cube")
    assert png.stat().st_size > 5_000
