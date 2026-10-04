"""手前の縁の試し刷りの絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_coupon_front.numbers()。

  coupon_front_sections.png   断面: いまの形・縁 0.8・縁 0.4（キーの辺の真ん中／つばの所）と、基板の代わりを入れる動き
  coupon_front_howto.png      刷り上がった板・組み方・手で見る所・報告してほしいこと

    .venv/bin/python3 projects/cckb-click/click_coupon_front.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import click_case as C  # noqa: E402
import click_case_figs as CF  # noqa: E402
import click_coupon_front as K  # noqa: E402
import click_figs as F  # noqa: E402

LAY, S = C.LAY, C.S
COL = CF.COL
RED, BLUE = "#c00000", "#1f5fbf"
SCREW = "#d0a000"


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.6, transform=ax.transAxes)


def _dim(ax, y0, y1, z, text, color=RED, up=0.25):
    ax.annotate("", (y0, z), (y1, z), arrowprops=dict(arrowstyle="<->", color=color, lw=1.0))
    ax.text((y0 + y1) / 2, z + up, text, fontsize=9, color=color, ha="center", va="bottom")


def _frame_axes(ax, title, win):
    ax.set_xlim(win[0], win[1])
    ax.set_ylim(win[2], win[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10.5)
    ax.tick_params(labelsize=7)
    ax.axhline(-S.PCB_T - S.BOTTOM_SHEET_T, color="#888", lw=0.6, ls=":")
    ax.text(win[1] - 0.1, -S.PCB_T - S.BOTTOM_SHEET_T - 0.05, "机（シート 0.5 の下面）", fontsize=7, color="#666", ha="right", va="top")


def _scene(m, x, t=S.PCB_T, th=0.0, dy=0.0):
    """縁 m の枠を x で切った [(色, 断面)]。基板の代わりは (th, dy) の姿。"""
    k = K.KS[-1]
    b = K.posed(K.board_in(m, t), m, th, dy)
    out = [(COL["frame"], CF.yz(K.frame(m), x)), (COL["pcb"], CF.yz(b, x)), (COL["cap"], CF.yz(C.cap_pose(k, "latched"), x))]
    if th == 0.0:
        out.append((SCREW, CF.yz(K.screws(m), x)))
    return out


def sections(out, num=None):
    num = num or K.numbers()
    k = K.KS[-1]
    xm, xs, xt = k.x + 8.0, k.x, LAY.hole(k)[0] + 1.5
    win = (-51.6, -40.5, -3.2, 6.6)
    fig, axs = plt.subplots(2, 4, figsize=(21, 10.6))
    fig.subplots_adjust(left=0.03, right=0.99, top=0.9, bottom=0.05, wspace=0.14, hspace=0.24)

    # いまの形（本番の枠・基板・ねじ）
    ax = axs[0][0]
    now = [(CF.COL["sheet"], C.sheet_solid()), (COL["pcb"], C.pcb_solid()), (COL["frame"], C.frame_full()), (COL["cap"], C.cap_pose(k, "latched")),
           (COL["sw"], C.switch_solids()[f"SW{k.i}"]), (SCREW, C.screw_solids()["H10"])]
    for col, part in now:
        F.fill(ax, CF.yz(part, xs), col, lw=0.5)
    _frame_axes(ax, "いまの形: ねじの壁 3.0（Space の真ん中で切った）", win)
    _dim(ax, LAY.frame[1], K.HOLE_Y + S.CAP_CLEAR, 5.6, f"キャップから外面まで {K.HOLE_Y + S.CAP_CLEAR - LAY.frame[1]:.1f}")
    ax.text(-48.2, -2.9, "ねじ（下から）", fontsize=8, ha="center")

    for col_i, m in enumerate(K.MARGINS):
        n = num["m"][m]
        g = K.geom(m)
        for row_i, (x, what) in enumerate(((xs, "キーの辺の真ん中（基板に載る所）"), (xt, "つばのくぼみの所"))):
            ax = axs[row_i][1 + col_i]
            for col, sec in _scene(m, x):
                F.fill(ax, sec, col, lw=0.5)
            _frame_axes(ax, f"縁 {m}: {what}", win)
            _dim(ax, g["yo"], K.HOLE_Y + S.CAP_CLEAR, 5.6, f"キャップから外面まで {n['cap_to_face']:.1f}")
            if row_i == 0:
                ax.annotate(f"爪: 基板の下へ {K.LIP_REACH - K.GAP:.2f} 入る\n（基板の下面から {n['below_board']:.1f} 下まで）", (g["tip_y"] - 0.2, K.LIP_BOTTOM + 0.1), (-46.5, -3.0),
                            fontsize=8, color=RED, arrowprops=dict(arrowstyle="->", color=RED, lw=0.8))
                ax.annotate(f"基板に載る幅 {n['seat']:.2f}", ((g["yb"] + K.HOLE_Y) / 2, 0.0), (-45.6, 1.2), fontsize=8.5, color=BLUE,
                            arrowprops=dict(arrowstyle="->", color=BLUE, lw=0.8))
                ax.text(g["yo"] - 0.15, 1.2, f"壁 {K.WALL}", fontsize=8.5, color=RED, ha="right", rotation=90, va="center")
            else:
                ax.annotate(f"くぼみの外の皮 {n['skin']:.1f}", (g["yo"] + n["skin"] / 2, 3.5), (-51.4, 1.6), fontsize=8.5, color=RED,
                            arrowprops=dict(arrowstyle="->", color=RED, lw=0.8))
                ax.text(-45.9, -2.9, f"基板の縁 {g['yb']:.3f}（いまの基板は {LAY.pcb[1]:.3f}）", fontsize=8, ha="center")

    # 入れる動き（縁 0.4・厚さ 1.6）
    m = K.MARGINS[-1]
    path = num["m"][m]["path"][S.PCB_T]
    ax = axs[1][0]
    F.fill(ax, CF.yz(K.frame(m), xm), COL["frame"], lw=0.5)
    picks = [path[0], path[len(path) // 2], path[-1]]
    for (th, dy), col, a in zip(picks, ("#d9ead3", "#a9d18e", COL["pcb"]), (0.9, 0.9, 1.0)):
        F.fill(ax, CF.yz(K.posed(K.board_in(m, S.PCB_T, False), m, th, dy), xm), col, lw=0.5, alpha=a)
    _frame_axes(ax, f"基板の代わりを入れる動き（縁 {m}・厚さ {S.PCB_T}）", (-51.6, -36.0, -6.2, 6.6))
    axs[1][3].axis("off")
    ax.text(-43.5, -5.6, "  →  ".join(f"{th:.0f}°・奥へ {dy:.2f}" for th, dy in picks) + "\n（薄い緑から濃い緑へ。枠は動かさずに描いた）", fontsize=8.5, ha="center")

    ax = axs[0][3]
    tol = num["tol"]
    p08, p04 = num["m"][K.MARGINS[0]], num["m"][K.MARGINS[1]]
    lines = [
        "数（立体から測った物・式）",
        "",
        f"キャップから枠の外面まで: いま {K.HOLE_Y + S.CAP_CLEAR - LAY.frame[1]:.1f} → {p08['cap_to_face']:.1f}（縁 0.8）・{p04['cap_to_face']:.1f}（縁 0.4）",
        f"穴の手前の縁の幅: {p08['rail']:.1f}・{p04['rail']:.1f}　　くぼみの外の皮: {p08['skin']:.1f}・{p04['skin']:.1f}",
        f"基板の外を下りる壁 {K.WALL}・基板との隙 {K.GAP}・爪の出 {K.LIP_REACH}",
        f"爪の掛かる面は水平から {K.LIP_SLOPE:.0f}°（支え無しで刷るため）",
        "",
        "爪が基板の下へ入っている量（掛かり）",
        f"  名目 {tol['nominal']['engage']:.2f}",
        f"  刷りの誤差 ±{K.PRINT_ERR} で {tol['print']['engage_min']:.2f}〜{tol['print']['engage_max']:.2f}",
        f"  基板の外形 ±{K.OUTLINE_TOL} も足すと {tol['all']['engage_min']:.2f}〜（隙は {tol['all']['gap_min']:+.2f} = 当たる）",
        "",
        "枠の手前を持ち上げたとき、爪が当たるまでに動く量",
        "  板の厚さ " + "・".join(f"{t} → {p04['play'][t]:.2f}" for t in K.BOARD_TS),
        f"  基板 1.44〜1.76 と刷りの誤差で {tol['print']['play_min']:+.2f}〜{tol['print']['play_max']:.2f}（負 = 食い込む）",
        "",
        f"爪は基板の下面から {p04['below_board']:.1f} 下まで = 底のシート 0.5 の下面より {p04['below_sheet']:.1f} 下",
        "（ねじの頭の最大 0.6 と同じ高さ）",
        "",
        f"手前の縁を奥へ押す固さ（Space の穴 {p04['span']:.1f} を渡る梁・計算）:",
        f"  縁 0.8 = {p08['rail_k']:.1f} N/mm・縁 0.4 = {p04['rail_k']:.1f} N/mm",
        f"  壁が基板の縁に当たるまで {K.GAP}（そこで止まる。キャップと穴の隙は {S.CAP_CLEAR}）",
    ]
    _note(ax, "\n".join(lines), 9)
    fig.suptitle("手前の縁の試し刷り: 断面（実寸の比・右が奥）。灰 = 枠・緑 = 基板（の代わり）・桃 = キャップ・黄 = ねじ", fontsize=13)
    p = out / "coupon_front_sections.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    return p


def howto(out, num=None, sliced=None):
    num = num or K.numbers()
    fig = plt.figure(figsize=(16, 15.5))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.5, 1.0, 1.0], hspace=0.14, wspace=0.08, left=0.03, right=0.985, top=0.945, bottom=0.01)

    ax = fig.add_subplot(gs[0, 0])
    kind_col = {"frame": COL["frame"], "board": COL["pcb"], "cap": COL["cap"]}
    for tag, name, kind, part, _ in K.plate_layout():
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.6, bb.max.Z / 2)), kind_col[kind], lw=0.5)
        ax.text((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, tag, fontsize=12, ha="center", va="center", color=RED,
                bbox=dict(fc="white", ec=RED, lw=0.6, pad=1.5))
    ax.set_xlim(-4, 99)
    ax.set_ylim(-4, 153)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("刷り上がった板（上から・ベッドに置いた向き）", fontsize=11)

    ax = fig.add_subplot(gs[0, 1])
    t = sliced or "（スライスの結果は docs/coupon-front.md）"
    _note(ax, "\n".join([
        "何を試すか",
        "  手前の壁のねじをやめて、枠の手前の壁を基板の縁の外へ下ろし、",
        "  先の小さな爪を基板の下へ回す形。手前の縁は 3.0 → 0.8 か 0.4 になる。",
        "  爪が刷れるか・基板を保てるかを、基板を変える前に確かめる。",
        "",
        "刷る物（1 枚・支え無し・0.4 ノズル・層 0.1）",
        f"  {t}",
        "  F08  枠の切れ端・手前の縁 0.8（奥の外面に縦の溝 2 本）",
        "  F04  枠の切れ端・手前の縁 0.4（同 1 本）",
        "       枠は上面をベッドに刷ってある = 爪がいちばん上に出来る",
        "  B1・B2・B3  基板の代わり。厚さ 1.4・1.6・1.8",
        "       （奥の縁の切り欠き 1・2・3 個）。どちらの枠にも合う",
        "  C1・C2・C3  キャップ 1u・1.5u・2.25u",
        "",
        "ほかに要る物: M2×4 のねじ 3 本（ほかの試し刷りと同じ物）",
        "",
        "これは試し刷りだけ。本番の枠と基板は変えていない。",
    ]), 11)

    ax = fig.add_subplot(gs[1, 0])
    m = K.MARGINS[-1]
    x = K.KS[-1].x + 8.0
    path = num["m"][m]["path"][S.PCB_T]
    th, dy = path[0]
    F.fill(ax, CF.yz(K.frame(m), x), COL["frame"], lw=0.5)
    F.fill(ax, CF.yz(C.cap_pose(K.KS[-1], "latched"), x), COL["cap"], lw=0.5)
    F.fill(ax, CF.yz(K.posed(K.board_in(m, S.PCB_T), m, th, dy), x), "#a9d18e", lw=0.5)
    ax.set_xlim(-50, -24)
    ax.set_ylim(-9.5, 7)
    ax.invert_yaxis()                                    # 組むときは枠を裏返して机に置く = 絵も上下を逆に
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("組み方 2〜3: 枠を裏返し、基板の代わりを手前の縁から斜めに差して倒す（絵は裏返した向き）", fontsize=10.5)
    ax.annotate("爪", (K.geom(m)["tip_y"], K.LIP_BOTTOM + 0.2), (-49.5, -5.5), fontsize=10, color=RED, arrowprops=dict(arrowstyle="->", color=RED))
    ax.annotate("基板の代わり（スイッチの代わりが下向き）", (-36.0, -3.6), (-41.0, -8.3), fontsize=9.5, arrowprops=dict(arrowstyle="->"))
    ax.annotate("机", (-30, 6.3), (-30, 6.3), fontsize=9, color="#666")

    ax = fig.add_subplot(gs[1, 1])
    _note(ax, "\n".join([
        "組み方",
        "  1. 枠を裏返して机に置く（上面が下）。キャップ 3 個を、つばを上にして穴に落とす",
        "     （C1 = 短い穴・C2 = 中・C3 = 長い穴）",
        "  2. 基板の代わり B2 を、スイッチの代わりを下に向けて持つ。",
        "     ねじ穴の無い方の縁（手前の縁）を、枠の爪のある側へ向ける",
        f"  3. 手前の縁を、爪の下へ斜めに差し込み（{path[0][0]:.0f}° くらい）、押し込みながら倒す",
        "     （倒さずに、平らに置いてから手前へ 0.5 ずらしても入る）",
        "  4. 奥のねじ穴 3 つに、M2×4 を締める（締めすぎない）",
        "  5. 表に返す。キャップを押して、カチッとはしないが、沈んで戻ることを見る",
        "",
        "外すとき: ねじ 3 本を外し、基板の代わりを奥へ 0.5 引いてから持ち上げる",
        "",
        "同じことを F08 と F04 の両方で。B1（薄い）と B3（厚い）でも入るかを見る",
    ]), 10.5)

    ax = fig.add_subplot(gs[2, 0])
    _note(ax, "\n".join([
        "手で見る所",
        "  ア. 爪が刷れているか（枠を裏返して、手前の縁の先を見る・爪でなぞる）。",
        "      垂れ・糸・欠けは無いか。F08 と F04 で違うか",
        "  イ. 基板の代わりが入るか・外せるか。B1・B2・B3 のどれが入って、どれがきついか",
        "  ウ. ねじを締めた状態で、枠の手前の縁に爪を掛けて持ち上げる。",
        "      浮くか（どのくらい）・爪が外れるか・壁が割れるか",
        "  エ. 手前の縁を、指で奥へ（キャップの方へ）押しながら、Space のキャップを押す。",
        "      引っ掛かるか・戻らなくなるか。押すのをやめると直るか",
        "  オ. 手前の縁の触り心地（角が痛くないか・たわむか）。F08 と F04 のどちらがよいか",
        "  カ. 机に置いたとき、手前の爪が机に当たって、がたつくか",
    ]), 10.5)

    ax = fig.add_subplot(gs[2, 1])
    tol = num["tol"]
    _note(ax, "\n".join([
        "報告してほしいこと（ア〜カを、F08・F04 それぞれ）",
        "  ・爪は刷れたか（写真があると助かる）",
        "  ・入った板（B1 / B2 / B3）・入らなかった板",
        "  ・ウで手前が浮いた量（見た目でよい: 浮かない・紙 1 枚・0.5 くらい…）と、壊れたか",
        "  ・エでキャップが引っ掛かったか",
        "  ・どちらの縁を選ぶか（0.8 / 0.4 / どちらも駄目）",
        "",
        "計算での見込み（刷って確かめる前の数）",
        f"  ウの浮き: B1 {num['m'][m]['play'][K.BOARD_TS[0]]:.2f}・B2 {num['m'][m]['play'][K.BOARD_TS[1]]:.2f}・B3 {num['m'][m]['play'][K.BOARD_TS[2]]:.2f}",
        f"  爪の掛かり: {tol['nominal']['engage']:.2f}（誤差で {tol['print']['engage_min']:.2f}〜{tol['print']['engage_max']:.2f}）",
        f"  カ: 爪は底のシート 0.5 の下面より {num['m'][m]['below_sheet']:.1f} 下へ出る（ねじの頭と同じ）",
    ]), 10.5)
    fig.suptitle("手前の縁の試し刷り（coupon_front_plate）: 刷る物・組み方・手で見る所", fontsize=14)
    p = out / "coupon_front_howto.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    return p


def render_all(out, num=None):
    num = num or K.numbers()
    return [sections(out, num), howto(out, num)]
