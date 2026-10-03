# 基板を JLCPCB に頼む手順（cckb-click）

**結論: 基板のデータは出来ている（DRC 違反 0・未配線 0・警告 0）。ただし発注の門は閉じている——独立した監査（#30）・人の確認（#31）・
CR1632 の起動試験（#32）が残っている。全部閉じてから、ZIP・BOM・CPL を上げ、下の表のとおりに選び、配置のプレビューで部品の向きを見てから払う。**

    tools/kb cckb-click gate        # いまは「閉 — #30・#31・#32」

## §1 頼む前に閉じるもの

| 順 | 何 | どうやって閉じるか |
|---|---|---|
| 1 | 独立した監査（#30） | 監査の指摘を直す。基板を直したら配線し直す（下の §2 の最初の 4 行） |
| 2 | CR1632 で起動できるか（#32） | projects/cckb/docs/task-10a-coin-cell-startup.md（CCKB と同じ回路なので同じ試験。買う物なし） |
| 3 | 在庫 | `.venv/bin/python3 projects/cckb-click/tools/parts_check.py` が「OK 問題 0 件」 |
| 4 | 利用者の決定 | 基板の表面処理（下の表）・予備のスイッチの数 |
| 5 | 人の確認（#31） | 下の §3 |

## §2 発注ファイルを出す

    tools/kb cckb-click pcb                                              # 未配線の板
    "$KICAD_PYTHON" projects/cckb-click/tools/route_click.py             # 配線（約 3 分。Freerouting 2.3.0 と java が要る）
    tools/kb cckb-click fab-fields                                       # LCSC の番号を板に焼く
    tools/kb cckb-click drc                                              # 違反 0・未配線 0・警告 0
    REQUIRE_KICAD=1 .venv/bin/pytest tests/test_cckb_click_board.py -q   # 板の検査（発注道具の出力まで）
    cd ~/Documents/KiCad/10.0/3rdparty/plugins
    "$KICAD_PYTHON" -m com_github_bennymeg_JLC-Plugin-for-KiCad.cli \
      -p "<リポジトリの絶対パス>/projects/cckb-click/pcb/cckb-click_main.kicad_pcb" -t -nI -nB

`$KICAD_PYTHON` は /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9。
ファイルは `projects/cckb-click/pcb/production/` に出る（git に入れない。頼む直前に出し直す）。

| 上げるファイル | 中身（検査が毎回確かめる） |
|---|---|
| `production/cckb-click_main.zip` | ガーバー（銅 2 層・マスク・ペースト・シルク・外形・ドリル） |
| `production/bom.csv` | 7 行: C202383 ×62・C54110 ×63・C52287685 ×2・C49678 ×2・C17514 ×2・C20606805 ×1・C431540 ×1 |
| `production/positions.csv` | **133 行・全部 top** |

**入っていないのが正しい物**: XIAO（手はんだ）・幅の広いキーの空きランド 22 個（SWA*・SWB*）・試験用のランド TP_VSW・ねじの穴。

### JLCPCB の注文画面で選ぶもの

| 項目 | 選ぶ値 | なぜ |
|---|---|---|
| Layers | 2 | |
| Dimensions | 自動で 291.15 × 100.65 mm と出るはず | 違ったら ZIP の外形を疑う |
| PCB Thickness | **1.6** | 高さの積み上げ（8.1）と、ねじ M2×4 の掛かりがこの厚さ |
| Surface Finish | **利用者が決める**: HASL（安い。電池の −が当たる裸の銅は、はんだめっきの面になる）か ENIG（高い。平らで金。電池の接触とスイッチの座りに良い） | open-gaps D2・P10 |
| Outer Copper Weight | 1 oz | |
| Via Covering | Tented（既定） | |
| Remove Order Number | Yes | 番号を刷らせない |
| **PCB Assembly** | オン・**Economic**・**Top Side**・数量 2 | 部品は全部表。Economic は片面だけ・基板 0.8〜1.6 mm（JLC の PCB Assembly Capabilities） |
| Tooling holes | Added by JLCPCB | 位置は下の §3 で見る |
| Confirm Production file / Confirm Parts Placement | **Yes**（両方） | §3 のため |

## §3 払う前に、配置のプレビューで見ること（#31）

機械で確かめたのは「発注道具が出した CPL の位置と回転で、JLC の部品データのパッドが板の同じ番号のパッドに 0.15 以内で載る」こと（133 個）。
**JLC の画面で実際にそう置かれるかは、人が見る。**

| 見る所 | 正しい姿 | 違ったら |
|---|---|---|
| ダイオード 63 個の帯（カソードの印） | キーの 62 個は帯が**左**（スイッチの手前・横向き）。D_PWR（左 Shift の左上）も帯が左 | 払わずに Claude に言う |
| 595 ×2（左 Shift の中） | 1 番ピンの丸が**右上**（奥の列の右端） | 同上 |
| 電源スイッチ（右の縁） | つまみが**基板の外向き（右）**。本体が基板の縁から少し内側・つまみだけ縁の外へ 0.7 | 同上 |
| 電池クリップ（右の手前） | 口（丸くえぐれた側）が**手前**・折り返しの止めが奥 | 同上 |
| スイッチ 62 個 | ランド 4 つの真ん中に、回っていない | 同上 |
| JLC が足した位置決めの穴（φ1.152 を隅に 2〜3 個） | 銅・部品・ねじの穴に掛かっていない | 位置を変えてもらう |

**JLC に聞かれうること・断られうること**

| 何 | こうする |
|---|---|
| 電源スイッチ MSK12C02 が基板の縁から 0.7 はみ出す（つまみ）。「縁からはみ出す部品は載せられない」と言われたら | その 1 個を実装から外して（BOM の行を消す）、届いてから手はんだ（7 か所。C431540 を LCSC か国内で 1 個買う）。**基板は変わらない** |
| 電池クリップ MY-1632-03-R（背 4.0）を Economic で載せられないと言われたら | Standard にするか、手はんだ（＋のランド 2 か所） |
| スイッチのはんだの量（Alps の仕様書 10.3(8) はペーストの厚さ 0.15 を勧める。**JLC のステンシルの厚さは調べていない**） | 届いたら、スイッチの端子にはんだが上がっているかをルーペで見る。足りなければランドにはんだを足す |
| 空きランド（はんだの載らない 22 か所 × 4 パッド）と TP_VSW に「部品が無い」と言われたら | そのとおり（載せない） |
