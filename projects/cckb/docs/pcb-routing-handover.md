# 基板の配線 — 引き継ぎ（cckb・2026-09-24）

## 結論

**基板は配線まで済んだ。発注前に人が見るものが 2 つ残っている**（JLC の配置プレビューで部品の向き、
ピン配置を 3 つの目で）。発注に使う板は `projects/cckb/pcb/cckb_main.kicad_pcb`。

| | 値 |
|---|---|
| DRC | 違反 0・未配線 0・警告 5（シルクが縁に近い 3・電源スイッチの位置決めの穴がホルダの下 2＝理由つき） |
| 配線 | 線 684 本・ビア 1030（GND の縫いのビア: リング 14・フェンス 259・格子 702・離島 4・1 本の島の 2 本目 11） |
| 遠回り（自動配線のネット） | 直線の最短に対して 1.03〜1.15 倍（3 を超えたら疑う目安） |
| GND ベタ | 表 22,392mm²・裏 21,695mm²。繋げなかった浮き島 20 個 65.6mm² は消した。ビア 1 本だけの島は 4 個（長さ 11.3mm 以下） |
| 電源の線 | V3V3・VBAT_SW・VBAT_IN は全部 0.3mm |
| 発注道具（Fabrication Toolkit） | BOM 5 行すべて LCSC 番号・CPL 69 行すべて裏（**電源スイッチは手はんだ**・2026-09-24）・ガーバーは 2 層だけ |
| 検査 | `tests/test_cckb_pcb.py` 56 本。検査ごとに、事実の写しか板の写しを壊して落ちることを確かめる検査が付く |

**2026-09-24 の独立監査の直し**（決定記録 `decisions/2026-09-24-audit-fixes.md`）: パッドの中のビア（縫いのビアの
当たり判定が同じネットのパッドを飛ばしていた）・XIAO の裏の露出パッド 8 個（前は 6 個）の下の表の銅・H3 の
インサートの下の表の銅・電源スイッチを手はんだに・XIAO のパッドを縁から内 2.2 に・パッド内ビアを φ0.7・
0805 と手はんだの GND パッドをサーマルに・ビア 1 本の長い GND の島に 2 本目。Freerouting は余裕 40µm で未配線 0
（30・35・25 では 1。`pcb/route.json` に記録）。

**2026-09-24 の 2 回目の監査の直し**（決定記録 §S1〜S3）: 金属が当たる 10 か所（キーの下のナット 9・H3 のインサート）
全部に禁止域 `METAL_KEEPOUT`（`interface.metal_on_pcb` が高さから判定）。配線は **`route_pcb.py --reroute CS`** で、
前の板の線・ビアを GND 以外そのまま持ってきて、禁止域に掛かった CS の 1 本（y −42.633）だけを決まった形
（円から離す側へ平行にずらして y −44.033・両端 45°）で置き直した。**変わった網は CS と GND（縫いのビア）だけ**
（ほかの 89 網は前の板と線・ビアが同じことを route_pcb が確かめる）。Freerouting は回していない（丸ごと引かせると
禁止域 10 個の入力で CS が 1 本繋がらなかった）。ペーストを手はんだの部品から外した・パッド内ビアを φ0.8 に・
D_PWR の値を BAT46W に（板の銅は変わらない）。

絵: `tools/kb cckb render` → `build/pcb_view/cckb.pcb.cckb_main.png`（表裏重ね）。

## 作り方（いつでも同じ板に戻る）

    tools/kb cckb pcb                                               # 未配線の板（置く・ネットを張る）
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py                # 配線 → ベタ → GND のビア（約 3〜10 分）
    "$KICAD_PYTHON" projects/cckb/tools/route_pcb.py --reroute CS   # いまの配線を持ってきて CS だけ直す（2 回目の監査の直しはこれ）
    tools/kb cckb fab-fields                                        # LCSC・BOM から外す印を焼く
    tools/kb cckb drc                                               # 記録 pcb/cckb_main.drc.json
    REQUIRE_KICAD=1 .venv/bin/pytest tests -q

**配置（spec.py・pcb_extra.py・lib のフットプリント）を変えたら、この 4 つを全部やり直す。**やり直していないと
`test_the_committed_unrouted_board_is_what_the_generator_makes_now`（パッドの形・ルール領域まで比べる）と
`test_the_routed_board_was_made_from_the_current_placement`（配線した元のファイルの sha256 まで比べる）が落ちる。
**boardhash の指紋は配置・結線・外形だけ**で、パッドの大きさや禁止域の変更では変わらない（2026-09-24 に気づいた）。

## だれが何を引いているか

| 部分 | 引き方 | どこ |
|---|---|---|
| キーの行（裏の横一直線）・列（表の縦）・スイッチ→ダイオード | 決まった形（道具が板のパッドから引く） | `projects/cckb/matrix_routes.py` の `plan` |
| XIAO から行のバスまで 5 本 | 決まった形（道順は spec.XIAO_ESCAPE） | 同 `escape` |
| GND のパッド → ビア（9 か所） | 決まった形（同じ層のスタブ→ビア） | `tools/route_pcb.py` の `gnd_fanout` |
| 列 → 595・SPI・3V3・電池の線 | Freerouting 2.3.0 | `tools/route_pcb.py` の `freeroute` |
| GND ベタ・リング・フェンス・格子・離島のビア | 決まった手順（置ける所だけ） | `tools/route_pcb.py` |

決まった形の線は、置く前に**板の上の物（パッド・穴・逃げ穴・外形）との間隔と、線どうしの衝突を
自分で確かめる**（ぶつかれば止まる）。最後の判定は KiCad の DRC。

## 途中でつまずいたこと（同じ道を通らないために）

1. **段階 1 の「配線の通り道」は引けなかった。**カソードどうしを結ぶ直線はスイッチのボスと中心穴を
   貫く。行のバスはキー中心の 4.3 下（最下段は 4.9 下）、列は中心穴の左 3.1 を通すことにし、取付の
   5 条件の検査も実際に引く線（`matrix_routes`）を相手にするよう替えた
2. **Freerouting 2.3.0 は `(autoroute_settings)` があるとネットを 1 本も見ない**（「0 unrouted items」）。
   HHKB の子基板と同じ。入れていない
3. 行列の線を `fix` で渡すと、Freerouting はそれを接続と見ず未配線 67 から動かない。**行列の線は
   障害物（protect）にし、行列のネットは「駆動側のピン」と「最寄りの行列のパッド」の 2 ピンに絞る**
4. XIAO の手前の列はパッドとパッド内ビアが同じ番号。2 つのまま渡すとパッド→ビアの 1.2mm だけ引いて
   止まる。**DSN からパッドを外すと今度は見えなくなり、表の線でパッドの列を横切った**（短絡）。
   → XIAO の下の表の銅の禁止域を基板の手前の縁まで伸ばした（禁止域は Freerouting にも見える）
5. Freerouting は外形・逃げ穴をネットクラスの間隔 0.2 でしか避けない（JLC の 0.3 を割った）→ 縁と
   逃げ穴のまわりに配線禁止の帯 0.32 を置いた
6. GND のビアを置く判定が、**逃げ穴の穴の真ん中**に置けてしまった・**長いスタブ**が隣のパッドを
   横切った・**同じ GND のビアどうしの穴間**を見ていなかった（JLC 0.45 を割って 27 件）。どれも直して
   DRC で 0
7. XIAO から行へ出る 5 本は Freerouting が 1 本も出せなかった（XIAO の下は裏しか使えない・左の角は
   逃げ穴と穴と SPI の束で塞がる・D0 の電池の線が真ん中にいる）。決まった形にした: 行 0〜2 は XIAO の
   下を裏で真上へ → ビア → 表の左の縁の通り道 → そのバスの高さでビア → 裏でバスへ
8. **KiCad 10 は板を読むときに線のネットを繋がりから付け直す**（ファイルで ROW0 と書いた線が COL3 と
   して読まれた）。DRC の「壊す検査」はネット名の書き換えでは作れない。線を太らせて壊す
9. Freerouting は同じ入力なら同じ結果だが、名札を 1 つ動かしただけで未配線が 0 → 2 に揺れた。
   余裕 30/35/25/40µm を順に試して、ログの未配線 0 の最初を採る（採った値は `pcb/route.json`）

## 決まっていないこと・承知して進めたこと

- **アンテナの禁止域のまわりの GND ビアは 4 辺そろわない**（右 9/11・手前 4/7・奥 1/7・左 0/11）。
  左は XIAO 自身の下、奥と手前は XIAO のパッドの列（open-gaps P7）。試作で RSSI を測る
- **XIAO の手前の列はパッド内ビア**（段階 1 の「穴なし」から変更。open-gaps P6）
- **電源スイッチの入の向きは図の読み**（つまみを手前へ寄せると入。open-gaps P5）。**利用者が手はんだ**（付ける前にテスターで確かめられる）
- **USB を挿す前に電源スイッチを OFF**（ショットキー D_PWR の逆漏れ。既定の BAT46W では 25℃ で電池へ入らないが高温は保証が無い。open-gaps 受け入れた差 A1・O12）
- 電源スイッチの位置決めの穴がホルダの下に来る DRC（npth_inside_courtyard 2 件）は警告に下げた
  （spec.DRC_SEVERITY。穴はホルダの＋の端子の下で銅は無く、突起は基板を抜けない）。検査が「この 2 件だけ」を見る
- XIAO の 3D モデルの高さ（表面実装での Z）は確かめていない（組み立てモデルの段で）

## 機械で守っていること（tests/test_cckb_pcb.py）

| 検査 | 守るもの |
|---|---|
| `test_every_pad_carries_the_declared_net` | 回路の宣言（circuit.py）→ パッド → 板のネット。部品 145・銅のパッド 320・ネットの無いパッドは宣言した NC の 11 個だけ |
| `test_the_routed_board_has_no_drc_violation_and_nothing_unrouted` | DRC 違反 0・未配線 0・知っている警告だけ |
| `test_jlc_parts_are_all_on_the_bottom` | JLC が実装する 70 個はパッドが全部裏。手で付ける物は BOM/CPL に無い |
| `test_the_board_matches_the_firmware_pin_map` | overlay の行のピン・&shifter の番号・CS・SPI・ADC が板のネットと一致 |
| `test_the_antenna_keepout_has_no_copper_after_the_fill` | 塗った後の禁止域の銅 0（ずらした対照では銅が数えられる） |
| `test_the_power_path_has_the_right_polarity` | ホルダ＋→スイッチ②、③→VBAT_SW→分圧・D_PWR→3V3、XIAO の BAT に何も無い |
| `test_the_xiao_pads_cover_the_castellations_of_the_official_step` | 公式 STEP のパッドが板のパッドの中・張り出し 0.6 |
| `test_the_power_switch_pads_hold_the_terminals_of_the_drawing` | 図面の端子・耳の金具・穴がパッドの中、ランドの外形が spec と一致 |
| `test_the_routed_board_was_made_from_the_current_placement` | 配置を変えて配線し直していない状態を捕まえる |
| `test_nothing_under_the_metal_on_the_board` | 取付の穴 11 を板から数え、金属が当たる 10 か所の円の中の線・ビア・塗った後の銅が 0（2 回目の監査） |
| `test_only_the_jlc_parts_get_solder_paste` | ペーストは JLC が実装するパッドだけ（166）。手はんだの部品に無い |
| `test_no_via_inside_any_pad` | 全部の銅のパッドにビアが掛からない（XIAO の D0〜D6 の 7 個だけ名指しで例外） |
| `test_nothing_on_top_under_the_xiao`・`test_the_xiao_bottom_pads_are_the_official_ones` | XIAO の裏の露出パッド 8 個（STEP を毎回数える・Seeed 公式のランドと名前）の下の表の銅 0 |
| `test_jlc_places_every_part_of_the_cpl_on_its_pads` | Fabrication Toolkit の CPL を JLC の部品データで置き直すと板のパッドに乗る（69 個） |
| `test_the_thermal_pads_are_exactly_the_declared_ones`・`test_no_long_gnd_island_hangs_on_a_single_via` | サーマルは spec.THERMAL_PADS だけ・ビア 1 本の島は 12mm 未満 |

## やってはいけないこと

- 配線した板（pcb/cckb_main.kicad_pcb）を KiCad で直接直して終わりにしない。直すなら生成器
  （spec.py・pcb_extra.py・matrix_routes.py）を直して作り直す。手で引いた線は次の作り直しで消える
- DSN から部品のパッドを消すなら、その場所を**禁止域で覆う**（見えなくなった所を Freerouting が通る。XIAO の手前の列はそうしてある）
- 警告を ignore にしない（spec.DRC_SEVERITY は error / warning だけを受け付ける）
