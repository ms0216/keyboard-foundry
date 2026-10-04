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
from build123d import Box, Compound, Cylinder, Pos, export_stl

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
    assert screw_wall_problems(halves, ring=1.3, step=90)       # 検査器が生きている: 1.3 の肉は無い（内側は 0.7）
    assert len(LAY.wall_screws()) == 22


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
    """E 重要 2: 監査の時は、下穴から斜め内向きの肉が 0.49（壁を厚くする幅 ± 1.2 の角）・真内向きが 0.6 だった。
    基板の穴を 0.1 外へ寄せ、壁を厚くする幅を ± 2.0 にした: 奥と手前の壁と 1u の脇は 0.7 以上。幅の広いキーの脇の 3 本だけ 0.49 が残る。"""
    thin = {}
    for ref, (x, y), kind in LAY.wall_screws():
        m, a = wall_flesh(halves["left" if x < LAY.seam_x(y) else "right"], x, y)
        if LAY.boss_half((x, y)) == S.SCREW_BOSS_HALF:
            assert m >= 0.69, (ref, m, a)
        else:
            thin[ref] = m
    assert sorted(thin) == ["H16", "H17", "H18"] and all(0.47 <= v <= 0.52 for v in thin.values()), thin


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
            want = 1.2 if (x, y) == thick else 0.71 if name == "back" else 0.49
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
    """蓋を外した状態（蓋が無くても同じに使える）。蓋のひさしを足しても、道と、指の届く面積は前と同じ。"""
    bad, area = battery_problems(halves)
    assert bad == [] and area == pytest.approx(23.0, abs=4.0), (bad, area)
    # クリップの口は手前・電池の縁は枠の外面から CELL_RECESS 内側・クリップの口の縁（真ん中のえぐり）より手前が指の切り欠きに出る
    (x, y), r = LAY.cell()
    # 電池は止めに当たる所（クリップの原点より 0.51 奥。1 回目の監査 E 重要 1）
    assert y - r - LAY.frame[1] == pytest.approx(LAY.cell_recess()) == pytest.approx(1.71)
    assert LAY.clip_body()[1] > LAY.frame[1] + LAY.cell_recess() + 1.0
    assert S.FINGER_NOTCH[1] - LAY.cell_recess() >= 2.7                 # 切り欠きから電池の上面が 2.79 見える
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
    """電源スイッチのつまみ（利用者の決定 2026-10-04: 外へ出さない・爪で動かす）。入・切の両方の位置で、行程の公差の端まで:
      - つまみが枠に当たらない・先が枠の外面と基板の縁の内側
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
            if tip > LAY.frame[2] - 1.0 or tip > LAY.pcb[2] - 1.0:
                out.append(f"つまみ（{name}）の先 {tip:.3f} が、枠の外面 {LAY.frame[2]}・基板の縁 {LAY.pcb[2]:.3f} の 1.0 内側に無い")
        env = Pos(*shift) * C.nail_envelope(pos)
        if vol(frame, env) > TOL:
            out.append(f"爪の入る場所（{name}の位置から押す）に枠がある {vol(frame, env):.2f} mm3")
        if vol(others, env) > TOL:
            out.append(f"爪の入る場所（{name}）に基板の上の物がある {vol(others, env):.2f} mm3")
    return out


def test_the_power_knob_stays_inside_the_frame_and_a_fingernail_reaches_it_from_the_top_and_the_side(halves):
    frame = corner_piece(halves)
    assert knob_problems(frame) == []
    # 外の事実: 本体は基板の縁から 2.5（JLC の規約）→ つまみの先は枠の外面から 1.35 内側。行程 1.6 ± 0.2・力は最大 250 gf（承認書）
    for pos in (1, -1):
        b = C.knob_solid(pos).bounding_box()
        assert LAY.frame[2] - b.max.X == pytest.approx(1.35) and LAY.pcb[2] - b.min.X == pytest.approx(S.PSW_EDGE_MIN)
    # 包絡の決め: つまみの脇 3.0・つまみの先から本体の側へ 1.0・行程の公差込みで掃く・枠の上面の 5 上まで
    e = C.nail_envelope(1).bounding_box()
    assert (e.size.Y, e.max.Z) == pytest.approx((S.PSW_NAIL[0] + S.PSW_TRAVEL + S.PSW_TRAVEL_TOL, 10.0)) and e.max.X > LAY.frame[2] + 5
    assert LAY.psw_knob(1)[2] - e.min.X == pytest.approx(S.PSW_NAIL[1])
    # 切り欠きは幅 10・包絡（行程の公差込み）の両側に 0.55 ずつ余る
    n = LAY.psw_notch()
    assert n[-1][1] - n[0][1] == pytest.approx(10.0) and n[-1][1] - C.nail_envelope(1).bounding_box().max.Y == pytest.approx(0.55)
    # 入の印は、つまみを入に寄せた側（奥）の枠の上面にあり、切り欠きの中に落ちていない
    mark = C.corner_cuts()["on_mark"].bounding_box()
    my, mx = (mark.min.Y + mark.max.Y) / 2, (mark.min.X + mark.max.X) / 2
    assert my > S.PSW_AT[1] + S.PSW_TRAVEL / 2 and S.PSW_ON == 1 and n[0][1] < my < n[-1][1]
    top = S.FRAME_UNDER + S.FRAME_T
    assert frame.is_inside((mx + 0.9, my, top - 0.2)) and not frame.is_inside((mx, my, top - 0.2)) and mx < n[0][0] - S.ON_MARK[0] / 2


@pytest.mark.parametrize("kw, word", [
    (dict(shift=(1.75, 0.0, 0.0)), "先"),                                   # 前の位置（1.75 外）: つまみが枠の外へ出る
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
    """切り欠きの内側は、屋根を基板の上 1.8 まで厚くして塞いである（薄い垂れ壁にしない）。指で 10 N 押したときの応力の見積もりが、
    Bambu PLA Basic の TDS の曲げ強さ 76 MPa の半分（積層の向きの弱さを見る）より十分小さい。"""
    got = C.notch_strength()
    assert got["roof_t"] == pytest.approx(3.2) and got["stub_len"] == pytest.approx(7.525)
    assert got["roof"] < got["limit"] / 4 and got["stub"] < got["limit"] / 4, got
    assert C.notch_strength(press=250.0)["roof"] > got["limit"]              # 検査器が生きている
    # 作った枠で: 厚い屋根は切り欠きの内側の面まであり、スイッチの本体の上 0.3 から枠の下面まで詰まっている
    r = C.psw_roof_rect()
    frame = C.frame_halves()["right"] & C._box((r[0] - 1, r[1] - 1, r[2] + 1, r[3] + 1), -1.0, 6.0)
    x, y = r[2] - 0.2, S.PSW_AT[1]
    assert not frame.is_inside((x, y, C.psw_ceiling() - 0.1)) and frame.is_inside((x, y, C.psw_ceiling() + 0.1)) and frame.is_inside((x, y, 4.9))
    assert not frame.is_inside((r[2] + 0.2, y, 2.5))


# ---------------------------------------------------------------------------
# 電池の蓋（差し込み式・枠だけで留まる・利用者の決定 2026-10-04）
# ---------------------------------------------------------------------------

def cover_problems(frame, cover=None, plain=None, shift=(0.0, 0.0, 0.0)):
    """蓋を組んだ位置で: 枠・電池・クリップ・基板・ほかの部品に当たらない・枠の上面と外面から出ない。
    手前へ抜く道（山の無い形を 0.25 おきに動かす）で枠・電池・クリップに当たらない = **入れられる・外せる**。"""
    out = []
    cover = Pos(*shift) * (C.cover_solid() if cover is None else cover)
    plain = Pos(*shift) * (C.cover_solid(False) if plain is None else plain)
    parts = C.board_parts()
    things = {"枠": frame, "電池": C.cell_solid(), "クリップ": parts["BT1"], "基板": C.pcb_solid(),
              "ほかの部品": Compound([v for n, v in parts.items() if n != "BT1"])}
    for name, v in things.items():
        if vol(v, cover) > TOL:
            out.append(f"蓋が{name}に当たる {vol(v, cover):.3f} mm3")
    b = cover.bounding_box()
    f = LAY.frame
    top = S.FRAME_UNDER + S.FRAME_T
    if b.max.Z > top + 1e-6 or b.min.Y < f[1] - 1e-6 or b.min.Z < 0.0:
        out.append(f"蓋が枠の上面・外面・基板の面から出る（上 {b.max.Z:.3f}・手前 {b.min.Y:.3f}・下 {b.min.Z:.3f}）")
    if top - b.max.Z > 0.01 or b.min.Y - f[1] > 0.01:
        out.append(f"蓋が枠の上面・外面と面一でない（上 {b.max.Z:.3f}・手前 {b.min.Y:.3f}）")
    depth = b.size.Y
    for i in range(1, int((depth + 2.0) / 0.25) + 1):
        moved = Pos(0, -0.25 * i, 0) * plain
        for name in ("枠", "電池", "クリップ", "基板"):
            if vol(things[name], moved) > TOL:
                out.append(f"蓋を手前へ {0.25 * i:.2f} 引いた所で{name}に当たる {vol(things[name], moved):.3f} mm3")
                break
    return out


def test_the_battery_cover_slides_in_and_out_and_sits_flush_without_touching_the_cell(halves):
    frame = corner_piece(halves)
    assert cover_problems(frame) == []
    cv = LAY.cover()
    cover = C.cover_solid()
    # 手前の板と、止めに当てた電池の縁の隙 0.51・上の板はクリップの上 4.1 から 0.2・電池の上 3.2 から付け根の下面まで 0.65
    (cx, cy), r = LAY.cell()
    assert (cy - r) - cv["y_front"] == pytest.approx(0.51) and cv["z_plate"] - LAY.z()["clip_top"] == pytest.approx(0.2)
    assert cv["z_root"] - S.CELL_T == pytest.approx(0.65) and LAY.clip_body()[1] - cv["y_root"] == pytest.approx(0.45)
    assert vol(cover, Pos(0, -0.4, 0) * C.cell_solid()) < TOL and vol(cover, Pos(0, -0.6, 0) * C.cell_solid()) > 0.01
    # 蓋は口と切り欠きを塞ぐ: 口の幅 16.6 − 隙 2 × 0.15・切り欠きの奥の壁まで 0.15
    b = cover.bounding_box()
    assert (b.size.X, b.max.Y) == pytest.approx((16.6 - 2 * S.COVER_CLEAR, cv["y1"] - S.COVER_CLEAR))
    # 蓋があると電池は出せない（蓋が道を塞ぐ）・蓋を外せば、道は前と同じ（test_the_battery_slides_out_...）
    assert vol(cover, cell_path()) > 10.0
    # 厚さは増えない
    assert LAY.z()["total"] == pytest.approx(8.1)


def test_the_cover_is_held_by_the_rails_the_back_wall_and_the_detent(halves):
    """留まる向きを 1 つずつ: 上（ひさし）・左右（切り欠きの壁）・奥（切り欠きの奥の壁）・手前（山が溝の手前の肉に掛かる）。"""
    frame = corner_piece(halves)
    plain, cover = C.cover_solid(False), C.cover_solid()
    for name, d in (("上", (0, 0, 0.35)), ("左", (-0.3, 0, 0)), ("右", (0.3, 0, 0)), ("奥", (0, 0.3, 0))):
        assert vol(frame, Pos(*d) * plain) > 0.01, name
    # 遊び: 上へは 0.2 まで（斜めのひさしと蓋の隙 0.15）
    assert vol(frame, Pos(0, 0, 0.1) * plain) < TOL
    # 手前: 山の無い形は素通し（道の検査）。山があると、手前へ引くと溝の手前の肉に当たり、越えるのに腕が掛かり（COVER_BUMP[0]）だけたわむ
    assert vol(frame, cover) < TOL and vol(frame, Pos(0, -0.3, 0) * cover) > 0.001
    by = LAY.cover()["bump"][0][1]
    under_lip = Pos(0, -(by - LAY.frame[1]) + 0.2, 0) * cover                 # 山の頂を、溝の手前の肉の真下へ
    hit = frame & under_lip
    assert hit.bounding_box().size.Z == pytest.approx(S.COVER_BUMP[0], abs=0.02)
    # 溝の手前に残る肉は 0.4（1 本の線の幅）
    g = C.detent_groove()
    lip = min(y for y, z in [(g[0][0] + 0.2 / ((g[2][1] - g[0][1]) / (g[2][0] - g[0][0])), 0)]) - LAY.frame[1]
    assert lip == pytest.approx(0.4, abs=0.02)
    # ばね: ひずみが PLA の許容（spec.PLA_STRAIN_LIMIT・出どころは spec のコメント）の内。引き抜く力の見積もりは 1〜3 N
    sp = C.cover_spring()
    assert sp["strain"] <= S.PLA_STRAIN_LIMIT and sp["strain"] == pytest.approx(0.0087, abs=2e-4) and 1.0 < sp["hold"] < 3.0, sp
    import types
    short = types.SimpleNamespace(**{k: getattr(S, k) for k in dir(S) if k.isupper()})
    short.COVER_ARM = (4.0, 0.7, 0.5)
    assert C.cover_spring(short)["strain"] > S.PLA_STRAIN_LIMIT                # 検査器が生きている: 腕が 4.0 なら超える
    assert S.PLA_STRAIN_LIMIT == 0.01 and 76.0 / 2750.0 * 0.36 == pytest.approx(S.PLA_STRAIN_LIMIT, abs=1e-4)


@pytest.mark.parametrize("kw, word", [
    (dict(shift=(0.0, 0.0, 0.3)), "当たる"),                                 # 0.3 浮いた蓋: ひさしに当たる・上面から出る
    (dict(shift=(0.0, 0.6, 0.0)), "電池"),                                   # 0.6 奥: 電池に当たる
    (dict(shift=(0.4, 0.0, 0.0)), "枠"),                                     # 0.4 右
    (dict(shift=(0.0, -0.3, 0.0)), "外面"),                                  # 0.3 手前へ出ている
    (dict(wide=True), "引いた所"),                                           # 上の板が切り欠きより広い蓋: 道で枠に当たる
])
def test_the_cover_check_notices_a_break(halves, kw, word):
    if kw.pop("wide", False):
        cv = LAY.cover()
        ear = C._box((cv["nx1"] - 0.5, cv["y_root"], cv["nx1"] + 0.6, cv["y1"] - 0.5), cv["z_plate"], cv["z_top"] - 0.1)
        kw = dict(cover=C.cover_solid(), plain=C.cover_solid(False) + Pos(0, -3.0, 0) * ear)
    bad = cover_problems(corner_piece(halves), **kw)
    assert any(word in b for b in bad), bad


def overhangs(part):
    """刷る向きに置いた立体の、45° より寝た下向きの面 [(高さ, 面積)]（ベッドの面は除く）。"""
    out = []
    for f in part.faces():
        try:
            n = f.normal_at()
        except Exception:
            continue
        if n.Z < -0.72 and f.center().Z > 1e-3:
            out.append((round(f.center().Z, 2), round(f.area, 3)))
    return out


def test_the_cover_prints_front_face_down_without_support_and_the_frame_seat_too(halves):
    pr = C.cover_print()
    b = pr.bounding_box()
    assert overhangs(pr) == [] and b.min.Z == pytest.approx(0.0, abs=1e-6) and b.size.Z == pytest.approx(S.FINGER_NOTCH[1] - S.COVER_CLEAR)
    assert len(pr.solids()) == 1 and pr.is_valid
    # 検査器が生きている: 上面をベッドに置くと、手前の板の腕の隙間・付け根の下面が宙に浮く
    assert overhangs(P.flip_to_bed(C.cover_solid()))
    # 枠（上面をベッドに）: ひさし・山の溝・厚い屋根・切り欠きを足しても、宙に浮く面は前と同じ（test_the_frame_prints_top_down_without_support）。
    # 斜めの面（ひさし 40.6°・溝 45°）も、刷る向きで下を向かない
    assert overhangs(P.flip_to_bed(corner_piece(halves))) == [] or all(z < 0.5 for z, _ in overhangs(P.flip_to_bed(corner_piece(halves))))
    # 腕は、刷る向きではベッドの面の中で曲がる（積層を剥がす向きに曲げない）: 腕の長い向きは x・たわむ向きは z（使う向き）= 刷る向きの y
    assert S.COVER_ARM[1] <= 1.0 and S.COVER_FRONT_T >= 1.0


# ---------------------------------------------------------------------------
# 角の試し刷り（coupon_corner）: 本番の枠から切り出した物か・代わりの物が本物と同じ所にあるか
# ---------------------------------------------------------------------------

def test_the_corner_coupon_is_cut_from_the_real_frame_and_its_stand_ins_sit_where_the_real_parts_do():
    cc = C.corner_coupon()
    assert set(cc) == {"frame", "base", "knob", "cell", "cover"}
    box = C.corner_coupon_box()
    top = S.FRAME_UNDER + S.FRAME_T
    real = C.frame_full() & C._box(box, -1.0, top + 1.0)
    extra, missing = cc["frame"] - real, real - cc["frame"]
    wall = C._box((box[0], LAY.key_area[1] - 0.01, box[0] + S.COUPON_CORNER_WALL, box[3]), 0.0, S.FRAME_UNDER + 0.01)
    assert missing.volume < TOL and 50 < extra.volume < 90 and vol(extra, wall) == pytest.approx(extra.volume, abs=0.01)
    # 切れ端には、つまみの切り欠き・電池の口・蓋の座・ねじ H15 の下穴が入っている
    n = LAY.psw_notch()
    assert box[1] < n[0][1] and n[-1][1] + 1.0 < box[3] and box[0] < LAY.cover()["x0"] - 5.0
    h15 = next(c for ref, c, _ in LAY.screws() if ref == "H15")
    assert not cc["frame"].is_inside((*h15, 1.0)) and cc["frame"].is_inside((*h15, S.SCREW_PILOT_DEPTH + 0.3))
    # 当て板: 基板と同じ厚さ・右と手前の縁は基板の縁・ねじ穴 3 つ（H15 と蓋の 2 つ）は本番の位置
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
    # 電池の代わり: φ16 × 3.2・止めに当てた位置で、当て板の止めに 0〜0.01 で触れ、案内の間（隙 0.15）にいる。クリップの代わりは枠に当たらない
    cb = cc["cell"].bounding_box()
    assert (cb.size.X, cb.size.Z) == pytest.approx((S.CELL_D, S.CELL_T)) and vol(cc["cell"], base) < TOL
    assert vol(Pos(0, 0.3, 0) * cc["cell"], base) > 0.01 and vol(Pos(0.3, 0, 0) * cc["cell"], base) > 0.01
    assert vol(cc["frame"], base) < TOL and vol(cc["cover"], base) < TOL and vol(cc["cover"], cc["frame"]) < TOL
    # 電池の代わりは、当て板の上を口から出し入れできる
    assert vol(cell_path(), base) < TOL and vol(cell_path(), cc["frame"]) < TOL
    # 蓋は本番と同じ物
    assert cc["cover"] is C.cover_solid()
    plate = C.corner_coupon_plate()
    size = plate.bounding_box().size
    assert len(plate.solids()) == 5 and max(size.X, size.Y) <= 80 and plate.bounding_box().min.Z == pytest.approx(0.0, abs=1e-6)


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
