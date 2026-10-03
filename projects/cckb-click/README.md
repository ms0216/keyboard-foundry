# cckb-click

CCKB（HHKB 英語配列・62 キー・19.05 ピッチ・XIAO nRF52840）を、**薄い表面実装のタクトスイッチ**と
**枠の下から入れる軸の無いキーキャップ**で作り直す機種。目標の厚さは約 8.1 mm（CCKB は 14.2）。
方式は Salicylic_acid3 さんの ClickBoard（出どころと条件は [LICENSE](LICENSE)。**非営利に限る**）。

`projects/cckb/`（発注できる状態の CCKB）には手を入れない。だめなら CCKB に戻れる。

## いまの段: 刷るだけの試し（基板なし）

基板を設計する前に、キャップと枠を刷って触り、形を決める。

```
.venv/bin/python3 projects/cckb-click/click_coupons.py     # STL（最小の一式 ＋ あとで刷る 14 個）・断面図・上から見た図・.blend を build/cckb-click/ に
.venv/bin/python3 projects/cckb-click/tools/slice_precise.py   # 最小の一式を精度優先の設定でスライスし、G-code を検査（時間・材料・継ぎ目の場所）
.venv/bin/pytest tests/test_cckb_click.py -q                # 形の検査
```

| 読むもの | 何 |
|---|---|
| [docs/coupon-test.md](docs/coupon-test.md) | **試し刷りの手順と記入表**（最初に刷る 1 枚・刷り方・測る表・結果の意味） |
| print/ | 精度優先の刷り方のプリセット（0.4 ノズル用・0.2 ノズル用。Bambu Studio / OrcaSlicer に読み込む） |
| [docs/open-gaps.md](docs/open-gaps.md) | 決まったこと・試し刷りが決めること・基板が来るまで分からないこと |
| [docs/decisions/](docs/decisions/) | スイッチ・構造（積み上げと刷る向き）・ライセンスの決定 |
| [docs/provisional-values.md](docs/provisional-values.md) | まだ実測していない値（`[暫定]`） |
| spec.py | 寸法（積み上げ・穴・隙・つば）。値ごとに出どころ |

## 状態（2026-10-03）

| | |
|---|---|
| 配列 | CCKB と同じ（layout.json） |
| スイッチ | Alps SKRAAWE010（JLC C202383）に決定。基板は SKRACAE010 も載る足跡にする（基板の段） |
| 積み上げ | 基板の上面 0 / 枠の下面 3.0 / 掛かる面 4.0 / 押す面 3.6 / 枠の上面 5.0 / キャップの上面 6.0 `[暫定]` |
| キャップと枠 | 形は作った（click_parts.py）。**まだ刷っていない** |
| 試し刷り | 最小の一式（1 枚・0.4 ノズルで約 45 分）を、精度優先の設定で Bambu Studio と OrcaSlicer の両方でスライスし、G-code を検査した。**まだ刷っていない。**刷るかは利用者の判断 |
| 基板・ファーム・ケース | 未着手（試し刷りの結果を見てから）。`tools/kb cckb-click plate / pcb / zmk` はまだ動かない |
