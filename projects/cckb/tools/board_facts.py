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
  copper_in   引数の矩形（CAD）ごとに、層ごとの銅の面積 mm²（塗ったベタ・線・ビア・パッド）。
              引数が "c:x,y,r" なら円（内に接する 128 角形）
  islands     GND ベタの島ごとに 層・面積・外接矩形・中にある GND のビアの数
  gnd_fill    GND ベタの塗った形（層ごとに島の外形と穴の点列）。検査が「銅の上の道のりで最寄りの GND の
              ビアまで」を測る（2026-09-26 の 2 回目の V2 監査 D-1・D-2）
  silk_to_mask シルクの文字（名札・値・板の文字）ごとに、同じ面のパッドのマスクの開口までの最短（1.0 で打ち切り）
              （同 C-3: R_LO の名札が 0.081）
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


def _drill_wh(p):
    """穴の X 幅・Y 幅（板の上で。90° 回っていれば入れ替える。軸に平行でない長円は落とす）。"""
    ds = p.GetDrillSize()
    w, h = round(MM(ds.x), 4), round(MM(ds.y), 4)
    deg = round(p.GetOrientation().AsDegrees()) % 180
    if p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG and deg not in (0, 90):
        raise SystemExit(f"{p.GetParentFootprint().GetReference()} の長円の穴が {deg}° 回っている")
    return [h, w] if deg == 90 else [w, h]


def rect_poly(r):
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    if r[0] == "c":            # 円: 内に接する 128 角形（円の中だけを数える。弦と弧の差は 0.0006 以下）
        _, cx, cy, rad = r
        import math
        pts = [(cx + rad * math.cos(2 * math.pi * i / 128),
                cy + rad * math.sin(2 * math.pi * i / 128)) for i in range(128)]
    else:
        x0, y0, x1, y1 = r
        pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for x, y in pts:
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


def _pts(chain):
    return [xy(chain.CPoint(k)) for k in range(chain.PointCount())]


def gnd_fill(board):
    """{層: [{outline: 点列, holes: [点列]}]}（CAD）。GND のベタの塗った形そのもの。"""
    out = {}
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for n, lay in LAYERS.items():
            if z.IsOnLayer(lay):
                ps = z.GetFilledPolysList(lay)
                out.setdefault(n, []).extend(
                    dict(outline=_pts(ps.Outline(i)), holes=[_pts(ps.Hole(i, h)) for h in range(ps.HoleCount(i))])
                    for i in range(ps.OutlineCount()))
    return out


SILK_MASK = {pcbnew.F_SilkS: pcbnew.F_Mask, pcbnew.B_SilkS: pcbnew.B_Mask}


def silk_to_mask(board, reach=1.0):
    """シルクの文字ごとに、同じ面のパッドのマスクの開口（パッドの形 ＋ そのパッドのマスクの広げ）までの最短 mm。
    reach より遠ければ reach。[{owner, text, layer, dist, near}]。"""
    err = pcbnew.FromMM(0.001)
    openings = {m: [] for m in SILK_MASK.values()}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for m in openings:
                if p.IsOnLayer(m):
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, m, p.GetSolderMaskExpansion(m), err, pcbnew.ERROR_OUTSIDE)
                    openings[m].append((p.GetBoundingBox(), ps, f"{fp.GetReference()}.{p.GetNumber()}"))
    texts = [(fp.GetReference(), t) for fp in board.GetFootprints() for t in (fp.Reference(), fp.Value())
             if t.IsVisible() and t.GetLayer() in SILK_MASK]
    texts += [("", d) for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetLayer() in SILK_MASK]
    out = []
    for owner, t in texts:
        sh = t.GetEffectiveTextShape()
        bb = t.GetBoundingBox()
        bb.Inflate(pcbnew.FromMM(reach))
        best, near = reach, ""
        for pbb, ps, name in openings[SILK_MASK[t.GetLayer()]]:
            if not bb.Intersects(pbb) or not ps.Collide(sh, pcbnew.FromMM(best)):
                continue
            lo, hi = 0.0, best                     # 当たる最小の余裕を 2 分で（0.001 まで）
            while hi - lo > 0.0005:
                mid = (lo + hi) / 2
                if ps.Collide(sh, pcbnew.FromMM(mid)):
                    hi = mid
                else:
                    lo = mid
            best, near = hi, name
        out.append(dict(owner=owner, text=t.GetText(), layer=board.GetLayerName(t.GetLayer()),
                        dist=round(best, 3), near=near))
    return out


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
                thermal=p.GetLocalZoneConnection() == pcbnew.ZONE_CONNECTION_THERMAL,
                round=p.GetShape(pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
                == pcbnew.PAD_SHAPE_CIRCLE,
                npth=p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH,
                paste=p.IsOnLayer(pcbnew.F_Paste) or p.IsOnLayer(pcbnew.B_Paste),
                pos=xy(p.GetPosition()), box=box(p.GetBoundingBox()),
                drill=round(MM(p.GetDrillSize().x), 4),
                # 穴の形（丸か長円か）と板の上の X 幅・Y 幅（回転を解いた後）。JLC の「長円の長さ ≧ 幅 × 2」を見る
                slot=p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG,
                drill_wh=_drill_wh(p)))
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
    out["islands"] = []
    gvias = [t.GetPosition() for t in board.GetTracks()
             if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for n, lay in LAYERS.items():
            if not z.IsOnLayer(lay):
                continue
            polys = z.GetFilledPolysList(lay)
            for i in range(polys.OutlineCount()):
                ol = polys.Outline(i)
                holes = [polys.Hole(i, h) for h in range(polys.HoleCount(i))]
                nv = sum(1 for v in gvias if ol.PointInside(v)
                         and not any(h.PointInside(v) for h in holes))
                out["islands"].append(dict(layer=n, area=round(abs(ol.Area()) / 1e12, 3),
                                           box=box(ol.BBox()), vias=nv))
    out["gnd_fill"] = gnd_fill(board)
    out["silk_to_mask"] = silk_to_mask(board)
    out["origin"] = list(ORIGIN)                     # CAD → KiCad（x + ox, oy − y）
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
    rects = [["c"] + [float(v) for v in a[2:].split(",")] if a.startswith("c:")
             else [float(v) for v in a.split(",")] for a in sys.argv[3:]]
    data = facts(sys.argv[1], rects)
    Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False))
    print(f"OK 部品 {len(data['footprints'])} / パッド {len(data['pads'])} / 線 {len(data['tracks'])}"
          f" / ビア {len(data['vias'])} / 未接続 {data['unconnected']}")
