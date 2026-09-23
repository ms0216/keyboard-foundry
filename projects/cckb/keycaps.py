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
    """刷る種類ごとに 1 個（名前 → 立体）。数は print_counts。"""
    import interface as I

    ifc = ifc or I.Interface()
    widths = sorted(print_counts(ifc.keys))
    missing = [w for w in widths if w not in NAMES]
    assert not missing, f"キャップの名前が無い幅: {missing}"
    return {NAMES[w]: keycap(w, ifc.s, ifc.sw) for w in widths}
