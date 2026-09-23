"""ZMK のシールド。**基板と同じ行列から作られ、キーマップの数と合っていること。**"""

import re

import pytest

from foundry import check_zmk_config, zmk
from foundry.project import load


@pytest.fixture()
def shields(hhkb_ref, tmp_path, monkeypatch):
    monkeypatch.setattr(zmk, "SHIELDS", tmp_path / "shields")
    monkeypatch.setattr(check_zmk_config, "SHIELDS", tmp_path / "shields")
    p = load(hhkb_ref)
    made, unknown = zmk.scaffold(p)
    zmk.write_transform(p)
    return p, tmp_path / "shields" / "hhkb_ref", made, unknown


def _rc(text):
    body = re.search(r"map\s*=\s*<(.*?)>\s*;", re.sub(r"/\*.*?\*/", " ", text, flags=re.S), re.S)
    return [(int(r), int(c)) for r, c in re.findall(r"RC\((\d+),(\d+)\)", body.group(1))]


def test_the_transform_is_the_boards_matrix(shields):
    p, d, _, _ = shields
    rc = _rc((d / "hhkb_ref-transform.dtsi").read_text())
    rows, offsets = zmk.layout(p)
    assert rc == [x for _, _, x in rows]
    assert offsets == {"left": 0, "right": 6}          # HHKB の右 overlay の col-offset
    left_keys, left_rc = p.matrix("left")
    assert rc[:27] == left_rc


def test_the_right_half_declares_its_column_offset(shields):
    _, d, _, _ = shields
    assert "col-offset = <6>" in (d / "hhkb_ref_right.overlay").read_text()
    assert "col-offset" not in (d / "hhkb_ref_left.overlay").read_text()


def test_only_the_left_half_is_central(shields):
    _, d, _, _ = shields
    assert "SPLIT_ROLE_CENTRAL=y" in (d / "hhkb_ref_left.conf").read_text()
    assert "SPLIT_ROLE_CENTRAL" not in (d / "hhkb_ref_right.conf").read_text()


def test_every_layer_has_one_binding_per_key(shields):
    _, d, _, _ = shields
    layers = check_zmk_config.count_bindings(d / "hhkb_ref.keymap")
    assert [n for _, n in layers] == [61, 61]


def test_unknown_legends_become_none_and_are_reported(shields):
    _, d, _, unknown = shields
    assert "Fn" not in unknown                          # Fn は &mo 1
    km = (d / "hhkb_ref.keymap").read_text()
    assert "&kp ESC" in km and "&mo 1" in km


def test_missing_pins_stop_the_build_loudly(shields):
    """ピンが未定のまま雛形を作ったら、ビルドが #error で止まること（黙って空の kscan にしない）。"""
    _, d, _, _ = shields
    assert "#error" in (d / "hhkb_ref_left.overlay").read_text()


def test_scaffold_never_overwrites_what_the_user_edited(shields):
    p, d, _, _ = shields
    km = d / "hhkb_ref.keymap"
    km.write_text(km.read_text() + "\n// 利用者が直した\n")
    made, _ = zmk.scaffold(p)
    assert made == [] and "利用者が直した" in km.read_text()
