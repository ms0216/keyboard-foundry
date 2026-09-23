"""foundry の生成器が、**発注済みの HHKB の基板**を再現できるか。

**自分の生成物どうしの一致は検証ではない。**ここで突き合わせる相手は
HHKB リポジトリで利用者が手を入れて JLCPCB に出した実物の板
（e7a35cd の pcb/hhkb_split_{left,right}.kicad_pcb）から抜き出した
tests/fixtures/hhkb_boards.json。

合格条件は「差分ゼロ」ではなく「**差が意図したものだけ**」。意図した差は
ネットの名前だけ——HHKB は行をケーブル上の位置（ROW_A〜E）で名付け、foundry は
行番号（ROW0〜4）で名付ける。だから名前は一対一の対応があれば合格とする。
"""

import json

import pytest

from conftest import FIXTURES
from foundry.board_dump import key_parts
from foundry.layout import centered
from foundry.project import load

REAL = json.loads((FIXTURES / "hhkb_boards.json").read_text())


@pytest.mark.parametrize("piece", ["left", "right"])
def test_every_key_part_sits_where_the_ordered_board_has_it(hhkb_boards, piece):
    ours = key_parts(hhkb_boards[piece].read_text())
    real = REAL[piece]
    assert set(ours) == set(real), (sorted(set(ours) ^ set(real)))
    assert len(ours) >= 60                        # 空の集合どうしで緑にしない
    bad = []
    for ref, a in ours.items():
        b = real[ref]
        for k in ("x", "y"):
            if abs(a[k] - b[k]) > 1e-3:
                bad.append(f"{ref}.{k} {a[k]} / 実物 {b[k]}")
        if a["rot"] != b["rot"] % 360 or a["back"] != b["back"] or a["fp"] != b["fp"]:
            bad.append(f"{ref} 向き・面・形 {a['rot'], a['back'], a['fp']} / "
                       f"実物 {b['rot'], b['back'], b['fp']}")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("piece", ["left", "right"])
def test_the_nets_are_the_ordered_boards_nets_up_to_naming(hhkb_boards, piece):
    """キーまわりの全パッドで、ネットの対応が一対一であること。"""
    ours = key_parts(hhkb_boards[piece].read_text())
    real = REAL[piece]
    m, conflicts, n = {}, [], 0
    for ref, part in ours.items():
        for pad, net in part["pads"].items():
            rn = real[ref]["pads"].get(pad, "<無>")
            n += 1
            if m.setdefault(net, rn) != rn:
                conflicts.append(f"{ref}.{pad}: {net} → {rn}（先に {m[net]}）")
    assert n >= 100, f"突き合わせたパッドが {n} 個しかない（抜き出しが壊れている）"
    assert not conflicts, "\n".join(conflicts[:10])
    assert len(set(m.values())) == len(m), "2 つのネットが実物の 1 つに潰れている"
    assert "" not in m and "" not in m.values(), "ネットの無いパッドが混ざった"


def test_the_extraction_notices_a_moved_part(hhkb_boards):
    """**検査器が壊れていないか。**1 部品を 0.1mm 動かしたら気づくこと。"""
    import re

    from foundry.boardhash import _blocks

    text = hhkb_boards["left"].read_text()
    blk = next(b for _, b in _blocks(text) if '"Reference" "SW5"' in b)
    m = re.search(r"\n\t\t\(at ([-\d.]+) ", blk)
    moved_blk = blk[:m.start(1)] + f"{float(m.group(1)) + 0.1:.4f}" + blk[m.end(1):]
    moved = key_parts(text.replace(blk, moved_blk))
    assert abs(moved["SW5"]["x"] - key_parts(text)["SW5"]["x"] - 0.1) < 1e-6


def test_the_plate_uses_the_same_key_centres_as_the_board(hhkb_ref):
    """プレートの開口と基板のスイッチが同じ座標から出ていること（実物の板と比べる）。"""
    p = load(hhkb_ref)
    for piece in ("left", "right"):
        keys, _ = p.matrix(piece)
        positions, _ = centered(keys)
        for i, (x, y) in enumerate(positions, start=1):
            b = REAL[piece][f"SW{i}"]
            assert abs(x - b["x"]) < 1e-3 and abs(-y - b["y"]) < 1e-3, (piece, i)


def test_the_generated_board_has_no_drc_errors(hhkb_boards):
    """未配線の板に DRC のエラーが無いこと（未配線は数えない）。

    **警告も数えて固定する。**hole_to_hole はキー 1 つにつき 1 件——Kailh の
    フットプリントが持つ 0.4398mm（JLC は 0.45）。部品の寸法なので直せず、
    HHKB #50 で JLC が製造前に連絡してくる前提で受け入れた。数が変わったら
    別の穴が近づいたということ。
    """
    from conftest import require
    from foundry import drc, paths

    require(paths.KICAD_CLI, "DRC")
    for piece, n_keys in (("left", 27), ("right", 34)):
        r = drc.run(hhkb_boards[piece])
        assert r["violations"] == 0, r["details"]
        assert r["warning_kinds"].get("hole_to_hole") == n_keys, r["warning_kinds"]


def test_the_generator_refuses_a_hole_too_close_to_the_edge(hhkb_ref, tmp_path):
    """**検査器が効いているか。**基板を手前へ 1.2mm 詰めると、スペースのスタビの
    穴（ワイヤ奥に回した後の小穴で 2.14mm）が 1.0mm を割る。生成器が止まること。"""
    import shutil
    import subprocess

    from conftest import ROOT, require
    from foundry import paths

    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path / "hhkb_ref"
    shutil.copytree(hhkb_ref, d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    spec = d / "spec.py"
    spec.write_text(spec.read_text().replace("PCB_INSET_Y = 5.3", "PCB_INSET_Y = 6.5"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "穴が外形に近すぎる" in r.stderr, r.stdout + r.stderr
