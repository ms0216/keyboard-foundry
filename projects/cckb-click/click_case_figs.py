"""cckb-click の本番の組み立ての絵。**作った立体そのものを切って描く**（寸法から描き直さない）。縦横は実寸比。

  main_sections.png   断面 6 枚: キー 2 個（置いたとき・押し切り）／外周のねじ／XIAO と USB の切り欠き／電池の口と指の切り欠き／電源スイッチのつまみ
  main_top.png        上から（枠の上面の高さで切る）と、枠の下（基板の上 1.5）で切った図。柱・壁・部品・ねじ・継ぎ目
  main_tilt.png       2.25u と 1u の縁を押し切った傾き（公差の端）と、その下の部品
  coupon_screw.png    ねじの試し刷り（本番の枠から切り出した壁と当て板）
  main_corner.png     右手前の角: つまみの切り欠き・電池の口・ねじで留める蓋を、上から・断面で
  coupon_corner.png   角の試し刷り（枠の切れ端・当て板・つまみと電池の代わり・蓋）
  cover_screw.png     **電池の蓋（ねじ 2 本で留める）の説明**: ねじを通る断面・電池の中心の断面・上から・電池の替え方
  coupon_cover_howto.png  蓋の試し刷り（角の試し刷り）の組み方と、手で見る所

    .venv/bin/python3 projects/cckb-click/click_case.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Compound, Plane, Pos  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

import click_case as C  # noqa: E402
import click_figs as F  # noqa: E402
import click_parts as P  # noqa: E402

LAY, S = C.LAY, C.S
COL = {"frame": "#c8c8c8", "frame2": "#b4bcc6", "cap": "#f2b0b0", "pcb": "#7fb686", "sw": "#555555", "part": "#b98a55",
       "xiao": "#6f8fd0", "bat": "#d9d9d9", "screw": "#e0b020", "sheet": "#404040", "plug": "#9a9a9a", "cover": "#e08a3c",
       "knob": "#111111", "clip": "#7a5cc0"}
RED = "#c00000"


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


def _scene(stem=None, mode="rest", keys=None, cover=True):
    """[(色, 立体)]。mode = rest（ステムに載る）/ pressed / 傾き（"+x" など。keys に効く）。cover=False で電池の蓋とそのねじを外す。"""
    halves = C.frame_halves()
    rest = min(0.0, (S.SW_STEM_TOP if stem is None else stem) - P.levels(S)["pad"])
    caps = []
    for k in LAY.keys:
        if keys is not None and k.i in keys and mode != "rest":
            caps.append(C.cap_pose(k, mode))
        else:
            caps.append(Pos(0, 0, rest) * C.cap_pose(k, "latched"))
    bp = C.board_parts()
    sw_stem = None if mode == "rest" else S.SW_BODY_H + 0.1
    sws = C.switch_solids(LAY, stem)
    if keys is not None and mode != "rest":
        low = C.switch_solids(LAY, sw_stem)
        sws = {n: (low[n] if n in {f"SW{i}" for i in keys} else v) for n, v in sws.items()}
    return [(COL["sheet"], C.sheet_solid()), (COL["pcb"], C.pcb_solid()),
            (COL["screw"], Compound(list(C.screw_solids(cover=cover).values()))),
            (COL["sw"], Compound(list(sws.values()))),
            (COL["part"], Compound([v for n, v in bp.items() if n not in ("U_MCU", "BT1")])),
            (COL["xiao"], bp["U_MCU"]), (COL["bat"], Compound([bp["BT1"], C.cell_solid()])),
            (COL["frame"], halves["left"]), (COL["frame2"], halves["right"]),
            (COL["cap"], Compound(caps))] + ([(COL["cover"], C.cover_solid())] if cover else [])


def _draw(ax, scene, cut, lim, title, levels=()):
    for color, part in scene:
        F.fill(ax, cut(part), color, lw=0.5)
    for z, text in levels:
        ax.plot(lim[:2], [z, z], ":", color="#555", lw=0.5)
        ax.text(lim[1] - 0.1, z + 0.04, text, fontsize=7, ha="right", va="bottom", color="#222")
    ax.set_xlim(lim[0], lim[1])
    ax.set_ylim(lim[2], lim[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)


def sections(out):
    z = LAY.z()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0"),
          (z["cap_top"], "キャップの上面 6.0"), (z["desk"], f"机 {z['desk']:.1f}")]
    rest = _scene()
    k = next(k for k in LAY.keys if k.label == "G")
    pressed = _scene(mode="pressed", keys={k.i, k.i + 1})
    fig, axs = plt.subplots(3, 2, figsize=(17, 13))
    zl = (-2.6, 6.6)
    _draw(axs[0][0], rest, lambda p: F.xz(p, k.y), (k.x - 12, k.x + 31, *zl), f"キー 2 個（{k.label} と右隣）・置いたとき（ステム 3.4 に載る）", lv)
    _draw(axs[0][1], pressed, lambda p: F.xz(p, k.y), (k.x - 12, k.x + 31, *zl), "同じ所・2 個とも押し切り（公差の端: 1.0 沈む）", lv)
    sx = S.SCREWS_PERIMETER[3][0]
    _draw(axs[1][0], rest, lambda p: yz(p, sx), (24, 52, *zl), f"奥の壁のねじ（x {sx}）: 基板の下から M2×4・頭はシートの厚さの中", lv)
    _draw(axs[1][1], rest, lambda p: F.xz(p, S.XIAO_AT[1]), (-148, -112, *zl), "左の角: XIAO と USB の切り欠き（y は XIAO の中心）", lv)
    cx = S.CLIP_AT[0]
    _draw(axs[2][0], rest, lambda p: yz(p, cx), (-52, -26, *zl), "右の角: 電池クリップ・電池の口（手前の壁）・蓋（橙。x は電池の中心）", lv)
    _draw(axs[2][1], rest, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (128, 148, *zl),
          "右の縁: 電源スイッチ（つまみが入の位置の y）。つまみは枠の外面の内側・壁は上まで切り欠き", lv)
    fig.suptitle("cckb-click の断面（作った立体を切った物。灰 = 枠・赤 = キャップ・緑 = 基板・黒 = スイッチ・茶 = 部品・黄 = ねじ）", fontsize=12)
    fig.tight_layout()
    p = out / "main_sections.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def top(out):
    scene = _scene()
    f = LAY.frame
    fig, axs = plt.subplots(2, 1, figsize=(20, 14.5))
    lim = (f[0] - 2, f[2] + 2, f[1] - 2, f[3] + 2)
    _draw(axs[0], scene, lambda p: F.xy(p, 4.5), lim, "枠の上面の少し下（z 4.5）で切った図: 枠（左右で色を分けた）・キャップ・角の屋根・USB と電池の切り欠き")
    _draw(axs[1], scene, lambda p: F.xy(p, 1.0), lim, "基板の上 1.0 で切った図: 外周の壁・柱・ねじの所の厚い壁・スイッチ・ダイオード・XIAO・電池クリップ・電源スイッチ")
    for ax in axs:
        xs, ys = zip(*LAY.seam_path())
        ax.plot(xs, ys, "--", color="#d00000", lw=0.8)
    for ref, c, kind in LAY.screws():
        axs[1].plot(*c, "o", ms=5, mfc="none", mec="#b06000" if kind == "perimeter" else "#888888")
    fig.tight_layout()
    p = out / "main_top.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def tilt(out):
    z = LAY.z()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0")]
    wide = next(k for k in LAY.keys if k.label == "Enter")
    one = next(k for k in LAY.keys if k.label == "G")
    fig, axs = plt.subplots(2, 2, figsize=(18, 8))
    for row, (k, modes) in enumerate(((wide, ("+x", "-x")), (one, ("+x", "+y")))):
        for col, m in enumerate(modes):
            scene = _scene(mode=m, keys={k.i})
            half = k.w * 19.05 / 2 + 6
            if m[1] == "x":
                _draw(axs[row][col], scene, lambda p: F.xz(p, k.y - 5.6), (k.x - half, k.x + half, -2.4, 6.6),
                      f"{k.label}（{k.w}u）の {m} の縁を押し切り・ダイオードを通る面（y = キーの中心 − 5.6）", lv)
            else:
                _draw(axs[row][col], scene, lambda p: yz(p, k.x + 1.2), (k.y - 14, k.y + 14, -2.4, 6.6),
                      f"{k.label}（{k.w}u）の {m} の縁を押し切り・ダイオードを通る面（x = キーの中心 ＋ 1.2）", lv)
    fig.suptitle("縁を押し切った傾き（公差の端: 真ん中が 1.0 沈むまで。真ん中のスイッチの本体は無いものとして回した = 実物より深い）", fontsize=11)
    fig.tight_layout()
    p = out / "main_tilt.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


def screw_coupon(out):
    """ねじの試し刷り: 上から（基板の上 1.0 で切る）と、ねじを通る断面（ふつうの壁・厚くした壁・左の壁）。"""
    sc = C.screw_coupon()
    boxes = C.screw_coupon_boxes()
    d, depth = LAY.pilot()
    fig, axs = plt.subplots(2, 3, figsize=(18, 9))
    axs[0][0].remove()
    axs[0][1].remove()
    scene = lambda n: [(COL["pcb"], sc[f"base_{n}"]), (COL["frame"], sc[f"frame_{n}"])]      # noqa: E731
    bb, screws, thick = boxes["back"]
    ax = plt.subplot2grid((2, 3), (0, 0), colspan=2, fig=fig)
    _draw(ax, scene("back"), lambda p: F.xy(p, 1.0), (bb[0] - 2, bb[2] + 2, bb[1] - 2, bb[3] + 2),
          "奥の壁の切れ端（基板の上 1.0 で切った図）: ねじ 3 本。右の 1 本だけ壁を穴の中へ 0.5 厚くした（その側の端の角を落としてある）")
    for i, (x, y) in enumerate(screws):
        ax.text(x, bb[1] - 1.2, f"{i + 1} {'厚い（内の肉 1.2）' if (x, y) == thick else 'ふつう（内の肉 0.7）'}", ha="center", fontsize=9)
    sb, (sscrew,), _ = boxes["side"]
    _draw(axs[0][2], scene("side"), lambda p: F.xy(p, 1.0), (sb[0] - 2, sb[2] + 2, sb[1] - 2, sb[3] + 2),
          "左の壁の切れ端: ねじ 1 本（壁を厚くする幅が狭い所。斜めの肉 0.49）")
    axs[0][2].text(sscrew[0] + 4.5, sscrew[1], "4", fontsize=9)
    zl = (-2.2, 5.6)
    lv = [(0.0, "当て板の上面 0（基板の上面）"), (depth, f"下穴の底 {depth}"), (S.SCREW_L - S.PCB_T, f"M2×4 の先 {S.SCREW_L - S.PCB_T:.1f}")]
    _draw(axs[1][0], scene("back"), lambda p: yz(p, screws[0][0]), (bb[1] - 1, bb[3] + 1, *zl), "1 のねじを通る断面（ふつう）", lv)
    _draw(axs[1][1], scene("back"), lambda p: yz(p, thick[0]), (bb[1] - 1, bb[3] + 1, *zl), "3 のねじを通る断面（厚くした壁）", lv)
    _draw(axs[1][2], scene("side"), lambda p: F.xz(p, sscrew[1]), (sb[0] - 1, sb[2] + 1, *zl), "4 のねじを通る断面（左の壁）", lv)
    fig.suptitle("ねじの試し刷り coupon_screw（本番の枠から切り出した壁 ＋ 厚さ 1.6 の当て板。灰 = 枠・緑 = 当て板）", fontsize=12)
    fig.tight_layout()
    p = out / "coupon_screw.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def corner(out):
    """右手前の角: 上から（蓋あり・なし）・つまみの高さで切った図・断面 3 枚（電池の中心／蓋のねじ／つまみ）。"""
    z = LAY.z()
    f = LAY.frame
    cv = LAY.cover()
    lv = [(0.0, "基板の上面 0"), (z["frame_under"], "枠の下面 3.0"), (z["frame_top"], "枠の上面 5.0")]
    with_c, without = _scene(), _scene(cover=False)
    clip = [(COL["clip"], C.clip_solid())]
    knobs = [(COL["knob"], C.knob_solid(1)), ("#888888", C.knob_solid(-1))]
    fig, axs = plt.subplots(2, 3, figsize=(20, 11))
    lim = (106, f[2] + 1.5, f[1] - 1.5, -29)
    _draw(axs[0][0], with_c, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）・蓋（橙）を付けた図。枠の上面・外面と面一")
    _draw(axs[0][1], without, lambda p: F.xy(p, 4.65), lim, "同じ・蓋とねじを外した図（電池の上面が口から見える）")
    _draw(axs[0][2], with_c + knobs, lambda p: F.xy(p, 0.7), lim, "基板の上 0.7 で切った図。蓋の足 2 つとねじ（黄）・つまみ（黒 = 入・灰 = 切）")
    for ax in axs[0]:
        ax.plot([f[2], f[2]], [lim[2], lim[3]], ":", color="#d00000", lw=0.6)
        ax.plot([lim[0], lim[1]], [f[1], f[1]], ":", color="#d00000", lw=0.6)
    zl = (-2.4, 6.0)
    _draw(axs[1][0], with_c, lambda p: yz(p, S.CLIP_AT[0]), (-52, -40, *zl), "断面（電池の中心 x）: 手前の板と電池の隙 0.51", lv)
    _draw(axs[1][1], [s for s in with_c if s[0] != COL["bat"]] + [(COL["bat"], C.cell_solid())] + clip, lambda p: yz(p, cv["screws"][0][0]),
          (-52, -40, *zl), "断面（蓋のねじ x 115）: 基板の下から M2×4 → 蓋の足。紫 = クリップの板（図面）", lv)
    on = _scene() + [(COL["knob"], C.knob_solid(1))]
    _draw(axs[1][2], on, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_ON * S.PSW_TRAVEL / 2), (136, 148, *zl),
          f"断面（つまみが入の y）: つまみの先は枠の外面（赤の点線）の {f[2] - LAY.psw_knob(1)[2]:.2f} 内側・内側の上の縁は斜め", lv)
    axs[1][2].plot([f[2], f[2]], zl, ":", color="#d00000", lw=0.6)
    fig.suptitle("右手前の角（作った立体を切った物）: 電源スイッチのつまみの切り欠きと、電池の口・ねじ 2 本で留める蓋（橙）", fontsize=12)
    fig.tight_layout()
    p = out / "main_corner.png"
    fig.savefig(p, dpi=80)
    plt.close(fig)
    return p


def corner_coupon(out):
    """角の試し刷り: 上から（2 つの高さ）と断面 2 枚。"""
    cc = C.corner_coupon()
    box = C.corner_coupon_box()
    cv = LAY.cover()
    scene = [(COL["pcb"], cc["base"]), (COL["frame"], cc["frame"]), (COL["bat"], cc["cell"]), (COL["knob"], cc["knob"]), (COL["cover"], cc["cover"]),
             (COL["screw"], Compound(list(C.cover_screw_solids().values())))]
    fig, axs = plt.subplots(2, 2, figsize=(17, 11))
    lim = (box[0] - 3, box[2] + 1.5, box[1] - 1.5, box[3] + 3)
    _draw(axs[0][0], scene, lambda p: F.xy(p, 4.65), lim, "上から（z 4.65）: 枠の切れ端（灰）・蓋（橙）")
    axs[0][1].plot(*zip(*cv["screws"]), "o", ms=14, mfc="none", mec=RED)
    _draw(axs[0][1], scene, lambda p: F.xy(p, 0.7), lim, "当て板の上 0.7: 蓋の足とねじ（赤丸）・スイッチの本体の代わり・クリップの代わり（止めと案内）・電池の代わり")
    zl = (-2.2, 5.6)
    lv = [(0.0, "当て板の上面 0（基板の上面）"), (5.0, "枠の上面 5.0")]
    _draw(axs[1][0], scene, lambda p: yz(p, cv["screws"][0][0]), (box[1] - 1, box[3] + 3, *zl), "断面（蓋のねじ x 115）", lv)
    _draw(axs[1][1], scene, lambda p: F.xz(p, S.PSW_AT[1] + S.PSW_TRAVEL / 2), (box[0] - 3, box[2] + 1, *zl), "断面（つまみが入の y）", lv)
    fig.suptitle("角の試し刷り coupon_corner = 蓋の試し刷り（本番の枠から切り出した右手前の角 ＋ 当て板。緑 = 当て板と代わりの物・橙 = 蓋・黄 = ねじ・黒 = つまみの小片）", fontsize=12)
    fig.tight_layout()
    p = out / "coupon_corner.png"
    fig.savefig(p, dpi=85)
    plt.close(fig)
    return p


def _plain(ax):
    ax.set_xticks([])
    ax.set_yticks([])


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.6, transform=ax.transAxes)


def _label(ax, text, at, to, color="#222"):
    ax.annotate(text, at, to, fontsize=9.5, color=color, ha="center", va="center",
                arrowprops=dict(arrowstyle="->", color=color, lw=0.9), bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.85))


def _corner_scene(frame, cover_dy=None, screws=True, cell=True, clip=True, board=None):
    """右手前の角の [(色, 立体)]。cover_dy = 蓋を手前へずらす量（None で蓋なし）。"""
    out = [(COL["sheet"], C.sheet_solid()), (COL["pcb"], C.pcb_solid() if board is None else board), (COL["frame"], frame)]
    if cell:
        out.append((COL["bat"], C.cell_solid()))
    if clip:
        out.append((COL["clip"], C.clip_solid()))
    if cover_dy is not None:
        out.append((COL["cover"], Pos(0, -cover_dy, 0) * C.cover_solid()))
    if screws:
        out.append((COL["screw"], Compound(list(C.cover_screw_solids().values()))))
    return out


def cover_screw(out):
    """電池の蓋の説明（利用者に見せる絵）。作った立体を切って描く。数は立体・spec から。"""
    cv = LAY.cover()
    z = LAY.z()
    f = LAY.frame
    frame = C.frame_halves()["right"] & C._box((104.0, f[1] - 1.0, 140.0, -30.0), -1.0, 6.0)
    sx, sy = cv["screws"][0]
    (cx, cy), r = LAY.cell()
    d, depth = LAY.pilot()
    fig = plt.figure(figsize=(16, 13.2))
    gs = fig.add_gridspec(3, 6, height_ratios=[1.35, 0.8, 1.0], hspace=0.2, wspace=0.12, left=0.02, right=0.985, top=0.94, bottom=0.01)
    full = _corner_scene(frame, 0.0)

    # 1. ねじを通る断面
    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, full, lambda p: yz(p, sx), (-52.6, -42.0, -2.9, 6.3), "① ねじを通る面で切った図（横から。左が手前 = 外）")
    _label(ax, "蓋（橙）\n上面は枠と同じ高さ", (-49.6, 4.75), (-50.9, 5.9), RED)
    _label(ax, f"蓋の足\n（基板の上に立つ）", (-49.2, 1.2), (-51.6, 1.6), RED)
    _label(ax, f"ねじ M2×4\n（外周と同じ物）", (sy, 1.0), (-45.6, -0.9))
    _label(ax, "頭は裏（シートの穴の中）", (sy - 1.2, -1.95), (-51.0, -1.1))
    _label(ax, f"クリップの板（紫）\nいちばん低くて 3.5", (-46.6, 3.6), (-44.6, 5.6), "#5a3ca0")
    _label(ax, "電池", (-44.0, 1.6), (-43.2, 4.9), "#555")
    ax.set_xlabel(f"ねじは足の樹脂に {z['screw_grip']:.1f} 掛かる。先は基板の上 {z['screw_grip']:.1f}（基板が薄い側で {z['screw_tip']:.2f}）・下穴の深さ {depth}。"
                  f"クリップの板まで {S.CLIP_H - S.CLIP_SHEET_T - S.CLIP_TOL - z['screw_tip']:.2f}", fontsize=9.5)
    _plain(ax)

    # 2. 電池の中心の断面
    ax = fig.add_subplot(gs[0, 3:])
    _draw(ax, full, lambda p: yz(p, cx), (-52.6, -42.0, -2.9, 6.3), "② 電池の真ん中で切った図（横から）")
    _label(ax, "手前の板\n（口を塞ぐ）", (-50.0, 2.0), (-51.6, -0.9), RED)
    _label(ax, "上の板\n（電池の上を塞ぐ）", (-47.2, 4.65), (-46.0, 5.9), RED)
    _label(ax, "爪を掛ける溝", (-49.0, 4.7), (-50.6, 5.9))
    ax.text(-45.0, 1.6, "電池 CR1632", fontsize=10, ha="center", color="#444")
    ax.set_xlabel(f"手前の板と電池の縁の隙 {(cy - r) - cv['y_front']:.2f}・上の板とクリップの上面の隙 {cv['z_plate'] - z['clip_top']:.1f}", fontsize=9.5)
    _plain(ax)

    # 3. 上から（足の高さ・上面）
    lim = (cv["x0"] - 6.5, cv["x1"] + 6.5, f[1] - 2.2, -37.0)
    ax = fig.add_subplot(gs[1, :2])
    _draw(ax, full, lambda p: F.xy(p, 1.0), lim, "③ 基板の上 1.0 で切った図（上から。下が手前）")
    for (x, y), name in zip(cv["screws"], ("H30", "H31")):
        _label(ax, f"ねじ {name}", (x, y), (x, y + 6.5))
    _label(ax, "足", (cv["boss"][0][0] + 0.6, sy - 1.0), (cv["x0"] - 4.0, f[1] - 1.2), RED)
    _label(ax, "足", (cv["boss"][1][1] - 0.6, sy - 1.0), (cv["x1"] + 4.0, f[1] - 1.2), RED)
    ax.text(cx, cy + 2.0, "電池", fontsize=10, ha="center", color="#444")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 2:4])
    _draw(ax, full, lambda p: F.xy(p, 4.65), lim, "④ 枠の上面のすぐ下で切った図（蓋を付けた所）")
    ax.text(cx, (cv["y0"] + cv["y1"]) / 2, "蓋", fontsize=11, ha="center", va="center", color="white")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 4:])
    off = _corner_scene(frame, None, screws=False)
    _draw(ax, off, lambda p: F.xy(p, 4.65), lim, "⑤ 蓋とねじを外した所（電池が口から見える）")
    ax.annotate("", (cx, f[1] - 1.8), (cx, cy - r + 1.5), arrowprops=dict(arrowstyle="->", color=RED, lw=1.8))
    ax.text(cx + 1.0, f[1] - 1.2, "電池は手前へ", fontsize=9.5, color=RED)
    _plain(ax)

    # 4. 手順
    ax = fig.add_subplot(gs[2, :2])
    pulled = _corner_scene(frame, 5.0, screws=False)
    _draw(ax, pulled, lambda p: yz(p, sx), (-57.5, -42.0, -2.9, 6.3), "⑥ 蓋は手前からまっすぐ滑らせて入れる・抜く")
    ax.annotate("", (-51.0, 2.4), (-55.8, 2.4), arrowprops=dict(arrowstyle="<->", color=RED, lw=1.6))
    _plain(ax)
    _note(fig.add_subplot(gs[2, 2:4]),
          "電池の替え方\n"
          "1. キーボードを裏返す\n"
          "2. 右手前の角の、ねじ 2 本を外す\n"
          "   （底のシートに穴が開いている。＋ドライバー）\n"
          "3. 表に返し、蓋の溝に爪を掛けて手前へ引き抜く\n"
          "4. 電池を爪で押し下げながら手前へ引き出す\n"
          "5. 新しい電池を ＋ を上にして奥まで押し込む\n"
          "6. 蓋を手前から奥まで滑らせる（上面が枠と揃う）\n"
          "7. 裏返して、ねじ 2 本を止まる所まで締める\n"
          "   （樹脂に切るねじ。強く締めない）")
    _note(fig.add_subplot(gs[2, 4:]),
          "知っておくこと\n"
          "・ねじは電池の通り道に立つ。だから電池を替える\n"
          "  たびに 2 本外す（基板の穴の位置は変えられない）\n"
          "・ねじは上からは入れられない: 基板の穴は素通しで、\n"
          "  ねじ山を切る相手は蓋の樹脂しか無い\n"
          "・蓋とねじ 2 本が無くても、キーボードは同じに使える\n"
          "  （電池はクリップが持つ）\n"
          f"・ねじは外周と同じ M2×4。全部で 22 本になる\n"
          "・樹脂のねじ山は、抜き差しで少しずつ弱る。\n"
          "  試し刷りで 5 回まで確かめる。弱ったら蓋だけ刷り直す")
    fig.suptitle("電池の蓋（ねじ 2 本で留める）: 基板はいまのまま・穴 H30・H31 を使う　　橙 = 蓋・黄 = ねじ・緑 = 基板・灰 = 枠と電池・紫 = 電池クリップ・黒 = 底のシート",
                 fontsize=13)
    p = out / "cover_screw.png"
    fig.savefig(p, dpi=96)
    plt.close(fig)
    return p


def coupon_cover_howto(out):
    """蓋の試し刷り（角の試し刷り）の、刷ったあとの組み方と手で見る所。"""
    cc = C.corner_coupon()
    box = C.corner_coupon_box()
    cv = LAY.cover()
    sx, sy = cv["screws"][0]
    plate = C.corner_coupon_plate()
    fig = plt.figure(figsize=(16, 14.0))
    gs = fig.add_gridspec(3, 6, height_ratios=[1.0, 1.15, 0.8], hspace=0.16, wspace=0.12, left=0.02, right=0.985, top=0.94, bottom=0.01)
    ax = fig.add_subplot(gs[0, :3])
    names = ("電池の代わり", "蓋", "つまみの代わり", "当て板（基板の代わり）", "枠の切れ端")
    for name, part in zip(names, sorted(plate.solids(), key=lambda q: (round(q.bounding_box().min.Y, 1), q.bounding_box().min.X))):
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.5, bb.max.Z / 2)), "#d8d8d8", lw=0.5)
        small = bb.size.Y < 8.0                                    # 小さい物は、名前を手前（下）に出す
        ax.text((bb.min.X + bb.max.X) / 2, bb.min.Y - 2.2 if small else (bb.min.Y + bb.max.Y) / 2, name, fontsize=10, ha="center", va="center",
                color=RED, bbox=dict(fc="white", ec=RED, lw=0.6, pad=1.5))
    pb = plate.bounding_box()
    ax.set_xlim(pb.min.X - 8, pb.max.X + 8)
    ax.set_ylim(pb.min.Y - 5, pb.max.Y + 3)
    ax.set_aspect("equal")
    ax.set_title("0. 刷り上がった板を上から（5 個・サポート無し・向きはそのまま）", fontsize=11)
    _plain(ax)
    scene = [(COL["pcb"], cc["base"]), (COL["frame"], cc["frame"]), (COL["bat"], cc["cell"]), (COL["knob"], cc["knob"]), (COL["cover"], cc["cover"]),
             (COL["screw"], Compound(list(C.cover_screw_solids().values())))]
    ax = fig.add_subplot(gs[0, 3:])
    _draw(ax, scene, lambda p: yz(p, sx), (box[1] - 1.5, -40.0, -2.9, 6.3), "ねじを通る面で切った図（組んだ所。左が手前）")
    _label(ax, "蓋の足", (-49.2, 1.2), (-51.3, 2.6), RED)
    _label(ax, "ねじ M2×4", (sy, -0.8), (-45.6, -2.2))
    _label(ax, "当て板", (-44.0, -0.8), (-42.0, -2.2), "#2a6a30")
    _plain(ax)
    lim = (box[0] - 3, box[2] + 1.5, box[1] - 6.5, box[3] + 3)
    ax = fig.add_subplot(gs[1, :2])
    pulled = [s if s[0] != COL["cover"] else (COL["cover"], Pos(0, -5.0, 0) * cc["cover"]) for s in scene[:-1]]
    _draw(ax, pulled, lambda p: F.xy(p, 1.0), lim, "① 当て板に電池の代わりを置き、枠をかぶせ、蓋を手前から")
    ax.annotate("", ((cv["x0"] + cv["x1"]) / 2, cv["y0"] - 0.4), ((cv["x0"] + cv["x1"]) / 2, cv["y0"] - 4.6), arrowprops=dict(arrowstyle="->", color=RED, lw=1.8))
    _plain(ax)
    ax = fig.add_subplot(gs[1, 2:4])
    _draw(ax, scene, lambda p: F.xy(p, 1.0), lim, "② 奥まで入れた所（当て板の上 1.0 で切った図）")
    for x, y in cv["screws"]:
        ax.add_patch(Circle((x, y), 2.4, fc="none", ec=RED, lw=1.2))
    ax.text((cv["x0"] + cv["x1"]) / 2, cv["y0"] - 3.0, "赤丸 = 裏からねじを入れる穴", fontsize=9.5, color=RED, ha="center")
    _plain(ax)
    ax = fig.add_subplot(gs[1, 4:])
    _draw(ax, scene, lambda p: F.xy(p, 4.65), lim, "③ 上から見た所（蓋の上面が枠と揃う）")
    _plain(ax)
    _note(fig.add_subplot(gs[2, :3]),
          "組み方\n"
          "1. 当て板を平らな面を下にして置く。つまみの代わりを溝に落とす\n"
          "2. 電池の代わり（丸い板）を、当て板の真ん中の止めに当てて置く\n"
          "3. 枠の切れ端を、平らな面（刷ったときの下の面）を上にしてかぶせる\n"
          "   左と奥の当てに突き当てる\n"
          "4. 蓋を、平らな面を上にして、手前から奥まで滑らせる\n"
          "5. 全体を手で押さえたまま裏返す。当て板の手前の縁に穴が 3 つ並んでいる\n"
          "   角に近い端の 1 つ（枠のねじ）を先に締めると、枠が当て板に留まって楽\n"
          "   残りの 2 つ（蓋のねじ。電池の左右）に M2×4 を入れて、止まる所まで締める\n"
          "   （止まってから 1/8 回転まで。樹脂に切るねじなので強く締めない）")
    _note(fig.add_subplot(gs[2, 3:]),
          "手で見る所（結果を教えてください）\n"
          "a. 蓋が引っ掛からずに奥まで入るか・きつすぎないか\n"
          "b. ねじ 2 本が、止まる手応えで締まるか（空回りしないか）\n"
          "c. 締めた後、蓋が動かないか・がたつかないか・内へ落ちないか\n"
          "d. 蓋の上面・手前の面が、枠と段なく揃うか\n"
          "e. 蓋の足（ねじの所）に、割れ・白い筋が出ていないか\n"
          "f. ねじを外して蓋を抜き、もう一度付ける × 5 回。何回目まで止まるか\n"
          "g. 蓋とねじを外すと、電池の代わりが爪で出し入れできるか\n"
          "h. 溝に爪を掛けて、蓋を引き抜けるか\n"
          "※ クリップの板（本物は基板の 3.75 上）の代わりは付いていない。\n"
          "   足が板の下に入る所は、基板が届いてから本物で見る")
    fig.suptitle("蓋の試し刷り（coupon_corner_plate_n04.gcode.3mf・A1 mini・0.4 ノズル・サポート無し）の組み方と見る所　　緑 = 当て板・橙 = 蓋・黄 = ねじ",
                 fontsize=13)
    p = out / "coupon_cover_howto.png"
    fig.savefig(p, dpi=96)
    plt.close(fig)
    return p


def render_all(out):
    (out / "cover_spring.png").unlink(missing_ok=True)          # 前の蓋（ばね）の絵。古い絵を、いまの蓋の絵と見間違えない
    return [sections(out), top(out), tilt(out), screw_coupon(out), corner(out), corner_coupon(out), cover_screw(out), coupon_cover_howto(out)]
