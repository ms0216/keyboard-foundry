"""CCKB の基板・プレート・ケースの境界を、spec.py の値から形にする。**寸法は持たない。**

図（tools/draw_interface.py）・取付位置の探索（tools/find_mounts.py）・検査
（tests/test_cckb_interface.py）・基板の次の段（pcb_extra.py）が同じ形を使う。
形を 2 か所で作るとずれる（HHKB でネジ位置をプレートとケースで別々に持ち食い違わせた）。

座標は CAD（キー領域の中心が原点・X 右・Y 奥・mm）。Z は机が 0。
KiCad の Python（3.9）からも読むので標準ライブラリだけ。
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundry.layout import UNIT, centered          # noqa: E402
from foundry.mech import CHOC_STAB_OUTLINE, STAB_KERF, switch_of  # noqa: E402
from foundry.project import load                    # noqa: E402


# ---------------------------------------------------------------------------
# 幾何の小道具（矩形は (x0, y0, x1, y1)）
# ---------------------------------------------------------------------------

def rect(cx, cy, w, h):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def rect_gap(a, b):
    """2 つの矩形の間の距離（重なっていれば負: 重なりの浅い方の深さ）。"""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def circle_rect_gap(c, r, box):
    """円 (中心 c・半径 r) と矩形の間の距離（重なりは負）。"""
    x, y = c
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    if dx == 0 and dy == 0:                      # 中心が矩形の中
        return -r - min(x - box[0], box[2] - x, y - box[1], box[3] - y)
    return math.hypot(dx, dy) - r


def inside(box, inner, margin=0.0):
    """inner が box の中に margin 以上離れて入っているか。"""
    return (inner[0] - box[0] >= margin - 1e-9 and inner[1] - box[1] >= margin - 1e-9
            and box[2] - inner[2] >= margin - 1e-9 and box[3] - inner[3] >= margin - 1e-9)


def poly_offset_axis(poly, d):
    """軸に平行な辺だけの単純多角形を d だけ外へ広げる（角は丸めない）。

    各辺を外向きの法線方向に d ずらし、隣どうしの交点を取る。plate.stab_cutout_face の
    `offset(kind=INTERSECTION)` と同じ結果（軸平行の辺なら一致する）。
    """
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n)) / 2
    s = 1.0 if area > 0 else -1.0                # 反時計回りなら外は進む向きの右
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if x1 == x2:
            nx = s * (-1.0 if y2 < y1 else 1.0)
            lines.append(("v", x1 + nx * d))
        elif y1 == y2:
            ny = s * (-1.0 if x2 > x1 else 1.0)
            lines.append(("h", y1 + ny * d))
        else:
            raise ValueError("軸に平行でない辺")
    out = []
    for i in range(n):
        a, b = lines[i - 1], lines[i]
        x = a[1] if a[0] == "v" else b[1]
        y = a[1] if a[0] == "h" else b[1]
        out.append((round(x, 6), round(y, 6)))
    return out


def point_in_poly(p, poly):
    x, y = p
    ins = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
            ins = not ins
    return ins


def seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                                                / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def circle_poly_gap(c, r, poly):
    """円と多角形の距離（重なりは負）。"""
    d = min(seg_dist(c, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
    return -d - r if point_in_poly(c, poly) else d - r


def poly_box(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def hex_r(af):
    """二面幅 af の正六角形の外接円の半径。"""
    return af / math.sqrt(3)


# ---------------------------------------------------------------------------
# 機種の形
# ---------------------------------------------------------------------------

class Interface:
    """spec.py から導いた形。**ここで新しい寸法を作らない**（割り算・足し算だけ）。"""

    def __init__(self, project=None):
        self.p = project or load("cckb")
        self.s = self.p.spec
        self.keys = self.p.keys()
        self.positions, (kw, kh) = centered(self.keys)
        self.kw, self.kh = kw, kh
        self.sw = switch_of(self.s)

    # --- 外形 -------------------------------------------------------------
    @property
    def key_area(self):
        return rect(0, 0, self.kw, self.kh)

    @property
    def wall_gap(self):
        """基板の外形とトレイの壁の内面の隙（片側）。**ケースの形はここからだけ読む**（裁定 R5）。"""
        return self.s.CASE_PCB_GAP

    @property
    def wall_inner(self):
        return grow(self.pcb, self.wall_gap)

    @property
    def case_outer(self):
        return grow(self.wall_inner, self.s.CASE_WALL)

    @property
    def pcb(self):
        return grow(self.key_area, self.s.PLATE_MARGIN_X - self.s.PCB_INSET_X)

    # --- 高さ -------------------------------------------------------------
    def z(self):
        s = self.s
        pcb_bot = s.CASE_FLOOR + s.UNDER_PCB
        top = pcb_bot + s.PCB_T
        plate_top = top + s.PLATE_TOP_ABOVE_PCB
        rim = top + s.RIM_ABOVE_PCB
        return dict(
            floor_top=s.CASE_FLOOR, pcb_bottom=pcb_bot, pcb_top=top,
            plate_bottom=plate_top - self.sw.plate_t, plate_top=plate_top,
            switch_top=top + s.SWITCH_TOP_ABOVE_PCB, stem_top=top + s.SWITCH_STEM_ABOVE_PCB,
            keycap_top=top + s.SWITCH_STEM_ABOVE_PCB + s.KEYCAP_TOP_T,
            keycap_bottomed=top + s.SWITCH_TOP_ABOVE_PCB + s.KEYCAP_TOP_T,
            rim=rim, lid_bottom=rim - s.LID_T,
            pin_tip=top - s.SWITCH_PIN_L,
            stab_bottom=plate_top - s.STAB_HOUSING_H,
            xiao_top=top + s.XIAO_H, holder_top=top + s.HOLDER_H,
            usb_center=top + s.XIAO_USB_Z,
            psw_bottom=pcb_bot - s.PSW_H)

    # --- キー ---------------------------------------------------------------
    def rows(self):
        """段 → [(位置, キー)]（上の段から 0）。"""
        out = {}
        for pos, k in zip(self.positions, self.keys):
            out.setdefault(round(k.y_mm / UNIT - 0.5), []).append((pos, k))
        return [sorted(out[r], key=lambda pk: pk[0][0]) for r in sorted(out)]

    def corners(self):
        """最下段の空いた角のセル（左・右）。配列から導く。"""
        bottom = self.rows()[-1]
        y = bottom[0][0][1]
        left = min(p[0] - k.w_mm / 2 for p, k in bottom)
        right = max(p[0] + k.w_mm / 2 for p, k in bottom)
        hx = self.kw / 2
        return dict(left=(-hx, y - UNIT / 2, left, y + UNIT / 2),
                    right=(right, y - UNIT / 2, hx, y + UNIT / 2))

    def switch_bodies(self):
        """基板の上のスイッチの胴（プレートの開口と同じ 13.8 角）。"""
        c = self.sw.cutout
        return [rect(x, y, c, c) for x, y in self.positions]

    def stab_pivots(self):
        out = []
        for (x, y), k in zip(self.positions, self.keys):
            s = self.sw.stab_offset_for(k.w_u)
            if s is not None:
                out += [(x - s, y, -1), (x + s, y, 1)]
        return out

    def _stab_poly(self, px, py, side, grow_by):
        pts = poly_offset_axis(list(CHOC_STAB_OUTLINE), grow_by) if grow_by else \
            list(CHOC_STAB_OUTLINE)
        return [(px + side * x, py + y) for x, y in pts]

    def stab_plate_openings(self):
        """プレートのスタビの開口（輪郭 ＋ STAB_KERF）。"""
        return [self._stab_poly(px, py, sd, STAB_KERF) for px, py, sd in self.stab_pivots()]

    def stab_reliefs(self):
        """基板の逃げ穴（輪郭 ＋ STAB_RELIEF_MARGIN）。**基板の次の段が Edge.Cuts に描く。**"""
        m = self.s.STAB_RELIEF_MARGIN
        return [self._stab_poly(px, py, sd, m) for px, py, sd in self.stab_pivots()]

    def stab_housings(self):
        """ハウジングの平面（spec.STAB_HOUSING・製造図の最大公差）。

        Keebio の輪郭の中に置く: 本体は輪郭の奥行の中央、突起は切り欠きの中央で
        切り欠きの奥端までを占めるとみなす（突起の長さは製造図に無い。長い側に取る）。
        """
        w, d, nw = self.s.STAB_HOUSING
        out = []
        ys = [y for _, y in CHOC_STAB_OUTLINE]
        y0, y_notch, y1 = min(ys), sorted(set(ys))[1], max(ys)
        dy = ((y_notch - y0) - d) / 2
        for px, py, sd in self.stab_pivots():
            body = [(-w / 2, y0 + dy), (w / 2, y0 + dy), (w / 2, y_notch - dy),
                    (nw / 2, y_notch - dy), (nw / 2, y1), (-nw / 2, y1),
                    (-nw / 2, y_notch - dy), (-w / 2, y_notch - dy)]
            out.append([(px + sd * x, py + y) for x, y in body])
        return out

    # --- 角の部品 -------------------------------------------------------------
    def usb_face_x(self):
        return self.case_outer[0] + self.s.USB_RECESS

    def xiao(self):
        x, y = self.s.XIAO_AT
        return rect(x, y, self.s.XIAO_L, self.s.XIAO_W)

    def xiao_pads_extent(self):
        """XIAO の表面実装パッドの並びの外形（長手はピンの範囲、幅方向に XIAO_PAD_EXT 出る）。"""
        b = self.xiao()
        x = self.s.XIAO_AT[0]
        h = self.s.XIAO_PIN_SPAN / 2 + self.s.XIAO_PAD_L / 2
        e = self.s.XIAO_PAD_EXT
        return (x - h, b[1] - e, x + h, b[3] + e)

    def usb_shell(self):
        """XIAO の USB-C メスの平面（口は −x）。"""
        b = self.xiao()
        y = self.s.XIAO_AT[1]
        return (b[0] - self.s.XIAO_USB_OVERHANG, y - self.s.XIAO_USB_W / 2,
                b[0] + self.s.XIAO_USB_D - self.s.XIAO_USB_OVERHANG, y + self.s.XIAO_USB_W / 2)

    def antenna_chip(self):
        """アンテナのチップ。USB と反対の端（+x）、幅方向は D0〜D6 の列の側（手前 −y）。"""
        b = self.xiao()
        a0, a1 = self.s.XIAO_ANT_FROM_EDGE
        w0, w1 = self.s.XIAO_ANT_SIDE
        y = self.s.XIAO_AT[1]
        return (b[2] - a1, y - w1, b[2] - a0, y - w0)

    def antenna_keepout(self):
        b = self.xiao()
        y = self.s.XIAO_AT[1]
        h = self.s.ANT_KEEPOUT_HALF_W
        return (b[2] - self.s.ANT_KEEPOUT_IN, y - h, b[2] + self.s.ANT_KEEPOUT_OUT, y + h)

    def holder_pads(self):
        x, y = self.s.HOLDER_AT
        pw, ph = self.s.HOLDER_PAD
        c = self.s.HOLDER_PAD_SPAN / 2 - pw / 2
        return [rect(x - c, y, pw, ph), rect(x + c, y, pw, ph)]

    def holder_body(self):
        x, y = self.s.HOLDER_AT
        return rect(x, y, *self.s.HOLDER_BODY)

    def cell(self):
        return (self.s.HOLDER_AT, self.s.CELL_D / 2)

    def psw_body(self):
        x, y = self.s.PSW_AT
        return rect(x, y, self.s.PSW_BODY[1], self.s.PSW_BODY[0])

    def psw_land(self):
        """ランド（縁に沿って PSW_LAND_L・端子は内側へ PSW_TERM_EXT、耳は外へ PSW_PAD_OUT）。"""
        b = self.psw_body()
        y = self.s.PSW_AT[1]
        return (b[0] - self.s.PSW_TERM_EXT, y - self.s.PSW_LAND_L / 2,
                b[2] + self.s.PSW_PAD_OUT, y + self.s.PSW_LAND_L / 2)

    def psw_knob(self):
        b = self.psw_body()
        y = self.s.PSW_AT[1]
        k = self.s.PSW_KNOB[0]
        return (b[2], y - k / 2 - self.s.PSW_TRAVEL / 2, b[2] + self.s.PSW_KNOB_L,
                y + k / 2 + self.s.PSW_TRAVEL / 2)

    def psw_pegs(self):
        x, y = self.s.PSW_AT
        h = self.s.PSW_PEG_PITCH / 2
        return [((x, y - h), self.s.PSW_PEG_HOLE / 2), ((x, y + h), self.s.PSW_PEG_HOLE / 2)]

    def lid_pillar(self):
        return (self.s.LID_PILLAR_AT, self.s.LID_PILLAR_D / 2)

    # --- 角のふた（上から見た形）----------------------------------------------
    def cover(self, side):
        """角のふたの天板。内側 2 辺はセルの境目から CASE_KEY_GAP 離し、外側は外面まで。"""
        c = self.corners()[side]
        o = self.case_outer
        g = self.s.CASE_KEY_GAP
        if side == "left":
            return (o[0], o[1], c[2] - g, c[3] - g)
        return (c[0] + g, o[1], o[2], c[3] - g)

    def cover_cavity(self, side):
        """ふたの下の空間（壁の内面と、ふたの内側の垂れ壁の内面で囲む）。

        左は奥の垂れ壁を持たない（XIAO 17.78 が入らない。プレートの開口の縁で止める）。
        """
        c = self.cover(side)
        w = self.wall_inner
        t = self.s.LID_T
        if side == "left":
            return (w[0], w[1], c[2] - t, c[3])
        return (c[0] + t, w[1], w[2], c[3] - t)

    # --- 取付 -------------------------------------------------------------
    def mounts(self):
        return list(self.s.MOUNTS["main"])

    def in_corner(self, p):
        return any(c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3]
                   for c in self.corners().values())

    # --- 印刷する部品の平面 ---------------------------------------------------
    def plate_pieces(self):
        """プレートの分割後の外接矩形（左・右）。"""
        xs = self.s.PLATE_SPLIT["main"]
        p = grow(self.key_area, self.s.PLATE_MARGIN_X)
        return dict(left=(p[0], p[1], max(xs), p[3]), right=(min(xs), p[1], p[2], p[3]))

    def plate_seam(self):
        """プレートの継ぎ目の折れ線（上から下へ）。段の中は縦、段の境目で横に渡る。"""
        xs = self.s.PLATE_SPLIT["main"]
        p = grow(self.key_area, self.s.PLATE_MARGIN_Y)
        ys = [self.kh / 2 - i * UNIT for i in range(len(xs) + 1)]
        ys[0], ys[-1] = p[3], p[1]
        pts = []
        for i, x in enumerate(xs):
            pts += [(x, ys[i]), (x, ys[i + 1])]
        return pts

    def case_pieces(self):
        """トレイの左右の外接矩形と、角のふた 2 つ。"""
        o = self.case_outer
        back, front = self.s.CASE_SEAM
        return dict(tray_left=(o[0], o[1], max(back, front), o[3]),
                    tray_right=(min(back, front), o[1], o[2], o[3]),
                    cover_left=self.cover("left"), cover_right=self.cover("right"))


def size(box):
    return (box[2] - box[0], box[3] - box[1])


# ---------------------------------------------------------------------------
# 取付位置の 5 条件（縁・キーとプレート開口・部品・コートヤード・配線の通り道）
# ---------------------------------------------------------------------------
# 基板の規則（foundry/pcb_rules.py の JLC の値）。穴 φ2.2（MountingHole_2.2mm_M2）
HOLE_D = 2.2
HOLE_CRTYD_R = 2.45          # KiCad の MountingHole_2.2mm_M2 の F.CrtYd（円）
EDGE_MIN = 1.0               # 穴の縁から外形まで（依頼の条件・pcb_rules.NPTH_EDGE_MIN と同じ）
COPPER_GAP = 0.3             # 穴と銅（パッド）の間（JLC の外形・穴と銅の規則）
TRACK_HALF = 0.1             # 配線 0.2 の半分（pcb_rules.TRACK_W）
BAND_HALF = 1.0              # 段の境目で列の配線が横に渡る帯の半幅


def corridors(ifc, geo):
    """これから引く行列の配線（設計書 §12）。線分 [(a, b), ...]（表裏とも）。

    **実際に板に置く線と同じ**（matrix_routes.plan。tools/route_pcb.py も同じ関数を通す）。
    段階 1 はカソードどうしを結ぶ直線を通り道にしていたが、その直線はスイッチのボスと
    中心穴を貫くので引けなかった（2026-09-24 基板の段で置き換えた）。
    """
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import matrix_routes

    m = matrix_routes.plan(ifc.p, geo["pads"])
    e, _ = matrix_routes.escape(ifc.p, geo["pads"], others=m)
    return [(a, b) for _, _, a, b in m + e]


def band_ys(ifc):
    """段の境目の y（4 本）。"""
    return [ifc.kh / 2 - i * UNIT for i in range(1, len(ifc.rows()))]


def mount_problems(ifc, geo, p, corner_ok=False, cache=None):
    """取付位置 p が満たさない条件の一覧（空なら全部満たす）。

    geo は tools/board_geometry.py が**生成した基板から**書き出したもの。取付穴そのもの
    （参照名 H*）は相手にしない。corner_ok: 角のふたを留める穴（プレートが無い所）。
    """
    import re
    s = ifc.s
    out = []
    r_hole = HOLE_D / 2
    r_nut = hex_r(s.NUT_AF)
    r_pocket = hex_r(s.MOUNT_POCKET_AF)
    r_boss = s.MOUNT_BOSS_D / 2
    # 1. 縁: 穴の縁から基板の外形まで
    e = ifc.pcb
    edge = min(p[0] - e[0], e[2] - p[0], p[1] - e[1], e[3] - p[1]) - r_hole
    if edge < EDGE_MIN - 1e-9:
        out.append(f"縁まで {edge:.2f}")
    # 2. キーとプレートの開口（ナットの穴のまわりに肉 MOUNT_POCKET_WEB を残す）
    in_corner = ifc.in_corner(p)
    if in_corner and not corner_ok:
        out.append("角（プレートが無い）")
    if not in_corner:
        need = r_pocket + s.MOUNT_POCKET_WEB
        for b in ifc.switch_bodies():
            if circle_rect_gap(p, need, b) < 0:
                out.append(f"スイッチの開口 {b[0]:.1f},{b[1]:.1f}")
        for poly in ifc.stab_plate_openings():
            if circle_poly_gap(p, need, poly) < 0:
                out.append("スタビの開口")
        pl = grow(ifc.key_area, s.PLATE_MARGIN_X)
        if min(p[0] - pl[0], pl[2] - p[0], p[1] - pl[1], pl[3] - p[1]) < need:
            out.append("プレートの外形")
        seam = ifc.plate_seam()
        if min(seg_dist(p, a, b) for a, b in zip(seam, seam[1:])) < need:
            out.append("プレートの継ぎ目")
    # 3. 部品: 上はナット（基板の上面）、下はトレイのボス。パッド・穴・スタビの逃げ・角の部品
    for pad in geo["pads"]:
        if re.fullmatch(r"H\d+", pad["ref"]):
            continue
        if (pad["front"] or pad["npth"]) and circle_rect_gap(p, r_nut, pad["box"]) < COPPER_GAP:
            out.append(f"上: {pad['ref']} のパッド")
        if (pad["back"] or pad["npth"]) and circle_rect_gap(p, r_boss, pad["box"]) < COPPER_GAP:
            out.append(f"下: {pad['ref']} のパッド")
        if circle_rect_gap(p, r_hole, pad["box"]) < COPPER_GAP:
            out.append(f"穴: {pad['ref']} のパッド")
    for poly in ifc.stab_reliefs():
        if circle_poly_gap(p, r_boss, poly) < COPPER_GAP:
            out.append("スタビの逃げ穴")
    for name, box in (("XIAO", ifc.xiao_pads_extent()), ("ホルダ", ifc.holder_body()),
                      ("電源スイッチ", ifc.psw_land())):
        if circle_rect_gap(p, max(r_boss, r_nut), box) < COPPER_GAP:
            out.append(name)
    for pad in ifc.holder_pads():
        if circle_rect_gap(p, r_boss, pad) < COPPER_GAP:
            out.append("ホルダのパッド")
    c, r = ifc.cell()
    if math.hypot(p[0] - c[0], p[1] - c[1]) < r + r_nut + COPPER_GAP:
        out.append("電池")
    c, r = ifc.lid_pillar()
    if math.hypot(p[0] - c[0], p[1] - c[1]) < r + r_boss + COPPER_GAP:
        out.append("ふたの柱")
    # 4. コートヤード: 穴のコートヤード（表）と表のコートヤード、ボスと裏のコートヤード
    for fp in geo["footprints"]:
        if re.fullmatch(r"H\d+", fp["ref"]):
            continue
        cy = fp["courtyard"]
        if "front" in cy and circle_rect_gap(p, HOLE_CRTYD_R, cy["front"]) < 0:
            out.append(f"表のコートヤード {fp['ref']}")
        if "back" in cy and circle_rect_gap(p, r_boss, cy["back"]) < 0:
            out.append(f"裏のコートヤード {fp['ref']}")
    # 5. 配線の通り道
    keep = r_hole + COPPER_GAP + TRACK_HALF
    segs = cache.setdefault("corr", None) if cache is not None else None
    if segs is None:
        segs = corridors(ifc, geo)
        if cache is not None:
            cache["corr"] = segs
    for a, b in segs:
        if seg_dist(p, a, b) < keep:
            out.append(f"配線 {a}->{b}")
            break
    if any(abs(p[1] - yb) < keep + BAND_HALF for yb in band_ys(ifc)):
        out.append("段の境目の帯")
    return out


def support_problems(ifc, geo, p):
    """基板を下から支える柱（ネジ無し）を p に立てられない理由の一覧。

    柱は基板の裏面に当たるだけ（配線はソルダーマスクの上から押すので避けない）。
    避けるのは裏に出る物（パッド・足・ボス・ダイオード・スタビ）と、基板の次の段が
    電子部品を置く角の裏（XIAO の下・電池の下）。
    """
    import re
    r = ifc.s.SUPPORT_D / 2
    out = []
    e = ifc.pcb
    if min(p[0] - e[0], e[2] - p[0], p[1] - e[1], e[3] - p[1]) < r + COPPER_GAP:
        out.append("縁")
    if ifc.in_corner(p):
        out.append("角の裏（電子部品の場所）")
    for pad in geo["pads"]:
        if (pad["back"] or pad["npth"]) and circle_rect_gap(p, r, pad["box"]) < COPPER_GAP:
            out.append(f"{pad['ref']} のパッド")
    for fp in geo["footprints"]:
        if "back" in fp["courtyard"] and not re.fullmatch(r"H\d+", fp["ref"]) \
                and circle_rect_gap(p, r, fp["courtyard"]["back"]) < 0:
            out.append(f"裏のコートヤード {fp['ref']}")
    for poly in ifc.stab_reliefs():
        if circle_poly_gap(p, r, poly) < COPPER_GAP:
            out.append("スタビの逃げ穴")
    for m in ifc.mounts():
        if math.hypot(p[0] - m[0], p[1] - m[1]) < r + ifc.s.MOUNT_BOSS_D / 2 + COPPER_GAP:
            out.append("取付のボス")
    return out
