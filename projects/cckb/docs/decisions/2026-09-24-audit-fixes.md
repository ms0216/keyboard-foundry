# 独立監査（A〜F）の所見を発注前に基板・ケース・手順に入れる

- **日付:** 2026-09-24
- **状態:** 決定
- **決めた人:** Claude（利用者の不在中。裁定 R1〜R7 は統括 `.superpowers/sdd/cckb-autonomy/audit-rulings.md`）
- **出典:** 監査の報告 `.superpowers/sdd/cckb-autonomy/audit-A.md`〜`audit-F.md`。所見ごとの行き先は
  同じ場所の `fix-report.md`

## 結論（先に）

| # | 所見 | 決めたこと | 確かめ方 |
|---|---|---|---|
| R1 | C_U1（JLC がリフローで付ける 0805）の GND パッドの**中**に縫いのビア（BT1 にも 1 本） | 根本原因（`route_pcb.Space.free()` が同じネットのパッドを当たり判定から外していた）を直し、同じネットのパッドも縫いのビアの障害物（銅の縁から 0.1）にした。配線・塗りをやり直した | `test_no_via_inside_any_pad`（全部の銅のパッド。例外は XIAO の D0〜D6 の 7 個だけ・名指しで数を固定）。C_U1 のパッドにビアを戻すと落ちる |
| R2 | 電源スイッチのつまみが外形から 1.95 出たまま JLC が実装・CPL の原点が 0.448 ずれる | **(b) 手はんだに回す**（下の §R2）。BOM・CPL から外し、利用者の買い物に足した | Fabrication Toolkit を板の写しに通した CPL を、JLC の部品データ（EasyEDA）の原点とパッドで置き直して板のパッドと比べる `test_jlc_places_every_part_of_the_cpl_on_its_pads`（69 個・回転を 90°/180° 違える・原点を 0.45 ずらすと落ちる） |
| R3 | XIAO の裏の露出パッドは 6 個でなく 8 個。NFC2 の真下に D7 のパッド・GND ビア・GND ベタ | 8 個を公式 STEP と Seeed 公式フットプリントで確定（spec.XIAO_BOTTOM_PADS）。XIAO のパッドを縁から内 2.85 → **2.2**（Seeed 公式のランド 2.18 に揃える）、禁止域を 8 個 ＋ 0.3 まで広げた | `test_the_xiao_bottom_pads_are_the_official_ones`（STEP を毎回数える: 8）・`test_nothing_on_top_under_the_xiao`（8 個を名指し）。板の写しで D7 を前の長さに戻すと NFC2 で落ちる |
| R4 | USB 給電中にスイッチ ON だと、消耗した CR1632 へ B5819W の逆漏れが流れうる | ~~**部品は替えない**（下の §R4: 条件を両方満たす品が JLC に無い）~~ **→ 比べ方が誤っていた。下の §S2 で比べ直し、既定を BAT46W（C54110）に替えた（最後に決めるのは発注前の利用者）**。手順書・説明書に「**USB を挿す前に電源スイッチを OFF**」、台帳の受け入れた差に数字を残した | 候補 8 品番のデータシートの数字（下の表） |
| R5 | 基板とトレイの壁の隙が片側 0.2 | 片側 **0.5**。外面は動かさず壁を 1.6 → 1.3（下の §R5） | `test_cckb_case.py`・`test_cckb_interface.py` |
| R6 | H3 のインサートの縁が表の CS の線・GND ビアに 0.02 掛かる | H3 のまわりに表の銅・ビア・ベタの禁止域（インサートの外径 3.2 ＋ 0.3 → 半径 1.9） | `test_nothing_on_top_under_the_h3_insert`（**→ 2 回目の監査で `test_nothing_under_the_metal_on_the_board` に置き換えた。§S1**。線・ビアの形と、塗った後の銅の面積。対照の円では銅が数えられる）。線を足すと落ちる |
| R7 | 軽微 23 件 | 基板に効くもの（パッド内ビアの輪・サーマル・1 本ビアの島）は一緒に直した。文書は直した。残りは open-gaps に理由つき | fix-report.md の一覧 |

## §R2 電源スイッチ: JLC に実装させるか、手はんだか

### 事実（JLC の公式の資料・2026-09-24 に読んだ）

- **PCB Assembly FAQs (Part 2)** <https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2>:
  "For economic assembly, as boards will be panelised … There will be a tolerance of about 0.2mm when
  routing the boards for depanelizing … We suggest that the edges of the traces and components must be
  more than 0.3mm away from the edge of the board."
- **PCB Assembly Fixtures** <https://jlcpcb.com/help/article/PCB-ASSEMBLY-FIXTURES>: "3. When SMT components
  exceed the PCB — In cases when the SMT components exceed the PCB board, or the component's center of
  gravity is not on the board or edge rail …, the carrier needs to be used."（治具は費用と日数がかかる）
- **Terms and Conditions of JLCPCB Assembly Service** <https://jlcpcb.com/help/article/Terms-and-Conditions-of-JLCPCB-Assembly-Service>
  §2-3: "The distance between the body of the components and the edge of the board must be equal or
  greater than 2.5mm."（Standard。Economic は上の 0.3）
- 部品が外形からはみ出すことを**許す**と書いた JLC の資料は見つからなかった
  （PCBA の能力の表 <https://jlcpcb.com/capabilities/pcb-assembly-capabilities> にも記述が無い）

板の値: つまみの先は外形から 1.95、コートヤードは 2.245 出る（監査 C・E）。

### 決めたこと: (b) 手はんだ

裁定の規則「公式の資料で (a) が確実に通ると言えないなら (b)」に当てはめた。(a)（Economic のまま
Fabrication Toolkit の位置補正で原点を合わせ、はみ出しはエッジレール等で逃がす）は、
上の 3 つがどれも「はみ出す SMT 部品はキャリアが要る／縁から 0.3 以上」と書いていて、確実に通るとは言えない。

- `spec.NOT_ASSEMBLED` に `power_switch` を足した → `foundry.fab_fields` が SW_PWR を BOM・CPL から外す
- 利用者の買い物に **MK-12C02-G025（LCSC C778186）** を足した（1 台 1 個。予備を含めて 3 個を勧める）
- 手はんだは裏面の端子 3（0.9×1.8・ピッチ 1.5/3.0）と耳 4。位置決めの突起 φ0.7 が穴 φ0.9 に入るので
  置くだけで位置が決まる。**付ける順: XIAO → スイッチ（プレートを付ける前・基板の裏が上を向いているうち）**
  （printing-and-assembly.md §5）
- 裏のペースト（B_Paste）には SW_PWR のパッドの開口が残る（フットプリントのまま）。JLC がステンシルで
  塗ってリフローすると、付ける前のパッドにはんだが盛られた状態で届く（予備はんだ。手はんだの邪魔にはならない）
- B-1（CPL の原点が EasyEDA と 0.448 ずれる）は、SW_PWR が CPL から外れたので効かなくなった。
  **ほかの 69 個は、監査 B の照合を検査にした**（上の表）

### 捨てた案

| 案 | 捨てた理由 |
|---|---|
| (a) JLC 実装のまま・FT Position Offset で原点を合わせる | 原点は合わせられるが、はみ出しが公式の資料で通ると言えない（キャリアの費用・EQ で止まる・切り離しでつまみを傷める） |
| スイッチを内へ寄せて外形の中に収める | つまみがケースの外面から 2.1 引っ込み、爪が届かない（D9・P4）。境界の凍結（interface §5）も崩す |
| Standard PCBA ＋ エッジレール | 本体と縁 2.5mm の規則にスイッチ本体（縁から 0.55）が反する |

## §R4 USB 給電中の逆漏れ: ダイオードを替えるか

> **⚠ 2026-09-24（2 回目の監査 A2-1・A2-2）: この節の比べ方は誤り。記録として残し、正しい比べ方と結論は下の §S2。**
> 誤り 1: 条件 1 で、B5819W には分圧が電池から吸う電流を差し引いたのに、替える候補には IR そのものに 1µA 未満を求めた。
> 誤り 2: 条件 2 で BAT46W の**最大値**（0.45V @10mA）と B5819W の**典型値**（0.30V @100mA）を比べた。
> 誤り 3: 表の BAT46W の行で CJ（C54110）と Diodes（C83152）の値を 1 行にまとめた。「Tj 60℃ で 5.0µA」は Diodes と Vishay の値で、
> 板に載る CJ のデータシートには高温の保証が無い。

### 効く条件

| # | 条件 | 値 | 何で確かめたか |
|---|---|---|---|
| 1 | 逆漏れ IR（USB 給電中・スイッチ ON・消耗した電池） | VR ≈ 3.3 − 1.9 = **1.4V** で、25℃・40℃ とも**最悪値が 1µA 未満**（Energizer のリチウムコインの逆充電の上限 1µA・設計書 §4） | データシートの**保証値**（典型の曲線は最悪ではない） |
| 2 | 順電圧 Vf（打ち止めを決める。parts.md） | 0.2〜10mA で B5819W と同等以下 | データシート |
| 3 | JLC に在庫・フットプリント | SOD-123 なら板を変えずに差し替え | JLC の API（2026-09-24） |

### 事実（データシート・LCSC で取った PDF）

| 品番（LCSC） | IR の保証値 | 40℃ | Vf の保証値（0.2〜10mA） | 判定 |
|---|---|---|---|---|
| **B5819W**（C8598・いま・CJ） | 1mA @40V だけ。典型の曲線で **25℃・VR 1V で約 5µA** | 無規定（曲線 75℃ で約 60µA） | 無規定。典型の曲線は 100mA で約 0.30V（それより低い電流は描かれていない。10mA ではこれより低い） | 条件 1 を満たさない（だから所見） |
| BAT46W（C54110・CJ／C83152・Diodes） | **0.3µA @1.5V**（25℃） | 5.0µA @1.5V・**Tj 60℃**。40℃ は無規定（25→60℃ の指数で補うと約 1.0µA） | 0.25V @0.1mA・**0.45V @10mA**。典型の曲線は 10mA で約 0.30V | 条件 1 は 40℃ で保証が無い。条件 2 は 10mA で B5819W（100mA で 0.30V）より高い |
| BAT46W（C14099・Vishay） | 0.5µA @1.5V（25℃） | 5µA @1.5V・Tj 60℃ | 0.25V @0.1mA・0.45V @10mA | 同上 |
| BAT42W（C134396・Diodes） | 0.5µA @25V（25℃） | 100µA @25V・Tj 100℃ だけ | **0.40V @10mA** | 条件 1 は 40℃ 無規定、条件 2 が高い |
| BAT43W（C19167・CJ） | 0.5µA @25V（25℃） | 無規定 | 0.26〜**0.33V @2mA**・0.45V @15mA | 条件 2 が高い |
| RB751V40（C553814・Nexperia・SOD-323） | 0.5µA @30V（25℃） | 無規定（曲線は 25/85/125℃） | **0.37V @1mA** | 条件 2 が高い（フットプリントも別） |
| 1N4148W（C81598・シリコン） | 25nA @20V（25℃） | 30µA @25V・Tj 150℃ | **0.715V @1mA**・0.855V @10mA | 条件 2 が大きく高い |
| SD103AW（C8606・CJ） | **5µA** @30V | — | 0.37V @20mA | 条件 1 を満たさない |
| B5817W（C8597・CJ） | 1mA @20V だけ | — | 0.45V @1A | 条件 1 の保証が無い |

PDF（LCSC）: B5819W <https://datasheet.lcsc.com/datasheet/pdf/4ac2c059be7c462694ab0715ce987a85.pdf>・
BAT46W CJ <https://www.lcsc.com/datasheet/lcsc_datasheet_1810251820_Jiangsu-Changjing-Electronics-Technology-Co---Ltd--BAT46W_C54110.pdf>・
BAT46W Vishay <https://datasheet.lcsc.com/datasheet/pdf/86b54bf47f592e7eb6de314e5e61af98.pdf>・
BAT46W Diodes <https://datasheet.lcsc.com/datasheet/pdf/18e08184e5865113cc055d7c9a1d2463.pdf>・
BAT42W Diodes <https://datasheet.lcsc.com/datasheet/pdf/d305a62001dc43cfab8d44301c23edf4.pdf>・
BAT43W CJ <https://datasheet.lcsc.com/datasheet/pdf/76a3e055d6ed4991b21fa0ca43348979.pdf>・
RB751V40 Nexperia <https://datasheet.lcsc.com/datasheet/pdf/bd6d964dba1c632c4e076399f160c3d8.pdf>・
1N4148W <https://datasheet.lcsc.com/datasheet/pdf/8abd7fc00ebe41ffb03ad1383c10753b.pdf>・
SD103AW <https://datasheet.lcsc.com/datasheet/pdf/76bb472f2a624330a45712fcd6688552.pdf>・
B5817W <https://datasheet.lcsc.com/datasheet/pdf/3b3f32cf2655436c8aa5147f96bd7261.pdf>。
HHKB の比較（foundry/parts.py の diode の欄: SOD-123 のショットキー 29 件と BAT/1SS/NSR/RB751/PMEG/MBR/SS/1N5711/BAS40 の系列）
でも「低い逆電圧の IR と低電流の Vf の両方を保証するのは BAT46W だけ」で、その BAT46W も上の通り
40℃ の IR と 10mA の Vf で条件を満たさない。

**なぜ両立しないか**: ショットキーの逆漏れと順電圧は障壁の高さと接合の面積で引き換えになる
（漏れが小さい品は、同じ電流で Vf が高い）。1A 級の B5819W は面積が大きく、mA 級では Vf が低いが漏れが大きい。

### 決めたこと: 部品は替えない。手順で避ける

裁定の規則「IR が最悪でも 1µA 未満で、Vf が B5819W と同等以下の品が無ければ、部品は替えず、
手順書・説明書に『USB を挿す前に電源スイッチを OFF』を太字で書き、台帳に受け入れた差として残す」。

- スイッチは電池と回路の間にある（VBAT_IN は BT1.＋ と SW_PWR.② の 2 パッドだけ・監査 A が板で確認）。
  **OFF なら電池は完全に切り離され、逆漏れの経路が無い**
- 書いた所: `docs/printing-and-assembly.md` §5・§6（使い方）、`docs/task-10a-coin-cell-startup.md`（USB の対照実験の前に OFF・
  「USB を挿してスイッチ ON で電池に流れる電流の向きと大きさ」を 1 項目足した）、open-gaps の受け入れた差 A1
- 数字（台帳に残す）: 逆電圧 1.4V・B5819W の典型 約 5µA（25℃）・分圧が電池から取る 1.2µA を引いて
  25℃ で約 +1〜4µA が電池へ。上限 1µA。温度が上がると 1 桁増える

## §R5 基板とトレイの壁の隙

- JLC の外形公差 ±0.2（<https://jlcpcb.com/capabilities/pcb-capabilities>）と PLA の縮み 0.2〜0.3% を足すと、
  片側 0.2 の隙は奥行き（96.25 の内側に 95.85＋0.2）で 0 以下になりうる（監査 E 重要 2）
- **境界の値は 1 か所**: `spec.CASE_PCB_GAP = 0.5` を `interface.wall_inner`（= 基板の外形 ＋ CASE_PCB_GAP）
  だけが読み、`case.r_in`（壁の内面の角の丸み = 基板の角 R ＋ 隙）は interface から導く
- **外面は動かさない**（外面 = 基板 ＋ 0.5 ＋ 壁 1.3 = キー領域 ＋ 2.1 で、前の キー領域 ＋ 0.5 ＋ 1.6 と同じ）: 外面が動くと USB の口の
  引っ込み（0.3 → 0.6・上限 0.6）とつまみの先（外面 ＋0.15 → −0.15）が変わる。壁を 1.6 → **1.3**（0.4 ノズル 3 周・
  肉厚の下限 1.2 の内側）にして内面だけを 0.3 外へ
- 指の窪み `PSW_SCOOP` を 1.0 → **0.9**: 壁 1.3 − 1.0 では窪みの奥の壁が 0.3（線 1 本に満たない）。0.9 なら 0.4、
  つまみの先は窪みの底から 1.05（`PSW_NAIL_REACH` 1.0 以上）
- 付いてくる改善: XIAO の USB 側の端と壁の内面の隙 0.23 → 0.53（監査 E 軽微 1）。上から見えるキャップと壁の隙は
  1.025 → 1.325（HHKB 実機の実測 1.0〜1.5 の中）

## 2 回目の監査の直し（S1〜S3・2026-09-24）

裁定は統括 `.superpowers/sdd/cckb-autonomy/audit2-rulings.md`。報告は同じ場所の `audit2-A.md`〜`audit2-E.md`、
所見ごとの行き先は `fix2-report.md`。

### §S1 基板に金属が当たる所の下に銅を置かない（全部の取付を数で）

- **何が起きたか**: 1 回目の R6 は H3 のインサートだけに禁止域を置いた。配線し直したら CS の表の線が H5・H6 の
  **鋼の六角ナットの真下**（中心から 1.603。ナットの角は 2.31）を通った（監査 E 2 回目 重要 1）。ほかの 9 か所を
  見る検査が無かった
- **母数**: 取付の穴は板に 11（H0〜H9・H_LID）。`interface.metal_on_pcb()` が穴ごとに金属（ナット・インサート・
  ネジの頭・上からのネジ）を並べ、**高さで**どの面に当たるかを決める（組み立てモデルと同じ積み上げ。
  `tests/test_cckb_case.py` がモデルの金属の立体と突き合わせる）:

  | 取付 | 金属 | 当たる面 | 当たる円（半径） |
  |---|---|---|---|
  | H0〜H2・H4〜H9（9） | M2 六角ナット（z 5.0〜6.6） | **上面** | 2.425 = max(ナットの外接 2.309 ＋ 穴の遊び 0.1, プレートの六角の穴の外接 2.425) |
  | H3 | 左のふたの熱圧入インサート（z 5.0〜8.0） | **上面** | 1.6（外径 3.2） |
  | H0〜H9 | 下からの皿ネジの頭（z 0.9〜2.1） | 当たらない（基板の下面 3.4 との間はトレイの樹脂のボス） | — |
  | H_LID | 柱のインサート（z 5.8〜8.8）・上からのネジ（z 6.0〜12.0） | 当たらない（樹脂の柱が穴 φ6.0 を通り、金属は基板より上） | — |

  ネジの軸は非めっきの穴の中を通るだけ（穴と銅の間は DRC の規則）。**下面に当たる金属は 0**
- **直したこと**: 当たる円 ＋ `spec.METAL_COPPER_CLEAR`（0.3。前の `INSERT_COPPER_CLEAR` を改名）の禁止域
  `METAL_KEEPOUT`（当たる側の層・線/ビア/ベタ禁止）を 10 か所に（pcb_extra）。ナットは半径 2.725、H3 は 1.9（前と同じ）
- **配線は CS だけを直した**（`route_pcb.py --reroute CS`）: 前の板の線・ビアを GND 以外そのまま持ってきて、CS のうち
  禁止域に掛かる 1 本（F.Cu y −42.633・x −37.463〜54.064）だけを外し、欠けた所を Freerouting に繋がせた。
  **CS を丸ごと外して引かせると 1 本繋がらなかった**（余裕 30/35µm で未配線 1）。まっさらから全部を引き直すと
  余裕 30/35 で未配線 3/2 で、しかも Freerouting の網を全部動かす（監査の済んだ配線を捨てる）ので採らなかった。
  変わった網の数え方と結果は下の「S1 の結果」。**Freerouting は回していない**: 外した 1 本は `route_pcb.detours` が
  決まった形（円から離れる側へ平行にずらし、両端を元の端へ 45° で戻す）で置き直した。禁止域を 1〜2 個にした DSN では
  Freerouting 自身がこれと同じ 3 本（y −43.99）で繋いだ——禁止域 10 個の DSN では繋がらなかった
- **S1 の結果**（前の板 f95a7c9 と網ごとに線・ビアの集合を比べた）: 91 網のうち **89 網は線もビアも同じ**。
  **CS**: 線 1 本（F.Cu y −42.633・x −37.463〜54.064）→ 3 本（(−37.463, −42.633)→(−36.063, −44.033)→(52.664, −44.033)→
  (54.064, −42.633)）。ビアは同じ。H5・H6 の中心から線の縁まで 2.9（禁止域 2.725 の外）。**GND**: スタブ 9 本は同じ
  （1µm 未満の丸めの差）、縫いのビア 999 → 1003（34 消えて 38 増えた: ナットのまわり 11・CS の脇のフェンスが y −45 から
  −44.7/−46 へ 7→23 ほか）。DRC 違反 0・未配線 0・警告 5（silk_edge_clearance 3・npth_inside_courtyard 2。前と同じ）
- **検査**: `test_every_mount_hole_is_judged_and_the_metal_touches_only_the_top`（母数 11・当たる 10）、
  `test_nothing_under_the_metal_on_the_board`（10 か所それぞれの円の中の当たる側の線・ビア・塗った後の銅が 0。
  対照の円〔D7 のパッドの上〕では銅が数えられる）、`test_the_metal_check_notices_a_track_under_a_nut`（H5・H6・H0 に
  監査で見つかった形の CS を足すと落ちる）・`…_a_missing_hole_judgement`（判定の無い穴を足すと落ちる）。
  **直す前の板（HEAD f95a7c9）に同じ検査を当てると H5・H6 の CS を出す**（fix2-report.md に出力）

### §S2 USB 給電中の逆流: 正しい物差しで比べ直す

**物差し**: 電池に入る正味の電流 ＝ ショットキーの逆漏れ IR（VR・温度）− 分圧が電池から吸う電流。
スイッチ ON・USB あり: カソードは XIAO の 3V3（3.3V）、アノードは VBAT_SW ＝ 電池。逆電圧 VR ＝ 3.3 − Vbat ＝ 0.1〜1.4V
（Vbat 1.9〜3.2V）。IR は VR とともに増えるので（どのデータシートの曲線も単調）、**VR 1.5V の保証値は 1.4V 以下の上限になる**。
分圧は 1MΩ＋1MΩ（1%）で、吸う電流は少なくとも Vbat / 2.04MΩ ＝ **0.93µA（1.9V）〜1.57µA（3.2V）**。
逆漏れがこれより小さければ、電池は充電されず分圧へ放電する。上限は Energizer CR1632 の「Max Rev Charge: 1 microampere」
（<https://data.energizer.com/pdfs/cr1632.pdf>・2026-09-24 に取り直して読んだ）。

**Vf は同じ種類の値どうしで**（0.2〜10mA は XIAO の平均〜送信の山の電流）。順電圧は電流とともに増えるので、ある電流の
保証値はそれより低い電流の上限にもなる。

| | B5819W（C8598・CJ・いま） | BAT46W（**C54110・CJ**・キーと同じ品） | BAT46W（C83152・Diodes） |
|---|---|---|---|
| IR の保証値（VR ≦ 1.5V に効くもの） | **1mA @40V だけ**（25℃）→ 上限として意味が無い | **0.3µA @1.5V**（25℃）。高温は**無規定** | 0.3µA @1.5V（25℃）・**5.0µA @1.5V・Tj 60℃** |
| 電池に入る正味（保証値・25℃） | 保証から言えない（上限 約 +1000µA） | **0**（0.3 − 0.93 < 0） | **0** |
| 電池に入る正味（保証値・60℃） | 言えない | 言えない | ≦ +4.1µA（1.9V）・+3.4µA（3.2V）→ 上限 1µA を越えうる |
| 同（典型の曲線・25℃・VR 1V） | IR 約 5µA → **約 +3.4〜+4.1µA** | IR 約 0.2〜0.3µA → 0 | （曲線を読んでいない） |
| Vf の保証値（0.2〜10mA） | **≦ 0.6V**（1A の値だけ。低い電流の保証は無い） | **≦ 0.45V**（@10mA）・≦ 0.25V（@0.1mA） | 同左 |
| Vf の典型（25℃・0.2 / 1 / 10mA） | **描かれていない**（曲線は 100mA の 約 0.31V から） | 約 0.19 / 0.255 / 0.31V（CJ の曲線を 200dpi で描いて読んだ） | — |
| 打ち止め 2.4V（overlay の仮の値）でのレールの保証 | 2.4 − 0.6 = 1.8V | 2.4 − 0.45 = **1.95V** | 同左 |
| JLC（`foundry.jlcpcb_lookup`・2026-09-24） | Basic・在庫 471,222・$0.028 | Extended（キー 62 個で手数料は払い済み）・在庫 45,945・$0.0292 | Extended・在庫 108,765・$0.1037 |

出典（2026-09-24 に LCSC から取り直して pdftotext と描いた曲線で読んだ）: B5819W CJ
<https://datasheet.lcsc.com/datasheet/pdf/4ac2c059be7c462694ab0715ce987a85.pdf>・BAT46W CJ（C54110）
<https://datasheet.lcsc.com/datasheet/pdf/f97c8b3ccdb24c5ba21cb2c31ad9c922.pdf>・BAT46W Diodes（C83152）
<https://datasheet.lcsc.com/datasheet/pdf/18e08184e5865113cc055d7c9a1d2463.pdf>・BAT46W Vishay（参考・同じ保証値の 0.5µA 版）
<https://datasheet.lcsc.com/datasheet/pdf/86b54bf47f592e7eb6de314e5e61af98.pdf>。

**読み方**: 保証値で言えるのは「BAT46W なら 25℃ で電池に入らない」まで。B5819W は保証から何も言えず、典型でも
25℃ で上限の 3〜4 倍。40℃ 以上はどちらも保証が無い（Diodes の 60℃ の保証値では BAT46W も上限を越えうる）。
Vf は保証値どうしなら BAT46W の方が低い（≦0.45 と ≦0.6）。典型どうしは B5819W の低い電流の値が無いので比べられない
（1 回目の監査 A2 の見積もり「10mA で約 0.24V、差 60〜80mV」は曲線の外挿で、測った値ではない）。

**既定（利用者が決めるまで）: BAT46W C54110**（裁定の「安全側 ＝ 正味の逆流が保証値で 1µA 未満になる方」）。
板は変わらない（D_PWR は同じ D_SOD-123）。`spec.PARTS["schottky"]` の品番 1 行と、pcb_extra の D_PWR の値の名前だけ。
BOM はキーと同じ行にまとまり 5 → 4 行。

**利用者が発注前に決めること**（`.superpowers/sdd/cckb-autonomy/progress.md`「利用者に確認したいこと」・open-gaps O12）:
BAT46W（逆流を保証値で 0 にする・Vf の保証値も低い）か、B5819W（Basic・Vf の典型は低いかもしれないが保証が無い・
25℃ でも典型で電池へ数 µA）か。どちらでも「USB を挿す前に電源スイッチを OFF」の規則は残す（40℃ 以上では BAT46W でも保証が無い）。
**起動の余裕はダイオードで変わりうるので、task-10a を両方のダイオードで測る**（手順書に書いた）。

### §S3 軽微 13 件

行き先は `fix2-report.md` の一覧。基板に効いたもの: SW_PWR などの手はんだの部品のパッドからペーストの層を外した（B2-1・C1。
B.Paste の開口 173 → 166）、XIAO のパッド内ビアの輪 φ0.7 → φ0.8（C2。アニュラ 0.25 ＝ JLC の推奨）。
XIAO の裏の USB のシールドのめっきの長穴 4 個を `spec.XIAO_BOTTOM_SLOTS` として数え、検査で名指し（D4。禁止域の形は変わらない）。

## この決定が乗っている前提（動いたら読み直す）

- R2: JLC の公式の資料が「はみ出す SMT 部品はキャリア」「Economic は縁から 0.3」と書いていること。
  JLC がはみ出しを許すと明記したら、(a) に戻して BOM/CPL に戻せる（CPL の原点は FT Position Offset で 0.448）
- S1: 基板に当たる金属がナット 9・インサート 1 で、下面に当たる金属が無いこと（ネジの頭がトレイに沈み、基板の下がトレイの
  樹脂のボスであること）。**座金を足す・ネジを上からに変える・ナットを基板の下に回す、なら `interface.metal_on_pcb` と禁止域を読み直す**
- S2: 分圧が 1MΩ＋1MΩ でスイッチの後ろ・ダイオードの前にあること（分圧を大きくすると吸う電流が減り、正味が電池へ向く）
- R4: 電池が CR1632（リチウム一次）であること。CR2032 に替えても同じ（上限 1µA は同じ系列）。
  **電池を充電式にする・理想ダイオードの IC に替える、なら読み直す**
- R5: 基板の外形 ±143.175 × ±47.925（spec.PLATE_MARGIN・CORNER_R）が変わらないこと

## まだ決めていないこと

| 項目 | 決められない理由 |
|---|---|
| A-4（595 の末端 QH' を D9 に戻して数珠つなぎを自分で検査する） | 回路の足し算で、利用者との合意の外。**発注前にしか足せない**ので open-gaps O11 で利用者に聞く |
