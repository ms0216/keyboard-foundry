# 引き継ぎ（cckb）

> **2026-09-24 時点の要約。**基板は配線まで済み（DRC 違反 0・未配線 0・警告 5）。発注前の人の確認
> （JLC の配置プレビュー・ピン配置の独立確認）と、起動試験（#1）・ケース（#3）が残る。
> 基板の詳細は [pcb-routing-handover.md](pcb-routing-handover.md)。

## いまの状態

| 板 / 部品 | 状態 | 何で確かめたか |
|---|---|---|
| 基板 `pcb/cckb_main.kicad_pcb` | 配線済み・発注データを出して読んだ | DRC（kicad-cli）・tests/test_cckb_pcb.py・Fabrication Toolkit の出力 |

## 現行の手順

    tools/kb cckb plate
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
