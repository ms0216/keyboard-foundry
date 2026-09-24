"""CCKB の境界（角・ネジ・電源スイッチ・スタビ・継ぎ目・高さ）を図にする。

    .venv/bin/python3 projects/cckb/tools/draw_interface.py      # → build/cckb/interface_*.png

**寸法は持たない。**形はすべて projects/cckb/interface.py（spec.py の値）から取る。
決定記録 docs/decisions/2026-09-24-interface.md の図はこれが出す。出したら Read で見ること。
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle   # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface import Interface, hex_r, size          # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "build" / "cckb"
plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "sans-serif"]


def box(ax, b, **kw):
    kw.setdefault("fill", False)
    ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], **kw))


def hexagon(ax, c, af, **kw):
    import math
    r = hex_r(af)
    pts = [(c[0] + r * math.cos(math.radians(90 + 60 * i)),
            c[1] + r * math.sin(math.radians(90 + 60 * i))) for i in range(6)]
    ax.add_patch(Polygon(pts, closed=True, fill=False, **kw))


def plan(ax, ifc, what=("all",)):
    s = ifc.s
    box(ax, ifc.case_outer, ec="k", lw=1.4)
    box(ax, ifc.wall_inner, ec="k", lw=0.6)
    box(ax, ifc.pcb, ec="g", lw=0.8, ls="--")
    for (x, y), k in zip(ifc.positions, ifc.keys):
        box(ax, (x - k.w_mm / 2 + s.KEYCAP_GAP, y - 9.525 + s.KEYCAP_GAP,
                 x + k.w_mm / 2 - s.KEYCAP_GAP, y + 9.525 - s.KEYCAP_GAP), ec="0.75", lw=0.5)
    for b in ifc.switch_bodies():
        box(ax, b, ec="0.45", lw=0.6)
    for poly in ifc.stab_reliefs():
        ax.add_patch(Polygon(poly, closed=True, fill=False, ec="m", lw=0.7))
    for poly in ifc.stab_housings():
        ax.add_patch(Polygon(poly, closed=True, fill=True, fc="m", alpha=0.25, lw=0))
    for side in ("left", "right"):
        box(ax, ifc.cover(side), ec="b", lw=1.0, ls=":")
        box(ax, ifc.cover_cavity(side), ec="b", lw=0.5)
    box(ax, ifc.xiao(), fc="#9cf", fill=True, ec="b", lw=0.8)
    box(ax, ifc.xiao_pads_extent(), ec="b", lw=0.4, ls="--")
    box(ax, ifc.usb_shell(), fc="0.6", fill=True, ec="k", lw=0.6)
    box(ax, ifc.antenna_chip(), fc="r", fill=True, lw=0)
    box(ax, ifc.antenna_keepout(), ec="r", lw=0.8, ls="--")
    box(ax, ifc.holder_body(), fc="#fd9", fill=True, ec="k", lw=0.6)
    for p in ifc.holder_pads():
        box(ax, p, fc="#fb0", fill=True, ec="k", lw=0.4)
    c, r = ifc.cell()
    ax.add_patch(Circle(c, r, fill=False, ec="k", lw=0.8))
    box(ax, ifc.psw_body(), fc="#c9f", fill=True, ec="k", lw=0.5, alpha=0.7)
    for pc in ifc.psw_pins():
        ax.add_patch(Circle(pc, s.PSW_PAD_D / 2, fc="#fb0", ec="k", lw=0.4))
    box(ax, ifc.psw_lever_range(), fc="k", fill=True, lw=0, alpha=0.35)
    box(ax, ifc.psw_lever(s.PSW_ON), fc="k", fill=True, lw=0)
    box(ax, slot_of(ifc), ec="r", lw=0.8)
    c, r = ifc.lid_pillar()
    ax.add_patch(Circle(c, r, fc="#fc9", ec="k", lw=0.6))
    ax.add_patch(Circle(c, s.LID_PILLAR_HOLE / 2, fill=False, ec="g", lw=0.6, ls="--"))
    for m in ifc.mounts():
        ax.add_patch(Circle(m, s.MOUNT_BOSS_D / 2, fill=False, ec="c", lw=0.8))
        hexagon(ax, m, s.MOUNT_POCKET_AF, ec="k", lw=0.7)
        ax.add_patch(Circle(m, 1.1, fc="k"))
    for p in s.SUPPORTS:
        ax.add_patch(Circle(p, s.SUPPORT_D / 2, fc="c", ec="none", alpha=0.6))
    seam = ifc.plate_seam()
    ax.plot([p[0] for p in seam], [p[1] for p in seam], color="orange", lw=1.6)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)


def slot_of(ifc):
    """右のふたのレバーの穴（case.Case.psw_slot と同じ物を case から読む）。"""
    from case import Case
    return Case(ifc).psw_slot()


def section_rects(ax, items):
    for (x0, x1, z0, z1), style in items:
        ax.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, **style))


def left_corner(ifc):
    s, z = ifc.s, ifc.z()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 12), gridspec_kw=dict(height_ratios=[1, 1]))
    plan(a1, ifc)
    c = ifc.corners()["left"]
    a1.set_xlim(c[0] - 12, c[2] + 14)
    a1.set_ylim(ifc.case_outer[1] - 3, c[3] + 12)
    a1.set_title("左の角（平面）: XIAO（青）・USB-C（灰）・アンテナ（赤）と銅の禁止域（赤破線）・"
                 "ふた（青点線）・ふたのネジ H3", fontsize=9)
    y0 = s.XIAO_AT[1]
    a1.axhline(y0, color="k", lw=0.4, ls="-.")
    a1.text(c[0] - 11, y0 + 0.5, "断面 A", fontsize=8)
    # 断面 A（y = XIAO の中心・x-z）
    o, w = ifc.case_outer, ifc.wall_inner
    pcb = ifc.pcb
    xb = ifc.xiao()
    usb = ifc.usb_shell()
    face = ifc.usb_face_x()
    alt_x = c[2] + 9.525                  # 隣の Alt の中心
    items = [
        ((o[0], o[2], 0, s.CASE_FLOOR), dict(fc="0.85", ec="k", lw=0.5)),
        # 左の壁: トレイの壁は USB の口の下まで、上はふたの舌（基板を上から落とすため）
        ((o[0], w[0], 0, z["usb_center"] - s.XIAO_USB_H / 2 - s.PORT_CLEAR),
         dict(fc="0.85", ec="k", lw=0.5)),
        ((o[0], w[0], z["usb_center"] + s.XIAO_USB_H / 2 + s.PORT_CLEAR, z["rim"] - s.LID_T),
         dict(fc="#aac", ec="k", lw=0.5)),
        ((pcb[0], pcb[2], z["pcb_bottom"], z["pcb_top"]), dict(fc="#6b6", ec="k", lw=0.5)),
        ((xb[0], xb[2], z["pcb_top"], z["pcb_top"] + 1.25), dict(fc="#9cf", ec="k", lw=0.5)),
        ((face, usb[2], z["usb_center"] - s.XIAO_USB_H / 2, z["usb_center"] + s.XIAO_USB_H / 2),
         dict(fc="0.6", ec="k", lw=0.5)),
        ((xb[2] - 17, xb[2] - 4, z["pcb_top"] + 1.25, z["pcb_top"] + 3.25),
         dict(fc="#bde", ec="k", lw=0.4)),
        ((o[0], ifc.cover("left")[2], z["rim"] - s.LID_T, z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
        ((ifc.cover("left")[2] - s.LID_T, ifc.cover("left")[2], z["pcb_top"] + 0.2, z["rim"]),
         dict(fc="#aac", ec="k", lw=0.5)),
        ((ifc.antenna_chip()[0], ifc.antenna_chip()[2], z["pcb_top"] + 1.25, z["pcb_top"] + 1.75),
         dict(fc="r", ec="k", lw=0.3)),
        # 利用者が挿すプラグ（挿しきった状態）: 樹脂の面は口から USB_SHELL_EXPOSED 手前
        ((face - s.USB_SHELL_EXPOSED, face - s.USB_SHELL_EXPOSED + 6.65,
          z["usb_center"] - s.USB_PLUG_SHELL[1] / 2, z["usb_center"] + s.USB_PLUG_SHELL[1] / 2),
         dict(fc="#ccc", ec="k", lw=0.4, ls="--")),
        ((face - s.USB_SHELL_EXPOSED - 12, face - s.USB_SHELL_EXPOSED,
          z["usb_center"] - s.USB_PLUG_BODY_H / 2, z["usb_center"] + s.USB_PLUG_BODY_H / 2),
         dict(fc="#eee", ec="k", lw=0.4, ls="--")),
        # 隣の Alt: スイッチとキャップ（押し切り）
        ((alt_x - 6.9, alt_x + 6.9, z["pcb_top"], z["plate_top"]), dict(fc="0.7", ec="k", lw=0.4)),
        ((alt_x - 7.5, alt_x + 7.5, z["plate_top"], z["switch_top"]), dict(fc="0.7", ec="k", lw=0.4)),
        ((alt_x - 9.525 + s.KEYCAP_GAP, alt_x + 9.525 - s.KEYCAP_GAP, z["keycap_top"] - s.KEYCAP_TOP_T,
          z["keycap_top"]), dict(fc="#fed", ec="k", lw=0.4)),
        ((alt_x - 9.525 + s.KEYCAP_GAP, alt_x + 9.525 - s.KEYCAP_GAP, z["keycap_bottomed"] - s.KEYCAP_TOP_T,
          z["keycap_bottomed"]), dict(fill=False, ec="r", lw=0.6, ls=":")),
        ((c[2], alt_x + 12, z["plate_bottom"], z["plate_top"]), dict(fc="#ddb", ec="k", lw=0.4)),
    ]
    section_rects(a2, items)
    a2.plot([s.MOUNTS["main"][3][0]] * 2, [z["screw_head"], z["screw_head"] + s.SCREW_L], color="k", lw=2)
    a2.axhline(0, color="k", lw=1)
    for name in ("pcb_top", "plate_top", "rim", "keycap_top"):
        a2.axhline(z[name], color="0.6", lw=0.3, ls=":")
        a2.text(o[0] - 21, z[name], f"{name} {z[name]:.2f}", fontsize=7, va="center")
    a2.text(face - 11, z["usb_center"] + 4, f"USB 中心 z={z['usb_center']:.2f}\n口は外面から "
            f"{s.USB_RECESS} 内側\nプラグの樹脂 {s.USB_PLUG_BODY_W}×{s.USB_PLUG_BODY_H}", fontsize=7)
    a2.text(alt_x - 8, z["keycap_top"] + 0.6, "隣の Alt のキャップ（赤点線は押し切り）", fontsize=7)
    a2.set_xlim(o[0] - 22, alt_x + 12)
    a2.set_ylim(-1, z["keycap_top"] + 3)
    a2.set_aspect("equal")
    a2.set_title("断面 A（y = %.2f）: 床・基板・XIAO・USB-C とプラグ・ふた・隣のキー" % y0, fontsize=9)
    a2.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "interface_corner_left.png", dpi=130)
    plt.close(fig)


def right_corner(ifc):
    s, z = ifc.s, ifc.z()
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(11, 16),
                                     gridspec_kw=dict(height_ratios=[1.1, 1, 1]))
    plan(a1, ifc)
    c = ifc.corners()["right"]
    a1.set_xlim(c[0] - 12, ifc.case_outer[2] + 4)
    a1.set_ylim(ifc.case_outer[1] - 3, c[3] + 12)
    hy = s.HOLDER_AT[1]
    a1.axhline(hy, color="k", lw=0.4, ls="-.")
    a1.axvline(s.PSW_AT[0], color="k", lw=0.4, ls="-.")
    a1.text(c[0] - 11, hy + 0.5, "断面 B", fontsize=8)
    a1.text(s.PSW_AT[0] + 0.3, c[3] + 8, "断面 C", fontsize=8)
    a1.set_title("右の角（平面）: ホルダ・CR1632（円）・ふたの柱（橙）・電源スイッチ SS-12D00G3（紫・表）・"
                 "足（黄）・レバー（黒 = 入の位置・灰 = 動く範囲）・ふたの穴（赤）", fontsize=9)
    o, w, pcb = ifc.case_outer, ifc.wall_inner, ifc.pcb
    cov = ifc.cover("right")
    hb = ifc.holder_body()
    (cx, _), cr = ifc.cell()
    (px, _), pr = ifc.lid_pillar()
    base = [
        ((o[0] - 2, o[2], 0, s.CASE_FLOOR), dict(fc="0.85", ec="k", lw=0.5)),
        ((w[2], o[2], 0, z["rim"] - s.LID_T), dict(fc="0.85", ec="k", lw=0.5)),
        ((c[0] - 12, pcb[2], z["pcb_bottom"], z["pcb_top"]), dict(fc="#6b6", ec="k", lw=0.5)),
        # ふたの天板（y = ホルダの中心はレバーの穴を通るので、穴の左右に分けて描く）
        ((cov[0], slot_of(ifc)[0], z["rim"] - s.LID_T, z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
        ((slot_of(ifc)[2], cov[2], z["rim"] - s.LID_T, z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
        ((cov[0], cov[0] + s.LID_T, z["pcb_top"] + 0.2, z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
    ]
    items = base + [
        ((hb[0], hb[2], z["pcb_top"], z["holder_top"]), dict(fc="#fd9", ec="k", lw=0.5, alpha=0.6)),
        ((cx - cr, cx + cr, z["pcb_top"] + 1.0, z["pcb_top"] + 1.0 + s.CELL_T),
         dict(fc="0.5", ec="k", lw=0.5)),
        ((px - pr, px + pr, s.CASE_FLOOR, z["lid_bottom"]), dict(fc="#fc9", ec="k", lw=0.5)),
        ((px - 1.6, px + 1.6, z["lid_bottom"] - 4.0, z["lid_bottom"]), dict(fc="#c96", ec="k", lw=0.4)),
        # 電源スイッチ（この断面は真ん中の足を通る）: 本体・レバー（先は名目）・足
        ((ifc.psw_body()[0], ifc.psw_body()[2], z["psw_seat"], z["psw_top"]), dict(fc="#c9f", ec="k", lw=0.5)),
        ((ifc.psw_lever(1)[0], ifc.psw_lever(1)[2], z["psw_top"], z["psw_tip"]), dict(fc="k")),
        ((s.PSW_AT[0] - s.PSW_PIN[0] / 2, s.PSW_AT[0] + s.PSW_PIN[0] / 2, z["psw_pin_end"], z["psw_seat"]),
         dict(fc="#c80", ec="k", lw=0.3)),
    ]
    section_rects(a2, items)
    # 電池の出し入れ: 傾けて + 側（右端）のクリップの下へ差し込み、反対側を押し下げる
    import math
    ang = math.radians(15)
    z0 = z["pcb_top"] + 1.0
    hx, hz = cx + cr, z0
    corners = [(cx - cr, z0), (cx + cr, z0), (cx + cr, z0 + s.CELL_T), (cx - cr, z0 + s.CELL_T)]
    rot = [(hx + (x - hx) * math.cos(ang) - (zz - hz) * math.sin(ang),
            hz + (x - hx) * math.sin(ang) * -1 + (zz - hz) * math.cos(ang)) for x, zz in corners]
    a2.add_patch(Polygon(rot, closed=True, fill=False, ec="r", ls="--", lw=0.8))
    zc = z0 + s.CELL_T
    a2.annotate("", xy=(cx, zc + 1), xytext=(cx - 6, zc + 9),
                arrowprops=dict(arrowstyle="->", color="r"))
    a2.text(cx - 20, zc + 9.5, "ふたを外し、電池を傾けて右端のクリップの下へ入れ、左を押し下げる\n"
            "（取り出しは左の縁を爪で起こす。ホルダの左は柱まで空いている）", fontsize=7, color="r")
    for name in ("pcb_top", "holder_top", "lid_bottom", "rim"):
        a2.axhline(z[name], color="0.6", lw=0.3, ls=":")
        a2.text(c[0] - 11.5, z[name], f"{name} {z[name]:.2f}", fontsize=7, va="center")
    a2.axhline(0, color="k", lw=1)
    a2.set_xlim(c[0] - 12, o[2] + 3)
    a2.set_ylim(-1, z["rim"] + 12)
    a2.set_aspect("equal")
    a2.set_title("断面 B（y = %.2f）: ホルダ・電池・ふた（天板 %.1f）・ふたの柱とインサート・電源スイッチ（紫）" %
                 (hy, s.LID_T), fontsize=9)
    a2.grid(alpha=0.2)
    # 断面 C（電源スイッチの足の並び・x = PSW_AT.x の y-z）
    x0 = s.PSW_AT[0]
    pb = ifc.psw_body()
    sl = slot_of(ifc)
    on = ifc.psw_lever(s.PSW_ON)
    off = ifc.psw_lever(-s.PSW_ON)
    tip = ifc.psw_tip_range()
    cy0, cy1 = ifc.cover("right")[1], ifc.cover("right")[3]
    items = [
        ((o[1], cy1 + 3, 0, s.CASE_FLOOR), dict(fc="0.85", ec="k", lw=0.5)),
        ((pcb[1], cy1 + 3, z["pcb_bottom"], z["pcb_top"]), dict(fc="#6b6", ec="k", lw=0.5)),
        ((cy0, sl[1], z["lid_bottom"], z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
        ((sl[3], cy1, z["lid_bottom"], z["rim"]), dict(fc="#aac", ec="k", lw=0.5)),
        ((pb[1], pb[3], z["psw_seat"], z["psw_top"] + s.PSW_H_TOL), dict(fc="#c9f", ec="k", lw=0.6)),
        ((on[1], on[3], z["psw_top"], tip[1]), dict(fc="k")),
        ((off[1], off[3], z["psw_top"], tip[1]), dict(fill=False, ec="k", lw=0.6, ls="--")),
    ]
    for _, py in ifc.psw_pins():
        items.append(((py - s.PSW_PIN[1] / 2, py + s.PSW_PIN[1] / 2, z["psw_pin_end"], z["psw_seat"]),
                      dict(fc="#c80", ec="k", lw=0.3)))
    section_rects(a3, items)
    a3.axhspan(tip[0], tip[2], xmin=0, xmax=1, color="r", alpha=0.08)
    a3.text(o[1] - 7.5, z["rim"] + 0.9,
            f"ふたの穴 {sl[3] - sl[1]:.1f}（y）× {sl[2] - sl[0]:.1f}（x）。レバーの先は名目 {tip[1]:.2f}"
            f"（ふたの上面 {z['rim']:.2f} より {z['rim'] - tip[1]:+.2f} 下）、公差で {tip[0]:.2f}〜{tip[2]:.2f}（薄い赤）。\n"
            f"本体は爪 {s.PSW_TAB} で浮く。足は基板の下面から {s.PSW_PIN_TRIM} に切る（床まで {z['psw_pin_end'] - s.CASE_FLOOR:.1f}）。"
            f"黒 = 入（{'奥' if s.PSW_ON > 0 else '手前'}）・点線 = 切", fontsize=7, color="r")
    for name in ("floor_top", "psw_pin_end", "pcb_bottom", "pcb_top", "psw_seat", "psw_top", "lid_bottom", "rim"):
        a3.axhline(z[name], color="0.6", lw=0.3, ls=":")
        a3.text(o[1] - 7.5, z[name], f"{name} {z[name]:.2f}", fontsize=7, va="center")
    a3.axhline(0, color="k", lw=1)
    a3.set_xlim(o[1] - 8, cy1 + 3)
    a3.set_ylim(-1, z["rim"] + 4)
    a3.set_aspect("equal")
    a3.set_xlabel("y [mm]")
    a3.set_title("断面 C（x = %.3f）: 電源スイッチ SS-12D00G3（表）・足・レバーとふたの穴" % x0, fontsize=9)
    a3.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "interface_corner_right.png", dpi=130)
    plt.close(fig)


def zstack(ifc):
    s, z = ifc.s, ifc.z()
    fig, ax = plt.subplots(figsize=(12, 6))
    # 左スペースの右のスタビを通る x-z 断面（y = 最下段の中心）
    (px, py, sd) = [p for p in ifc.stab_pivots() if p[1] < -30][1]
    kx = px - sd * 12.0
    items = [
        ((kx - 20, px + 12, 0, s.CASE_FLOOR), dict(fc="0.85", ec="k", lw=0.5)),
        # 参考: 滑り止めの島（四隅だけ。この断面には無い）の上面。破線
        ((px + 4, px + 12, s.CASE_FLOOR, z["island_top"]), dict(fill=False, ec="b", lw=0.6, ls="--")),
        ((kx - 20, px + 12, z["pcb_bottom"], z["pcb_top"]), dict(fc="#6b6", ec="k", lw=0.5)),
        ((kx - 20, px + 12, z["plate_bottom"], z["plate_top"]), dict(fc="#ddb", ec="k", lw=0.5)),
        ((kx - 6.9, kx + 6.9, z["pcb_top"], z["plate_top"]), dict(fc="0.7", ec="k", lw=0.4)),
        ((kx - 7.5, kx + 7.5, z["plate_top"], z["switch_top"]), dict(fc="0.7", ec="k", lw=0.4)),
        ((kx - 1.5, kx + 1.5, z["switch_top"], z["stem_top"]), dict(fc="0.5", ec="k", lw=0.4)),
        ((kx - 20, px + 12, z["keycap_top"] - s.KEYCAP_TOP_T, z["keycap_top"]),
         dict(fc="#fed", ec="k", lw=0.4)),
        ((kx - 0.6, kx + 0.6, z["pin_tip"], z["pcb_top"]), dict(fc="#c80", ec="k", lw=0.3)),
        ((px - 3.16, px + 3.16, z["stab_bottom"], z["plate_top"]), dict(fc="m", alpha=0.4, ec="k", lw=0.4)),
        ((px - 3.65, px + 3.65, z["pcb_bottom"], z["pcb_top"]), dict(fc="w", ec="m", lw=0.8, ls="--")),
        ((kx + 7.6 - 0.8, kx + 7.6 + 0.8, z["pcb_bottom"] - 1.25, z["pcb_bottom"]),
         dict(fc="#333", ec="k", lw=0.3)),
    ]
    section_rects(ax, items)
    for name, v in sorted(z.items(), key=lambda kv: kv[1]):
        if name in ("xiao_top", "holder_top", "usb_center", "lid_bottom", "island_top") or name.startswith("psw_"):
            continue
        ax.axhline(v, color="0.6", lw=0.3, ls=":")
        ax.text(px + 12.5, v, f"{name} {v:.2f}", fontsize=7, va="center")
    ax.axhline(0, color="k", lw=1)
    worst = z["pcb_bottom"] + s.PCB_T * (1 - s.PCB_T_TOL) - (s.SWITCH_PIN_L + s.SWITCH_PIN_TOL)
    ax.text(kx - 19, z["pin_tip"] - 0.9, f"足の先 {z['pin_tip']:.2f}（最悪 {worst:.2f}・"
            f"床の上面 {s.CASE_FLOOR}）", fontsize=7)
    ax.text(px + 4, z["island_top"] + 0.2, f"滑り止めの島 {z['island_top']:.2f}（四隅だけ・裏に出る物の下を避ける）",
            fontsize=6, color="b")
    ax.text(px - 3, z["stab_bottom"] - 0.9, f"スタビの下端（最低）{z['stab_bottom']:.2f}", fontsize=7,
            color="m")
    ax.set_xlim(kx - 20, px + 26)
    ax.set_ylim(-1, z["keycap_top"] + 2)
    ax.set_aspect("equal")
    ax.set_title("高さの積み上げ（左スペースのスイッチとスタビを通る断面）: 床 %.1f・下の空き %.1f・"
                 "基板 %.1f・キャップ上面まで %.2f" % (s.CASE_FLOOR, s.UNDER_PCB, s.PCB_T,
                                                    z["keycap_top"]), fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "interface_zstack.png", dpi=130)
    plt.close(fig)


def seams(ifc):
    o = ifc.case_outer
    opts = [("A: まっすぐ x = 0（左右対称）", (0.0, 0.0)),
            ("B: まっすぐ x = 4.76（手前のスペースの隙間）", (4.7625, 4.7625)),
            ("C（既定）: 奥は 7|8 の隙間 9.53・手前はスペースの隙間 4.76", tuple(ifc.s.CASE_SEAM))]
    fig, axes = plt.subplots(3, 1, figsize=(12, 14))
    for ax, (title, (back, front)) in zip(axes, opts):
        plan(ax, ifc)
        ax.plot([back, back, front, front], [o[3], 0, 0, o[1]], color="r", lw=2.2)
        lw_ = max(back, front) - o[0]
        rw_ = o[2] - min(back, front)
        ax.text(o[0] + 2, o[3] + 2, f"左 {lw_:.1f} × {size(o)[1]:.1f}", fontsize=9)
        ax.text(o[2] - 50, o[3] + 2, f"右 {rw_:.1f} × {size(o)[1]:.1f}", fontsize=9)
        ok = max(lw_, rw_) <= ifc.s.PRINT_MAX
        ax.set_title(f"{title}   最大 {max(lw_, rw_):.1f}mm {'≦' if ok else '＞'} "
                     f"{ifc.s.PRINT_MAX}（A1 mini）。橙はプレートの継ぎ目（キーの境目）", fontsize=10)
        ax.set_xlim(o[0] - 3, o[2] + 3)
        ax.set_ylim(o[1] - 3, o[3] + 6)
    fig.tight_layout()
    fig.savefig(OUT / "interface_seams.png", dpi=110)
    plt.close(fig)


def whole(ifc):
    fig, ax = plt.subplots(figsize=(16, 6.5))
    plan(ax, ifc)
    o = ifc.case_outer
    back, front = ifc.s.CASE_SEAM
    ax.plot([back, back, front, front], [o[3], 0, 0, o[1]], color="r", lw=1.6)
    for i, m in enumerate(ifc.mounts()):
        ax.text(m[0] + 3, m[1] + 2.5, f"H{i}", fontsize=8)
    ax.set_xlim(o[0] - 3, o[2] + 3)
    ax.set_ylim(o[1] - 3, o[3] + 3)
    ax.set_title("CCKB 平面: 外形 %.2f×%.2f・取付 %d（六角＝ナット・水色＝トレイのボス）・支え %d（水色の点）・"
                 "スタビの逃げ（紫）・プレートの継ぎ目（橙）・トレイの継ぎ目（赤）" %
                 (size(o)[0], size(o)[1], len(ifc.mounts()), len(ifc.s.SUPPORTS)), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "interface_plan.png", dpi=120)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ifc = Interface()
    for f in (whole, left_corner, right_corner, zstack, seams):
        f(ifc)
    for p in sorted(OUT.glob("interface_*.png")):
        print("OK", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
