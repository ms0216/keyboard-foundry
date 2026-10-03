"""cckb-click の板から、CCKB の board_facts.py が書かない事実を JSON に書き出す。**KiCad の Python。**

    "$KICAD_PYTHON" projects/cckb-click/tools/click_facts.py <板.kicad_pcb> <出力.json> <電池の中心 x,y,半径（CAD）>

**KiCad が読んだ板そのもの**を測る（生成器の意図は書かない）。1 回目の監査（2026-10-04）で、検査が見ていなかった所:
  silk_graphics  シルクの**図形**（線・円・矩形。文字は board_facts.silk_to_mask が見る）ごとに、線の太さと、同じ面のパッドの
                 マスクの開口までの最短 mm（1.0 で打ち切り）。監査 C 軽微 1: 試験用のランドの輪が開口から 0.10・太さ 0.12
  cell           電池の缶（＋）の縁から、表の銅（電池クリップ自身のパッドを除く。ベタ・線・ビア・ほかのパッド）までの最短 mm。
                 seated = 止めに当てた位置の円、path = そこから手前の基板の縁まで抜き差しする道（3.0 で打ち切り）。監査 E 重要 1
座標は CAD（キー領域の中心が原点・Y 上向き・mm）。
"""

import json
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from foundry.pcb import ORIGIN  # noqa: E402

SILK_MASK = {pcbnew.F_SilkS: pcbnew.F_Mask, pcbnew.B_SilkS: pcbnew.B_Mask}
ERR = pcbnew.FromMM(0.001)


def nearest(a, b, reach):
    """多角形 a と b の距離 mm（reach で打ち切り。重なっていれば 0）。当たる最小の余裕を 2 分で。"""
    if not a.Collide(b, pcbnew.FromMM(reach)):
        return reach
    lo, hi = 0.0, reach
    while hi - lo > 0.0005:
        mid = (lo + hi) / 2
        if a.Collide(b, pcbnew.FromMM(mid)):
            hi = mid
        else:
            lo = mid
    return hi


def silk_graphics(board, reach=1.0):
    openings = {m: [] for m in SILK_MASK.values()}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for m in openings:
                if p.IsOnLayer(m):
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, m, p.GetSolderMaskExpansion(m), ERR, pcbnew.ERROR_OUTSIDE)
                    openings[m].append((p.GetBoundingBox(), ps, f"{fp.GetReference()}.{p.GetNumber()}"))
    items = [(fp.GetReference(), g) for fp in board.GetFootprints() for g in fp.GraphicalItems()
             if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in SILK_MASK]
    items += [("", g) for g in board.GetDrawings() if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in SILK_MASK]
    out = []
    for owner, g in items:
        poly = pcbnew.SHAPE_POLY_SET()
        g.TransformShapeToPolygon(poly, g.GetLayer(), 0, ERR, pcbnew.ERROR_OUTSIDE)
        bb = g.GetBoundingBox()
        bb.Inflate(pcbnew.FromMM(reach))
        best, near = reach, ""
        for pbb, ps, name in openings[SILK_MASK[g.GetLayer()]]:
            if not bb.Intersects(pbb):
                continue
            d = nearest(ps, poly, best)
            if d < best:
                best, near = d, name
        out.append(dict(owner=owner, shape=g.GetShapeStr(), width=round(pcbnew.ToMM(g.GetWidth()), 4),
                        layer=board.GetLayerName(g.GetLayer()), dist=round(best, 3), near=near))
    return out


def front_copper_without(board, skip_ref):
    ps = pcbnew.SHAPE_POLY_SET()
    lay = pcbnew.F_Cu
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(lay):
            ps.Append(z.GetFilledPolysList(lay))
    for t in board.GetTracks():
        if t.IsOnLayer(lay):
            t.TransformShapeToPolygon(ps, lay, 0, ERR, pcbnew.ERROR_OUTSIDE)
    for fp in board.GetFootprints():
        if fp.GetReference() == skip_ref:
            continue
        for p in fp.Pads():
            if p.IsOnLayer(lay) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                p.TransformShapeToPolygon(ps, lay, 0, ERR, pcbnew.ERROR_OUTSIDE)
    ps.Simplify()
    return ps


def poly(points):
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in points:
        ps.Append(pcbnew.FromMM(ORIGIN[0] + x), pcbnew.FromMM(ORIGIN[1] - y))
    return ps


def cell(board, cx, cy, r, reach=3.0):
    cu = front_copper_without(board, "BT1")
    edge_y = min(ORIGIN[1] - pcbnew.ToMM(board.GetBoardEdgesBoundingBox().GetBottom()), cy)
    circle = [(cx + r * math.cos(2 * math.pi * i / 256), cy + r * math.sin(2 * math.pi * i / 256)) for i in range(256)]
    path = [(cx - r, edge_y), (cx + r, edge_y), (cx + r, cy), (cx - r, cy)]
    return dict(center=[cx, cy], r=r, seated=round(nearest(cu, poly(circle), reach), 3),
                path=round(nearest(cu, poly(path), reach), 3))


if __name__ == "__main__":
    board = pcbnew.LoadBoard(sys.argv[1])
    cx, cy, r = (float(v) for v in sys.argv[3].split(","))
    data = dict(silk_graphics=silk_graphics(board), cell=cell(board, cx, cy, r))
    Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False))
    print(f"OK シルクの図形 {len(data['silk_graphics'])} / 電池の縁から表の銅まで {data['cell']}")
