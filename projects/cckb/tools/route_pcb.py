"""CCKB の基板を配線して、発注に使う板 projects/cckb/pcb/cckb_main.kicad_pcb を作る。**KiCad の Python。**

    tools/kb cckb pcb                                        # 未配線の板（置く・ネットを張る）
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py         # ここ。配線 → ベタ → GND ビア
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py --reroute CS[,NET...]
        # いまの配線済みの板（pcb/cckb_main.kicad_pcb）から、名指しした網と GND 以外の線・ビアを
        # **そのまま持ってきて**、名指しした網だけを Freerouting に引かせる（発注前の小さな直しで、
        # 監査の済んだ配線を動かさない。2 回目の監査 S1）。持ってきた線が禁止域に掛かれば落とす
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py --reroute VBAT_IN,VBAT_SW --clear X0,Y0,X1,Y1
        # 部品を動かしたとき: 名指しした網の前の線・ビアのうち、**端が矩形（CAD）の中にあるもの**を
        # 捨ててから引き直す（前の部品の位置へ行く線を残さない）。引いた後、名指しした網の行き止まりの
        # 線（端が何にも繋がっていない）を消す。2026-09-24 に電源スイッチとホルダを動かしたとき
    .venv/bin/python3 -m foundry.drc projects/cckb/pcb/cckb_main.kicad_pcb

順序（docs/knowledge/pcb.md）:
  1. 行列を決まった形で引く（matrix_routes.plan。板の上のパッドから）
  2. GND の SMD パッドに同じ層のスタブ → ビア（ベタが偶然被っている接続に頼らない）
  3. 残りを Freerouting 2.3.0（行列の線は protect・行列のネットは駆動側と最寄りのパッドの 2 ピンに
     絞る。GND・SW*_D はネットごと外して線は protect）
  4. SES の取り込みは既存の配線を作り直す → **行列と GND のスタブが残っているかを数えて確かめる**
     （足りなければ置き直し、置き直せなければ落とす）。ルール領域の層も戻す（SES 往復で消える）
  5. 両面の GND ベタ → フェンス（長い配線の脇）→ リング（アンテナの禁止域の縁）→ 格子 →
     離島（面積で見る。つなぎ直し、残りは消して面積を記録）→ 塗り直し
  6. 保存と記録（route.json: 未配線の板の指紋・Freerouting・数）

**板の寸法・規則は持たない**（spec.py・pcb_rules.py から読む）。持つのは規則に足す余裕だけ
（GND_CLEAR・SAME_NET_PAD_CLEAR・DETOUR_CLEAR など。どれも名前とコメントで余裕と書いてある）。**配線を加工する判定を書かない**——線は置くか、
置いた線が残っているかを数えるだけ（HHKB の教訓）。
"""

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[1]
for p in (str(ROOT), str(PROJ), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import board_geometry                                   # noqa: E402
import interface                                        # noqa: E402
import matrix_routes                                    # noqa: E402
from foundry import boardhash, paths                    # noqa: E402
from foundry.pcb import ORIGIN, sync_project_rules      # noqa: E402
from foundry.pcb_rules import JLC, TRACK_W, VIA_D, VIA_DRILL   # noqa: E402
from foundry.project import load                        # noqa: E402

SRC = PROJ / "pcb" / "unrouted" / "cckb_main.kicad_pcb"
OUT = PROJ / "pcb" / "cckb_main.kicad_pcb"
JAR = paths.FREEROUTING_JAR
# 使う Freerouting の版。**jar の名前ではなく中身で確かめる**（MANIFEST の Build-Revision）。
# v2.3.0 のタグ = この commit（GitHub API repos/freerouting/freerouting/git/ref/tags/v2.3.0、2026-09-24 に確認）
FREEROUTING_REVISION = "2d4de019aa89e9fa3dc1dc44e09bf509760cafc1"
PASSES = 100
# Freerouting は丸めで規則を下回る（HHKB: 20→30）。**同じ入力なら同じ結果**（HHKB で 3 回確かめた）
# だが、板を少し変えると未配線が 0 から 2 に揺れた（2026-09-24・名札を動かしただけ）。
# そこで余裕を決まった順に試し、Freerouting のログで未配線 0 の最初を採る（どれを採ったかは記録）
# V2 の板（2026-09-25）は穴が増えて左の角が混み、4 つでは足りないことがあった（未配線 1〜3 が余裕ごとに揺れる）。
# 同じ順の後ろに 20・45・50・15 を足した（前の 4 つで決まる板の結果は変わらない）
DSN_CLEARANCE_MARGINS_UM = (30, 35, 25, 40, 20, 45, 50, 15)
PREWIRED = re.compile(r"GND|SW\d+_D|ROW\d+")   # 自分で引き切ったネット（DSN から外す）
FIXED = re.compile(r"COL\d+")    # 自分で引いたが、595 までの最後の 1 本は Freerouting が繋ぐ

MM = pcbnew.FromMM
GND_CLEAR = 0.25                    # ベタとほかのネットの間
VIA_R = VIA_D / 2
# 縫いのビアと**同じネットの**パッドの間（銅の縁どうし）。パッドの中・縁に掛けない（はんだを
# 吸わない）ための逃げで、電気の間隔ではない。監査 C の提案「ビアの輪 ＋ 0.1 以上」
SAME_NET_PAD_CLEAR = 0.1


def kpt(x, y):
    return pcbnew.VECTOR2I_MM(ORIGIN[0] + x, ORIGIN[1] - y)


def cad(v):
    return (pcbnew.ToMM(v.x) - ORIGIN[0], ORIGIN[1] - pcbnew.ToMM(v.y))


LAYER = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


# ---------------------------------------------------------------------------
# 1. 行列
# ---------------------------------------------------------------------------

def matrix_segments(board):
    """行列（plan）と XIAO から行のバスまで（escape）。([線], [ビア])"""
    geo = board_geometry.dump_board(board)
    proj = load(PROJ)
    m = matrix_routes.plan(proj, geo["pads"])
    e, vias = matrix_routes.escape(proj, geo["pads"], others=m)
    return m + e, vias


def oe_ties(board):
    """595 の OE（13 番・GND）を、同じ部品の GND（8 番）へ**本体の下で**つなぐ線（裏・幅 0.3）。
    [(net, layer, a, b)]。形はパッドの位置から: 13 番 → 2 つのパッドの x の真ん中 → 8 番の高さ → 8 番。

    なぜ: OE のファンアウトのビアは 1 本で、V2 の板では Freerouting の線（3V3・SPI）にビアの周りの
    小さなベタごと囲まれ、OE が本土の GND から離れた（2026-09-25・KiCad の未配線 1）。GND のパッドどうしを
    部品の中で直につなげば、囲まれても 8 番（本土につながる）から GND が来る。
    """
    out = []
    for ref in ("U1", "U2"):
        fp = board.FindFootprintByReference(ref)
        p13, p8 = fp.FindPadByNumber("13"), fp.FindPadByNumber("8")
        if p13.GetNetname() != "GND" or p8.GetNetname() != "GND":
            raise SystemExit(f"{ref}: 13 番 {p13.GetNetname()}・8 番 {p8.GetNetname()}（どちらも GND のはず）")
        a, b = cad(p13.GetPosition()), cad(p8.GetPosition())
        xm = round((a[0] + b[0]) / 2, 4)
        pts = [a, (xm, a[1]), (xm, b[1]), b]
        out += [("GND", "B.Cu", p, q) for p, q in zip(pts, pts[1:])]
    return out


def power_segments(board, others):
    """電源の長い線（matrix_routes.power_runs・spec.POWER_RUNS）。[(net, layer, a, b)]"""
    geo = board_geometry.dump_board(board)
    return matrix_routes.power_runs(load(PROJ), geo["pads"], others=others)


def power_ends(proj):
    """電源の決まった線の網 → DSN に残すピン名の集合から外すピン（線の to の端。from と線で繋がっている）。"""
    return {net: f"{how['to'][0]}-{how['to'][1]}" for net, how in getattr(proj.spec, "POWER_RUNS", {}).items()}


def snap_rounded_twins(board, segs, tol_nm=5):
    """SES の取り込みで 1nm ずれて戻った計画の線（計画の線と端が tol_nm 以内・ぴったりではない）を、計画の
    座標に戻す。戻した数。**計画の線を置き直す前に**呼ぶ（置き直すと 1nm ずれた二重の線になり、端が繋がらない
    行き止まりに見えた。2026-09-25 V2 の VBAT_SW で prune_dangling の検査が落ちた）。消さずに動かすのは、
    この pcbnew で線を Remove した後に GetTracks が壊れることがあったから（同じ日に実測）。"""
    want = [(s[0], LAYER[s[1]], _nm(s[2]), _nm(s[3])) for s in segs]
    exact = {(n, lay) + tuple(sorted([a, b])) for n, lay, a, b in want}
    n_snap = 0
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        s, e = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
        if (t.GetNetname(), t.GetLayer()) + tuple(sorted([s, e])) in exact:
            continue
        for n, lay, a, b in want:
            if n != t.GetNetname() or lay != t.GetLayer():
                continue
            hit = next(((p, q) for p, q in ((a, b), (b, a))
                        if max(abs(s[0] - p[0]), abs(s[1] - p[1]), abs(e[0] - q[0]), abs(e[1] - q[1])) <= tol_nm),
                       None)
            if hit:
                t.SetStart(pcbnew.VECTOR2I(*hit[0]))
                t.SetEnd(pcbnew.VECTOR2I(*hit[1]))
                n_snap += 1
                break
    return n_snap


def lay_vias(board, vias):
    have = {(v.GetPosition().x, v.GetPosition().y) for v in board.GetTracks()
            if v.GetClass() == "PCB_VIA"}
    n = 0
    for net, p in vias:
        q = kpt(*p)
        if (q.x, q.y) in have:
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(q)
        v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL))
        v.SetNet(board.FindNet(net))
        board.Add(v)
        n += 1
    return n


def lay_segments(board, segs, width=TRACK_W):
    n = 0
    for net, layer, a, b in segs:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(kpt(*a))
        t.SetEnd(kpt(*b))
        t.SetWidth(MM(width))
        t.SetLayer(LAYER[layer])
        ni = board.FindNet(net)
        if ni is None:
            raise SystemExit(f"板にネット {net} が無い")
        t.SetNet(ni)
        board.Add(t)
        n += 1
    return n


def _nm(p):
    v = kpt(*p)
    return (v.x, v.y)


def _key_nm(net, layer, a, b):
    """比べるのは KiCad の整数座標（nm）。mm の小数を丸めて比べると丸めの向きで食い違う。"""
    return (net, layer) + tuple(sorted([a, b]))


def tracks_present(board, segs):
    """計画の線が板に**そのまま**あるか。無いものを返す。"""
    have = set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            s, e = t.GetStart(), t.GetEnd()
            have.add(_key_nm(t.GetNetname(), t.GetLayerName(), (s.x, s.y), (e.x, e.y)))
    return [s for s in segs if _key_nm(s[0], s[1], _nm(s[2]), _nm(s[3])) not in have]


# ---------------------------------------------------------------------------
# 置けるかの判定（ビア・スタブ）。**板の実物の形**（pcbnew の SHAPE）で当てる
# ---------------------------------------------------------------------------

class Space:
    def __init__(self, board):
        self.board = board
        self.refresh()
        self.edges = [s for s in board.GetDrawings()
                      if s.GetLayer() == pcbnew.Edge_Cuts]
        # 外形（スタビの逃げ穴を穴として含む）。**縁の線に近いかだけでは足りない**——逃げ穴の
        # 真ん中（縁から 0.35 より遠い）に置いたビアが通っていた（2026-09-24 の 1 回目）
        self.outline = pcbnew.SHAPE_POLY_SET()
        if not board.GetBoardPolygonOutlines(self.outline, False):
            raise SystemExit("外形の多角形が作れない")
        self.rules = [z for z in board.Zones() if z.GetIsRuleArea()]

    def refresh(self):
        b = self.board
        self.items = []                        # (bbox, 層, ネット, 形の取り出し)
        for fp in b.GetFootprints():
            for p in fp.Pads():
                self.items.append((p.GetBoundingBox(), p))
        for t in b.GetTracks():
            self.items.append((t.GetBoundingBox(), t))

    def free(self, pos, net, layers=(pcbnew.F_Cu, pcbnew.B_Cu), r=VIA_R, drill=VIA_DRILL / 2,
             clear=0.25, stub_from=None, stub_layer=None):
        """pos（KiCad の点）にビア（半径 r）を置けるか。stub_from があれば、そこから
        stub_layer の上のスタブ（幅 0.3）も当てる。"""
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(pos)
        via.SetWidth(MM(2 * r))
        via.SetDrill(MM(2 * drill))
        shapes = [(lay, via.GetEffectiveShape(lay)) for lay in layers]
        if stub_from is not None:
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(stub_from)
            t.SetEnd(pos)
            t.SetWidth(MM(0.3))
            t.SetLayer(stub_layer)
            shapes.append((stub_layer, t.GetEffectiveShape(stub_layer)))
        if not self.outline.Contains(pos):
            return False
        # 絞り込みの窓は**スタブも含めて**（ビアの周りだけ見て、長いスタブが隣のパッドを
        # 横切った。2026-09-24 の 1 回目: R_LO の GND のスタブが同じ部品の VBAT_SENSE を跨いだ）
        reach = MM(r + 1.5)
        lo_x, hi_x, lo_y, hi_y = pos.x - reach, pos.x + reach, pos.y - reach, pos.y + reach
        if stub_from is not None:
            lo_x, hi_x = min(lo_x, stub_from.x - reach), max(hi_x, stub_from.x + reach)
            lo_y, hi_y = min(lo_y, stub_from.y - reach), max(hi_y, stub_from.y + reach)
        for bb, it in self.items:
            if bb.GetLeft() > hi_x or bb.GetRight() < lo_x or \
                    bb.GetTop() > hi_y or bb.GetBottom() < lo_y:
                continue
            same = it.GetNetname() == net and net != ""
            if isinstance(it, pcbnew.PCB_VIA):       # 穴どうし（JLC 0.45）は**ネットに関係なく**
                d = math.hypot(pos.x - it.GetPosition().x, pos.y - it.GetPosition().y)
                if d - MM(drill) - it.GetDrillValue() / 2 < MM(JLC["hole_to_hole"] + 0.05):
                    return False      # 1 回目: 同じ GND のビアを丸ごと飛ばし、穴間 0.38 が 27 件
            if isinstance(it, pcbnew.PAD):
                if it.GetDrillSize().x > 0:          # 穴どうし（JLC 0.45）
                    # 穴は**実物の形**（長円なら線分）で当てる。前は穴の X の径の丸とみなしていて、
                    # V2 の縦長の穴（位置決め 1.6 × 2.0・スタビの爪 4.2 × 4.4）の脇に縫いのビアが落ちた
                    hole = it.GetEffectiveHoleShape()
                    if hole.Collide(pcbnew.SHAPE_CIRCLE(pos, MM(drill)), MM(JLC["hole_to_hole"] + 0.05)):
                        return False
                    if it.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                        if hole.Collide(pcbnew.SHAPE_CIRCLE(pos, MM(r)), MM(0.3)):
                            return False
                        continue
                if same:
                    # **同じネットのパッドもビアの障害物**（ビアの輪 ＋ SAME_NET_PAD_CLEAR）。
                    # 前は飛ばしていて、縫いのビアが C_U1（JLC がリフローで付ける 0805）と
                    # BT1 の GND パッドの**中**に落ちた（監査 C 重要 1・2026-09-24）。パッドの上の
                    # ビアははんだを吸う（JLC PCBA FAQ Part 2 Q17）。スタビ（自分のパッドから
                    # 出る線）は同じネットなので当ててよい——当てるのはビアの形だけ
                    for lay, sh in shapes[:len(layers)]:
                        if it.IsOnLayer(lay) and \
                                it.GetEffectiveShape(lay).Collide(sh, MM(SAME_NET_PAD_CLEAR)):
                            return False
                    continue
            elif same:
                continue
            for lay, sh in shapes:
                if not it.IsOnLayer(lay):
                    continue
                if it.GetEffectiveShape(lay).Collide(sh, MM(clear)):
                    return False
        # 外形・逃げ穴（Edge.Cuts）から
        for e in self.edges:
            if e.GetEffectiveShape().Collide(shapes[0][1], MM(JLC["edge_clearance"] + 0.05)):
                return False
        for z in self.rules:
            for lay, sh in shapes:
                if z.IsOnLayer(lay) and (z.GetDoNotAllowVias() or z.GetDoNotAllowTracks()) and \
                        z.Outline().Collide(sh, MM(0.1)):
                    return False
        return True

    def add_via(self, pos, net, stub_from=None, stub_layer=None):
        b = self.board
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pos)
        v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL))
        v.SetNet(b.FindNet(net))
        b.Add(v)
        self.items.append((v.GetBoundingBox(), v))
        if stub_from is not None:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(stub_from)
            t.SetEnd(pos)
            t.SetWidth(MM(0.3))
            t.SetLayer(stub_layer)
            t.SetNet(b.FindNet(net))
            b.Add(t)
            self.items.append((t.GetBoundingBox(), t))
        return v


# ---------------------------------------------------------------------------
# 2. GND のファンアウト
# ---------------------------------------------------------------------------

def gnd_fanout(board, space):
    """GND の SMD パッドごとに、同じ層のスタブ（0.3）→ ビア。部品の中心から外向きを優先。"""
    placed, failed = [], []
    for fp in board.GetFootprints():
        c = fp.GetPosition()
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            q = p.GetPosition()
            half = max(p.GetBoundingBox().GetWidth(), p.GetBoundingBox().GetHeight()) / 2
            out = math.atan2(q.y - c.y, q.x - c.x) if (q.x, q.y) != (c.x, c.y) else 0.0
            dirs = sorted((math.radians(a) for a in range(0, 360, 15)),
                          key=lambda a: abs(math.remainder(a - out, 2 * math.pi)))
            done = False
            for dist in (0.9, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0):
                for a in dirs:
                    pos = pcbnew.VECTOR2I(int(q.x + math.cos(a) * (half + MM(dist))),
                                          int(q.y + math.sin(a) * (half + MM(dist))))
                    if space.free(pos, "GND", stub_from=q, stub_layer=layer):
                        space.add_via(pos, "GND", stub_from=q, stub_layer=layer)
                        placed.append(f"{fp.GetReference()}.{p.GetNumber()}")
                        done = True
                        break
                if done:
                    break
            if not done:
                failed.append(f"{fp.GetReference()}.{p.GetNumber()}")
    if failed:
        raise SystemExit(f"GND のファンアウトが置けないパッド: {failed}")
    return placed


# ---------------------------------------------------------------------------
# 3. Freerouting
# ---------------------------------------------------------------------------

def _java():
    tried = []
    for cand in (shutil.which("java"),) + paths.JAVA_CANDIDATES:
        if not cand or not Path(cand).exists():
            continue
        tried.append(cand)
        r = subprocess.run([cand, "-version"], capture_output=True, timeout=60)
        if r.returncode == 0:
            return cand
    raise SystemExit(f"動く java が無い（brew install openjdk）。試したもの: {tried}")


def matrix_ends(board):
    """行列のネットごとに、Freerouting に繋がせる 2 つのピン {ネット: (駆動側の参照名, 相手のピン名)}。

    行列は自分で引き切ってある（matrix_routes）。残るのは XIAO・595 から行列までの 1 本だけ
    なので、DSN ではネットのピンを「駆動側（XIAO か 595）」と「そのネットで駆動側に最も近い
    行列のパッド」の 2 つに絞る。行列の線は障害物（protect）として渡す。
    （fix で渡すと Freerouting 2.3.0 は線を接続と見ず、未配線 67・違反 230 から動かなかった。
    2026-09-24 実測）
    """
    out = {}
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if FIXED.fullmatch(n or ""):
                pads.setdefault(n, []).append((fp.GetReference(), p))
    for n, ps in pads.items():
        drv = [(r, p) for r, p in ps if r in ("U_MCU", "U1", "U2")]
        mx = [(r, p) for r, p in ps if re.fullmatch(r"(SW|D)\d+", r)]
        if len(drv) < 1 or not mx:
            raise SystemExit(f"{n}: 駆動側 {len(drv)} / 行列 {len(mx)}")
        q = drv[0][1].GetPosition()
        r, p = min(mx, key=lambda rp: math.hypot(rp[1].GetPosition().x - q.x,
                                                  rp[1].GetPosition().y - q.y))
        out[n] = ({d[0] for d in drv}, f"{r}-{p.GetNumber()}")
    return out


def edit_dsn(dsn, ends, margin_um, only=None, power=None):
    """only: 引かせる網の集合（None なら全部）。それ以外は PREWIRED と同じく外して線を protect に。
    power: {電源の網: 外すピン}（spec.POWER_RUNS の線の to の端）。その網の線は protect にし、
    ピンから to の端を外す（from の端と決まった線で繋がっている。残りを Freerouting が from へ繋ぐ）。"""
    power = power or {}
    t = dsn.read_text()
    # (a) 引き切ったネット（GND・SW*_D）を丸ごと外し、線は障害物（protect）にする
    names = sorted({n for n in re.findall(r"\(net ([^\s()]+)", t)
                    if PREWIRED.fullmatch(n) or (only is not None and n not in only)})
    for n in names:
        e = re.escape(n)
        t = re.sub(rf"\s*\(plane {e} \(polygon [\s\S]*?\)\)", "", t)
        t = re.sub(rf"\s*\(net {e}\s*\n\s*\(pins [^)]*\)\s*\n\s*\)", "", t)
        t = re.sub(rf"(\(class \S+ [^)]*?)\b{e}\b", r"\1", t)
        t = re.sub(rf"\(net {e}\)\s*\(type route\)", "(type protect)", t)
    left = [n for n in re.findall(r"\(net ([^\s()]+)", t) if n in names]
    if left:
        raise SystemExit(f"DSN から外しきれないネット: {sorted(set(left))}")
    # (b) 行列のネット: ピンを 2 つ（駆動側・最寄りの行列のパッド）に絞り、線は protect
    n_pins = {}

    def narrow(m):
        net, pins = m.group(1), m.group(2).split()
        drv, anchor = ends[net]
        keep = [p for p in pins if p.rsplit("-", 1)[0] in drv] + [anchor]
        if anchor not in pins or len(keep) < 2:
            raise SystemExit(f"{net}: DSN のピン {pins} に {anchor} / 駆動側 {drv} が無い")
        n_pins[net] = len(keep)
        return f"(net {net}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (COL\d+)\s*\n\s*\(pins ([^)]*)\)", narrow, t)
    if only is not None:
        ends = {n: e for n, e in ends.items() if n in only}
    if set(n_pins) != set(ends):
        raise SystemExit(f"DSN で絞れなかった行列のネット: {set(ends) - set(n_pins)}")
    n_fix = [0]

    def protect(m):
        n_fix[0] += 1
        return "(type protect)"
    t = re.sub(r"\(net COL\d+\)\s*\(type route\)", protect, t)
    # (b1) 電源の決まった線の網: to の端のピンを外し、線は protect
    n_pw = {}

    def narrow_power(m):
        net, pins = m.group(1), m.group(2).split()
        drop = power[net]
        if drop not in pins:
            raise SystemExit(f"{net}: DSN のピン {pins} に {drop} が無い")
        keep = [p for p in pins if p != drop]
        n_pw[net] = len(keep)
        return f"(net {net}\n      (pins {' '.join(keep)})"
    for net in power:
        if only is not None and net not in only:
            continue
        t = re.sub(rf"\(net ({re.escape(net)})\s*\n\s*\(pins ([^)]*)\)", narrow_power, t)
        t = re.sub(rf"\(net {re.escape(net)}\)\s*\(type route\)", "(type protect)", t)
    missing = {n for n in power if (only is None or n in only)} - set(n_pw)
    if missing:
        raise SystemExit(f"DSN で絞れなかった電源の網: {missing}")
    # (b2) XIAO の D0〜D6 はパッドとパッド内ビアが同じ番号（DSN では "D2" がビア・"D2@1" が
    # パッド）。**2 つを別のピンとして渡すと Freerouting はパッド → ビアの 1.2mm だけ引いて
    # 止まった**（1 回目: 行 5 本とも XIAO から出なかった）。パッドとビアは銅が重なって
    # 1 つ（KiCad の連結でも 1 つ）なので、DSN からはパッド（@1）を外し、裏へ抜けるビアから引かせる
    n_twin = [0]

    def drop_twin(m):
        pins = m.group(2).split()
        keep = [p for p in pins if not (p.startswith("U_MCU-") and p.endswith("@1")
                                        and p[:-2] in pins)]
        n_twin[0] += len(pins) - len(keep)
        return f"(net {m.group(1)}\n      (pins {' '.join(keep)})"
    t = re.sub(r"\(net (\S+)\s*\n\s*\(pins ([^)]*)\)", drop_twin, t)
    # ネットから外すだけでは、パッドは「ネットの無い障害物」としてビアに被さって残り、
    # ビアから 1 本も出なかった（2 回目）。**XIAO の部品の形（image）からも外す**
    img = re.search(r"\(image XIAO_nRF52840_SMD[\s\S]*?\n    \)", t)
    body = img.group(0)
    twins = re.findall(r"\n\s*\(pin \S+ (D\d+)@1 [^)]*\)", body)
    body2 = re.sub(r"\n\s*\(pin \S+ D\d+@1 [^)]*\)", "", body)
    t = t.replace(body, body2)
    if sorted(twins) != [f"D{i}" for i in range(7)]:
        raise SystemExit(f"XIAO の image から外したパッド {twins}（D0〜D6 の 7 つのはず）")
    # (c) クリアランスを少し増やす（KiCad の規則は変えない）
    n = [0]

    def bump(m):
        n[0] += 1
        return f"(clearance {int(m.group(1)) + margin_um})"
    t = re.sub(r"\(clearance (\d+)\)(?!\s*\(type)", bump, t)
    if not n[0]:
        raise SystemExit("DSN にクリアランスが無い（書式が変わった？）")
    # (d) (autoroute_settings) は入れない。**あるだけで Freerouting 2.3.0 が
    # ネットを 1 本も見なくなった**（CCKB 2026-09-24: "0 unrouted items"・"no SMD pins"。
    # HHKB の子基板でも同じ。ブロックを消すと同じ DSN で配線が始まった）
    dsn.write_text(t)
    return dict(stripped=names, protected_wires=n_fix[0], clearances=n[0], narrowed=n_pins,
                twins_dropped=n_twin[0], power_narrowed=n_pw)


def freerouting_revision(jar):
    """jar の MANIFEST の Build-Revision（無ければ None）。"""
    import zipfile

    with zipfile.ZipFile(jar) as z:
        for line in z.read("META-INF/MANIFEST.MF").decode().splitlines():
            if line.startswith("Build-Revision:"):
                return line.split(":", 1)[1].strip()
    return None


def freeroute(board, work, only=None):
    if not JAR.exists():
        raise SystemExit(f"Freerouting が無い: {JAR}")
    rev = freerouting_revision(JAR)
    if rev != FREEROUTING_REVISION:
        raise SystemExit(f"Freerouting の版が違う: {JAR} の Build-Revision {rev}"
                         f"（v2.3.0 は {FREEROUTING_REVISION}）")
    dsn, ses = work / "cckb.dsn", work / "cckb.ses"
    ends = matrix_ends(board)
    tried = []
    for margin in DSN_CLEARANCE_MARGINS_UM:
        for f in (dsn, ses):
            if f.exists():
                f.unlink()
        if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
            raise SystemExit("DSN の書き出しに失敗")
        info = edit_dsn(dsn, ends, margin, only, power_ends(load(PROJ)))
        log = work / f"freerouting_{margin}.log"
        with log.open("w") as fh:
            r = subprocess.run([_java(), "-jar", str(JAR), "-de", str(dsn), "-do", str(ses),
                                "-mp", str(PASSES), "--gui.enabled=false"],
                               stdout=fh, stderr=subprocess.STDOUT, timeout=3600)
        text = log.read_text()
        if r.returncode != 0 or not ses.exists():
            raise SystemExit(f"Freerouting が失敗（{r.returncode}）:\n{text[-3000:]}")
        m = re.findall(r"\((\d+) unrouted and", text)
        left = int(m[-1]) if m else None
        tried.append((margin, left))
        print(f"   Freerouting 余裕 {margin}µm: ログの未配線 {left}")
        if left == 0:
            break
    else:
        raise SystemExit(f"Freerouting がどの余裕でも引ききれない: {tried}")
    before = {f.GetReference(): (f.GetPosition(), f.GetOrientationDegrees()) for f in board.GetFootprints()}
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("SES の取り込みに失敗")
    # SES は部品の位置も持ち、取り込むと部品が丸めの分（1〜50nm）動く（2026-09-24。open-gaps A10 の
    # 50nm もこれ）。**配線器に部品を動かさせない**: 取り込む前の位置と向きに戻す
    moved = 0
    for f in board.GetFootprints():
        pos, deg = before[f.GetReference()]
        if f.GetPosition() != pos or f.GetOrientationDegrees() != deg:
            f.SetOrientationDegrees(deg)
            f.SetPosition(pos)
            moved += 1
    info["footprints_restored"] = moved
    print(f"   SES の取り込みで動いた部品を元の位置に戻した: {moved}")
    info["tried"] = tried
    info["margin_um"] = margin
    return info


def restore_rule_areas(board):
    """SES の往復でルール領域の層が消える（HHKB 実測）。名前で層を戻す。"""
    # 金属の禁止域は名前が 1 つなので、層も 1 つでなければ戻せない（いまは全部が上面のナット・インサート）
    metal = {lay for _, lay, _, _ in interface.Interface(load(PROJ)).metal_keepouts()}
    if metal != {"F.Cu"}:
        raise SystemExit(f"METAL_KEEPOUT の層が {metal}（名前で層を戻せない。名前を層ごとに分ける）")
    want = {"ANTENNA_KEEPOUT": (pcbnew.F_Cu, pcbnew.B_Cu), "XIAO_UNDERSIDE": (pcbnew.F_Cu,),
            "EDGE_KEEPOUT": (pcbnew.F_Cu, pcbnew.B_Cu), "METAL_KEEPOUT": (pcbnew.F_Cu,),
            "PSW_TAB_KEEPOUT": (pcbnew.F_Cu,),      # 電源スイッチの枠の爪の下（pcb_extra.psw_tab_keepouts）
            "NPTH_KEEPOUT": (pcbnew.F_Cu, pcbnew.B_Cu)}  # 長円の非めっきの穴の縁（pcb_extra.npth_ovals）
    seen = set()
    for z in board.Zones():
        if not z.GetIsRuleArea():
            continue
        name = z.GetZoneName()
        if name not in want:
            raise SystemExit(f"知らないルール領域 {name!r}")
        ls = pcbnew.LSET()
        for lay in want[name]:
            ls.addLayer(lay)
        z.SetLayerSet(ls)
        seen.add(name)
    if seen != set(want):
        raise SystemExit(f"ルール領域が足りない: {set(want) - seen}")


def widen_thin(board):
    n = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < MM(TRACK_W):
            t.SetWidth(MM(TRACK_W))
            n += 1
    return n


# ---------------------------------------------------------------------------
# 5. GND ベタとビア
# ---------------------------------------------------------------------------

def pour(board):
    gnd = board.FindNet("GND")
    bb = board.GetBoardEdgesBoundingBox()
    zones = []
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetNet(gnd)
        z.SetLayer(layer)
        z.SetZoneName(f"GND_{'F' if layer == pcbnew.F_Cu else 'B'}")
        z.SetLocalClearance(MM(GND_CLEAR))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        # サーマルにするパッド（spec.THERMAL_PADS）のスポーク。JLC の最小の線 0.1 より十分太く、
        # 0805 のパッドの幅 1.0 の半分以下
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        pts = pcbnew.VECTOR_VECTOR2I()
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                     (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
            pts.append(pcbnew.VECTOR2I(x, y))
        z.AddPolygon(pts)
        board.Add(z)
        zones.append(z)
    return zones


def fill(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()


def gnd_zones(board):
    return [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"]


def islands(board):
    """GND ベタの島ごとに (層, 面積 mm², 繋がっているか, 内部の点)。

    **繋がっているか**は KiCad の連結（塗ったベタ・パッド・線・ビア）で見る: 島の中に
    GND のパッドかビアか線の端が 1 つでもあり、それが本土（最大の島）と同じ連結成分なら本土。
    ここでは簡単に、**島の中に GND のビアかパッドがあるか**で判定し、無ければ浮き島とする。
    """
    anchors = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                anchors.append((p.GetPosition(), p))
    for t in board.GetTracks():
        if t.GetNetname() == "GND" and t.GetClass() == "PCB_VIA":
            anchors.append((t.GetPosition(), t))
    out = []
    for z in gnd_zones(board):
        lay = z.GetLayer()
        polys = z.GetFilledPolysList(lay)
        for i in range(polys.OutlineCount()):
            ol = polys.Outline(i)
            area = abs(ol.Area()) / 1e12
            for h in range(polys.HoleCount(i)):
                area -= abs(polys.Hole(i, h).Area()) / 1e12
            hit = any(it.IsOnLayer(lay) and polys.Contains(pos) and ol.PointInside(pos)
                      for pos, it in anchors)
            out.append((lay, area, hit, i))
    return out


def gnd_components(board):
    """GND の連結成分を**島・ビア・パッド・線をつないで**数える（islands は「島の中にビアがあれば本土」と
    簡単に見るので、ビア 1 本で表裏の 2 つの浮き島がつながっただけの組を本土と見誤る。2026-09-25 V2 の
    1 回目: U1 の脇に残った表 4.4 mm²・裏 2.8 mm² の組で KiCad の未配線が 1）。
    [(成分に入るビアの一覧, パッドの数, 島の面積の和 mm², 島 [(層, 多角形)])]（面積の大きい順。先頭が本土）。
    """
    polys = []
    for z in gnd_zones(board):
        lay = z.GetLayer()
        ps = z.GetFilledPolysList(lay)
        for i in range(ps.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET()
            one.AddOutline(ps.Outline(i))
            for h in range(ps.HoleCount(i)):
                one.AddHole(ps.Hole(i, h))
            polys.append((lay, one, abs(one.Area()) / 1e12))
    par = list(range(len(polys)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def node():
        par.append(len(par))
        return len(par) - 1

    def attach(n, pos, layers):
        for i, (lay, poly, _) in enumerate(polys):
            if lay in layers and poly.Contains(pos):
                par[find(n)] = find(i)
    items, at = [], {}
    for tr in board.GetTracks():
        if tr.GetNetname() != "GND":
            continue
        n = node()
        if tr.GetClass() == "PCB_VIA":
            attach(n, tr.GetPosition(), (pcbnew.F_Cu, pcbnew.B_Cu))
            ends = [tr.GetPosition()]
            items.append(("via", n, tr))
        else:
            attach(n, tr.GetStart(), (tr.GetLayer(),))
            attach(n, tr.GetEnd(), (tr.GetLayer(),))
            ends = [tr.GetStart(), tr.GetEnd()]
        for e in ends:
            at.setdefault((e.x, e.y), []).append(n)
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname() != "GND":
                continue
            n = node()
            attach(n, pd.GetPosition(), [lay for lay in (pcbnew.F_Cu, pcbnew.B_Cu) if pd.IsOnLayer(lay)])
            items.append(("pad", n, pd))
            q = pd.GetPosition()
            at.setdefault((q.x, q.y), []).append(n)
    for ns in at.values():                       # 端どうしが同じ点（パッド → スタブ → ビア）
        for a in ns[1:]:
            par[find(a)] = find(ns[0])
    comp = {}
    for i, (lay, poly, area) in enumerate(polys):
        c = comp.setdefault(find(i), [[], 0, 0.0, []])
        c[2] += area
        c[3].append((lay, poly))
    for kind, n, it in items:
        c = comp.setdefault(find(n), [[], 0, 0.0, []])
        if kind == "via":
            c[0].append(it)
        else:
            c[1] += 1
    return sorted(comp.values(), key=lambda c: -c[2])


def join_gnd_components(board, space, step=0.25):
    """本土から離れた GND の成分の島の中で、**反対の面が本土の島**の点にビアを打ってつなぐ（打った数）。
    （stitch_islands は「島の中にビアが無い」島しか見ない。ビアでつながった浮いた組はここで拾う）"""
    placed = 0
    for _ in range(3):
        fill(board)
        comps = gnd_components(board)
        if len(comps) == 1:
            break
        main = comps[0][3]
        progress = False
        for vias, _, _, isl in comps[1:]:
            done = False
            for lay, poly in isl:
                other = [p for l2, p in main if l2 != lay]
                bb = poly.BBox()
                y = bb.GetTop() + MM(step) // 2
                while y < bb.GetBottom() and not done:
                    x = bb.GetLeft() + MM(step) // 2
                    while x < bb.GetRight():
                        pos = pcbnew.VECTOR2I(int(x), int(y))
                        if poly.Contains(pos) and any(o.Contains(pos) for o in other) \
                                and space.free(pos, "GND"):
                            space.add_via(pos, "GND")
                            placed += 1
                            done = progress = True
                            break
                        x += MM(step)
                    y += MM(step)
                if done:
                    break
            # 両面とも線に囲まれた組: 組のビア・パッドから、本土の上の点へスタブ（0.3）を引いてビアを打つ
            pads = [pd for fp in board.GetFootprints() for pd in fp.Pads() if pd.GetNetname() == "GND"
                    and any(p.Contains(pd.GetPosition()) for _, p in isl)]
            for v in list(vias) + pads:
                if done:
                    break
                q = v.GetPosition()
                for dist in [0.6 + 0.3 * k for k in range(18)]:
                    for deg in range(0, 360, 15):
                        pos = pcbnew.VECTOR2I(int(q.x + math.cos(math.radians(deg)) * MM(dist)),
                                              int(q.y + math.sin(math.radians(deg)) * MM(dist)))
                        if not any(p.Contains(pos) for _, p in main):
                            continue
                        lays = [lay for lay in (pcbnew.B_Cu, pcbnew.F_Cu) if v.IsOnLayer(lay)]
                        lay = next((lay for lay in lays
                                    if space.free(pos, "GND", stub_from=q, stub_layer=lay)), None)
                        if lay is not None:
                            space.add_via(pos, "GND", stub_from=q, stub_layer=lay)
                            placed += 1
                            done = progress = True
                            break
                    if done:
                        break
        if not progress:
            break
    fill(board)
    return placed


def orphan_gnd_vias(board):
    """本土につながらない GND の成分のうち、**パッドを含まない**物のビアを消す（消した数）。
    パッドを含む成分が本土から離れていれば落とす（部品の GND が浮いている）。"""
    comps = gnd_components(board)
    bad = [c for c in comps[1:] if c[1]]
    if bad:
        raise SystemExit(f"GND のパッドが本土につながらない成分が {len(bad)} 個"
                         f"（パッド {[c[1] for c in bad]}・面積 {[round(c[2], 2) for c in bad]}）")
    n = 0
    for vias, _, _, _ in comps[1:]:
        for v in vias:
            board.Remove(v)
            n += 1
    return n


def fence_and_grid(board, space, pitch=6.0, fence_pitch=5.0):
    """長い配線の脇（フェンス）→ 格子。どちらも置ける所だけ。数を返す。"""
    n_fence = 0
    for t in list(board.GetTracks()):
        if t.GetClass() != "PCB_TRACK" or t.GetNetname() == "GND" or \
                re.fullmatch(r"(ROW|COL)\d+|SW\d+_D", t.GetNetname()):
            continue                       # 行列（走査の遅い信号）は格子に任せる
        a, b = t.GetStart(), t.GetEnd()
        L = math.hypot(b.x - a.x, b.y - a.y)
        if L < MM(10):
            continue
        ux, uy = (b.x - a.x) / L, (b.y - a.y) / L
        off = MM(pcbnew.ToMM(t.GetWidth()) / 2 + GND_CLEAR + VIA_R + 0.05)
        k = MM(fence_pitch / 2)
        while k < L:
            for sgn in (1, -1):
                pos = pcbnew.VECTOR2I(int(a.x + ux * k - sgn * uy * off),
                                      int(a.y + uy * k + sgn * ux * off))
                if space.free(pos, "GND"):
                    space.add_via(pos, "GND")
                    n_fence += 1
            k += MM(fence_pitch)
    bb = board.GetBoardEdgesBoundingBox()
    n_grid = 0
    y = bb.GetTop() + MM(pitch / 2)
    while y < bb.GetBottom():
        x = bb.GetLeft() + MM(pitch / 2)
        while x < bb.GetRight():
            pos = pcbnew.VECTOR2I(int(x), int(y))
            near = False
            for dx in (0, 1, -1):
                for dy in (0, 1, -1):
                    p2 = pcbnew.VECTOR2I(int(x + dx * MM(1.0)), int(y + dy * MM(1.0)))
                    if space.free(p2, "GND"):
                        space.add_via(p2, "GND")
                        n_grid += 1
                        near = True
                        break
                if near:
                    break
            x += MM(pitch)
        y += MM(pitch)
    return n_fence, n_grid


def ring(board, space, box, pitch=1.2):
    """アンテナの禁止域の縁（4 辺）に GND ビア。置けた数を辺ごとに返す。"""
    x0, y0, x1, y1 = box
    g = VIA_R + 0.15                    # 禁止域の縁からビアの縁まで 0.15
    sides = {"奥": [(x, y1 + g) for x in _steps(x0, x1, pitch)],
             "手前": [(x, y0 - g) for x in _steps(x0, x1, pitch)],
             "左": [(x0 - g, y) for y in _steps(y0, y1, pitch)],
             "右": [(x1 + g, y) for y in _steps(y0, y1, pitch)]}
    got = {}
    for side, pts in sides.items():
        n = 0
        for x, y in pts:
            pos = kpt(x, y)
            if space.free(pos, "GND"):
                space.add_via(pos, "GND")
                n += 1
        got[side] = (n, len(pts))
    return got


def _steps(a, b, pitch):
    n = max(1, int((b - a) / pitch))
    return [a + (b - a) * i / n for i in range(n + 1)]


def stitch_islands(board, space, rounds=4):
    """浮き島に、反対面のベタと重なる点でビアを打つ。繋げない島の面積を返す。"""
    placed = 0
    for _ in range(rounds):
        fill(board)
        floating = [(lay, area, i) for lay, area, hit, i in islands(board) if not hit]
        if not floating:
            return placed, []
        progress = False
        for lay, area, i in floating:
            z = next(z for z in gnd_zones(board) if z.GetLayer() == lay)
            polys = z.GetFilledPolysList(lay)
            ol = polys.Outline(i)
            bb = ol.BBox()
            step = MM(0.5)
            done = False
            y = bb.GetTop() + step // 2
            while y < bb.GetBottom() and not done:
                x = bb.GetLeft() + step // 2
                while x < bb.GetRight():
                    pos = pcbnew.VECTOR2I(int(x), int(y))
                    if ol.PointInside(pos) and space.free(pos, "GND"):
                        space.add_via(pos, "GND")
                        placed += 1
                        done = progress = True
                        break
                    x += step
                y += step
        if not progress:
            break
    fill(board)
    return placed, [(lay, a) for lay, a, hit, _ in islands(board) if not hit]


def island_vias(board):
    """GND ベタの島ごとに [(層, 面積 mm², 島の外形, [ビアの位置])]。"""
    vias = [t.GetPosition() for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    out = []
    for z in gnd_zones(board):
        lay = z.GetLayer()
        polys = z.GetFilledPolysList(lay)
        for i in range(polys.OutlineCount()):
            ol = polys.Outline(i)
            area = abs(ol.Area()) / 1e12
            inside = [v for v in vias if ol.PointInside(v) and not any(
                polys.Hole(i, h).PointInside(v) for h in range(polys.HoleCount(i)))]
            out.append((lay, area, ol, inside))
    return out


def double_single_via_islands(board, space):
    """ビア 1 本だけで繋がった島に、そのビアから**いちばん遠い**置ける点でもう 1 本打つ。

    1 本だけの島は、その 1 本を根元にした棒になり、長いと 2.4GHz で共振しうる（FR4 の λ/4 は
    約 17mm）。監査 D 軽微 4（B.Cu の 19mm の島がビア 1 本だった）。置けた数と、置けずに
    残った島（層・面積・長さ）を返す。
    """
    fill(board)
    placed, left = 0, []
    for lay, area, ol, inside in island_vias(board):
        if len(inside) != 1:
            continue
        v0 = inside[0]
        bb = ol.BBox()
        step = MM(0.5)
        cands = []
        y = bb.GetTop() + step // 2
        while y < bb.GetBottom():
            x = bb.GetLeft() + step // 2
            while x < bb.GetRight():
                pos = pcbnew.VECTOR2I(int(x), int(y))
                if ol.PointInside(pos):
                    cands.append((math.hypot(pos.x - v0.x, pos.y - v0.y), pos))
                x += step
            y += step
        cands.sort(key=lambda dp: -dp[0])
        done = False
        for d, pos in cands:
            if d < MM(2.0):                     # 近すぎる 2 本目は棒を短くしない
                break
            if space.free(pos, "GND"):
                space.add_via(pos, "GND")
                placed += 1
                done = True
                break
        if not done:
            left.append((lay, area, pcbnew.ToMM(max(bb.GetWidth(), bb.GetHeight()))))
    fill(board)
    return placed, left


# ---------------------------------------------------------------------------
# 名指しした網だけを引き直す（--reroute）
# ---------------------------------------------------------------------------

def _track_key(t):
    s, e = t.GetStart(), t.GetEnd()
    return _key_nm(t.GetNetname(), t.GetLayerName(), (s.x, s.y), (e.x, e.y)) + (t.GetWidth(),)


def _via_key(v):
    return (v.GetNetname(), v.GetPosition().x, v.GetPosition().y, v.GetWidth(pcbnew.F_Cu),
            v.GetDrillValue())


def kept_wiring(prev, reroute, board, clear=None):
    """前の板の線とビアのうち、GND（ベタ・縫いのビアは毎回作る）以外。引き直す網（reroute）は
    board のルール領域に掛からない部分だけ（掛かる部分を Freerouting が繋ぎ直す）。
    clear（CAD の矩形）があれば、引き直す網の線・ビアのうち端がその中にある物を先に捨てる（数は返す）。
    ([(ネット, 層名, 始点, 終点, 幅)], [(ネット, 位置, 径, 穴)], [外した物], 捨てた数)（KiCad の整数座標）。"""
    tracks, vias = [], []
    for t in prev.GetTracks():
        n = t.GetNetname()
        if n == "GND":
            continue
        if t.GetClass() == "PCB_VIA":
            vias.append((n, (t.GetPosition().x, t.GetPosition().y), t.GetWidth(pcbnew.F_Cu),
                         t.GetDrillValue()))
        else:
            tracks.append((n, t.GetLayerName(), (t.GetStart().x, t.GetStart().y),
                           (t.GetEnd().x, t.GetEnd().y), t.GetWidth()))
    n_clear = 0
    if clear is not None:
        def inside(q):
            x, y = cad(pcbnew.VECTOR2I(*q))
            return clear[0] <= x <= clear[2] and clear[1] <= y <= clear[3]
        keep_t = [x for x in tracks if not (x[0] in reroute and (inside(x[2]) or inside(x[3])))]
        keep_v = [x for x in vias if not (x[0] in reroute and inside(x[1]))]
        n_clear = len(tracks) - len(keep_t) + len(vias) - len(keep_v)
        tracks, vias = keep_t, keep_v
    part = [x for x in tracks if x[0] in reroute]
    pv = [x for x in vias if x[0] in reroute]
    bad_t = {i for i, x in enumerate(part) if kept_in_rule_areas(board, [x], [])}
    bad_v = {i for i, x in enumerate(pv) if kept_in_rule_areas(board, [], [x])}
    tracks = [x for x in tracks if x[0] not in reroute] + [x for i, x in enumerate(part) if i not in bad_t]
    vias = [x for x in vias if x[0] not in reroute] + [x for i, x in enumerate(pv) if i not in bad_v]
    return tracks, vias, [part[i] for i in sorted(bad_t)] + [pv[i] for i in sorted(bad_v)], n_clear


def prune_dangling(board, nets):
    """網 nets の行き止まりの線（端がパッド・ビア・同じ網の別の線のどれにも触れない）と、何にも
    触れないビアを消す。消せなくなるまで繰り返す。消した数。**名指しした網だけ**（持ってきた網は触らない）。"""
    n = 0
    while True:
        items = [t for t in board.GetTracks() if t.GetNetname() in nets]
        pads = [pd for fp in board.GetFootprints() for pd in fp.Pads() if pd.GetNetname() in nets]
        gone = []
        for t in items:
            net = t.GetNetname()
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                touch = any(u is not t and u.GetNetname() == net and u.GetClass() != "PCB_VIA"
                            and q in (u.GetStart(), u.GetEnd()) for u in items) or \
                    any(pd.GetNetname() == net and pd.HitTest(q) for pd in pads)
                if not touch:
                    gone.append(t)
                continue
            for q in (t.GetStart(), t.GetEnd()):
                lay = t.GetLayer()
                touch = any(u is not t and u.GetNetname() == net and (
                    (u.GetClass() == "PCB_VIA" and u.GetPosition() == q) or
                    (u.GetClass() != "PCB_VIA" and u.GetLayer() == lay and q in (u.GetStart(), u.GetEnd())))
                    for u in items) or \
                    any(pd.GetNetname() == net and pd.IsOnLayer(lay) and pd.HitTest(q) for pd in pads)
                if not touch:
                    gone.append(t)
                    break
        if not gone:
            return n
        for t in gone:
            board.Remove(t)
        n += len(gone)


def lay_kept(board, tracks, vias):
    """持ってきた線・ビアのうち、板に無いものを置く。置いた数。"""
    have_t = {_track_key(t) for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"}
    have_v = {_via_key(v) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"}
    n = 0
    for net, layer, a, b, w in tracks:
        if _key_nm(net, layer, a, b) + (w,) in have_t:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(*a))
        t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(w)
        t.SetLayer(LAYER[layer])
        t.SetNet(board.FindNet(net))
        board.Add(t)
        n += 1
    for net, p, d, drill in vias:
        if (net, p[0], p[1], d, drill) in have_v:
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(*p))
        v.SetWidth(d)
        v.SetDrill(drill)
        v.SetNet(board.FindNet(net))
        board.Add(v)
        n += 1
    return n


def kept_in_rule_areas(board, tracks, vias):
    """持ってきた線・ビアが、線/ビアを禁止するルール領域に掛かる網。{網: [領域名]}。"""
    out = {}
    zones = [z for z in board.Zones() if z.GetIsRuleArea()]
    for net, layer, a, b, w in tracks:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(*a))
        t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(w)
        t.SetLayer(LAYER[layer])
        sh = t.GetEffectiveShape(LAYER[layer])
        for z in zones:
            if z.GetDoNotAllowTracks() and z.IsOnLayer(LAYER[layer]) and z.Outline().Collide(sh, 0):
                out.setdefault(net, []).append(z.GetZoneName())
    for net, p, d, drill in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(*p))
        v.SetWidth(d)
        v.SetDrill(drill)
        for lay in LAYER.values():
            if any(z.GetDoNotAllowVias() and z.IsOnLayer(lay) and
                   z.Outline().Collide(v.GetEffectiveShape(lay), 0) for z in zones):
                out.setdefault(net, []).append("via")
    return out


DETOUR_CLEAR = TRACK_W + 0.05   # ずらした線とほかの銅・禁止域の間（ネットクラスの間隔 = TRACK_W ＋ Freerouting と同じ余裕 0.05）


def detours(board, dropped):
    """引き直す網から外した線（禁止域に掛かった物）を、**決まった形で**置き直す。

    外した線が水平か垂直で、掛かったのが金属の禁止域（METAL_KEEPOUT の円）だけのとき、線を円から
    離れる側へ平行にずらし（円の外接多角形の頂点 ＋ 線の半幅 ＋ DETOUR_CLEAR）、両端を 45° で元の端へ戻す。
    それ以外の形は扱わない（落とす）。置いた線がほかの網の銅・ルール領域に当たれば落とす。
    （Freerouting に繋がせると、禁止域を 10 個にしたとき同じ隙を繋げない入力があった——2026-09-24、
    禁止域を 1〜2 個にした入力では Freerouting 自身がこれと同じ 3 本〔y −43.99〕で繋いだ）
    [(ネット, 層名, 始点, 終点, 幅)] を返す。"""
    circles = []
    for z in board.Zones():
        if z.GetIsRuleArea() and z.GetZoneName() == "METAL_KEEPOUT":
            ol = z.Outline().Outline(0)
            pts = [ol.CPoint(i) for i in range(ol.PointCount())]
            bb = z.Outline().BBox()
            c = bb.Centre()
            circles.append((z, c, max(math.hypot(p.x - c.x, p.y - c.y) for p in pts)))
    out = []
    for seg in dropped:
        if len(seg) != 5:
            raise SystemExit(f"外したビアは置き直せない（形を決めていない）: {seg}")
        net, layer, a, b, w = seg
        horiz, vert = a[1] == b[1], a[0] == b[0]
        if not (horiz or vert):
            raise SystemExit(f"斜めの線の置き直しは決めていない: {seg}")
        u = 0 if horiz else 1                  # 線に沿う軸
        v = 1 - u                              # ずらす軸
        lo, hi = sorted((a, b), key=lambda q: q[u])
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(*a))
        t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(w)
        t.SetLayer(LAYER[layer])
        sh = t.GetEffectiveShape(LAYER[layer])
        hit = [(c, R) for z, c, R in circles if z.IsOnLayer(LAYER[layer]) and z.Outline().Collide(sh, 0)]
        others = [n for n in kept_in_rule_areas(board, [seg], []).get(net, []) if n != "METAL_KEEPOUT"]
        if not hit or others:
            raise SystemExit(f"金属の禁止域でないルール領域に掛かった線: {seg} {others}")
        side = {1 if a[v] > (c.y if v else c.x) else -1 for c, R in hit}
        if len(side) != 1:
            raise SystemExit(f"禁止域が線の両側にある（どちらへずらすか決まらない）: {seg}")
        sgn = side.pop()
        off = max(abs((c.y if v else c.x) + sgn * (R + w // 2 + MM(DETOUR_CLEAR)) - a[v]) for c, R in hit)
        off = int(math.ceil(off / MM(0.01))) * MM(0.01)
        y1 = a[v] + sgn * off

        def pt(p_u, p_v):
            return (p_u, p_v) if u == 0 else (p_v, p_u)
        path = [pt(lo[u], a[v]), pt(lo[u] + off, y1), pt(hi[u] - off, y1), pt(hi[u], a[v])]
        if hi[u] - lo[u] < 2 * off:
            raise SystemExit(f"線が短くて 45° で戻せない: {seg}")
        new = [(net, layer, p, q, w) for p, q in zip(path, path[1:])]
        # 置いた線がほかの網の銅・ルール領域に当たらないか
        if kept_in_rule_areas(board, new, []):
            raise SystemExit(f"ずらした線もルール領域に掛かる: {new}")
        for n2, l2, p, q, w2 in new:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*p))
            t.SetEnd(pcbnew.VECTOR2I(*q))
            t.SetWidth(w2)
            t.SetLayer(LAYER[l2])
            sh = t.GetEffectiveShape(LAYER[l2])
            for it in list(board.GetTracks()) + [pd for fp in board.GetFootprints() for pd in fp.Pads()]:
                if it.GetNetname() == net or not it.IsOnLayer(LAYER[l2]):
                    continue
                if it.GetEffectiveShape(LAYER[l2]).Collide(sh, MM(DETOUR_CLEAR)):
                    raise SystemExit(f"ずらした線 {(p, q)} が {it.GetNetname()} の銅に当たる")
        out += new
    return out


def wiring_of(board, nets):
    """網ごとの (線の鍵の集合, ビアの鍵の集合)。"""
    out = {n: (set(), set()) for n in nets}
    for t in board.GetTracks():
        n = t.GetNetname()
        if n in out:
            out[n][1 if t.GetClass() == "PCB_VIA" else 0].add(
                _via_key(t) if t.GetClass() == "PCB_VIA" else _track_key(t))
    return out


def net_pieces(board, net):
    """網 net のパッドが、線とビアでいくつの塊に分かれているか（1 なら繋がっている）。
    線の端どうし・線の端とビア・線の端とパッド（同じ層で、端がパッドの形の中）を繋ぐ。"""
    items = []                                           # (種類, 物)
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname() == net:
                items.append(pd)
    tracks = [t for t in board.GetTracks() if t.GetNetname() == net]
    items += tracks
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        parent[find(i)] = find(j)

    def ends(it):
        if isinstance(it, pcbnew.PAD):
            return []
        if it.GetClass() == "PCB_VIA":
            return [(it.GetPosition(), None)]
        return [(it.GetStart(), it.GetLayer()), (it.GetEnd(), it.GetLayer())]

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            hit = False
            for pa, la in ends(a):
                if isinstance(b, pcbnew.PAD):
                    hit |= (la is None or b.IsOnLayer(la)) and b.HitTest(pa)
                for pb, lb in ends(b):
                    hit |= pa == pb and (la is None or lb is None or la == lb)
            if not hit and isinstance(a, pcbnew.PAD):
                for pb, lb in ends(b):
                    hit |= (lb is None or a.IsOnLayer(lb)) and a.HitTest(pb)
            if hit:
                join(i, j)
    pads = [i for i, it in enumerate(items) if isinstance(it, pcbnew.PAD)]
    return len({find(i) for i in pads})


def split_clear(argv):
    """argv から --clear X0,Y0,X1,Y1 を抜く → (残り, 矩形 or None)。"""
    if "--clear" not in argv:
        return list(argv), None
    i = argv.index("--clear")
    try:
        box = tuple(float(v) for v in argv[i + 1].split(","))
    except (IndexError, ValueError):
        box = ()
    if len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]:
        raise SystemExit("使い方: --clear X0,Y0,X1,Y1（CAD・X0<X1・Y0<Y1）")
    return list(argv[:i]) + list(argv[i + 2:]), box


def parse_args(argv):
    if not argv:
        return None
    if len(argv) != 2 or argv[0] != "--reroute" or not argv[1]:
        raise SystemExit("使い方: route_pcb.py [--reroute NET[,NET...] [--clear X0,Y0,X1,Y1]]")
    return set(argv[1].split(","))


def main():
    argv, clear = split_clear(sys.argv[1:])
    reroute = parse_args(argv)
    if clear is not None and reroute is None:
        raise SystemExit("--clear は --reroute と一緒に使う")
    prev_sha = None
    if reroute is not None:
        if not OUT.exists():
            raise SystemExit(f"--reroute は前の配線済みの板 {OUT} が要る")
        prev_sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
        prev = pcbnew.LoadBoard(str(OUT))
    work = PROJ / "pcb" / "route_work"
    work.mkdir(exist_ok=True)
    board = pcbnew.LoadBoard(str(SRC))
    if reroute is not None:
        # 引き直す網は、新しい板の禁止域に掛かる線・ビアだけを外し、決まった形で置き直す（detours）。
        # それでも繋がらない網だけを Freerouting に引かせる。**CS を丸ごと外して Freerouting に引かせると
        # 1 本繋がらなかった**（2026-09-24・余裕 30/35µm。禁止域を減らした入力では繋がる、という不安定さ）
        k_tracks, k_vias, dropped, n_clear = kept_wiring(prev, reroute, board, clear)
        del prev
        print(f"   引き直す網 {sorted(reroute)} から捨てた線・ビア（端が {clear} の中）: {n_clear}")
        print(f"   引き直す網 {sorted(reroute)} から外した線・ビア（禁止域に掛かる）: {dropped}")
    segs, mvias = matrix_segments(board)
    n_mx = lay_segments(board, segs)
    lay_vias(board, mvias)
    pw_w = load(PROJ).spec.POWER_TRACK_W
    pw = power_segments(board, segs)
    n_pw = lay_segments(board, pw, width=pw_w)
    n_oe = lay_segments(board, oe_ties(board), width=0.3)   # GND のスタブと同じ太さ（SES 後の置き直しも 0.3）
    space = Space(board)
    fan = gnd_fanout(board, space)
    fan_tracks = [(t.GetNetname(), t.GetLayerName(), cad(t.GetStart()), cad(t.GetEnd()))
                  for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"
                  and t.GetNetname() == "GND"]
    fan_vias = [cad(t.GetPosition()) for t in board.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    print(f"   行列 {n_mx} 区間 / 電源の決まった線 {n_pw} 区間 / OE と GND の線 {n_oe} 区間 / GND ファンアウト {len(fan)} 個")
    if reroute is not None:
        bad = kept_in_rule_areas(board, k_tracks, k_vias)
        if bad:
            raise SystemExit(f"持ってきた配線がルール領域に掛かる網 {bad}。--reroute に足すこと")
        n_kept = lay_kept(board, k_tracks, k_vias)
        det = detours(board, dropped)            # 持ってきた配線を置いた後で（当たりを見るため）
        print(f"   外した線の置き直し: {[(n, l, cad(pcbnew.VECTOR2I(*a)), cad(pcbnew.VECTOR2I(*b))) for n, l, a, b, _ in det]}")
        k_tracks = k_tracks + det
        n_kept += lay_kept(board, det, [])
        kept_nets = sorted(({t[0] for t in k_tracks} | {v[0] for v in k_vias}) - reroute)
        want_kept = wiring_of(board, kept_nets)
        print(f"   前の板から持ってきた線・ビア {n_kept}（網 {len(kept_nets)}）/ 引き直す網 {sorted(reroute)}")
    if reroute is not None:
        left = [n for n in sorted(reroute) if net_pieces(board, n) != 1]
        if not left:
            info = dict(stripped=[], protected_wires=0, clearances=0, narrowed={}, twins_dropped=0,
                        tried=[], margin_um=None)
            print(f"   引き直す網 {sorted(reroute)} は置き直しで繋がった（Freerouting を回さない）")
        else:
            info = freeroute(board, work, set(left))
    else:
        info = freeroute(board, work, reroute)
    if info["tried"]:
        print(f"   Freerouting: 外したネット {len(info['stripped'])} 本（GND・SW*_D・ROW*）/ protect の線"
              f" {info['protected_wires']} / 採った余裕 {info['margin_um']}µm（試した {info['tried']}）")
    restore_rule_areas(board)
    if info["tried"]:           # SES を取り込んだときだけ（取り込みが既存の配線を作り直す）
        # SES の取り込みで消えたものを置き直す（位置は決定的）
        miss = tracks_present(board, segs)
        if miss:
            lay_segments(board, miss)
        n_mv = lay_vias(board, mvias)
        miss2 = tracks_present(board, segs)
        if miss2:
            raise SystemExit(f"行列の線が置き直せない: {miss2[:5]}")
        n_twin = snap_rounded_twins(board, pw)
        if n_twin:
            print(f"   SES で 1nm ずれた電源の線を計画の座標に戻した: {n_twin}")
        miss_pw = tracks_present(board, pw)
        if miss_pw:
            lay_segments(board, miss_pw, width=pw_w)
        if tracks_present(board, pw):
            raise SystemExit(f"電源の決まった線が置き直せない: {tracks_present(board, pw)[:5]}")
        have_gnd = tracks_present(board, fan_tracks)
        if have_gnd:
            lay_segments(board, have_gnd, width=0.3)
        have_v = {cad(t.GetPosition()) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"}
        for v in fan_vias:
            if v not in have_v:
                nv = pcbnew.PCB_VIA(board)
                nv.SetPosition(kpt(*v))
                nv.SetWidth(MM(VIA_D))
                nv.SetDrill(MM(VIA_DRILL))
                nv.SetNet(board.FindNet("GND"))
                board.Add(nv)
        n_thin = widen_thin(board)
        print(f"   SES 後に置き直した: 行列 {len(miss)} / ビア {n_mv} / GND スタブ {len(have_gnd)} / 細い線 {n_thin}")
    if reroute is not None:
        # SES の取り込みで持ってきた配線が消えた・増えたなら、前の板と同じ集合に戻す
        # **引き直す網は戻さない**: SES は引き直す網の持ってきた線も 1µm に丸めて返すので、元の線を
        # 戻すと 0.4µm ずれた二重の線・ビアになる（2026-09-24 に VBAT_SW で起きた）
        n_back = lay_kept(board, [x for x in k_tracks if x[0] not in reroute],
                          [x for x in k_vias if x[0] not in reroute]) if info["tried"] else 0
        extra = []
        for t in list(board.GetTracks()):
            n = t.GetNetname()
            if n not in want_kept:
                continue
            key = _via_key(t) if t.GetClass() == "PCB_VIA" else _track_key(t)
            if key not in want_kept[n][1 if t.GetClass() == "PCB_VIA" else 0]:
                extra.append(t)
        for t in extra:
            board.Remove(t)
        got = wiring_of(board, kept_nets)
        # **前の板そのものと**比べる（行列を引き直した線が前の板と違えば、ここで分かる）
        prev_w = {n: ({_key_nm(n, l, a, b) + (w,) for n2, l, a, b, w in k_tracks if n2 == n},
                      {(n, p[0], p[1], d, dr) for n2, p, d, dr in k_vias if n2 == n}) for n in kept_nets}
        if got != want_kept or got != prev_w:
            diff = [n for n in kept_nets if got[n] != want_kept[n] or got[n] != prev_w[n]]
            raise SystemExit(f"持ってきた配線が前の板と同じにならない網: {diff}")
        print(f"   持ってきた配線: SES 後に置き直した {n_back} / 余分を消した {len(extra)}"
              f" / 前の板と同じ網 {len(kept_nets)}")

    # 持ってきた配線を戻した後で（戻すと消した行き止まりがまた増える）
    n_pruned = prune_dangling(board, reroute) if reroute is not None else 0
    if n_pruned:
        print(f"   引き直した網の行き止まりの線・ビアを消した: {n_pruned}")
    pour(board)
    fill(board)
    space = Space(board)
    ifc = interface.Interface(load(PROJ))
    n_ring = ring(board, space, ifc.antenna_keepout())
    n_fence, n_grid = fence_and_grid(board, space)
    n_is, left = stitch_islands(board, space)
    n_dbl, single = double_single_via_islands(board, space)
    # 繋げなかった島は消す（浮いた銅は 2.4GHz でアンテナになりうる）。面積は記録する
    removed = sum(a for _, a in left)
    for z in gnd_zones(board):
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    fill(board)
    # ビアだけでつながった浮き島の組（islands の簡単な判定では本土に見える）: 本土へつなぐビアを打ち、
    # それでも残ったパッドの無い組はビアを消して塗り直す
    n_join = join_gnd_components(board, Space(board))
    n_orphan = orphan_gnd_vias(board)
    if n_orphan:
        fill(board)
    if len(gnd_components(board)) != 1:
        raise SystemExit(f"GND が {len(gnd_components(board))} 個の成分に分かれたまま")
    print(f"   GND ビア: リング {n_ring} / フェンス {n_fence} / 格子 {n_grid} / 離島 {n_is}"
          f" / 消した島 {len(left)} 個 {removed:.2f} mm² / 1 本の島に足した {n_dbl}"
          f" / 1 本のまま {[(round(a, 1), round(L, 1)) for _, a, L in single]}"
          f" / 浮いた組を本土へつないだビア {n_join} / 浮いた組のビアを消した {n_orphan}")

    board.BuildConnectivity()
    unconnected = board.GetConnectivity().GetUnconnectedCount(False)
    board.Save(str(OUT))
    pro_src = SRC.with_suffix(".kicad_pro")
    shutil.copy(pro_src, OUT.with_suffix(".kicad_pro"))
    sync_project_rules(OUT, getattr(load(PROJ).spec, "DRC_SEVERITY", None))
    areas = {("F" if lay == pcbnew.F_Cu else "B"): round(sum(
        a for l2, a, _, _ in islands(board) if l2 == lay), 1) for lay in (pcbnew.F_Cu, pcbnew.B_Cu)}
    rec = dict(board=OUT.name, unrouted=SRC.name,
               unrouted_fingerprint=boardhash.fingerprint(SRC),
               # 指紋（boardhash）は配置・結線・外形だけで、**パッドの形とルール領域を見ない**。
               # 配線した元のファイルそのもの（バイト列）も残す（2026-09-24: XIAO のパッドを縮め、
               # 禁止域を足しても指紋は変わらなかった）
               unrouted_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest(),
               freerouting=JAR.name, passes=PASSES, margin_um=info["margin_um"],
               margins_tried=info["tried"],
               matrix_segments=n_mx, power_segments=n_pw, gnd_fanout=len(fan), ring=n_ring, fence=n_fence,
               grid=n_grid, island_vias=n_is, second_island_vias=n_dbl,
               single_via_islands=[dict(layer="F.Cu" if lay == pcbnew.F_Cu else "B.Cu",
                                        area_mm2=round(a, 2), length_mm=round(L, 2))
                                   for lay, a, L in single],
               rerouted_nets=sorted(reroute) if reroute is not None else None,
               cleared_box=list(clear) if clear is not None else None,
               cleared=n_clear if reroute is not None else None,
               pruned_dangling=n_pruned,
               kept_from_sha256=prev_sha,
               islands_removed=len(left), joined_vias=n_join, orphan_vias_removed=n_orphan,
               islands_removed_mm2=round(removed, 2), gnd_area_mm2=areas,
               unconnected=unconnected)
    (PROJ / "pcb" / "route.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    shutil.rmtree(work)
    print(f"{'OK' if unconnected == 0 else 'NG'} {OUT.name}: 未配線 {unconnected} / GND の面積 {areas}")
    return 0 if unconnected == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
