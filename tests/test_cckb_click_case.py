"""cckb-click の本番の枠・キャップ・組み立て。projects/cckb-click/click_case.py。

**生成した立体そのもの**を重ねる・動かす・切って見る（式どうしを比べない）。各検査の下に「故意に壊すと落ちる」検査を置く。
壊す検査は、枠を作り直さず（1 回 25 秒）、相手の物（部品・キャップ・電池・プラグ）を動かして同じ関数に通す。

外の事実: 部品の背と外形はデータシート（spec.py・click_case.PART_H の各行）、A1 mini の実効 168.4、
利用者が試し刷りで決めた 1 マスの形（click_parts.py。同じ関数で作っていることを断面で確かめる）。
"""

import math
import sys

import pytest
import trimesh
from build123d import Box, Compound, Cylinder, Pos, Rot, export_stl

from conftest import ROOT
from foundry.layout import UNIT

sys.path.insert(0, str(ROOT / "projects" / "cckb-click"))
import click_case as C  # noqa: E402
import click_layout as L  # noqa: E402
import click_parts as P  # noqa: E402

LAY, S = C.LAY, C.S
TOL = 1e-3          # mm3。面が触れているだけの組の丸め
pytestmark = pytest.mark.slow


def vol(a, b):
    c = a & b
    try:
        return 0.0 if c is None else float(c.volume)
    except (AttributeError, ValueError):
        return 0.0


@pytest.fixture(scope="module")
def halves():
    return C.frame_halves()


@pytest.fixture(scope="module")
def frame(halves):
    return Compound([halves["left"], halves["right"]])


_LOWER = {}


def LOWER():
    """柱と厚い壁（枠と同じに削った形）。作るのは 1 回。"""
    if not _LOWER:
        _LOWER.update(C.lower_solids())
    return _LOWER


def near(k, solids, grow=1.5):
    """キー k の穴の近くにある立体（外接矩形で絞る）。"""
    h = L.grow(LAY.hole(k), grow)
    out = []
    for name, v in solids.items():
        b = v.bounding_box()
        if b.max.X > h[0] and b.min.X < h[2] and b.max.Y > h[1] and b.min.Y < h[3]:
            out.append((name, v))
    return out


# ---------------------------------------------------------------------------
# 枠: 2 枚・1 つの塊・A1 mini・試し刷りと同じ 1 マス
# ---------------------------------------------------------------------------

def test_the_frame_is_two_solid_pieces_that_fit_the_a1_mini(halves, tmp_path):
    full = C.frame_full()
    for side, part in halves.items():
        assert len(part.solids()) == 1 and part.is_valid, side
        b = part.bounding_box().size
        assert max(b.X, b.Y) <= S.PRINT_MAX and b.Z == pytest.approx(S.FRAME_UNDER + S.FRAME_T), (side, b)
        stl = tmp_path / f"{side}.stl"
        export_stl(C.frame_print(part), str(stl))
        m = trimesh.load(str(stl))
        assert m.is_watertight and m.bounds[0][2] == pytest.approx(0.0, abs=1e-6), side
    # 2 枚の和は元の枠から、継ぎ目の隙（幅 FRAME_SEAM_GAP の帯）を引いた物。継ぎ目のリブは左が持つ
    lost = full.volume - halves["left"].volume - halves["right"].volume
    assert 0.0 < lost < S.FRAME_SEAM_GAP * 110 * 5.0
    f = LAY.frame
    assert halves["left"].bounding_box().max.X == pytest.approx(max(S.FRAME_SPLIT) + 1.0, abs=0.01)
    # 右の枠の左の端: 段の境目のリブは左右どちらか広い方の段に合わせて左が持つので、右にはその内側の穴の縁の肉が無い。
    # 残るいちばん左は、手前の壁（最下段の継ぎ目 4.7625 ＋ リブの半分 ＋ 隙）
    assert halves["right"].bounding_box().min.X == pytest.approx(S.FRAME_SPLIT[-1] + 1.0 + S.FRAME_SEAM_GAP, abs=0.01)
    assert (full.bounding_box().size.X, full.bounding_box().size.Y) == pytest.approx((f[2] - f[0], f[3] - f[1]))
    assert (f[2] - f[0], f[3] - f[1]) == pytest.approx((291.75, 101.25))


def test_no_post_is_cut_by_the_seam():
    reg = C.left_region(LAY)
    for p in LAY.all_posts():
        r = L.rect(*p)
        c = C._rect2d(r) & reg
        a = 0.0 if c is None else sum(f.area for f in c.faces())
        assert a < 1e-6 or a > (r[2] - r[0]) * (r[3] - r[1]) - 1e-6, p
    assert len(LAY.all_posts()) == len(LAY.posts()) + 5


def scan(frame, a, b, n=240):
    """a から b までの線の上で、枠の中にある区間 [(t0, t1)]（t は a からの距離）。"""
    length = math.dist(a, b)
    out, start = [], None
    for i in range(n + 1):
        t = i / n
        p = tuple(a[j] + (b[j] - a[j]) * t for j in range(3))
        inside = frame.is_inside(p)
        if inside and start is None:
            start = t * length
        if not inside and start is not None:
            out.append((start, t * length))
            start = None
    if start is not None:
        out.append((start, length))
    return out


def test_every_key_cell_is_the_cell_the_user_tested(halves):
    """穴 17.05 角・リブ 2.0・くぼみ（深さ 1.0・穴の縁から 0.6）・柱の高さ 3.0 を、立体の中の点で測る。
    試し刷りの枠（click_parts.frame）を同じ線で測った値と同じ。"""
    k = next(k for k in LAY.keys if k.label == "G")
    frame = halves[LAY.side_of(k)]                  # 1 つの立体で測る（2 枚をまとめた物は、中か外かの判定が遅い）
    c = P.Cell(k.x, k.y, S.HOLE_B)
    coupon = P.frame([c, P.Cell(k.x + UNIT, k.y, S.HOLE_B)], S, wall=False)
    lines = {
        "穴の幅（z 4.5）": ((k.x - 12, k.y, 4.5), (k.x + 12, k.y, 4.5)),
        "くぼみ（z 3.5・穴の角の近く）": ((k.x + 6, k.y + 7.0, 3.5), (k.x + 13, k.y + 7.0, 3.5)),
        "くぼみの上（z 4.5）": ((k.x + 6, k.y + 7.0, 4.5), (k.x + 13, k.y + 7.0, 4.5)),
        "柱（右のリブの下・縦）": ((k.x + UNIT / 2, k.y, -0.5), (k.x + UNIT / 2, k.y, 5.5)),
    }
    def clip(segs, lo, hi):
        return [(round(max(u, lo), 1), round(min(v, hi), 1)) for u, v in segs if v > lo and u < hi]

    for name, (a, b) in lines.items():
        # 穴の幅の線は、左の縁（試し刷りは外形の縁・本番は隣のキー）を外して比べる: 穴の左の縁の少し手前から、右のリブの先まで
        lo, hi = (3.2, 22.7) if name.startswith("穴") else (0.0, 99.0)
        ours, theirs = clip(scan(frame, a, b), lo, hi), clip(scan(coupon, a, b), lo, hi)
        assert ours == theirs and ours, (name, ours, theirs)
    hole = scan(frame, *lines["穴の幅（z 4.5）"])
    gap = [b[0] - a[1] for a, b in zip(hole, hole[1:])]
    assert max(gap) == pytest.approx(17.05, abs=0.07)
    assert scan(frame, *lines["柱（右のリブの下・縦）"]) == [pytest.approx((0.5, 5.5), abs=0.03)]      # 走査の刻みは 0.025


def up_faces(part, below):
    """上を向いた平らな面で、高さが below より低い物 [(高さ, 面積)]。上面をベッドに刷るので、これが宙に浮く面になる。"""
    out = []
    for f in part.faces():
        try:
            n = f.normal_at()
        except Exception:
            continue
        if n.Z > 0.999 and f.center().Z < below - 1e-6:
            out.append((round(f.center().Z, 3), round(f.area, 2)))
    return out


def test_the_frame_prints_top_down_without_support(halves):
    """上面をベッドに刷る → 使う向きで「上を向いた面」は上面だけのはず（ほかは宙に浮く）。許すのは 2 種類だけ:
      - 入の印の底（φ1.2 の点。深さ 0.4）
      - 継ぎ目の溝の真下に来た柱の頭（幅 2.0 の溝をまたぐ、奥行き 0.3 以下の小さな橋。試し刷りの枠にもあった形:
        決定記録 2026-10-03-print-recipe §4）。**数と大きさを固定する**（増えたら落ちる）"""
    top = S.FRAME_UNDER + S.FRAME_T
    faces = [f for side in C.SIDES for f in up_faces(halves[side], top)]
    mark = [f for f in faces if f[0] == pytest.approx(top - S.ON_MARK[1])]
    bridges = [f for f in faces if f[0] == pytest.approx(S.FRAME_UNDER)]
    assert mark == [(top - S.ON_MARK[1], pytest.approx(math.pi * (S.ON_MARK[0] / 2) ** 2, abs=0.02))], mark
    assert len(mark) + len(bridges) == len(faces) and len(bridges) == 26, faces
    # 柱は溝に 0.3 掛かる（0.34 mm2）。奥の壁のねじの所の厚い壁は、溝の奥行き 0.5 いっぱいに掛かる（1.0 mm2）
    assert max(a for _, a in bridges) <= S.SEAM_NOTCH[0] * S.SEAM_NOTCH[1] + 1e-6
    # 検査器が生きている: 足（上を向いた円盤）を付けた立体では見つかる
    foot = C.feet()[0][1]
    assert any(z == S.HOLDDOWN_H for z, _ in up_faces(foot, top))


def test_the_thin_places_are_at_least_what_the_nozzle_can_print():
    """部品の逃げで薄くなる所（spec と layout から）。0.4 ノズルの壁: 左は 1.2 以上（外周 3 本）。屋根は 0.6 以上。
    **XIAO の手前の壁は 1.135**（1 回目の監査 E 軽微 2 で、逃げをパッドの外接 ＋ 0.3 から ＋ PART_CLEAR 0.4 に広げた。前は 1.235）。
    下限を 1.1 にした: 線幅 0.42 の外周 2 本（0.84）＋ 隙間埋め。高さは基板の上 3.7 までで、その上は壁の全厚 3.0 が続く"""
    f, xb, xp = LAY.frame, LAY.xiao(), LAY.xiao_pads()
    left_wall = (xb[0] - S.PART_CLEAR) - f[0]
    front_wall = (xp[1] - S.PART_CLEAR) - f[1]
    roofs = {"XIAO": 5.0 - S.XIAO_ROOF_UNDER, "電池クリップ": 5.0 - S.CLIP_ROOF_UNDER}
    assert left_wall >= 1.2 and front_wall >= 1.1, (left_wall, front_wall)
    assert front_wall == pytest.approx(1.135)
    assert all(v >= 0.6 for v in roofs.values()), roofs
    z = LAY.z()
    assert S.XIAO_ROOF_UNDER - z["xiao_body_top"] >= S.PART_HEADROOM and S.CLIP_ROOF_UNDER - z["clip_top"] >= S.PART_HEADROOM - 1e-9
    assert z["usb_top"] < 5.0                                   # USB のシェルは切り欠きの中で、枠の上面より低い


# ---------------------------------------------------------------------------
# ねじ
# ---------------------------------------------------------------------------

def local(frame, x, y, half=5.0):
    """ねじのまわりだけ切り出す（枠まるごとに is_inside を当てると 1 点 0.1 秒かかる）。"""
    return frame & (Pos(x, y, 2.0) * Box(2 * half, 2 * half, 8.0))


def screw_wall_problems(halves, ring=0.45, step=45):
    """外周のねじの下穴の周り（下穴の縁から ring）が、基板の上 0.3〜2.5 で枠の中にある。下穴の中は空いている。"""
    out = []
    d, depth = LAY.pilot()
    for ref, (x, y), kind in LAY.wall_screws():                # 外周 20 ＋ 予備 2
        frame = local(halves["left" if x < LAY.seam_x(y) else "right"], x, y)
        for z in (0.3, 1.4, 2.5):
            if frame.is_inside((x, y, z)):
                out.append(f"{ref}: 下穴が空いていない（z {z}）")
            for a in range(0, 360, step):
                p = (x + (d / 2 + ring) * math.cos(math.radians(a)), y + (d / 2 + ring) * math.sin(math.radians(a)), z)
                if not frame.is_inside(p):
                    out.append(f"{ref}: 下穴の周り {a}° z {z} に肉が無い")
        if not frame.is_inside((x, y, depth + 0.3)):
            out.append(f"{ref}: 下穴がくぼみの層（{depth} より上）まで抜けている")
    return out


def test_every_perimeter_screw_has_plastic_all_around_its_pilot_hole(halves):
    bad = screw_wall_problems(halves)
    assert bad == [], bad
    assert screw_wall_problems(halves, ring=1.3, step=90)       # 検査器が生きている: 1.3 の肉は無い（内側は 0.8）
    assert len(LAY.wall_screws()) == 22
    # 下穴の径は 22 本とも φ1.6（予備の 2 本も）: 穴の縁のすぐ内は空・すぐ外は肉（外面の向きへ）
    assert LAY.pilot()[0] == 1.6
    f = LAY.frame
    for ref, (x, y), _ in LAY.wall_screws():
        piece = local(halves["left" if x < LAY.seam_x(y) else "right"], x, y)
        d = {(-1, 0): x - f[0], (1, 0): f[2] - x, (0, -1): y - f[1], (0, 1): f[3] - y}
        ux, uy = min(d, key=d.get)                              # 外面の向き
        assert not piece.is_inside((x + ux * 0.77, y + uy * 0.77, 1.4)) and piece.is_inside((x + ux * 0.83, y + uy * 0.83, 1.4)), ref


def wall_flesh(frame, x, y, zs=(0.3, 1.4, 2.5), step=10):
    """下穴の縁から外へ、枠の中にいる間の距離のいちばん短い物（全方位・基板の上 0.3〜2.5）。(肉, 角度)。"""
    d, _ = LAY.pilot()
    loc = local(frame, x, y)
    best = (9.0, 0)
    for z in zs:
        for a in range(0, 360, step):
            r = d / 2 + 0.01
            while r < 4.0 and loc.is_inside((x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a)), z)):
                r += 0.02
            best = min(best, (round(r - d / 2, 2), a))
    return best


def test_the_plastic_around_each_pilot_hole_is_as_thick_as_the_board_allows(halves):
    """E 重要 2: 監査の時（下穴 φ1.8）は、下穴から斜め内向きの肉が 0.49（壁を厚くする幅 ± 1.2 の角）・真内向きが 0.6 だった。
    基板の穴を 0.1 外へ寄せ、壁を厚くする幅を ± 2.0 にした。**下穴を φ1.6 にしたので、どこも 0.1 増えた**: 奥と手前の壁と 1u の脇は 0.8 以上・
    幅の広いキーの脇の 3 本だけ 0.59（φ1.8 のときの 0.49）。ねじの外径 2.0 の外に残る壁（0.6／0.39）は、下穴の径では変わらない。"""
    thin = {}
    for ref, (x, y), kind in LAY.wall_screws():
        m, a = wall_flesh(halves["left" if x < LAY.seam_x(y) else "right"], x, y)
        if LAY.boss_half((x, y)) == S.SCREW_BOSS_HALF:
            assert m >= 0.79, (ref, m, a)
        else:
            thin[ref] = m
    assert sorted(thin) == ["H16", "H17", "H18"] and all(0.57 <= v <= 0.62 for v in thin.values()), thin


def pad_relief_problems(halves, clear, z=0.2):
    """電源スイッチと XIAO のパッドの外接から clear 外まで、基板のすぐ上（z 0.2）に枠が無い。"""
    out = []
    for side, name, box in (("right", "電源スイッチ", LAY.psw_pads()), ("left", "XIAO", LAY.xiao_pads())):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        loc = halves[side] & (Pos(cx, cy, 1.0) * Box(box[2] - box[0] + 6, box[3] - box[1] + 6, 3.0))
        g = L.grow(box, clear)
        n = 12
        ring = [(g[0] + (g[2] - g[0]) * i / n, y) for i in range(n + 1) for y in (g[1], g[3])]
        ring += [(x, g[1] + (g[3] - g[1]) * i / n) for i in range(n + 1) for x in (g[0], g[2])]
        p = LAY.pcb
        hit = [q for q in ring if p[0] < q[0] < p[2] and p[1] < q[1] < p[3] and loc.is_inside((q[0], q[1], z))]
        if hit:
            out.append(f"{name}: パッドの外接 ＋ {clear} に枠がある {hit[:2]}")
    return out


def test_the_frame_keeps_clear_of_the_solder_pads_of_the_corner_parts(halves):
    """E 軽微 1・2: 枠の逃げ = パッドの外接 ＋ PART_CLEAR 0.4（はんだの裾・刷った穴の縮み）。前は 0.08〜0.28 だった。"""
    assert pad_relief_problems(halves, S.PART_CLEAR - 0.05) == []
    # 検査器が生きている: XIAO は 0.6 外に枠がある。電源スイッチのまわりは基板の面まで空いている（角の中・つまみの切り欠き）ので、
    # 厚い屋根の高さ（基板の上 2.0）で見ると枠がある
    assert [b[:4] for b in pad_relief_problems(halves, S.PART_CLEAR + 0.2)] == ["XIAO"]
    assert any("電源スイッチ" in b for b in pad_relief_problems(halves, S.PART_CLEAR - 0.05, z=2.0))


# ---------------------------------------------------------------------------
# ねじの試し刷り（coupon_screw）: 本番の枠から切り出した物か・当て板が基板と同じか
# ---------------------------------------------------------------------------

def test_the_screw_coupon_is_cut_from_the_real_frame_with_one_thickened_wall():
    """切り出す元は、左右に分ける前の枠（奥の壁の切れ端は継ぎ目 x 9.525 をまたぐ。試し刷りには継ぎ目の隙 0.1 を入れない）。"""
    frame = C.frame_full()
    sc = C.screw_coupon()
    boxes = C.screw_coupon_boxes()
    assert set(sc) == {"frame_back", "frame_side", "base_back", "base_side"}
    top = S.FRAME_UNDER + S.FRAME_T
    for name, (box, screws, thick) in boxes.items():
        piece, real = sc[f"frame_{name}"], frame & C._box(box, -1.0, top + 1.0)
        extra = (piece - real).volume
        missing = (real - piece).volume
        if thick is None:
            assert extra < TOL and missing < TOL, (name, extra, missing)
        else:
            # 足したのは厚くした壁（幅 4.0 × 0.5 × 高さ 3.0）だけ・削ったのは印（その側の端の外の角・三角柱）だけ
            assert extra == pytest.approx(4.0 * S.COUPON_SCREW_THICK * S.FRAME_UNDER, abs=0.05), extra
            assert missing == pytest.approx(S.COUPON_SCREW_MARK ** 2 / 2 * top, abs=0.2), missing
            assert thick[0] == max(x for x, _ in screws)                  # 印のある端 = 厚くしたねじの側
        base = sc[f"base_{name}"].bounding_box()
        assert (base.min.Z, base.max.Z) == pytest.approx((-S.PCB_T, 0.0))            # 当て板 = 基板の厚さ 1.6
        d, depth = LAY.pilot()
        for x, y in screws:
            assert (x, y) in [c for _, c, k in LAY.screws() if k == "perimeter"]       # 本番のねじの位置
            assert not piece.is_inside((x, y, 1.0)) and piece.is_inside((x, y, depth + 0.3))         # 下穴は本番の深さ
            assert not sc[f"base_{name}"].is_inside((x, y, -0.8)) and sc[f"base_{name}"].is_inside((x + S.SCREW_HOLE_D / 2 + 0.2, y, -0.8))
            m, _ = wall_flesh(piece, x, y)
            want = 1.3 if (x, y) == thick else 0.81 if name == "back" else 0.59
            assert m == pytest.approx(want, abs=0.03), (name, x, m)
        # 当て板の縁は基板の縁（穴の縁から 1.0）
        edge = min(base.max.Y - screws[0][1], screws[0][0] - base.min.X)
        assert edge - S.SCREW_HOLE_D / 2 == pytest.approx(1.0, abs=1e-6)
    plate = C.screw_coupon_plate()
    size = plate.bounding_box().size
    assert len(plate.solids()) == 4 and max(size.X, size.Y) <= 80 and plate.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    # ねじ M2×4 は当て板 1.6 を抜けて 2.4 掛かる（本番と同じ）
    assert S.SCREW_L - S.PCB_T == pytest.approx(LAY.z()["screw_grip"])


def test_the_screws_grip_the_wall_and_stay_out_of_the_pockets():
    z = LAY.z()
    assert z["screw_grip"] >= 2.0 and z["screw_tip"] <= S.SCREW_PILOT_DEPTH - 0.2 and S.SCREW_PILOT_DEPTH < S.FRAME_UNDER
    assert S.HOLDDOWN_FEET is False and len(C.screw_solids()) == 20


# ---------------------------------------------------------------------------
# 干渉: 置いたとき
# ---------------------------------------------------------------------------

def static_problems(halves, parts=None, switches=None, caps=None):
    parts = C.board_parts() if parts is None else parts
    switches = C.switch_solids(LAY, S.SW_STEM_TOP + S.SW_STEM_TOP_TOL) if switches is None else switches
    caps = {k.i: C.cap_pose(k, "latched") for k in LAY.keys} if caps is None else caps
    out = []
    for side in C.SIDES:
        for name, group in (("基板の上の部品", parts), ("スイッチ", switches), ("キャップ", caps)):
            if not group:
                continue
            v = vol(halves[side], Compound(list(group.values())))
            if v > TOL:
                bad = [n for n, s in group.items() if vol(halves[side], s) > TOL]
                out.append(f"{side} の枠と{name}: {v:.3f} mm3 {bad[:6]}")
    if caps and switches:
        v = vol(Compound(list(caps.values())), Compound(list(switches.values())))
        if v > TOL:
            out.append(f"キャップとスイッチ（ステムがいちばん高い）: {v:.3f} mm3")
    if caps and parts:
        v = vol(Compound(list(caps.values())), Compound(list(parts.values())))
        if v > TOL:
            out.append(f"キャップと部品: {v:.3f} mm3")
    return out


def test_nothing_interferes_at_rest(halves):
    assert static_problems(halves) == []
    assert len(C.board_parts()) == 62 + 9 + 4 and len(C.switch_solids()) == 62
    # 載せないコンデンサのランドは、載せてよいいちばん大きな部品（1206 の最大の外形・背は spec.CAP_LAND_H）で見ている
    for ref, h in S.CAP_LAND_H.items():
        b = C.board_parts()[ref].bounding_box().size
        assert (b.X, b.Y, b.Z) == pytest.approx((1.8, 3.4, h))


def _tall_part_under_a_post(p, s, c):
    d = C.diode_at(LAY.keys[19])
    p["D20"] = Pos(d[0], d[1] - 2.6, 0) * Box(2.8, 1.8, 3.2, align=C.CEN_MIN)       # 段の境目の柱の下へ動いた背の高い部品


@pytest.mark.parametrize("break_it, word", [
    (lambda p, s, c: p.update(U_MCU=Pos(0, 0, 0.5) * p["U_MCU"]), "部品"),                    # XIAO が 0.5 高い → 屋根に当たる
    (lambda p, s, c: p.update(BT1=Pos(0, 3.0, 0) * p["BT1"]), "部品"),                        # クリップが 3 奥 → 逃げの壁・柱
    (lambda p, s, c: p.update(SW_PWR=Pos(0, 0, 0.5) * p["SW_PWR"]), "部品"),                  # 電源スイッチが 0.5 高い
    (_tall_part_under_a_post, "部品"),
    (lambda p, s, c: s.update(SW1=P.standin(P.Cell(LAY.keys[0].x, LAY.keys[0].y, S.HOLE_B, standin=3.8), S)), "ステム"),
    (lambda p, s, c: c.update({1: Pos(0.35, 0, 0) * c[1]}), "キャップ"),                     # キャップが横へ 0.35（隙 0.2 を越える）
])
def test_the_rest_check_notices_a_break(halves, break_it, word):
    parts, sws = C.board_parts(), C.switch_solids(LAY, S.SW_STEM_TOP + S.SW_STEM_TOP_TOL)
    caps = {1: C.cap_pose(LAY.keys[0], "latched")}
    before = {**parts, **{f"s{k}": v for k, v in sws.items()}, **{f"c{k}": v for k, v in caps.items()}}
    break_it(parts, sws, caps)
    # 壊した物だけを同じ関数に通す（全部を重ね直すと 1 通り 80 秒かかる）
    after = {**parts, **{f"s{k}": v for k, v in sws.items()}, **{f"c{k}": v for k, v in caps.items()}}
    changed = {k for k, v in after.items() if before.get(k) is not v}
    assert len(changed) == 1
    pick = lambda d, pre: {k: v for k, v in d.items() if pre + str(k) in changed}      # noqa: E731
    got = static_problems(halves, pick(parts, ""), {"SW1": sws["SW1"]}, {1: caps[1]} if "c1" in changed or "sSW1" in changed else {})
    assert any(word in b for b in got), got


# ---------------------------------------------------------------------------
# 干渉: 押し切り・縁を押し切った傾き（公差の端）
# ---------------------------------------------------------------------------

def press_problems(keys=None, parts=None, lower=None, feet=None, descent=None):
    """各キーを、まっすぐ押し切り・4 つの縁を押し切った傾きで、基板の上の物（自分の真ん中のスイッチは除く）・
    柱・厚い壁・（足）と重ねる。"""
    parts = dict(C.board_parts()) if parts is None else parts
    sws = C.switch_solids(LAY, S.SW_BODY_H + 0.1)             # 押されていない隣のスイッチは本体だけ見れば足りる
    lower = LOWER() if lower is None else lower
    feet = {} if feet is None else feet
    out = []
    for k in (LAY.keys if keys is None else keys):
        things = near(k, parts) + [(n, v) for n, v in near(k, sws) if n != f"SW{k.i}"] + near(k, lower) + near(k, feet)
        if not things:
            out.append(f"SW{k.i}: 近くに何も無い（絞り込みが空）")
            continue
        group = Compound([v for _, v in things])
        for mode in C.POSES:
            cap = C.cap_pose(k, mode, descent=descent)
            if vol(cap, group) <= TOL:              # まとめて 1 回。当たったときだけ、相手を 1 個ずつ探す
                continue
            for name, v in things:
                x = vol(cap, v)
                if x > TOL:
                    out.append(f"{k.label}（SW{k.i}）{mode}: {name} に {x:.3f} mm3")
    return out


def test_no_cap_hits_anything_when_fully_pressed_or_tilted_at_the_tolerance_limit():
    assert press_problems() == []


def test_the_lowest_point_of_a_tilted_cap_is_above_every_part():
    """縁を押し切ったキャップの下面のいちばん低い所（立体の外接）と、部品の背。"""
    low = {}
    for k in LAY.keys:
        low[k.w] = min(low.get(k.w, 9.0), min(C.cap_pose(k, m).bounding_box().min.Z for m in ("+x", "-x", "+y", "-y")))
    assert min(low.values()) > max(C.PART_H.values()) + 0.2, low
    assert min(low.values()) == pytest.approx(1.6, abs=0.1)
    assert C.descent_max() == pytest.approx(1.0)


def test_the_bulk_capacitor_land_under_the_z_key_takes_a_low_part_but_not_a_tall_one():
    """C_3V3 は Z のキーのキャップの下。背 1.45（0805 の 22〜47 µF の最大）までは、縁を押し切ったキャップに当たらない。
    背 1.6 ± 0.2 の 1206（最大 1.8）は当たる → 載せてよい背を spec.CAP_LAND_H と手順書に書いてある。"""
    z = next(k for k in LAY.keys if k.label == "Z")
    parts = dict(C.board_parts())
    assert press_problems(keys=[z], parts=parts) == []
    b = parts["C_3V3"].bounding_box()
    assert b.max.Z == pytest.approx(1.45) and LAY.hole(z)[0] < b.min.X and b.max.X < z.x - S.SW_BODY / 2
    parts["C_3V3"] = Pos((b.min.X + b.max.X) / 2, (b.min.Y + b.max.Y) / 2, 0) * Box(b.size.X, b.size.Y, 1.9, align=C.CEN_MIN)
    assert any("C_3V3" in x for x in press_problems(keys=[z], parts=parts))
    # C_BAT は右の角の屋根の下（枠の下面 3.0）: 背 2.8 まで。置いたときの干渉は test_nothing_interferes_at_rest が見る
    assert S.CAP_LAND_H["C_BAT"] <= S.FRAME_UNDER - 0.2


@pytest.mark.parametrize("kw, word", [
    (dict(parts={"D34": Pos(*C.diode_at(next(k for k in LAY.keys if k.label == "G")), 0) * Box(2.8, 1.8, 2.3, align=C.CEN_MIN)}), "D34"),
    (dict(lower={"post_bad": C._box((-24.0, -4.0, -22.4, 4.0), 0.0, 3.0)}), "post_bad"),
    (dict(descent=1.6), "D"),
])
def test_the_press_check_notices_a_tall_part_a_post_under_the_hole_and_a_deeper_press(kw, word):
    k = next(k for k in LAY.keys if k.label == "G")
    assert any(word in b for b in press_problems(keys=[k], **kw)), press_problems(keys=[k], **kw)


def test_the_optional_holddown_foot_stays_under_the_tilted_cap_but_a_taller_one_would_not():
    """中の押さえの足（既定では付けない）: 高さ 1.4 なら、縁を押し切ったキャップの下。2.0 なら当たる。"""
    feet = {f"foot{i}": v for i, (c, v) in enumerate(C.feet())}
    keys = [next(k for k in LAY.keys if LAY.hole(k)[0] < c[0] < LAY.hole(k)[2] and abs(k.y - c[1]) < 1e-6) for c, _ in C.feet()]
    assert len(keys) == 8 and press_problems(keys=keys, feet=feet) == []
    tall = {n: Pos(c[0], c[1], 0) * Cylinder(S.HOLDDOWN_D / 2, 2.0, align=C.CEN_MIN) for n, (c, _) in zip(feet, C.feet())}
    assert any("foot" in b for b in press_problems(keys=keys, feet=tall))


# ---------------------------------------------------------------------------
# 組めるか・外せるか
# ---------------------------------------------------------------------------

def cap_columns():
    """各キャップが枠の下から入る道（キャップの平面を、掛かった位置から下へ伸ばした柱）。つばは掛かる面まで。"""
    lv = P.levels(S)
    out = {}
    for k in LAY.keys:
        c = P.Cell(0.0, 0.0, S.HOLE_B, w_u=k.w)
        from build123d import extrude
        body = Pos(0, 0, -6.0) * extrude(P.body_plan(c, S), lv["cap_top"] + 6.0)
        tabs = Pos(0, 0, -6.0) * extrude(P.tab_plan(c, S), lv["latch"] + 6.0)
        out[k.i] = Pos(k.x, k.y, 0) * (body + tabs)
    return out


def test_all_62_caps_drop_into_the_inverted_frame(halves):
    """枠を裏返して置き、キャップを上面を下にして落とす = 使う向きで、キャップが下からまっすぐ入る。道の上に枠の物が無い。"""
    cols = cap_columns()
    for side in C.SIDES:
        v = vol(halves[side], Compound(list(cols.values())))
        assert v < TOL, (side, v, [i for i, c in cols.items() if vol(halves[side], c) > TOL][:8])
    # 壊すと落ちる: 厚い壁をつばの来る角まで伸ばすと、つばの道を塞ぐ
    k = LAY.keys[0]
    hole = LAY.hole(k)
    block = C._box((hole[0] + 0.5, hole[3] - 0.01, hole[0] + 4.0, hole[3] + 1.0), 0.0, 3.0)
    assert vol(block, cols[k.i]) > 0.1


def test_the_board_goes_onto_the_frame_straight_and_nothing_hangs_below_it():
    """基板を枠にかぶせる = 部品が枠の空間へ下からまっすぐ入る。部品の立体が基板の面（z 0）から立つ柱なら、置いたときの干渉が
    そのまま道の検査になる（test_nothing_interferes_at_rest）。柱でない物（宙に浮いた形）が無いことを見る。"""
    for name, v in {**C.board_parts(), **C.switch_solids()}.items():
        b = v.bounding_box()
        assert b.min.Z <= (0.2 if name == "SW_PWR_knob" else 1e-6), name
    # 基板の下へ出るのはねじの頭だけ。頭はシートの厚さの中（公差の端で 0.1 出る）
    z = LAY.z()
    lowest = min(v.bounding_box().min.Z for v in C.screw_solids().values())
    assert lowest == pytest.approx(-S.PCB_T - S.SCREW_HEAD_H) and lowest >= z["desk"] - 0.1 - 1e-9
    assert vol(C.sheet_solid(), Compound(list(C.screw_solids().values()))) < TOL


def cell_path(dy0=0.0, dy1=-22.0, dx=0.0):
    """電池を口から抜く道（中心を dy0 から dy1 まで動かした跡）。"""
    (x, y), r = LAY.cell()
    return Compound([Pos(x + dx, y + dy0, 0) * Cylinder(r, S.CELL_T, align=C.CEN_MIN),
                     Pos(x + dx, y + dy1, 0) * Cylinder(r, S.CELL_T, align=C.CEN_MIN),
                     C._box((x + dx - r, y + dy1, x + dx + r, y + dy0), 0.0, S.CELL_T)])


_FREE = {}


def battery_problems(halves, path=None, n_free_min=15.0):
    out = []
    path = cell_path() if path is None else path
    v = vol(halves["right"], path)
    if v > TOL:
        out.append(f"電池の抜き差しの道が枠に当たる {v:.2f} mm3")
    others = {n: s for n, s in {**C.board_parts(), **C.switch_solids()}.items() if n != "BT1"}
    v = vol(Compound(list(others.values())), path)
    if v > TOL:
        out.append(f"電池の道がほかの部品に当たる {v:.2f} mm3")
    # 指で触れる所: 電池の上面のうち、真上に枠が無い面積（0.5 おきの点で数える）
    (x, y), r = LAY.cell()
    if "area" not in _FREE:                       # 枠は同じなので 1 回だけ数える
        free, step = 0, 0.5
        n = int(r / step) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                px, py = x + i * step, y + j * step
                if math.hypot(px - x, py - y) > r:
                    continue
                if not any(halves["right"].is_inside((px, py, zz)) for zz in (3.4, 3.9, 4.4, 4.9)):
                    free += 1
        _FREE["area"] = free * step * step
    area = _FREE["area"]
    if area < n_free_min:
        out.append(f"電池の上面で指の届く所が {area:.1f} mm2（{n_free_min} 以上）")
    return out, area


def test_the_battery_slides_out_through_the_front_wall_without_taking_anything_apart(halves):
    """蓋を外した状態（電池を替えるとき）。口の手前の角に歯があっても、道と、指の届く面積は前と同じ。"""
    bad, area = battery_problems(halves)
    assert bad == [] and area == pytest.approx(23.0, abs=4.0), (bad, area)
    # クリップの口は手前・電池の縁は枠の外面から CELL_RECESS 内側・クリップの口の縁（真ん中のえぐり）より手前が指の切り欠きに出る
    (x, y), r = LAY.cell()
    # 電池は止めに当たる所（クリップの原点より 0.51 奥。1 回目の監査 E 重要 1）
    assert y - r - LAY.frame[1] == pytest.approx(LAY.cell_recess()) == pytest.approx(1.71)
    assert LAY.clip_body()[1] > LAY.frame[1] + LAY.cell_recess() + 1.0
    assert S.FINGER_NOTCH_DEPTH - LAY.cell_recess() >= 2.7              # 口から電池の上面が 2.79 見える
    assert S.CELL_T < S.CLIP_H - 0.25                            # 電池はクリップの板（厚さ 0.25）の下に入る


def test_the_battery_check_notices_a_blocked_slot_and_a_covered_cell(halves):
    assert any("枠" in b for b in battery_problems(halves, cell_path(dx=1.0))[0])                  # 口から 1.0 ずれた道
    assert any("枠" in b for b in battery_problems(halves, cell_path(dy0=3.0))[0])                 # 奥へ 3 入れすぎ
    assert any("指" in b for b in battery_problems(halves, n_free_min=40.0)[0])


def test_the_usb_plug_goes_in_and_its_body_stays_outside(halves):
    shell, body = C.usb_plug()
    parts = C.board_parts()
    assert vol(halves["left"], shell) < TOL and vol(halves["left"], body) < TOL
    assert vol(C.pcb_solid(), body) < TOL and vol(C.pcb_solid(), shell) < TOL
    # プラグのシェルは XIAO の口（USB のシェルの中）へ入る
    assert vol(parts["U_MCU"], shell) > 10.0
    # 樹脂は枠の外面より外。机（シートの下面）より上
    assert body.bounding_box().max.X <= LAY.frame[0] - 0.5 and body.bounding_box().min.Z > LAY.z()["desk"] + 0.5
    # 壊すと落ちる: 口を USB_RECESS より 1.5 引っ込めた XIAO では、プラグの樹脂が枠に当たる
    assert vol(halves["left"], Pos(1.5, 0, 0) * body) > 1.0


def corner_piece(halves):
    """右の枠の、右手前の角だけ（まるごとに当てると遅い）。"""
    if "corner" not in _FREE:
        f = LAY.frame
        _FREE["corner"] = halves["right"] & C._box((100.0, f[1] - 1.0, f[2] + 1.0, -26.0), -1.0, 6.0)
    return _FREE["corner"]


def knob_problems(frame, shift=(0.0, 0.0, 0.0), block=None):
    """電源スイッチのつまみ（利用者の決定 2026-10-04: 外へ出さない・試し刷り v2 の (ii) の位置）。入・切の両方の位置で、行程の公差の端まで:
      - つまみが枠に当たらない・先が基板の縁の PSW_TIP_INSIDE（0.30）以上内側・枠の外面の 0.60 以上内側（**外へ出る物が無い**）
      - 爪の入る場所（click_case.nail_envelope: つまみの脇 3.0 幅・つまみの先から 1.0 掛かる所から外へ・上は枠の上まで）に、
        枠も、基板の上のほかの物も無い = **上からも横からも爪が届く**
    shift はつまみと包絡をずらす量（壊す検査）。block は枠に足す立体（切り欠きを狭めた枠の代わり）。"""
    out = []
    frame = frame if block is None else Compound([frame, block])
    others = Compound([v for n, v in C.board_parts().items() if not n.startswith("SW_PWR_knob")] + [C.pcb_solid()])
    for pos, name in ((1, "入"), (-1, "切")):
        for dy in (0.0, pos * S.PSW_TRAVEL_TOL / 2):
            k = Pos(*shift) * C.knob_solid(pos, dy=dy)
            if vol(frame, k) > TOL:
                out.append(f"つまみ（{name}・行程 {dy:+.1f}）が枠に当たる {vol(frame, k):.3f} mm3")
            tip = k.bounding_box().max.X
            if tip > LAY.pcb[2] - S.PSW_TIP_INSIDE + 1e-6 or tip > LAY.frame[2] - S.PSW_TIP_INSIDE - S.PCB_INSET_X + 1e-6:
                out.append(f"つまみ（{name}）の先 {tip:.3f} が、基板の縁 {LAY.pcb[2]:.3f} の {S.PSW_TIP_INSIDE} 内側・枠の外面 {LAY.frame[2]:.3f} の 0.60 内側に無い")
        env = Pos(*shift) * C.nail_envelope(pos)
        if vol(frame, env) > TOL:
            out.append(f"爪の入る場所（{name}の位置から押す）に枠がある {vol(frame, env):.2f} mm3")
        if vol(others, env) > TOL:
            out.append(f"爪の入る場所（{name}）に基板の上の物がある {vol(others, env):.2f} mm3")
    return out


def test_the_power_knob_stays_inside_the_frame_and_a_fingernail_reaches_it_from_the_top_and_the_side(halves):
    frame = corner_piece(halves)
    assert knob_problems(frame) == []
    # 利用者が試し刷り v2 の (ii) で選んだ位置: つまみの先は、入でも切でも基板の縁の 0.30 内側・枠の外面の 0.60 内側。本体は基板の縁から 1.75。
    # 行程 1.6 ± 0.2・力は最大 250 gf（承認書）
    for pos in (1, -1):
        b = C.knob_solid(pos).bounding_box()
        assert (LAY.pcb[2] - b.max.X, LAY.frame[2] - b.max.X) == pytest.approx((0.30, 0.60))
        assert LAY.pcb[2] - b.min.X == pytest.approx(S.PSW_BODY_TO_EDGE) and S.PSW_BODY_TO_EDGE == 1.75
    # 作った枠の立体でも、枠の外面より外に出る物は無い（つまみ・スイッチの本体・基板）
    outer = max(v.bounding_box().max.X for v in [C.knob_solid(1), C.knob_solid(-1), C.board_parts()["SW_PWR"], C.pcb_solid()])
    assert outer <= LAY.frame[2] - 0.3 + 1e-6 and frame.bounding_box().max.X == pytest.approx(LAY.frame[2])
    # 包絡の決め: つまみの脇 3.0・つまみの先から本体の側へ 1.0・行程の公差込みで掃く・枠の上面の 5 上まで
    e = C.nail_envelope(1).bounding_box()
    assert (e.size.Y, e.max.Z) == pytest.approx((S.PSW_NAIL[0] + S.PSW_TRAVEL + S.PSW_TRAVEL_TOL, 10.0)) and e.max.X > LAY.frame[2] + 5
    assert LAY.psw_knob(1)[2] - e.min.X == pytest.approx(S.PSW_NAIL[1])
    # 切り欠き（利用者が (ii) で触った形）: 内側の面で幅 10・包絡（行程の公差込み）の両側に 0.55 ずつ余る・外面では片側 2.4 ずつ広い 14.8
    n = LAY.psw_notch()
    assert n[-1][1] - n[0][1] == pytest.approx(10.0) and n[-1][1] - C.nail_envelope(1).bounding_box().max.Y == pytest.approx(0.55)
    assert n[-2][1] - n[1][1] == pytest.approx(14.8) and n[1][0] == pytest.approx(LAY.frame[2]) and S.PSW_NOTCH == (10.0, 2.4, 2.0)
    top = S.FRAME_UNDER + S.FRAME_T
    x0, y = n[0][0], S.PSW_AT[1]
    assert x0 == pytest.approx(LAY.psw_body()[2] + S.PART_CLEAR) and LAY.frame[2] - x0 == pytest.approx(1.65)
    # 外面で広がっている: 内側の幅の外・外面のすぐ内（y は中心から 6.5）に枠が無い。内側の面の高さ（x0 のすぐ外）では、幅 10 の外に枠がある
    assert not frame.is_inside((LAY.frame[2] - 0.2, y + 6.5, 4.0)) and not frame.is_inside((LAY.frame[2] - 0.2, y - 6.5, 4.0))
    assert frame.is_inside((x0 + 0.1, y + 5.6, 4.0)) and frame.is_inside((x0 + 0.1, y - 5.6, 4.0)) and frame.is_inside((LAY.frame[2] - 0.2, y + 7.8, 4.0))
    # 内側の面の上の縁は 45° に落ちている（2.0）・その下は厚い屋根が 1.2 残る（スイッチの本体の上 0.3 から）
    assert not frame.is_inside((x0 - 0.5, y, top - 0.1)) and frame.is_inside((x0 - 0.5, y, top - 1.8)) and frame.is_inside((x0 - 2.3, y, top - 0.1))
    assert frame.is_inside((x0 - 0.1, y, C.psw_ceiling() + 0.1)) and frame.is_inside((x0 - 0.1, y, top - 2.0 - 0.1)) and not frame.is_inside((x0 - 0.1, y, top - 1.8))
    # 入の印は、つまみを入に寄せた側（奥）の、斜めに落とした面のすぐ内の**平らな上面**にあり、斜面にも切り欠きにも落ちていない
    mark = C.corner_cuts()["on_mark"].bounding_box()
    my, mx = (mark.min.Y + mark.max.Y) / 2, (mark.min.X + mark.max.X) / 2
    assert my > S.PSW_AT[1] + S.PSW_TRAVEL / 2 and S.PSW_ON == 1 and n[0][1] < my < n[-1][1]
    assert my == pytest.approx(S.PSW_AT[1] + S.PSW_TRAVEL / 2 + S.PSW_KNOB[0] / 2)       # 高さ（y）は前と同じ: 入に寄せたつまみの奥の縁
    assert frame.is_inside((mx + 0.9, my, top - 0.2)) and not frame.is_inside((mx, my, top - 0.2)) and frame.is_inside((mx, my, top - S.ON_MARK[1] - 0.1))
    assert mx + S.ON_MARK[0] / 2 < x0 - S.PSW_NOTCH[2]


@pytest.mark.parametrize("kw, word", [
    (dict(shift=(1.0, 0.0, 0.0)), "先"),                                    # 最初の位置（1.0 外）: つまみが枠の外へ 0.40 出る
    (dict(shift=(0.1, 0.0, 0.0)), "先"),                                    # 0.1 外: 先は基板の縁の 0.20 内側（0.30 を割る）
    (dict(shift=(0.0, 1.0, 0.0)), "爪"),                                    # 切り欠きが 1.0 ずれている
    (dict(shift=(0.0, 0.0, 0.9)), "当たる"),                                # つまみが 0.9 高い → 厚い屋根に当たる
    (dict(block="narrow"), "爪"),                                           # 切り欠きの幅が 9（奥の端に 1.0 の塊）
    (dict(block="lid"), "爪"),                                              # 切り欠きの上が塞がっている（上から届かない）
    (dict(block="side"), "爪"),                                             # 切り欠きの外面の側が塞がっている（横から届かない）
])
def test_the_knob_check_notices_a_break(halves, kw, word):
    n, f = LAY.psw_notch(), LAY.frame
    blocks = {"narrow": C._box((n[0][0], n[-1][1] - 1.0, f[2], n[-1][1]), 0.0, 5.0),
              "lid": C._box((n[0][0], n[0][1], f[2], n[-1][1]), 4.0, 5.0),
              "side": C._box((f[2] - 0.8, n[0][1], f[2], n[-1][1]), 0.0, 5.0)}
    kw = dict(kw, block=blocks[kw["block"]]) if "block" in kw else kw
    bad = knob_problems(corner_piece(halves), **kw)
    assert any(word in b for b in bad), bad


def test_the_wall_around_the_knob_notch_is_strong_enough():
    """切り欠きの内側は、屋根を基板の上 1.8 まで厚くして塞いである（薄い垂れ壁にしない）。指で 10 N 押したときの応力の見積もりを、
    Bambu PLA Basic の TDS の曲げ強さ 76 MPa の半分（積層の向きの弱さを見る）= 38 MPa と比べる。**内側の上の縁を斜めに落としたので、
    前の形（7.3 MPa）より弱い**:
      - 縁の 2.0 幅だけが梁として働くと見た場合（いちばん厳しい見方。断面は台形）: 20.4 MPa = 上限の 0.54 倍
      - 厚い屋根の全幅 5.4 が働くと見た場合: 3.5 MPa
    どちらの断面も**枠の立体から測る**（式で置いた台形と、立体から測った断面が合うことも見る）。"""
    got = C.notch_strength()
    assert (got["roof_t"], got["roof_edge"]) == pytest.approx((3.2, 1.2)) and got["stub_len"] == pytest.approx(5.125)
    assert got["stub_area"] == pytest.approx(7.525 * 3.0 - 2.4 * 1.65 / 2) and got["stub"] < got["limit"] / 4, got
    assert got["roof"] == pytest.approx(20.4, abs=0.2) and got["roof"] < got["limit"] / 1.5, got
    assert C.notch_strength(press=20.0)["roof"] > got["limit"]               # 検査器が生きている: 20 N なら厳しい見方では上限を超える
    # 作った枠で: 厚い屋根は切り欠きの内側の面まであり、スイッチの本体の上 0.3 から詰まっている。内側の面では上の 2.0 が斜めに落ちている
    r = C.psw_roof_rect()
    frame = C.frame_halves()["right"] & C._box((r[0] - 1, r[1] - 1, LAY.frame[2] + 1, r[3] + 1), -1.0, 6.0)
    x, y = r[2] - 0.2, S.PSW_AT[1]
    assert not frame.is_inside((x, y, C.psw_ceiling() - 0.1)) and frame.is_inside((x, y, C.psw_ceiling() + 0.1)) and frame.is_inside((x, y, 2.9))
    assert not frame.is_inside((x, y, 4.9)) and frame.is_inside((r[2] - 2.2, y, 4.9))
    assert not frame.is_inside((r[2] + 0.2, y, 2.5))
    # 立体から測った断面: 縁の 2.0 幅は面積 4.4（2.0 × 3.2 から三角 2.0 を引いた台形）で、式と同じ応力。全幅は 5.4
    area, _, _, _ = C.roof_section(frame, 2.0)
    assert area == pytest.approx(2.0 * 3.2 - 2.0 * 2.0 / 2, abs=0.05)
    assert C.notch_roof_stress(frame, 2.0) == pytest.approx(got["roof"], rel=0.02)
    full = r[2] - r[0]
    assert full == pytest.approx(5.4) and C.notch_roof_stress(frame, full) < got["limit"] / 4
    # 検査器が生きている: 斜めに落とす量を 3.0 にした枠なら（内側の面で 0.2 しか残らない）、厳しい見方で上限を超える
    deep = frame - C._prism_y([(r[2] - 4.0, 6.0), (r[2] + 0.01, 2.0 - 0.01), (r[2] + 0.01, 6.0)], r[1], r[3])
    assert C.notch_roof_stress(deep, 2.0) > got["limit"]


def test_a_fingertip_reaches_past_the_knob_tip_on_the_real_frame(halves):
    """指で届くか（利用者が「奥すぎる」と言った前の位置との違い）。指先 = 半径 PSW_FINGER_R の硬い球（**仮定**。比べる物差し）を、
    本番の枠の角・基板・スイッチの本体に当てて、机に置いたまま、つまみの先より奥へどれだけ入るかを測る。いまの位置は +0.16
    （利用者が試し刷り v2 の (ii) で「こちらがよい」と言った形と同じ数）。前の位置は −0.03（tests/test_cckb_click_coupon_v2.py）。"""
    things = Compound([corner_piece(halves), C.pcb_solid(), C._box(LAY.psw_body(), 0.0, LAY.z()["psw_top"])])
    got = C.finger_reach(things)
    assert (got["tip_in"], got["open"], got["depth"], got["r"]) == pytest.approx((0.60, 14.8, 1.65, S.PSW_FINGER_R)) and S.PSW_FINGER_R == 7.5
    assert got["bite"] == pytest.approx(0.16, abs=0.03) and got["bite"] > 0.1, got
    # 検査器が生きている: 外面で広げていない切り欠き（幅 10 のまま = 広がりを塞いだ枠）では、入る量が 0.10 減る（+0.06）
    n, f2 = LAY.psw_notch(), LAY.frame[2]
    plugs = Compound([C._box((n[0][0], n[-1][1], f2, n[-2][1]), 0.0, 5.0), C._box((n[0][0], n[1][1], f2, n[0][1]), 0.0, 5.0)])
    assert C.finger_reach(Compound([things, plugs]))["bite"] == pytest.approx(got["bite"] - 0.10, abs=0.03)


# ---------------------------------------------------------------------------
# 電池の蓋（道具なし・上から落とし込む。利用者の決定 2026-10-04・決定記録 2026-10-04-cover-latch）
# 利用者の条件: **電池は、押しても振っても出ない。人が、しっかり付いた蓋を先に外したときだけ出せる。**蓋の留めは形で止まる物（摩擦だけの留めにしない）。
# 外の事実: クリップの図面 MY-CP-0247（板厚 0.25・高さ 4.0・止めの折れ 2.80・未注の公差 ± 0.25）・CR1632 φ16 × 3.2・1.8 g（Energizer のデータシート）・
# Bambu PLA Basic の TDS（曲げ弾性率 2750・曲げ強さ 76）・落下の仮定 JEDEC JESD22-B111 条件 B（1500 G・0.5 ms）
# ---------------------------------------------------------------------------
DIRS = {"手前": (0, -1, 0), "奥": (0, 1, 0), "左": (-1, 0, 0), "右": (1, 0, 0), "上": (0, 0, 1), "下": (0, 0, -1),
        "左手前": (-0.7071, -0.7071, 0), "右手前": (0.7071, -0.7071, 0), "手前上": (0, -0.7071, 0.7071), "手前下": (0, -0.7071, -0.7071)}


def clip_nominal():
    """電池クリップの、図面の名目の形（板と止め）。電池が動けるかを見る相手（clip_solid は公差の端まで太らせた形で、止めに当てた電池と重なる）。"""
    b = LAY.clip_body()
    x = S.CLIP_AT[0]
    return Compound([C._box(b, S.CLIP_H - S.CLIP_SHEET_T, S.CLIP_H),
                     C._box((x - S.CLIP_STOP_W / 2, b[3] - S.CLIP_SHEET_T, x + S.CLIP_STOP_W / 2, b[3]), S.CLIP_H - S.CLIP_STOP_DROP, S.CLIP_H)])


def cover_things(frame):
    """蓋の相手 {名前: 立体}。クリップは図面から作った「金属のある所」（公差の端まで）。"""
    parts = C.board_parts()
    cv = LAY.cover()
    near = [k for k in LAY.keys if k.x1 > cv["x0"] - UNIT and k.y - UNIT / 2 < cv["y1"] + UNIT]
    (cx, cy), r = LAY.cell()
    return {"枠": frame, "電池": C.cell_solid(), "クリップ": C.clip_solid(), "基板": C.pcb_solid(),
            "ほかの部品": Compound([v for n, v in parts.items() if n != "BT1"]),
            "底のシート": C.sheet_solid(),
            "枠のねじ": Compound(list(C.screw_solids().values())),
            "キャップ": Compound([C.cap_pose(k, m) for k in near for m in ("latched",) + C.POSES]),
            # 電池を押さえる舌（図面に寸法が無い）は電池の円の中にある: 電池の上面の少し上まで、電池の円 ＋ 隙（− 0.05）に蓋が入らないことで見る
            "電池の円（舌の来る所）": Pos(cx, cy, 0) * Cylinder(r + S.COVER_CELL_CLEAR - 0.05, S.CELL_T + 0.6, align=C.CEN_MIN)}


def moved(part, d, k):
    return Pos(d[0] * k, d[1] * k, d[2] * k) * part


def first_hit(part, others, d, steps):
    """part を d の向きへ steps の量ずつ動かして、others に当たる最初の量（当たらなければ None）。"""
    for k in steps:
        if vol(others, moved(part, d, k)) > TOL:
            return k
    return None


def cover_problems(frame, cover=None, opened=None, shift=(0.0, 0.0, 0.0), things=None, variant=None):
    """蓋を組んだ位置で:
      - 枠・電池・クリップ・基板・ほかの部品・シート・ねじ・キャップに当たらない。上面は枠と面一・手前の面は枠の外面から出ない・足は基板に着く
      - **電池の止め**: 蓋は手前へ COVER_RECESS より多くは動けない（耳が溝の斜めの面に座る）。棒を押し込んだ蓋（opened）でも同じ = 止めは棒に頼っていない
      - **留め**: 棒を押し込まない蓋は、上へ COVER_CATCH_GAP ＋ 0.1 より多くは動けない（棒の先が歯の下に当たる）
      - **入れられる・外せる**: 棒を release_max 押し込んだ蓋は、まっすぐ上へ 7 mm、何にも当たらずに動く（0.25 おき）"""
    out = []
    rel = C.cover_numbers(variant)["release_max"]
    cover = Pos(*shift) * (C.cover_solid(variant) if cover is None else cover)
    opened = Pos(*shift) * (C.cover_solid(variant, rel) if opened is None else opened)
    things = things or cover_things(frame)
    for name, v in things.items():
        if vol(v, cover) > TOL:
            out.append(f"蓋が{name}に当たる {vol(v, cover):.3f} mm3")
    b = cover.bounding_box()
    f = LAY.frame
    top = S.FRAME_UNDER + S.FRAME_T
    if b.max.Z > top + 1e-6 or b.min.Y < f[1] - 1e-6 or b.min.Z < -1e-6:
        out.append(f"蓋が枠の上面・外面・基板の面から出る（上 {b.max.Z:.3f}・手前 {b.min.Y:.3f}・下 {b.min.Z:.3f}）")
    if top - b.max.Z > 0.01 or b.min.Y - f[1] > S.COVER_RECESS + 0.01 or b.min.Z > 0.01:
        out.append(f"蓋が枠の上面と面一でない・手前の面が引っ込みすぎ・足が基板に着かない（上 {b.max.Z:.3f}・手前 {b.min.Y:.3f}・下 {b.min.Z:.3f}）")
    for name, c in (("棒を押し込まない蓋", cover), ("棒を押し込んだ蓋", opened)):
        k = first_hit(c, things["枠"], DIRS["手前"], (0.1, 0.2, 0.3, 0.4, 0.6, 1.0, 2.0, 3.0))
        if k is None or k > S.COVER_RECESS + 0.16:
            out.append(f"{name}が手前へ止まらない（{k} 動いて枠に当たる。{S.COVER_RECESS + 0.15:.2f} 以内）")
    k = first_hit(cover, things["枠"], DIRS["上"], (0.1, 0.2, 0.3, 0.4, 0.6, 1.0, 2.0, 3.0, 4.0, 4.9))
    if k is None or k > S.COVER_CATCH_GAP + 0.11:
        out.append(f"蓋が上へ抜ける（{k} 動いて枠に当たる。{S.COVER_CATCH_GAP + 0.1:.2f} 以内）")
    on_path = ("枠", "電池", "クリップ", "基板", "ほかの部品")
    obstacles = Compound([things[n] for n in on_path])               # まとめて当てる（当たった所だけ、相手を 1 つずつ調べる）
    for i in range(0, 29):
        up = Pos(0, 0, 0.25 * i) * opened
        if vol(obstacles, up) > TOL:
            hit = {n: round(vol(things[n], up), 3) for n in on_path if vol(things[n], up) > TOL}
            out.append(f"棒を押し込んだ蓋を上へ {0.25 * i:.2f} 持ち上げた所で{'・'.join(hit)}に当たる {hit}")
            break
    return out


@pytest.fixture(scope="module")
def cover_env(halves):
    return cover_things(corner_piece(halves))


def test_the_drop_in_battery_cover_fits_and_all_three_variants_fit_the_same_frame(halves, cover_env):
    """蓋は上からまっすぐ落とす。試し刷りの 3 つ（棒の厚さ・隙の違い）は、同じ枠に入る。**基板は変えない**（穴 H30・H31 は使わない）。"""
    frame = corner_piece(halves)
    for n in sorted(S.COVER_VARIANTS):
        assert cover_problems(frame, things=cover_env, variant=n) == [], n
        cover = C.cover_solid(n)
        assert len(cover.solids()) == 1 and cover.is_valid, n
    assert sorted(S.COVER_VARIANTS) == [1, 2, 3] and S.COVER_MAIN == 2
    cv = LAY.cover()
    cover = C.cover_solid()
    b = cover.bounding_box()
    # 口: 幅 19.0（歯の間 17.0 = 電池 16 の左右に 0.5）・外面から奥行き 4.5。蓋は口の中に片側 0.15・手前の面は外面の 0.15 内・上面は枠と同じ高さ
    assert (cv["x1"] - cv["x0"], cv["tooth"][1] - cv["tooth"][0]) == pytest.approx((19.0, 17.0)) and cv["y1"] - cv["y0"] == pytest.approx(4.5)
    assert (b.min.Y - LAY.frame[1], b.max.Z, b.min.Z) == pytest.approx((S.COVER_RECESS, 5.0, 0.0), abs=1e-6)
    assert cv["side"] == pytest.approx((cv["x0"] + 0.15, cv["x1"] - 0.15))
    # 棒: 高さ 0.8・切れ目 0.4・長さ 13.7。下の棒 A は基板の上 1.7〜2.5（先は右）・上の棒 B は 2.9〜3.7（先は左）。歯の下面は棒の上面の 0.2 上
    assert cv["band"] == {"A": pytest.approx((1.7, 2.5)), "B": pytest.approx((2.9, 3.7))} and cv["leaf_len"] == pytest.approx(13.7)
    assert cv["ledge"] == {"A": pytest.approx(2.7), "B": pytest.approx(3.9)} and (cv["z_sill"], cv["z_strip"]) == (pytest.approx((0.1, 1.3)), pytest.approx(4.1))
    yf = cv["yf"]
    za, zb = 2.1, 3.3
    assert cover.is_inside((cv["tip"]["A"] - 0.3, yf + 0.5, za)) and not cover.is_inside((cv["tip"]["A"] - 0.3, yf + 0.5, zb))     # 右の先にいるのは下の棒
    assert cover.is_inside((cv["tip"]["B"] + 0.3, yf + 0.5, zb)) and not cover.is_inside((cv["tip"]["B"] + 0.3, yf + 0.5, za))     # 左の先は上の棒
    xm = (cv["x0"] + cv["x1"]) / 2
    assert all(cover.is_inside((xm, yf + 0.5, z)) for z in (0.7, za, zb, 4.6)) and not any(cover.is_inside((xm, yf + 0.5, z)) for z in (1.5, 2.7, 3.9))
    # 棒の先の後ろは空いている: 先の側の足は、棒の高さ ± 切れ目の幅だけ、手前から奥まで抜いてある（奥行き 2.5 − 棒の厚さ 1.0 = 1.5 ≧ 外すたわみ 1.1 ＋ 0.2）。
    # その上と下の足は詰まっている。付け根の側の足は、棒の高さでも詰まっている
    t = cv["t"]
    xr_, xl_ = cv["tip"]["A"] - 1.0, cv["tip"]["B"] + 1.0
    assert not any(cover.is_inside((xr_, yf + t + d, za)) for d in (0.3, 0.8, 1.4)) and cover.is_inside((xr_, yf + 2.0, 0.7)) and cover.is_inside((xr_, yf + 2.0, zb))
    assert not any(cover.is_inside((xl_, yf + t + d, zb)) for d in (0.3, 0.8, 1.4)) and cover.is_inside((xl_, yf + 2.0, za)) and cover.is_inside((xl_, yf + 2.0, 4.2))
    assert cv["y_block"] - (yf + t) >= C.cover_numbers()["release_max"] + 0.2 and S.COVER_FRONT_T == 1.0
    # 棒・下の帯と電池の縁の隙 0.56・上の板はクリップの上 4.1 から 0.2。足の内の奥の角と電池の縁の隙は COVER_CELL_CLEAR 0.3（足が先に当たる）
    (cx, cy), r = LAY.cell()
    corner = (cv["block"][0][1], cv["y_block"])
    assert math.hypot(corner[0] - cx, corner[1] - cy) - r == pytest.approx(S.COVER_CELL_CLEAR, abs=0.01)
    assert (cy - r) - (yf + t) == pytest.approx(0.56) and cv["z_plate"] - LAY.z()["clip_top"] == pytest.approx(0.2)
    # 足は、クリップの板（外接の矩形）の 0.2 手前で終わる。**板の下へは入れない**（上へ抜くとき、板に当たる）: 上の板より下の蓋は、板の端より手前だけ
    low = cover & C._box((cv["side"][0] + 0.05, -60, cv["side"][1] - 0.05, -30), -1.0, cv["z_plate"] - 0.05)
    assert low.bounding_box().max.Y == pytest.approx(cv["y_block"]) and LAY.clip_body()[1] - cv["y_block"] == pytest.approx(S.COVER_CLIP_CLEAR)
    clip = cover_env["クリップ"]
    assert vol(cover, Pos(0, 0, -3.0) * clip) < TOL                                                     # 板がどれだけ低くても、足には当たらない
    assert vol(cover, Pos(0, 0, 0.15) * clip) < TOL and vol(cover, Pos(0, 0, 0.3) * clip) > 0.01        # 板が 0.3 高ければ、上の板に当たる（隙 0.2）
    # 基板の穴 H30・H31 は使わない: 蓋の足が上に載るだけ（穴に入る物は無い）・ねじは 20 本・底のシートは穴を塞ぐ
    assert cv["holes"] == [(115.0, -48.225), (129.0, -48.225)] and b.min.Z >= -1e-9
    assert len(C.screw_solids()) == 20 and not any(ref in C.screw_solids(spare=True) for ref in ("H30", "H31"))
    for x, y in cv["holes"]:
        assert cover.is_inside((x, y, 0.3)) and C.sheet_solid().is_inside((x, y, -S.PCB_T - 0.25)) and not C.pcb_solid().is_inside((x, y, -0.8))
    # 厚さは増えない。蓋があると電池は出せない
    assert LAY.z()["total"] == pytest.approx(8.1) and vol(cover, cell_path()) > 10.0


def test_the_cell_is_stopped_by_solid_plastic_and_the_load_does_not_pass_through_the_springs(halves, cover_env):
    """**電池が押す向き（手前）と、蓋が外れる向き（上）が直角。**電池の力の道: 電池 → 蓋の足 → 耳の 45° の面 → 枠の溝の手前の壁。棒は道に無い。"""
    frame = corner_piece(halves)
    cv = LAY.cover()
    cover, opened = C.cover_solid(), C.cover_solid(None, C.cover_numbers()["release_max"])
    cell = C.cell_solid()
    # 電池は手前へ 0.35 で蓋に当たる。当たるのは足の奥の角（手前の面から 2.0 より奥）で、棒・手前の板ではない。**棒を切り取った蓋でも同じ所で止まる**
    # = 止めは棒に頼っていない
    xm = (cv["x0"] + cv["x1"]) / 2
    no_leaves = cover - C._box((cv["tooth"][0] - 2.0, cv["yf"] - 1, cv["tooth"][1] + 2.0, cv["yf"] + 1.05), cv["z_sill"][1] + 0.05, cv["z_strip"] - 0.05)
    assert not no_leaves.is_inside((xm, cv["yf"] + 0.5, 2.1)) and not no_leaves.is_inside((xm, cv["yf"] + 0.5, 3.3)) and len(no_leaves.solids()) == 1
    for c in (cover, no_leaves):
        assert first_hit(cell, c, DIRS["手前"], (0.1, 0.2, 0.3, 0.4, 0.5)) == pytest.approx(0.4)                # 0.3 と 0.4 の間（計算では 0.35）
        hit = moved(cell, DIRS["手前"], 0.5) & c
        assert hit.bounding_box().min.Y > cv["yf"] + 2.0 and hit.bounding_box().max.Z > S.CELL_T - 0.1 and hit.bounding_box().min.Z < 0.1     # 電池の高さいっぱいで当たる
    # 蓋は手前へ 0.21（斜めの面の隙 0.15 を前後に測った量）で枠に座る。座っても枠の外面から出ない（0.15 引っ込めてある分より 0.06 多いだけ: 下の数）
    seat = S.COVER_CLEAR * math.sqrt(2.0)
    assert vol(frame, moved(cover, DIRS["手前"], seat - 0.02)) < TOL and vol(frame, moved(cover, DIRS["手前"], seat + 0.03)) > TOL
    assert seat - S.COVER_RECESS == pytest.approx(0.062, abs=0.001)
    # 受ける面: 左右の耳の斜めの面（45°・上から下まで 5.0・長さ 2.0 × √2）。0.3 押し込んだ重なりのうち、口の左右の外にある 2 つ。
    # （0.3 から先は、蓋の角の斜めの面が歯の奥の角にも当たる = 2 つ目の止め: 重なりは口の中にもう 2 つ）
    over = (moved(cover, DIRS["手前"], 0.3) & frame).solids()
    sides = sorted((q for q in over if q.bounding_box().max.X < cv["x0"] + 0.01 or q.bounding_box().min.X > cv["x1"] - 0.01), key=lambda q: q.bounding_box().min.X)
    assert len(sides) == 2 and len(over) == 4 and sides[0].bounding_box().max.X < cv["x0"] + 0.01 and sides[1].bounding_box().min.X > cv["x1"] - 0.01
    for q in sides:
        bb = q.bounding_box()
        assert bb.size.Z == pytest.approx(5.0, abs=0.01) and bb.size.X == pytest.approx(S.COVER_WEDGE, abs=0.25), bb
    # 刷った物が ± 0.15 ずれ、蓋が片側へ寄り切っても掛かりが残る: 隙 0.20 の蓋（蓋 3）を、さらに 0.3 右へ寄せて手前へ押す → 左の耳も 1.4 以上掛かる
    loose = Pos(0.3, 0, 0) * C.cover_solid(3)
    over = moved(loose, DIRS["手前"], 1.0) & frame
    left = [q for q in over.solids() if q.bounding_box().max.X < cv["x0"] + 0.01]
    assert left and max(q.bounding_box().size.X for q in left) >= 1.4 and S.COVER_WEDGE - 0.3 - 0.3 >= 1.4 - 1e-9
    # 外れる向きは上だけ: 棒を押し込んだ蓋は、上へは動き（cover_problems）、手前・奥・左右・下へは 0.3 以内で止まる
    held = Compound([frame, cover_env["基板"]])
    for name in ("手前", "奥", "左", "右", "下"):
        assert first_hit(opened, held, DIRS[name], (0.1, 0.2, 0.3)) is not None, name
    assert sum(a * b for a, b in zip(DIRS["手前"], DIRS["上"])) == 0
    # 力の見積もり（計算。刷った物の値ではない）: 1500 G で電池 1.8 g が押す力 26.5 N。耳の斜めの面の面圧 1.3 MPa（曲げ強さ 76 の 1/50）
    num = C.cover_numbers()
    assert S.CELL_MASS == 1.8 and S.DROP_G == 1500.0 and num["cell_force"] == pytest.approx(26.5, abs=0.1)
    assert num["ear_pressure"] == pytest.approx(1.32, abs=0.02) and num["ear_pressure"] < S.PLA_BEND / 50


def test_with_the_cover_locked_the_cell_has_no_way_out_in_any_direction(halves, cover_env):
    """蓋を付けた状態で、電池（止めに当てた位置）を 10 の向きへ動かす。どの向きも 1.0 以内で、枠・蓋・クリップ（図面の名目の板と止め）・基板のどれかに
    当たり、その先 3 mm（手前の向きは、電池の半分の 8 mm）まで当たり続ける（すり抜けない）。蓋が無ければ、手前へは 22 mm 何にも当たらない（電池を替える道）。"""
    frame = corner_piece(halves)
    cell = C.cell_solid()
    cage = Compound([frame, C.cover_solid(), clip_nominal(), cover_env["基板"]])
    assert vol(cage, cell) < TOL
    for name, d in DIRS.items():
        k = first_hit(cell, cage, d, (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0))
        far = (1.5, 2.0, 3.0) + ((5.0, 8.0) if name == "手前" else ())
        assert k is not None and all(vol(cage, moved(cell, d, s)) > TOL for s in far), name
    assert first_hit(cell, cage, DIRS["手前"], (0.3, 0.4)) == 0.4 and first_hit(cell, cage, DIRS["上"], (0.5, 0.6)) == 0.6     # 手前は 0.35 で足・上は 0.55 でクリップの板
    # 検査器が生きている: 蓋を外すと、手前へ出る（歯の間 17.0 を電池 16.0 が通る）
    open_cage = Compound([frame, clip_nominal(), cover_env["基板"]])
    assert all(vol(open_cage, moved(cell, DIRS["手前"], s)) < TOL for s in (0.5, 1.0, 2.0, 5.0, 12.0, 22.0))
    # 電池を 0.5 より大きく右へ寄せて出そうとすると、右の歯に当たる（右の歯は電池の高さに掛かる。左の歯は電池より上）
    assert vol(frame, Pos(0.7, -9.0, 0) * cell) > TOL and vol(frame, Pos(-0.7, -9.0, 0) * cell) < TOL and S.CELL_T < LAY.cover()["ledge"]["B"]


def tipped(part, axis, deg, pivot):
    """立体を、pivot を通る axis（"x" / "y" / "z"）の向きの軸のまわりに deg 回す。"""
    piv = Pos(*pivot)
    return piv * Rot(*[deg if a == axis else 0 for a in "xyz"]) * piv.inverse() * part


def lock_problems(frame, board, cover=None, variant=None, deflect=(0.0,)):
    """**留まっているか**: 棒を deflect だけ押し込んだ蓋が、枠と基板の中で、平行に動かしても・回しても出てこない。
      平行: 手前・奥・左右・下は 0.3 以内、上は 0.3 以内で当たる
      回す: 手前の上の縁・手前の下の縁（x の軸）、左の下の角・右の下の角（y の軸 = 片側だけ持ち上がる動き）、真ん中（z の軸）のまわりに ± 4〜12°
            （± 2° までは隙の中の遊び: 上の縁が 0.17 動く）"""
    out = []
    cv = LAY.cover(variant)
    f = LAY.frame
    held = Compound([frame, board])
    xm = (cv["x0"] + cv["x1"]) / 2
    for d in deflect:
        c = C.cover_solid(variant, d) if cover is None else cover
        for name in ("手前", "奥", "左", "右", "下", "上"):
            k = first_hit(c, held, DIRS[name], (0.1, 0.2, 0.3))
            if k is None:
                out.append(f"棒を {d} 押し込んだ蓋が、{name}へ 0.3 動く")
        for label, axis, pivot in (("手前の上の縁", "x", (xm, f[1], 5.0)), ("手前の下の縁", "x", (xm, f[1], 0.0)), ("左の下の角", "y", (cv["x0"], f[1], 0.0)),
                                   ("右の下の角", "y", (cv["x1"], f[1], 0.0)), ("真ん中", "z", (xm, f[1] + 1.5, 0.0))):
            for deg in (4.0, 8.0, 12.0, -4.0, -8.0, -12.0):
                if vol(held, tipped(c, axis, deg, pivot)) < 0.01:
                    out.append(f"棒を {d} 押し込んだ蓋が、{label}のまわりに {deg}° 回る")
    return out


def test_the_cover_cannot_come_out_unless_the_springs_are_pushed_in_and_it_is_lifted(halves, cover_env):
    """留め: 棒の先が、枠の歯の下に**直角の面で**当たる（摩擦で留める所は無い）。外すには、棒の先を 0.95（蓋が前へ寄り切っていれば 1.1）押し込んで、
    そのまま持ち上げる = **2 つの動きを同時に**（Energizer のデータシートの「電池の蓋は、道具か、同時に行う 2 つの独立した動きで開く形に」と同じ形）。
    試し刷りの 4 つの蓋は「内側へ落ちる」ことがよくあった → 倒れる向き・片側だけ浮く向きも、立体を回して見る。"""
    frame = corner_piece(halves)
    board = cover_env["基板"]
    num = C.cover_numbers()
    cv = LAY.cover()
    assert (num["release"], num["release_max"]) == pytest.approx((0.95, 1.1))
    for n in sorted(S.COVER_VARIANTS):
        assert lock_problems(frame, board, variant=n) == [], n
    # 棒を押し込む量が足りないと抜けない: 0.5・0.8 では上へ 0.3 以内で歯に当たる。0.95（名目）で初めて上へ抜ける
    cover = C.cover_solid()
    for d in (0.5, 0.8):
        assert first_hit(C.cover_solid(None, d), frame, DIRS["上"], (0.1, 0.2, 0.3)) is not None, d
    assert all(vol(frame, Pos(0, 0, 0.25 * i) * C.cover_solid(None, 0.95)) < TOL for i in range(29))
    # 片方の棒だけ押し込んでも抜けない: 押し込んだ蓋の右半分 ＋ 押し込まない蓋の左半分（左の歯に上の棒が掛かったまま）
    xm = (cv["x0"] + cv["x1"]) / 2
    half = (C.cover_solid(None, 1.1) & C._box((xm, -60, 140, -30), -1, 6)) + (cover & C._box((100, -60, xm, -30), -1, 6))
    assert first_hit(half, frame, DIRS["上"], (0.1, 0.2, 0.3)) is not None
    # 掛かり: 歯は口の壁から 1.0 出ている。棒の先は蓋の側面まで = 歯の下に 0.85 入る（左右に 0.15 寄っても 0.7・刷りが 0.15 ずれても 0.55）。
    # 前後は、歯の厚さ 1.0 のうち 0.85（蓋の手前の面が 0.15 引っ込んでいる分を除く）
    over = Pos(0, 0, 0.5) * cover & frame
    tips = sorted(over.solids(), key=lambda q: q.bounding_box().min.X)
    assert len(tips) == 2
    for q, key in zip(tips, ("B", "A")):
        bb = q.bounding_box()
        assert (bb.size.X, bb.size.Y) == pytest.approx((S.COVER_TOOTH[0] - S.COVER_CLEAR, S.COVER_LIP - S.COVER_RECESS), abs=0.02), key
        assert bb.min.Z == pytest.approx(cv["ledge"][key], abs=0.01)
    # 歯の下面も棒の上面も水平（直角に当たる。斜めの面で外れる向きの力が出ない）: 棒の先の真上 0.1 は空・0.3 は枠
    for key, x in (("A", cv["tip"]["A"] - 0.4), ("B", cv["tip"]["B"] + 0.4)):
        z1 = cv["band"][key][1]
        for y in (cv["yf"] + 0.1, cv["yf"] + 0.4, cv["yf"] + 0.75):
            assert cover.is_inside((x, y, z1 - 0.05)) and not frame.is_inside((x, y, z1 + 0.1)) and frame.is_inside((x, y, z1 + 0.3)), (key, y)
    # 蓋を持ち上げようとすると、棒の先のすぐ下に蓋の硬い所が来る（棒だけが撓んで蓋が浮く、にならない）: 棒の先の 1.5 内で、切れ目 0.4 の下は詰まっている
    slit = S.COVER_LEAF[1]
    assert cover.is_inside((cv["tip"]["A"] - 1.8, cv["yf"] + 0.5, cv["band"]["A"][0] - slit - 0.1))        # 下の棒の下 = 下の帯
    assert cover.is_inside((cv["tip"]["B"] + 1.8, cv["yf"] + 0.5, cv["band"]["B"][0] - slit - 0.1))        # 上の棒の下 = 下の棒の付け根（左の足）
    assert S.COVER_CATCH_GAP + slit == pytest.approx(0.6)                                                   # 蓋が上へ動ける量の上限（歯の隙 ＋ 切れ目）


def test_the_spring_numbers_and_what_a_drop_can_do_to_them():
    """棒（板ばね）の計算。**計算は、前の 4 つの蓋で外れた。ここの数は目安で、決めるのは試し刷り**（だから 3 つ刷る）。
    前の蓋と違う所: 棒は電池の力を受けない・掛かりは直角の面・長さ 13.7（前は 6.3 以下）・外すたわみ 0.95〜1.1 に対して付け根のひずみ 1.4 %。"""
    n1, n2, n3 = (C.cover_numbers(n) for n in (1, 2, 3))
    cv = LAY.cover()
    # 蓋 2（本番の候補）: 先を押す固さ 0.21 N/mm・真ん中を押して外す力は棒 1 本 0.75 N（2 本で 1.5 N = 150 gf）・付け根のひずみ 1.41 %
    # （曲げ強さ ÷ 曲げ弾性率 = 2.76 % の 0.51 倍。0.55 倍を上限に置く: 外すときに一瞬だけ掛かる・何百回も繰り返さない）
    assert (n2["k_tip"], n2["push_force"], n2["strain"]) == pytest.approx((0.214, 0.753, 1.407), abs=0.005)
    assert n2["strain_limit"] == pytest.approx(2.76, abs=0.01) and n2["strain"] < 0.55 * n2["strain_limit"] and n1["strain"] < n2["strain"]
    assert n2["push"] == pytest.approx(0.44) and n2["push"] < 0.56                       # 真ん中の押し込みは、棒と電池の隙より小さい
    # 落下 1500 G が棒の厚さの向き（奥向き）に掛かったとき、棒が自分の重さで動く量（静的）: 蓋 2 は 0.35・蓋 1 は 0.55。外れ始めは 0.80（蓋が奥へ寄り切ったとき）。
    # 余裕は 蓋 2 で 2.3 倍・蓋 1 で 1.5 倍。**衝撃は静的な値より大きく揺らすことがある**（半波 0.5 ms は棒の固有の周期と同じ桁）= 余裕の全部は当てにしない。
    # 棒が一瞬外れても、蓋は同時に上へ 0.8（棒の高さ）動かないと抜けない
    need = n2["release"] - S.COVER_RECESS
    assert need == pytest.approx(0.80) and (n1["drop_tip"], n2["drop_tip"], n3["drop_tip"]) == pytest.approx((0.55, 0.35, 0.34), abs=0.01)
    assert need / n2["drop_tip"] > 2.2 and need / n1["drop_tip"] > 1.4
    # 蓋の自分の重さ 0.20 g が 1500 G で出す力 2.9 N は、上向きなら歯（直角の面）が受ける。電池の力 26.5 N は耳が受ける
    assert n2["cover_force"] == pytest.approx(2.94, abs=0.05) and n2["cell_force"] == pytest.approx(26.5, abs=0.1)
    assert C.cover_solid().volume * C.PLA_DENSITY == pytest.approx(0.200, abs=0.005)
    # 検査器が生きている: 棒を 0.6 に薄くすると、1500 G で外れ始めを超える。1.2 に厚くすると、ひずみが上限を超える
    b, length = S.COVER_LEAF[0], cv["leaf_len"]
    assert C.PLA_DENSITY * b * 0.6 * S.DROP_G * 9.80665e-3 * length ** 4 / (8 * S.PLA_E * b * 0.6 ** 3 / 12) > need
    assert n2["strain"] * 1.2 > 0.55 * n2["strain_limit"]


def _mutated_cover(monkeypatch, variant=None, deflect=0.0, **spec):
    for k, v in spec.items():
        monkeypatch.setattr(S, k, v)
    C.cover_solid.cache_clear()
    try:
        return C.cover_solid(variant, deflect)
    finally:
        C.cover_solid.cache_clear()


@pytest.mark.parametrize("kw, word", [
    (dict(shift=(0.0, 0.0, 0.3)), "上面"),                                   # 0.3 浮いた蓋: 上面から出る・歯に当たる
    (dict(shift=(0.0, 0.3, 0.0)), "枠"),                                     # 0.3 奥: 口の奥の壁・溝の奥の面
    (dict(shift=(0.4, 0.0, 0.0)), "枠"),                                     # 0.4 右
    (dict(shift=(0.0, -0.3, 0.0)), "枠"),                                    # 0.3 手前: 耳が溝の斜めの面に食い込む
    (dict(shift=(0.0, 0.0, -0.2)), "基板"),                                  # 0.2 沈んだ蓋
    (dict(under_clip=True), "持ち上げた所"),                                 # 足がクリップの板の下まで入っている蓋: 置いた位置では当たらないが、上へ抜けない
    (dict(spec=dict(COVER_BLOCK=5.8, COVER_CELL_CLEAR=-0.5)), "電池"),       # 足が広くて、電池の縁に食い込む
    (dict(spec=dict(COVER_BLOCK=5.8, COVER_CELL_CLEAR=0.1)), "電池の円"),    # 足が広くて、電池との隙が 0.1（電池には当たらないが、舌の来る所に入る）
    (dict(spec=dict(COVER_TOP_T=1.0)), "クリップ"),                          # 上の板が厚い: クリップの上面に当たる
    (dict(spec=dict(COVER_RECESS=-0.1)), "外面"),                            # 手前の面が枠の外面から 0.1 出ている
    (dict(clip_high=0.3), "クリップ"),                                       # クリップが 0.3 高い（はんだで浮いた）なら、上の板に当たる
    (dict(no_ears=True), "手前へ止まらない"),                                # 耳の無い蓋: 電池に押されると手前へ出る
    (dict(no_teeth=True), "上へ抜ける"),                                     # 歯の無い枠: 棒を押さなくても上へ抜ける
    (dict(short_leaf=True), "上へ抜ける"),                                   # 棒の先が歯に届かない蓋
    (dict(sill_corner=True), "持ち上げた所"),                                # 歯の下に、棒のほかの物（角を欠いていない下の帯）が残っている蓋: 押し込んでも抜けない
])
def test_the_cover_check_notices_a_break(halves, cover_env, monkeypatch, kw, word):
    frame = corner_piece(halves)
    cv = LAY.cover()
    args = dict(things=dict(cover_env))
    rel = C.cover_numbers()["release_max"]
    if "shift" in kw:
        args["shift"] = kw["shift"]
    if "spec" in kw:
        args["cover"] = _mutated_cover(monkeypatch, **kw["spec"])
        args["opened"] = _mutated_cover(monkeypatch, None, rel, **kw["spec"])
    if "clip_high" in kw:
        args["things"]["クリップ"] = Pos(0, 0, kw["clip_high"]) * cover_env["クリップ"]
    if kw.get("under_clip"):
        lump = C._box((cv["block"][0][0], cv["y_block"] - 0.1, cv["block"][0][0] + 3.0, cv["y_block"] + 1.2), 0.0, 3.1)
        args["cover"], args["opened"] = C.cover_solid() + lump, C.cover_solid(None, rel) + lump
    if kw.get("no_ears"):
        inside = C._box((cv["side"][0], -60, cv["side"][1], -30), -1, 6)
        args["cover"], args["opened"] = C.cover_solid() & inside, C.cover_solid(None, rel) & inside
    if kw.get("no_teeth"):
        args["things"]["枠"] = frame - Compound(list(C.cover_teeth().values()))
    if kw.get("short_leaf"):
        cut = Compound([C._box((cv["x0"] - 1, cv["yf"] - 1, cv["tooth"][0] + 0.3, cv["yf"] + 1.1), 1.4, 3.9),
                        C._box((cv["tooth"][1] - 0.3, cv["yf"] - 1, cv["x1"] + 1, cv["yf"] + 1.1), 1.4, 3.9)])
        args["cover"] = C.cover_solid() - cut
    if kw.get("sill_corner"):
        lump = C._box((cv["tooth"][1] - 0.5, cv["yf"], cv["side"][1], cv["yf"] + 0.8), 0.1, 1.3)
        args["cover"], args["opened"] = C.cover_solid() + lump, C.cover_solid(None, rel) + lump
    bad = cover_problems(frame, **args)
    assert any(word in b for b in bad), bad


def test_the_lock_check_notices_a_frame_without_teeth_and_a_cover_pushed_in(halves, cover_env):
    frame = corner_piece(halves)
    board = cover_env["基板"]
    bare = frame - Compound(list(C.cover_teeth().values()))
    assert any("上" in b for b in lock_problems(bare, board))                                   # 歯が無ければ上へ動く
    assert any("上" in b for b in lock_problems(frame, board, deflect=(1.1,)))                  # 棒を押し込めば上へ動く（= 外し方）
    # 歯が片方だけでも、名目の隙では出てこない（片側だけ浮かそうとすると、蓋の角が口の壁に突っ張る）。**刷った隙が広ければ、片側が少し浮きうる** = 歯は 2 つ要る
    assert lock_problems(frame - C.cover_teeth()["left"], board) == []
    assert any("手前" in b for b in lock_problems(frame, board, cover=C.cover_solid() & C._box((LAY.cover()["side"][0], -60, LAY.cover()["side"][1], -30), -1, 6)))


def overhangs(part):
    """刷る向きに置いた立体の、45° より寝た下向きの面 [(高さ, 面積, x の長さ, y の長さ)]（ベッドの面は除く）。"""
    out = []
    for f in part.faces():
        try:
            n = f.normal_at()
        except Exception:
            continue
        if n.Z < -0.72 and f.center().Z > 1e-3:
            bb = f.bounding_box()
            out.append((round(f.center().Z, 2), round(f.area, 3), round(bb.size.X, 2), round(bb.size.Y, 2)))
    return out


def test_the_cover_prints_front_face_down_without_support_and_the_frame_seat_too(halves):
    """蓋は**手前の面をベッドに**刷る（棒と切れ目が平面の形になる）。耳の面と角の欠きは 45°。45° より寝た下向きの面は無い。
    枠（上面をベッドに）は、歯も溝も宙に浮かない。"""
    for n in sorted(S.COVER_VARIANTS):
        pr = C.cover_print(C.cover_solid(n, 0.0, True))
        b = pr.bounding_box()
        assert b.min.Z == pytest.approx(0.0, abs=1e-6) and len(pr.solids()) == 1 and pr.is_valid
        assert (b.size.Y, b.size.Z) == pytest.approx((5.0, S.FINGER_NOTCH_DEPTH - S.COVER_RECESS - S.COVER_VARIANTS[n]["clear"]))
        assert [o for o in overhangs(pr) if o[1] > 0.05] == [], (n, overhangs(pr))               # 0.05 mm2 より小さい面（耳と足の継ぎ目の重ね）は数えない
    assert C.cover_print().bounding_box().size.X == pytest.approx(22.7)
    # 検査器が生きている: 上面をベッドに置く（枠と同じ向き）と、棒と下の帯が宙に浮く
    assert sum(a for _, a, _, _ in overhangs(P.flip_to_bed(C.cover_solid()))) > 20.0
    # 枠（上面をベッドに）: 宙に浮く面は、入の印の底（前からある）だけ
    ov = overhangs(P.flip_to_bed(corner_piece(halves)))
    assert all(z < 0.5 for z, _, _, _ in ov), ov
    # 歯は、枠の上面（ベッド）から生えている: 上面のすぐ下は詰まっていて、歯の下面より下は空
    cv = LAY.cover()
    frame = corner_piece(halves)
    for x, key in ((cv["x0"] + 0.5, "B"), (cv["x1"] - 0.5, "A")):
        assert frame.is_inside((x, cv["y0"] + 0.3, 4.9)) and frame.is_inside((x, cv["y0"] + 0.3, cv["ledge"][key] + 0.1))
        assert not frame.is_inside((x, cv["y0"] + 0.3, cv["ledge"][key] - 0.1)) and not frame.is_inside((x, cv["y0"] + 0.3, 0.5))
    # 歯の上の奥の縁は斜め（0.6）: 蓋を押し下げると、棒の先の下の斜めの面と合わせて 1.2 = 外すたわみ 1.1 より多く、自分で逃げる
    x = cv["x1"] - 0.5
    assert not frame.is_inside((x, cv["y_lip"] - 0.1, 4.8)) and frame.is_inside((x, cv["y_lip"] - 0.1, 4.3)) and frame.is_inside((x, cv["y_lip"] - 0.7, 4.9))
    assert S.COVER_TOOTH[1] + (S.COVER_LEAF[0] - 0.2) >= C.cover_numbers()["release_max"] + 0.1 - 1e-9


# ---------------------------------------------------------------------------
# 角の試し刷り = 蓋の試し刷り（coupon_corner）: 本番の枠から切り出した物か・代わりの物が本物と同じ所にあるか・蓋 3 つが組めるか
# ---------------------------------------------------------------------------

def test_the_corner_coupon_is_cut_from_the_real_frame_and_its_stand_ins_sit_where_the_real_parts_do():
    cc = C.corner_coupon()
    assert set(cc) == {"frame", "base", "knob", "cell", "cover1", "cover2", "cover3"}
    box = C.corner_coupon_box()
    top = S.FRAME_UNDER + S.FRAME_T
    real = C.frame_full() & C._box(box, -1.0, top + 1.0)
    extra, missing = cc["frame"] - real, real - cc["frame"]
    wall = C._box((box[0], LAY.key_area[1] - 0.01, box[0] + S.COUPON_CORNER_WALL, box[3]), 0.0, S.FRAME_UNDER + 0.01)
    assert missing.volume < TOL and 50 < extra.volume < 90 and vol(extra, wall) == pytest.approx(extra.volume, abs=0.01)
    # 切れ端には、つまみの切り欠き・電池の口（上から下まで抜けている）・耳の溝・歯・ねじ H15 の下穴が入っている
    n = LAY.psw_notch()
    cv = LAY.cover()
    assert box[1] < n[1][1] and n[-2][1] + 1.0 < box[3] and box[0] < cv["gx"][0] - 3.0
    xm = (cv["x0"] + cv["x1"]) / 2
    assert all(not cc["frame"].is_inside((xm, cv["y0"] + 1.0, z)) for z in (0.5, 2.5, 4.5)) and cc["frame"].is_inside((cv["gx"][0] - 0.5, cv["y0"] + 1.0, 2.5))
    assert not cc["frame"].is_inside((cv["x0"] - 0.5, cv["y_groove"] - 0.3, 2.5)) and cc["frame"].is_inside((cv["x0"] - 0.5, cv["y_groove"] + 0.3, 2.5))
    assert cc["frame"].is_inside((cv["x0"] + 0.5, cv["y0"] + 0.5, 4.5)) and cc["frame"].is_inside((cv["x1"] - 0.5, cv["y0"] + 0.5, 3.0))
    h15 = next(c for ref, c, _ in LAY.screws() if ref == "H15")
    assert not cc["frame"].is_inside((*h15, 1.0)) and cc["frame"].is_inside((*h15, S.SCREW_PILOT_DEPTH + 0.3))
    # 当て板: 基板と同じ厚さ・右と手前の縁は基板の縁・穴 3 つ（H15 と、使っていない H30・H31）は本番の位置
    base = cc["base"]
    b = base.bounding_box()
    assert (b.min.Z, b.max.X, b.min.Y) == pytest.approx((-S.PCB_T, LAY.pcb[2], LAY.pcb[1]))
    for ref in ("H15", "H30", "H31"):
        c = next(c for r, c, _ in LAY.screws() if r == ref)
        assert not base.is_inside((*c, -0.8)) and base.is_inside((c[0] + S.SCREW_HOLE_D / 2 + 0.2, c[1], -0.8)), ref
    # 代わりの物: スイッチの本体（外形と背は本物）・つまみ（幅・先の位置は本物。入と切の位置で、塊にも枠にも当たらない。その先へは行かない）
    pb = LAY.psw_body()
    assert base.is_inside((pb[0] + 0.2, pb[1] + 0.2, LAY.z()["psw_top"] - 0.1)) and not base.is_inside((pb[0] + 0.2, pb[1] + 0.2, LAY.z()["psw_top"] + 0.1))
    assert not base.is_inside((pb[0] - 0.2, S.PSW_AT[1], 0.5)) and not base.is_inside((pb[2] + 0.2, pb[1] + 0.2, 0.5))
    for pos in (1, -1):
        k = C.knob_standin(pos)
        kb, rk = k.bounding_box(), LAY.psw_knob(pos)
        assert (kb.max.X, kb.max.Z) == pytest.approx((rk[2], S.PSW_KNOB_Z[1])) and vol(k, base) < TOL and vol(k, cc["frame"]) < TOL
        tipbox = k & C._box((pb[2] + 0.01, -99, 200, 99), -1, 9)
        assert (tipbox.bounding_box().min.Y, tipbox.bounding_box().max.Y) == pytest.approx((rk[1], rk[3]))
        assert vol(Pos(0, pos * 0.4, 0) * k, base) > 0.01                            # 行程の端で止まる
    assert vol(C.knob_standin(1), cc["knob"]) == pytest.approx(cc["knob"].volume)
    # 電池の代わり: φ16 × 3.2・止めに当てた位置で、当て板の止めに 0〜0.01 で触れ、案内の間（隙 0.15）にいる。真ん中に、押す棒を差す穴 φ3
    cb = cc["cell"].bounding_box()
    (cx, cy), r = LAY.cell()
    assert (cb.size.X, cb.size.Z) == pytest.approx((S.CELL_D, S.CELL_T)) and vol(cc["cell"], base) < TOL
    assert not cc["cell"].is_inside((cx, cy, 1.0)) and cc["cell"].is_inside((cx + S.COUPON_PUSH[0] / 2 + 0.2, cy, 1.0))
    assert vol(Pos(0, 0.3, 0) * cc["cell"], base) > 0.01 and vol(Pos(0.3, 0, 0) * cc["cell"], base) > 0.01
    # 当て板の長い穴（裏から棒を差して、電池の代わりを手前へ押す）: 電池の穴の真下から、手前へ 6.0。電池の代わりが足に当たる 0.35 より長く動かせる
    assert not base.is_inside((cx, cy, -0.8)) and not base.is_inside((cx, cy - 5.5, -0.8)) and base.is_inside((cx, cy - 6.5, -0.8)) and S.COUPON_PUSH == (3.0, 4.0, 6.0)
    assert vol(cc["frame"], base) < TOL
    # 蓋 3 つ: 当て板にも枠の切れ端にも電池の代わりにも当たらず、足は当て板に着く。棒を押し込めば上へ抜ける・押し込まなければ抜けない・手前へは止まる。
    # 電池の代わりは、蓋があると手前へ 0.35 で止まる
    marks = []
    for n in sorted(S.COVER_VARIANTS):
        cov = cc[f"cover{n}"]
        assert vol(cov, base) < TOL and vol(cov, cc["frame"]) < TOL and vol(cov, cc["cell"]) < TOL and cov.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
        assert cover_problems(cc["frame"], cover=cov, variant=n, things={"枠": cc["frame"], "電池": cc["cell"], "基板": base,
                                                                        "クリップ": Pos(0, 0, 50) * base, "ほかの部品": Pos(0, 0, 50) * base}) == [], n
        assert first_hit(cc["cell"], cov, DIRS["手前"], (0.3, 0.4, 0.5)) == pytest.approx(0.4)
        # 見分ける切り欠き: 上の板の奥の縁に n 個（本番の蓋には無い）
        missing = C.cover_solid(n) - cov
        marks.append(len(missing.solids()))
        assert missing.volume == pytest.approx(n * S.COVER_MARK[0] * S.COVER_MARK[1] * S.COVER_TOP_T, rel=0.02)
    assert marks == [1, 2, 3]
    # 電池の代わりは、蓋が無ければ、当て板の上を口から出し入れできる
    assert vol(cell_path(), base) < TOL and vol(cell_path(), cc["frame"]) < TOL
    plate = C.corner_coupon_plate()
    size = plate.bounding_box().size
    assert len(plate.solids()) == 7 and max(size.X, size.Y) <= 95 and plate.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)
    # 並べた板: 蓋は手前の面をベッドに（高さ 4.2）・枠の切れ端は上面をベッドに（高さ 5.0）。互いに 3 以上離れている
    layout = dict(C.corner_coupon_layout())
    assert list(layout) == ["cell", "knob", "cover1", "cover2", "cover3", "base", "frame"]
    assert layout["frame"].bounding_box().size.Z == pytest.approx(5.0) and all(layout[f"cover{n}"].bounding_box().size.Z == pytest.approx(4.2, abs=0.06) for n in (1, 2, 3))
    names = list(layout)
    for i, a in enumerate(names):
        for b_ in names[i + 1:]:
            ba, bb = layout[a].bounding_box(), layout[b_].bounding_box()
            gap = L.rect_gap((ba.min.X, ba.min.Y, ba.max.X, ba.max.Y), (bb.min.X, bb.min.Y, bb.max.X, bb.max.Y))
            assert gap >= 3.0, (a, b_, gap)


# ---------------------------------------------------------------------------
# キャップ・書き出し・重さ
# ---------------------------------------------------------------------------

def test_the_caps_are_the_tested_shape_in_the_four_widths_of_the_layout():
    assert C.cap_counts() == {1.0: 51, 1.5: 5, 1.75: 2, 2.25: 4}
    for w in C.CAP_WIDTHS:
        b = C.cap_shape(w).bounding_box()
        assert b.size.Z == pytest.approx(2.4) and b.min.Z == pytest.approx(3.6)
        body = P.body_plan(P.Cell(0, 0, S.HOLE_B, w_u=w), S).bounding_box().size
        assert (body.X, body.Y) == pytest.approx((w * UNIT - 2.0 - 2 * S.CAP_CLEAR, 17.05 - 2 * S.CAP_CLEAR))
    plates = C.caps_plates()
    assert len(plates["caps_1u"].solids()) == 51 and len(plates["caps_wide"].solids()) == 11
    for p in plates.values():
        s = p.bounding_box().size
        assert max(s.X, s.Y) <= S.PRINT_MAX and p.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)


def test_the_weights_and_the_thickness_are_computed_from_the_solids():
    w = C.weights()
    assert w["合計"] == pytest.approx(sum(v for k, v in w.items() if k != "合計"))
    assert 25 < w["枠（左）"] + w["枠（右）"] < 36 and 75 < w["基板"] < 95 and 150 < w["合計"] < 230
    assert LAY.z()["total"] == pytest.approx(8.1)


# ---------------------------------------------------------------------------
# たわみの見積もり（click_stiffness.py）が、作った枠と同じ断面を使っているか
# ---------------------------------------------------------------------------

def test_the_stiffness_estimate_uses_the_rib_section_of_the_real_frame(halves):
    """式の断面（面積）= 作った枠をキーの縁に沿って切ったいちばん細い所。式だけ 2.8 で、枠は 2.64 だった（面取りの分）。"""
    import click_stiffness as K

    k = next(k for k in LAY.keys if k.label == "G")
    frame, t = halves[LAY.side_of(k)], 0.02
    areas = []
    for j in range(-19, 20):
        cut = Pos(k.x + UNIT / 2, k.y + j * 0.5, S.FRAME_UNDER + S.FRAME_T / 2) * Box(LAY.rib() + 0.6, t, S.FRAME_T + 0.02)
        areas.append(vol(frame, cut) / t)
    a, _ = K.rib_section(LAY)
    assert min(areas) == pytest.approx(a, abs=0.02), (min(areas), a)
    got = K.local(LAY)
    assert max(v for name, v in got.items() if "広がる向き" not in name) < K.MARGIN, got
    # 検査器が生きている: 材料が半分の硬さなら、強く押したときに余裕を超える
    assert max(K.local(LAY, e_pla=K.E_PLA[0] / 2).values()) > K.MARGIN
