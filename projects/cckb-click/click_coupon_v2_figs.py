"""試し刷り v2 の「刷ったあと、どう組んでどこを見るか」の絵（build/cckb-click/coupon_v2_howto.png）。
**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_coupon_v2.numbers() が測った物。

    .venv/bin/python3 projects/cckb-click/click_coupon_v2.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Compound, Cylinder, Pos  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

import click_case as C  # noqa: E402
import click_case_figs as CF  # noqa: E402
import click_coupon_v2 as V  # noqa: E402
import click_figs as F  # noqa: E402

LAY, S = C.LAY, C.S
COL = CF.COL
RED = "#c00000"


def _plain(ax):
    ax.set_xticks([])
    ax.set_yticks([])


def _note(ax, text, size=9.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.55, transform=ax.transAxes)


def _screw(x, y):
    return Compound([Pos(x, y, -S.PCB_T - S.SCREW_HEAD_H) * Cylinder(S.SCREW_HEAD_D / 2, S.SCREW_HEAD_H, align=C.CEN_MIN),
                     Pos(x, y, -S.PCB_T) * Cylinder(S.SCREW_D / 2, S.SCREW_L, align=C.CEN_MIN)])


def howto(out, num=None):
    num = num or V.numbers()
    sc, kn, cs = V.screw_v2(), V.knob_v2(), V.cover_set()
    fig = plt.figure(figsize=(16, 21.5))
    gs = fig.add_gridspec(6, 6, height_ratios=[1.45, 0.8, 1.25, 0.8, 0.95, 0.8], hspace=0.3, wspace=0.25,
                          left=0.03, right=0.985, top=0.955, bottom=0.01)

    # 0. 刷り上がった板を上から
    ax = fig.add_subplot(gs[0, :])
    layout = V.plate_layout()
    kind_col = {"A": "#c8c8c8", "B": "#b4bcc6", "C": "#f0c8a0"}
    for tag, name, part in layout:
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.6, bb.max.Z / 2)), kind_col[tag[0]], lw=0.5)
        ax.text((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, tag, fontsize=12, ha="center", va="center", color=RED,
                bbox=dict(fc="white", ec=RED, lw=0.6, pad=1.5))
    ax.set_xlim(-48, 198)
    ax.set_ylim(-3, 54)
    ax.set_aspect("equal")
    _plain(ax)
    ax.set_title("0. 刷り上がった板を上から見た図（1 枚に 13 個。赤い記号で呼ぶ）　A = ねじ・B = 電源スイッチのつまみ・C = 電池の蓋", fontsize=12, loc="left")
    names = [f"{t} {n}" for t, n, _ in layout]
    ax.text(-47, 52, "\n".join(names[:7]), fontsize=9, va="top", linespacing=1.6)
    ax.text(154, 52, "\n".join(names[7:]), fontsize=9, va="top", linespacing=1.6)

    # A. ねじ
    box, screws, _ = C.screw_coupon_boxes()["back"]
    ax = fig.add_subplot(gs[1, :3])
    CF._draw(ax, [(COL["pcb"], sc["base_back"]), (COL["frame"], sc["frame_back"])], lambda p: F.xy(p, 1.0),
             (box[0] - 1, box[2] + 1, box[1] - 4.5, box[3] + 3.5), "A1（奥の壁）を切った図。外面の溝の数が下穴の径（A3 も同じ）")
    for ((x, y), d), row in zip(sc["holes"]["back"], num["screw"][:3]):
        ax.text(x, box[1] - 1.2, f"φ{d}\n壁の残り {row['flesh']}", ha="center", va="top", fontsize=9)
    for i, ((x, y), d) in enumerate(sc["holes"]["back"]):
        ax.annotate(f"溝 {i + 1} 本", (x + S.COUPON_V2_MARK[3] + 0.6 * i, box[3]), (x + 5.2, box[3] + 2.6), fontsize=9, ha="center",
                    arrowprops=dict(arrowstyle="->", color=RED, lw=0.8), color=RED)
    _plain(ax)
    ax = fig.add_subplot(gs[1, 3])
    (hx, hy), hd = sc["holes"]["back"][1]
    scene = [(COL["pcb"], sc["base_back"]), (COL["frame"], sc["frame_back"]), (COL["screw"], _screw(hx, hy))]
    CF._draw(ax, scene, lambda p: CF.yz(p, hx), (box[1] - 0.5, box[3] + 0.8, -2.6, 8.6), "断面: 当て板の下からねじ")
    ax.text(box[1] - 0.3, 8.4, "黄 = M2×4\n緑 = 当て板（基板の代わり）\n灰 = 枠の壁（刷ったときと上下逆）", fontsize=7.5, va="top")
    _plain(ax)
    _note(fig.add_subplot(gs[1, 4:]),
          "A. ねじ（A1＋A2・A3＋A4）\n"
          "① 枠の切れ端を、刷った向きのまま（平らな面が下）置く\n"
          "② 当て板を穴を合わせて載せ、ねじを 6 本とも締める\n"
          "　 止まった所でやめる（そこから 1/8 回転まで）\n"
          "③ 見る: 止まる手応えがあるか・空回りしないか\n"
          "　 壁（とくに A3 = 薄い側）に割れ・白い筋が無いか\n"
          "④ 抜いて締め直す × 5 回。何回目まで止まるか\n"
          "溝 1 本 = φ1.5（いちばんきつい）・2 本 = φ1.6・3 本 = φ1.7\n"
          "v1 は φ1.8 で、ねじ山の掛かりが半径 0.10 しか無かった\n"
          "（1.7 → 0.15・1.6 → 0.20・1.5 → 0.22）")

    # B. つまみ
    kb = V.knob_box()
    pitch = V.knob_pitch()
    ax = fig.add_subplot(gs[2, :2])
    knobs = Compound([kn["knob_1"], kn["knob_2"]])
    turn = lambda polys: [([(y, -x) for x, y in o], [[(y, -x) for x, y in r] for r in i]) for o, i in polys]      # noqa: E731（外面を手前に）
    CF._draw(ax, [(COL["pcb"], kn["base"]), (COL["frame"], kn["frame"]), (COL["knob"], knobs)], lambda p: turn(F.xy(p, 0.7)),
             (kb[1] - 1, kb[3] + pitch + 3, -(kb[2] + 5.5), -(kb[0] - 5)), "B1＋B2 を上から（つまみの高さで切った図。下が外面）")
    for i, label in enumerate(("(i) いまの位置（上面に点 1 個）", "(ii) 0.75 外（点 2 個）")):
        yc = S.PSW_AT[1] + i * pitch
        ax.text(yc, -(kb[0] - 3.2), label, fontsize=9.5, ha="center", va="center")
        ax.annotate("指", (yc + 2.6, -(kb[2] - 0.3)), (yc + 2.6, -(kb[2] + 4.2)), fontsize=10, color=RED, ha="center",
                    arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
        ax.annotate("つまみ", (yc + 0.8, -(V.shifted(V.KNOB_VARIANTS[i][0]).psw_knob(1)[2] - 0.5)), (yc - 4.6, -(kb[2] + 3.4)), fontsize=9,
                    ha="center", arrowprops=dict(arrowstyle="->", color="#222", lw=0.8))
    _plain(ax)
    for i, (row, name) in enumerate(zip((num["knob"][1], num["knob"][2]), ("(i) いまの位置", "(ii) 0.75 外"))):
        ax = fig.add_subplot(gs[2, 2 + i])
        y = S.PSW_AT[1] + i * pitch + S.PSW_TRAVEL / 2
        scene = [(COL["pcb"], kn["base"]), (COL["frame"], kn["frame"]), (COL["knob"], kn[f"knob_{i + 1}"])]
        CF._draw(ax, scene, lambda p, y=y: F.xz(p, y), (137.5, 153.5, -2.4, 17.6), f"断面 {name}（右が外）")
        ax.add_patch(Circle((row["cx"], row["cz"]), row["r"], fc="#f4c9a8", ec="#a06030", lw=0.8, alpha=0.55))
        ax.plot([LAY.frame[2]] * 2, [-2.4, 6.5], ":", color=RED, lw=0.7)
        ax.plot([137.5, 153.5], [-S.PCB_T - S.BOTTOM_SHEET_T] * 2, "-", color="#555", lw=0.8)
        ax.text(153.2, -2.0, "机", fontsize=8, ha="right", va="bottom", color="#555")
        ax.text(137.9, 17.3, f"つまみの先は外面の {row['tip_in']:.2f} 内\n丸 = 指先の代わり\n（半径 {row['r']} の硬い球・机の上）\n"
                f"つまみの先より奥へ {row['bite']:+.2f}\n（＋ = 届く・− = 届かない）", fontsize=8.5, va="top")
        _plain(ax)
    _note(fig.add_subplot(gs[2, 4:]),
          "B. 電源スイッチのつまみ（B1〜B4）\n"
          "① 当て板 B2 の 2 つの塊の溝に、小片 B3・B4 を落とす\n"
          "　 （T の足が外へ出る向き。どちらも同じ形）\n"
          "② 壁の切れ端 B1 を、上面を上にしてかぶせる\n"
          "　 左と奥の当てに突き当てる。点 1 個の側が (i)\n"
          "③ 机に置いたまま、指の腹で前後に動かす（1.6 mm）\n"
          "　 上から・横から。爪を使わずに動かせるか\n"
          "④ (i) と (ii) を比べる。(ii) で勝手に動きそうか\n"
          "(ii) は基板のスイッチを 0.75 外へ動かす案\n"
          "（JLC の「縁から 2.5 mm」を割る = 頼み方が変わる）\n"
          "切り欠きは v1 より外へ広げ、内側の縁を斜めに落とした")

    # C. 蓋
    cv = LAY.cover()
    stub = cs["frame"]
    y_cut = cv["y0"] + 1.1                              # 山を通る面
    captions = {1: "蓋 1（点 1 個）折り返しばね\n掛かり 0.60・ひずみ {s:.2f} %・引き抜き 約 {h:.1f} N",
                2: "蓋 2（点 2 個）細い腕 2 本\n掛かり 0.45・ひずみ {s:.2f} %・引き抜き 約 {h:.1f} N",
                3: "蓋 3（点 3 個）ばね無し・両端の筋で擦る\nしめしろ 片側 0.10（留まる力は計算できない）"}
    for n in (1, 2, 3):
        ax = fig.add_subplot(gs[3, 2 * (n - 1):2 * n])
        sp = num["cover"][n]["spring"]
        CF._draw(ax, [(COL["frame2"], stub), (COL["cover"], cs[f"cover_{n}"])], lambda p: F.xz(p, y_cut),
                 (cv["x0"] - 1.6, cv["x1"] + 1.6, -0.4, 5.6),
                 captions[n].format(s=sp["strain"] * 100, h=sp["hold"]) if sp else captions[n])
        if n < 3:
            g = V._geom(n)
            for sg in (-1, 1):
                ax.annotate("山", (g["xm"] + sg * sum(g["hook_u"]) / 2, g["z_arm"] + 0.2), (g["xm"] + sg * 5.0, 4.6), fontsize=9, color=RED,
                            ha="center", arrowprops=dict(arrowstyle="->", color=RED, lw=0.8))
        else:
            g = V._geom(3)
            for sg in (-1, 1):
                ax.annotate("筋", (g["xm"] + sg * (g["half"] + 0.1), 0.9), (g["xm"] + sg * 6.0, 2.0), fontsize=9, color=RED,
                            ha="center", arrowprops=dict(arrowstyle="->", color=RED, lw=0.8))
        _plain(ax)
        if n == 1:
            ax.text(0.0, -0.1, "↑ 蓋を手前（外）から見た断面。橙 = 蓋・灰 = 枠の切れ端 C1。v1 の蓋は山の掛かりが 0.25（頂は 1 層 = 0.1 mm だけ）で、留まらなかった",
                    fontsize=9, transform=ax.transAxes, va="top")
    g = V._geom(1)
    xh = g["xm"] + sum(g["hook_u"]) / 2
    for k, (shift, title) in enumerate(((0.0, "蓋 1 の山を横から: 入った所\n（山が溝の中・手前の肉に掛かる）"),
                                        (num["cover"][1]["detent"]["right"][1], "手前へ引く途中\n（山が肉の下をくぐる = 腕が 0.6 たわむ）"))):
        ax = fig.add_subplot(gs[4, k])
        cover = Pos(0, -shift, 0) * cs["cover_1"]
        CF._draw(ax, [(COL["frame2"], stub), (COL["bat"], C.cell_solid()), (COL["cover"], cover)], lambda p: CF.yz(p, xh),
                 (cv["y0"] - 1.6, cv["y0"] + 4.2, 1.6, 5.4), title)
        ax.title.set_fontsize(9)
        ax.text(cv["y0"] - 1.5, 1.75, "← 手前（外）", fontsize=8)
        _plain(ax)
    ax = fig.add_subplot(gs[4, 2:4])
    CF._draw(ax, [(COL["pcb"], cs["base"]), (COL["frame2"], stub), (COL["cover"], Pos(0, -5.5, 0) * cs["cover_1"])],
             lambda p: F.xy(p, 4.65), (cv["x0"] - 8, cv["x1"] + 5, cv["y0"] - 7.5, cv["y1"] + 4.5), "C1＋C2 を上から。蓋は手前から奥へまっすぐ")
    ax.annotate("", ((cv["x0"] + cv["x1"]) / 2, cv["y0"] - 0.6), ((cv["x0"] + cv["x1"]) / 2, cv["y0"] - 5.2),
                arrowprops=dict(arrowstyle="->", color=RED, lw=1.6))
    _plain(ax)
    _note(fig.add_subplot(gs[4, 4:]),
          "C. 電池の蓋（C1〜C5）\n"
          "① 枠の切れ端 C1 を、上面を上にして当て板 C2 に載せる\n"
          "② 蓋を 1 つずつ、手前から奥へ滑らせて入れる\n"
          "③ 見る: カチッと止まるか・傾けて振って落ちないか\n"
          "　 枠の上面・手前の面と段が無いか・がたつくか\n"
          "④ 上面の溝に爪を掛けて手前へ引く → 抜けるか\n"
          "⑤ 留まった蓋は 20 回抜き差し。腕が白くならないか\n"
          "いちばん見込みがあるのは蓋 1")

    # 結果を書く表
    ax = fig.add_subplot(gs[5, :])
    ax.axis("off")
    rows = [["A1 奥の壁 φ1.5／1.6／1.7", "止まる手応え（○×）・割れ・何回目まで", "", "", ""],
            ["A3 左の壁（薄い）φ1.5／1.6／1.7", "同じ。壁の白い筋・ふくらみ", "", "", ""],
            ["B (i) いまの位置", "指の腹で動かせるか（上から／横から）", "", "", ""],
            ["B (ii) 0.75 外", "同じ。勝手に動きそうか", "", "", ""],
            ["C 蓋 1・2・3", "止まるか／落ちないか／抜けるか／20 回後", "", "", ""]]
    table = ax.table(cellText=rows, colLabels=["どれ", "見ること", "1 つ目", "2 つ目", "3 つ目"], loc="upper center",
                     colWidths=[0.2, 0.29, 0.17, 0.17, 0.17])
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.75)
    ax.set_title("結果はここに書いて教えてください（空欄に ○・×・回数）", fontsize=11, loc="left")
    fig.suptitle("試し刷り v2 の組み方と見る所（coupon_v2_plate_n04.gcode.3mf・A1 mini・0.4 ノズル・サポート無し・向きはそのまま）", fontsize=14)
    p = out / "coupon_v2_howto.png"
    fig.savefig(p, dpi=74)                              # 1184 × 1591 px（1600 以下）
    plt.close(fig)
    return p
