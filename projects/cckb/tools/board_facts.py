"""配線して塗った板から、検査が突き合わせる事実を JSON に書き出す。**KiCad の Python。**

    "$KICAD_PYTHON" projects/cckb/tools/board_facts.py <板.kicad_pcb> <出力.json> [x0,y0,x1,y1 ...]

**KiCad が読んだ板そのもの**（pcbnew が回転・裏返し・塗りまで解いた物）を書く。宣言
（circuit.py）や生成器の意図は書かない——検査はそれを相手に突き合わせる（tests/test_cckb_pcb.py）。

書くもの:
  footprints  参照名・面・属性（BOM/CPL から外すか）・フィールド（LCSC・FT Layer Override）
  pads        参照名・番号・ネット・層（IsOnLayer で F/B）・位置・外接矩形・穴
  tracks/vias ネット・層・端点・幅
  zones       名前・ネット・層・ルール領域か・塗った面積（層ごと）・外形
  edge        Edge.Cuts の線分（外形とスタビの逃げ穴）
  unconnected KiCad の連結で数えた未接続
  copper_in   引数の矩形（CAD）ごとに、層ごとの銅の面積 mm²（塗ったベタ・線・ビア・パッド）
座標は CAD（キー領域の中心が原点・Y 上向き・mm）。
"""

import json
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from foundry.pcb import ORIGIN  # noqa: E402

MM = pcbnew.ToMM
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def xy(v):
    return [round(MM(v.x) - ORIGIN[0], 4), round(ORIGIN[1] - MM(v.y), 4)]


def box(b):
    return [round(MM(b.GetLeft()) - ORIGIN[0], 4), round(ORIGIN[1] - MM(b.GetBottom()), 4),
            round(MM(b.GetRight()) - ORIGIN[0], 4), round(ORIGIN[1] - MM(b.GetTop()), 4)]


def rect_poly(r):
    x0, y0, x1, y1 = r
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        ps.Append(pcbnew.FromMM(ORIGIN[0] + x), pcbnew.FromMM(ORIGIN[1] - y))
    return ps


def copper(board, layer):
    """その層の銅をすべて 1 つの多角形に（塗ったベタ・線・ビア・パッド）。"""
    ps = pcbnew.SHAPE_POLY_SET()
    err = pcbnew.FromMM(0.005)
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(layer):
            ps.Append(z.GetFilledPolysList(layer))
    for t in board.GetTracks():
        if t.IsOnLayer(layer):
            t.TransformShapeToPolygon(ps, layer, 0, err, pcbnew.ERROR_INSIDE)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(layer) and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                p.TransformShapeToPolygon(ps, layer, 0, err, pcbnew.ERROR_INSIDE)
    ps.Simplify()
    return ps


def facts(path, rects):
    board = pcbnew.LoadBoard(str(path))
    board.BuildConnectivity()
    out = {"footprints": [], "pads": [], "tracks": [], "vias": [], "zones": [], "edge": []}
    for fp in board.GetFootprints():
        fields = {f.GetName(): f.GetText() for f in fp.GetFields()}
        out["footprints"].append(dict(
            ref=fp.GetReference(), value=fp.GetValue(), pos=xy(fp.GetPosition()),
            rot=round(fp.GetOrientationDegrees(), 3), flipped=fp.IsFlipped(),
            fpid=fp.GetFPID().GetLibItemName().wx_str(),
            exclude_bom=bool(fp.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM),
            exclude_pos=bool(fp.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_POS_FILES),
            fields=fields))
        for p in fp.Pads():
            out["pads"].append(dict(
                ref=fp.GetReference(), num=p.GetNumber(), net=p.GetNetname(),
                front=p.IsOnLayer(pcbnew.F_Cu), back=p.IsOnLayer(pcbnew.B_Cu),
                smd=p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD,
                npth=p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
                pos=xy(p.GetPosition()), box=box(p.GetBoundingBox()),
                drill=round(MM(p.GetDrillSize().x), 4)))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            out["vias"].append(dict(net=t.GetNetname(), pos=xy(t.GetPosition()),
                                    d=round(MM(t.GetWidth(pcbnew.F_Cu)), 4),
                                    drill=round(MM(t.GetDrillValue()), 4)))
        else:
            out["tracks"].append(dict(net=t.GetNetname(), layer=t.GetLayerName(),
                                      a=xy(t.GetStart()), b=xy(t.GetEnd()),
                                      w=round(MM(t.GetWidth()), 4)))
    for z in board.Zones():
        d = dict(name=z.GetZoneName(), net=z.GetNetname(), rule=z.GetIsRuleArea(),
                 layers=[n for n, lay in LAYERS.items() if z.IsOnLayer(lay)],
                 outline=box(z.Outline().BBox()), area={}, outlines={})
        if not z.GetIsRuleArea():
            for n, lay in LAYERS.items():
                if z.IsOnLayer(lay):
                    polys = z.GetFilledPolysList(lay)
                    d["area"][n] = round(polys.Area() / 1e12, 3)
                    d["outlines"][n] = polys.OutlineCount()
        else:
            d.update(no_tracks=z.GetDoNotAllowTracks(), no_vias=z.GetDoNotAllowVias(),
                     no_fill=z.GetDoNotAllowZoneFills())
        out["zones"].append(d)
    for s in board.GetDrawings():
        if s.GetLayer() == pcbnew.Edge_Cuts:
            out["edge"].append(dict(shape=s.GetShapeStr(), a=xy(s.GetStart()), b=xy(s.GetEnd())))
    out["unconnected"] = board.GetConnectivity().GetUnconnectedCount(False)
    out["copper_in"] = []
    cu = {n: copper(board, lay) for n, lay in LAYERS.items()}
    for r in rects:
        area = {}
        for n in LAYERS:
            ps = pcbnew.SHAPE_POLY_SET(cu[n])
            ps.BooleanIntersection(rect_poly(r))
            area[n] = round(ps.Area() / 1e12, 4)
        out["copper_in"].append(dict(rect=r, area=area))
    return out


if __name__ == "__main__":
    rects = [[float(v) for v in a.split(",")] for a in sys.argv[3:]]
    data = facts(sys.argv[1], rects)
    Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False))
    print(f"OK 部品 {len(data['footprints'])} / パッド {len(data['pads'])} / 線 {len(data['tracks'])}"
          f" / ビア {len(data['vias'])} / 未接続 {data['unconnected']}")
