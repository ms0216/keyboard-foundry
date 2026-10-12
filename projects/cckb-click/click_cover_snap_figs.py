"""蓋の別案 B4（左右のばねの腕で掛ける蓋）の絵（build/cckb-click/）。**作った立体そのものを切って描く**（寸法から描き直さない）。数は click_cover_snap の
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
    acc, tg, ej = num["cell_access"], num["target"], moves["eject"]
    e2 = ej[B.MAIN]
    full = (99.5, 146.5, -53.6, -29.8)
    fig = plt.figure(figsize=(23, 21))
    gs = fig.add_gridspec(4, 6, height_ratios=[1.0, 0.7, 0.95, 1.6], hspace=0.2, wspace=0.25, top=0.955, bottom=0.01)
    fig.suptitle("電池の蓋の別案 B4: 手前からまっすぐ押し込む → カチッ。外すときは、**左右のつまみを内へつまむだけ → 蓋が出てくる → 取る**"
                 "        橙 = 蓋・灰 = 枠・紫 = クリップ・緑 = 基板の代わり        **試し刷りの候補。本番の蓋・枠・基板は変えていない**",
                 fontsize=13, y=0.985)

    ax = fig.add_subplot(gs[0, :3])
    _draw(ax, scene(), lambda p: F.xy(p, 1.5), full, "① 掛けた所（基板の上 1.5 で切った図。下が手前）。クリップと電池は、いまより 2.0 奥")
    _arrow(ax, (B.XLIP - 0.5, B.YS + 0.3), (100.3, -42.5), f"かぎ（掛かり {arm['engage']:.1f}）が\n口の縁の裏に掛かる")
    _arrow(ax, (B.XN + 0.4, -41.0), (100.3, -39.0), "ばねの腕（奥で付いて、\n手前へ戻る）")
    _arrow(ax, (B.XN + 0.6, B.YF + 0.5), (108.3, -52.6), "つまみ（腕の先。上まで高くした）", va="center")
    _arrow(ax, (B.XLIP - 1.5, B.Y0 + 0.2), (100.0, -52.6), f"指の入るくぼみ（幅 {tg['scoop'][0]:.0f}）", va="center")
    _arrow(ax, (B.CX, B.YF + 1.5), (118.5, -52.6), f"手前の板 {num['pocket']['plate_t']:.1f}", va="center")
    _arrow(ax, (B.H15_NEW[0], B.H15_NEW[1]), (139.2, -44.5), "ねじ H15 を\nここへ動かす（提案）", color=BLUE)
    _arrow(ax, (B.CX + 5.0, B.CY + 6.5), (131.0, -31.0), f"クリップと電池を 奥へ {B.DBACK:.1f}（提案）", color=BLUE, va="center")
    ax = fig.add_subplot(gs[0, 3:])
    d_end, y_end = e2["path"][-1][1], e2["rest"]
    _draw(ax, scene(dl=d_end, dr=d_end, dy=-y_end), lambda p: F.xy(p, 1.5), full,
          f"② 左右をつまんで、指を離した後（引いていない）: 蓋は {y_end:.1f} 出て止まる → 指でつまんで取る")
    ax.annotate("", (B.CX, B.YF - y_end - 1.6), (B.CX, B.YF - 0.2), arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.8))

    ax = fig.add_subplot(gs[1, :3])
    for color, part, z in [(COL["pcb"], B.base(), 1.0), (COL["bat"], B.cell(), 3.0), (COL["frame"], B.frame(), 4.0)]:
        F.fill(ax, F.xy(part, z), color, lw=0.5)
    ax.set_xlim(99.5, 146.5)
    ax.set_ylim(-51.6, -41.5)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_title("③ 蓋を外して、上から見た所（枠は 4.0・電池は 3.0 で切った図）: 口の真ん中は、手前と上へ開いた箱", fontsize=10.5)
    front = B.CY - B.CELL_R
    _arrow(ax, (B.CX, front + acc["top_nominal"] / 2), (132.5, -44.6),
           f"上から見える電池: 奥行き {acc['top_nominal']:.2f} × 幅 {acc['top'][1]:.1f}\nここを爪で下へ押しながら、手前へ引く", va="center")
    ax.annotate("", (B.CX, B.Y0 - 0.6), (B.CX, front + 0.3), arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.6))
    ax = fig.add_subplot(gs[1, 3:])
    _draw(ax, scene(clip=False), lambda p: F.xz(p, B.YF + 0.25), (99.5, 146.5, -2.0, 6.0), "④ 手前から見た所（蓋の手前の面のすぐ奥で切った図）")
    _arrow(ax, (B.XN + 0.6, 4.0), (100.2, 5.6), f"つまみ: 高さ {tg['face'][1]:.2f}（B3 は 2.8）", va="center")
    _arrow(ax, (B.XN + B.TAB_W + arm["front_gap"] / 2, 1.5), (104.0, -1.5), f"見える隙間: 幅 {arm['front_gap']:.1f}（左右。上へも開いている）", va="center")

    zoom = (103.2, 113.2, -52.9, -47.4)
    shots = [("⑤ 掛けた所（上面の少し下 4.0 で切った図）", dict(), None),
             (f"⑥ 両方をつまみ切る → まぐさの端の斜めの面が、蓋を {e2['cam']:.1f} 押し出す", dict(dl=B.D_MAX, dr=B.D_MAX, dy=-e2["cam"]), "cam"),
             (f"⑦ 指を離す → かぎは縁の裏へ戻れず、腕のばねが さらに押し出す → {y_end:.1f} で止まる", dict(dl=d_end, dr=d_end, dy=-y_end), "rest")]
    for k, (title, kw, tag) in enumerate(shots):
        ax = fig.add_subplot(gs[2, 2 * k:2 * k + 2])
        _draw(ax, scene(**kw), lambda p: F.xy(p, 4.0), zoom, title, size=9.5)
        if tag is None:
            _arrow(ax, (B.XLIP - B.TAB_FLARE - 0.02, B.YF + 0.45), (103.4, -52.3), f"つまむ面（奥行き {tg['face'][0]:.1f} × 高さ {tg['face'][1]:.2f}）\n指の先・爪の横で、内へ押す", va="center")
            _arrow(ax, (B.cam_line(B.YT - B.CAM_F / 2) + 0.05, B.YT - B.CAM_F / 2), (108.3, -52.3), "まぐさの端の斜めの面", va="center")
            _arrow(ax, (B.XN + B.TAB_W - 0.05, B.YT - 0.05), (108.6, -47.75), "つまみの角 K", va="center")
        elif tag == "cam":
            _arrow(ax, (B.XN + 1.3, B.YF - e2["cam"] + 0.6), (103.4, -52.3), f"内へ {tg['travel']:.1f}・{arm['pinch']:.1f} N ずつ", va="center")

    st = num["stress"][True]
    sf = num["strength"]
    names = dict(plate_tension="板の引っ張り", plate_compression="板の圧縮", stem="柱", arm="腕", buckle="腕の座屈", hook="かぎのせん断", lip="縁の面圧")
    ax = fig.add_subplot(gs[3, 0:2])
    _note(ax, "閉め方（道具なし）\n"
              "1. 蓋を、上の板を上・腕を奥にして、口の手前に置く\n"
              f"2. まっすぐ奥へ押し込む（約 {arm['insert_force']:.0f} N = {arm['insert_force'] * 102:.0f} g。0.3 ずれていても、\n"
              "   自分で真ん中に寄る）→ 左右がカチッ\n\n"
              "**開け方（つまむ → 出てくる → 取る）**\n"
              "1. 親指と人差し指の先（または爪の横）を、左右のくぼみに当てて、\n"
              f"   つまみを**内へ押すだけ**（片側 {tg['travel']:.1f} mm・約 {arm['pinch']:.1f} N = {arm['pinch'] * 102:.0f} g ずつ）\n"
              f"2. つまみ切ると、蓋が手前へ {e2['cam']:.1f} 押し出される（⑥）\n"
              f"3. 指を離すと、蓋はさらに出て、{y_end:.1f} 出た所で止まる（⑦）。\n"
              "   もう掛かっていないので、指でつまんで取る\n"
              "※ 引きながらつまむ動きは要らない。片方だけつまんでも、蓋は出てこない\n\n"
              "つまむ所の大きさ（枠が許す、いちばん大きい形。**3 mm の面には届かない**）\n"
              f"・くぼみ（指の入り口）: 幅 {tg['scoop'][0]:.0f} × 奥行き {tg['scoop'][1]:.1f}。枠の上面まで開いている\n"
              f"・つまむ面（内へ押す面）: 奥行き {tg['face'][0]:.1f} × 高さ {tg['face'][1]:.2f}\n"
              f"・つまみの上面: 幅 {tg['top'][0]:.1f} × 奥行き {tg['top'][1]:.1f}（上から指の腹で内へずらしても動く）\n"
              "・奥行きが 1.0 で止まるのは、その奥に、かぎの掛かる縁（厚さ 1.6）が要るから\n\n"
              "電池の出し方（蓋を外した後・③）: 見えている上面と手前の縁を、爪か\n"
              "指の先で下へ押しながら手前へ引く。**本物のクリップの固さは、\n"
              "試し刷りでは分からない**")
    ax = fig.add_subplot(gs[3, 2:4])
    _note(ax, "B3 から直した所（利用者が刷った結果を受けて）\n"
              "・**外せない → つまむだけで出てくる**: つまみを上まで高くして、その内の\n"
              "  奥の角 K を、枠の手前の壁の残り（まぐさ）の端の斜めの面に当てる。\n"
              f"  かぎが外れた後、K が内へ {B.CAM_I} 動くと、蓋が手前へ {B.CAM_F:.2f} 出る（比 {B.CAM_R:.0f}）\n"
              "・つまむ所: 高さ 2.8 → 4.85・くぼみを幅 3.0 に。爪の段はやめた\n"
              "・かぎの角の斜め 0.35 → 0.30・予圧 0.30 → 0.05（つまむ量が増えた分、\n"
              "  ひずみの上限に入れるため）。**座りの力は、ほぼ無くなった**（がたは刷って見る）\n"
              "・ベッドから剥がれた（3 つのうち 2 つ）: 腕の底の縁を落とすのをやめた・\n"
              f"  胴の縁の落とし 0.15 → 0.10 = 底の面積 164 → {num['cam']['footprint']:.0f} mm2・蓋を板の\n"
              "  真ん中の列へ・1 層目を遅く（外周 50 → 20・中 105 → 30 mm/s）。\n"
              "  縁取り（brim）と、ちぎる耳は付けていない\n\n"
              "蓋 3 つの違い = かぎの掛かり（腕・つまみ・案内の隙 0.25 は同じ）\n"
              + "".join(f"  蓋 {n}: 掛かり {num['arms'][n]['engage']:.1f}・かぎが外れてから押し始めるまでの余裕 {num['arms'][n]['cam_margin']:.2f}・\n"
                        f"      つまんで {ej[n]['cam']:.1f} → 離して {ej[n]['rest']:.1f} 出る\n" for n in sorted(B.VARIANTS))
              + "  余裕が足りないと、かぎが外れ切る前に蓋が押されて、噛む。\n"
              "  余裕を増やすと、掛かりが減る。どこが良いかは、刷って決める\n\n"
              "片方だけつまむと: つまんだ側が "
              f"{moves['one_arm'][0]:.2f} 出て止まる。もう片方は {moves['one_arm_other']:.2f}\n"
              "  = 蓋は出てこない。ただし、片方ずつ 2 回つまめば開く\n\n"
              "**基板の変更の提案（B2 から同じ。いまは何も変えていない）**\n"
              f"・クリップ BT1 を奥へ {B.DBACK:.1f}・ねじ H15 を x {B.H15_OLD[0]:.1f} → {B.H15_NEW[0]:.1f}・\n"
              "  使っていない穴 H30・H31 を消す")
    ax = fig.add_subplot(gs[3, 4:])
    _note(ax, "数（立体から測った物と、TDS の値での計算。刷った物の値ではない）\n"
              f"・腕: 厚さ {arm['t']:.2f} × 高さ {B.HS:.1f} × 長さ {arm['length']:.1f}・予圧 {arm['pre']:.2f}\n"
              f"・付け根のひずみ: つまみ切って {arm['strain_pinch']:.2f} %（上限 {arm['strain_use']:.2f} %）・\n"
              f"  入れるとき {arm['strain_insert']:.2f} %・胴に当たって止まるとき {arm['strain_stop']:.2f} %\n"
              f"・つまむ力 {arm['pinch']:.1f} N ずつ・押し込む力 {arm['insert_force']:.1f} N（摩擦 0.3 込み）\n"
              f"・つまんで出る量 {e2['cam']:.1f}・離して止まる所 {y_end:.1f}（蓋 {B.MAIN}。摩擦を見ない）\n"
              f"  その間、腕 2 本が蓋を押す力は 平均 {e2['force']:.1f} N（蓋は {num['mass']:.2f} g）\n"
              f"・出た所から奥へ戻れる量 {e2['back']:.2f}（自分では掛かり直さない）\n"
              f"・電池が 20 N（指で強く押す・仮定）で、真ん中に当たるとき [MPa]\n"
              f"  板 {st['plate']['tension']:.0f}／{st['plate']['compression']:.0f}・柱 {st['stem']['stress']:.0f}・腕 {st['arm']['stress']:.0f}"
              f"（強さ: 引っ張り {S.PLA_TENSILE:.0f}・曲げ {S.PLA_BEND:.0f} → 半分以内）\n"
              "・強さに届く力 [N]: "
              + "・".join(f"{names[k]} {v:.0f}" for k, v in sorted(sf.items(), key=lambda q: q[1])[:3]) + "\n"
              f"  いちばん小さい {num['weakest'][1]:.0f} N = 電池 1.8 g の慣性で {num['weakest_g']:.0f} G（**導いた値**）\n"
              f"・電池が押す力は、つまみの斜めの面には掛からない（K と斜めの面の間は\n"
              f"  {B.K_CLEAR + B.CAM_M:.2f} 空いている）。押されると、かぎは外へ開く向き = 掛かる向き\n"
              f"・掛けた蓋の動ける量: 手前 {moves['forward']:.2f}・上 {moves['up']:.2f}・\n"
              f"  胴の遊び 奥 {moves['back']:.2f}・左右 {moves['side']:.2f}\n"
              f"・窓の上の壁の残り（張り出し {num['lintel']['length']:.1f}）を 10 N で押す: 下がり {num['lintel']['drop']:.3f}\n"
              "・上から見える物: 蓋の真ん中・左右のつまみの上面（幅 2.0）・その内の隙間\n"
              f"  （幅 {arm['front_gap']:.1f} × 奥行き 2.3）・指のくぼみ。蓋を付けた状態で、枠の外面・上面より\n"
              "  出る物は無い")
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def howto(out, num=None, moves=None):
    num = num or B.numbers()
    moves = moves or B.measure_moves()
    arm, ej = num["arms"], moves["eject"]
    acc = num["cell_access"]
    fig = plt.figure(figsize=(22, 16.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[0.85, 1.15], hspace=0.16, wspace=0.12)
    fig.suptitle("蓋の別案 B4 の試し刷り（coupon_cover_snap_plate_n04.gcode.3mf）: 刷り方・組み方・手で見る所", fontsize=14, y=0.995)
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
    ax.set_title("刷り上がった板（上から。下が手前）。蓋は、板の真ん中の列", fontsize=11)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[0, 1:])
    _draw(ax, scene(), lambda p: F.xy(p, 4.0), (99.5, 146.5, -53.0, -40.5), "組んだ所を、上面の少し下（4.0）で切った図。下が手前")
    _arrow(ax, (B.XN + 0.6, B.YF + 0.8), (101.0, -52.3), "つまみ（左）", va="center")
    _arrow(ax, (B.mx(B.XN) - 0.6, B.YF + 0.8), (140.5, -52.3), "つまみ（右）", va="center")
    ax.annotate("", (B.XN + 2.6, B.YF + 0.9), (B.XLIP - 2.6, B.YF + 0.9), arrowprops=dict(arrowstyle="->", color=BLUE, lw=2.0))
    ax.annotate("", (B.mx(B.XN) - 2.6, B.YF + 0.9), (B.mx(B.XLIP) + 2.6, B.YF + 0.9), arrowprops=dict(arrowstyle="->", color=BLUE, lw=2.0))
    ax.text(B.CX, -52.3, "外し方: 左右のつまみを、内へ押すだけ（青い矢印）→ 蓋が出てくる → 取る", fontsize=11, color=BLUE, ha="center", va="center")
    ax = fig.add_subplot(gs[1, 0])
    _note(ax, "刷る前に（前回、蓋 3 つのうち 2 つがベッドから剥がれた）\n"
              "・**ベッドの板を洗う**（食器用の洗剤と水で洗って、よく乾かす。指の脂が\n"
              "  付いていると、小さい物から剥がれる）\n"
              "・渡したファイルは、1 層目だけ遅くしてある（外周 20・中 30 mm/s）。\n"
              "  ほかは前回と同じ設定。縁取り（brim）は付けていない\n"
              "・蓋は、板の真ん中の列に置いてある（前回は、いちばん手前の列）\n"
              "・蓋の腕の底の縁を落とすのをやめた（1 層目から、腕の幅いっぱい）\n"
              "・それでも剥がれたら、どの蓋の・どの端から浮いたかを教えてください\n\n"
              "蓋の見分け方（上の板の奥の縁の切り欠きの数）= **かぎの掛かり**\n"
              + "".join(f"  蓋 {n}（切り欠き {n} つ）: 掛かり {arm[n]['engage']:.1f}・押し始めるまでの余裕 {arm[n]['cam_margin']:.2f}\n" for n in arm)
              + "  腕・つまみ・案内の隙（0.25 = 前回、刷れて入った蓋の値）は 3 つとも同じ\n"
              "  蓋 1 = いちばんしっかり掛かる。つまんだとき、かぎが外れ切る前に\n"
              "      押し始めて噛むかもしれない\n"
              "  蓋 3 = いちばん外しやすいはず。掛かりは小さい\n\n"
              "組み方\n"
              "1. 蓋の腕を、指で内へ 2 mm ほど押して、戻ることを見る\n"
              "2. 当て板に、枠の角を載せる（左と奥の当てに寄せる）\n"
              "3. 電池の代わりを、口から奥の止めまで入れる\n"
              f"4. 蓋を、手前からまっすぐ押し込む（約 {arm[B.MAIN]['insert_force']:.0f} N。左右がカチッ）\n\n"
              f"**この試し刷りは、クリップと電池を奥へ {B.DBACK:.1f}・ねじ H15 を右へ 3.5\n"
              "動かした基板の形**（いまの基板には合わない）", size=10.5)
    ax = fig.add_subplot(gs[1, 1])
    _note(ax, "手で見る所（蓋 1・2・3 のそれぞれで）\n"
              "a. 入るか・カチッと鳴るか\n"
              "b. 手前の面・上面が枠と揃うか（出っ張る物が無いか）\n"
              "c. 蓋をつまんで揺すって、がたつくか（**今回、座らせる力は弱い**）\n"
              "d. **外す: 左右のつまみを、指の先（または爪の横）で内へ押すだけ**\n"
              "   ・引かずに、つまむだけで蓋が出てくるか（つまんで "
              f"{ej[B.MAIN]['cam']:.1f}・離して {ej[B.MAIN]['rest']:.1f} の計算）\n"
              "   ・出た蓋を、指でつまんで取れるか\n"
              "   ・指が、つまみに掛かるか（くぼみに入るか）・力・痛くないか\n"
              "   ・途中で引っ掛かる（噛む）蓋はどれか\n"
              "   **つまんでも出てこない蓋は、不合格**（こじらない・裏から押さない）\n"
              "e. 片方のつまみだけを押す: 蓋が出てこないこと（その側が少し出て\n"
              "   止まるのは、計算どおり）\n"
              "f. **電池の代わりを、裏から棒で強く押す**: 蓋が外れないか・\n"
              "   蓋の真ん中が手前へふくらむか・白くなるか・戻るか\n"
              "g. 振る・机の高さから硬い床へ落とす（向きを変えて 5 回）\n"
              "h. 鞄の中のように、手前の面と上面を布・鍵・ペンの先で擦る・押す:\n"
              "   開かないか（つまみは、上面からも触れる）\n"
              "i. 20 回 開け閉めする: かぎ・腕・つまみが白くなる・欠ける・ゆるくなる\n"
              "j. **電池の出し方**: 蓋を外して、電池の代わりの、見えている上面\n"
              f"   （奥行き {acc['top_nominal']:.1f}）と手前の縁を、爪か指の先で下へ押しながら手前へ引く。\n"
              "   届くか・動きに無理が無いか（**本物のクリップが電池を押さえる\n"
              "   固さは、この試し刷りでは再現できない**）\n"
              "k. 口の縁・まぐさの端（つまみが当たる所）が欠けないか", size=10.5)
    ax = fig.add_subplot(gs[1, 2])
    _note(ax, "教えてほしいこと\n"
              "・**d で、つまむだけで出てきた蓋・出てこなかった蓋**（いちばん知りたい）\n"
              "・指がつまみに掛かったか（指の先で足りたか・爪が要ったか）\n"
              "・c で、がたついた蓋\n"
              "・f で、どのくらい押したら何が起きたか\n"
              "・h で、開いたか\n"
              "・刷っている途中で剥がれた物があれば、どれが・どこから\n"
              "・見た目: 上面に見える、つまみと隙間が気になるか\n\n"
              "この試し刷りで分からないこと\n"
              "・本物のクリップと電池での固さ → 電池を出すのに要る力\n"
              "・基板を変えてよいか（クリップを奥へ 2.0・H15 を右へ 3.5・\n"
              "  H30 と H31 を消す。配線と検査の見直しが要る）\n"
              "・長く使ったときの、腕のへたり", size=10.5)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return out


def render_all(out, moves=None):
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    num = B.numbers()
    moves = moves or B.measure_moves()
    return [cover_snap(out / "cover_snap.png", num, moves), howto(out / "coupon_cover_snap_howto.png", num, moves)]
