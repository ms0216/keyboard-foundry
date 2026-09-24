"""試し刷りの小片（公差のクーポン）。**本番の部品を刷る前に刷る。**

「未実測なら先に公差のクーポン」（docs/knowledge/case-and-print.md）。どれも本番と同じ厚さ・
同じ向きで刷り、本番の部品（スイッチ・スタビ・ナット・インサート・M2 ネジ）をはめて選ぶ。
**どの穴かは縁の切り欠きの数で見分ける**（1 本目 = 表の最初の値）。

  coupon_switch  プレート 1.2 にスイッチの開口 13.7 / 13.8 / 13.9 / 14.0（スイッチの爪が掛かって抜けないか）
  coupon_stab    プレート 1.2 に Choc スタビ 1 組（±12.0）＋スイッチの開口。広げ 0.05 / 0.15 / 0.25 の 3 枚
  coupon_stem    キャップの天板の小片に脚 2 本。細くする量 0.00 / 0.10 / 0.15 / 0.20 の 4 枚（切り欠き 0〜3）
  coupon_nut     プレート 1.2 に M2 ナットの六角の穴 4.1 / 4.2 / 4.3（落ちて入り、回らないか）
  coupon_insert  インサートの柱 φ5.2（下穴 2.9 / 3.0 / 3.1）と、ネジを捕まえる膜（穴 1.4 / 1.6 / 1.8）
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build123d import Compound, Pos, Rot, extrude  # noqa: E402

import case_spec as CS  # noqa: E402
from case import box, cyl, fuse, hex_prism  # noqa: E402
from foundry.layout import UNIT  # noqa: E402
from foundry.mech import CHOC_V1  # noqa: E402
from foundry.plate import M2_CLEAR_D, choc_stab_polygons, stab_cutout_face  # noqa: E402


def notches(part, n, x0, y_edge, t, depth=1.0, w=0.8, pitch=2.0):
    """縁（y = y_edge の手前の辺）に n 本の切り欠き。"""
    for k in range(n):
        x = x0 + k * pitch
        part = part - box(x, y_edge - 1, -1, x + w, y_edge + depth, t + 1)
    return part


def row(parts, gap):
    """立体を x に並べて 1 つの Compound にする（1 つの STL で刷る）。"""
    out, x = [], 0.0
    for p in parts:
        bb = p.bounding_box()
        out.append(Pos(x - bb.min.X, -bb.min.Y, -bb.min.Z) * p)
        x += bb.size.X + gap
    return Compound(out)


def switch_coupon(cs=CS, sw=CHOC_V1):
    t = sw.plate_t
    n = len(cs.COUPON_SWITCH_CUTOUTS)
    w, d = n * UNIT, UNIT
    part = box(0, 0, 0, w, d, t)
    for k, c in enumerate(cs.COUPON_SWITCH_CUTOUTS):
        x = (k + 0.5) * UNIT
        part = part - box(x - c / 2, d / 2 - c / 2, -1, x + c / 2, d / 2 + c / 2, t + 1)
        part = notches(part, k + 1, x - 3, 0.0, t)
    return part


def stab_coupon(kerf, idx, cs=CS, sw=CHOC_V1):
    t = sw.plate_t
    s = sw.stab_offset_for(2.25)
    w, d = 2 * s + 12.0, UNIT + 4.0          # 奥の縁（スタビの切り欠きの先 8.6）に肉を残す
    part = box(-w / 2, -d / 2, 0, w / 2, d / 2, t)
    part = part - box(-sw.cutout / 2, -sw.cutout / 2, -1, sw.cutout / 2, sw.cutout / 2, t + 1)
    for poly in choc_stab_polygons(s):
        face = stab_cutout_face(s, polygon=poly, kerf=kerf)
        part = part - Pos(0, 0, -1) * extrude(face, t + 2)
    return notches(part, idx + 1, -w / 2 + 2, -d / 2, t)


def stem_coupon(fit, idx, cs=CS, spec=None):
    import keycaps

    t = spec.KEYCAP_TOP_T
    a = 14.0
    part = box(-a / 2, -a / 2, 0, a / 2, a / 2, t)
    part = fuse([part] + keycaps.posts((0.0,), fit, cs))
    part = notches(part, idx, -a / 2 + 1.5, -a / 2, t)
    return Rot(180, 0, 0) * part          # 天板をベッドに（本番のキャップと同じ向き）


def nut_coupon(cs=CS, sw=CHOC_V1):
    t = sw.plate_t
    n = len(cs.COUPON_NUT_AFS)
    pitch = 10.0
    part = box(0, 0, 0, n * pitch, 10.0, t)
    for k, af in enumerate(cs.COUPON_NUT_AFS):
        part = part - hex_prism((k + 0.5) * pitch, 5.0, af, -1, t + 1)
        part = notches(part, k + 1, k * pitch + 1.0, 0.0, t, pitch=1.6)
    return part


def insert_coupon(spec, cs=CS):
    """床（spec.CASE_FLOOR）の上に、柱（下穴を比べる）と、膜のボス（ネジを捕まえる穴を比べる）。"""
    base_t = spec.CASE_FLOOR
    pitch = 9.0
    n = len(cs.COUPON_INSERT_HOLES) + len(cs.COUPON_CAPTIVE_HOLES)
    part = box(0, 0, 0, n * pitch, 10.0, base_t)
    h = cs.INSERT_L + cs.INSERT_HOLE_EXTRA + 1.0
    for k, hd in enumerate(cs.COUPON_INSERT_HOLES):
        x = (k + 0.5) * pitch
        part = part.fuse(cyl(x, 5.0, base_t - 0.1, base_t + h, spec.LID_PILLAR_D))
        part = part - cyl(x, 5.0, base_t + h - cs.INSERT_L - cs.INSERT_HOLE_EXTRA, base_t + h + 1, hd)
        part = notches(part, k + 1, k * pitch + 1.0, 0.0, base_t, pitch=1.6)
    # 膜: 本番（右のふたを天板を下に刷る）と同じく、ベッド側から φ2.4 の穴、上端に膜
    web_h = cs.LID_BOSS_H + spec.LID_T
    for j, hd in enumerate(cs.COUPON_CAPTIVE_HOLES):
        k = len(cs.COUPON_INSERT_HOLES) + j
        x = (k + 0.5) * pitch
        part = part.fuse(cyl(x, 5.0, 0, web_h, spec.LID_PILLAR_D))
        part = part - cyl(x, 5.0, -1, web_h - cs.CAPTIVE_WEB_T, M2_CLEAR_D)
        part = part - cyl(x, 5.0, web_h - cs.CAPTIVE_WEB_T - 0.01, web_h + 1, hd)
        part = notches(part, j + 1, k * pitch + 1.0, 0.0, base_t, pitch=1.6)
    return part.clean()


def parts(ifc=None, cs=CS):
    import interface as I

    ifc = ifc or I.Interface()
    s = ifc.s
    return {
        "coupon_switch": switch_coupon(cs, ifc.sw),
        "coupon_stab": row([stab_coupon(k, i, cs, ifc.sw)
                            for i, k in enumerate(cs.COUPON_STAB_KERFS)], cs.COUPON_GAP),
        "coupon_stem": row([stem_coupon(f, i, cs, s)
                            for i, f in enumerate(cs.STEM_FIT_STEPS)], cs.COUPON_GAP),
        "coupon_nut": nut_coupon(cs, ifc.sw),
        "coupon_insert": insert_coupon(s, cs),
    }
