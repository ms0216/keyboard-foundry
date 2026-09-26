# 引き継ぎ（cckb）

> **2026-09-25 時点の要約。**基板は配線まで済み（DRC 違反 0・未配線 0・警告 3）。電源スイッチは 2026-09-24 に
> SS-12D00G3（表・右のふたの穴から爪で）へ置き換えた（[decisions/2026-09-24-power-switch.md](decisions/2026-09-24-power-switch.md)）。
> ケース（#3）は閉じた。発注前に残るのは起動試験（#1）と人の確認（#4: JLC の配置プレビュー・ピン配置の独立確認）。
> **いまの状態の正本は [status.md](status.md)**、基板の詳細は [pcb-routing-handover.md](pcb-routing-handover.md)。
> この文書の下の表は書きかけのまま（上の 2 つを読む）。

## いまの状態

| 板 / 部品 | 状態 | 何で確かめたか |
|---|---|---|
| 基板 `pcb/cckb_main.kicad_pcb` | 配線済み・発注データを出して読んだ | DRC（kicad-cli）・tests/test_cckb_pcb.py・Fabrication Toolkit の出力 |

## 現行の手順

    tools/kb cckb plate            # 2026-09-26 からプレートは使わない（spec.PLATE = False）。build/cckb/plate_optional/ に出る
    tools/kb cckb pcb
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py
    tools/kb cckb fab-fields
    tools/kb cckb drc
    tools/kb cckb zmk
    .venv/bin/pytest tests -q

## 機械で守っていること

| 検査 | 守るもの |
|---|---|

## やめた方式とその理由

## やってはいけないこと

## 次にやること（済んだものは取り消し線で残す）
