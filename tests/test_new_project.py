"""新しい機種を始める道具が、そのまま通る機種を作ること（端から端まで）。"""

import importlib.util

import pytest

from conftest import FIXTURES, ROOT
from foundry import check_zmk_config, tags, zmk
from foundry.plate import build_plate
from foundry.project import load


@pytest.fixture()
def np():
    s = importlib.util.spec_from_file_location("new_project", ROOT / "tools" / "new_project.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_a_new_split_project_loads_and_builds(np, tmp_path, monkeypatch):
    d = np.create("demo", FIXTURES / "hhkb_ref" / "layout.json", projects=tmp_path)
    p = load(d)
    assert p.spec.PIECES == ("left", "right")
    assert [len(v) for v in p.pieces().values()] == [27, 34]
    part, _, _ = build_plate(p.spec, p.pieces()["left"], "left")
    assert part.volume > 0
    # 雛形の暫定値と台帳が最初から一致していること（検査の仕組みごと渡す）
    assert tags.provisional_mismatches(d / "spec.py", d / "docs" / "provisional-values.md") == []
    monkeypatch.setattr(zmk, "SHIELDS", tmp_path / "shields")
    zmk.scaffold(p)
    zmk.write_transform(p)
    km = tmp_path / "shields" / "demo" / "demo.keymap"
    assert {n for _, n in check_zmk_config.count_bindings(km)} == {61}
    assert "$" not in (d / "docs" / "open-gaps.md").read_text()      # 置き換え漏れ


def test_it_refuses_to_overwrite_and_bad_names(np, tmp_path):
    layout = FIXTURES / "hhkb_ref" / "layout.json"
    np.create("demo", layout, projects=tmp_path)
    with pytest.raises(SystemExit):
        np.create("demo", layout, projects=tmp_path)
    with pytest.raises(SystemExit):
        np.create("Demo-1", layout, projects=tmp_path)
    with pytest.raises(SystemExit):
        np.create("uni", layout, pieces=("main",), projects=tmp_path)   # 島は 2 つ
