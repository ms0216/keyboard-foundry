"""スイッチの種類。**既定値で埋めない**——spec.py に書いていない種類で黙って作らない。"""

import types

import pytest

from foundry import mech
from foundry.project import load


def test_the_reference_machine_names_mx_hotswap(hhkb_ref):
    sw = mech.switch_of(load(hhkb_ref).spec)
    assert sw is mech.SWITCHES["mx_hotswap"]
    assert (sw.cutout, sw.plate_t, sw.value) == (14.0, 1.5, "CPG151101S11-2")


def test_an_unknown_switch_name_is_refused():
    with pytest.raises(ValueError, match="SWITCHES"):
        mech.switch_of(types.SimpleNamespace(SWITCH="alps"))


def test_a_spec_without_switch_is_refused(hhkb_ref, tmp_path):
    import shutil

    d = tmp_path / "p"
    shutil.copytree(hhkb_ref, d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    s = d / "spec.py"
    s.write_text("\n".join(l for l in s.read_text().splitlines() if not l.startswith("SWITCH")))
    with pytest.raises(AttributeError, match="SWITCH"):
        load(d)


def test_a_width_without_footprint_is_refused():
    with pytest.raises(RuntimeError, match="1.25u"):
        mech.SWITCHES["mx_hotswap"].footprint(1.25)
