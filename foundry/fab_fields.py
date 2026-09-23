"""**実際に発注する道具（Fabrication Toolkit）が読むものを板に焼き込む。KiCad の Python。**

    "$KICAD_PYTHON" -m foundry.fab_fields <機種> [板.kicad_pcb ...]   # 既定は pcb/*.kicad_pcb

発注は KiCad のプラグイン Fabrication Toolkit（bennymeg/JLC-Plugin-for-KiCad）で行う。
HHKB で本番の板に**実際に通したら**、自前の出力で直したつもりの誤りがそのまま出た:
  1. BOM の「LCSC Part #」が全行空（番号がリポジトリにしか無かった）
  2. CPL がホットスワップソケットを top と書く（プラグインは置いた面で決める。
     ソケットは F.Cu に置いてパッドが B.Cu）
  3. 利用者が挿す XIAO が BOM と CPL に載る
プラグインが読むのはフットプリントのフィールド `LCSC` と `FT Layer Override`、
属性 FP_EXCLUDE_FROM_BOM / POS_FILES。ここはそれを書くだけ（冪等）。

参照名 → 種類は spec.FAB_KINDS（正規表現 → 種類）。種類 → LCSC は spec.PARTS
（無ければ foundry.parts.PARTS）。**どれにも当たらない部品は一覧に出す**——
検査対象に入っていない部品は、検査していないのと同じ。
"""

import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from foundry import parts                                      # noqa: E402
from foundry.project import load                               # noqa: E402

LCSC_FIELD = "LCSC"
LAYER_FIELD = "FT Layer Override"
EXCLUDE = pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
# キーまわり（pcb.py が置くもの）。**fullmatch で絞る**（接頭辞だと D_PWR を巻き込む）
KEY_KINDS = {r"SW\d+": "keyswitch", r"D\d+": "diode"}
# 実装しない機械部品（スタビの穴・取付穴）
NOT_PARTS = (r"ST\d+", r"H\d+")


def solder_side(fp):
    """はんだ付けする面。**置いた面ではなくパッドの銅箔で決める**（IsFlipped は置いた面）。"""
    smd = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    if not smd:
        return "bottom" if fp.IsFlipped() else "top"
    return "bottom" if all(p.IsOnLayer(pcbnew.B_Cu) for p in smd) else "top"


def _set_hidden(fp, name, value):
    fp.SetField(name, value)
    f = fp.GetField(name)
    f.SetVisible(False)
    f.SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)


def stamp(board, spec):
    kinds = {**KEY_KINDS, **getattr(spec, "FAB_KINDS", {})}
    table = getattr(spec, "PARTS", parts.PARTS)
    not_assembled = getattr(spec, "NOT_ASSEMBLED", parts.NOT_ASSEMBLED)
    n = dict(lcsc=0, layer=0, excluded=0)
    unknown = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        kind = next((k for pat, k in kinds.items() if re.fullmatch(pat, ref)), None)
        if kind is None:
            if not any(re.fullmatch(p, ref) for p in NOT_PARTS):
                unknown.append(ref)
            continue
        if kind in not_assembled:
            fp.SetAttributes(fp.GetAttributes() | EXCLUDE)
            n["excluded"] += 1
            continue
        if not table[kind]["lcsc"]:
            raise ValueError(f"{ref}（{kind}）の LCSC 番号が空。PARTS に書く")
        _set_hidden(fp, LCSC_FIELD, table[kind]["lcsc"])
        n["lcsc"] += 1
        side = solder_side(fp)
        if side != ("bottom" if fp.IsFlipped() else "top"):
            _set_hidden(fp, LAYER_FIELD, side)
            n["layer"] += 1
        elif fp.HasField(LAYER_FIELD):
            fp.RemoveField(LAYER_FIELD)
    return n, unknown


def main(argv):
    p = load(argv[0])
    boards = [Path(a) for a in argv[1:]] or sorted((p.root / "pcb").glob("*.kicad_pcb"))
    bad = 0
    for path in boards:
        board = pcbnew.LoadBoard(str(path))
        n, unknown = stamp(board, p.spec)
        board.Save(str(path))
        print(f"{'NG' if unknown else 'OK'} {path.name}: LCSC {n['lcsc']} / 面の上書き "
              f"{n['layer']} / BOM・CPL から除外 {n['excluded']}")
        if unknown:
            bad = 1
            print(f"   種類の決まっていない部品（spec.FAB_KINDS に書く）: {unknown}")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
