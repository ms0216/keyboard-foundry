"""スライスした G-code の層を絵にする（cckb-click）。**形を決めた狙いが、実際の線になっているかを見る。**

    tools/kb cckb-click slice --printer a1mini          # 先に
    .venv/bin/python3 projects/cckb-click/tools/draw_slice_layers.py

見るもの（build/cckb-click/slice_layers.png）:
  - キャップ（下面がベッド）: 1 層目（下の縁の面取りで引っ込む）・2 層目（つばの上面 = 掛かる面）・3 層目（つばが無くなる）
  - 枠（上面がベッド）: くぼみの高さの層（隣のくぼみとの間の壁 0.8 に線が出ているか）・枠の下面の層・柱の層
G-code は相対押し出し（M83）。押し出しのある G1 だけを線にする。
"""

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "build" / "cckb-click"
COLORS = {"Outer wall": "#c0392b", "Inner wall": "#e08e0b", "Gap infill": "#8e44ad"}


def layers(gcode):
    """層の高さ → [(x0, y0, x1, y1, 種類)]。"""
    out, z, feat, x, y = {}, None, "", None, None
    num = re.compile(r"([XYZE])(-?\d*\.?\d+)")
    for line in gcode.read_text(errors="replace").splitlines():
        if line.startswith("; Z_HEIGHT:"):
            z = round(float(line.split(":")[1]), 3)
        elif line.startswith("; FEATURE:"):
            feat = line.split(":", 1)[1].strip()
        elif line.startswith(("G1 ", "G0 ", "G2 ", "G3 ")):
            v = dict(num.findall(line.split(";")[0]))
            nx, ny = float(v.get("X", x or 0)), float(v.get("Y", y or 0))
            if z is not None and x is not None and float(v.get("E", 0)) > 0 and ("X" in v or "Y" in v):
                out.setdefault(z, []).append((x, y, nx, ny, feat))
            x, y = nx, ny
    return out


def draw(ax, segs, title, window=None):
    for x0, y0, x1, y1, feat in segs:
        ax.plot([x0, x1], [y0, y1], "-", color=COLORS.get(feat, "#7f8c8d"), lw=1.1)
    if window:
        ax.set_xlim(window[0], window[1])
        ax.set_ylim(window[2], window[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.grid(True, lw=0.2)


def main():
    cap = sorted((BUILD / "slice" / "a1mini" / "coupon_b_caps").glob("*.gcode"))
    frame = sorted((BUILD / "slice" / "a1mini" / "coupon_b_frame").glob("*.gcode"))
    if not cap or not frame:
        print("NG G-code が無い。先に tools/kb cckb-click slice --printer a1mini")
        return 1
    lc, lf = layers(cap[-1]), layers(frame[-1])
    fig, axs = plt.subplots(2, 3, figsize=(16, 10.5))
    # キャップ 1 個の左手前の角（最初の層の線の左下から 6 mm 角）
    walls = [s for s in lc[0.4] if s[4] == "Outer wall"]          # スカート（捨て線）を除いて、物の外周から窓を決める
    x0, y0 = min(((s[0], s[1]) for s in walls), key=lambda p: p[0] + p[1])      # いちばん左手前のキャップの角（並べ方で向きが変わる）
    win = (x0 - 2.5, x0 + 5.0, y0 - 2.5, y0 + 5.0)
    for ax, z, t in zip(axs[0], (0.2, 0.4, 0.6), ("1 層目（ベッドの面 = 押す面。縁は面取りで内へ）", "2 層目（上面がつばの上面 = 掛かる面）",
                                                   "3 層目（つばが無くなり胴だけ）")):
        draw(ax, lc[z], f"キャップ z={z}: {t}", win)
    # 枠の、穴と穴の間（最初のリブ）。枠は上面がベッドなので z=1.6 がくぼみの中、2.0 が枠の下面、3.0 は柱と壁だけ
    fwalls = [s for s in lf[3.0] if s[4] == "Outer wall"]
    fx0 = min(min(s[0], s[2]) for s in fwalls)
    fy0 = min(min(s[1], s[3]) for s in fwalls)
    fwin = (fx0 + 15.0, fx0 + 28.0, fy0 - 1.0, fy0 + 12.0)
    for ax, z, t in zip(axs[1], (0.8, 1.6, 3.0), ("くぼみの底（1.0）の下。まだ枠の厚み", "くぼみの中（隣のくぼみとの間の壁 0.8 に線があるか）",
                                                   "枠の下面より上: 柱と外周の壁だけ")):
        draw(ax, lf[z], f"枠 z={z}: {t}", fwin)
    fig.suptitle("スライスした線（A1 mini・0.20mm Standard・OrcaSlicer の CLI）。赤 = 外周・橙 = 内周・紫 = すき間埋め・灰 = そのほか。"
                 "1 目盛 1 mm", fontsize=11)
    fig.tight_layout()
    out = BUILD / "slice_layers.png"
    fig.savefig(out, dpi=100)
    print(f"OK {out}  キャップ {len(lc)} 層・枠 {len(lf)} 層")
    return 0


if __name__ == "__main__":
    sys.exit(main())
