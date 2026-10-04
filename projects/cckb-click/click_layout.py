"""cckb-click の平面の形を spec.py の値から導く。**寸法は持たない**（割り算・足し算だけ）。

基板（pcb_extra.py・click_routes.py・tools/route_pcb.py）と、枠・キャップ・組み立て（click_case.py）と、検査が同じ形を使う。
形を 2 か所で作るとずれる（HHKB でネジ位置をプレートとケースで別々に持ち食い違わせた）。

座標は CAD（キー領域の中心が原点・X 右・Y 奥・mm）。矩形は (x0, y0, x1, y1)。
KiCad の Python（3.9）からも読むので標準ライブラリだけ。
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundry.layout import UNIT, centered        # noqa: E402
from foundry.mech import SKRA_LAND               # noqa: E402
from foundry.project import load                 # noqa: E402


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
    """円（中心 c・半径 r）と矩形の距離（重なりは負）。"""
    x, y = c
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    if dx == 0 and dy == 0:
        return -r - min(x - box[0], box[2] - x, y - box[1], box[3] - y)
    return math.hypot(dx, dy) - r


class Key:
    """キー 1 個。i = 基板の SW{i}（キーマップ順・1 から）。x, y = 中心。w = 幅（u）。r, c = 行列。"""

    def __init__(self, i, x, y, w, r, c, label):
        self.i, self.x, self.y, self.w, self.r, self.c, self.label = i, x, y, w, r, c, label

    @property
    def x0(self):
        return self.x - self.w * UNIT / 2

    @property
    def x1(self):
        return self.x + self.w * UNIT / 2


class Layout:
    def __init__(self, project=None):
        self.p = project or load(HERE)
        self.s = self.p.spec
        keys, rc = self.p.matrix("main")
        pos, (self.kw, self.kh) = centered(keys)
        self.keys = [Key(i, round(x, 6), round(y, 6), k.w_u, r, c, k.label)
                     for i, (k, (x, y), (r, c)) in enumerate(zip(keys, pos, rc), start=1)]

    # --- 外形 -----------------------------------------------------------------
    @property
    def key_area(self):
        return (-self.kw / 2, -self.kh / 2, self.kw / 2, self.kh / 2)

    @property
    def frame(self):
        """枠の外形。"""
        a = self.key_area
        return (a[0] - self.s.PLATE_MARGIN_X, a[1] - self.s.PLATE_MARGIN_Y,
                a[2] + self.s.PLATE_MARGIN_X, a[3] + self.s.PLATE_MARGIN_Y)

    @property
    def pcb(self):
        f = self.frame
        return (f[0] + self.s.PCB_INSET_X, f[1] + self.s.PCB_INSET_Y, f[2] - self.s.PCB_INSET_X, f[3] - self.s.PCB_INSET_Y)

    def rows(self):
        """段の中心の y（上の段から）。"""
        return sorted({k.y for k in self.keys}, reverse=True)

    # --- キーの穴・ランド ----------------------------------------------------
    def rib(self):
        """リブの幅（穴と穴の間）。"""
        return UNIT - self.s.HOLE_B[0]

    def hole(self, k):
        """キーの穴（枠の開口）。幅の広いキーはリブの幅を 1u と同じに保つ。"""
        return rect(k.x, k.y, k.w * UNIT - self.rib(), self.s.HOLE_B[1])

    def side_offset(self, k):
        """幅の広いキーの空きランドの、キーの中心からの距離。1u は None。"""
        if k.w < 1.5:
            return None
        return (k.w * UNIT - self.rib()) / 2 - self.s.SIDE_SW_END

    def switch_sites(self):
        """スイッチの置き場 [(参照名, x, y, 実装するか)]。真ん中 SW{i}（実装する）・空きランド SWA{i}（左）・SWB{i}（右）。"""
        out = []
        for k in self.keys:
            out.append((f"SW{k.i}", k.x, k.y, True))
            off = self.side_offset(k)
            if off is not None:
                out.append((f"SWA{k.i}", round(k.x - off, 6), k.y, False))
                out.append((f"SWB{k.i}", round(k.x + off, 6), k.y, False))
        return out

    def land(self, x, y):
        """スイッチのランドの外接（Alps の図の外外 8.5 × 5.0）。"""
        return rect(x, y, *SKRA_LAND["outer"])

    def switch_body(self, x, y):
        return rect(x, y, self.s.SW_BODY, self.s.SW_BODY)

    # --- 柱（枠と基板の間）--------------------------------------------------
    def posts(self):
        """柱の位置 [(x, y, x の長さ, y の長さ)]。リブの中点: 横に隣り合うキーの間（縦長）と、すぐ奥にキーがある所（横長）。
        click_parts.rib_posts と同じ規則（tests が実物の枠と突き合わせる）。"""
        s = self.s
        out = set()
        for a in self.keys:
            for b in self.keys:
                if abs(b.y - a.y) < 1e-6 and abs(b.x0 - a.x1) < 1e-6:
                    out.add((round(a.x1, 6), a.y, s.POST_W, s.POST_L))
                if abs(b.y - a.y - UNIT) < 1e-6:
                    lo, hi = max(a.x0, b.x0), min(a.x1, b.x1)
                    if hi - lo > s.POST_L:
                        out.add((round((lo + hi) / 2, 6), round(a.y + UNIT / 2, 6), s.POST_L, s.POST_W))
        return sorted(out)

    def corner_posts(self):
        """角（XIAO・電池）の屋根を支える柱。角の境目のリブの下: 横の境目（キーとの間）の真ん中に縦長 1 本、
        奥の境目（段 3 との間）に、上のキーの辺の真ん中ごとに横長 1 本。"""
        s = self.s
        out = []
        for side in ("left", "right"):
            c = self.corner(side)
            x = c[2] if side == "left" else c[0]
            out.append((round(x, 6), round((c[1] + c[3]) / 2, 6), s.POST_W, s.POST_L))
            for k in self.keys:
                if abs(k.y - UNIT / 2 - c[3]) < 1e-6 and c[0] - 1e-6 <= k.x0 and k.x1 <= c[2] + 1e-6:
                    out.append((k.x, round(c[3], 6), s.POST_L, s.POST_W))
                elif abs(k.y - UNIT / 2 - c[3]) < 1e-6 and k.x0 < c[2] and k.x1 > c[0]:
                    lo, hi = max(k.x0, c[0]), min(k.x1, c[2])
                    out.append((round((lo + hi) / 2, 6), round(c[3], 6), s.POST_L, s.POST_W))
        return sorted(out)

    def all_posts(self):
        return self.posts() + self.corner_posts()

    def post_rects(self):
        return [rect(*p) for p in self.all_posts()]

    def col_via(self, k):
        """列を裏へ落とすビア（キーの中心から）。右に空きランドのあるキーは、真ん中のランドの上。"""
        dx, dy = self.s.COL_VIA if self.side_offset(k) is None else self.s.COL_VIA_WIDE
        return (round(k.x + dx, 6), round(k.y + dy, 6))

    def fanout_band(self):
        """595 から列への束の帯（表）: 右の 595 の右から右端の列のビアの右まで・段 3 のランドの奥の端から段 2 のバスの少し手前まで
        （束の手前の線とランドの間に残る幅 1.3 の帯も、行き先へ下りる線で 19 mm おきに切られて袋小路になるので、一緒に塗らない）。"""
        s = self.s
        row_y = self.rows()[s.FANOUT_ROW]
        x0 = max(s.PART_AT["U1"][0], s.PART_AT["U2"][0]) + 3.5      # 595 の右から（595 のまわりは塗る: GND のピンのビアが表のベタに繋がる）
        x1 = max(self.col_via(k)[0] for k in self.keys if k.r == s.FANOUT_ROW) + 1.0
        return (x0, row_y + SKRA_LAND["outer"][1] / 2, x1, row_y + UNIT + s.ROW_BUS_DY - 0.4)

    # --- 高さ（基板の上面 = 0）-------------------------------------------------
    def z(self):
        """積み上げの高さ。基板の厚さは JLC の ±10%（1.44〜1.76）。"""
        s = self.s
        pcb_min = s.PCB_T * 0.9
        cap_top = s.FRAME_UNDER + s.FRAME_T + s.CAP_ABOVE_FRAME
        return dict(
            desk=-s.PCB_T - s.BOTTOM_SHEET_T, pcb_bottom=-s.PCB_T, frame_under=s.FRAME_UNDER,
            frame_top=s.FRAME_UNDER + s.FRAME_T, cap_top=cap_top,
            total=s.BOTTOM_SHEET_T + s.PCB_T + cap_top,                    # 机からキャップの上面まで
            head_below_sheet=s.SCREW_HEAD_H - s.BOTTOM_SHEET_T,            # ねじの頭がシートの下面から出る量（公差の端）
            screw_tip=s.SCREW_L - pcb_min, screw_grip=s.SCREW_L - s.PCB_T,  # 外周のねじの先（基板が薄い側）・掛かり（名目）
            pilot_top=s.SCREW_PILOT_DEPTH,
            holddown_top=s.HOLDDOWN_H, holddown_tip=s.HOLDDOWN_SCREW_L - pcb_min,
            holddown_grip=min(s.HOLDDOWN_H, s.HOLDDOWN_SCREW_L - s.PCB_T),
            xiao_body_top=s.XIAO_BODY_H + s.XIAO_SOLDER_T, usb_top=s.XIAO_H + s.XIAO_SOLDER_T,
            clip_top=s.CLIP_H + s.XIAO_SOLDER_T, cell_top=s.CELL_T, psw_top=s.PSW_H + s.XIAO_SOLDER_T)

    # --- ねじ -----------------------------------------------------------------
    def pilot(self):
        """枠の下穴（径, 深さ）。"""
        return self.s.SCREW_PILOT_D, self.s.SCREW_PILOT_DEPTH

    def screws(self):
        """[(参照名, (x, y), 種類)]。種類は "perimeter"（外周の壁に M2×4）・"holddown"（中の低い足に M2×3）・
        "spare"（外周の壁の予備。基板の穴と枠の下穴はあるが、既定では締めない）・
        "cover"（電池の蓋をねじで留める日のための穴。**基板の穴だけ**で、枠に下穴は無い）。基板の H{n} と同じ順（足した順）。"""
        s = self.s
        kinds = (["perimeter"] * len(s.SCREWS_PERIMETER) + ["holddown"] * len(s.HOLDDOWN_AT) + ["spare"] * len(s.SCREWS_SPARE)
                 + ["cover"] * len(s.SCREWS_COVER))
        return [(f"H{i}", tuple(p), kind)
                for i, (p, kind) in enumerate(zip(s.SCREWS_PERIMETER + s.HOLDDOWN_AT + s.SCREWS_SPARE + s.SCREWS_COVER, kinds))]

    def boss_half(self, c):
        """外周のねじ c の所で壁を厚くする幅の半分。奥と手前の壁は SCREW_BOSS_HALF。左右の壁は、隣のキーが幅の広いキー
        （空きランドがある）なら SCREW_BOSS_HALF_SIDE・1u なら SCREW_BOSS_HALF。"""
        s = self.s
        f = self.frame
        x, y = c
        if min(y - f[1], f[3] - y) < min(x - f[0], f[2] - x):
            return s.SCREW_BOSS_HALF
        k = min((k for k in self.keys if (k.x < 0) == (x < 0)), key=lambda k: (abs(k.y - y) > UNIT / 2, -abs(k.x)))
        return s.SCREW_BOSS_HALF if self.side_offset(k) is None else s.SCREW_BOSS_HALF_SIDE

    def wall_screws(self):
        """外周の壁に下穴を持つねじ（外周 ＋ 予備）[(参照名, (x, y), 種類)]。"""
        return [v for v in self.screws() if v[2] in ("perimeter", "spare")]

    def screw_head_keepouts(self):
        """ねじの頭（基板の下面）の下で裏の銅を禁止する円 [(参照名, 中心, 半径)]。"""
        r = self.s.SCREW_HEAD_D / 2 + self.s.METAL_COPPER_CLEAR
        return [(ref, c, r) for ref, c, _ in self.screws()]

    def holddown_foot(self, c):
        """中の押さえの足（円）が付く柱。足は柱（リブの中点）から右へ HOLDDOWN_OFFSET。柱が無ければ落とす。"""
        want = (round(c[0] - self.s.HOLDDOWN_OFFSET, 6), c[1])
        for p in self.posts():
            if abs(p[0] - want[0]) < 1e-3 and abs(p[1] - want[1]) < 1e-3 and p[2] < p[3]:
                return p
        raise ValueError(f"中の押さえ {c} の左 {self.s.HOLDDOWN_OFFSET} に縦の柱が無い")

    # --- 継ぎ目 ---------------------------------------------------------------
    def seam_x(self, y):
        """高さ y の所で左右の枠を分ける x（キーの境目）。段の外（壁）は最寄りの段の値。"""
        rows = self.rows()
        r = min(range(len(rows)), key=lambda i: abs(rows[i] - y))
        return self.s.FRAME_SPLIT[r]

    def side_of(self, k):
        return "left" if k.x < self.seam_x(k.y) else "right"

    def seam_offsets(self):
        """継ぎ目の線（キーの境目）から、左の枠の右の面・右の枠の左の面まで。左がリブを丸ごと持つ。"""
        half = self.rib() / 2
        return half, half + self.s.FRAME_SEAM_GAP

    def seam_path(self):
        """継ぎ目の折れ線（奥の外形から手前の外形まで。キーの境目の上）。[(x, y), ...]"""
        f = self.frame
        rows = self.rows()
        pts = [(self.s.FRAME_SPLIT[0], f[3])]
        for r in range(len(rows) - 1):
            yb = rows[r] - UNIT / 2
            pts += [(self.s.FRAME_SPLIT[r], yb), (self.s.FRAME_SPLIT[r + 1], yb)]
        pts.append((self.s.FRAME_SPLIT[-1], f[1]))
        return pts

    # --- 左の角: XIAO ---------------------------------------------------------
    def corner(self, side):
        """最下段の空いた角（キー領域の中の矩形）。side = "left" / "right"。"""
        a = self.key_area
        low = [k for k in self.keys if k.y == min(self.rows())]
        y1 = a[1] + UNIT
        if side == "left":
            return (a[0], a[1], min(k.x0 for k in low), y1)
        return (max(k.x1 for k in low), a[1], a[2], y1)

    def xiao(self):
        x, y = self.s.XIAO_AT
        return rect(x, y, self.s.XIAO_L, self.s.XIAO_W)

    def xiao_pads(self):
        """XIAO のパッドの並びの外接（幅方向に XIAO_PAD_EXT 出る）。"""
        b = self.xiao()
        return (b[0], b[1] - self.s.XIAO_PAD_EXT, b[2], b[3] + self.s.XIAO_PAD_EXT)

    def usb_shell(self):
        """XIAO の USB-C メスの平面（口は −x）。"""
        b = self.xiao()
        y = self.s.XIAO_AT[1]
        return (b[0] - self.s.XIAO_USB_OVERHANG, y - self.s.XIAO_USB_W / 2,
                b[0] + self.s.XIAO_USB_D - self.s.XIAO_USB_OVERHANG, y + self.s.XIAO_USB_W / 2)

    def antenna_chip(self):
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

    def antenna_front_strip(self):
        """アンテナの禁止域の手前の端と、行 4 の裏の線（spec.XIAO_ESCAPE の run_y）の間。裏の GND のベタを塗らない矩形。
        ここのベタは幅 0.45・長さ 5 の細い帯で、禁止域の縁に沿って右の端だけで繋がっていた（1 回目の監査 D 軽微 4）。
        **禁止域そのものは広げない**（広げると行 4 の線が通れない）。"""
        k = self.antenna_keepout()
        return (k[0], self.s.XIAO_ESCAPE["ROW4"]["run_y"], k[2], k[1])

    def xiao_exposed(self):
        """XIAO の裏の露出パッド 8 個と USB のシールドの長穴 4 個（＋ XIAO_BOTTOM_CLEAR）。{名前: 矩形}。"""
        s = self.s
        x, y = s.XIAO_AT
        c = s.XIAO_BOTTOM_CLEAR
        out = {f"pad{n}": r for n, (_, r) in s.XIAO_BOTTOM_PADS.items()}
        out.update(s.XIAO_BOTTOM_SLOTS)
        return {n: (x + r[0] - c, y + r[1] - c, x + r[2] + c, y + r[3] + c) for n, r in out.items()}

    def xiao_back_no_fill(self):
        """XIAO の下の裏で GND のベタを塗らない範囲: 表の銅を禁止している範囲と同じ（XIAO の外形の中・手前は基板の縁から・左も縁から）。
        ここの裏は、行 0〜4 の線（2.54 おきの縦線と、左へ曲がる横線）で幅 2 mm 足らずの帯と袋に切られる。表が禁止なのでビアも打てず、
        帯の先はビアから銅の上で 19〜22 mm あった（検査 gnd_far）。XIAO は自分の基板に GND の面を持っている。"""
        return self.xiao_underside()[0]

    def xiao_underside(self):
        """XIAO の下で表の銅を禁止する範囲 [矩形, ...]。CCKB の pcb_extra.xiao_underside と同じ決め方:
        XIAO の外形の中で、手前は基板の縁から、奥は露出パッドの奥の端まで。外形の外へ出る露出パッドは足す。"""
        s = self.s
        b = self.xiao()
        pads = list(self.xiao_exposed().values())
        top = max(p[3] for p in pads)
        pad_inner = s.XIAO_AT[1] + s.XIAO_W / 2 - s.XIAO_PAD_IN
        if top >= pad_inner:
            raise RuntimeError(f"XIAO の下の禁止域の奥 {top:.3f} が奥の列のパッドの内端 {pad_inner:.3f} を越える")
        # 左は基板の縁まで（XIAO の左の端と基板の縁の間 1.5 に残る表のベタは、ビアの打てない細い帯で、奥へ 20 mm 続く袋小路になる。
        # 検査 gnd_far が見つけた。真上は USB のシェルの張り出し）
        out = [(self.pcb[0], self.pcb[1], b[2], top)]
        out += [p for p in pads if p[0] < b[0] or p[2] > b[2] or p[3] > top]
        return out

    # --- 右の角: 電池・電源スイッチ ------------------------------------------
    def cell(self):
        """**止めに当てた**電池（中心, 半径）。クリップの原点から奥へ: 止めの外面 CLIP_STOP − 板の厚さ − 電池の半径
        （図面 MY-CP-0247。1 回目の監査 E 重要 1: 前はクリップの原点を中心にしていて、缶の縁が表のベタの縁の真上だった）。"""
        s = self.s
        r = s.CELL_D / 2
        return (s.CLIP_AT[0], round(s.CLIP_AT[1] + s.CLIP_STOP - s.CLIP_SHEET_T - r, 6)), r

    def cell_recess(self):
        """電池の手前の縁が枠の外面から引っ込む量。"""
        (_, y), r = self.cell()
        return y - r - self.frame[1]

    def clip_pads(self):
        """＋のランド 2 つ（左・右）。"""
        x, y = self.s.CLIP_AT
        h = self.s.CLIP_PAD_SPAN / 2
        return [rect(x - h, y, *self.s.CLIP_PAD), rect(x + h, y, *self.s.CLIP_PAD)]

    def clip_body(self):
        """クリップの板（止めから口まで）。"""
        x, y = self.s.CLIP_AT
        return (x - self.s.CLIP_BODY_W / 2, y - self.s.CLIP_MOUTH, x + self.s.CLIP_BODY_W / 2, y + self.s.CLIP_STOP)

    def cell_keepout(self):
        """電池の下と抜き差しの道（表の銅を置かない）。矩形: 電池の幅 ＋ 余裕・奥は止めの外面 ＋ CELL_KEEPOUT_BACK・手前は基板の縁。"""
        s = self.s
        (x, _), r = self.cell()
        c = s.CELL_KEEPOUT_CLEAR
        return (x - r - c, self.pcb[1], x + r + c, s.CLIP_AT[1] + s.CLIP_STOP + s.CELL_KEEPOUT_BACK)

    def ic_band(self):
        """2 つの 595 の本体の下を抜ける表の GND の帯で、表の線を通さない矩形 [矩形, ...]（spec.IC_BAND）。ランドを結ぶ線
        （spec.LINK_UNDER）の間。名指しのビア（spec.IC_BAND_VIA_X）の所は空ける。"""
        s = self.s
        left, right, clear = s.IC_BAND
        y = s.PART_AT["U1"][1]
        land_y = SKRA_LAND["inner"][1] / 2 + (SKRA_LAND["outer"][1] - SKRA_LAND["inner"][1]) / 4      # ランドの列の中心（2.0）
        half = land_y - s.LINK_UNDER - 0.1 - clear                                                  # 線の半幅 0.1
        x0 = min(s.PART_AT["U1"][0], s.PART_AT["U2"][0]) - left
        x1 = max(s.PART_AT["U1"][0], s.PART_AT["U2"][0]) + right
        cuts = sorted(v for v in s.IC_BAND_VIA_X if x0 < v < x1)
        xs = [x0] + [e for v in cuts for e in (v - 0.7, v + 0.7)] + [x1]
        return [(xs[i], y - half, xs[i + 1], y + half) for i in range(0, len(xs), 2)]

    def psw_body(self):
        """電源スイッチの本体（長辺が y・つまみは +x）。"""
        x, y = self.s.PSW_AT
        cx = x + self.s.PSW_ORIGIN_TO_BODY
        return rect(cx, y, self.s.PSW_BODY[1], self.s.PSW_BODY[0])

    def psw_pads(self):
        """電源スイッチのパッドの外接（端子・枠のランド）。"""
        x, y = self.s.PSW_AT
        b = self.s.PSW_PAD_BOX
        return (x + b[0], y + b[1], x + b[2], y + b[3])

    def psw_knob(self, pos):
        """つまみ（pos = +1 奥 / −1 手前）。"""
        b = self.psw_body()
        y = self.s.PSW_AT[1] + pos * self.s.PSW_TRAVEL / 2
        w, out = self.s.PSW_KNOB
        return (b[2], y - w / 2, b[2] + out, y + w / 2)

    def psw_knob_sweep(self, tol=0.0):
        """つまみが動く範囲。tol で行程の公差の分だけ両側へ広げる。"""
        a, b = self.psw_knob(-1), self.psw_knob(1)
        return (a[0], a[1] - tol / 2, a[2], b[3] + tol / 2)

    def psw_notch(self):
        """つまみの切り欠き（枠の右の壁を上まで抜く範囲）の平面の多角形 [(x, y), ...]。内側の面は本体の縁 ＋ PART_CLEAR。
        外面の側の角は斜めに落とす（指が入りやすい・角が欠けにくい）。外面の 1.0 外まで。"""
        s = self.s
        w, ch = s.PSW_NOTCH
        x0 = self.psw_body()[2] + s.PART_CLEAR
        x1 = self.frame[2]
        y0, y1 = s.PSW_AT[1] - w / 2, s.PSW_AT[1] + w / 2
        return [(x0, y0), (x1 - ch, y0), (x1, y0 - ch), (x1 + 1.0, y0 - ch), (x1 + 1.0, y1 + ch), (x1, y1 + ch), (x1 - ch, y1), (x0, y1)]

    def psw_nail(self, pos):
        """爪の入る場所（検査の包絡・平面の矩形）。つまみが pos（+1 奥 / −1 手前）にあるとき、反対の端へ押すために、
        つまみの脇（押す側）に要る場所: 幅 PSW_NAIL[0]・つまみの先から本体の側へ PSW_NAIL[1] 掛かる所から、枠の外面の 10 外まで。"""
        s = self.s
        k = self.psw_knob(pos)
        w, bite = s.PSW_NAIL
        y0, y1 = (k[3], k[3] + w) if pos > 0 else (k[1] - w, k[1])
        return (k[2] - bite, y0, self.frame[2] + 10.0, y1)

    # --- 電池の蓋（差し込み式）--------------------------------------------------
    def cover(self):
        """蓋の寸法（CAD・基板の上面 = 0）。枠の切り欠き（click_case.corner_cuts）と蓋（click_case.cover_solid）の両方がここから作る。
          x0, x1    電池の口（幅 = 電池 ＋ 2 × CELL_SLOT_CLEAR）
          nx0, nx1  指の切り欠き（幅 FINGER_NOTCH[0]）。上の縁にひさし（COVER_RAIL）
          y0        枠の外面・y_front 手前の板の奥の面・y_root 上の板の付け根の奥の端・y1 切り欠きの奥の壁
          z_slot    口の上の壁の下面（= 切り欠きの底）・z_top 枠の上面・z_plate 上の板の下面・z_root 付け根の下面
          bump      山の中心 [(x, y), (x, y)]（腕の先の COVER_BUMP[2] の真ん中。口の上の壁の下面の溝と同じ y）"""
        s = self.s
        (cx, _), r = self.cell()
        f = self.frame
        top = s.FRAME_UNDER + s.FRAME_T
        w, d = s.FINGER_NOTCH
        x0, x1 = cx - r - s.CELL_SLOT_CLEAR, cx + r + s.CELL_SLOT_CLEAR
        nx0, nx1 = cx - w / 2, cx + w / 2
        # 山は腕の先（蓋の端 = 口の端 ＋ 隙）から COVER_BUMP[2] だけ。口の上の壁（口の端から切り欠きの壁まで）の下より内へは出ない
        bx = s.COVER_CLEAR + min(s.COVER_BUMP[2], nx0 - x0 - 2 * s.COVER_CLEAR) / 2
        by = f[1] + s.COVER_FRONT_T - s.COVER_BUMP[1] / 2 - 0.05
        return dict(x0=x0, x1=x1, nx0=nx0, nx1=nx1, y0=f[1], y_front=f[1] + s.COVER_FRONT_T, y_root=f[1] + s.COVER_ROOT[1],
                    y1=f[1] + d, z_slot=s.CELL_T + s.CELL_SLOT_CLEAR + 0.1, z_top=top, z_plate=top - s.COVER_TOP_T,
                    z_root=top - s.COVER_ROOT[0],
                    bump=[(x0 + bx, by), (x1 - bx, by)])
