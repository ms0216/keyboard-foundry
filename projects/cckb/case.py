"""CCKB のケース（トレイ 2・角のふた 2）を作る。**寸法は持たない**（spec / interface / case_spec）。

形（決定記録 2026-09-24-interface.md §5）:
  - トレイ = 床＋外壁。はんだ付けした基板＋プレートを**上から**落とす。継ぎ目は案 C
    （奥の壁 x=9.525・手前の壁 x=4.7625・床は y=0 で段）で左右 2 つ。それぞれ下からの M2 皿ネジで
    基板の上面のナット（プレートの六角の穴が回り止め）に留まる。継ぎ目どうしは繋がない（D13）
  - 床から立つもの: 取付のボス φ5.6（10）、支えの柱 φ3.0（38）、右の角のふたの柱 φ5.2（インサート）
  - 左の壁: XIAO の USB-C の口（上に開いた切り欠き。上は左のふたの舌が塞ぐ）
  - 右の壁: 電源スイッチのつまみの切り欠き（同上。右のふたのひれが塞ぐ）＋外面の指の窪み
  - 床の裏の四隅: 滑り止めのくぼみ
  - 左のふた: 天板＋キー側の垂れ壁＋USB の舌＋H3 のボス（インサート。下からのネジで基板に締める）
  - 右のふた（電池のふた）: 天板＋キー側の垂れ壁 2 辺＋つまみのひれ＋柱に当たるボス。
    上からの M2 皿ネジ 1 本で柱のインサートへ。**ネジはふたの膜に捕まって落ちない**

座標は CAD（キー領域の中心が原点・X 右・Y 奥・Z は机 = 0）。印刷の向きは export 時に回す。

    .venv/bin/python3 projects/cckb/case.py      # build/cckb/ に全部の印刷部品の STL と絵
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build123d import (Align, Box, Compound, Cone, Cylinder, Part, Polygon,  # noqa: E402
                       Pos, RectangleRounded, RegularPolygon, Rot, extrude)

import case_spec as CS  # noqa: E402
import interface as I  # noqa: E402
from foundry.plate import M2_CLEAR_D  # noqa: E402

MIN = (Align.MIN, Align.MIN, Align.MIN)
CEN_MIN = (Align.CENTER, Align.CENTER, Align.MIN)


# ---------------------------------------------------------------------------
# 立体の小道具
# ---------------------------------------------------------------------------

def box(x0, y0, z0, x1, y1, z1):
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=MIN)


def rbox(r, z0, z1):
    """矩形 r=(x0,y0,x1,y1) の角柱。"""
    return box(r[0], r[1], z0, r[2], r[3], z1)


def cyl(x, y, z0, z1, d):
    return Pos(x, y, z0) * Cylinder(d / 2, z1 - z0, align=CEN_MIN)


def cone(x, y, z0, z1, d0, d1):
    return Pos(x, y, z0) * Cone(d0 / 2, d1 / 2, z1 - z0, align=CEN_MIN)


def rounded(r, rad, z0, z1):
    w, h = r[2] - r[0], r[3] - r[1]
    return Pos((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, z0) * extrude(RectangleRounded(w, h, rad), z1 - z0)


def prism(pts, z0, z1):
    """多角形の角柱。**時計回りの点列は裏向きの面になり、下へ押し出される**ので反時計回りに揃える。"""
    pts = list(pts)
    area = sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1]
               for k in range(len(pts)))
    if area < 0:
        pts.reverse()
    return Pos(0, 0, z0) * extrude(Polygon(*pts, align=None), z1 - z0)


def hex_prism(x, y, af, z0, z1):
    """二面幅 af の六角柱。**向きは foundry.plate の六角の穴と同じ**（rotation=30: 二面が ±x）。"""
    return Pos(x, y, z0) * extrude(RegularPolygon(af / math.sqrt(3), 6, rotation=30), z1 - z0)


def fuse(shapes):
    shapes = list(shapes)
    out = shapes[0]
    if len(shapes) > 1:
        out = out.fuse(*shapes[1:])
    return out.clean()


def one_solid(part, name):
    """部品が 1 つの立体か（膜で繋がっているだけ・離れた島がある、を捕まえる）。"""
    n = len(part.solids())
    assert n == 1, f"{name}: 立体が {n} 個に分かれている"
    return part


# ---------------------------------------------------------------------------
# ケース
# ---------------------------------------------------------------------------

class Case:
    """ケースの部品。ifc（interface.Interface）と cs（case_spec）から作る。

    故意に壊す検査は `I.Interface(project)` の spec を差し替えて渡す。
    """

    def __init__(self, ifc=None, cs=CS):
        self.i = ifc or I.Interface()
        self.s = self.i.s
        self.c = cs
        self.z = self.i.z()

    # --- 導いた値（ここで新しい寸法を作らない） -----------------------------------
    @property
    def r_in(self):
        """壁の内面の角の丸み = 基板の角 R ＋ 壁との隙（同心。隙は interface.wall_gap）。"""
        return self.s.CORNER_R + self.i.wall_gap

    @property
    def r_out(self):
        return self.r_in + self.s.CASE_WALL

    def usb_opening(self):
        """壁の USB の口 (y0, y1, z0, z1)。メスの外形＋片側 PORT_CLEAR。上は左のふたの舌。"""
        s, y = self.s, self.s.XIAO_AT[1]
        w = s.XIAO_USB_W / 2 + s.PORT_CLEAR
        h = s.XIAO_USB_H / 2 + s.PORT_CLEAR
        zc = self.z["usb_center"]
        return (y - w, y + w, zc - h, zc + h)

    def psw_slot(self):
        """つまみの切り欠き (y0, y1, z0)。つまみの動く範囲＋片側 PSW_SLOT_CLEAR。上へは開く。"""
        k = self.i.psw_knob()
        c = self.c.PSW_SLOT_CLEAR
        return (k[1] - c, k[3] + c, self.z["psw_bottom"] - c)

    def psw_scoop(self):
        """指の窪み (x0, y0, z0, x1, y1, z1)。外面から PSW_SCOOP。"""
        o = self.i.case_outer
        y = self.s.PSW_AT[1]
        w = self.c.PSW_SCOOP_W / 2
        z0, z1 = self.c.PSW_SCOOP_Z
        return (o[2] - self.s.PSW_SCOOP, y - w, z0, o[2] + 1.0, y + w, z1)

    def pillar_top(self):
        return self.z["lid_bottom"] - self.c.LID_BOSS_H

    def corner_wall_top(self, side):
        return self.z["lid_bottom"] - (self.c.LID_L_WALL_GAP if side == "left" else 0.0)

    def antislip_pads(self):
        """滑り止めのくぼみの矩形 4 つ（左奥・左手前・右奥・右手前）。"""
        o = self.i.case_outer
        w, h = self.c.ANTISLIP_PAD
        e = self.c.ANTISLIP_INSET
        out = []
        for x0 in (o[0] + e, o[2] - e - w):
            for y0 in (o[3] - e - h, o[1] + e):
                out.append((x0, y0, x0 + w, y0 + h))
        return out

    def seam_regions(self):
        """継ぎ目の左右の領域（SEAM_GAP の半分ずつ引いた多角形）。"""
        back, front = self.s.CASE_SEAM
        g = self.c.SEAM_GAP / 2
        B = 400.0
        left = [(-B, B), (back - g, B), (back - g, g), (front - g, g), (front - g, -B), (-B, -B)]
        right = [(back + g, B), (B, B), (B, -B), (front + g, -B), (front + g, -g), (back + g, -g)]
        return left, right

    def seam_line(self):
        """継ぎ目の中心線（奥から手前へ）。"""
        back, front = self.s.CASE_SEAM
        o = self.i.case_outer
        return [(back, o[3]), (back, 0.0), (front, 0.0), (front, o[1])]

    # --- ネジの座（下から入れる皿ネジ） -----------------------------------------
    def screw_seat(self, x, y, sink):
        """下から入れる皿ネジの座ぐり＋円錐の座＋穴（**削る側の立体**）。sink は頭の面の高さ。"""
        s, c = self.s, self.c
        dh = c.SCREW_HEAD_D + 2 * c.SEAT_CLEAR
        ds = c.SCREW_D + 2 * c.SEAT_CLEAR
        return fuse([cyl(x, y, -1.0, sink, dh),
                     cone(x, y, sink, sink + s.SCREW_HEAD_H, dh, ds),
                     cyl(x, y, -1.0, self.z["pcb_bottom"] + 1.0, M2_CLEAR_D)])

    def screw_seat_top(self, x, y, top):
        """上から入れる皿ネジの座（頭の面 = top）。"""
        s, c = self.s, self.c
        dh = c.SCREW_HEAD_D + 2 * c.SEAT_CLEAR
        ds = c.SCREW_D + 2 * c.SEAT_CLEAR
        return fuse([cyl(x, y, top, top + 1.0, dh),
                     cone(x, y, top - s.SCREW_HEAD_H, top, ds, dh)])

    # --- トレイ -------------------------------------------------------------
    def tray(self):
        s, c, z, i = self.s, self.c, self.z, self.i
        o, w = i.case_outer, i.wall_inner
        body = rounded(o, self.r_out, 0.0, z["rim"]) - rounded(w, self.r_in, z["floor_top"], z["rim"] + 1)
        cut = []
        # 角: ふたが載る所の壁を下げる（ふたの縁の内側 2 辺に FIT/2 の隙）
        for side in ("left", "right"):
            r = I.grow(i.cover(side), c.FIT / 2)
            cut.append(rbox(r, self.corner_wall_top(side), z["rim"] + 1))
        # USB の口（上に開く。上は左のふたの舌）
        y0, y1, z0, _ = self.usb_opening()
        cut.append(box(o[0] - 1, y0, z0, w[0] + 0.5, y1, z["rim"] + 1))
        # 電源スイッチのつまみ（上に開く。上は右のふたのひれ）
        y0, y1, z0 = self.psw_slot()
        cut.append(box(w[2] - 0.5, y0, z0, o[2] + 1, y1, z["rim"] + 1))
        # 指の窪み
        cut.append(box(*self.psw_scoop()))
        # 滑り止めのくぼみ
        for r in self.antislip_pads():
            cut.append(rbox(r, -1.0, s.ANTISLIP_RECESS))
        body = body - fuse(cut)
        # 床から立つもの
        posts = [cyl(x, y, z["floor_top"] - 0.1, z["pcb_bottom"], s.MOUNT_BOSS_D) for x, y in i.mounts()]
        posts += [cyl(x, y, z["floor_top"] - 0.1, z["pcb_bottom"], s.SUPPORT_D) for x, y in s.SUPPORTS]
        px, py = s.LID_PILLAR_AT
        posts.append(cyl(px, py, z["floor_top"] - 0.1, self.pillar_top(), s.LID_PILLAR_D))
        body = body.fuse(*posts)
        holes = [self.screw_seat(x, y, s.SCREW_SINK) for x, y in i.mounts()]
        top = self.pillar_top()
        holes.append(cyl(px, py, top - c.INSERT_L - c.INSERT_HOLE_EXTRA, top + 1, c.INSERT_HOLE_D))
        return (body - fuse(holes)).clean()

    def tray_halves(self, tray=None):
        tray = tray or self.tray()
        left, right = self.seam_regions()
        out = {}
        for name, pts in (("tray_L", left), ("tray_R", right)):
            out[name] = one_solid((tray & prism(pts, -5, 30)).clean(), name)
        return out

    # --- 角のふた -------------------------------------------------------------
    def _lid_common(self, side):
        z, i, c = self.z, self.i, self.c
        cov = i.cover(side)
        top = rounded(i.case_outer, self.r_out, z["lid_bottom"], z["rim"]) & rbox(cov, -1, 30)
        inner = (max(cov[0], i.wall_inner[0]), max(cov[1], i.wall_inner[1]),
                 min(cov[2], i.wall_inner[2]), min(cov[3], i.wall_inner[3]))
        drop = rbox(inner, z["pcb_top"] + c.LID_DROP_GAP, z["lid_bottom"] + 0.01) \
            - rbox(i.cover_cavity(side), 0, 30)
        return top.fuse(drop)

    def lid_left(self):
        s, c, z, i = self.s, self.c, self.z, self.i
        lid = self._lid_common("left")
        o, w = i.case_outer, i.wall_inner
        # USB の舌: 壁の切り欠きの口より上を塞ぐ
        y0, y1, _, z1 = self.usb_opening()
        tongue = box(o[0], y0 + c.FIT / 2, z1, w[0], y1 - c.FIT / 2, z["lid_bottom"] + 0.01)
        # H3 のボス: 基板の上面に当たり、下からのネジをインサートで受ける
        mx, my = self.left_lid_mount()
        cav = i.cover_cavity("left")
        r = c.INSERT_HOLE_D / 2 + c.LID_BOSS_WEB
        boss = box(mx - r, my - r, z["pcb_top"], cav[2] + 0.01, i.cover("left")[3], z["lid_bottom"] + 0.01)
        lid = lid.fuse(tongue, boss)
        hole = cyl(mx, my, z["pcb_top"] - 1, z["pcb_top"] + c.INSERT_L + c.INSERT_HOLE_EXTRA,
                   c.INSERT_HOLE_D)
        return one_solid((lid - hole).clean(), "lid_L")

    def left_lid_mount(self):
        """左のふたを留める取付（角の中にある 1 つ）。"""
        m = [p for p in self.i.mounts() if self.i.in_corner(p)]
        assert len(m) == 1, m
        return m[0]

    def lid_right(self):
        s, c, z, i = self.s, self.c, self.z, self.i
        lid = self._lid_common("right")
        o, w = i.case_outer, i.wall_inner
        # つまみのひれ: 切り欠きの上（基板の下面＋隙から）を塞ぐ
        y0, y1, _ = self.psw_slot()
        fin = box(w[2], y0 + c.FIT / 2, z["pcb_bottom"] + c.LID_DROP_GAP, o[2],
                  y1 - c.FIT / 2, z["lid_bottom"] + 0.01) - box(*self.psw_scoop())
        # 柱に当たるボス
        px, py = s.LID_PILLAR_AT
        boss = cyl(px, py, self.pillar_top(), z["lid_bottom"] + 0.01, s.LID_PILLAR_D)
        lid = lid.fuse(fin, boss)
        top = self.pillar_top()
        holes = fuse([self.screw_seat_top(px, py, z["rim"]),
                      cyl(px, py, top + c.CAPTIVE_WEB_T, z["rim"], M2_CLEAR_D),
                      cyl(px, py, top - 1, top + c.CAPTIVE_WEB_T + 0.01, c.CAPTIVE_HOLE_D)])
        return one_solid((lid - holes).clean(), "lid_R")

    # --- 全部 -----------------------------------------------------------------
    def parts(self):
        out = self.tray_halves()
        out["lid_L"] = self.lid_left()
        out["lid_R"] = self.lid_right()
        return out


# ---------------------------------------------------------------------------
# 印刷の向き（部品の名前 → 組み立ての姿勢から印刷の姿勢への変換）
# ---------------------------------------------------------------------------

def print_pose(name, part):
    """印刷の向きに回して、底を z=0・平面の中心を原点に置く。

    - トレイ: 床をベッドに（そのまま）。切り欠きは全部上に開いているのでサポート無し
    - ふた: 天板をベッドに（上下を返す）。垂れ壁・舌・ひれ・ボスが上に立つ
    - キーキャップ: 天板をベッドに（上下を返す）。脚とスカートが上に立ち、サポート無し
      （keycaps_set_* は並べるときに返してある）
    """
    if name.startswith(("lid_", "keycap_")):
        part = Rot(180, 0, 0) * part
    bb = part.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * part


def export_all(out=None):
    """印刷する全部品を build/cckb/ に書く（プレートは foundry.plate、キャップと小片も）。

    slice_check は projects/cckb/*.py より古い STL を「古い」として落とすので、**全部を一度に作る**。
    """
    from foundry.plate import main as plate_main
    from foundry.project import load
    from foundry.verify import to_mesh

    import coupons
    import keycaps

    p = load("cckb")
    out = Path(out or p.build)
    out.mkdir(parents=True, exist_ok=True)
    plate_main(["cckb"])
    parts = dict(Case().parts())
    parts.update(keycaps.print_parts())
    parts.update(coupons.parts())
    report = {}
    for name, part in parts.items():
        posed = print_pose(name, part)
        mesh, stl = to_mesh(posed, out / f"{name}.stl")
        bb = posed.bounding_box()
        report[name] = dict(size=(round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2)),
                            volume=round(part.volume, 1), watertight=bool(mesh.is_watertight),
                            solids=len(part.solids()))
        ok = mesh.is_watertight and max(bb.size.X, bb.size.Y) <= p.spec.PRINT_MAX
        print(f"{'OK' if ok else 'NG'} {name:14s} {bb.size.X:7.2f} x {bb.size.Y:6.2f} x {bb.size.Z:5.2f}"
              f"  体積 {part.volume / 1000:6.2f} cm3  水密={mesh.is_watertight}  立体 {len(part.solids())}")
    return report


if __name__ == "__main__":
    export_all()
