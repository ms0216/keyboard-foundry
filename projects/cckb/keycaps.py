"""CCKB のキーキャップ（無刻印・自分で刷る・D14）。**寸法は持たない**（spec / case_spec / mech）。

形: 平らな天板（KEYCAP_TOP_T）＋まわりのスカート＋Choc V1 のステムに挿す脚 2 本。
2.25u は Choc スタビの軸（mech の支点の半間隔 ±12.0）にも脚 2 本ずつ。

  - 平面: キーの幅 × 1u から、四周 KEYCAP_GAP ずつ引く（1u は 18.0 角）
  - 高さ: 天板の下面 = ステムの上面（interface.z()["stem_top"]）。上面 = keycap_top（14.2）
  - 脚: Kailh CPG135001D01-16 の穴 1.20 × 3.00・中心間 5.70（case_spec）から STEM_POST_FIT 細く
  - 刷る向き: 天板をベッドに（上下を返す）。脚とスカートが上に立ち、サポート無し

局所座標: 原点 = キーの中心・天板の下面（z=0）。上が +Z。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build123d import Axis, chamfer  # noqa: E402

import case_spec as CS  # noqa: E402
from case import box, fuse  # noqa: E402
from foundry.layout import UNIT  # noqa: E402

# 刷る種類（幅 u → 名前）。数は配列から数える（print_counts）
NAMES = {1.0: "keycap_1u", 1.5: "keycap_1u5", 1.75: "keycap_1u75", 2.25: "keycap_2u25"}


def stem_xs(w_u, sw):
    """脚を立てる x（キーの中心から）。スタビのキーは支点にも。"""
    s = sw.stab_offset_for(w_u)
    return (0.0,) if s is None else (-s, 0.0, s)


def posts(xs, fit, cs=CS, z_top=0.0):
    """脚（ステムの穴 2 つに入る角柱）を xs の各位置に。"""
    sx, sy = cs.STEM_SLOT
    px, py = (sx - fit) / 2, (sy - fit) / 2
    out = []
    for x in xs:
        for d in (-cs.STEM_PITCH / 2, cs.STEM_PITCH / 2):
            out.append(box(x + d - px, -py, z_top - cs.STEM_POST_L, x + d + px, py, z_top + 0.01))
    return out


def keycap(w_u, spec, sw, cs=CS, fit=None):
    """1 個のキーキャップ（局所座標）。"""
    fit = cs.STEM_POST_FIT if fit is None else fit
    g = spec.KEYCAP_GAP
    w, d = w_u * UNIT - 2 * g, UNIT - 2 * g
    t = spec.KEYCAP_TOP_T
    top = box(-w / 2, -d / 2, 0, w / 2, d / 2, t)
    top = chamfer(top.edges().group_by(Axis.Z)[-1], cs.KEYCAP_CHAMFER)
    k = cs.KEYCAP_SKIRT_T
    skirt = box(-w / 2, -d / 2, -cs.KEYCAP_SKIRT_H, w / 2, d / 2, 0.01) \
        - box(-w / 2 + k, -d / 2 + k, -cs.KEYCAP_SKIRT_H - 1, w / 2 - k, d / 2 - k, 1)
    return fuse([top, skirt] + posts(stem_xs(w_u, sw), fit, cs)).clean()


def print_counts(keys):
    """幅 u → 刷る数（配列から）。"""
    out = {}
    for k in keys:
        out[k.w_u] = out.get(k.w_u, 0) + 1
    return out


def print_parts(ifc=None):
    """刷る種類ごとに 1 個（名前 → 立体）＋全 62 個を A1 mini 2 枚に並べた物。数は print_counts。"""
    import interface as I

    ifc = ifc or I.Interface()
    counts = print_counts(ifc.keys)
    widths = sorted(counts)
    missing = [w for w in widths if w not in NAMES]
    assert not missing, f"キャップの名前が無い幅: {missing}"
    caps = {w: keycap(w, ifc.s, ifc.sw) for w in widths}
    out = {NAMES[w]: caps[w] for w in widths}
    out.update(batches(caps, counts, ifc.s.PRINT_MAX))
    return out


def batches(caps, counts, limit, gap=2.0):
    """全部のキャップを、刷る向き（天板が下）でベッドに並べた Compound 2 つ。

    1 枚目は 1u だけ、2 枚目は幅の広いキャップ。行に左から詰め、はみ出したら次の行へ。
    **1 枚に入らなければ落とす**（黙って 3 枚目を作らない）。
    """
    from build123d import Compound, Pos, Rot

    def lay(items):
        placed, x, y, row_h = [], 0.0, 0.0, 0.0
        for w in items:
            bb = caps[w].bounding_box()
            if x + bb.size.X > limit:
                x, y = 0.0, y + row_h + gap
                row_h = 0.0
            flip = Rot(180, 0, 0) * caps[w]
            fb = flip.bounding_box()
            placed.append(Pos(x - fb.min.X, y - fb.min.Y, -fb.min.Z) * flip)
            x += bb.size.X + gap
            row_h = max(row_h, bb.size.Y)
        c = Compound(placed)
        size = c.bounding_box().size
        assert max(size.X, size.Y) <= limit, f"キャップが 1 枚に並ばない: {size}"
        return c

    ones = [1.0] * counts.get(1.0, 0)
    wide = sorted((w for w, n in counts.items() if w != 1.0 for _ in range(n)), reverse=True)
    return {"keycaps_set_1u": lay(ones), "keycaps_set_wide": lay(wide)}
