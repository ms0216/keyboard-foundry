# cckb-click

CCKB（HHKB 英語配列・62 キー・19.05 ピッチ・XIAO nRF52840）を、**薄い表面実装のタクトスイッチ**と
**枠の下から入れる軸の無いキーキャップ**で作り直す機種。目標の厚さは約 8.1 mm（CCKB は 14.2）。
方式は Salicylic_acid3 さんの ClickBoard（出どころと条件は [LICENSE](LICENSE)。**非営利に限る**）。

`projects/cckb/`（発注できる状態の CCKB）には手を入れない。だめなら CCKB に戻れる。

## いまの段: 基板・枠・キャップ・ファームまで設計した（独立した監査の前）

**いまの状態は [docs/status.md](docs/status.md)。**残っているものは [docs/open-gaps.md](docs/open-gaps.md) の冒頭。

```
tools/kb cckb-click pcb                                            # 未配線の板
"$KICAD_PYTHON" projects/cckb-click/tools/route_click.py           # 配線（Freerouting 2.3.0 と java が要る）
tools/kb cckb-click fab-fields && tools/kb cckb-click drc          # LCSC の番号・DRC
.venv/bin/python3 projects/cckb-click/click_case.py                # 枠・キャップの STL・断面図・.blend を build/cckb-click/ に
.venv/bin/python3 projects/cckb-click/tools/slice_main.py          # 刷る 4 枚をスライスして G-code を検査
.venv/bin/python3 projects/cckb-click/click_stiffness.py           # たわみの見積もり
.venv/bin/python3 projects/cckb-click/tools/parts_check.py         # 部品の在庫・単価（JLC の API）
.venv/bin/pytest tests/test_cckb_click.py tests/test_cckb_click_pcb.py tests/test_cckb_click_board.py tests/test_cckb_click_case.py -q
tools/kb cckb-click gate                                           # 発注の門（いまは閉）
```

| 読むもの | 何 |
|---|---|
| [docs/status.md](docs/status.md) | **いまの状態**・CCKB との比較・利用者が決めること |
| [docs/open-gaps.md](docs/open-gaps.md) | 発注を止めているもの・実物が来るまで分からないこと |
| [docs/decisions/](docs/decisions/) | 決定の記録（スイッチ・構造・刷り方・試し刷りの結果・基板と枠） |
| [docs/shopping-list.md](docs/shopping-list.md)・[docs/order-steps.md](docs/order-steps.md) | 買う物・基板の頼み方 |
| [docs/printing-guide.md](docs/printing-guide.md)・[docs/assembly-guide.md](docs/assembly-guide.md) | 刷り方・組み立て |
| [docs/coupon-test.md](docs/coupon-test.md) | 試し刷りの手順と結果（2026-10-03 に利用者が刷った） |
| print/ | 精度優先の刷り方のプリセット |
| [docs/provisional-values.md](docs/provisional-values.md) | まだ実測していない値（`[暫定]`） |
| spec.py | 寸法と部品。値ごとに出どころ |
