"""キー配置から行列（row, col）の割り当てを計算する。

**基板とファームウェアは同じ割り当てを使う。**片方だけ直すとキーが入れ替わる。
生成はここ 1 か所で行い、基板（pcb.py）とシールド（zmk.py）の両方がここを読む。
KiCad の Python（3.9）からも import されるので標準ライブラリだけ。
"""

from __future__ import annotations

from .layout import keymap_order


def assignments(keys, columns="physical"):
    """キーを keymap_order に並べ、各キーの (row, col) を同じ順で返す。

    columns="ordinal" は「段の中で左から何番目か＝列番号」。HHKB の右半分は
    利用者がこちらを選んだ（素直で、配線は扇形で吸収した）。

    **列は「段の中で何番目か」ではなく、物理的な x で決める。**番号で割り当てると
    キー数が違う段（最下段）で、同じ列のキーが物理的に大きく離れる
    （HHKB で 38mm の横断配線になった）。キー数が最も多い段を基準の列とし、
    各段のキーを x 順・単調増加で最も近い列へ割り当てる（単調なので交差しない）。

    **これは初期値にすぎない。**HHKB では利用者が最下段を「一番左のキーに一番左の列」
    へ直した。直したい場合は spec.MATRIX_OVERRIDE に {キーの順番: (row, col)} を書く。
    """
    keys = keymap_order(keys)
    rows = {}
    for k in keys:
        rows.setdefault(round(k.y_mm, 2), []).append(k)
    ys = sorted(rows)
    ref = sorted(max(rows.values(), key=len), key=lambda k: k.x_mm)
    out = {}
    for r, y in enumerate(ys):
        row = sorted(rows[y], key=lambda k: k.x_mm)
        if columns == "ordinal":
            out.update((id(k), (r, c)) for c, k in enumerate(row))
            continue
        if columns != "physical":
            raise ValueError(f"columns は physical / ordinal（{columns!r}）")
        c_prev = -1
        for i, k in enumerate(row):
            hi = len(ref) - (len(row) - i - 1)
            best = min(range(c_prev + 1, hi), key=lambda c: abs(ref[c].x_mm - k.x_mm))
            out[id(k)] = (r, best)
            c_prev = best
    return keys, [out[id(k)] for k in keys]


def shape(rc):
    """(行数, 列数)。"""
    return max(r for r, _ in rc) + 1, max(c for _, c in rc) + 1
