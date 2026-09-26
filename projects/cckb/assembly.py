"""CCKB を組み上げたモデルと、その検査の道具。**寸法は持たない**（spec / interface / case_spec）。

**製品として存在する物を全部置く**（HHKB の教訓: USB が挿さらなかったのは、利用者が挿す
ケーブルがモデルに入っていなかったから）。入っていない物は検査していない。

  印刷する物: トレイ 2・ふた 2・キーキャップ 62（spec.PLATE が True ならプレート 2＋スペースの枠。いまは使わない）
  基板: **発注する配線済みの板**（pcb/cckb_main.kicad_pcb を KiCad の Python で読む）。外形と
        スタビの逃げ穴は Edge.Cuts、穴はパッドの穴（取付 10・ふたの柱の穴・スイッチの足・ビア入りの
        パッド）。XIAO・電池ホルダ・電源スイッチは**板の上のフットプリントの位置と向き**に、
        図面の外形（spec）で置く。裏の部品は板の裏に付いたフットプリントのコートヤード × 背の上限
  買う物: スイッチ 62（図面の外形＋足）・スタビ 8・XIAO（USB-C のメス）・電池ホルダ・CR1632・
        電源スイッチ・M2 ナット 9・M2×6 皿 11・インサート 2・滑り止め 4
  外から来る物: USB-C プラグ（金属＋樹脂）・机・ドライバー・爪

形は実物より**大きく**取る（包絡）。印刷する物は生成した立体そのもの。

検査の道具:
  interference(...)  B-rep の総当たり（外接箱で絞ってから共通部分の体積）
  sweep(...)         平行移動で通る領域（前を向いた面の角柱 ∪ 元の立体 = 厳密）
  probe(...)         断面を線で刺して、材料の厚さを測る

    .venv/bin/python3 projects/cckb/assembly.py     # 検査の結果と絵を build/cckb/ に
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build123d import Compound, Pos, Solid  # noqa: E402

import case_spec as CS  # noqa: E402
import interface as I  # noqa: E402
import keycaps as KC  # noqa: E402
from case import Case, box, cone, cyl, fuse, hex_prism, prism, rbox  # noqa: E402
from foundry import paths  # noqa: E402
from foundry.layout import UNIT  # noqa: E402
from foundry.mech import CHOC_V2_STAB_HOLES, CHOC_V2_STAB_SOURCES  # noqa: E402


# ---------------------------------------------------------------------------
# 基板の実物（KiCad）
# ---------------------------------------------------------------------------

ROUTED_BOARD = I.ROUTED_BOARD


def board_geometry(board=ROUTED_BOARD):
    """**発注する配線済みの板**のフットプリント（位置・向き・裏か）・パッド・コートヤード・
    外形（Edge.Cuts）を CAD 座標で返す。

    生成器の板ではなく配線済みの板を読む: ケースが当たるかを見る相手は、刷ったケースに
    入る実物だから。板が生成器と食い違わないことは tests/test_cckb_pcb.py の鮮度の検査が見る
    （未配線の板 = いまの生成器・route.json の指紋 = 未配線の板）。

    発注する板は、コミットした写し（interface.board_geometry・板の sha256 で突き合わせる）を読む
    ので KiCad が要らない（CI でもケースの検査が走る。最終レビュー I5）。ほかの板は KiCad の Python で読む。
    """
    if Path(board) == ROUTED_BOARD:
        return I.board_geometry(board)
    return read_board_geometry(board)


def read_board_geometry(board):
    """板を KiCad の Python（tools/board_geometry.py）で読む。"""
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "geo.json"
        r = subprocess.run([paths.KICAD_PYTHON, str(HERE / "tools/board_geometry.py"), str(board), str(out)],
                           cwd=paths.ROOT, capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
        return json.loads(out.read_text())


# ---------------------------------------------------------------------------
# 幾何の道具
# ---------------------------------------------------------------------------

def solids_of(part):
    return list(part.solids()) if part is not None else []


def _bb(s):
    b = s.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def _bb_overlap(a, b, eps=1e-6):
    return all(a[k] < b[k + 3] - eps and b[k] < a[k + 3] - eps for k in range(3))


SLIVER = 1e-3               # 共通部分の一番薄い向きがこれ未満なら丸めの削りかす（基板の座標は 1e-4 に丸めてある）


class GeometryFailure(RuntimeError):
    """形状演算（共通部分・体積）が失敗した。**干渉 0 と数えない。**"""


def common_volume(a, b, slivers=None):
    """共通部分の体積。**丸めの削りかす**（厚さ SLIVER 未満）は 0 にして slivers に数える。

    OCC の真偽演算が壊れた立体を返して体積が取れないときは GeometryFailure を上げる。
    前は 0 を返していて、その組は「重なっていない」ことになった（最終レビュー I2）。
    検査が一番信用できなくなる場所で緑になるので、握り潰さない。
    """
    c = a & b
    if c is None:
        return 0.0
    try:
        v = float(c.volume)
    except (AttributeError, ValueError) as e:
        raise GeometryFailure(f"共通部分の体積が取れない: {type(e).__name__}: {e}") from e
    if v > 0:
        sz = c.bounding_box().size
        if min(sz.X, sz.Y, sz.Z) < SLIVER:
            if slivers is not None:
                slivers.append(v)
            return 0.0
    return v


def interference(groups_a, groups_b=None, skip=(), tol=1e-3, slivers=None, failures=None):
    """群どうしの重なり {(名前 a, 名前 b): 体積}。**外接箱で絞ってから B-rep の共通部分**。

    groups: {名前: 立体}。groups_b が無ければ groups_a の中の全組。skip は見ない組（名前の組）。
    返すのは tol を超えた組だけ。削りかす（common_volume）は slivers（リスト）に数える——
    **隠さない**: 呼ぶ側が数を報告する。

    形状演算の失敗（GeometryFailure）は、failures（リスト）を渡せば ((a, b), 理由) を積んで
    続ける（呼ぶ側が 0 件を確かめる）。渡さなければそのまま上げる。どちらでも 0 とは数えない。
    """
    names_a = list(groups_a)
    if groups_b is None:
        pairs = [(a, b) for k, a in enumerate(names_a) for b in names_a[k + 1:]]
        gb = groups_a
    else:
        pairs = [(a, b) for a in names_a for b in groups_b]
        gb = groups_b
    cache = {}

    def sols(g, n):
        key = (id(g), n)
        if key not in cache:
            cache[key] = [(s, _bb(s)) for s in solids_of(g[n])]
        return cache[key]

    out = {}
    for a, b in pairs:
        if (a, b) in skip or (b, a) in skip or a == b:
            continue
        v = 0.0
        for sa, ba in sols(groups_a, a):
            for sb, bb in sols(gb, b):
                if _bb_overlap(ba, bb):
                    try:
                        v += common_volume(sa, sb, slivers)
                    except GeometryFailure as e:
                        if failures is None:
                            raise GeometryFailure(f"{a} × {b}: {e}") from e
                        failures.append(((a, b), str(e)))
        if v > tol:
            out[(a, b)] = v
    return out


def sweep(part, vec):
    """part を vec だけ平行移動するときに通る領域（元の立体 ∪ 前を向いた面の角柱）。

    厳密: 移動後の立体の点 q について、q − vec から q への線分が立体を出るなら、出た所の
    前向きの面の角柱に q が入る。出なければ q は元の立体の中。
    """
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    v = gp_Vec(*vec)
    n = math.sqrt(sum(c * c for c in vec))
    d = tuple(c / n for c in vec)
    prisms = []
    for s in solids_of(part):
        for f in s.faces():
            nrm = f.normal_at(f.center())
            if nrm.X * d[0] + nrm.Y * d[1] + nrm.Z * d[2] > 1e-6:
                prisms.append(Solid(BRepPrimAPI_MakePrism(f.wrapped, v).Shape()))
    return fuse(solids_of(part) + prisms)


def moved(part, vec):
    return Pos(*vec) * part


def material_runs(mesh, origin, direction):
    """線（origin から direction へ）が立体の中を通る区間の長さ [(入る, 出る), ...]。"""
    import numpy as np

    o = np.array([origin], dtype=float)
    d = np.array([direction], dtype=float)
    locs, _, _ = mesh.ray.intersects_location(o, d, multiple_hits=True)
    if len(locs) == 0:
        return []
    t = sorted(set(round(float((p - o[0]) @ d[0]), 6) for p in locs))
    return [(t[k], t[k + 1]) for k in range(0, len(t) - 1, 2)]


def mesh_of(part):
    import trimesh

    verts, faces = part.tessellate(0.02, 0.2)
    return trimesh.Trimesh([(v.X, v.Y, v.Z) for v in verts], faces, process=True)


# ---------------------------------------------------------------------------
# 組み立て
# ---------------------------------------------------------------------------

# **部品ごとに「何で留まっているか」**。ここに無い部品を組み立てに足すと検査が落ちる
# （留め方が書かれていない部品は、留まっていないのと同じ。HHKB gen_assembly.HELD_BY）
HELD_BY = {
    "tray_L": "下からの M2×6 皿 5 本（H0・H1・H2・H4・H5）で基板の上面のナットへ（＋H3 は左のふたと共締め）",
    "tray_R": "下からの M2×6 皿 4 本（H6〜H9）で基板の上面のナットへ",
    "lid_L": "下からの M2×6 皿（H3）がトレイ・基板を抜けて、ふたのボスのインサートへ。ボスの下面が基板の上面に締まる",
    "lid_R": "上からの M2×6 皿 1 本（膜で捕まえてあり、外してもふたから落ちない）が、トレイの柱のインサートへ",
    # プレート（spec.PLATE が True のときだけ組み立てに入る。決定記録 2026-09-26-plateless）
    "plate_L": "スイッチ（はんだ付け）の爪。プレートはスイッチで基板に留まる（D11）",
    "plate_R": "同上",
    "plate_frames": "スペース 2 キーのスイッチの枠（別に刷る）。スイッチの ±x の辺の爪 4 つとつばが挟む（プレートと同じ）",
    "pcb": "取付 10 本（ナット）と、ボス・柱に載る",
    "switches": "基板にはんだ付け（足 2 本）。中心の突起と位置決めの突起が基板の穴で位置を決める（プレートを戻せばその爪も）",
    "stabs": "基板に裏からねじ 1 本（箱のナット）と爪（基板の穴に掛かる）",
    "bottom_parts": "基板にはんだ付け（JLC の実装）",
    "xiao": "基板の表にはんだ付け（キャステレーション）",
    "holder": "基板の表にはんだ付け",
    "cell": "ホルダの＋のクリップが上から押さえ、右のふたが上を塞ぐ",
    "psw": "基板の表に差し、裏から利用者がはんだ付け（スルーホールの足 3 本）。足は切る（spec.PSW_PIN_TRIM）",
    "nuts": "下からのネジが締める。回り止めは、プレートが無い（いま）なら締める・緩めるときに上からナット回しかピンセットで押さえる"
            "（プレートを戻せばその六角の穴）",
    "screws": "ナット（キーの下 9）とインサート（H3）へねじ込み",
    "screw_lid": "柱のインサートへねじ込み。ふたの膜が抜け落ちを止める",
    "inserts": "熱圧入（下穴 INSERT_HOLE_D が外径より小さい）",
    "keycaps": "ステムの穴 2 つに脚を圧入",
    "pads": "くぼみに粘着",
    "usb_plug": "利用者が挿すケーブル（留める物ではない）",
    "desk": "机（基準）",
}

# 設計どおりに重なる組（名前の組 → 理由）。**見ない組には代わりの検査を置く**（下の EXPECTED_CHECKS）
PLATE_PARTS = ("plate_L", "plate_R", "plate_frames")


def held_by(asm):
    """この組み立てに入る部品の HELD_BY（プレートを使わなければ PLATE_PARTS を除く）。"""
    return {k: v for k, v in HELD_BY.items() if asm.plate or k not in PLATE_PARTS}


EXPECTED = {
    ("inserts", "tray_R"): "熱圧入（下穴は外径より小さい）",
    ("inserts", "lid_L"): "熱圧入（同上）",
    ("screw_lid", "lid_R"): "ネジが膜をねじ切って通る（捕まえる膜）",
}


# 板の上の部品で、**図面の外形で別に置く物**（ref → 群・板の上の向き〔度〕・裏か）。
# 位置と向きは板のフットプリントから読み、形は spec（データシート）から。向きが違えば落とす
# （形の向きを決め打ちしているので、板で回っていたら形が嘘になる）
PLACED = {"U_MCU": ("xiao", 90.0, False), "BT1": ("holder", 0.0, False), "SW_PWR": ("psw", 0.0, False)}


def placed_interface(ifc, geo):
    """ifc の写しで、XIAO・ホルダ・電源スイッチの位置を**板のフットプリント**に置き換えた物。

    ケース（self.i）は境界の決定の位置で作り、買う物（self.r）は板の実物の位置に置く——
    両者がずれればケースと部品が当たる（自分の宣言どうしを突き合わせない）。
    """
    import copy

    fps = {f["ref"]: f for f in geo["footprints"]}
    for ref, (_, deg, back) in PLACED.items():
        f = fps[ref]
        assert abs((f["deg"] - deg + 180) % 360 - 180) < 1e-6 and f["back"] == back, (ref, f)
    s = ifc.s
    over = {"XIAO_AT": (fps["U_MCU"]["x"] - s.XIAO_PIN_SHIFT, fps["U_MCU"]["y"]),   # 原点はピンの並びの中心
            "HOLDER_AT": (fps["BT1"]["x"], fps["BT1"]["y"]),                        # 原点は本体の中心
            "PSW_AT": (fps["SW_PWR"]["x"], fps["SW_PWR"]["y"])}                     # 原点は本体の中心
    ns = {k: getattr(s, k) for k in dir(s) if k.isupper()}
    ns.update(over)
    r = copy.copy(ifc)
    r.s = types.SimpleNamespace(**ns)
    return r


class Assembly:
    """組み上げた物。geo は board_geometry() の結果。

    self.i: 境界の決定（ケースはこれで作る）。self.r: 同じ物で、板の上の部品の位置を
    **配線済みの板のフットプリント**に置き換えた物（XIAO・ホルダ・電池・電源スイッチ・プラグはこれで置く）。
    """

    def __init__(self, geo, ifc=None, cs=CS, plate=None):
        self.i = ifc or I.Interface()
        self.s = self.i.s
        # プレートを置くか。既定は spec.PLATE（いまは False）。True/False を渡すと spec によらずその形で組む
        # （プレートを戻したときに組み立てが壊れていないことを、使わない間も検査が見るため）
        self.plate = bool(getattr(self.s, "PLATE", True)) if plate is None else plate
        self.c = cs
        self.z = self.i.z()
        self.case = Case(self.i, cs)
        self.geo = geo
        self.r = placed_interface(self.i, geo)

    # --- 印刷する物 ---------------------------------------------------------
    def printed(self):
        return self.case.parts()

    def plates(self):
        """プレート（左右＋スペースの枠）。**self.plate が False なら空**（組み立てに入れない）。"""
        if not self.plate:
            return {}
        return self.plate_parts()

    def plate_parts(self):
        """プレートの立体（self.plate によらず作る。戻すときの検査と、プレート無しの検査の比べに使う）。"""
        from foundry.plate import build_plate, plate_frames, split_plate

        p = self.i.p
        keys = p.pieces()["main"]
        whole, _, _ = build_plate(self.s, keys, "main")
        out = {}
        for name, part in split_plate(self.s, whole, "main", keys):
            out["plate_" + name.split("_")[-1]] = Pos(0, 0, self.z["plate_bottom"]) * part
        frames = plate_frames(self.s, keys, "main")
        if frames:
            out["plate_frames"] = Compound([Pos(0, 0, self.z["plate_bottom"]) * f for _, f in frames])
        return out

    def keycap_solids(self, pressed=False):
        z0 = self.z["stem_top"] - (self.travel() if pressed else 0.0)
        out = []
        cache = {}
        for (x, y), k in zip(self.i.positions, self.i.keys):
            if k.w_u not in cache:
                cache[k.w_u] = KC.keycap(k.w_u, self.s, self.i.sw, self.c)
            out.append(Pos(x, y, z0) * cache[k.w_u])
        return out

    # --- 基板 ---------------------------------------------------------------
    def pcb(self):
        """配線済みの板の Edge.Cuts（外形・スタビの逃げ穴 8）と、パッドの穴（取付・ふたの柱の穴 H_LID・
        スイッチの足・XIAO のパッド内ビア）。"""
        z = self.z
        o = self.geo["outline"]
        poly = lambda pts: [tuple(q) for q in pts]          # noqa: E731  build123d は点を tuple で受ける（list は面が潰れる）
        slab = prism(poly(o["outer"]), z["pcb_bottom"], z["pcb_top"])
        holes = [cyl(p["x"], p["y"], z["pcb_bottom"] - 1, z["pcb_top"] + 1, p["drill"])
                 for p in self.geo["pads"] if p["drill"] > 0]
        holes += [prism(poly(h), z["pcb_bottom"] - 1, z["pcb_top"] + 1) for h in o["holes"]]
        assert len(o["holes"]) == len(self.i.stab_pivots()), len(o["holes"])   # スタビの逃げ穴 8 だけ
        return slab - fuse(holes)

    def travel(self):
        """押し切りの沈み（静音の全行程の最大 2.8 ＋ 0.25）。キャップ・ステム・スタビの軸が一緒に沈む。"""
        return KC.travel_max(self.s)

    def switch_solids(self, pressed=False):
        """スイッチ（静音の V2 の図面の外形・包絡）。足・突起は**基板の穴の位置から**。

        胴（開口 13.95 角・プレートの上面まで）＋つば 15.0 角＋上の胴（ハウジングの上面 5.30 まで）＋静音のつば
        φSWITCH_COLLAR_D（5.70 まで）。ステム φ6.50 の中に窪み φ5.70（底 SW_RECESS_FLOOR）と十字 4.00 × 1.30。
        押し切るとステムは travel だけ沈む（胴にはその分の穴）。
        足: 中心の突起 φ4.80・端子（穴 φ1.2 より 0.2 細い）・位置決めの穴の中の突起（丸穴 φ2.1 より 0.2 細い円柱で包む。
        2026-09-26 に長穴 1.6 × 2.0 から）。長さは公差の上限と
        **基板の厚さの公差（薄い側）**を足す: 板は下面でボスに載るので、薄い板では足の先がその分下がる。
        """
        s, c, z = self.s, self.c, self.z
        cut = self.i.sw.cutout
        travel = self.travel()
        fps = {f["ref"]: f for f in self.geo["footprints"] if re.fullmatch(r"SW\d+", f["ref"])}
        pads = {}
        for p in self.geo["pads"]:
            if re.fullmatch(r"SW\d+", p["ref"]) and p["drill"] > 0:
                pads.setdefault(p["ref"], []).append(p)
        out = []
        dz = -travel if pressed else 0.0
        thin = s.PCB_T_TOL_ABS
        for ref, f in sorted(fps.items()):
            x, y = f["x"], f["y"]
            h = cut / 2
            f2 = c.SW_FLANGE / 2
            housing = fuse([box(x - h, y - h, z["pcb_top"], x + h, y + h, z["plate_top"]),
                            box(x - f2, y - f2, z["plate_top"], x + f2, y + f2, z["plate_top"] + c.SW_FLANGE_T),
                            box(x - h, y - h, z["plate_top"] + c.SW_FLANGE_T, x + h, y + h, z["switch_top"]),
                            cyl(x, y, z["switch_top"] - 0.01, z["collar_top"], s.SWITCH_COLLAR_D)])
            housing = housing - cyl(x, y, z["switch_top"] - travel - 0.1, z["collar_top"] + 1, c.SW_STEM_D + 0.1)
            parts = [housing]
            recess_floor = z["pcb_top"] + c.SW_RECESS_FLOOR
            stem = cyl(x, y, z["switch_top"] + dz, z["stem_top"] + dz, c.SW_STEM_D) \
                - cyl(x, y, recess_floor + dz, z["stem_top"] + dz + 1, c.SW_RECESS_D)
            stem = fuse([stem] + [Pos(x, y, 0) * q for q in KC.cross(0.0, recess_floor + dz - 0.01,
                                                                    z["stem_top"] + dz, c.STEM_CROSS)])
            parts.append(stem)
            for p in pads[ref]:
                if p["npth"] and p["drill"] > 3:          # 中心の穴 φ5.05（位置決めも丸の非めっきなので径で分ける）
                    length, d = s.SWITCH_STUD_L + s.SWITCH_STUD_TOL, s.SWITCH_STUD_D
                else:
                    length, d = s.SWITCH_PIN_L + s.SWITCH_PIN_TOL, p["drill"] - 0.2
                parts.append(cyl(p["x"], p["y"], z["pcb_top"] - length - thin, z["pcb_top"] + 0.01, d))
            out.append(fuse(parts))
        return out

    def stab_solids(self, pressed=False):
        """スタビ（遊舎工房 A050001-01-1）を支点ごとに。位置は販売者の足跡（実物の実測・mech.CHOC_V2_STAB_HOLES）、
        足跡に無い形は仕入れ先の図（参照・mech.CHOC_V2_STAB_SOURCES["drawing"]）と縮尺の読み（case_spec）。

        支点（キーの中心 ± mech.CHOC_V2_STAB_PIVOT 11.9）から、基板の上面を高さ 0 として（y はキーの中心から・ワイヤ = 奥 = +y）:
          ねじのボス   y −8.50〜−3.65（丸い端 r 2.90）・幅 5.80・高さ 2.85
          箱           y ±3.65・幅 5.80・下 −3.30（基板の穴を通る。薄い板の分 0.16 さらに下）〜上 5.00。
                       押したときは上面の口（スライダーの胴 STAB_SLIDER_W 角）が行程だけ空く（キャップの台が入る）
          肩           y 3.65〜爪の手前・幅 5.80・高さ STAB_SHOULDER_H（縮尺で読んだ）
          爪           φ3.50 を y 8.24（足跡の爪の穴の中心）に・下 −2.65〜上 STAB_CLAW_TOP
          ねじの頭     φSTAB_SCREW_HEAD_D を y −6.20 に・基板の下面から STAB_SCREW_HEAD_H（2026-09-26 に φ2.78 × 1.15 から）
          軸           十字 3.95 × 1.26・箱の上面から 8.60（押し切ると travel 沈む）
        ワイヤ φ1.20 はキーごとに左右の爪の間を爪の y・高さ STAB_WIRE_Z（角の包絡）。
        """
        s, c, z = self.s, self.c, self.z
        d = CHOC_V2_STAB_SOURCES["drawing"]
        T = z["pcb_top"]
        w2 = d["part"][0] / 2
        half = d["part"][1] / 2
        front = d["length"] - (d["claw"][0] + d["ring"] / 2)            # 8.50
        screw_y, claw_y = CHOC_V2_STAB_HOLES["screw"][0][1], CHOC_V2_STAB_HOLES["claw"][0][1]
        dz = -self.travel() if pressed else 0.0
        out = []
        piv = self.i.stab_pivots()
        for px, py, _ in piv:
            thin = s.PCB_T_TOL_ABS          # 薄い板では下へ出る物の先がその分下がる（switch_solids と同じ）
            body = box(px - w2, py - half, T - s.STAB_BOX_L - thin, px + w2, py + half, T + d["box_top"])
            if pressed:                     # スライダーの胴が沈んで空いた口
                sw = c.STAB_SLIDER_W / 2
                body = body - box(px - sw, py - sw, T + d["box_top"] + dz, px + sw, py + sw, T + d["box_top"] + 1)
            parts = [body,
                     box(px - w2, py - front + w2, T, px + w2, py - half + 0.01, T + d["boss_top"]),
                     cyl(px, py - front + w2, T, T + d["boss_top"], 2 * w2),
                     box(px - w2, py + half - 0.01, T, px + w2, py + claw_y - 0.6, T + c.STAB_SHOULDER_H),
                     cyl(px, py + claw_y, T - s.STAB_CLAW_L - thin, T + c.STAB_CLAW_TOP, d["ring"]),
                     cyl(px, py + screw_y, z["pcb_bottom"] - s.STAB_SCREW_HEAD_H, z["pcb_bottom"],   # 頭は基板の下面に着く
                         s.STAB_SCREW_HEAD_D)]
            parts += [Pos(px, py, 0) * q for q in KC.cross(0.0, T + d["box_top"] - 0.01 + dz,
                                                          T + d["stem_top"] + dz, d["slider"])]
            out.append(fuse(parts))
        for (xl, yl, _), (xr, _, _) in zip(piv[0::2], piv[1::2]):
            r = d["wire"] / 2
            out.append(box(xl, yl + claw_y - r, T + c.STAB_WIRE_Z - r, xr, yl + claw_y + r,
                           T + c.STAB_WIRE_Z + r))
        return out

    def bottom_refs(self):
        """裏に付く部品（板で**裏返したフットプリント**）のうち、図面の形で別に置かない物。

        「裏のコートヤードがある物」で拾うと、表から開けた穴（H_LID は両面にコートヤードを持つ）を
        部品として数え、図面の形で置いた電源スイッチ（psw）を二重に数える（2026-09-24 の統合で起きた）。
        """
        return sorted(f["ref"] for f in self.geo["footprints"] if f["back"] and f["ref"] not in PLACED)

    def bottom_parts(self):
        """裏の部品（ダイオード 62・595 ×2・パスコン 2・分圧 2・D_PWR）: コートヤード × 背の上限
        spec.BOTTOM_PART_H（データシートの最大の最大）。"""
        z = self.z
        fps = {f["ref"]: f for f in self.geo["footprints"]}
        return [rbox(fps[r]["courtyard"]["back"], z["pcb_bottom"] - self.s.BOTTOM_PART_H, z["pcb_bottom"])
                for r in self.bottom_refs()]

    def xiao(self):
        """XIAO: 基板＋上の部品（USB の上面の高さまでの箱）＋ USB-C のメス（中空）。板の U_MCU の位置。"""
        s, z = self.s, self.z
        b = self.r.xiao()
        board_t = s.XIAO_USB_Z - s.XIAO_USB_H / 2          # メスの下面 = XIAO の基板の上面
        u = self.r.usb_shell()
        zc = z["usb_center"]
        board = rbox(b, z["pcb_top"], z["pcb_top"] + board_t)
        comps = box(u[2], b[1], z["pcb_top"] + board_t, b[2], b[3], z["xiao_top"])
        shell = box(u[0], u[1], zc - s.XIAO_USB_H / 2, u[2], u[3], zc + s.XIAO_USB_H / 2)
        pw, ph = s.USB_PLUG_SHELL
        m = 0.05                                            # プラグの金属とメスの内側の隙
        cavity = box(u[0] - 1, u[1] + (s.XIAO_USB_W - pw) / 2 - m, zc - ph / 2 - m,
                     u[0] + self.c.USB_PLUG_INSERT + 0.2, u[3] - (s.XIAO_USB_W - pw) / 2 + m,
                     zc + ph / 2 + m)
        return fuse([board, comps, shell - cavity])

    def usb_plug(self):
        s, c = self.s, self.c
        u = self.r.usb_shell()
        y, zc = self.r.s.XIAO_AT[1], self.z["usb_center"]
        pw, ph = s.USB_PLUG_SHELL
        x_face = u[0] - s.USB_SHELL_EXPOSED                 # 樹脂の先端
        metal = box(x_face, y - pw / 2, zc - ph / 2, u[0] + c.USB_PLUG_INSERT, y + pw / 2, zc + ph / 2)
        body = box(x_face - c.USB_PLUG_BODY_L, y - s.USB_PLUG_BODY_W / 2, zc - s.USB_PLUG_BODY_H / 2,
                   x_face, y + s.USB_PLUG_BODY_W / 2, zc + s.USB_PLUG_BODY_H / 2)
        return fuse([metal, body])

    def holder(self):
        z = self.z
        (cx, cy), _ = self.r.cell()
        return rbox(self.r.holder_body(), z["pcb_top"], z["holder_top"]) \
            - cyl(cx, cy, z["pcb_top"] + self.c.CELL_Z_IN_HOLDER, z["holder_top"] + 1, self.s.CELL_D)

    def cell(self):
        (cx, cy), _ = self.r.cell()
        z0 = self.z["pcb_top"] + self.c.CELL_Z_IN_HOLDER
        return cyl(cx, cy, z0, z0 + self.s.CELL_T, self.c.CELL_REAL_D)

    def psw(self, trimmed=True, lever=None, envelope=True):
        """電源スイッチ SS-12D00G3（板の SW_PWR の位置・表）を**1 つの立体**で: 本体（公差の最大。
        基板の上面から。爪の出 PSW_TAB の隙間も詰めて包む）＋ レバー（動く範囲・先は公差の最高）＋
        足 3 本（**板のパッドの穴の位置**に、断面 PSW_PIN＋公差。先は切った長さ PSW_PIN_TRIM、
        trimmed=False なら切らない長さ〔図の最長〕）。lever = +1 / −1 ならレバーをその端だけに置く（絵用）。
        envelope=False なら高さを名目の値で（絵用。検査は包絡）。"""
        s, z = self.s, self.z
        top = z["psw_top"] + (s.PSW_H_TOL if envelope else 0.0)
        tip = self.r.psw_tip_range()[2 if envelope else 1]
        holes = [p for p in self.geo["pads"] if p["ref"] == "SW_PWR" and p["drill"] > 0]
        assert len(holes) == 3, len(holes)                 # lib/cckb.pretty/SW_SS-12D00G3
        end = z["psw_pin_end"] if trimmed else z["psw_seat"] - (s.PSW_PIN_L + s.PSW_PIN_TOL)
        px, py = (v + s.PSW_LEVER_TOL for v in s.PSW_PIN)
        pins = [box(p["x"] - px / 2, p["y"] - py / 2, end, p["x"] + px / 2, p["y"] + py / 2,
                    z["pcb_top"] + 0.01) for p in holes]
        return fuse([rbox(self.r.psw_body(), z["pcb_top"], top),
                     rbox(self.r.psw_lever_range() if lever is None else self.r.psw_lever(lever),
                          top - 0.01, tip)] + pins)

    def key_mounts(self):
        return [m for m in self.i.mounts() if not self.i.in_corner(m)]

    def nuts(self):
        s, z = self.s, self.z
        return [hex_prism(x, y, s.NUT_AF, z["pcb_top"], z["pcb_top"] + s.NUT_T)
                - cyl(x, y, z["pcb_top"] - 1, z["pcb_top"] + s.NUT_T + 1, self.c.SCREW_D)
                for x, y in self.key_mounts()]

    def screw_up(self, x, y, head_z):
        """下から入れる皿ネジ（頭の面 = head_z、先へ +z）。"""
        s, c = self.s, self.c
        return fuse([cone(x, y, head_z, head_z + s.SCREW_HEAD_H, c.SCREW_HEAD_D, c.SCREW_D),
                     cyl(x, y, head_z + s.SCREW_HEAD_H - 0.01, head_z + s.SCREW_L, c.SCREW_D)])

    def screws(self):
        return [self.screw_up(x, y, self.z["screw_head"]) for x, y in self.i.mounts()]

    def screw_lid(self):
        s, c = self.s, self.c
        (x, y), _ = self.i.lid_pillar()
        top = self.z["rim"]
        return fuse([cone(x, y, top - s.SCREW_HEAD_H, top, c.SCREW_D, c.SCREW_HEAD_D),
                     cyl(x, y, top - s.SCREW_L, top - s.SCREW_HEAD_H + 0.01, c.SCREW_D)])

    def inserts(self):
        c, z = self.c, self.z
        (px, py), _ = self.i.lid_pillar()
        top = self.case.pillar_top()
        mx, my = self.case.left_lid_mount()
        tube = lambda x, y, z0: (cyl(x, y, z0, z0 + c.INSERT_L, c.INSERT_OD)  # noqa: E731
                                 - cyl(x, y, z0 - 1, z0 + c.INSERT_L + 1, c.SCREW_D))
        return [tube(px, py, top - c.INSERT_L), tube(mx, my, z["pcb_top"])]

    def pads(self):
        s = self.s
        z0 = s.ANTISLIP_RECESS - s.ANTISLIP_SHEET_T
        return [rbox(r, z0, s.ANTISLIP_RECESS) for r in self.case.antislip_pads()]

    def desk(self):
        s = self.s
        o = self.i.case_outer
        z0 = s.ANTISLIP_RECESS - s.ANTISLIP_SHEET_T
        return box(o[0] - 60, o[1] - 60, z0 - 5, o[2] + 60, o[3] + 60, z0)

    # --- 全部 -----------------------------------------------------------------
    def groups(self, pressed=False, printed=None):
        """名前 → 立体（多数の同じ物は Compound）。"""
        g = dict(printed or self.printed())
        g.update(self.plates())
        g["pcb"] = self.pcb()
        g["switches"] = Compound(self.switch_solids(pressed))
        g["stabs"] = Compound(self.stab_solids(pressed))
        g["bottom_parts"] = Compound(self.bottom_parts())
        g["xiao"] = self.xiao()
        g["holder"] = self.holder()
        g["cell"] = self.cell()
        g["psw"] = self.psw()
        g["nuts"] = Compound(self.nuts())
        g["screws"] = Compound(self.screws())
        g["screw_lid"] = self.screw_lid()
        g["inserts"] = Compound(self.inserts())
        g["keycaps"] = Compound(self.keycap_solids(pressed))
        g["pads"] = Compound(self.pads())
        g["usb_plug"] = self.usb_plug()
        g["desk"] = self.desk()
        return g


# 基板と一緒に上から落とす物（はんだ付け・ナットを置いた状態。キャップはまだ）
BOARD_SET = ("pcb", "plate_L", "plate_R", "plate_frames", "switches", "stabs", "bottom_parts", "xiao", "holder",
             "cell", "psw", "nuts")

# どうやって入れるか（据わった位置から外への平行移動）。検査は sweep でたどる
INSERT_PATH = {
    "board": (0, 0, 30),              # 基板＋部品（＋プレートを使うならプレート）は上から落とす（トレイだけ置いた状態）
    "lid_L": (0, 0, 30),              # H3 を下へ抜いてから真上へ
    "lid_R": (0, 0, 30),              # ネジごと真上へ（ネジはふたに捕まっている）
    "cell": (0, 0, 30),               # 右のふたを外して真上へ（実物は＋のクリップの下から斜めに）
    "usb_plug": (-30, 0, 0),          # 左へ抜く
    "screws": (0, 0, -30),            # 下へ抜く（ドライバーも下から）
    "keycaps": (0, 0, 30),
}


def path_problems(asm, g):
    """入れる経路（INSERT_PATH）を sweep でたどり、ぶつかる相手を返す {経路: {相手: 体積}}。"""
    out = {}

    def check(name, moving, others):
        sw = {name: Compound([sweep(m, INSERT_PATH[name.split("+")[0]]) for m in moving])}
        bad = interference(sw, {k: g[k] for k in others})
        if bad:
            out[name] = {b: v for (_, b), v in bad.items()}

    board = [s for k in BOARD_SET if k in g for s in solids_of(g[k])]   # プレートは使うときだけ g にある
    check("board", board, ["tray_L", "tray_R"])
    everything = [k for k in g if k != "desk"]
    rest = lambda *ex: [k for k in everything if k not in ex]  # noqa: E731
    check("lid_L", solids_of(g["lid_L"]) + [solids_of(g["inserts"])[1]],
          rest("lid_L", "inserts", "screws", "usb_plug"))
    check("lid_R", solids_of(g["lid_R"]) + solids_of(g["screw_lid"]),
          rest("lid_R", "screw_lid", "inserts") + ["desk"])
    check("cell", solids_of(g["cell"]), rest("cell", "lid_R", "screw_lid"))
    check("usb_plug", solids_of(g["usb_plug"]), rest("usb_plug") + ["desk"])
    # 下からのネジ: ネジと、その下のドライバーの軸
    head = asm.z["screw_head"]
    drv = [cyl(x, y, head - 40, head, asm.c.DRIVER_D) for x, y in asm.i.mounts()]
    check("screws", solids_of(g["screws"]) + drv, rest("screws", "nuts", "inserts"))
    check("keycaps", solids_of(g["keycaps"]), rest("keycaps", "switches"))
    return out


def expected_overlaps_ok(asm, g):
    """EXPECTED の組の重なりが、**理由どおりの量だけ**か（見ない組の代わりの検査）。"""
    c = asm.c
    bad = []
    ring = lambda d0, d1, h: math.pi / 4 * (d0 * d0 - d1 * d1) * h  # noqa: E731
    lim = {("inserts", "tray_R"): ring(c.INSERT_OD, c.INSERT_HOLE_D, c.INSERT_L),
           ("inserts", "lid_L"): ring(c.INSERT_OD, c.INSERT_HOLE_D, c.INSERT_L),
           ("screw_lid", "lid_R"): ring(c.SCREW_D, c.CAPTIVE_HOLE_D, c.CAPTIVE_WEB_T)}
    for pair in EXPECTED:
        v = interference({pair[0]: g[pair[0]]}, {pair[1]: g[pair[1]]}).get(pair, 0.0)
        if not 0 < v <= lim[pair] * 1.02 + 1e-3:
            bad.append(f"{pair}: 重なり {v:.3f} mm3（理由の量 {lim[pair]:.3f}）")
    return bad


# ---------------------------------------------------------------------------
# 断面の絵・分解図
# ---------------------------------------------------------------------------

COLORS = {"tray_L": "#9fb6d4", "tray_R": "#88a6cc", "lid_L": "#f0b27a", "lid_R": "#eb984e",
          "plate_L": "#bbbbbb", "plate_R": "#a9a9a9", "plate_frames": "#7fb3d5", "pcb": "#27ae60", "switches": "#555555",
          "stabs": "#8e44ad", "bottom_parts": "#1e8449", "xiao": "#2c3e50", "holder": "#7f8c8d",
          "cell": "#d4ac0d", "psw": "#c0392b", "nuts": "#34495e", "screws": "#17202a",
          "screw_lid": "#17202a", "inserts": "#b7950b", "keycaps": "#aed6f1", "pads": "#e74c3c",
          "usb_plug": "#5d6d7e", "desk": "#eeeeee"}


def section_faces(part, plane):
    """B-rep の断面（平面との共通部分の面）を三角形 [(横, z) × 3] で返す。"""
    from build123d import Face, Plane

    axis, val = plane
    if axis == "x":
        pl = Plane(origin=(val, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    else:
        pl = Plane(origin=(0, val, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    big = pl * Face.make_rect(1000, 1000)
    h = 1 if axis == "x" else 0
    tris = []
    for s in solids_of(part):
        c = s & big
        if c is None:
            continue
        for f in c.faces():
            verts, idx = f.tessellate(0.01, 0.1)
            for t in idx:
                tris.append([(tuple(verts[k])[h], verts[k].Z) for k in t])
    return tris


def section_png(groups, out, plane, span, title):
    """断面の絵（B-rep を平面で切った面を塗る）。plane = ("x"|"y", 値)。span = (横の最小, 最大, z の最小, 最大)。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "sans-serif"]
    from matplotlib.patches import Patch

    axis, val = plane
    fig, ax = plt.subplots(figsize=(12, 5), dpi=170)
    seen = []
    for name, part in groups.items():
        tris = section_faces(part, plane)
        tris = [t for t in tris if any(span[0] - 5 <= p[0] <= span[1] + 5 for p in t)]
        if not tris:
            continue
        ax.add_collection(PolyCollection(tris, facecolors=COLORS.get(name, "#cccccc"),
                                         edgecolors=COLORS.get(name, "#cccccc"), linewidths=0.2))
        seen.append(name)
    ax.set_xlim(span[0], span[1])
    ax.set_ylim(span[2], span[3])
    ax.set_aspect("equal")
    ax.grid(True, linewidth=0.3, alpha=0.4)
    ax.set_xlabel(("y" if axis == "x" else "x") + " [mm]")
    ax.set_ylabel("z [mm]")
    ax.set_title(f"{title}   ({axis} = {val:.2f})", fontsize=9)
    ax.legend(handles=[Patch(color=COLORS.get(n, "#ccc"), label=n) for n in seen],
              fontsize=6, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return Path(out)


def exploded_png(meshes, out, lift):
    """分解図（部品ごとに z を持ち上げて、画家のアルゴリズムで描く）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import trimesh
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = plt.figure(figsize=(16, 10), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    elev, azim = 24, -62
    e, a = np.radians(elev), np.radians(azim)
    view = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    tris, cols = [], []
    for name, m in meshes.items():
        v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=4.0)
        t = v[f].copy()
        t[:, :, 2] += lift.get(name, 0.0)
        tris.append(t)
        cols += [COLORS.get(name, "#cccccc")] * len(t)
    tris = np.concatenate(tris)
    order = np.argsort(tris.mean(axis=1) @ view)
    ax.add_collection3d(Poly3DCollection(tris[order], facecolors=np.array(cols)[order],
                                         edgecolor="#333333", linewidths=0.02))
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(hi - lo)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return Path(out)


# ---------------------------------------------------------------------------
# 印刷する部品の検査（大きさ・肉厚・継ぎ目・留め方・指）
# ---------------------------------------------------------------------------

def print_sizes(parts, limit):
    """印刷の向きの平面の大きさ {名前: (x, y, 入るか)}。"""
    from case import print_pose

    out = {}
    for name, part in parts.items():
        bb = print_pose(name, part).bounding_box()
        out[name] = (bb.size.X, bb.size.Y, max(bb.size.X, bb.size.Y) <= limit + 1e-9)
    return out


def wall_probes(asm):
    """名前を付けた肉厚の測り所 [(名前, 部品, 起点, 向き, 下限, 理由)]。最初に通る材料の長さを測る。"""
    s, c, z, i, cs = asm.s, asm.c, asm.z, asm.i, asm.case
    o = i.case_outer
    m0 = i.mounts()[0]
    rb = s.MOUNT_BOSS_D / 2
    (px, py), _ = i.lid_pillar()
    mx, my = cs.left_lid_mount()
    usb = cs.usb_opening()
    pad = cs.antislip_pads()[0]
    need = 1.2
    slot = cs.psw_slot()
    mark = cs.psw_mark().bounding_box()
    return [
        ("床", "tray_L", (-60.3, 30.3, -5), (0, 0, 1), need, "0.4×3"),
        ("床（滑り止めのくぼみ）", "tray_L", ((pad[0] + pad[2]) / 2, (pad[1] + pad[3]) / 2, -5), (0, 0, 1),
         need, "O6: くぼみ 0.4 を引いて 1.2"),
        ("左の壁", "tray_L", (o[0] - 5, 10.3, 6.0), (1, 0, 0), need, "0.4×3"),
        ("奥の壁", "tray_L", (-60.3, o[3] + 5, 6.0), (0, -1, 0), need, ""),
        ("手前の壁", "tray_L", (-60.3, o[1] - 5, 6.0), (0, 1, 0), need, ""),
        ("USB の口の横の壁", "tray_L", (o[0] - 5, usb[0] - 1.0, 8.0), (1, 0, 0), need, ""),
        ("USB の口の下の壁", "tray_L", (o[0] - 5, s.XIAO_AT[1], usb[2] - 1.0), (1, 0, 0), need, ""),
        ("取付のボスの肉", "tray_L", (m0[0] - rb - 0.5, m0[1], (z["floor_top"] + z["pcb_bottom"]) / 2),
         (1, 0, 0), need, "穴 2.4・ボス 5.6"),
        ("右の壁", "tray_R", (o[2] + 5, 10.3, 6.0), (-1, 0, 0), need, ""),
        ("ふたの柱の肉（インサート）", "tray_R", (px - 4, py, cs.pillar_top() - 1.0), (1, 0, 0),
         (s.LID_PILLAR_D - c.INSERT_HOLE_D) / 2, "spec.LID_PILLAR_D（インサート 3.2＋肉 1.0）の決め方"),
        ("左のふたの天板", "lid_L", (-130.3, -40.3, 20), (0, 0, -1), need, "LID_T"),
        ("左のふたの垂れ壁", "lid_L", (-110, -40.3, 7.0), (-1, 0, 0), need, "LID_T"),
        ("左のふたのボスの肉（奥）", "lid_L", (mx, -20, 7.0), (0, -1, 0), need, "LID_BOSS_WEB"),
        ("左のふたのボスの肉（左）", "lid_L", (-126, my, 7.0), (1, 0, 0), need, "LID_BOSS_WEB"),
        ("USB の舌", "lid_L", (o[0] - 5, s.XIAO_AT[1], (usb[3] + z["lid_bottom"]) / 2), (1, 0, 0), need, ""),
        ("右のふたの天板", "lid_R", (120.3, -40.3, 20), (0, 0, -1), need, "LID_T"),
        ("右のふたの垂れ壁（左）", "lid_R", (90, -40.3, 7.0), (1, 0, 0), need, "LID_T"),
        ("右のふたの垂れ壁（奥）", "lid_R", (110.3, -20, 7.0), (0, -1, 0), need, "LID_T"),
        ("レバーの穴と外面の間", "lid_R", (o[2] + 5, (slot[1] + slot[3]) / 2, (z["lid_bottom"] + z["rim"]) / 2),
         (-1, 0, 0), need, "穴を右の縁から離す（spec.PSW_AT）"),
        ("入の刻印の下", "lid_R", (mark.center().X, (slot[1] + slot[3]) / 2 + 1.0, 20), (0, 0, -1),
         s.LID_T - asm.c.PSW_MARK_DEPTH, "**わざと薄い**（天板 1.2 − 刻印 0.4。天板の上の面の飾り）"),
        ("ふたのボスの肉", "lid_R", (px - 4, py, cs.pillar_top() + 0.8), (1, 0, 0), need, ""),
        ("ネジを捕まえる膜", "lid_R", (px + (c.CAPTIVE_HOLE_D / 2 + 0.2), py, 20), (0, 0, -1),
         c.CAPTIVE_WEB_T, "**わざと薄い**（ネジがねじ切って通る膜・0.2 層 × 2）"),
    ]


def measure_probes(asm, meshes):
    """wall_probes を測る → [(名前, 部品, 測った厚さ, 下限, 理由)]。材料に当たらなければ 0。"""
    out = []
    for name, part, org, d, need, why in wall_probes(asm):
        runs = material_runs(meshes[part], org, d)
        t = runs[0][1] - runs[0][0] if runs else 0.0
        out.append((name, part, t, need, why))
    return out


def keycap_probes(asm):
    """キーキャップ（1u・局所座標）の肉: 天板・スカート・筒の腕の先（十字の穴の腕の先と筒の外の間）・つばの窪みの上の天板。"""
    c, s = asm.c, asm.s
    m = mesh_of(KC.keycap(1.0, s, asm.i.sw, c))
    d = UNIT / 2 - s.KEYCAP_GAP
    r0, r1 = c.KEYCAP_COLLAR_RELIEF
    res = [("キャップの天板", material_runs(m, (3.6, 5.5, 10), (0, 0, -1)), s.KEYCAP_TOP_T),
           ("キャップのスカート", material_runs(m, (d + 3, 0.3, -0.5), (-1, 0, 0)), c.KEYCAP_SKIRT_T),
           # 腕の先の肉は 0.675（0.4 ノズル 2 本より薄い）。下限は「0.4 未満は無い」（case-and-print.md）。刷れるかは coupon_stem
           ("キャップの筒の腕の先", material_runs(m, (5.0, 0.0, -1.5), (-1, 0, 0)), 0.4),
           ("つばの窪みの上の天板", material_runs(m, ((r0 + r1) / 4, 0.3, 10), (0, 0, -1)),
            s.KEYCAP_TOP_T - KC.collar_relief_depth(s, c))]
    return [(n, "keycap_1u", r[0][1] - r[0][0] if r else 0.0, need, "") for n, r, need in res]


def z_scan(mesh, need, step=0.7, skip=()):
    """上から縦に刺した線の材料の長さが need 未満の所 [(x, y, 長さ)]。skip: [(x0,y0,x1,y1)] は見ない。"""
    import numpy as np

    lo, hi = mesh.bounds
    xs = np.arange(lo[0] + 0.137, hi[0], step)
    ys = np.arange(lo[1] + 0.113, hi[1], step)
    pts = [(x, y) for x in xs for y in ys
           if not any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in skip)]
    if not pts:
        return []
    o = np.array([(x, y, hi[2] + 5) for x, y in pts])
    d = np.tile([0.0, 0.0, -1.0], (len(o), 1))
    locs, idx, _ = mesh.ray.intersects_location(o, d, multiple_hits=True)
    hits = {}
    for p, k in zip(locs, idx):
        hits.setdefault(int(k), []).append(round(float(o[k][2] - p[2]), 5))
    thin = []
    for k, ts in hits.items():
        ts = sorted(set(ts))
        for a in range(0, len(ts) - 1, 2):
            if ts[a + 1] - ts[a] < need - 1e-6:
                thin.append((pts[k][0], pts[k][1], ts[a + 1] - ts[a]))
    return thin


def z_scan_skips(asm, name):
    """縦の走査で**わざと薄い所**（名前つき）。ここに無い薄い所は検査が落とす。"""
    c = asm.c
    (px, py), _ = asm.i.lid_pillar()
    r = c.SCREW_HEAD_D / 2 + c.SEAT_CLEAR + 0.2
    m = asm.case.psw_mark().bounding_box()
    # 床の止まり穴（わざと 0.8。下限は z_problems の「床の穴の底の肉 0.8」と test_the_floor_under_the_pockets_is_0_8）
    pockets = []
    for p in asm.i.floor_pockets():
        b = I.rect(*p["pos"], p["d"], p["d"]) if "d" in p else p["box"]
        pockets.append(I.grow(b, 0.05))
    return {"lid_R": [(px - r, py - r, px + r, py + r),                   # 捕まえる膜
                      (m.min.X - 0.2, m.min.Y - 0.2, m.max.X + 0.2, m.max.Y + 0.2)],   # 入の刻印
            "tray_L": pockets, "tray_R": pockets,
            }.get(name, [])


def seam_problems(asm, halves):
    """継ぎ目が柱・ボスを切っていないか: 各柱の円柱が**どちらか片方に丸ごと**入っているか。"""
    s, z = asm.s, asm.z
    posts = [(p, s.MOUNT_BOSS_D) for p in asm.i.mounts()] + [(p, s.SUPPORT_D) for p in s.SUPPORTS]
    posts.append((s.LID_PILLAR_AT, s.LID_PILLAR_D))
    bad = []
    for (x, y), d in posts:
        probe = cyl(x, y, z["floor_top"] + 0.2, z["pcb_bottom"] - 0.2, d - 0.1)
        vs = [common_volume(probe, h) for h in halves.values()]
        if sum(v > 1e-6 for v in vs) != 1:
            bad.append(((x, y), [round(v, 3) for v in vs]))
    return bad


def retention_problems(asm, g):
    """留まるか（外れる向きに少し動かすと、留める物に当たるか・ネジがかかっているか）。"""
    s, c, z = asm.s, asm.c, asm.z
    bad = []
    cell_up = moved(g["cell"], (0, 0, s.CELL_T / 2))
    if common_volume(cell_up, g["lid_R"]) <= 1e-3:
        bad.append("電池が半分（CELL_T/2）浮いてもふたに当たらない")
    if common_volume(moved(g["lid_R"], (0, 0, 0.5)), g["screw_lid"]) <= 1e-3:
        bad.append("右のふたを 0.5 持ち上げてもネジの頭に当たらない")
    # ねじ込みの長さ（M2 のピッチ 0.4 で 3 山 = 1.2 以上）
    tip = z["screw_head"] + s.SCREW_L
    if tip < z["pcb_top"] + s.NUT_T:
        bad.append(f"キーの下のネジの先 {tip:.2f} がナットの上面に届かない")
    if tip - z["pcb_top"] < 1.2:
        bad.append("H3 のネジがインサートに 1.2 かからない")
    lid_tip = z["rim"] - s.SCREW_L
    if asm.case.pillar_top() - max(lid_tip, asm.case.pillar_top() - c.INSERT_L) < 1.2:
        bad.append("右のふたのネジがインサートに 1.2 かからない")
    return bad


def nail_problems(asm, g):
    """電源スイッチのレバーに上から爪がかかるか・鞄の中で出ないか。

    - レバーの先（名目）がふたの上面より下（出ない）
    - レバーが両端のどちらにあっても、押し戻す側（端の外）のふたの穴に爪（厚さ NAIL_T の箱・幅はレバー）が
      上から入り、レバーの先から PSW_NAIL_REACH 下まで届く（ふた・トレイ・基板の物に当たらない）
    返り値は問題の一覧。公差の最高でのレバーの先の出は問題に数えず、呼ぶ側が別に見る（psw_tip_margin）。
    """
    c, z = asm.c, asm.z
    tip = asm.r.psw_tip_range()[1]
    bad = []
    if tip >= z["rim"]:
        bad.append(f"レバーの先（名目 {tip:.2f}）がふたの上面 {z['rim']:.2f} より下にない")
    for pos in (-1, 1):
        lv = asm.r.psw_lever(pos)
        y0, y1 = (lv[3], lv[3] + c.NAIL_T) if pos > 0 else (lv[1] - c.NAIL_T, lv[1])
        nail = box(lv[0], y0, tip - c.PSW_NAIL_REACH, lv[2], y1, z["rim"] + 5)
        for name in ("lid_R", "tray_R", "psw"):
            v = common_volume(nail, g[name])
            if v > 1e-3:
                bad.append(f"レバーが {'奥' if pos > 0 else '手前'} の端のとき、爪が {name} に当たる（{v:.2f} mm3）")
    return bad


# ふたとトレイの隙を測るときに、規定の隙から引く量（面どうしが隙 0 で接するのと、隙が規定どおりあるのを分ける）
FIT_EPS = 0.01


def lid_fit_problems(asm, g, need=None):
    """ふたとトレイの**接する面の隙**が、水平の 4 方向とも need（既定 FIT/2 = 片側）以上か。

    ふたを ±x・±y へ need − FIT_EPS 動かして、トレイと重なる向きを返す [(ふた, 向き, 相手, 体積)]。
    干渉の検査（interference）は重なりだけを数えるので、面が隙 0 で接していても 0 になる
    （4 回目の監査 E 重要 1: 垂れ壁の端がトレイの壁の内面に隙 0）。これは**残っている隙**を見る。
    """
    need = asm.c.FIT / 2 if need is None else need
    d = need - FIT_EPS
    trays = {k: g[k] for k in ("tray_L", "tray_R")}
    bad = []
    for lid in ("lid_L", "lid_R"):
        for name, v in (("+x", (d, 0, 0)), ("-x", (-d, 0, 0)), ("+y", (0, d, 0)), ("-y", (0, -d, 0))):
            hit = interference({lid: moved(g[lid], v)}, trays)
            bad += [(lid, name, b, round(vol, 3)) for (_, b), vol in hit.items()]
    return bad


def psw_tip_margin(asm):
    """レバーの先とふたの上面の差 (公差の最高で, 名目で, 最低で)。正ならふたの上面より下。"""
    lo, tip, hi = asm.r.psw_tip_range()
    rim = asm.z["rim"]
    return (rim - hi, rim - tip, rim - lo)


# プレートが無いとナットの回り止めが無い（決定記録 2026-09-26-plateless・open-gaps P15）。締める・緩めるときは上から
# ナット回しかピンセットで押さえる。そのために、ナットの外接円の外に残す平面の空き（スイッチの胴・スタビの箱まで）
# の下限。ピンセットの先（厚さ約 0.5〜1.0）が入る目安（道具は決めていない。手順書 手順 8）
NUT_HOLD_CLEAR = 1.0


def nut_access(asm):
    """キーの下のナット 9 個それぞれの、中心から胴（スイッチの開口の角）・つば（SW_FLANGE 角）・スタビの箱までの
    平面の距離 [(取付, 胴, つば, スタビ)]。つばは基板の上 2.2〜（ナットの上面 1.6 より上）。"""
    def gap(p, r):
        return math.hypot(max(r[0] - p[0], 0, p[0] - r[2]), max(r[1] - p[1], 0, p[1] - r[3]))
    bodies = asm.i.switch_bodies()
    flanges = [I.rect(x, y, asm.c.SW_FLANGE, asm.c.SW_FLANGE) for x, y in asm.i.positions]
    stabs = []
    for h in asm.i.stab_housings():
        xs, ys = [q[0] for q in h], [q[1] for q in h]
        stabs.append((min(xs), min(ys), max(xs), max(ys)))
    return [(m, min(gap(m, r) for r in bodies), min(gap(m, r) for r in flanges), min(gap(m, r) for r in stabs))
            for m in asm.key_mounts()]


def nut_access_problems(asm):
    """上からナットを押さえる道具が入らない取付（胴・スタビまでが外接円 ＋ NUT_HOLD_CLEAR 未満）。"""
    need = asm.s.NUT_AF / math.sqrt(3) + NUT_HOLD_CLEAR
    return [(m, round(b, 2), round(st, 2)) for m, b, _, st in nut_access(asm) if min(b, st) < need]


def pad_problems(asm):
    """滑り止めのくぼみとネジの座ぐりの**面の取り合い**（体積では見えない。矩形と円で数える）。"""
    s, c = asm.s, asm.c
    r = c.SCREW_HEAD_D / 2 + c.SEAT_CLEAR
    return [(p, m) for p in asm.case.antislip_pads() for m in asm.i.mounts()
            if I.circle_rect_gap(m, r, p) < c.ANTISLIP_INSET]


# 滑り止めの島（上面 island_top 1.6）と、基板の裏に出る物の平面の隙の下限。島の上面は足の先の最悪
# （1.34）より高く、裏の部品の包絡の下面（1.65）・電源スイッチの切った足の先（2.0）に近いので、上に来てはいけない
ISLAND_CLEAR = 0.5


def island_problems(asm):
    """滑り止めの島（case.antislip_islands）の上に、基板の裏に出る物が無いか（平面で ISLAND_CLEAR 未満）。

    裏に出る物: スイッチの穴（足・突起。SW\\d+）と電源スイッチ（SW_PWR）のパッド、裏の表面実装のパッド、
    裏のコートヤード（取付の穴 H\\d+ は除く）、スタビのハウジング。**板の形（発注する板）から読む**。
    組み立ての干渉の検査は隙 0 で当たるかを見る。これは余裕を見る。
    """
    obs = []
    for p in asm.geo["pads"]:
        if re.fullmatch(r"SW\d+|SW_PWR", p["ref"]) or (p["back"] and p["drill"] == 0):
            obs.append((f"{p['ref']} のパッド", p["box"]))
    for f in asm.geo["footprints"]:
        if not re.fullmatch(r"H\d+", f["ref"]):
            obs += [(f"{f['ref']} の裏のコートヤード", cy) for cy in I.courtyard_parts(f, "back")]
    for k, h in enumerate(asm.i.stab_housings()):
        xs, ys = [q[0] for q in h], [q[1] for q in h]
        obs.append((f"スタビ {k}", (min(xs), min(ys), max(xs), max(ys))))
    bad = []
    for k, r in enumerate(asm.case.antislip_islands()):
        for name, b in obs:
            dx = max(b[0] - r[2], r[0] - b[2], 0.0)
            dy = max(b[1] - r[3], r[1] - b[3], 0.0)
            gap = math.hypot(dx, dy) if (dx > 0 or dy > 0) else -1.0
            if gap < ISLAND_CLEAR:
                bad.append((k, name, round(gap, 3)))
    return bad


# 床の止まり穴と、床から立つ柱・ボス・島の間に残す肉（interface.POCKET_WALL・線 1 本）。
# 穴が柱の根元を削らない・島の中に空洞を作らない
POCKET_WALL = I.POCKET_WALL


def pocket_problems(asm):
    """床の止まり穴（case.floor_pockets の元の interface.floor_pockets）と、床から立つ物（取付のボス・支えの柱・
    右のふたの柱）・滑り止めの島の平面の隙が POCKET_WALL 未満の組。[(穴, 相手, 隙)]。"""
    s = asm.s
    posts = [(f"ボス {m}", m, s.MOUNT_BOSS_D / 2) for m in asm.i.mounts()]
    posts += [(f"支え {p}", p, s.SUPPORT_D / 2) for p in s.SUPPORTS]
    posts.append(("ふたの柱", s.LID_PILLAR_AT, s.LID_PILLAR_D / 2))
    bad = []
    for p in asm.i.floor_pockets():
        name = f"{p['ref']} の {p['kind']}"
        if "d" in p:
            r = p["d"] / 2
            b = (p["pos"][0] - r, p["pos"][1] - r, p["pos"][0] + r, p["pos"][1] + r)
            gap_c = lambda c, rr: math.hypot(p["pos"][0] - c[0], p["pos"][1] - c[1]) - r - rr  # noqa: E731
        else:
            b = p["box"]
            gap_c = lambda c, rr: I.circle_rect_gap(c, rr, b)  # noqa: E731
        for pname, c, rr in posts:
            g = gap_c(c, rr)
            if g < POCKET_WALL:
                bad.append((name, pname, round(g, 3)))
        for k, isl in enumerate(asm.case.antislip_islands()):
            g = I.rect_gap(b, isl)
            if g < POCKET_WALL:
                bad.append((name, f"島 {k}", round(g, 3)))
    return bad


def render_all(asm, g, out):
    """断面と分解図を out/ に書く。返り値は書いた絵のパス。"""
    s, z = asm.s, asm.z
    mx, my = asm.case.left_lid_mount()
    (px, py), _ = asm.i.lid_pillar()
    back, front = s.CASE_SEAM
    m0 = asm.i.mounts()[0]
    pads = asm.case.antislip_pads()
    pad_x = (pads[0][0] + pads[0][2]) / 2
    pad_fr_y = (pads[3][1] + pads[3][3]) / 2
    zs = (-1.5, 16.0)
    key = next(pos for pos, k in zip(asm.i.positions, asm.i.keys) if k.w_u == 1.0 and abs(pos[1] - 19.05) < 0.1)
    space = next((pos, k) for pos, k in zip(asm.i.positions, asm.i.keys) if k.w_u == 2.25 and pos[1] < -30)
    pivot_x = space[0][0] - asm.i.sw.stab_offset_for(2.25)
    # 押し切った状態（キャップ・スイッチ・スタビだけ作り直す）。「押す」の付く絵はこれを切る
    gp = dict(g, switches=Compound(asm.switch_solids(True)), stabs=Compound(asm.stab_solids(True)),
              keycaps=Compound(asm.keycap_solids(True)))
    across = (space[0][0] - 17, space[0][0] + 17)
    shots = [
        ("section_keycap_socket", ("y", key[1]), (key[0] - 11, key[0] + 11),
         "キャップの受け口（y = キーの中心）: 筒・十字・静音のつば・天板の窪み・止まり穴"),
        ("section_keycap_socket_pressed", ("y", key[1]), (key[0] - 11, key[0] + 11),
         "キャップの受け口を押し切った所（y = キーの中心）: 天板の窪みと静音のつば"),
        ("section_stab_across", ("y", space[0][1]), across,
         "左のスペースのスタビを横に（y = キーの中心）: 両端の軸・キャップの台と十字の穴・箱・ねじ・止まり穴"),
        ("section_stab_across_pressed", ("y", space[0][1]), across,
         "同じ所を押し切った所: 台が箱の上面の口へ入る"),
        ("section_stab_pivot", ("x", pivot_x), (space[0][1] - 14, space[0][1] + 14),
         "左のスペースのスタビの支点（縦）: ボス・箱・肩・爪・ワイヤ・止まり穴"
         + ("・プレートの羽と枠" if asm.plate else "（プレート無し）")),
        ("section_left_corner_usb", ("y", s.XIAO_AT[1]), (-152, -108), "左の角: XIAO・USB-C のメスとプラグ・左のふた（舌）"),
        ("section_left_corner_h3", ("x", mx), (-53, -18), "左の角: H3 のネジ・インサート・ふたのボス"),
        ("section_right_corner_cell", ("y", py), (92, 150), "右の角: 電池・ホルダ・柱・捕まえたネジ"),
        ("section_right_corner_psw", ("x", s.PSW_AT[0]), (-53, -25), "右の角: 電源スイッチ（足・本体・レバー）とふたの穴"),
        ("section_psw_side", ("y", s.PSW_AT[1]), (110, 152), "右の角: ホルダの＋・電源スイッチ・ふたの穴と刻印"),
        ("section_seam_back", ("y", 30.3), (back - 20, back + 20), "継ぎ目（奥）: 床の段・支え"),
        ("section_seam_front", ("y", -30.3), (front - 20, front + 20), "継ぎ目（手前）"),
        ("section_seam_wall", ("x", (back + front) / 2), (-52, 52), "継ぎ目の段（y=0）を横から"),
        ("section_stab_space", ("y", -38.1), (-65, -25), "スタビのキー（左のスペース）: ハウジング・逃げ穴・床"),
        ("section_mount_h0", ("y", m0[1]), (m0[0] - 12, m0[0] + 12), "取付 H0: 皿ネジ・ボス・基板・ナット"
         + ("・プレートの六角の穴" if asm.plate else "（プレート無し: ナットの回り止めは上から押さえる）")),
        ("section_antislip_island", ("x", pad_x), (18, 52),
         "左奥の滑り止め: 床 1.2・くぼみの所だけ島（上面 1.6）・上下の段のスイッチの足"),
        ("section_antislip_island_front_right", ("y", pad_fr_y), (112, 150),
         "右手前の滑り止め: 島と電源スイッチ（島は電源スイッチの手前で止める）"),
    ]
    paths_ = []
    for name, plane, span, title in shots:
        sec = {k: v for k, v in (gp if name.endswith("_pressed") else g).items() if k != "desk"}
        paths_.append(section_png(sec, out / f"{name}.png", plane, (span[0], span[1], *zs), title))
    lift = {"tray_L": 0, "tray_R": 0, "pads": -10, "screws": -22, "pcb": 22, "bottom_parts": 22,
            "psw": 22, "xiao": 22, "holder": 22, "cell": 50, "switches": 36, "stabs": 36, "nuts": 36,
            "plate_L": 36, "plate_R": 36, "plate_frames": 36, "inserts": 70, "lid_L": 70, "lid_R": 70, "screw_lid": 86,
            "keycaps": 56, "usb_plug": 22}
    ex = {k: mesh_of(v) for k, v in g.items() if k in lift}
    paths_.append(exploded_png(ex, out / "assembly_exploded.png", lift))
    return paths_


def export_blend(g, out):
    """組み立てを build/cckb/assembly/*.stl ＋ style.json に書き、Blender で cckb.blend にする。

    **Blender は失敗しても 0 を返す**ので、出力の「OK <数>」とできたファイルで判定する。
    返り値は (.blend, 絵) のパス。Blender が無ければ None。
    """
    from foundry.verify import to_mesh

    d = out / "assembly"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    style = {}
    for name, part in g.items():
        if name == "desk":
            continue
        to_mesh(part, d / f"{name}.stl")
        style[name] = (COLORS.get(name, "#888888"), 0.55 if name.startswith("tray_") else 1.0)
    (d / "style.json").write_text(json.dumps(style))
    if not Path(paths.BLENDER).exists():
        return None
    r = subprocess.run([paths.BLENDER, "-b", "-P", str(HERE / "tools/blend_assembly.py")],
                       capture_output=True, text=True, timeout=900)
    ok = [line for line in r.stdout.splitlines() if line.startswith("OK ")]
    n = int(ok[-1].split()[1]) if ok else 0
    blend, png = d / "cckb.blend", d / "cckb_blender.png"
    assert n == len(style) and blend.exists() and png.exists(), r.stdout[-2000:] + r.stderr[-2000:]
    return blend, png


def main(plate=None):
    """plate: None なら spec.PLATE の形。spec と違う形（--plate / --no-plate）で組んだときは、絵を
    build/cckb/with_plate/（か without_plate/）に出し、Blender の模型は作らない（本番の模型を上書きしない）。"""
    import time

    t0 = time.time()
    geo = board_geometry()
    asm = Assembly(geo, plate=plate)
    g = asm.groups()
    out = asm.i.p.build
    default = asm.plate == bool(getattr(asm.s, "PLATE", True))
    if not default:
        out = out / ("with_plate" if asm.plate else "without_plate")
    out.mkdir(parents=True, exist_ok=True)
    print(f"プレート: {'あり' if asm.plate else '無し'}（spec.PLATE = {getattr(asm.s, 'PLATE', True)}）")
    print(f"組み立て {len(g)} 群・立体 {sum(len(solids_of(v)) for v in g.values())}  ({time.time() - t0:.0f}s)")
    sl, failed = [], []
    bad = interference(g, skip=set(EXPECTED) | {("pads", "desk")}, slivers=sl, failures=failed)
    print("干渉:", bad or "0", f"（丸めの削りかす {len(sl)} 件・計 {sum(sl):.4f} mm3 は 0 に数えた）")
    print("形状演算の失敗:", failed or "0")
    paths_bad = path_problems(asm, g)
    print("経路:", paths_bad or "0")
    overlaps_bad = expected_overlaps_ok(asm, g)
    print("設計どおりの重なり:", overlaps_bad or "OK")
    islands_bad = island_problems(asm)
    print("滑り止めの島の上:", islands_bad or "0")
    fit_bad = lid_fit_problems(asm, g)
    print("ふたとトレイの隙（片側 FIT/2）:", fit_bad or "OK")
    ng = bool(bad or failed or paths_bad or overlaps_bad or islands_bad or fit_bad)
    for p in render_all(asm, g, out):
        print("   ", p)
    if default:
        b = export_blend(g, out)
        print("Blender:", *(b or ["無い（BLENDER の場所: foundry/paths.py）"]))
    return asm, g, ng


if __name__ == "__main__":
    # NG を print だけにしない（CI・スクリプトから判定できるように。最終レビュー M5）
    #   --plate / --no-plate: spec.PLATE によらずプレートあり／無しで組む（戻すときの確かめ）
    flag = True if "--plate" in sys.argv[1:] else (False if "--no-plate" in sys.argv[1:] else None)
    sys.exit(1 if main(flag)[2] else 0)
