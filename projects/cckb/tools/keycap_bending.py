"""キーキャップの縁を押したときのたわみの見積り（決定記録 2026-09-28-keycap-skin §3）。

    .venv/bin/python3 projects/cckb/tools/keycap_bending.py [--old <前の keycaps.py> <前の case_spec.py> <前の spec.py>]

方法（前の見積りと同じ）: 片持ちの梁。**支えから縁まで**を x の断面ごとに切り、断面（天板＋スカート）の
図心まわりの断面二次モーメント I(x) を刷る形（keycaps.keycap）から測る。縁に P = 3 N を置き、
たわみ δ = ∫ P (x_e − x)² / (E I(x)) dx（単位荷重法）、根元の曲げ応力 σ = M c / I。
  E = 2580 MPa（Bambu PLA Basic。前の見積りと同じ値）
  1u     支え = ステムの外周（x = 3.25）→ 縁 x = 9 − KEYCAP_GAP
  2.25u  支え = スタビの台の外周（x = 11.9 + 2.55）→ 縁 x = 20.25 − KEYCAP_GAP
スカートの有無の 2 通り（天板だけ = 梁に沿う 2 本のスカートを内側で切る。縁の側のスカートは残る）。
**刷った層の向き**（天板は層に平行・曲げは層の面内）と穴・段の応力集中は見ていない。数は比べるための物。

梁は断面を x で切るので、**ステムのまわりの輪（つばの上）で力が筒へ集まる**ことが見えない。そこで edge_load: 円板
（Kirchhoff・ν = 0.35）を r の 1 次元の有限要素で、内の縁 = 筒の外周 r 2.75 を固定、1u の縁の真ん中 r 9.0 に 3 N。
厚さ t(r) は keycaps.plate_levels の値（膜・つばの上の輪・ハウジングの上）。スカートは入れない。縁を押す（打鍵）のも、
縁に爪をかけて片側からこじって抜くのも同じ形（向きが逆）。応力は 6M/t²（M_r・M_θ の大きい方）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[1]
for p in (str(ROOT), str(PROJ)):
    if p not in sys.path:
        sys.path.insert(0, p)

E = 2580.0       # MPa（Bambu PLA Basic。前の見積りと同じ値）
P = 3.0          # N（縁を指で押す）


def section_props(part, x):
    """part を x = 一定の面で切った断面の (面積, 図心 z, 図心まわりの I, 図心から上下の端までの最大)。"""
    from build123d import Face, Plane
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    face = Plane(origin=(x, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Face.make_rect(200, 200)
    sec = part & face
    props = GProp_GProps()
    zs = []
    for f in sec.faces():
        BRepGProp.SurfaceProperties_s(f.wrapped, props)
        bb = f.bounding_box()
        zs += [bb.min.Z, bb.max.Z]
    a = props.Mass()
    if a <= 0:
        return 0.0, 0.0, 0.0, 0.0
    zc = props.CentreOfMass().Z()
    i = props.MatrixOfInertia().Value(2, 2)        # 断面は x 一定の面なので Iyy = ∫ (z − zc)² dA
    return a, zc, i, max(max(zs) - zc, zc - min(zs))


def cantilever(part, x0, xe, step=0.05):
    """支え x0 から縁 xe の片持ち梁。(たわみ mm, 根元の応力 MPa, 根元の I, 根元の断面の高さ)。"""
    n = max(2, int(round((xe - x0) / step)))
    xs = [x0 + (xe - x0) * (k + 0.5) / n for k in range(n)]
    dx = (xe - x0) / n
    delta = 0.0
    for x in xs:
        _, _, i, _ = section_props(part, x)
        delta += P * (xe - x) ** 2 / (E * i) * dx
    _, _, i0, c0 = section_props(part, x0 + 1e-3)
    return delta, P * (xe - x0) * c0 / i0, i0, c0


def cases(kc, spec, sw, cs):
    from build123d import Box, Pos

    from foundry.layout import UNIT

    g = spec.KEYCAP_GAP
    out = []
    for w_u, x0 in ((1.0, cs.SW_STEM_D / 2), (2.25, 11.9 + cs.STAB_SOCKET_BOSS_D / 2)):
        cap = kc.keycap(w_u, spec, sw, cs)
        xe = w_u * UNIT / 2 - g
        d_in = UNIT - 2 * g - 2 * cs.KEYCAP_SKIRT_T
        plate_only = cap & (Pos(0, 0, 0) * Box(2 * xe, d_in, 20))
        for name, part in (("スカートあり", cap), ("天板だけ", plate_only)):
            out.append((f"{w_u}u", name, x0, xe) + cantilever(part, x0, xe))
    return out


NU = 0.35


def ring_fe(prof, a, b, harmonic, p=1.0, ne=600):
    """円板の曲げ（Kirchhoff）を r の 1 次元の有限要素（Hermite 3 次）で。w = W(r) cos(nθ)、n = harmonic（0 か 1）。
    内の縁 r = a を固定（筒はステムの十字に挿さっていて動かない・傾かない）、外の縁 r = b は自由で、
    θ = 0 の縁の 1 点に p（のうち n 次の成分）。返り値 (縁のたわみ, [(r, t, M_r, M_θ)])。"""
    import numpy as np

    rs = np.linspace(a, b, ne + 1)
    nd = 2 * (ne + 1)
    k = np.zeros((nd, nd))
    gp, gw = np.polynomial.legendre.leggauss(6)

    def shape(xi, h):
        n = np.array([1 - 3 * xi ** 2 + 2 * xi ** 3, h * (xi - 2 * xi ** 2 + xi ** 3), 3 * xi ** 2 - 2 * xi ** 3,
                      h * (-xi ** 2 + xi ** 3)])
        d1 = np.array([-6 * xi + 6 * xi ** 2, h * (1 - 4 * xi + 3 * xi ** 2), 6 * xi - 6 * xi ** 2,
                       h * (-2 * xi + 3 * xi ** 2)]) / h
        d2 = np.array([-6 + 12 * xi, h * (-4 + 6 * xi), 6 - 12 * xi, h * (-2 + 6 * xi)]) / h ** 2
        return n, d1, d2

    def curv(n, d1, d2, r):
        if harmonic == 0:
            return d2, d1 / r, np.zeros(4), 2 * np.pi
        kt = d1 / r - n / r ** 2
        return d2, kt, kt, np.pi

    def stiff(t):
        return E * t ** 3 / (12 * (1 - NU ** 2))

    for e in range(ne):
        r0, r1 = rs[e], rs[e + 1]
        h = r1 - r0
        d = stiff(prof((r0 + r1) / 2))
        ke = np.zeros((4, 4))
        for x, w in zip(gp, gw):
            xi = (x + 1) / 2
            r = r0 + xi * h
            kr, kt, ktw, fac = curv(*shape(xi, h), r)
            bm = np.outer(kr + kt, kr + kt) - (1 - NU) * (np.outer(kr, kt) + np.outer(kt, kr)) \
                + 2 * (1 - NU) * np.outer(ktw, ktw)
            ke += fac * d * bm * r * w * h / 2
        ix = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        k[np.ix_(ix, ix)] += ke
    f = np.zeros(nd)
    f[-2] = p                    # 1 点の荷重の n = 0・n = 1 の成分は、どちらも縁の W に p の仕事をする
    free = list(range(2, nd))
    u = np.zeros(nd)
    u[free] = np.linalg.solve(k[np.ix_(free, free)], f[free])
    out = []
    for e in range(ne):
        r0, r1 = rs[e], rs[e + 1]
        h = r1 - r0
        t = prof((r0 + r1) / 2)
        d = stiff(t)
        ue = u[[2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]]
        for xi in (0.02, 0.5, 0.98):
            r = r0 + xi * h
            n, d1, d2 = shape(xi, h)
            w0, w1, w2 = n @ ue, d1 @ ue, d2 @ ue
            if harmonic == 0:
                mr, mt = -d * (w2 + NU * w1 / r), -d * (w1 / r + NU * w2)
            else:
                mr, mt = -d * (w2 + NU * (w1 / r - w0 / r ** 2)), -d * ((w1 / r - w0 / r ** 2) + NU * w2)
            out.append((r, t, mr, mt))
    return u[-2], out


def edge_load(label, t_skin, t_ring, t_out, cs, p=P):
    """1u の縁の真ん中（r = 9.0・θ = 0）に p。押す（打鍵）も、縁に爪をかけて片側からこじって抜くのも同じ形
    （向きが逆なだけ）。内の縁 = 筒の外周 r 2.75。スカートは入れない（縁は自由）。**つばの上の輪 r 3.25〜4.35 を
    通る曲げは、縁の荷重を筒へ渡すのに必ず要る**（輪より内には膜と筒しか無い）。"""
    r_a, r0, r1 = cs.STEM_TUBE_OD / 2, cs.KEYCAP_COLLAR_RELIEF[0] / 2, cs.KEYCAP_COLLAR_RELIEF[1] / 2
    r_b = 9.0

    def prof(r):
        return t_skin if r < r0 else (t_ring if r < r1 else t_out)

    d0, o0 = ring_fe(prof, r_a, r_b, 0, p)
    d1, o1 = ring_fe(prof, r_a, r_b, 1, p)
    rows = [(r, t, 6 * max(abs(a0 + a1), abs(b0 + b1)) / t ** 2) for (r, t, a0, b0), (_, _, a1, b1) in zip(o0, o1)]
    worst = max(rows, key=lambda q: q[2])
    print(f"縁に {p:.0f} N\t{label}\t膜 {t_skin}・輪 {t_ring}・外 {t_out}\t縁のたわみ {(d0 + d1) * 1000:.0f} µm\t"
          f"最大の曲げ応力 {worst[2]:.1f} MPa（r {worst[0]:.2f}・厚さ {worst[1]}）")
    return worst[2]


def load_module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main(argv):
    import case_spec as CS
    import interface as I
    import keycaps as KC

    ifc = I.Interface()
    rows = {"いま": cases(KC, ifc.s, ifc.sw, CS)}
    if argv[:1] == ["--old"]:
        kc_old = load_module("keycaps_old", argv[1])
        cs_old = load_module("case_spec_old", argv[2])
        spec_old = load_module("spec_old", argv[3])
        rows["前"] = cases(kc_old, spec_old, ifc.sw, cs_old)
    for label, rs in rows.items():
        for key, name, x0, xe, d, sig, i0, c0 in rs:
            print(f"{label}\t{key}\t{name}\t支え {x0:.2f} → 縁 {xe:.3f}\tたわみ {d * 1000:.1f} µm\t"
                  f"根元の応力 {sig:.1f} MPa\tI {i0:.3f} mm4")
    # 縁の 1 点に 3 N（押す・片側からこじって抜く）: 前（天板 1.2・つばの窪みの所 0.95）と、膜 0.6 / 0.8 / 1.0 / 1.2
    # （いまの膜 spec.KEYCAP_TOP_T に「いま」と付ける。2026-10-03 から 1.0）
    edge_load("前", 1.2, 0.95, 1.2, CS)
    for t in (0.6, 0.8, 1.0, 1.2):
        label = f"膜 {t}" + ("（いま）" if abs(t - ifc.s.KEYCAP_TOP_T) < 1e-9 else "")
        lv = KC.plate_levels(_Over(ifc.s, KEYCAP_TOP_T=t), CS)
        edge_load(label, lv["skin"], lv["collar"], lv["housing"], CS)


class _Over:
    def __init__(self, base, **values):
        self._base = base
        self.__dict__.update(values)

    def __getattr__(self, name):
        return getattr(self._base, name)


if __name__ == "__main__":
    main(sys.argv[1:])
