"""cckb-click のたわみの見積もり（枠 ＋ 基板を、長手に曲がる 1 本の梁として）。

    .venv/bin/python3 projects/cckb-click/click_stiffness.py     # 表と build/cckb-click/main_stiffness.png

**断面は作った立体から測る**（枠を x 一定の面で切り、面積・図心・断面二次モーメントを多角形から計算する）。
継ぎ目（左右の枠の間）では枠の断面が無くなり、基板だけが曲げを受ける——そこも測ったとおりに入る。

材料の値は**一般値で、測っていない**（幅で持つ）:
  FR-4  曲げ弾性率 22 GPa（18〜24。JLC の板の値は未確認）
  PLA   曲げ弾性率 2.6 GPa（積層した PLA の文献値 2.3〜3.5 の低い側。刷る向きは長手に線が通る向き）

枠と基板がどれだけ「1 本」になるかは、ねじ（外周 20 本）がずれを止める度合いで決まる。**これは計算では分からない**ので、
両端を出す: 「重ねただけ」（ずれ放題 = 2 本の梁の和）と「一体」（ずれ 0）。実物はその間。

誤入力に効くのは梁全体のたわみではなく、**枠の下面と基板の間の距離が、押していないキーの所で縮む量**（公差の端で 0.1 縮むと ON）。
枠と基板は全部のキーの脇の柱で突っ張っているので、縮むのは柱と柱の間だけ。その量を local() が出す。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

E_FR4 = (18000.0, 22000.0, 24000.0)      # MPa（低・名目・高）
E_PLA = (2300.0, 2600.0, 3500.0)
G = 9.81e-3                              # N/g
GRIP = 30.0                              # 片端を持つときに手が掴む長さ
PRESS_N = 10.0                           # 「真ん中を押す」力（強く押し込む。打鍵は 1〜3 N）
MARGIN = 0.1                             # 公差の端で ON になるまでの、枠の下面と基板の距離の余裕


def poly_props(polys):
    """断面 [(外の輪郭, [穴])]（座標は (y, z)）→ (面積, 図心の z, 図心まわりの断面二次モーメント)。"""
    A = Sz = Izz = 0.0
    for outer, inner in polys:
        for ring, sign in [(outer, 1.0)] + [(h, -1.0) for h in inner]:
            a = s = i = 0.0
            pts = list(ring)
            for (y0, z0), (y1, z1) in zip(pts, pts[1:] + pts[:1]):
                c = y0 * z1 - y1 * z0
                a += c / 2
                s += (z0 + z1) * c / 6
                i += (z0 * z0 + z0 * z1 + z1 * z1) * c / 12
            k = sign * (1.0 if a >= 0 else -1.0)
            A, Sz, Izz = A + k * a, Sz + k * s, Izz + k * i
    if A <= 1e-9:
        return 0.0, 0.0, 0.0
    zc = Sz / A
    return A, zc, Izz - A * zc * zc


def frame_sections(step=2.0):
    """枠の断面を x ごとに [(x, 面積, 図心 z, I)]。"""
    from build123d import Plane

    import click_case as C
    import click_figs as F

    halves = C.frame_halves()
    f = C.LAY.frame
    out = []
    n = int((f[2] - f[0]) / step)
    for i in range(n + 1):
        x = f[0] + 0.5 + (f[2] - f[0] - 1.0) * i / n
        polys = []
        for side in C.SIDES:
            polys += F.section(halves[side], Plane.YZ.offset(x), "Y", "Z")
        out.append((x,) + poly_props(polys))
    return out


def ei_profiles(sections, lay, e_fr4, e_pla):
    """x ごとの曲げ剛性 [N·mm²]: 基板だけ・重ねただけ・一体。"""
    s = lay.s
    p = lay.pcb
    b, t = p[3] - p[1], s.PCB_T
    a_p, z_p, i_p = b * t, -t / 2, b * t ** 3 / 12
    out = []
    for x, a_f, z_f, i_f in sections:
        ei_p = e_fr4 * i_p
        loose = ei_p + e_pla * i_f
        if a_f <= 1e-9:
            out.append((x, ei_p, ei_p, ei_p))
            continue
        ea = e_fr4 * a_p + e_pla * a_f
        zc = (e_fr4 * a_p * z_p + e_pla * a_f * z_f) / ea
        one = e_fr4 * (i_p + a_p * (z_p - zc) ** 2) + e_pla * (i_f + a_f * (z_f - zc) ** 2)
        out.append((x, ei_p, loose, one))
    return out


def _integrate(xs, kappa, clamp_i=None):
    """曲率 κ(x) → たわみ。clamp_i があれば、そこで傾き 0・たわみ 0（片持ち）。無ければ両端のたわみ 0（単純支持）。"""
    n = len(xs)
    th = [0.0] * n
    y = [0.0] * n
    for i in range(1, n):
        dx = xs[i] - xs[i - 1]
        th[i] = th[i - 1] + (kappa[i] + kappa[i - 1]) / 2 * dx
        y[i] = y[i - 1] + (th[i] + th[i - 1]) / 2 * dx
    if clamp_i is not None:
        t0, y0 = th[clamp_i], y[clamp_i]
        return [y[i] - y0 - t0 * (xs[i] - xs[clamp_i]) for i in range(n)]
    slope = (y[-1] - y[0]) / (xs[-1] - xs[0])
    return [y[i] - y[0] - slope * (xs[i] - xs[0]) for i in range(n)]


def beam_cases(profile, mass_g, col):
    """梁のたわみの最大 [mm]。col = 1（基板だけ）・2（重ねただけ）・3（一体）。
    {"片端を持つ": …, "両端を持つ": …, "両端を持って真ん中を押す": …}"""
    xs = [r[0] for r in profile]
    ei = [r[col] for r in profile]
    L = xs[-1] - xs[0]
    w = mass_g * G / L
    out = {}
    # 片端（左）を持つ: 左から GRIP は手の中（動かない）。その右が片持ち
    ci = min(range(len(xs)), key=lambda i: abs(xs[i] - (xs[0] + GRIP)))
    kappa = [(-(w * (xs[-1] - x) ** 2 / 2) / e if i >= ci else 0.0) for i, (x, e) in enumerate(zip(xs, ei))]
    out["片端を持つ"] = max(abs(v) for v in _integrate(xs, kappa, ci))
    # 両端を持つ（単純支持・自重）
    kappa = [-(w * (x - xs[0]) * (xs[-1] - x) / 2) / e for x, e in zip(xs, ei)]
    out["両端を持つ"] = max(abs(v) for v in _integrate(xs, kappa))
    # 両端を持って真ん中を PRESS_N で押す（自重は上の値に足す）
    mid = (xs[0] + xs[-1]) / 2
    kappa = [-(PRESS_N / 2 * (x - xs[0] if x <= mid else xs[-1] - x)) / e for x, e in zip(xs, ei)]
    out["両端を持って真ん中を押す"] = max(abs(v) for v in _integrate(xs, kappa))
    return out


def rib_section(lay):
    """リブのいちばん細い断面（くぼみが両側から入る所）: 上の層（くぼみの底より上）は幅いっぱい、下の層はくぼみの間の壁だけ。
    (面積, 断面二次モーメント)。tests が作った枠を切って同じ面積になることを見る。"""
    s = lay.s
    b = lay.rib()
    web = b - 2 * (s.TAB_REACH + s.POCKET_CLEAR)
    t_top = s.FRAME_T - s.POCKET_DEPTH
    t_web = s.POCKET_DEPTH
    c = s.HOLE_CHAMFER                      # 穴の上の縁の面取りが、リブの上の両角を三角に削る（作った枠を切って測ると 2.8 でなく 2.64 だった）
    parts = [(b * t_top, t_web + t_top / 2, b * t_top ** 3 / 12),
             (web * t_web, t_web / 2, web * t_web ** 3 / 12),
             (-c * c, s.FRAME_T - c / 3, -2 * c ** 4 / 36)]
    a = sum(q[0] for q in parts)
    zc = sum(q[0] * q[1] for q in parts) / a
    i = sum(q[2] + q[0] * (q[1] - zc) ** 2 for q in parts)
    return a, i


def local(lay, e_fr4=E_FR4[0], e_pla=E_PLA[0]):
    """枠の下面と基板の距離が、押していないキーの所で縮む量 [mm]（材料は柔らかい側）。{何: 量}"""
    s = lay.s
    from foundry.layout import UNIT

    out = {}
    # 1. 指が押し切って、枠のリブの交点（柱と柱の真ん中）を押す。梁 = 柱の端から次の柱の端まで・両端固定・断面はいちばん細い所
    #    （実物は、柱の近くではくぼみが無く太い = これより硬い）。力は 3 N（打鍵で底を突く）と PRESS_N（強く押し込む）
    span = UNIT - s.POST_L
    _, i_rib = rib_section(lay)
    for f in (3.0, PRESS_N):
        out["リブの交点を %.0f N で押す（柱の間 %.2f・両端固定・くぼみの所の断面）" % (f, span)] = f * span ** 3 / (192 * e_pla * i_rib)
    # 2. 柱の縮み（1.6 × 5.0 × 高さ 3.0 の PLA に PRESS_N）
    out["柱 1 本が %.0f N で縮む" % PRESS_N] = PRESS_N * s.FRAME_UNDER / (e_pla * s.POST_W * s.POST_L)
    # 3. 手に持って押す: スイッチの下で基板が柱の間（1 キー）で逃げる量。**広がる向き**（誤入力しない側）だが、大きさを出す
    i_pcb = UNIT * s.PCB_T ** 3 / 12
    out["基板が柱の間で逃げる（%.0f N・幅 1 キーの帯・広がる向き）" % PRESS_N] = PRESS_N * UNIT ** 3 / (48 * e_fr4 * i_pcb)
    return out


def chord_gap(kappa, lay):
    """曲率 κ で一緒に曲がったとき、柱の間（1 キー）で枠（高さ 4）と基板（高さ −0.8）の弧の差。"""
    from foundry.layout import UNIT

    h = lay.s.FRAME_UNDER + lay.s.FRAME_T / 2 + lay.s.PCB_T / 2
    return UNIT ** 2 / 8 * kappa * kappa * h


def report():
    import click_case as C

    lay = C.LAY
    secs = frame_sections()
    mass = C.weights()["合計"]
    rows = {}
    for label, (ef, ep) in (("柔らかい側", (E_FR4[0], E_PLA[0])), ("名目", (E_FR4[1], E_PLA[1])), ("硬い側", (E_FR4[2], E_PLA[2]))):
        prof = ei_profiles(secs, lay, ef, ep)
        rows[label] = {name: beam_cases(prof, mass, col) for name, col in (("基板だけ", 1), ("重ねただけ", 2), ("一体", 3))}
        rows[label]["EI"] = dict(pcb=prof[len(prof) // 4][1], loose=max(r[2] for r in prof), one=max(r[3] for r in prof),
                                 one_min=min(r[3] for r in prof))
    return dict(mass=mass, sections=secs, rows=rows, local=local(lay))


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import click_case as C

    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    r = report()
    print(f"重さ {r['mass']:.0f} g・長さ {C.LAY.frame[2] - C.LAY.frame[0]:.1f}")
    for label, d in r["rows"].items():
        print(f"== {label}（EI 基板 {d['EI']['pcb']:.3g}・一体の最大 {d['EI']['one']:.3g}・一体の最小〔継ぎ目〕{d['EI']['one_min']:.3g} N·mm²）")
        for name in ("基板だけ", "重ねただけ", "一体"):
            print(f"   {name}: " + " / ".join(f"{k} {v:.2f}" for k, v in d[name].items()))
    for k, v in r["local"].items():
        print(f"   局所: {k}: {v:.4f} mm（余裕 {MARGIN}）")
    lay = C.LAY
    prof = ei_profiles(r["sections"], lay, E_FR4[1], E_PLA[1])
    fig, ax = plt.subplots(1, 1, figsize=(12, 4))
    xs = [p[0] for p in prof]
    for col, name in ((1, "基板だけ"), (2, "重ねただけ（ずれ放題）"), (3, "一体（ずれ 0）")):
        ax.plot(xs, [p[col] for p in prof], label=name)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("曲げ剛性 EI [N·mm²]")
    ax.set_title("長手の曲げ剛性（名目の材料の値）。真ん中の谷 = 枠の継ぎ目（基板だけ）")
    ax.legend()
    fig.tight_layout()
    out = C.OUT / "main_stiffness.png"
    fig.savefig(out, dpi=100)
    print("絵", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
