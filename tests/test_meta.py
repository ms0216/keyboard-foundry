"""リポジトリそのものの約束。**機種によらず効く。**

HHKB で高くついたものだけを入れてある:
  - requirements を手で並べて matplotlib が抜け、CI だけ落ちた（2 回。rtree でもう 1 回）
  - KiCad の Python（3.9・pcbnew しか無い）から読むモジュールに build123d が
    混ざり、ModuleNotFoundError で落ちた（pcb_rules / part_kinds の 2 回）
  - 同じ定数を二度定義し、後から書いた方が黙って勝った（XIAO_H 5.0 → 4.0）
  - 読まれていない定数を本物と思って書き換えた
  - [暫定] の値が文書とコードで倍以上ずれていた（SW_PWR_H 8.6 / 4.0）
"""

import ast
import re
import sys

import pytest

from conftest import ROOT
from foundry import paths, tags

REQ = ROOT / "requirements-dev.txt"
# 機種の中のコード（projects/<機種>/interface.py・tools/）も数える。spec.py の定数を
# 読むのはそこで、数えないと「読まれていない」と誤る（CCKB 2026-09-24）
PY_FILES = sorted(p for d in ("foundry", "tests", "tools", "projects") for p in (ROOT / d).rglob("*.py")
                  if "fixtures" not in p.parts and p.name != "spec.py")

# import 名 → 配布名（一致しないものだけ）
DIST = {"PIL": "pillow", "yaml": "PyYAML", "mpl_toolkits": "matplotlib"}
KICAD_ONLY = {"pcbnew"}
# Blender の Python の中だけで動く（projects/*/tools/blend_assembly.py）。pip では入らない
BLENDER_ONLY = {"bpy", "mathutils"}
# listed の依存が連れてくるもの。**どれが連れてくるかを書く。**
#   OCP … build123d の実体。verify.shape_digest が直接触る
BUNDLED = {"OCP"}

# **KiCad の Python から import されるモジュール。**標準ライブラリと互いだけに頼る
KICAD_SIDE = ["paths", "layout", "matrix", "mech", "pcb_rules", "pinmap", "project",
              "parts", "boardhash", "board_dump", "pcb", "fab_fields"]


def _imports(path):
    out = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            out.add(n.module.split(".")[0])
    return out


def _listed():
    return {line.split("==")[0].strip().lower() for line in REQ.read_text().splitlines()
            if line.strip() and not line.startswith("#")}


def test_every_import_is_listed_in_requirements():
    local = {"foundry", "conftest"} | {p.stem for p in PY_FILES}
    used = set().union(*(_imports(p) for p in PY_FILES))
    ext = used - set(sys.stdlib_module_names) - local - KICAD_ONLY - BLENDER_ONLY - BUNDLED
    missing = sorted(m for m in ext if DIST.get(m, m).lower() not in _listed())
    assert not missing, f"requirements-dev.txt に無い: {missing}"


def test_the_pinned_versions_match_the_environment():
    import importlib.metadata as md

    bad = []
    for line in REQ.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, ver = line.split("==")
        try:
            got = md.version(name.strip())
        except md.PackageNotFoundError:
            bad.append(f"{name}: 環境に入っていない")
            continue
        if got != ver.strip():
            bad.append(f"{name}: 記載 {ver.strip()} / 実際 {got}")
    assert not bad, "\n".join(bad)


def test_mesh_contains_works_which_needs_rtree():
    """rtree は import 名に出ない（trimesh の contains が使う）。**動くかで見る。**"""
    import numpy as np
    import trimesh

    box = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    assert list(box.contains(np.array([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]]))) == [True, False]


@pytest.mark.parametrize("name", KICAD_SIDE)
def test_kicad_side_modules_need_only_the_standard_library(name):
    """KiCad の Python は 3.9 で、pcbnew 以外の外部モジュールが無い。"""
    path = ROOT / "foundry" / f"{name}.py"
    src = path.read_text()
    ast.parse(src, feature_version=(3, 9))            # 3.10 以降の文法で書かない
    ext = _imports(path) - set(sys.stdlib_module_names) - KICAD_ONLY - {"foundry"}
    assert not ext, f"{name}.py が {ext} を import している"
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.ImportFrom) and n.level == 1:
            mods = [n.module] if n.module else [a.name for a in n.names]
            assert set(mods) <= set(KICAD_SIDE), f"{name}.py が .{mods} に頼っている"


def _constant_files():
    return sorted(ROOT.glob("foundry/*.py")) + sorted(paths.PROJECTS.glob("*/spec.py"))


@pytest.mark.parametrize("path", _constant_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_constant_is_defined_twice(path):
    seen, dup = set(), set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ([t] if isinstance(t, ast.Name) else getattr(t, "elts", [])):
                    if isinstance(n, ast.Name) and n.id.isupper():
                        (dup if n.id in seen else seen).add(n.id)
    assert not dup, f"二度定義されている定数 {sorted(dup)}"


def test_every_constant_is_either_used_or_marked_as_a_record():
    """読まれていない定数は設計を縛らないのに、効いていると思い込ませる。
    **使う・消す・[記録のみ] と書く**のどれかにする。spec.py は foundry が
    `spec.X` / `getattr(spec, "X")` で読むので、それも「読まれた」に数える。"""
    files = PY_FILES + _constant_files()
    reads = {p: tags.names_read(p) for p in files}
    silent = []
    for path in _constant_files():
        own = {n.id for n in ast.walk(ast.parse(path.read_text()))
               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        for name, line in tags.module_constants(path).items():
            if name in own or any(name in r for p, r in reads.items() if p != path):
                continue
            if not tags.marked_record_only(path, line):
                silent.append(f"{path.relative_to(ROOT)}:{line} {name}")
    assert not silent, "読まれていないのに [記録のみ] が無い:\n  " + "\n  ".join(silent)


@pytest.mark.parametrize("spec", sorted(paths.PROJECTS.glob("*/spec.py")),
                         ids=lambda p: p.parent.name)
def test_provisional_values_are_listed_with_the_same_numbers(spec):
    """[暫定] の値が projects/<機種>/docs/provisional-values.md に**同じ数値で**載っていること。
    文書を見て部品を買うので、ずれていると入らない物を買う。"""
    bad = tags.provisional_mismatches(spec, spec.parent / "docs" / "provisional-values.md")
    assert not bad, "\n".join(bad)


def test_the_tag_scanners_actually_find_tags(tmp_path):
    """**検査器が壊れていないか。**タグを書いた偽物で数える。"""
    f = tmp_path / "spec.py"
    f.write_text("A = 1  # [暫定] 推定\n# [記録のみ] 昔の値\nB = 2\nC, D = 3, 4\n")
    assert tags.provisional(f) == [(1, ["A"])]
    assert tags.marked_record_only(f, 3) and not tags.marked_record_only(f, 4)
    assert set(tags.module_constants(f)) == {"A", "B", "C", "D"}
    doc = tmp_path / "pv.md"
    doc.write_text("| `A` | 1 | x |\n")
    assert tags.provisional_mismatches(f, doc) == []
    doc.write_text("| `A` | 2 | x |\n")                  # 数値がずれたら気づく
    assert tags.provisional_mismatches(f, doc) == ["A: コード 1 / 文書 2.0"]
