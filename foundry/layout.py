"""KLE JSON を読み、キーごとの実寸座標（mm）に変換する。**配列の唯一の入口。**

プレート・基板・ファームウェアはすべてここを経由する。配列を変えれば全部が追従する。

KLE の書式で押さえるべき点:
  - 行は配列。文字列がキー、辞書は「次のキーに適用する属性」
  - `x` / `y` は「現在位置からの相対移動」で、累積する
  - `w` / `h` は **そのキー1つだけ** に効き、キーを置くと 1 に戻る
  - 先頭のメタデータ辞書（行ではなく単独の辞書）は読み飛ばす

**扱わないもの（読んだら落とす）:** 回転（r / rx / ry）と ISO 型の
2 矩形キー（x2 / w2 など）。黙って無視すると、座標のずれた基板が
何も言わずに出来上がる。必要になった機種で実装する。

KiCad の Python（3.9）からも import されるので、標準ライブラリだけで書く。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

UNIT = 19.05
UNSUPPORTED = ("r", "rx", "ry", "x2", "y2", "w2", "h2")


@dataclass(frozen=True)
class Key:
    """キー1つ。座標はキー中心、原点は配列の左上、Y は下向きが正。"""

    x_mm: float
    y_mm: float
    w_u: float
    h_u: float
    label: str

    @property
    def w_mm(self) -> float:
        return self.w_u * UNIT

    @property
    def h_mm(self) -> float:
        return self.h_u * UNIT

    @property
    def left_u(self) -> float:
        return self.x_mm / UNIT - self.w_u / 2

    @property
    def right_u(self) -> float:
        return self.x_mm / UNIT + self.w_u / 2


def load_layout(path) -> list[Key]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    keys: list[Key] = []
    y = 0.0
    for row in raw:
        if not isinstance(row, list):
            continue                      # 先頭のメタデータ辞書
        x = 0.0
        w = h = 1.0
        for item in row:
            if isinstance(item, dict):
                bad = sorted(set(item) & set(UNSUPPORTED))
                if bad:
                    raise ValueError(
                        f"{path}: KLE の {bad} は未対応（回転・ISO キー）。"
                        "黙って無視すると座標のずれた基板ができるので止める")
                x += float(item.get("x", 0))
                y += float(item.get("y", 0))
                w = float(item.get("w", 1))
                h = float(item.get("h", 1))
                continue
            # KLE のラベルは "\n" 区切りで複数の刻印を持つ。先頭（左上）を使う
            keys.append(Key(x_mm=(x + w / 2) * UNIT, y_mm=(y + h / 2) * UNIT,
                            w_u=w, h_u=h, label=str(item).split("\n")[0]))
            x += w
            w = h = 1.0                   # 属性は1キーで失効する
        y += 1.0
    return keys


def bounds_mm(keys: list[Key]) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) をキーの外形で返す。"""
    return (
        min(k.x_mm - k.w_mm / 2 for k in keys),
        min(k.y_mm - k.h_mm / 2 for k in keys),
        max(k.x_mm + k.w_mm / 2 for k in keys),
        max(k.y_mm + k.h_mm / 2 for k in keys),
    )


def islands(keys: list[Key], gap_u: float = 1.0) -> list[list[Key]]:
    """x 方向に gap_u 以上離れた島へ分ける（左から順）。一体型なら 1 つ。

    分割機の KLE は左右を離して置くので、その空きで切る。
    """
    ordered = sorted(keys, key=lambda k: k.left_u)
    out = [[ordered[0]]]
    reach = ordered[0].right_u
    for k in ordered[1:]:
        if k.left_u - reach >= gap_u:
            out.append([])
        out[-1].append(k)
        reach = max(reach, k.right_u)
    return out


def keymap_order(keys: list[Key]) -> list[Key]:
    """キーマップの並び順（上の段から、段の中は左から）に並べ替える。

    **islands は x 順で返す。**そのまま行列表と突き合わせると全キーの
    割り当てを取り違える（HHKB で 61 キー全部を取り違え、しかも期待値にも
    同じ誤った並びを使っていたので検査が通った）。突き合わせる前に必ず通す。
    """
    return sorted(keys, key=lambda k: (round(k.y_mm, 2), k.x_mm))


def centered(keys: list[Key]) -> tuple[list[tuple[float, float]], tuple[float, float]]:
    """キー中心を CAD 座標（キー領域の中心が原点・Y 上向き）に直す。

    返り値は (位置の並び, キー領域の幅・奥行)。プレート・基板・ケースが
    すべてこの 1 つの関数を使う。座標変換を複数箇所に書くとずれる。
    """
    x0, y0, x1, y1 = bounds_mm(keys)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [(k.x_mm - cx, cy - k.y_mm) for k in keys], (x1 - x0, y1 - y0)
