# 基板を JLCPCB に頼む手順（CCKB）

**結論: 基板のデータは出来ている。頼む前に利用者がやることが 6 つ残っている（下の §1）。
全部済んだら、ZIP・BOM・CPL の 3 ファイルを JLCPCB に上げ、下の表のとおりに選び、配置のプレビューで
部品の向きを 5 か所見てから払う。**

- 発注の門: `tools/kb cckb gate` がいま「**閉 — #1・#4**」を出す（2026-09-24）。#1 と #4 を閉じると「開」になる
- 発注前の確認表の正本は [fab-checklist.md](fab-checklist.md)。この文書はそれを**上から順にやる手順**にしたもの
- 買う物は [shopping-list.md](shopping-list.md)、組み立ては [assembly-guide.md](assembly-guide.md)

---

## §1 頼む前に閉じるもの（この順で）

**先に LCSC・秋月電子・遊舎工房に部品を頼む**（[shopping-list.md](shopping-list.md) §1・§3・§4）。下の 1〜3 は届いた部品で確かめる。

| 順 | 何（台帳の番号） | どうやって閉じるか | 駄目だったら | 決めないとどうなるか（既定） |
|---|---|---|---|---|
| 1 | **CR1632 で起動できるか**（open-gaps **#1**・門を止めている） | [task-10a-coin-cell-startup.md](task-10a-coin-cell-startup.md) を上から。ブレッドボードで XIAO 単体に抵抗 0/25/50/75Ω を挟み、常温と冷蔵で各 10 回。**BAT46W と B5819W の両方で**測る。合格の基準は手順書 §6（常温 0・25・50Ω と冷蔵 0・25Ω が全部 10/10）。所要 約 2 時間 | CR2032 に替える判断を Claude に返す（ホルダ・右の角の設計をやり直す。基板も変わる） | 門が開かない（発注できない） |
| 2 | **D_PWR の品番**（open-gaps **O12**） | 1 の結果を見て決める。既定の **BAT46W（C54110）** は USB 給電中に電源 ON でも 25℃ では電池へ逆流しない（データシートの保証値）。**B5819W（C8598）** は Basic だが保証が無く、典型で 25℃ でも電池へ数 µA。比べた表は [decisions/2026-09-24-audit-fixes.md](decisions/2026-09-24-audit-fixes.md) §S2 | B5819W にするなら Claude に言う（`spec.PARTS["schottky"]` の 1 行と D_PWR の値を替えて BOM を出し直す。板の銅は変わらない）。あわせて「ケースの USB の口の近くに OFF の刻印を足すか」（open-gaps A8） | **BAT46W のまま**頼まれる。困るのは「1 で BAT46W だけ起動の余裕が足りなかった」場合だけ |
| 3 | **電源スイッチ SS-12D00G3 の入の向きと高さ**（open-gaps **P5**・**O13**） | 届いた 1 個で: (a) レバーを片側へ寄せ、テスターで真ん中の足と**レバーの側の端の足**が導通するか（図面の読み）。(b) **基板の厚さをノギスで測る**（公称 1.6）。足を基板の端材か厚紙（実測した厚さの物）に差し込んで押し付け、**板の上面からレバーの先まで**をノギスで測り、**7.0 −（測った基板の厚さ − 1.6）未満**か確かめる（基板厚が公称どおりなら名目 6.9 ＝ 爪 0.4 ＋ 本体 3.5 ＋ レバー 3.0 で 7.0 未満ならふたの上面から出ない） | (a) が逆なら、ふたの刻印の向き（`spec.PSW_ON`）を反対にする（**板は変わらない**。足が対称で、どちらの端の足を入にしても向きは同じ）。(b) が閾値以上なら O13 の選択肢を Claude に言う | (a) 図面の読みのまま刷られる。逆なら刻印と逆の向きが入になる（壊れない）。(b) レバーの先がふたの上面から最大 0.36 出る（本体・レバー・基板の厚さの公差を積んだ最悪） |
| 4 | **スタビのワイヤがプレートの上か下か**（open-gaps **P11**） | 届いた Choc スタビを 1 組見て、ワイヤがハウジングの上面の側（キャップ側）に付くか。上なら何もしない | 下なら Claude に言う（基板のスタビの逃げ穴を広げる。**基板の変更**） | 「上」と読んで頼まれる（一次資料では未確認） |
| 5 | **アンテナのまわりを ¥0 で 1 回測る**（open-gaps **P7**・強く勧める） | [docs/knowledge/rf-antenna.md](../../../docs/knowledge/rf-antenna.md) の手順。XIAO の手前と奥をアルミ箔で覆い、M2 ネジ 1 本を H3 の位置に置いて、スマホの nRF Connect で RSSI を覆う前と比べる | 20dB 以上悪くなったら Claude に言う（基板の改版） | 試作で RSSI を見るまで分からない |
| 6 | **595 の末端を XIAO に戻すか**（open-gaps **O11**） | 要るか要らないかを決めるだけ。戻すと「SPI で送った値が戻ってくるか」をファームで確かめられる（数珠つなぎの断線を自分で見つけられる）。HHKB 分割機は戻していない | 「戻す」なら Claude に言う（回路 1 本・配線し直し・overlay。**発注前にしか足せない**） | **戻さない**（HHKB と同じ）。困るのは試作で列が効かないとき、原因を切り分ける道具が 1 つ少ないだけ |
| 7 | **人の確認**（open-gaps **#4**・門を止めている） | 下の §4 の「ピン配置を 3 つの目で」と、§3 の JLC の配置プレビュー | 違いが見つかったら払わずに Claude に言う | 門が開かない |

ケースの形（トレイ＋ふた・O8）は **2026-09-24 に利用者が決めた（このまま）**。基板の取付穴はこの形に乗っている。
プレートの縁を隠す飾りの縁（案 C）はあとから壁に嵌めるだけで基板は変わらないので、発注の前に決めなくてよい。
厚さ（O10）も決まった（床 1.2・13.8mm。ケースだけで基板は変わらない）。継ぎ目（O9）はケースだけで、基板の後でよい。

1〜7 が済んだら:

    tools/kb cckb parts        # 在庫を取り直す（74LVC595 C52287685 は 1,446 で薄い。10 を割ったら代替 C426713 に BOM だけ替える）
    tools/kb cckb gate         # 「開」になること

open-gaps の #1・#4 は**行を消さずに取り消し線**を引き、何で確かめたかを書く（台帳の約束）。

## §2 発注ファイルを出し直して、JLCPCB に上げる

板 `projects/cckb/pcb/cckb_main.kicad_pcb` から、発注道具（Fabrication Toolkit）で出す。ファイルは
`projects/cckb/pcb/production/`（git に入れていないので、頼む直前に出し直す）:

    tools/kb cckb fab-fields
    cd ~/Documents/KiCad/10.0/3rdparty/plugins
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
      -m com_github_bennymeg_JLC-Plugin-for-KiCad.cli \
      -p "<リポジトリの絶対パス>/projects/cckb/pcb/cckb_main.kicad_pcb" -t -nI -nB

| 上げるファイル | 中身（2026-09-24 に読んだ） |
|---|---|
| `production/cckb_main.zip` | ガーバー 13 ファイル（銅 2 層・マスク・ペースト・シルク・外形・PTH/NPTH のドリルと図） |
| `production/bom.csv` | **4 行**: C49678×2・C54110×63（キー 62＋D_PWR）・C17514×2・C52287685×2 |
| `production/positions.csv` | **69 行・全部 bottom** |

出し直したら `bom.csv` が 4 行・`positions.csv` が 69 行（全部 bottom）であることを目で見る。
XIAO・電池ホルダ・キーのスイッチ・電源スイッチは**入っていないのが正しい**（手はんだ）。

### JLCPCB の注文画面で選ぶもの

<https://jlcpcb.com/> → 「Order now」→ ZIP を上げる。

| 項目 | 選ぶ値 | なぜ |
|---|---|---|
| Base Material | FR-4 | |
| Layers | **2** | 2 層で足りた |
| Dimensions | 自動で 286.35×95.85 mm と出るはず | 違ったら ZIP の外形を疑う |
| PCB Qty | 5（最小） | |
| PCB Thickness | **1.6** | 背骨。たわみ 10N で 0.136mm（O3） |
| PCB Color | 自由（緑がいちばん安く早いことが多い） | |
| Surface Finish | **HASL（with lead）** | 無鉛にする理由が無い（fab-checklist §0） |
| Outer Copper Weight | **1 oz** | |
| Via Covering | **Tented**（既定のまま） | 板の設定がテント。XIAO の手前の 7 穴は部品の穴なので、この選択は効かない |
| Remove Order Number | **Yes**（fab-checklist §0 のとおり） | 表に番号を刷らせない |
| **PCB Assembly** | **オン** | |
| PCBA Type | **Economic** | Standard は部品から板端 2.5mm 以上が条件で合わない |
| Assembly Side | **Bottom Side** | 部品は全部裏 |
| PCBA Qty | 2（最小。1 台なら 2 で足りる） | |
| Tooling holes | JLC に任せる（Added by JLCPCB） | |
| **Confirm Parts Placement** | **Yes** | §3 の向きを自分で見るため |

「Next」で BOM と CPL を上げる。**BOM の突き合わせ画面で 4 行とも部品が見つかり、在庫があること**を見る
（C52287685 が足りなければ、戻って BOM の番号を C426713 に替える。ピン配置と 1 番の位置は同じ・open-gaps A4）。

**ここで代金が出る**（基板・組立・部品・送料）。この文書では代金を出していない（JLC の見積もりは画面でしか正確に出ない）。
参考に、部品代と Extended の段取り費だけで 2 枚実装 約 $10.6（[shopping-list.md](shopping-list.md) §7）。

## §3 配置プレビューで見る 5 か所（払う前に）

プレビューは **Bottom 表示で左右が裏返る**。「+」の印は 1 番ではなく**アノード**（HHKB で確かめた）。
**判定は部品の 3D の本体の帯（カソード）と、IC の 1 番の丸で**。同じ形の部品は 1 個見れば全部同じ。

| 部品 | 板の上で（表から見て） | プレビューで見ること | 絵（板） |
|---|---|---|---|
| U1 SN74LVC595 | 1 番は**右上**（16 番は左上で C_U1 の隣） | 1 番の丸（または面取り）が、C_U1 から遠い側の角 | `build/pcb_view/cckb.pcb.cckb_main__C_U1.png` |
| U2 SN74LVC595 | 1 番は右上（16 番は左上で C_U2 の隣） | U1 と同じ | — |
| キーのダイオード（縦 58 個。例 D1） | 帯（カソード）が**手前（−y）** | 帯が手前の側 | `build/pcb_view/cckb.pcb.cckb_main__SW54.png` |
| スタビのキーのダイオード（横 4 個: D42・D43・D58・D60） | 帯が**左（−x）** | 帯が左の側（プレビューは左右が裏返るので、画面では右に見えることがある——表から見た向きに直して判定する） | `build/pcb_view/cckb.pcb.cckb_main__D42.png` |
| D_PWR（電源のショットキー） | 帯が**右**（XIAO の 3V3 へ行く側） | 帯が右の側 | `build/pcb_view/cckb.pcb.cckb_main__D_PWR.png` |

絵は `tools/kb cckb render` で出る（build/ は git に入れていない）。見た結果は [fab-checklist.md](fab-checklist.md) §1 の
「JLC のプレビュー」「判定」の欄に日付つきで書く。**1 か所でも逆なら払わずに JLC の画面で回転を直す**（直した角度も書く）。

## §4 ピン配置を 3 つの目で（open-gaps #4 の残り）

[fab-checklist.md](fab-checklist.md) §3 の表の B・C・D の欄を埋める。A（データシート ↔ 設計）は済んでいる。
**同じ人が同じ表を読み返すのは 1 つの目にしかならない**ので、見方を変える。

| 目 | やること | 対象 |
|---|---|---|
| B 商品写真 | LCSC・スイッチサイエンス・秋月の商品写真で 1 番（丸・帯・＋の印）の位置を見て、KiCad の板の絵（`build/pcb_view/…__U_MCU.png`・`__BT1.png`・`__SW_PWR.png`）と向きを合わせる | 74LVC595・XIAO・SS-12D00G3・BS-16-B4AK003 |
| C KiCad でクリック | KiCad で `cckb_main.kicad_pcb` を開き、パッドをクリックしてネット名を読む: U1 の 12 番＝CS、XIAO の D7＝CS、BT1 の＋（パッド 1）＝VBAT_IN、SW_PWR の 2（真ん中）＝VBAT_IN・1（奥）＝VBAT_SW・3（手前）＝無し | 同上 |
| D 1:1 の印刷 | KiCad から板を 1:1 で紙に印刷（「実際のサイズ」）し、届いた実物（XIAO・電池ホルダ・電源スイッチ）を載せて、足とパッドが重なり＋の向きが合うかを見る（電源スイッチは紙に足を差して 3 つの穴に合うか） | XIAO・BS-16-B4AK003・SS-12D00G3 |

3 つ済んだら open-gaps #4 に取り消し線を引き、`tools/kb cckb gate` が「開」になることを見る。

## §5 頼んだ後

- [fab-checklist.md](fab-checklist.md) の「発注履歴」に 1 行（日付・枚数・表面処理・D_PWR の品番・注文番号）
- 基板が届いたら: 外形をノギスで測る（幅 286.35・奥行き 95.85。±0.2 を超えたら Claude に言う・open-gaps P12）、
  通電の前に導通を見る（fab-checklist §5）。組み立ては [assembly-guide.md](assembly-guide.md)
