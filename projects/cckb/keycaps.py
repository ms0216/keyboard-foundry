"""CCKB のキーキャップ（無刻印・自分で刷る・D14）。**寸法は持たない**（spec / case_spec / mech）。

形: 天板＋まわりのスカート＋ **Choc V2 静音の十字に挿す筒**（2026-09-26 に V1 の脚 2 本から）。
2.25u はスタビ（遊舎工房 A050001-01-1）の軸の受け口も（支点の半間隔 mech.CHOC_V2_STAB_PIVOT の ±11.9。販売者の足跡の実測）。

  - 平面: キーの幅 × 1u から、四周 KEYCAP_GAP ずつ引く（1u は 18.0 角）
  - 高さ: 上面 = ステムの上面 ＋ spec.KEYCAP_TOP_T（膜 0.6。keycap_top 13.8）。**天板の厚さは場所ごと**（2026-09-28
    利用者の決定・決定記録 2026-09-28-keycap-skin）: ステムの真上は膜（下面 = ステムの上面）、ハウジングの上・つばの上の輪は
    押し切りで当たらない厚さ（層の倍数に切り下げ）、それより外は KEYCAP_PLATE_T。数は plate_levels が spec から導く
  - 筒: 外径 STEM_TUBE_OD・長さ STEM_TUBE_L（ステムの上面から）・十字の穴 STEM_CROSS_SLOT（静音の窪み φ5.70 の中に入る）
  - スタビの受け口: 天板の下の細い台（φ STAB_SOCKET_BOSS_D・下端はステムの上面から STAB_SOCKET_GRIP）に十字の穴。
    穴は天板の中まで。押し切ると台は箱の上面の口（スライダーの通る角 STAB_SLIDER_W）に入る（2026-09-26・監査 E 重要 1）
  - 刷る向き: 天板をベッドに（上下を返す）。膜は 1〜3 層目。筒・台・スカートが上に立ち、サポート無し

局所座標: 原点 = キーの中心・ステムの上面（z=0。膜の下面）。上が +Z。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import math  # noqa: E402

from build123d import Axis, chamfer  # noqa: E402

import case_spec as CS  # noqa: E402
from case import box, cyl, fuse  # noqa: E402
from foundry.layout import UNIT  # noqa: E402
from foundry.mech import CHOC_V2_STAB_SOURCES  # noqa: E402

# 刷る種類（幅 u → 名前）。数は配列から数える（print_counts）
NAMES = {1.0: "keycap_1u", 1.5: "keycap_1u5", 1.75: "keycap_1u75", 2.25: "keycap_2u25"}


def travel_max(spec):
    """押し切りでキャップが沈む最大（静音の全行程 2.8 ＋ 0.25）。"""
    return spec.SWITCH_TRAVEL + spec.SWITCH_TRAVEL_TOL


def layer_floor(t, cs=CS):
    """厚さ t を刷る層（PRINT_LAYER）の倍数に切り下げる。スライサーは層の真ん中で切るので、層の倍数でない厚さは
    上の層に丸められて刷られうる（0.75 → 0.8）。切り下げれば刷った物は設計より厚くならない。"""
    return round(math.floor(t / cs.PRINT_LAYER + 1e-9) * cs.PRINT_LAYER, 6)


def plate_levels(spec, cs=CS):
    """天板の場所ごとの厚さ（キャップの上面から下へ）。**spec の数から導く**（2026-09-28・決定記録 2026-09-28-keycap-skin）。

    押し切り（travel_max）で天板の下面が障害物の上面より KEYCAP_PRESS_CLEAR 上に残る厚さの上限 =
      上面（ステム ＋ 膜） − (障害物の上面 ＋ 隙 ＋ 行程)
    を、刷る層の倍数に切り下げる。
      skin     ステムの真上の膜 = spec.KEYCAP_TOP_T（下面 = ステムの上面。ステムに支えられる）
      housing  ハウジングの上（上面 SWITCH_TOP_ABOVE_PCB 5.30）。KEYCAP_PLATE_T を超えない
      collar   静音のつばの上の輪（上面 SWITCH_COLLAR_ABOVE_PCB 5.70）
      plate    それより外 = KEYCAP_PLATE_T（膜の方が厚ければ膜）。スタビの箱（上面 5.00）の上にも来るので、箱の上限を超えたら落とす
    膜より薄い輪が 1 層を割るなら落とす（刷れない）。"""
    t = spec.KEYCAP_TOP_T
    top = spec.SWITCH_STEM_ABOVE_PCB + t
    press = travel_max(spec) + cs.KEYCAP_PRESS_CLEAR

    def room(obstacle):
        return top - (obstacle + press)

    plate = max(cs.KEYCAP_PLATE_T, t)          # 膜を KEYCAP_PLATE_T より厚くしたら（1.2 に戻すなど）外も膜の厚さ
    stab = room(CHOC_V2_STAB_SOURCES["drawing"]["box_top"])
    if plate > stab + 1e-9:
        raise ValueError(f"天板 {plate} が押し切りでスタビの箱に当たる（上限 {stab:.2f}）")
    housing = min(plate, layer_floor(room(spec.SWITCH_TOP_ABOVE_PCB), cs))
    collar = min(housing, layer_floor(room(spec.SWITCH_COLLAR_ABOVE_PCB), cs))
    if collar < cs.PRINT_LAYER - 1e-9:
        raise ValueError(f"つばの上の輪が {collar:.2f}（1 層 {cs.PRINT_LAYER} 未満）。膜を厚くする")
    return dict(skin=t, housing=housing, collar=collar, plate=plate)


def stab_grip(spec, cs=CS):
    """スタビの受け口の台の高さ（天板の下面から下へ）= 軸を掴む深さ STAB_SOCKET_GRIP。

    スタビの軸（十字）は箱の上面から stem_top − box_top（図 3.60）出ていて、その下はスライダーの胴（箱の口
    STAB_SLIDER_W の中を動く）。台の下端と胴の上面の距離は押しても変わらない（どちらも軸と一緒に動く）ので、
    掴む深さは 3.60 − KEYCAP_PRESS_CLEAR まで取れる。押し切ると台は箱の上面より下へ入るので、台の径は
    箱の口より細い（tests/test_cckb_case.py が見る）。**超えたら落とす。**"""
    d = CHOC_V2_STAB_SOURCES["drawing"]
    room = d["stem_top"] - d["box_top"] - cs.KEYCAP_PRESS_CLEAR
    if cs.STAB_SOCKET_GRIP > room + 1e-9:
        raise ValueError(f"スタビの受け口の深さ {cs.STAB_SOCKET_GRIP} が軸の出 {room:.2f} を越える")
    if cs.STAB_SOCKET_BOSS_D > cs.STAB_SLIDER_W - 2 * cs.STAB_SOCKET_CLEAR + 1e-9:
        raise ValueError(f"台 φ{cs.STAB_SOCKET_BOSS_D} が箱の口 {cs.STAB_SLIDER_W} に片側 {cs.STAB_SOCKET_CLEAR} 残らない")
    return cs.STAB_SOCKET_GRIP


def cross(x, z0, z1, size):
    """十字（長さ × 幅、2 方向）の角柱 2 本（x はキーの中心から）。"""
    ln, w = size
    return [box(x - ln / 2, -w / 2, z0, x + ln / 2, w / 2, z1), box(x - w / 2, -ln / 2, z0, x + w / 2, ln / 2, z1)]


def switch_socket(cs=CS, od=None, slot=None, length=None):
    """スイッチの十字に挿す筒（削る十字の穴は socket_holes）。"""
    od = cs.STEM_TUBE_OD if od is None else od
    length = cs.STEM_TUBE_L if length is None else length
    return cyl(0.0, 0.0, -length, 0.01, od)


def socket_holes(spec, cs=CS, slot=None, length=None, stab_xs=(), stab_slot=None):
    """削る側: スイッチの十字の穴（筒の下端からステムの上面まで）・スタビの十字の穴（台の下端から天板の中まで。
    上に STAB_SOCKET_TOP_KEEP を残す）。天板の下面の逃げ（ハウジング・つば）は cap_plate。"""
    slot = cs.STEM_CROSS_SLOT if slot is None else slot
    stab_slot = cs.STAB_CROSS_SLOT if stab_slot is None else stab_slot
    length = cs.STEM_TUBE_L if length is None else length
    out = cross(0.0, -length - 1.0, 0.0, slot)
    top = spec.KEYCAP_TOP_T - cs.STAB_SOCKET_TOP_KEEP
    for x in stab_xs:
        out += cross(x, -stab_grip(spec, cs) - 1.0, top, stab_slot)
    return out


def relief_half(inner, cs=CS, sw_cutout=None):
    """ハウジングの上の逃げの半幅（x・y）。inner = 逃げを広げてよい範囲の半幅（スカートの内側・小片なら縁）。
    逃げと inner の間の帯が KEYCAP_PLATE_MIN_W より細ければ inner まで広げる（刷れない細い段を残さない）。"""
    h = sw_cutout / 2 + cs.KEYCAP_HOUSING_MARGIN
    return tuple(i if i - h < cs.KEYCAP_PLATE_MIN_W else h for i in inner)


def cap_plate(w, d, spec, sw, cs=CS, inner=None, chamfered=True):
    """天板（局所座標・上面 = 膜の厚さ）。場所ごとの厚さは plate_levels:
    外 = plate、ハウジングの上（relief_half）= housing、つばの上の輪（KEYCAP_COLLAR_RELIEF）= collar、ステムの上 = skin。"""
    lv = plate_levels(spec, cs)
    t = lv["skin"]
    bottom = t - lv["plate"]
    slab = box(-w / 2, -d / 2, bottom, w / 2, d / 2, t)
    if chamfered:
        slab = chamfer(slab.edges().group_by(Axis.Z)[-1], cs.KEYCAP_CHAMFER)
    hx, hy = relief_half(inner or (w / 2, d / 2), cs, sw.cutout)
    r0, r1 = cs.KEYCAP_COLLAR_RELIEF
    cuts = [box(-hx, -hy, bottom - 1, hx, hy, t - lv["housing"]),
            cyl(0, 0, bottom - 1, t - lv["collar"], r1)]
    # ステムの上は膜（下面 = ステムの上面 z = 0）。ハウジングの上の厚さが膜と違っても、ここは膜にそろえる
    return fuse([slab - fuse(cuts), cyl(0, 0, 0, t, r0)]) - cyl(0, 0, -5, 0, r0)


def stab_bosses(xs, spec, cs=CS, d=None):
    """スタビの受け口の細い台（天板の下）。d で径を変えられる（小片）。"""
    d = cs.STAB_SOCKET_BOSS_D if d is None else d
    return [cyl(x, 0.0, -stab_grip(spec, cs), 0.01, d) for x in xs]


def stab_xs(w_u, sw):
    """スタビの受け口の x（キーの中心から）。スタビの無い幅は空。"""
    s = sw.stab_offset_for(w_u)
    return () if s is None else (-s, s)


def keycap(w_u, spec, sw, cs=CS):
    """1 個のキーキャップ（局所座標）。"""
    g = spec.KEYCAP_GAP
    w, d = w_u * UNIT - 2 * g, UNIT - 2 * g
    k = cs.KEYCAP_SKIRT_T
    plate = cap_plate(w, d, spec, sw, cs, inner=(w / 2 - k, d / 2 - k))
    top_of_skirt = spec.KEYCAP_TOP_T - plate_levels(spec, cs)["plate"] + 0.01
    skirt = box(-w / 2, -d / 2, -cs.KEYCAP_SKIRT_H, w / 2, d / 2, top_of_skirt) \
        - box(-w / 2 + k, -d / 2 + k, -cs.KEYCAP_SKIRT_H - 1, w / 2 - k, d / 2 - k, top_of_skirt + 1)
    xs = stab_xs(w_u, sw)
    body = fuse([plate, skirt, switch_socket(cs)] + stab_bosses(xs, spec, cs))
    return (body - fuse(socket_holes(spec, cs, stab_xs=xs))).clean()


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
