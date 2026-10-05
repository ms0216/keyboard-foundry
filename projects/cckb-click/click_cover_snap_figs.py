"""蓋の別案 B3（左右のばねの腕で掛ける蓋）の絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_cover_snap の
numbers()・arm_numbers()・stresses()・measure_moves()・cell_access()。

  cover_snap.png               しくみ（上から切った図・手前から・横から）・閉め方／開け方／電池の出し方・蓋 3 つの違い・B2 から直した所・基板の提案・数
  coupon_cover_snap_howto.png  刷り上がった板・蓋の見分け方・組み方・手で見る所・教えてほしいこと

    .venv/bin/python3 projects/cckb-click/click_cover_snap.py   が呼ぶ
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from build123d import Plane  # noqa: E402

import click_case as C  # noqa: E402
import click_case_figs as CF  # noqa: E402
import click_cover_snap as B  # noqa: E402
import click_figs as F  # noqa: E402

LAY, S = C.LAY, C.S
COL = CF.COL
RED, BLUE = "#c00000", "#1f5fbf"
GUIDE_USE = {1: "きつい", 2: "中", 3: "緩い"}


def _note(ax, text, size=10.5):
    ax.axis("off")
    ax.text(0.0, 1.0, text, fontsize=size, va="top", ha="left", linespacing=1.55, transform=ax.transAxes)


def scene(variant=B.MAIN, dl=None, dr=None, cover=True, clip=True, **pose):
    """組んだ試し刷り [(色, 立体)]。dl・dr = 腕の先を、座った形から内へ動かした量・pose = 蓋を動かす量（click_cover_snap.posed の引数）。"""
    out = [(COL["pcb"], B.base()), (COL["frame"], B.frame()), (COL["bat"], B.cell())]
    if clip:
        out.append((COL["clip"], B.clip()))
    if cover:
        out.append((COL["cover"], B.posed(B.cover(variant, True, dl, dr), **pose)))
    return out


def yz(part, x):
    return F.section(part, Plane.YZ.offset(x), "Y", "Z")


def _draw(ax, sc, cut, lim, title, size=10.5):
    for color, part in sc:
        try:
            F.fill(ax, cut(part), color, lw=0.5)
        except Exception:                                    # 切る面がその立体を通らない
            pass
    ax.set_xlim(lim[0], lim[1])
    ax.set_ylim(lim[2], lim[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=size)
    ax.tick_params(labelsize=7)


def _arrow(ax, tip, tail, text, color=RED, size=9.5, **kw):
    ax.annotate(text, tip, tail, fontsize=size, color=color, arrowprops=dict(arrowstyle="->", color=color, lw=1.1),
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.0) if text else None, **kw)


def cover_snap(out, num=None, moves=None):
    """moves = click_cover_snap.measure_moves()（検査と同じ探し方で測った数）。"""
    num = num or B.numbers()
    moves = moves or B.measure_moves()
    arm = num["arms"][B.MAIN]
    acc = num["cell_access"]
    rel = arm["release"] - arm["pre"]
    full = (99.5, 146.5, -51.6, -29.8)
    fig = plt.figure(figsize=(23, 21))
    gs = fig.add_gridspec(4, 6, height_ratios=[0.95, 0.75, 0.9, 1.75], hspace=0.2, wspace=0.25, top=0.955, bottom=0.01)
    fig.suptitle("電池の蓋の別案 B3（左右のばねの腕で掛ける蓋）: 手前からまっすぐ押し込む → 左右がカチッ。外すときは、左右のつまみを爪でつまんで引く"
                 "        橙 = 蓋・灰 = 枠・紫 = クリップ・緑 = 基板の代わり        **試し刷りの候補。本番の蓋・枠・基板は変えていない**",
                 fontsize=13, y=0.985)

    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), full, "① 掛けた所（基板の上 1.5 で切った図。下が手前）。クリップと電池は、いまより 2.0 奥")
    _arrow(ax, (B.XLIP - 0.5, B.YS + 0.3), (100.3, -42.5), f"かぎ（掛かり {B.ENGAGE:.1f}）が\n口の縁の裏に掛かる")
    _arrow(ax, (B.XN + 0.4, -41.0), (100.3, -39.0), "ばねの腕（奥で付いて、\n手前へ戻る）")
    _arrow(ax, (B.XN + 0.3, B.YF + 0.3), (108.3, -51.35), "つまみ（腕の先）", va="center")
    _arrow(ax, (B.CX - num["pocket"]["corner"], B.YB - 0.1), (114.2, -43.6), f"電池は、くぼみの左右の角で\n当たる（隙 {B.CELL_GAP}）")
    _arrow(ax, (B.CX, B.YF + 1.5), (118.5, -51.35), f"手前の板 {num['pocket']['plate_t']:.1f}", va="center")
    _arrow(ax, (B.H15_NEW[0], B.H15_NEW[1]), (139.2, -44.5), "ねじ H15 を\nここへ動かす（提案）", color=BLUE)
    _arrow(ax, (B.CX + 5.0, B.CY + 6.5), (131.0, -31.0), f"クリップと電池を 奥へ {B.DBACK:.1f}（提案）", color=BLUE, va="center")
    _arrow(ax, (B.mx(B.XN - B.GUIDE_CL) + 0.5, B.YR), (139.6, -36.2), "案内の壁（枠）。蓋 3 つで\nここの隙を 0.10／0.15／0.25", va="center")
    ax = fig.add_subplot(gs[0, 3:])
    _draw(ax, scene(dl=rel, dr=rel, dy=-4.0), lambda p: F.xy(p, 1.5), full, "② 左右のつまみを内へつまんで（かぎが縁から外れる）、手前へ 4 引いた所")
    _arrow(ax, (B.XN + 1.6, B.YF - 3.6), (B.XLIP - 5.5, B.YF - 0.6), "つまむ", va="center")
    _arrow(ax, (B.mx(B.XN) - 1.6, B.YF - 3.6), (B.mx(B.XLIP) + 3.2, B.YF - 0.6), "つまむ", va="center")

    ax = fig.add_subplot(gs[1, :3])
    off = [(COL["pcb"], B.base(), 1.0), (COL["bat"], B.cell(), 3.0), (COL["frame"], B.frame(), 4.0)]
    for color, part, z in off:
        F.fill(ax, F.xy(part, z), color, lw=0.5)
    ax.set_xlim(99.5, 146.5)
    ax.set_ylim(-51.6, -40.0)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_title("③ 蓋を外して、上から見た所（枠は 4.0・電池は 3.0 で切った図）: 口の真ん中は、手前と上へ開いた箱", fontsize=10.5)
    front = B.CY - B.CELL_R
    _arrow(ax, (B.CX, front + acc["top_nominal"] / 2), (132.5, -44.2),
           f"上から見える電池: 奥行き {acc['top_nominal']:.2f}（板が公差の端なら {acc['top'][0]:.2f}）× 幅 {acc['top'][1]:.1f}\nここを爪で下へ押しながら、手前へ引く", va="center")
    _arrow(ax, (B.CX + 6.0, B.CLIP_FRONT + 0.6), (132.5, -41.2), "クリップの板（試し刷りでは、枠に付けた代わり）", va="center")
    ax.annotate("", (B.CX, B.Y0 - 0.6), (B.CX, front + 0.3), arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.6))
    ax = fig.add_subplot(gs[1, 3:])
    _draw(ax, scene(clip=False), lambda p: F.xz(p, B.YF + 0.25), (99.5, 146.5, -2.0, 6.0), "④ 手前から見た所（蓋の手前の面のすぐ奥で切った図）")
    _arrow(ax, (B.XN + arm["t"] + arm["front_gap"] / 2, 1.5), (104.0, -1.5), f"見える隙間: 幅 {arm['front_gap']:.1f} × 高さ {B.ZW:.0f}（左右。奥は行き止まり）", va="center")
    _arrow(ax, ((B.XLIP + B.A0) / 2, 4.0), (101.0, 5.6), "枠の手前の壁は、上の 2.0 が残る", va="center")

    zoom = (104.4, 109.2, -50.9, -47.6)
    xg = B.XLIP - B.TAB_FLARE
    ax = fig.add_subplot(gs[2, 0:2])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), zoom, "⑤ 左のかぎとつまみ（掛けた所）")
    _arrow(ax, (B.XLIP - 0.45, B.YL), (104.5, -48.0), "掛かる面（直角）。電池が\n押すと、ここで止まる")
    _arrow(ax, (B.XLIP - B.TAB_FLARE / 2, B.YA - B.TAB_FLARE / 2), (107.75, -48.3), f"45° の面（長さ {num['seat_face']:.2f}）:\n腕が外へ開く力が、蓋を\n手前へ押す = 座る", va="center")
    _arrow(ax, (xg - B.NAIL_STEP[0] / 2, B.YF + B.NAIL_STEP[1]), (104.5, -49.9), f"爪が引っ掛かる段\n（出 {B.NAIL_STEP[0]}）", va="center")
    _arrow(ax, (xg - 0.3, B.YF + B.NAIL_STEP[1] + 0.15), (107.75, -50.6), f"爪の入る所（入り口 {num['grip_open']:.1f}）", va="center")
    ax = fig.add_subplot(gs[2, 2:4])
    out1, pose = moves["one_arm"][1]
    out1 = max(out1, num["arms"][1]["one_arm_calc"])
    _draw(ax, scene(variant=1, dl=rel * 0.45, **pose), lambda p: F.xy(p, 1.5), zoom,
          f"⑥ 蓋 1 で、左だけつまんで引いた所（出るのは {out1:.2f} まで）で、手を離しかけた形")
    _arrow(ax, (B.XLIP + 0.05, B.YL - 0.05), (104.5, -48.0), f"かぎの角の斜め（{B.HOOK_CH}）が縁の角に\n乗る → ばねが蓋を引き戻す")
    ax = fig.add_subplot(gs[2, 4:])
    _draw(ax, scene(), lambda p: yz(p, B.CX), (-52.0, -43.0, -2.0, 6.0), "⑦ 横から（電池の真ん中で切った図。左が手前）")
    _arrow(ax, (B.YF + 1.5, 2.0), (-51.9, -1.4), f"蓋の板 {num['pocket']['plate_t']:.1f}", va="center")
    _arrow(ax, ((B.YF + B.YB) / 2, 4.3), (-49.5, 5.6), f"電池の上に渡る帯（電池との隙 {B.STRIP_Z - S.CELL_T:.1f}）", va="center")

    st, sc = num["stress"][True], num["stress"][False]
    sf = num["strength"]
    names = dict(plate_tension="板の引っ張り", plate_compression="板の圧縮", stem="柱", arm="腕", buckle="腕の座屈", hook="かぎのせん断", lip="縁の面圧")
    one = {n: max(moves["one_arm"][n][0], num["arms"][n]["one_arm_calc"]) for n in sorted(B.VARIANTS)}    # 探した値と、式の見積もりの、大きい方
    verdict = {n: ("手を離すと戻る" if one[n] <= B.HOOK_CH - 0.05 else "戻るとは言えない" if one[n] <= B.HOOK_CH + 0.15 else "**片方ずつ 2 回で開く**")
               for n in one}
    ax = fig.add_subplot(gs[3, 0:2])
    _note(ax, "閉め方（道具なし）\n"
              "1. 蓋を、上の板を上・腕を奥にして、口の手前に置く\n"
              "2. まっすぐ奥へ押し込む（角を落としてあるので、0.3 ずれていても\n"
              "   自分で真ん中に寄る）。かぎの斜めの面が口の縁に乗り、腕が内へ逃げる\n"
              "3. 押し切る少し手前から、腕のばねが蓋を引き込み、左右がカチッ。\n"
              "   手を離すと、腕が 45° の面を押して、かぎが縁に当たる位置に座る\n\n"
              "開け方（指 2 本）\n"
              "1. 親指と人差し指の爪を、左右の口の縁の斜めの面から入れて、\n"
              f"   つまみの手前の端の段（出 {B.NAIL_STEP[0]}）の奥に掛ける\n"
              f"   （入り口の幅 {num['grip_open']:.1f}・段の奥の深さ {num['grip']:.1f}・高さ {B.HS:.1f}）\n"
              f"2. 内へつまむ（片側 {rel:.1f} mm・約 {arm['pinch']:.1f} N = {arm['pinch'] * 102:.0f} g ずつ）\n"
              "3. つまんだまま、手前へ引き抜く（爪は、段に引っ掛かっている）\n\n"
              "電池の出し方（蓋を外した後・③）\n"
              f"・口の真ん中は、幅 {acc['well'][0]:.0f} × 奥行き {acc['well'][1]:.1f} の、手前と上へ開いた箱\n"
              f"・電池は、外面から {acc['front'][1]:.1f} 奥。上から見える上面は 奥行き {acc['top_nominal']:.2f} × 幅 {acc['top'][1]:.1f}\n"
              f"  （いまの本番は {acc['top_production']:.2f}。その奥は、クリップの板の下）\n"
              "・見えている上面と手前の縁を、爪か指の先で**下へ押しながら手前へ**\n"
              "  引く。出てくるほど、押せる面が増える\n"
              "・**本物は、クリップの舌が電池を押さえている。その固さは、試し刷り\n"
              "  では分からない**（代わりは、ただの円板）。固ければ、クリップの板の\n"
              "  真ん中の切れ込み（図面の絵では 幅 4〜5・奥行き 1.5 ほど。寸法の記入\n"
              "  なし）の上の屋根に、爪の窓を足す手が残っている（作っていない）")
    ax = fig.add_subplot(gs[3, 2:4])
    _note(ax, "蓋 3 つの違い = 奥の案内の隙（腕とかぎは同じ）\n"
              + "".join(f"  蓋 {n}（{GUIDE_USE[n]}）: 隙 {num['arms'][n]['guide']:.2f}。片方だけつまむと {one[n]:.2f} 出る → {verdict[n]}\n" for n in one)
              + "  きついと: 刷りの誤差で噛むと、座らせる力（0.2〜0.4 N）も、爪で引く力も\n"
              "  摩擦に負ける = **爪で抜けない蓋は、その隙が不合格**（こじらない）\n"
              "  緩いと: 片方ずつ 2 回に分ければ開く（わざとでないと起きない動き）\n\n"
              "B2 から直した所（見直しを受けて）\n"
              "1. 案内の隙を、蓋 3 つで振った（B2 は 3 つとも 0.10）\n"
              f"2. つまみに、爪が引っ掛かる段（B2 は、爪の摩擦だけで引いていた）\n"
              "3. 「片方だけでは開かない」は、隙 0.10 の蓋 1 だけ（上の表）\n"
              f"4. 腕の付け根の丸み {B.ROOT_R} を、本当に腕の付け根に（B2 は柱を削っていた）\n"
              f"5. 電池の出し方を数で書いた・枠に、クリップの板の代わりを付けた\n"
              f"6. 奥の壁をやめた（C_BAT のランドに近く、薄かった）。押し切りの止めは\n"
              f"   屋根の縁と、電池＋クリップの止め。45° の面は 0.07 → {num['seat_face']:.2f}。\n"
              f"   帯と電池の隙 0.3 → {B.STRIP_Z - S.CELL_T:.1f}\n\n"
              "**基板の変更の提案（いまは何も変えていない）**\n"
              f"・クリップ BT1 を奥へ {B.DBACK:.1f}: ({S.CLIP_AT[0]:.1f}, {S.CLIP_AT[1]:.3f}) → ({S.CLIP_AT[0]:.1f}, {S.CLIP_AT[1] + B.DBACK:.3f})\n"
              "  ＋のランド 2 つ・−のランド・電池の下の銅の逃げ・VBAT_IN の線が\n"
              "  一緒に動く。逃げの奥に入るビア 3 つ（y = −30.625）を外す\n"
              f"・ねじ H15: x {B.H15_OLD[0]:.1f} → {B.H15_NEW[0]:.1f}。ビア 1 つを外す。裏の、ねじの頭の\n"
              "  銅の逃げも一緒に動く\n"
              "・使っていない穴 H30・H31 を消す（裏の、頭の銅の逃げも消える）\n"
              f"・枠: クリップの上の薄い屋根が奥へ {B.DBACK:.1f} 伸びる（Shift・Fn の\n"
              "  穴のくぼみまでの厚い屋根が 約 4.1 → 2.1 になる）")
    ax = fig.add_subplot(gs[3, 4:])
    _note(ax, "数（立体から測った物と、TDS の値での計算。刷った物の値ではない）\n"
              f"・腕: 厚さ {arm['t']:.2f} × 高さ {B.HS:.1f} × 長さ {arm['length']:.1f}・予圧 {arm['pre']:.2f}\n"
              f"・かぎの掛かり {arm['engage']:.2f}（直角の所 {arm['engage_flat']:.2f} ＋ 角の斜め {B.HOOK_CH}）\n"
              f"  誤差を全部悪い側に取って {arm['engage_worst']:.2f}\n"
              f"・外すときの付け根のひずみ {arm['strain_release']:.2f} %（上限 {arm['strain_use']:.2f} %）\n"
              f"  入れるとき {arm['strain_insert']:.2f} %・胴に当たって止まるとき {arm['strain_stop']:.2f} %\n"
              f"・座る力（腕 2 本が、蓋を手前へ）: {arm['seat_y'][0]:.2f}〜{arm['seat_y'][1]:.2f} N\n"
              f"  （摩擦を引いて〜引かずに。予圧が誤差の端で {arm['seat_y_ends'][0][0]:.2f}〜{arm['seat_y_ends'][1][1]:.2f} N。蓋は {num['mass']:.2f} g）\n"
              f"・落下 {S.DROP_G:.0f} G（仮定）で、かぎが自分の重さで揺れる量 {arm['drop']:.2f}\n"
              f"  （外れるのは {arm['pre'] + arm['engage']:.2f} = {arm['drop_margin']:.1f} 倍）\n"
              f"・電池が 20 N（指で強く押す・仮定）で押すときの応力 [MPa]\n"
              f"  真ん中で当たる（悪い側）: 板 {st['plate']['tension']:.0f}／{st['plate']['compression']:.0f}・柱 {st['stem']['stress']:.0f}・腕 {st['arm']['stress']:.0f}\n"
              f"  左右の角で当たる（設計）: 板 {sc['plate']['tension']:.0f}／{sc['plate']['compression']:.0f}・柱 {sc['stem']['stress']:.0f}・腕 {sc['arm']['stress']:.0f}\n"
              f"  強さ（TDS）: 引っ張り {S.PLA_TENSILE:.0f}・曲げ {S.PLA_BEND:.0f} → どこも半分以内\n"
              "・強さに届く力 [N]（真ん中で当たるとき）\n  "
              + "・".join(f"{names[k]} {v:.0f}" for k, v in sorted(sf.items(), key=lambda q: q[1])[:4]) + "\n  "
              + "・".join(f"{names[k]} {v:.0f}" for k, v in sorted(sf.items(), key=lambda q: q[1])[4:]) + "\n"
              f"  いちばん小さい {num['weakest'][1]:.0f} N は、電池 1.8 g の慣性に直すと {num['weakest_g']:.0f} G\n"
              "  （**導いた値**。要求ではない。落として測った値でもない）\n"
              f"・掛けた蓋の動ける量: 手前 {moves['forward']:.2f}・上 {moves['up']:.2f}\n"
              f"  胴の遊び（腕を逃がして）: 奥 {moves['back']:.2f}・左右は案内の隙\n"
              f"・電池の代わりは、手前へ {moves['cell']:.2f} で蓋に当たる\n"
              f"・窓の上の壁を 10 N で押す: 下がり {num['lintel']['drop']:.2f}（蓋との隙 {num['lintel']['gap']:.1f}）・{num['lintel']['stress']:.0f} MPa\n"
              f"・ねじの下穴から、かぎの空洞まで {num['h14_wall']:.1f}（H14・動かした H15）")
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def howto(out, num=None, moves=None):
    num = num or B.numbers()
    arm = num["arms"]
    acc = num["cell_access"]
    one = {n: max(moves["one_arm"][n][0] if moves else 0.0, arm[n]["one_arm_calc"]) for n in sorted(B.VARIANTS)}
    fig = plt.figure(figsize=(22, 16.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[0.85, 1.15], hspace=0.16, wspace=0.12)
    fig.suptitle("蓋の別案 B3 の試し刷り（coupon_cover_snap_plate_n04.gcode.3mf）: 組み方と、手で見る所", fontsize=14, y=0.995)
    ax = fig.add_subplot(gs[0, 0])
    names = {"cell": "電池の代わり", "cover1": "蓋 1", "cover2": "蓋 2", "cover3": "蓋 3", "base": "当て板（基板の代わり）", "frame": "枠の角（上面が下）"}
    cols = {"cell": COL["bat"], "base": COL["pcb"], "frame": COL["frame"]}
    for name, part, _ in B.plate_layout():
        bb = part.bounding_box()
        F.fill(ax, F.xy(part, min(0.6, bb.max.Z / 2)), cols.get(name, COL["cover"]), lw=0.5)
        ax.text((bb.min.X + bb.max.X) / 2, bb.max.Y + 0.6, names[name], fontsize=9, ha="center", va="bottom")
    pb = B.plate().bounding_box()
    ax.set_xlim(pb.min.X - 2, pb.max.X + 2)
    ax.set_ylim(pb.min.Y - 2, pb.max.Y + 4)
    ax.set_aspect("equal")
    ax.set_title("刷り上がった板（上から。下が手前）", fontsize=11)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[0, 1:])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), (99.5, 146.5, -51.6, -27.5), "組んだ所（基板の上 1.5 で切った図。下が手前）")
    _arrow(ax, (B.CX, B.CY - 3.0), (B.CX + 3.5, -28.6), "電池の代わりを、裏の長い穴から\n細い棒で手前へ押す（試し刷りだけ）", va="center")
    _arrow(ax, (B.XN + 0.3, B.YF + 0.3), (100.2, -51.3), "つまみ", va="center")
    _arrow(ax, (B.mx(B.XN) - 0.3, B.YF + 0.3), (141.5, -51.3), "つまみ", va="center")
    _arrow(ax, (B.XN - 0.1, B.YR + 0.5), (100.3, -34.5), "案内（ここの隙が、蓋 3 つで違う）", va="center")
    ax = fig.add_subplot(gs[1, 0])
    _note(ax, "蓋の見分け方（上の板の奥の縁の切り欠きの数）= **奥の案内の隙**\n"
              + "".join(f"  蓋 {n}（切り欠き {n} つ）: 隙 {arm[n]['guide']:.2f}（{GUIDE_USE[n]}）\n" for n in arm)
              + "  腕（厚さ 0.90・予圧 0.30）と、かぎは 3 つとも同じ\n\n"
              "それぞれ、何を見るための蓋か\n"
              f"  蓋 1（0.10）: 片方だけつまんで引いても {one[1]:.2f} しか出ず、手を離すと\n"
              "      戻るはず。**ただし、噛んで抜けなくなるかもしれない**\n"
              f"  蓋 2（0.15）: その中間（片方で {one[2]:.2f}）\n"
              f"  蓋 3（0.25）: 噛まないはず。代わりに、片方ずつ 2 回で開く（片方で {one[3]:.2f}）\n\n"
              "**きつくて、爪で引き抜けない蓋は、その隙が不合格。**\n"
              "こじったり、道具で引いたりしないで、次の蓋へ（本番では、\n"
              "電池を裏から押せない。爪で抜けない蓋は、使えない蓋）\n\n"
              "組み方\n"
              "1. 蓋の腕を、爪で内へ 2 mm ほど押して、戻ることを見る\n"
              "   （胴に付いて刷れていたら、そこで教えてください）\n"
              "2. 当て板に、枠の角を載せる（左と奥の当てに寄せる。\n"
              "   M2 のねじがあれば、裏から 2 本で留められる）\n"
              "3. 電池の代わりを、口から奥の止めまで入れる\n"
              "4. 蓋を、手前からまっすぐ押し込む（左右がカチッ）\n\n"
              f"**この試し刷りは、クリップと電池を奥へ {B.DBACK:.1f}・ねじ H15 を右へ 3.5\n"
              "動かした基板の形**（いまの基板には合わない）。枠の角には、\n"
              "クリップの板（電池の上の金属）の代わりが付いている", size=10.5)
    ax = fig.add_subplot(gs[1, 1])
    _note(ax, "手で見る所（蓋 1・2・3 のそれぞれで）\n"
              "a. 入るか・カチッと鳴るか・押し切る手前で、自分から\n"
              "   引き込まれる感じがあるか\n"
              "b. 手前の面が枠と揃うか・指で押して離すと、元の位置に戻るか\n"
              "c. 蓋をつまんで揺すって、がたつくか（前後・左右・上下）\n"
              "d. **電池の代わりを、裏から棒で強く押す**: 蓋が外れないか・\n"
              "   蓋の真ん中が手前へふくらむか・白くなるか・戻るか\n"
              "e. 振る（電池の代わりを入れたまま、強く）: 外れないか・音\n"
              "f. 机の高さから、硬い床へ落とす（向きを変えて 5 回）\n"
              "g. 鞄の中のように、手前の面を布・鍵・ペンの先で擦る・押す\n"
              "h. **片方のつまみだけ**を爪で内へ押して引く → 手を離す:\n"
              "   元に戻るか・外れたままか（蓋ごとに違うはず）。左右で\n"
              "i. **両方をつまんで、爪だけで引き抜く**（裏から押さない）:\n"
              "   爪が段に掛かるか・抜けるか・力・痛くないか。\n"
              "   **抜けなければ、その蓋は不合格**（こじらない）\n"
              "j. 20 回 開け閉めする: かぎ・腕・つまみの段が白くなる・欠ける・\n"
              "   ゆるくなる・座りが弱くなる（b をもう一度）\n"
              "k. **電池の出し方**: 蓋を外して、電池の代わりの、見えている\n"
              f"   上面（奥行き {acc['top_nominal']:.1f}）と手前の縁を、爪か指の先で下へ押しながら\n"
              "   手前へ引く。爪・指が届くか、動きに無理が無いかを見る\n"
              "   （**本物のクリップが電池を押さえる固さは、この試し刷り\n"
              "   では再現できない**。代わりは、ただの円板で、すぐ動く）\n"
              "l. 口の縁（枠の、かぎが掛かる所）が欠けないか", size=10.5)
    ax = fig.add_subplot(gs[1, 2])
    _note(ax, "教えてほしいこと\n"
              "・a〜l で、駄目だった物と、どの蓋か\n"
              "・**i で、爪だけで抜けた蓋・抜けなかった蓋**（いちばん知りたい）\n"
              "・h で、手を離したときに戻った蓋・外れたままだった蓋\n"
              "・c で、がたついた蓋\n"
              "・d で、どのくらい押したら何が起きたか\n"
              "・k で、爪・指が電池に届いたか\n"
              "・見た目: 手前の面の左右の隙間が気になるか\n\n"
              "この試し刷りで分からないこと\n"
              "・本物のクリップと電池での固さ（電池はクリップの舌で\n"
              "  押さえられている）→ 電池を出すのに要る力\n"
              "・基板を変えてよいか（クリップを奥へ 2.0・H15 を右へ 3.5・\n"
              "  H30 と H31 を消す。配線と検査の見直しが要る）\n"
              "・長く使ったときの、腕のへたり（予圧が抜けて、座りが弱くなる）", size=10.5)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def render_all(out, moves=None):
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    num = B.numbers()
    moves = moves or B.measure_moves()
    return [cover_snap(out / "cover_snap.png", num, moves), howto(out / "coupon_cover_snap_howto.png", num, moves)]
