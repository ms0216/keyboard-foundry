"""基板の実物の形（パッド・穴・コートヤード）を JSON に書き出す。**KiCad の Python で動かす。**

    "$KICAD_PYTHON" projects/cckb/tools/board_geometry.py <基板.kicad_pcb> <出力.json>

なぜ要るか: 取付ネジ・支柱・角の部品が「基板の部品に当たらないか」を、
**自分の宣言ではなく生成した基板そのもの**と突き合わせるため
（tests/test_cckb_interface.py・projects/cckb/tools/find_mounts.py が読む）。
pcbnew はパッドの位置を回転・裏返しまで解いた世界座標で返すので、
S 式を自分で解くより取り違えが無い（board_dump.py は位置の回転を解かない）。

座標は CAD（キー領域の中心が原点・Y 上向き・mm）。ORIGIN は foundry/pcb.py と同じ。
**寸法は持たない**（読むだけ）。
"""

import json
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from foundry.pcb import ORIGIN  # noqa: E402

MM = pcbnew.ToMM


def _box(b):
    """KiCad の BOX2I → CAD の (x0, y0, x1, y1)。Y を反転する。"""
    x0, x1 = MM(b.GetLeft()) - ORIGIN[0], MM(b.GetRight()) - ORIGIN[0]
    y0, y1 = ORIGIN[1] - MM(b.GetBottom()), ORIGIN[1] - MM(b.GetTop())
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def dump(path):
    return dump_board(pcbnew.LoadBoard(str(path)))


def dump_board(board):
    out = {"footprints": [], "pads": [], "edge": _box(board.GetBoardEdgesBoundingBox())}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        crt = {}
        for name, layer in (("front", pcbnew.F_CrtYd), ("back", pcbnew.B_CrtYd)):
            poly = fp.GetCourtyard(layer)
            if poly.OutlineCount():
                crt[name] = _box(poly.BBox())
        q = fp.GetPosition()
        out["footprints"].append(dict(
            ref=ref, fp=fp.GetFPID().GetLibItemName().wx_str(),
            x=round(MM(q.x) - ORIGIN[0], 4), y=round(ORIGIN[1] - MM(q.y), 4),
            deg=round(fp.GetOrientationDegrees(), 4), back=fp.IsFlipped(), courtyard=crt))
        for pad in fp.Pads():
            p = pad.GetPosition()
            attr = pad.GetAttribute()
            out["pads"].append(dict(
                ref=ref, num=pad.GetNumber(), net=pad.GetNetname(),
                x=round(MM(p.x) - ORIGIN[0], 4), y=round(ORIGIN[1] - MM(p.y), 4),
                box=_box(pad.GetBoundingBox()),
                front=pad.IsOnLayer(pcbnew.F_Cu), back=pad.IsOnLayer(pcbnew.B_Cu),
                npth=attr == pcbnew.PAD_ATTRIB_NPTH,
                round=pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE,
                drill=round(MM(pad.GetDrillSize().x), 4)))
    return out


def outline(board):
    """Edge.Cuts を KiCad が組んだ多角形（外形 ＋ 内側の穴 = スタビの逃げ穴）で返す。

    {"outer": [[x, y], ...], "holes": [[[x, y], ...], ...]}（CAD 座標。円弧は KiCad が折れ線にした物）。
    組み立てモデル（projects/cckb/assembly.py）が**発注する板の形**として読む。
    """
    ps = pcbnew.SHAPE_POLY_SET()
    assert board.GetBoardPolygonOutlines(ps, False), "Edge.Cuts が閉じていない"
    assert ps.OutlineCount() == 1, ps.OutlineCount()

    def pts(chain):
        return [[round(MM(chain.CPoint(k).x) - ORIGIN[0], 4), round(ORIGIN[1] - MM(chain.CPoint(k).y), 4)]
                for k in range(chain.PointCount())]

    return {"outer": pts(ps.Outline(0)),
            "holes": [pts(ps.Hole(0, k)) for k in range(ps.HoleCount(0))]}


if __name__ == "__main__":
    board = pcbnew.LoadBoard(sys.argv[1])
    data = dump_board(board)
    data["outline"] = outline(board)
    Path(sys.argv[2]).write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"OK 部品 {len(data['footprints'])} / パッド {len(data['pads'])} → {sys.argv[2]}")
