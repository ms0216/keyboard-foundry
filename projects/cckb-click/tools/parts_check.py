"""cckb-click の JLC の部品を、発注の直前に確かめ直す: 在庫・区分・単価（JLC の検索 API）と、実装の種類（部品ページの PCBA Type）。

    .venv/bin/python3 projects/cckb-click/tools/parts_check.py

`tools/kb cckb-click parts`（foundry.jlcpcb_lookup）は在庫・区分・単価まで。**Economic で載るか**は検索 API に無いので、
部品ページ https://jlcpcb.com/partdetail/<C 番号> の「PCBA Type」を読む。各行の頭に OK / NG。出力を捨てない。
読めなかったら NG（「たぶん大丈夫」にしない）。それでも最後は注文画面で見る（docs/order-steps.md）。
"""

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from foundry.jlcpcb_lookup import classify, price_at, search  # noqa: E402
from foundry.project import load  # noqa: E402

# 1 台ぶん（JLC の実装は最小 2 枚）の数
QTY = {"keyswitch": 62, "diode": 62, "schottky": 1, "74LVC595": 2, "cap_100n": 2, "res_1M": 2, "coin_clip": 1, "power_switch": 1}
BOARDS = 2


def pcba_type(code):
    r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", f"https://jlcpcb.com/partdetail/{code}"],
                       capture_output=True, text=True)
    m = re.search(r"PCBA Type(?:<[^>]*>|\s)*([A-Za-z ]+?)\s*<", r.stdout)
    return m.group(1).strip() if m else None


def main():
    spec = load(HERE.parent).spec
    bad = 0
    seen = {}
    for kind, part in sorted(spec.PARTS.items()):
        code = part["lcsc"]
        n = QTY[kind] * BOARDS
        if code in seen:                       # 同じ品（ダイオードと D_PWR）は数を足して 1 回
            seen[code][1] += n
            continue
        seen[code] = [kind, n]
    for code, (kind, n) in seen.items():
        rows = [c for c in search(code, 5) if c.get("componentCode") == code]
        if not rows:
            print(f"NG {code}（{kind}）: 検索に出ない")
            bad += 1
            continue
        c = rows[0]
        stock = c.get("stockCount") or 0
        kind_pcba = pcba_type(code)
        price = price_at(c, n)
        ok = stock >= n * 3 and kind_pcba is not None and "Economic" in kind_pcba
        bad += not ok
        print(f"{'OK' if ok else 'NG'} {code} {c.get('componentModelEn')}（{kind}）: {classify(c)}・在庫 {stock:,}・"
              f"{n} 個で ${price} × {n} = ${price * n if price else '?':.2f}・PCBA Type: {kind_pcba}")
    print("NG" if bad else "OK", f"問題 {bad} 件（在庫が要る数の 3 倍未満・Economic で載らない・読めない）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
