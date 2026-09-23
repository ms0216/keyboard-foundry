"""KLE の読み込み。**HHKB の配列で外の事実（実機の数え方）と突き合わせる。**"""

import json

import pytest

from conftest import FIXTURES
from foundry.layout import UNIT, islands, keymap_order, load_layout

HHKB = FIXTURES / "hhkb_ref" / "layout.json"


def test_hhkb_split_has_61_keys_in_two_islands_of_27_and_34():
    keys = load_layout(HHKB)
    assert len(keys) == 61
    assert [len(i) for i in islands(keys)] == [27, 34]


def test_pitch_is_19_05mm_between_neighbours():
    row = sorted((k for k in load_layout(HHKB) if round(k.y_mm, 2) == round(UNIT / 2, 2)),
                 key=lambda k: k.x_mm)
    gaps = [round(b.left_u - a.right_u, 6) for a, b in zip(row, row[1:])]
    # 同じ島の中は隙間 0（＝中心間 19.05 の倍数）。島の間の 1 か所だけ 1u 以上
    assert sorted(g for g in gaps if g) and all(g >= 1 for g in gaps if g), gaps
    assert sum(1 for g in gaps if g) == 1, gaps


def test_attributes_apply_to_one_key_only():
    keys = load_layout(HHKB)
    widths = sorted({k.w_u for k in keys})
    assert all((w * 4).is_integer() for w in widths)
    assert widths[0] == 1.0


def test_keymap_order_is_top_row_first_then_left_to_right():
    keys = keymap_order(islands(load_layout(HHKB))[0])
    ys = [round(k.y_mm, 2) for k in keys]
    assert ys == sorted(ys)
    assert [k.label for k in keys[:3]] == ["Esc", "1", "2"]


@pytest.mark.parametrize("attr", ["r", "rx", "w2"])
def test_rotation_and_iso_keys_are_refused_not_ignored(tmp_path, attr):
    """黙って無視すると座標のずれた基板ができる。"""
    f = tmp_path / "k.json"
    f.write_text(json.dumps([[{attr: 15}, "A", "B"]]))
    with pytest.raises(ValueError):
        load_layout(f)


def test_a_unibody_layout_is_one_island(tmp_path):
    f = tmp_path / "k.json"
    f.write_text(json.dumps([["Q", "W", "E"], ["A", "S", "D"]]))
    assert [len(i) for i in islands(load_layout(f))] == [6]
