# CCKB 実装計画 1/3 — 土台（核の Choc 対応・機種・プレート・未配線基板・ファーム・発注前の起動試験）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CCKB の配列・プレート・未配線の基板・ZMK のシールドを foundry から生成し、HHKB 配列への準拠を検査で守る。あわせて、基板の発注をせき止める「CR1632 で起動できるか」の試験手順を用意する。

**Architecture:** 核（foundry/）に「スイッチの種類」（`mech.Switch`）を足し、MX ホットスワップと Kailh Choc V1 直付けを表で切り替える。機種 `projects/cckb/` は HHKB の KLE からスペースだけを 3 分割した配列を持ち、要求（HHKB 準拠）を検査にする。ケース・配線・発注データは計画 2・3 で扱う（この計画の成果と試験の結果に依存するため）。

**Tech Stack:** Python 3.13（venv）・build123d・KiCad 10（同梱 Python 3.9 の pcbnew・kicad-cli）・ZMK（GitHub Actions でビルド）・pytest

**Spec:** [docs/superpowers/specs/2026-09-23-cckb-design.md](../specs/2026-09-23-cckb-design.md)（以下「設計書」）。作業の前に必ず読む。あわせて CLAUDE.md の「検証の作法」と docs/method/lessons.md。

## Global Constraints

- KiCad の Python から読むモジュール（`foundry/{paths,layout,matrix,mech,pcb_rules,pinmap,project,parts,boardhash,board_dump,pcb,fab_fields}.py`）は**標準ライブラリだけ・3.9 の文法**（tests/test_meta.py が見る）
- 同じ値を 2 か所に書かない。定数は使うか消すか `[記録のみ]` と書く（test_meta）。`[暫定]` の値は `projects/cckb/docs/provisional-values.md` に同じ数値で載せる（test_meta）
- 生成器は寸法を持たない。寸法は `spec.py` と `mech.py`、配列は `layout`、行列は `matrix`
- **HHKB の再現検査 `tests/test_regression_hhkb.py` を核の変更のたびに通す**
- 検査を足すときは、**故意に壊して落ちることを確かめてから**入れる（壊した結果を作業記録に書く）
- 接頭辞で走査しない（`re.fullmatch`）
- 機種名 `cckb`・基板に刷る名前 `CCKB`。他社の商標（HHKB）を基板に刷らない
- スイッチ Kailh Choc V1（PG1350）・62 個・19.05mm ピッチ・直付け。プレート FR4 1.2mm
- コミットは触ったファイルだけ名指しで stage（`git add -A` 禁止）。commit の直前に `git status -sb` の 1 行目を別の呼び出しで読む
- 利用者への報告は日本語

## Review Focus

1. **Choc のフットプリントの向き** — 2 つのライブラリが一致しても、データシートの図と向き（端子がキーの上側か）が合っていなければ全キーが 90° ずれる。Task 2 で図と照合する検査を置く
2. **3 つのスペースが別々のスイッチで、3 つとも SPACE を送る** — 行列で同じ (row, col) に潰れていないこと・キーマップのベース面で SPACE が 3 つあること（Task 7）
3. **MX の既存機種（HHKB）の結果が 1 つも変わらない** — 核の整理は純粋な移動（Task 1。再現検査と既存の検査がすべて緑）
4. **角の開口がキーの周りの桟を削らない** — 角のプレート開口が隣のキーの開口と繋がらないこと（Task 5）
5. **ダイオードが隣のキーの端子や穴と重ならない** — 幅の違うキー（2.25u の隣など）でも DRC 違反 0（Task 6）

---

## ファイル構成

| ファイル | 責務 | 作る/直す |
|---|---|---|
| `foundry/mech.py` | スイッチの種類ごとの規格値（`Switch`・`SWITCHES`・`switch_of`） | 直す |
| `foundry/project.py` | `REQUIRED` に `SWITCH` を足す | 直す |
| `foundry/plate.py` | 開口・板厚・スタビを `Switch` から読む。`PLATE_OPENINGS` を抜く | 直す |
| `foundry/pcb.py` | フットプリント・Value・ダイオード位置・スタビを `Switch` から読む | 直す |
| `lib/keyswitch.pretty/SW_Kailh_Choc_V1.kicad_mod` | Choc V1 直付けのフットプリント（kiswitch 上流） | 作る |
| `lib/README.md` | 取り込んだ記録とデータシート照合 | 直す |
| `docs/templates/spec.py.tmpl` | `SWITCH` と `PLATE_OPENINGS` の行 | 直す |
| `tests/fixtures/hhkb_ref/spec.py` | `SWITCH = "mx_hotswap"` | 直す |
| `tests/fixtures/hhkb_original.json` | HHKB 英語配列の KLE（外の事実。HHKB リポジトリから写す） | 作る |
| `tests/test_mech.py` | スイッチの種類の検査 | 作る |
| `tests/test_choc.py` | Choc のフットプリントとデータシートの照合 | 作る |
| `tests/test_plate.py` | `PLATE_T` などの参照を `Switch` へ | 直す |
| `projects/cckb/` | 機種（spec.py・layout.json・docs/） | 作る（tools/new_project.py） |
| `tests/test_cckb.py` | CCKB の要求（HHKB 準拠・角・プレート・基板） | 作る |
| `config/boards/shields/cckb/` | ZMK シールド | 作る |
| `projects/cckb/docs/task-10a-coin-cell-startup.md` | 発注前の起動試験の手順書 | 作る |
| `projects/cckb/docs/open-gaps.md` | 台帳（せき止めているもの） | 直す |

---

### Task 1: 核に「スイッチの種類」を足す（MX を表へ移すだけ。挙動は変えない）

**Files:**
- Modify: `foundry/mech.py`（全体を置き換え）
- Modify: `foundry/project.py:24-25`（REQUIRED）
- Modify: `foundry/plate.py`（import と build_plate・main）
- Modify: `foundry/pcb.py:28-30, 170-205`
- Modify: `tests/fixtures/hhkb_ref/spec.py`・`docs/templates/spec.py.tmpl`・`tests/test_plate.py`
- Create: `tests/test_mech.py`

**Interfaces:**
- Produces: `foundry.mech.Switch`（frozen dataclass。属性 `name: str`・`cutout: float`・`plate_t: float`・`fp: dict[float, str]`・`value: str`・`diode_offset: tuple[float, float]`・`diode_angle: int`・`stab_offset: dict[float, float]`・`stab_fp: dict[float, str]`・`stab_kind: str | None`。メソッド `footprint(w_u) -> str`・`stab_offset_for(w_u) -> float | None`）、`foundry.mech.SWITCHES: dict[str, Switch]`、`foundry.mech.switch_of(spec) -> Switch`、`foundry.mech.stab_flipped(key, keys) -> bool`（据え置き）、`foundry.mech.STAB_KERF`（据え置き）

- [ ] **Step 1: 失敗する検査を書く** — `tests/test_mech.py`

```python
"""スイッチの種類。**既定値で埋めない**——spec.py に書いていない種類で黙って作らない。"""

import types

import pytest

from foundry import mech
from foundry.project import load


def test_the_reference_machine_names_mx_hotswap(hhkb_ref):
    sw = mech.switch_of(load(hhkb_ref).spec)
    assert sw is mech.SWITCHES["mx_hotswap"]
    assert (sw.cutout, sw.plate_t, sw.value) == (14.0, 1.5, "CPG151101S11-2")


def test_an_unknown_switch_name_is_refused():
    with pytest.raises(ValueError, match="SWITCHES"):
        mech.switch_of(types.SimpleNamespace(SWITCH="alps"))


def test_a_spec_without_switch_is_refused(hhkb_ref, tmp_path):
    import shutil

    d = tmp_path / "p"
    shutil.copytree(hhkb_ref, d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    s = d / "spec.py"
    s.write_text("\n".join(l for l in s.read_text().splitlines() if not l.startswith("SWITCH")))
    with pytest.raises(AttributeError, match="SWITCH"):
        load(d)


def test_a_width_without_footprint_is_refused():
    with pytest.raises(RuntimeError, match="1.25u"):
        mech.SWITCHES["mx_hotswap"].footprint(1.25)
```

- [ ] **Step 2: 失敗することを確かめる**

Run: `.venv/bin/pytest tests/test_mech.py -q`
Expected: FAIL（`AttributeError: module 'foundry.mech' has no attribute 'switch_of'`）

- [ ] **Step 3: `foundry/mech.py` を置き換える**

```python
"""スイッチ・スタビ・ソケットの規格値。**プレートと基板が共有する。**

スイッチの種類ごとの値は `Switch` 1 つにまとめ、機種は spec.py の `SWITCH` で
名指しする（**既定値で埋めない**。書いていない種類で黙って作らない）。
同じ寸法を 2 箇所に書かない（HHKB でネジ位置をプレートとケースで別々に持ち、
食い違わせた）。KiCad の Python（3.9）からも import されるので標準ライブラリだけ。
"""

from __future__ import annotations

from dataclasses import dataclass

# [記録のみ] ケースを設計するときの値（MX 規格）。いまの生成器は読まない
PLATE_TO_PCB = 3.5       # プレート下面から基板上面まで 5.0 − 1.5

# プレートのスタビ開口を規格の輪郭から外へ広げる量（片側）。
# swillkb のパス（kerf=0）は実物のハウジング（6.804）より片側 0.027 狭い。
# 刷ったプレートで実物に片側 0.1 空くように 0.1 + 0.05（HHKB #30 の実測）。
# スタビは基板保持なので広げてよい。**スイッチの開口は広げてはいけない**（プレート保持）。
STAB_KERF = 0.15


@dataclass(frozen=True)
class Switch:
    """スイッチ 1 種類の規格値。

    fp          キー幅(u) → フットプリント名（lib/keyswitch.pretty）。**無い幅は落とす**
    value       基板の Value。JLC の部品照合に使われる（キー名を入れると BOM から漏れる）
    diode_offset / diode_angle  ダイオード（裏面）の置き場所。KiCad 座標（Y 下向き）で
                キー中心から
    stab_offset キー幅(u) → スタビ支点の半間隔。2u 未満は不要
    stab_fp     半間隔 → 基板のスタビのフットプリント（基板に穴の要らない種類は空）
    stab_kind   プレートのスタビ開口の形（plate.py が解釈する）。None は未定義
    """

    name: str
    cutout: float
    plate_t: float
    fp: dict
    value: str
    diode_offset: tuple
    diode_angle: int
    stab_offset: dict
    stab_fp: dict
    stab_kind: object

    def footprint(self, w_u):
        if w_u not in self.fp:
            raise RuntimeError(f"{self.name}: {w_u}u のフットプリントが無い。"
                               "近い幅で代用しない（mech.py の fp に足す）")
        return self.fp[w_u]

    def stab_offset_for(self, w_u):
        """幅 w_u のキーに要るスタビ半間隔。2u 未満は不要で None。"""
        if w_u < 2.0:
            return None
        if w_u not in self.stab_offset:
            raise ValueError(f"{self.name}: {w_u}u のスタビ間隔が未定義。"
                             "プレートと基板の両方に効くので mech.py に足す")
        return self.stab_offset[w_u]


# MX 互換・Kailh ホットスワップ（CPG151101S11-2）。HHKB で発注済みの値。
# スタビ半間隔は Cherry 規格（0.47in = 11.938 / 0.75in = 19.05）。
# **2〜2.75u は同じ 2u スタビ**。3u は国内で買えなかった（HHKB・2026-08-31）。
# ダイオード: 縦置きにしてソケットの端子 2（+5.842, −5.08）と同じ x に並べると
# スイッチ → ダイオードが L 字 2 本で済む。x 7.3 は位置決めポスト（外周 5.955）と
# 禁止域 ±1.15 を避ける値。y 2.0 は中央ポスト（φ4）を避け、行のバスを y 3.65 に通せる
MX_HOTSWAP = Switch(
    name="mx_hotswap",
    cutout=14.0,            # MX 標準のプレート開口
    plate_t=1.5,            # MX のプレート厚（FR4 1.6 でも成立）
    fp={1.0: "SW_Hotswap_Kailh_MX_1.00u", 1.5: "SW_Hotswap_Kailh_MX_1.50u",
        1.75: "SW_Hotswap_Kailh_MX_1.75u", 2.25: "SW_Hotswap_Kailh_MX_2.25u",
        2.75: "SW_Hotswap_Kailh_MX_2.75u", 3.0: "SW_Hotswap_Kailh_MX_3.00u"},
    value="CPG151101S11-2",
    diode_offset=(7.3, 2.0),
    diode_angle=90,
    stab_offset={2.0: 11.938, 2.25: 11.938, 2.5: 11.938, 2.75: 11.938,
                 3.0: 19.05, 6.25: 50.0, 7.0: 57.15},
    stab_fp={11.938: "Stabilizer_Cherry_MX_2.00u", 19.05: "Stabilizer_Cherry_MX_3.00u"},
    stab_kind="cherry",
)

SWITCHES = {s.name: s for s in (MX_HOTSWAP,)}


def switch_of(spec):
    """spec.SWITCH の種類。**知らない名前は落とす。**"""
    if spec.SWITCH not in SWITCHES:
        raise ValueError(f"SWITCH = {spec.SWITCH!r} は mech.SWITCHES に無い: {sorted(SWITCHES)}")
    return SWITCHES[spec.SWITCH]


def stab_flipped(key, keys):
    """スタビを 180° 回す（ワイヤを奥へ）か。**最前列のキーだけ回す。**

    素の向きだと大穴 φ3.988 が手前に来る。HHKB のスペースでは基板前縁まで
    0.381mm しか残らず、外形公差 ±0.2 で 0.18mm の橋になった（#53）。
    回すと 2.14mm。市販基板でもスペースのスタビはワイヤ奥が普通。
    """
    return round(key.y_mm, 2) == max(round(k.y_mm, 2) for k in keys)
```

- [ ] **Step 4: `foundry/project.py` の REQUIRED に `SWITCH` を足す**

```python
REQUIRED = ("NAME", "LAYOUT", "PIECES", "SWITCH", "PLATE_MARGIN_X", "PLATE_MARGIN_Y",
            "CORNER_R", "PCB_INSET_X", "PCB_INSET_Y", "MOUNTS")
```

- [ ] **Step 5: `foundry/plate.py` を `Switch` から読むように直す**

import を置き換える:

```python
from .layout import centered
from .mech import STAB_KERF, stab_flipped, switch_of
```

`build_plate` を置き換える（`stab_polygon`・`stab_cutout_face`・`plate_size` はそのまま）:

```python
def build_plate(spec, keys, piece):
    """1 枚のプレート。返り値は (part, (幅, 奥行), キー中心の並び)。"""
    sw = switch_of(spec)
    positions, _ = centered(keys)
    w, h = plate_size(spec, keys)
    stabs = [(pos, sw.stab_offset_for(k.w_u), stab_flipped(k, keys))
             for pos, k in zip(positions, keys)]
    with BuildPart() as plate:
        with BuildSketch():
            RectangleRounded(w, h, spec.CORNER_R)
            with Locations(*positions):
                Rectangle(sw.cutout, sw.cutout, mode=Mode.SUBTRACT)
            for pos, s, f in stabs:
                if s is None:
                    continue
                if sw.stab_kind != "cherry":
                    raise NotImplementedError(
                        f"{sw.name}: スタビ開口 {sw.stab_kind!r} の形が plate.py に無い")
                add(stab_cutout_face(s, at=pos, flipped=f), mode=Mode.SUBTRACT)
            mounts = spec.MOUNTS[piece]
            if mounts:
                with Locations(*mounts):
                    Circle(M2_CLEAR_D / 2, mode=Mode.SUBTRACT)
        extrude(amount=sw.plate_t)
    return plate.part, (w, h), positions
```

`main` の表示行の `PLATE_T` を `switch_of(p.spec).plate_t` に替える:

```python
        print(f"{'OK' if mesh.is_watertight else 'NG'} {piece:6s} {len(keys):3d} keys "
              f"{w:7.2f} x {h:6.2f} x {switch_of(p.spec).plate_t}mm 水密={mesh.is_watertight}")
```

- [ ] **Step 6: `foundry/pcb.py` を `Switch` から読むように直す**

import（28〜30 行）を置き換える:

```python
from foundry.mech import stab_flipped, switch_of                   # noqa: E402
```

`build` の中、`n_stab = 0` の直前に `kind = switch_of(spec)` を足し、ループの冒頭〜ダイオード位置を次に置き換える:

```python
    kind = switch_of(spec)
    n_stab = 0
    for i, ((kx, ky), k, (r, c)) in enumerate(zip(positions, keys, rc), start=1):
        sw = _load(KEYSWITCH_LIB, kind.footprint(k.w_u))
        sw.SetPosition(to_kicad(kx, ky))
        sw.SetReference(f"SW{i}")
        # Value は JLC の部品照合に使われる。キー名を入れると BOM から静かに漏れる（HHKB）
        sw.SetValue(kind.value)
        board.Add(sw)
        s = kind.stab_offset_for(k.w_u)
        if s is not None and s in kind.stab_fp:
            st = _load(KEYSWITCH_LIB, kind.stab_fp[s])
            st.SetPosition(to_kicad(kx, ky))
            if stab_flipped(k, keys):
                st.SetOrientationDegrees(180)
            st.SetReference(f"ST{i}")
            board.Add(st)
            n_stab += 1
```

ダイオードの位置と向き:

```python
        d.SetPosition(pcbnew.VECTOR2I_MM(ORIGIN[0] + kx + kind.diode_offset[0],
                                         ORIGIN[1] - ky + kind.diode_offset[1]))
        d.SetOrientationDegrees(kind.diode_angle)
```

モジュールの docstring の「フットプリントが mech.SWITCH_FP に無い」の記述が残っていれば削る（`grep -n SWITCH_FP foundry/pcb.py` で 0 件）。

- [ ] **Step 7: 機種側の宣言を足す**

`tests/fixtures/hhkb_ref/spec.py` の `PIECES = ("left", "right")` の次の行に:

```python
SWITCH = "mx_hotswap"        # HHKB は MX 互換＋Kailh ホットスワップ
```

`docs/templates/spec.py.tmpl` の `PIECES = $PIECES ...` の次の行に:

```python
SWITCH = "mx_hotswap"        # foundry/mech.py の SWITCHES のどれか（mx_hotswap / choc_v1）
```

- [ ] **Step 8: `tests/test_plate.py` の参照を直す**

import を置き換える:

```python
from foundry.mech import switch_of
```

`_solid` と `test_outline_is_key_field_plus_margins` と `test_stab_cutouts_are_on_the_wide_keys_only` を次に置き換える:

```python
def _solid(part, x, y, t=1.5):
    return part.is_inside(Vector(x, y, t / 2))


def test_outline_is_key_field_plus_margins(left):
    p, keys, part, (w, h), _ = left
    t = switch_of(p.spec).plate_t
    bb = part.bounding_box().size
    assert abs(bb.X - w) < 1e-3 and abs(bb.Y - h) < 1e-3 and abs(bb.Z - t) < 1e-3
    assert (w, h) == plate_size(p.spec, keys)


def test_stab_cutouts_are_on_the_wide_keys_only(left):
    p, keys, part, _, positions = left
    sw = switch_of(p.spec)
    for (x, y), k in zip(positions, keys):
        s = sw.stab_offset_for(k.w_u)
        if s is None:
            continue
        # スタビ支点の中心（ワイヤの向きによらず支点の x は ±s）が抜けていること
        assert not _solid(part, x + s, y) and not _solid(part, x - s, y), k.label
```

- [ ] **Step 9: 消した名前を grep して 0 件にする**

Run: `grep -rn -E "SWITCH_CUTOUT|\bPLATE_T\b|SWITCH_FP|STAB_FP|DIODE_OFFSET|DIODE_ANGLE|STAB_OFFSET\b|mech\.stab_offset_for|from foundry.mech import .*stab_offset_for" foundry tests tools lib/README.md docs/knowledge docs/templates`
Expected: 0 件。`lib/README.md` の「foundry/mech.py の SWITCH_FP」は「foundry/mech.py の `Switch.fp`」に書き換える。

- [ ] **Step 10: 全検査を回す（HHKB の再現を含む）**

Run: `REQUIRE_KICAD=1 .venv/bin/pytest tests -q`
Expected: 全部 PASS（新しい 4 件を含む）。`test_regression_hhkb.py` が 1 件でも落ちたら、整理が挙動を変えている。直すのは整理の方

- [ ] **Step 11: 故意に壊して、再現検査が気づくことを確かめる**

`MX_HOTSWAP` の `diode_offset` を `(7.4, 2.0)` に変えて `REQUIRE_KICAD=1 .venv/bin/pytest tests/test_regression_hhkb.py -q` → `test_every_key_part_sits_where_the_ordered_board_has_it` が落ちることを見る。戻して緑に戻ることを見る。

- [ ] **Step 12: コミット**

```bash
git status -sb | head -1
git add foundry/mech.py foundry/project.py foundry/plate.py foundry/pcb.py \
  tests/fixtures/hhkb_ref/spec.py docs/templates/spec.py.tmpl tests/test_plate.py \
  tests/test_mech.py lib/README.md
git diff --cached --stat
git commit -m "核: スイッチの種類（mech.Switch）を足し、MX の値を表へ移す

spec.py の SWITCH で名指しする（既定値で埋めない）。挙動は変えていない
（HHKB の再現検査が緑。diode_offset を 0.1 ずらすと落ちることを確かめた）。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 核に Kailh Choc V1（直付け）を足す

**Files:**
- Create: `lib/keyswitch.pretty/SW_Kailh_Choc_V1.kicad_mod`
- Modify: `lib/README.md`
- Modify: `foundry/mech.py`（`CHOC_V1` と `SWITCHES`）
- Create: `tests/test_choc.py`

**Interfaces:**
- Consumes: `mech.Switch`・`mech.SWITCHES`（Task 1）
- Produces: `mech.SWITCHES["choc_v1"]`（`cutout=13.8`・`plate_t=1.2`・`value="PG1350"`・`fp` は 1/1.5/1.75/2.25u とも `"SW_Kailh_Choc_V1"`・`stab_kind=None` と `stab_offset={}`〔Task 3 で埋める〕）

- [ ] **Step 1: フットプリントを取り込む**

```bash
curl -sL -o lib/keyswitch.pretty/SW_Kailh_Choc_V1.kicad_mod \
  https://raw.githubusercontent.com/perigoso/keyswitch-kicad-library/main/library/footprints/Switch_Keyboard_Kailh.pretty/SW_Kailh_Choc_V1.kicad_mod
grep -c "(pad " lib/keyswitch.pretty/SW_Kailh_Choc_V1.kicad_mod
```

Expected: パッドの行が 5 個以上（端子 2・中心穴・ボス 2）。**幅つき（`_1.00u` など）は使わない**: キャップ外形（Dwgs.User）が Choc の 18×17 ピッチで描かれていて、19.05 ピッチでは嘘になる。パッドは全幅で同一（2026-09-23 に 1.00u と 2.25u で確認済み）。

- [ ] **Step 2: データシートの図を読み、端子の位置と向きを書き取る**

```bash
curl -sL -o /tmp/choc_v1.pdf "https://raw.githubusercontent.com/keyboardio/keyswitch_documentation/master/datasheets/Kailh/CPG135001D01-16.pdf"
pdftoppm -r 150 -png /tmp/choc_v1.pdf /tmp/choc_v1
```

生成した PNG を Read で見て、「推奨 PCB 穴」の図から次を読み取る: 端子 2 本の穴径と位置・中心穴径・ボス 2 本の径と位置・プレート開口・**端子がキーのどちら側（LED 窓・ステムの向きに対して）にあるか**。KiCad 座標（Y 下向き、キーの手前が +Y）に直して `tests/test_choc.py` の `DATASHEET` に書く。**2 つのライブラリ（kiswitch・Keebio）は端子を (0, −5.9)・(5, −3.8) に置いている**——図がこれと 90° 違って見えたら、図の座標軸の向きを取り違えていないかを先に疑い、決着しなければ作業を止めて利用者に図を見せる。

- [ ] **Step 3: 失敗する検査を書く** — `tests/test_choc.py`

`DATASHEET` の数値は Step 2 で読んだ値を入れる。下は kiswitch の値で、図と一致していた場合の形:

```python
"""Kailh Choc V1 のフットプリントを**データシートと**突き合わせる。

自分の生成物どうしの一致は検証ではない。相手は Kailh の図面
CPG135001D01（keyboardio/keyswitch_documentation に保存された PDF）。
座標は KiCad（キー中心が原点・Y 下向き）。
"""

import re

from conftest import ROOT
from foundry.mech import SWITCHES

FP = ROOT / "lib" / "keyswitch.pretty" / "SW_Kailh_Choc_V1.kicad_mod"

# CPG135001D01 の推奨 PCB 穴（図から読んだ値。読んだ日と図の番号を書く）
DATASHEET = {
    "pins": {"1": (0.0, -5.9), "2": (5.0, -3.8)},   # 端子 φ1.2 相当の穴
    "pin_drill_min": 1.2,
    "center": 3.4,                                   # 中心の穴
    "bosses": [(-5.5, 0.0), (5.5, 0.0)],
    "boss_d": 1.9,
    "plate_cutout": 13.8,
}


def _pads():
    out = []
    for m in re.finditer(r"\(pad \"?([^\"\s]*)\"? (\w+) circle \(at ([-\d.]+) ([-\d.]+)\)"
                         r".*?\(drill ([\d.]+)\)", FP.read_text(), re.S):
        num, kind, x, y, drill = m.groups()
        out.append((num, kind, float(x), float(y), float(drill)))
    return out


def test_the_pins_are_where_the_datasheet_puts_them():
    pads = _pads()
    assert len(pads) >= 5                                 # 空の集合で緑にしない
    for num, (x, y) in DATASHEET["pins"].items():
        hit = [p for p in pads if p[0] == num and p[1] == "thru_hole"]
        assert hit, f"端子 {num} が無い"
        assert all(abs(p[2] - x) < 0.05 and abs(p[3] - y) < 0.05 for p in hit), hit
        assert all(p[4] >= DATASHEET["pin_drill_min"] for p in hit), hit


def test_the_center_hole_and_bosses_match():
    npth = [p for p in _pads() if p[1] == "np_thru_hole"]
    centre = [p for p in npth if abs(p[2]) < 1e-6 and abs(p[3]) < 1e-6]
    assert centre and centre[0][4] >= DATASHEET["center"], centre
    for bx, by in DATASHEET["bosses"]:
        b = [p for p in npth if abs(p[2] - bx) < 0.05 and abs(p[3] - by) < 0.05]
        assert b and b[0][4] >= DATASHEET["boss_d"], (bx, by, npth)


def test_the_switch_table_uses_this_footprint_and_the_datasheet_cutout():
    sw = SWITCHES["choc_v1"]
    assert set(sw.fp.values()) == {FP.stem}
    assert sw.cutout == DATASHEET["plate_cutout"]
    assert sw.plate_t == 1.2                  # Choc スタビがプレート 1.2mm を要求（設計書 D2）


def test_the_checker_notices_a_moved_pin(tmp_path, monkeypatch):
    """**検査器が壊れていないか。**端子 2 を 0.1mm 動かした偽物で落ちること。"""
    import pytest

    import test_choc

    fake = tmp_path / FP.name
    fake.write_text(FP.read_text().replace("(at 5 -3.8)", "(at 5.1 -3.8)"))
    monkeypatch.setattr(test_choc, "FP", fake)
    with pytest.raises(AssertionError):
        test_choc.test_the_pins_are_where_the_datasheet_puts_them()
```

- [ ] **Step 4: 失敗することを確かめる**

Run: `.venv/bin/pytest tests/test_choc.py -q`
Expected: `test_the_switch_table_uses_...` が `KeyError: 'choc_v1'` で FAIL。ほかの 3 件は PASS（フットプリントがデータシートと一致している）。**もしパッドの検査が落ちたら、フットプリントを直さず作業を止めて報告する**（どちらが正しいかは図で決める）

- [ ] **Step 5: `foundry/mech.py` に Choc V1 を足す**

`MX_HOTSWAP` の定義の後、`SWITCHES` の前に:

```python
# Kailh Choc V1（PG1350）を基板に**直付け**（設計書 D2・D3）。
# 開口 13.8・プレート 1.2 は Kailh の図面 CPG135001D01（tests/test_choc.py が照合）。
# 1.2mm は Choc のスタビがプレートに留まる厚さでもある。
# fp は全幅で同じ（パッドが同一。幅つきは 18×17 ピッチのキャップ外形を描くので使わない）。
# value は部品表の照合用。スイッチは JLCPCB に在庫が無く利用者が手はんだする（D3）。
# ダイオードの位置は Task 6 で DRC を通して決める（ここはその初期値）。
# スタビは Task 3 で外の事実から埋める。**それまでは 2u 以上のキーで落ちる。**
CHOC_V1 = Switch(
    name="choc_v1",
    cutout=13.8,
    plate_t=1.2,
    fp={w: "SW_Kailh_Choc_V1" for w in (1.0, 1.5, 1.75, 2.25)},
    value="PG1350",
    diode_offset=(7.6, -1.0),
    diode_angle=90,
    stab_offset={},
    stab_fp={},
    stab_kind=None,
)

SWITCHES = {s.name: s for s in (MX_HOTSWAP, CHOC_V1)}
```

（もとの `SWITCHES = {s.name: s for s in (MX_HOTSWAP,)}` の行は消す。二重定義は test_meta が落とす）

- [ ] **Step 6: 通ることを確かめる**

Run: `.venv/bin/pytest tests/test_choc.py tests/test_mech.py tests/test_meta.py -q`
Expected: PASS

- [ ] **Step 7: `lib/README.md` に記録を足す**

表に行を足す: `| SW_Kailh_Choc_V1 | Choc V1 直付け（CCKB）。全幅で共用 |`。「寸法を検証した記録」に、Step 2 で読んだ図の値と `tests/test_choc.py` の照合結果（端子・中心穴・ボス・開口）、出典（kiswitch 上流の URL とコミット日・Kailh CPG135001D01）、幅つきを使わない理由を書く。

- [ ] **Step 8: コミット**

```bash
git status -sb | head -1
git add lib/keyswitch.pretty/SW_Kailh_Choc_V1.kicad_mod lib/README.md foundry/mech.py tests/test_choc.py
git diff --cached --stat
git commit -m "核: Kailh Choc V1（直付け）を足す。フットプリントを Kailh の図面と照合

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Choc スタビの寸法を外の事実で確定する（設計書 §8 O2 を含む）

**なぜ要るか:** Enter・左 Shift・スペース左右の 4 キー（2.25u）にスタビが要る。プレートの開口と、基板に穴が要るかどうかは、スタビの寸法で決まる。**kiswitch にも Kailh の図面集にも Choc スタビの図は無かった**（2026-09-23 に確認）。推測で開口を切ると、刷った板・発注した基板が無駄になる。

**Files:**
- Modify: `foundry/mech.py`（`CHOC_V1` の `stab_offset`・`stab_fp`・`stab_kind`）
- Modify: `foundry/plate.py`（`stab_kind == "choc"` の開口）
- Create: `projects/cckb/docs/decisions/2026-09-XX-choc-stabilizer.md`（Task 4 の後に置く。日付は実施日）
- Test: `tests/test_choc.py` に追記

**Interfaces:**
- Produces: `mech.SWITCHES["choc_v1"].stab_offset_for(2.25) -> float`（支点の半間隔）、`stab_kind == "choc"`、`plate.choc_stab_polygon(s, at, flipped) -> list[tuple[float, float]]`

- [ ] **Step 1: 図面を探す（上から順に。見つかったら止める）**

1. Kailh 公式（kailh.com / kailhswitch.com）の「Choc stabilizer」「PG1350 stabilizer」の製品ページと PDF
2. 遊舎工房の商品ページ（`https://shop.yushakobo.jp/products/a0500st-00-1`）の画像・寸法
3. EasyEDA の部品「KAILH PG1350 CHOC 2U STABILIZER PCB CUTOUT」（`https://easyeda.com/components/KAILH-PG1350-CHOC-2U-STABILIZER-PCB-CUTOUT_1fa68b8ca3bd48e5ad9f008e6bba0314`）
4. 公開されている Choc 配列のキーボードで、スタビを使っている KiCad / プレートの DXF（例: Keebio の Choc 対応基板、Sofle Choc）。**2 つ以上の独立した出所で一致した値だけを使う**

書き取る値: 支点の半間隔（2u 用）・プレート開口の輪郭（各頂点）・プレートの下に出る部分の寸法（基板との隙間 1.0mm に収まるか。収まらなければ基板の逃げ穴の位置と径）・**CFX の 2.25u キャップのステム位置と合うか**（設計書 O2）。

- [ ] **Step 2: 分岐**

- **2 つ以上の出所で一致した**: Step 3 へ
- **見つからない／一致しない**: ここで止める。`projects/cckb/docs/open-gaps.md` の「★ 発注をせき止めているもの」に「Choc スタビの寸法」を立て、**利用者に「本番の品番（Kailh Choc スタビ 2u・遊舎工房 ¥550）と CFX の 2.25u キャップを先に買い、ノギスで採寸する」ことを提案する**（購入は利用者の判断）。Task 5 のプレートと Task 6 の基板は、スタビの無いキーだけで進められないので、Task 4・7・8 を先にやる

- [ ] **Step 3: 検査を先に書く** — `tests/test_choc.py` に追記。値は Step 1 の出所の値

```python
# Choc スタビ（2u）。出所を 2 つ書く（例: Kailh の図面・EasyEDA の外形）
STAB = {"half_span": None, "outline": None}   # ← Step 1 の値で置き換える（None のまま残さない）


def test_the_stab_table_matches_the_sources():
    sw = SWITCHES["choc_v1"]
    assert STAB["half_span"] is not None, "Step 1 の値を入れる"
    assert sw.stab_kind == "choc"
    for w in (2.0, 2.25):
        assert abs(sw.stab_offset_for(w) - STAB["half_span"]) < 1e-3


def test_the_plate_opening_is_the_sourced_outline():
    from foundry.plate import choc_stab_polygon

    pts = choc_stab_polygon(STAB["half_span"])
    assert [(round(x, 3), round(y, 3)) for x, y in pts] == \
        [(round(x, 3), round(y, 3)) for x, y in STAB["outline"]]
```

- [ ] **Step 4: 落ちることを確かめる**（`choc_stab_polygon` が無い・`stab_kind` が None）

Run: `.venv/bin/pytest tests/test_choc.py -q` → FAIL

- [ ] **Step 5: 実装する**

`foundry/plate.py` に、出所の輪郭を返す関数（`stab_polygon` と同じ規約: 中心 `at`、`flipped` でワイヤを奥へ、Y 上向き）を足し、`build_plate` の `stab_kind` の分岐を次にする:

```python
                if sw.stab_kind == "cherry":
                    add(stab_cutout_face(s, at=pos, flipped=f), mode=Mode.SUBTRACT)
                elif sw.stab_kind == "choc":
                    add(stab_cutout_face(s, at=pos, flipped=f, polygon=choc_stab_polygon),
                        mode=Mode.SUBTRACT)
                else:
                    raise NotImplementedError(
                        f"{sw.name}: スタビ開口 {sw.stab_kind!r} の形が plate.py に無い")
```

`stab_cutout_face` に引数 `polygon=stab_polygon` を足し、`Polyline(*polygon(s, at=at, flipped=flipped), close=True)` にする。`mech.CHOC_V1` の `stab_offset` に `{2.0: 値, 2.25: 値}`、`stab_kind="choc"`、基板に逃げ穴が要るなら `stab_fp` とフットプリント（`lib/keyswitch.pretty/`）を足す。

- [ ] **Step 6: 通す・壊す・戻す**

`REQUIRE_KICAD=1 .venv/bin/pytest tests -q` が緑。`STAB["half_span"]` を 0.1 ずらして落ちることを見て戻す。

- [ ] **Step 7: 決定記録を書き、コミット**

`projects/cckb/docs/decisions/<日付>-choc-stabilizer.md`（雛形 docs/templates/decision.md）に、出所 2 つ・値・CFX 2.25u との適合・基板の逃げ穴の要否を書く。

```bash
git status -sb | head -1
git add foundry/mech.py foundry/plate.py tests/test_choc.py projects/cckb/docs/decisions/
git commit -m "核: Choc スタビ（2u）の寸法を 2 つの出所から入れる

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 機種 cckb を作り、要求（HHKB 準拠）を検査にする

**Files:**
- Create: `tests/fixtures/hhkb_original.json`（HHKB リポジトリの `layout/hhkb_original.json` をそのまま写す）
- Create: `/tmp/cckb_layout.json`（作業用）→ `projects/cckb/`（`tools/new_project.py` が作る）
- Modify: `projects/cckb/spec.py`・`projects/cckb/docs/provisional-values.md`
- Create: `tests/test_cckb.py`

**Interfaces:**
- Consumes: `mech.SWITCHES["choc_v1"]`（Task 2）
- Produces: `projects/cckb/`（`load("cckb")` で読める。`PIECES == ("main",)`・62 キー）

- [ ] **Step 1: 外の事実を fixtures に写す**

```bash
cp ../2608042258_HHKB_devided/layout/hhkb_original.json tests/fixtures/hhkb_original.json
```

（出所は先頭のメタデータに書いてある: QMK `keyboards/hhkb/ansi/info.json` と Wikimedia の KLE 図）

- [ ] **Step 2: CCKB の配列を作る**（スペースだけを 2.25＋1.5＋2.25 に替える）

```bash
.venv/bin/python3 - <<'EOF'
import json
src = json.load(open("tests/fixtures/hhkb_original.json"))
row = src[-1]
i = row.index("Space")
assert row[i - 1] == {"w": 6}, row
row[i - 1:i + 1] = [{"w": 2.25}, "Space", {"w": 1.5}, "Space", {"w": 2.25}, "Space"]
src[0] = {"name": "CCKB",
          "notes": "HHKB 英語配列（tests/fixtures/hhkb_original.json）のスペース 6u を "
                   "2.25u+1.5u+2.25u に分けたもの。設計書 docs/superpowers/specs/2026-09-23-cckb-design.md §1"}
json.dump(src, open("/tmp/cckb_layout.json", "w"), ensure_ascii=False, indent=1)
EOF
.venv/bin/python3 tools/new_project.py cckb /tmp/cckb_layout.json
```

Expected: `作った projects/cckb/` と、シールドの雛形 `config/boards/shields/cckb/` の各ファイル。`&none にした刻印` が出たら一覧を控える（Task 7 で埋める）。

- [ ] **Step 3: 失敗する検査を書く** — `tests/test_cckb.py`

```python
"""CCKB の要求。**HHKB 英語配列の実物の KLE と突き合わせる**（設計書 §1）。

守るもの: スペース以外の全キーの中心・幅・刻印、ピッチ、最下段の空き（左 1.5u・右 2.5u）、
スペースが 4.0〜10.0u を 3 キーで隙間なく覆うこと。
"""

from conftest import FIXTURES
from foundry import paths
from foundry.layout import UNIT, load_layout
from foundry.project import load

HHKB = FIXTURES / "hhkb_original.json"


def _row(k):
    return round(k.y_mm / UNIT - 0.5)


def differences(ours, ref):
    """スペース以外で、HHKB と違うキーを返す（空なら準拠）。"""
    key = lambda k: (_row(k), round(k.left_u, 4))
    a = {key(k): k for k in ours if k.label != "Space"}
    b = {key(k): k for k in ref if k.label != "Space"}
    out = sorted(f"{p}: {'無い' if p not in a else ''}{'余分' if p not in b else ''}"
                 for p in set(a) ^ set(b))
    for p in set(a) & set(b):
        if (a[p].label, a[p].w_u, round(a[p].x_mm, 4), round(a[p].y_mm, 4)) != \
           (b[p].label, b[p].w_u, round(b[p].x_mm, 4), round(b[p].y_mm, 4)):
            out.append(f"{p}: {a[p]} / HHKB {b[p]}")
    return out


def test_every_key_but_space_is_where_the_hhkb_has_it():
    ours = load("cckb").keys()
    ref = load_layout(HHKB)
    assert len(ref) == 60 and len(ours) == 62            # 空どうしで緑にしない
    assert differences(ours, ref) == []


def test_the_three_space_keys_cover_the_hhkb_space_exactly():
    ref = [k for k in load_layout(HHKB) if k.label == "Space"]
    sp = sorted((k for k in load("cckb").keys() if k.label == "Space"), key=lambda k: k.x_mm)
    assert [k.w_u for k in sp] == [2.25, 1.5, 2.25]
    assert abs(sp[0].left_u - ref[0].left_u) < 1e-9 and abs(sp[-1].right_u - ref[0].right_u) < 1e-9
    assert all(abs(a.right_u - b.left_u) < 1e-9 for a, b in zip(sp, sp[1:]))   # 隙間なし
    assert len({round(k.y_mm, 4) for k in sp + ref}) == 1


def test_the_bottom_row_leaves_the_hhkb_corners_empty():
    bottom = [k for k in load("cckb").keys() if _row(k) == 4]
    assert min(k.left_u for k in bottom) == 1.5 and max(k.right_u for k in bottom) == 12.5


def test_the_checker_notices_a_moved_key(tmp_path):
    """**検査器が壊れていないか。**Q を 0.25u 動かした配列で差が出ること。"""
    import json

    raw = json.loads(HHKB.read_text())
    row = raw[2]
    row.insert(row.index("Q"), {"x": 0.25})
    f = tmp_path / "moved.json"
    f.write_text(json.dumps(raw))
    assert differences(load_layout(f), load_layout(HHKB))


def test_the_machine_uses_choc_v1():
    from foundry.mech import switch_of

    assert switch_of(load("cckb").spec).name == "choc_v1"
    assert (paths.PROJECTS / "cckb" / "layout.json").exists()
```

- [ ] **Step 4: 失敗することを確かめる**

Run: `.venv/bin/pytest tests/test_cckb.py -q`
Expected: `test_the_machine_uses_choc_v1` が FAIL（雛形の `SWITCH = "mx_hotswap"`）。ほかは PASS（配列は Step 2 で作った）。`test_the_checker_notices_a_moved_key` が PASS すること＝検査器が生きている。

- [ ] **Step 5: `projects/cckb/spec.py` を書く**

雛形を次の内容に置き換える（`[暫定]` は計画 2 のケース設計で確定する）:

```python
"""CCKB（Completely Compact KeyBoard）の設計値。**寸法・部品・行列の決定はここに集める。**

持ち運び用の HHKB 英語配列準拠キーボード。設計書: docs/superpowers/specs/2026-09-23-cckb-design.md
要求（HHKB 準拠）は tests/test_cckb.py が HHKB の実物の KLE と突き合わせる。
値ごとに**なぜその値か**を書く。`[暫定]` は docs/provisional-values.md に同じ数値で載せる。
"""

NAME = "CCKB"                # 基板に刷る名前（他社の商標 HHKB は刷らない）
LAYOUT = "layout.json"       # HHKB 英語配列のスペースを 2.25+1.5+2.25u に分けたもの
PIECES = ("main",)           # 一体型（設計書 D1）
SWITCH = "choc_v1"           # Kailh Choc V1 直付け（設計書 D2・D3）

# キー領域からプレート外形までの余白（片側）。ケースの上枠がプレートの縁を押さえる
# 形は計画 2 で決める。それまでキー領域ちょうど（外周のキーの開口の外に 2.625mm の桟）
PLATE_MARGIN_X = 0.0         # [暫定] 計画 2（ケース）で決める
PLATE_MARGIN_Y = 0.0         # [暫定] 計画 2（ケース）で決める
CORNER_R = 1.0               # [暫定] 計画 2（ケース）で決める
# 基板はキー領域いっぱい。角（XIAO・電池）もキー領域の外接矩形の中にある
PCB_INSET_X = 0.0            # [暫定] 計画 2（ケース）で決める
PCB_INSET_Y = 0.0            # [暫定] 計画 2（ケース）で決める

# 取付ネジ（計画 2 で 5 条件を同時に満たす位置を決める。設計書 O4）
MOUNTS = {"main": []}

MATRIX_COLUMNS = "physical"

ZMK = {
    "shield": "cckb",
    "board": "xiao_ble//zmk",
}
```

`projects/cckb/docs/provisional-values.md` の表を次にする:

```markdown
| 定数 | 現在値 | 何の値か | どうやって確かめるか | 外したときの影響 |
|---|---|---|---|---|
| `PLATE_MARGIN_X` | 0.0 | キー領域からプレート外形まで（左右） | 計画 2 のケースの断面図 | 上枠がプレートを押さえられない |
| `PLATE_MARGIN_Y` | 0.0 | 同（前後） | 同上 | 同上 |
| `CORNER_R` | 1.0 | プレート・基板の角の丸み | 同上 | 上枠との合い |
| `PCB_INSET_X` | 0.0 | プレート外形から基板外形まで（左右） | 同上 | 基板がケースの壁に当たる |
| `PCB_INSET_Y` | 0.0 | 同（前後） | 同上 | 同上 |
```

- [ ] **Step 6: 通す**

Run: `.venv/bin/pytest tests/test_cckb.py tests/test_meta.py -q`
Expected: PASS

- [ ] **Step 7: コミット**

```bash
git status -sb | head -1
git add tests/fixtures/hhkb_original.json tests/test_cckb.py projects/cckb build.yaml config/boards/shields/cckb
git diff --cached --stat
git commit -m "機種 cckb: HHKB 英語配列のスペースを 3 分割した配列と、準拠の検査

HHKB の実物の KLE（QMK・Wikimedia）と全キーを突き合わせる。Q を 0.25u
動かすと差が出ることを確かめた。

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: プレート（角を抜く・Choc の開口）を生成して見る

**Files:**
- Modify: `foundry/plate.py`（`PLATE_OPENINGS` を抜く）
- Modify: `projects/cckb/spec.py`（`PLATE_OPENINGS: dict[str, list[tuple[float, float, float, float]]]`。中心 x, 中心 y, 幅, 奥行。CAD 座標）
- Modify: `docs/templates/spec.py.tmpl`（`PLATE_OPENINGS = {p: [] for p in PIECES}`）
- Modify: `tests/fixtures/hhkb_ref/spec.py`（`PLATE_OPENINGS = {"left": [], "right": []}`）
- Test: `tests/test_cckb.py`

**Interfaces:**
- Consumes: `spec.PLATE_OPENINGS`（Task 4）・`switch_of`（Task 1）
- Produces: `build/cckb/plate_main.stl`・`plate_main.png`

- [ ] **Step 0: spec.py に角の開口を書き、配列の空きと一致する検査を足す**

`projects/cckb/spec.py` の `MOUNTS` の後に:

```python
# プレートの開口（キー以外）。最下段の空いた角には XIAO（左）と電池ホルダ（右）が
# 基板の表に立つので、プレートを抜く（プレート下面と基板の隙間は 1.0mm しかない）。
# CAD 座標（キー領域の中心が原点・Y 上向き・mm）で (中心 x, 中心 y, 幅, 奥行)。
# キー領域は 15u × 5u（285.75 × 95.25）。左の角は x 0〜1.5u、右の角は 12.5〜15u、
# どちらも最下段（y は −47.625〜−28.575）。tests/test_cckb.py が配列から導いた角と照合する
PLATE_OPENINGS = {"main": [
    (-142.875 + 0.75 * 19.05, -38.1, 1.5 * 19.05, 19.05),
    (-142.875 + 13.75 * 19.05, -38.1, 2.5 * 19.05, 19.05),
]}
```

`tests/test_cckb.py` に追記:

```python
def test_the_plate_openings_are_exactly_the_empty_corners():
    from foundry.layout import centered

    p = load("cckb")
    keys = p.keys()
    positions, (kw, kh) = centered(keys)
    bottom = [(pos, k) for pos, k in zip(positions, keys) if _row(k) == 4]
    y_bottom = bottom[0][0][1]
    left_edge = min(pos[0] - k.w_mm / 2 for pos, k in bottom)
    right_edge = max(pos[0] + k.w_mm / 2 for pos, k in bottom)
    expect = [((-kw / 2 + left_edge) / 2, y_bottom, left_edge + kw / 2, UNIT),
              ((right_edge + kw / 2) / 2, y_bottom, kw / 2 - right_edge, UNIT)]
    got = p.spec.PLATE_OPENINGS["main"]
    assert len(got) == 2
    for g, e in zip(got, expect):
        assert all(abs(a - b) < 1e-6 for a, b in zip(g, e)), (g, e)
```

- [ ] **Step 1: 失敗する検査を書く** — `tests/test_cckb.py` に追記

```python
import pytest


@pytest.fixture(scope="module")
def plate():
    from foundry.plate import build_plate

    p = load("cckb")
    part, size, positions = build_plate(p.spec, p.keys(), "main")
    return p, part, size, positions


def _solid(part, x, y):
    from build123d import Vector

    return part.is_inside(Vector(x, y, 0.6))


def test_the_plate_is_open_at_every_key_and_at_both_corners(plate):
    p, part, _, positions = plate
    assert len(positions) == 62
    for x, y in positions:
        assert not _solid(part, x, y)
    for cx, cy, w, h in p.spec.PLATE_OPENINGS["main"]:
        assert not _solid(part, cx, cy), (cx, cy)


def test_the_web_around_the_corner_keys_survives(plate):
    """角の開口が隣のキー（Alt・Shift・Fn）の周りの桟を削っていないこと（Review Focus 4）。"""
    p, part, _, positions = plate
    keys = p.keys()
    for (x, y), k in zip(positions, keys):
        if k.label in ("Alt", "Meta", "Fn", "Shift"):
            # 開口の縁（13.8/2）とキーの枠（19.05/2）の間の桟の中点
            for dx, dy in ((8.2, 0), (-8.2, 0), (0, 8.2), (0, -8.2)):
                inside_corner = any(abs(x + dx - cx) < w / 2 and abs(y + dy - cy) < h / 2
                                    for cx, cy, w, h in p.spec.PLATE_OPENINGS["main"])
                if not inside_corner:
                    assert _solid(part, x + dx, y + dy), (k.label, dx, dy)


def test_the_plate_is_1_2mm_and_printable_as_a_check(plate, tmp_path):
    from foundry.verify import to_mesh

    _, part, (w, h), _ = plate
    assert abs(part.bounding_box().size.Z - 1.2) < 1e-6
    mesh, _ = to_mesh(part, tmp_path / "plate.stl")
    assert mesh.is_watertight
```

（FR4 で JLCPCB に出すので「刷る」わけではないが、水密は形が閉じている確認として見る）

- [ ] **Step 2: 失敗することを確かめる**

Run: `.venv/bin/pytest tests/test_cckb.py -q`
Expected: `test_the_plate_is_open_at_every_key_and_at_both_corners` が角で FAIL。Task 3 が未了で 2.25u のスタビが未定義なら、`build_plate` が `ValueError: choc_v1: 2.25u のスタビ間隔が未定義` で落ちる——**正しい落ち方**。その場合は Task 3 を先に終える（飛ばす仕組みを作らない）

- [ ] **Step 3: `foundry/plate.py` で開口を抜く**

`build_plate` の `mounts = ...` の直前に:

```python
            for cx, cy, ow, oh in spec.PLATE_OPENINGS[piece]:
                with Locations((cx, cy)):
                    Rectangle(ow, oh, mode=Mode.SUBTRACT)
```

`foundry/project.py` の `REQUIRED` に `"PLATE_OPENINGS"` を足す（既定値で埋めない）。`docs/templates/spec.py.tmpl` の `MOUNTS` の後に:

```python
# プレートの開口（キー以外）。(中心 x, 中心 y, 幅, 奥行)。基板の表に背の高い部品を立てる所
PLATE_OPENINGS = {p: [] for p in PIECES}
```

`tests/fixtures/hhkb_ref/spec.py` の `MOUNTS` の後に `PLATE_OPENINGS = {"left": [], "right": []}`。

- [ ] **Step 4: 通す**

Run: `REQUIRE_KICAD=1 .venv/bin/pytest tests -q`
Expected: 全部 PASS（test_meta の `PLATE_OPENINGS` も読まれて緑）

- [ ] **Step 5: 生成して、自分の目で見る**

Run: `tools/kb cckb plate`
Expected: `OK main  62 keys  285.75 x  95.25 x 1.2mm 水密=True`。`build/cckb/plate_main.png` を Read で開き、次を見て作業記録に書く: 左下 1.5u・右下 2.5u の角が抜けている／スペースの 3 開口とスタビの開口が 2.25u のキー 4 つにだけある／外周の桟が切れていない。

- [ ] **Step 6: 故意に壊す**

`PLATE_OPENINGS` の右の角の幅を `2.6 * 19.05` にして `test_the_plate_openings_are_exactly_the_empty_corners` と `test_the_web_around_the_corner_keys_survives` が落ちることを見る。戻す。

- [ ] **Step 7: コミット**

```bash
git status -sb | head -1
git add foundry/plate.py foundry/project.py docs/templates/spec.py.tmpl tests/fixtures/hhkb_ref/spec.py tests/test_cckb.py projects/cckb/spec.py
git commit -m "プレート: spec.PLATE_OPENINGS で角を抜く。CCKB のプレートを生成

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 未配線の基板（Choc 直付け・ダイオード位置）を生成し、DRC 0 を検査にする

**Files:**
- Modify: `foundry/mech.py`（`CHOC_V1.diode_offset` を DRC で決まった値に）
- Test: `tests/test_cckb.py`
- Generated: `projects/cckb/pcb/unrouted/cckb_main.kicad_pcb`

**Interfaces:**
- Consumes: `foundry.pcb`（Task 1）・`foundry.drc.run(path) -> dict`（`violations`・`warning_kinds`・`details`）・`foundry.board_dump.key_parts(text) -> dict`
- Produces: 未配線の板（計画 3 の出発点）

- [ ] **Step 1: 失敗する検査を書く** — `tests/test_cckb.py` に追記

```python
@pytest.fixture(scope="module")
def board(tmp_path_factory):
    import shutil
    import subprocess

    from conftest import ROOT, require

    require(paths.KICAD_PYTHON, "基板の生成")
    d = tmp_path_factory.mktemp("cckb") / "cckb"
    shutil.copytree(paths.PROJECTS / "cckb", d, ignore=shutil.ignore_patterns("pcb", "__pycache__"))
    r = subprocess.run([paths.KICAD_PYTHON, "-m", "foundry.pcb", str(d)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d / "pcb" / "unrouted" / "cckb_main.kicad_pcb"


def test_the_board_has_one_switch_and_one_diode_per_key(board):
    import re

    from foundry.board_dump import key_parts

    parts = key_parts(board.read_text())
    sw = [r for r in parts if re.fullmatch(r"SW\d+", r)]
    d = [r for r in parts if re.fullmatch(r"D\d+", r)]
    assert len(sw) == 62 and len(d) == 62
    assert all(parts[r]["fp"].endswith("SW_Kailh_Choc_V1") for r in sw)
    assert all(parts[r]["back"] for r in d)                      # ダイオードは裏（D8）


def test_the_matrix_nets_are_5_rows_by_15_columns(board):
    import re

    nets = set(re.findall(r'\(net "([^"]+)"\)', board.read_text()))
    assert {n for n in nets if re.fullmatch(r"ROW\d+", n)} == {f"ROW{i}" for i in range(5)}
    assert {n for n in nets if re.fullmatch(r"COL\d+", n)} == {f"COL{i}" for i in range(15)}


def test_the_unrouted_board_has_no_drc_violations(board):
    """Review Focus 5。**警告も数えて記録する**（隠さない）。"""
    from conftest import require
    from foundry import drc

    require(paths.KICAD_CLI, "DRC")
    r = drc.run(board)
    assert r["violations"] == 0, r["details"]
    print("DRC 警告の内訳:", r["warning_kinds"])
```

（`key_parts` の返す項目名 `fp`・`back` は `foundry/board_dump.py` を読んで合わせる。違えば検査側を直す）

- [ ] **Step 2: 生成して回す**

Run: `tools/kb cckb pcb && REQUIRE_KICAD=1 .venv/bin/pytest tests/test_cckb.py -q -s`
Expected: 基板が出る（`main 基板 285.75 x 95.25mm スイッチ 62 / ダイオード 62 ...`）。DRC の検査は、初期値 `(7.6, -1.0)` で違反が出れば FAIL。

- [ ] **Step 3: ダイオードの位置を決める**

違反の中身（`details`）を読み、`CHOC_V1.diode_offset` を動かす。決める条件（全部を同時に）:
1. DRC 違反 0（隣のキーの端子・穴・ダイオードを含む）
2. ダイオードのアノード側パッドが、スイッチ端子 2（(5, −3.8)）と L 字 2 本で結べる位置（x を端子 2 に近く）
3. キーの枠（±9.525）の内側・ボス φ1.9（(±5.5, 0)）と中心穴 φ3.45 から銅で 0.3mm 以上

動かすたびに `tools/kb cckb pcb` → `tools/kb cckb render` → hook が出す絵を Read で見る。決めた値と、3 条件をどう確かめたかを `foundry/mech.py` の `CHOC_V1` のコメントに書く。

- [ ] **Step 4: 通す・壊す**

`REQUIRE_KICAD=1 .venv/bin/pytest tests -q` が緑。`diode_offset` の x を 5.0（端子 2 に重なる位置）にして DRC の検査が落ちることを見る。戻す。

- [ ] **Step 5: 絵を見る**

`tools/kb cckb render` の出力（`build/` の PNG）を Read で開き、全キーでダイオードが同じ向き・同じ場所にあること、角（左 1.5u・右 2.5u）に部品が無いこと、裏のシルクのキー名が読めることを見て作業記録に書く。

- [ ] **Step 6: コミット**

```bash
git status -sb | head -1
git add foundry/mech.py tests/test_cckb.py projects/cckb/pcb/unrouted
git commit -m "CCKB: 未配線の基板（Choc 直付け 62 キー）。ダイオード位置を DRC 0 で決める

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: ZMK シールド（595 ×2・電池・HHKB 既定のキーマップ）

**Files:**
- Modify: `config/boards/shields/cckb/cckb.overlay`・`cckb.conf`・`cckb.keymap`（雛形を置き換える）
- Generated: `config/boards/shields/cckb/cckb-transform.dtsi`（`python -m foundry.zmk cckb`）
- Modify: `projects/cckb/spec.py`（`ZMK["pins"]` は書かない。overlay を人が持つ）
- Test: `tests/test_cckb.py`

**Interfaces:**
- Consumes: `zmk.layout(project)`（キーマップの並び）・`check_zmk_config.count_bindings(path) -> list[tuple[str, int]]`
- Produces: シールド `cckb`（`build.yaml` に `xiao_ble//zmk` × `cckb`）

キーマップの並び（`zmk.layout` の順・62 キー）:
行 0: Esc 1 2 3 4 5 6 7 8 9 0 - = \ `（15）／行 1: Tab Q W E R T Y U I O P [ ] Del（14）／行 2: Ctrl A S D F G H J K L ; ' Enter（13）／行 3: Shift Z X C V B N M , . / Shift Fn（13）／行 4: Alt Meta Space Space Space Meta Alt（7）

- [ ] **Step 1: 失敗する検査を書く** — `tests/test_cckb.py` に追記

```python
SHIELD = paths.ROOT / "config" / "boards" / "shields" / "cckb"


def test_every_layer_has_62_bindings():
    from foundry.check_zmk_config import count_bindings

    layers = count_bindings(SHIELD / "cckb.keymap")
    assert [n for _, n in layers] == [62, 62, 62, 62], layers


def test_the_three_space_keys_all_send_space_on_both_bases():
    """Review Focus 2。3 つのスペースは別のスイッチで、既定では 3 つとも SPACE（設計書 §1）。"""
    import re

    from foundry import zmk

    p = load("cckb")
    rows, _ = zmk.layout(p)
    idx = [i for i, (_, k, _) in enumerate(rows) if k.label == "Space"]
    assert len(idx) == 3 and len({rows[i][2] for i in idx}) == 3     # (row, col) が別々
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", (SHIELD / "cckb.keymap").read_text(), flags=re.S)
    for layer in ("base_mac", "base_win"):
        body = re.search(layer + r"\s*\{\s*bindings\s*=\s*<(.*?)>;", text, re.S).group(1)
        binds = re.findall(r"&\w+(?:\s+[A-Z_0-9]+(?:\s+\d+)?)?", body)
        assert [binds[i].split()[-1] for i in idx] == ["SPACE"] * 3, layer


def test_the_recovery_bindings_exist():
    km = (SHIELD / "cckb.keymap").read_text()
    assert "&bootloader" in km and "&bt BT_CLR" in km        # ケースを開けずに復旧


def test_the_shield_config_passes_the_checker():
    import subprocess
    import sys

    from conftest import ROOT

    r = subprocess.run([sys.executable, "-m", "foundry.check_zmk_config"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: 失敗することを確かめる**

Run: `.venv/bin/pytest tests/test_cckb.py -q -k "bindings or space or recovery or shield"`
Expected: FAIL（雛形のキーマップは 2 層・overlay は `#error`）

- [ ] **Step 3: overlay を書く** — `config/boards/shields/cckb/cckb.overlay`

```dts
/*
 * CCKB。一体型・62 キー・5 行 × 15 列（行列は cckb-transform.dtsi・生成物）。
 * 構成は HHKB 分割機の hhkb_split.dtsi と同じ（実機で確認済み）。
 *
 * ピン（XIAO nRF52840・D0..D10）。**計画 3 の配線で行の並びを変えてよい**
 * （行の並びはファームで吸収する。配線をひねらない）:
 *   D0        電池電圧（ADC は D0..D5 だけ）
 *   D2..D6    行 0..4（MCU 直結の入力。割り込みで起きられる）
 *   D7        595 の CS（ラッチ）
 *   D8 / D10  SPI SCK / MOSI（xiao_spi）。D9 は board の pinctrl が MISO に確保
 *   D1        予備
 * 列 15 本は 74LVC595 ×2 の数珠つなぎ（&shifter 0..14。15 は空き）。
 * 74HC595 は下限 2.0V で使えない（docs/knowledge/parts.md）。
 */

#include "cckb-transform.dtsi"

/ {
	chosen {
		zmk,kscan = &kscan0;
		zmk,battery = &vbatt;
	};

	kscan0: kscan_0 {
		compatible = "zmk,kscan-gpio-matrix";
		wakeup-source;
		diode-direction = "col2row";
		row-gpios
			= <&xiao_d 2 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
			, <&xiao_d 3 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
			, <&xiao_d 4 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
			, <&xiao_d 5 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
			, <&xiao_d 6 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>
			;
		col-gpios
			= <&shifter 0 GPIO_ACTIVE_HIGH>, <&shifter 1 GPIO_ACTIVE_HIGH>
			, <&shifter 2 GPIO_ACTIVE_HIGH>, <&shifter 3 GPIO_ACTIVE_HIGH>
			, <&shifter 4 GPIO_ACTIVE_HIGH>, <&shifter 5 GPIO_ACTIVE_HIGH>
			, <&shifter 6 GPIO_ACTIVE_HIGH>, <&shifter 7 GPIO_ACTIVE_HIGH>
			, <&shifter 8 GPIO_ACTIVE_HIGH>, <&shifter 9 GPIO_ACTIVE_HIGH>
			, <&shifter 10 GPIO_ACTIVE_HIGH>, <&shifter 11 GPIO_ACTIVE_HIGH>
			, <&shifter 12 GPIO_ACTIVE_HIGH>, <&shifter 13 GPIO_ACTIVE_HIGH>
			, <&shifter 14 GPIO_ACTIVE_HIGH>
			;
	};

	/*
	 * 電池の残量（firmware/ の foundry,battery-alkaline。**化学に依らず**電圧の窓を
	 * % にする線形の写像で、Li/MnO2 でもそのまま使える）。分圧 1MΩ+1MΩ は
	 * 電源スイッチの後ろ・ショットキーの手前（docs/knowledge/power.md）。
	 * empty-millivolts は**打ち止め**。発注前の起動試験（projects/cckb/docs/
	 * task-10a-coin-cell-startup.md）の結果で決める。いまの 2400 は仮の値。
	 * full-millivolts 3200 は CR1632 の新品の開路電圧の上限（Energizer の図で 3.2V）。
	 */
	vbatt: vbatt {
		compatible = "foundry,battery-alkaline";
		io-channels = <&adc 0>;
		output-ohms = <1000000>;
		full-ohms = <2000000>;
		empty-millivolts = <2400>;
		full-millivolts = <3200>;
		/delete-property/ power-gpios;
	};
};

&xiao_spi {
	status = "okay";
	cs-gpios = <&xiao_d 7 GPIO_ACTIVE_LOW>;

	shifter: 595@0 {
		compatible = "zmk,gpio-595";
		status = "okay";
		gpio-controller;
		spi-max-frequency = <4000000>;
		reg = <0>;
		#gpio-cells = <2>;
		ngpios = <16>;
	};
};

&adc {
	status = "okay";
};
```

- [ ] **Step 4: conf を書く** — `config/boards/shields/cckb/cckb.conf`

```
# CCKB。各行の理由は docs/knowledge/zmk-and-xiao.md。
CONFIG_ZMK_KEYBOARD_NAME="CCKB"
CONFIG_SPI=y
# 既定は n。ボタン電池では桁が変わる（スリープ 2〜3µA・HHKB の実測）
CONFIG_ZMK_SLEEP=y
CONFIG_ZMK_IDLE_SLEEP_TIMEOUT=1800000
CONFIG_ZMK_KSCAN_DEBOUNCE_PRESS_MS=3
CONFIG_ZMK_KSCAN_DEBOUNCE_RELEASE_MS=5
# macOS は ZMK 既定（min 7.5ms）を Apple §58.6 違反として要求ごと捨てる
CONFIG_BT_PERIPHERAL_PREF_MIN_INT=12
CONFIG_BT_PERIPHERAL_PREF_MAX_INT=12
CONFIG_BT_PERIPHERAL_PREF_LATENCY=30
CONFIG_BT_PERIPHERAL_PREF_TIMEOUT=600
CONFIG_ZMK_BATTERY_REPORTING=y
CONFIG_ZMK_BATTERY_REPORTING_FETCH_MODE_STATE_OF_CHARGE=y
# 打ち止めを割ったら自分から止まる（firmware/src/low_battery_off.c）
CONFIG_ZMK_PM_SOFT_OFF=y
```

（状態 LED は積まない: XIAO は角の上枠の下にあり、見えない。YAGNI）

- [ ] **Step 5: keymap を書く** — `config/boards/shields/cckb/cckb.keymap`

HHKB 分割機のキーマップ（実機 HHKB の DIP・Fn 面を task-c6 で確認したもの）を CCKB の並びに写したもの:

```dts
/*
 * CCKB。並びは cckb-transform.dtsi の map と同じ（上の段から、段の中は左→右。62 キー）。
 * 層は HHKB 分割機（../2608042258_HHKB_devided/config/boards/shields/hhkb_split/hhkb_split.keymap）
 * と同じ: base_mac / base_win / fn / sys。**スペースは 3 つとも SPACE**（設計書 §1。
 * 真ん中は使ってみてから別のキーに替えてよい）。
 */

#include <behaviors.dtsi>
#include <dt-bindings/zmk/bt.h>
#include <dt-bindings/zmk/keys.h>
#include <dt-bindings/zmk/outputs.h>

#define BASE_MAC 0
#define BASE_WIN 1
#define FN       2
#define SYS      3

/ {
	keymap {
		compatible = "zmk,keymap";

		base_mac {
			bindings = <
			&kp ESC   &kp N1 &kp N2 &kp N3 &kp N4 &kp N5 &kp N6 &kp N7 &kp N8 &kp N9 &kp N0 &kp MINUS &kp EQUAL &kp BSLH &kp GRAVE
			&kp TAB   &kp Q  &kp W  &kp E  &kp R  &kp T  &kp Y  &kp U  &kp I  &kp O  &kp P  &kp LBKT  &kp RBKT  &kp BSPC
			&kp LCTRL &kp A  &kp S  &kp D  &kp F  &kp G  &kp H  &kp J  &kp K  &kp L  &kp SEMI &kp SQT &kp RET
			&kp LSHFT &kp Z  &kp X  &kp C  &kp V  &kp B  &kp N  &kp M  &kp COMMA &kp DOT &kp SLASH &kp RSHFT &mo FN
			&kp LALT  &kp LGUI &kp SPACE &kp SPACE &kp SPACE &kp RGUI &kp RALT
			>;
		};

		base_win {
			bindings = <
			&kp ESC   &kp N1 &kp N2 &kp N3 &kp N4 &kp N5 &kp N6 &kp N7 &kp N8 &kp N9 &kp N0 &kp MINUS &kp EQUAL &kp BSLH &kp GRAVE
			&kp TAB   &kp Q  &kp W  &kp E  &kp R  &kp T  &kp Y  &kp U  &kp I  &kp O  &kp P  &kp LBKT  &kp RBKT  &kp BSPC
			&kp LCTRL &kp A  &kp S  &kp D  &kp F  &kp G  &kp H  &kp J  &kp K  &kp L  &kp SEMI &kp SQT &kp RET
			&kp LSHFT &kp Z  &kp X  &kp C  &kp V  &kp B  &kp N  &kp M  &kp COMMA &kp DOT &kp SLASH &kp RSHFT &mo FN
			&kp LGUI  &kp LALT &kp SPACE &kp SPACE &kp SPACE &kp RALT &kp RGUI
			>;
		};

		fn {
			bindings = <
			&kp K_POWER &kp F1 &kp F2 &kp F3 &kp F4 &kp F5 &kp F6 &kp F7 &kp F8 &kp F9 &kp F10 &kp F11 &kp F12 &kp INS &kp DEL
			&kp CAPS    &trans &trans &trans &trans &trans &trans &trans &kp PSCRN &kp SLCK &kp PAUSE_BREAK &kp UP &trans &trans
			&mo SYS     &kp C_VOL_DN &kp C_VOL_UP &kp C_MUTE &kp C_EJECT &trans &kp KP_MULTIPLY &kp KP_DIVIDE &kp HOME &kp PG_UP &kp LEFT &kp RIGHT &trans
			&trans      &trans &trans &trans &trans &trans &kp KP_PLUS &kp KP_MINUS &kp END &kp PG_DN &kp DOWN &trans &trans
			&trans      &trans &trans &trans &trans &kp C_STOP &trans
			>;
		};

		sys {
			bindings = <
			&bootloader &bt BT_SEL 0 &bt BT_SEL 1 &bt BT_SEL 2 &bt BT_SEL 3 &sys_reset &bootloader &sys_reset &none &none &out OUT_USB &none &none &none &bt BT_CLR
			&none &none &to BASE_WIN &none &none &none &none &none &none &none &none &none &none &none
			&trans &none &none &none &none &none &none &none &none &none &none &none &none
			&none &none &none &none &none &none &none &to BASE_MAC &none &none &none &none &trans
			&none &none &none &none &none &none &none
			>;
		};
	};
};
```

- [ ] **Step 6: transform を生成し、検査を通す**

Run: `.venv/bin/python3 -m foundry.zmk cckb && .venv/bin/python3 -m foundry.check_zmk_config && .venv/bin/pytest tests/test_cckb.py -q`
Expected: 全部 PASS。`grep -c "RC(" config/boards/shields/cckb/cckb-transform.dtsi` の RC の数が 62。

- [ ] **Step 7: 故意に壊す**

keymap の base_mac の 3 つ目の `&kp SPACE` を `&kp BSPC` にして `test_the_three_space_keys_all_send_space_on_both_bases` が落ちることを見る。戻す。

- [ ] **Step 8: コミットして CI でビルドする**

```bash
git status -sb | head -1
git add config/boards/shields/cckb build.yaml tests/test_cckb.py
git commit -m "CCKB: ZMK シールド（595×2・電池・HHKB 既定のキーマップ、スペース 3 つとも SPACE）

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git status -sb | head -1
git push
gh run list --limit 3
```

`gh run watch` で build.yml の完了を待たず、並行して Task 8 を進める。完了したら Artifacts の `firmware` に `cckb-xiao_ble__zmk-zmk.uf2` があり、**大きさが 400KB 前後**（115KB 級なら BLE が抜けている。docs/knowledge/zmk-and-xiao.md）であることを確かめ、作業記録に「CI でビルド成功・実機未確認」と書く。赤なら `gh run view --log-failed` で原因まで降りる。

---

### Task 8: 発注前の起動試験の手順書と、台帳（せき止めているもの）

**Files:**
- Create: `projects/cckb/docs/task-10a-coin-cell-startup.md`（雛形 docs/templates/task.md）
- Modify: `projects/cckb/docs/open-gaps.md`
- Test: `tests/test_cckb.py`（門が閉じていること）

**Interfaces:**
- Consumes: Task 7 の .uf2・`foundry.gate`（`blockers(doc) -> list[str]`・`is_gate_open(doc)`）
- Produces: 利用者が実行できる手順書。門は閉じたまま（計画 2・3 と試験が終わるまで）

- [ ] **Step 1: 門が閉じていることの検査を書く** — `tests/test_cckb.py` に追記

```python
def test_the_order_gate_is_closed_until_the_startup_test_and_the_case_are_done():
    from foundry import gate

    doc = (paths.PROJECTS / "cckb" / "docs" / "open-gaps.md").read_text()
    b = set(gate.blockers(doc))
    assert {"1", "2", "3", "4"} <= b, b          # 起動試験・角の断面・ケース・配線
    assert not gate.is_gate_open(doc)
```

Run: `.venv/bin/pytest tests/test_cckb.py -q -k gate` → FAIL（台帳は雛形のまま）

- [ ] **Step 2: 台帳に書く** — `projects/cckb/docs/open-gaps.md` の「★ 発注をせき止めているもの」

```markdown
| # | 何 | 次の一手 |
|---|---|---|
| #1 | CR1632 で起動・スリープ復帰できるか（設計書 D4。新品で内部抵抗 約 25Ω） | 利用者が task-10a-coin-cell-startup.md を実施。不合格なら D4 を CR2032 に替える |
| #2 | 右の角の断面（ホルダ BS-16-B4AK003＋電池＋ふた）と左の角（XIAO・USB） | 計画 2 |
| #3 | ケース（上枠・角のふた・底板・滑り止め）と組み立て検査・スライス | 計画 2 |
| #4 | 基板の完成（XIAO・595・電源の配置、配線、GND、発注データ） | 計画 3 |
```

「まだ決めていない判断」に設計書 §8 の O2（Task 3 で閉じたなら取り消し線）・O3・O4・O5・O6 を写す。

- [ ] **Step 3: 手順書を書く** — `projects/cckb/docs/task-10a-coin-cell-startup.md`

雛形の節（なぜやるか・構成・用意するもの・配線・手順・判定）を埋める。中身として必ず入れるもの:

- **なぜ**: 「CR1632 は新品で内部抵抗 約 25Ω（Energizer CR1632 データシートの IR 曲線）。HHKB の親側は 25Ω で起動が確率的だった（task-c4-c5 ②）。一体型は役が軽いので大丈夫なはずだが、**計算は実測より楽観的だった**ので測る」
- **構成**: XIAO nRF52840 単体（キー・595 なし）に `cckb-xiao_ble__zmk-zmk.uf2`（Task 7 のコミットを名指し）。給電は **CR1632 → 直列抵抗 → B5819W（または HHKB の 1N5819）→ 3V3**。BAT 端子に繋がない。USB は挿さない（挿すと電池の試験にならない）
- **用意するもの**: CR1632 新品 ×2（ダイソー 2 個 110 円）、電池ホルダかワニ口、抵抗 0Ω（ジャンパ）・25Ω（100Ω×4 並列）・50Ω（100Ω×2 並列）・75Ω（直列 25＋50）、ショットキー、ブレッドボード、スマホ（nRF Connect かホスト PC の Bluetooth 設定）
- **手順**: 各条件で「電池を入れる → 30 秒以内に接続するか」を 10 回、「接続したまま `CONFIG_ZMK_IDLE_SLEEP_TIMEOUT` を待たずにスリープへ入れる手段」が無いので、**電源を入れ直す＝起動**を 10 回とする（スリープ復帰は起動と同じ手順・knowledge/power.md）。条件は 常温 × {0, 25, 50, 75Ω}、冷蔵庫で 2 時間冷やした電池 × {0, 25, 50Ω}。各回で電池端の電圧（無負荷）を記録
- **判定（先に決めておく）**: 常温の 0・25・50Ω と冷蔵の 0・25Ω で **10/10**＝合格。75Ω・冷蔵 50Ω は記録のみ（打ち止めの参考）。1 回でも失敗した条件があれば、その条件だけを 10 回測り直す（lessons J）。**合格なら #1 を取り消し線で閉じ、empty-millivolts を「最後に 10/10 だった条件の無負荷電圧」から決める**
- **対照**: 最初に USB 給電で 10/10 繋がることを見せる（道具と手順が生きていること）

- [ ] **Step 4: 通す**

Run: `.venv/bin/pytest tests -q`
Expected: PASS

- [ ] **Step 5: 門が閉じていることを道具で見る**

Run: `tools/kb cckb gate`
Expected: 閉じている（#1〜#4 を挙げる）。出力を作業記録に貼る。

- [ ] **Step 6: コミット**

```bash
git status -sb | head -1
git add projects/cckb/docs/open-gaps.md projects/cckb/docs/task-10a-coin-cell-startup.md tests/test_cckb.py
git commit -m "CCKB: 発注前の起動試験（CR1632）の手順書と、発注をせき止める台帳

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## 計画 1 を終えたときに利用者へ報告すること

- 回した検査（件数と結果）／回していない検査
- `build/cckb/plate_main.png` と基板の絵（見たこと）
- CI のビルド結果（.uf2 の大きさ）
- **利用者にお願いすること**: 起動試験（task-10a）の実施。Task 3 が未了なら、Choc スタビと CFX 2.25u の購入の判断
- 計画 2（角の作図・ケース）と計画 3（基板の完成・発注データ）を書くこと

## このあと（計画 2・3。この計画の成果と試験の結果に依存するので、終わってから書く）

- **計画 2**: 左右の角の平面図と断面図（XIAO・USB-C・ホルダ・電池・ふた・電源スイッチ）→ 上枠・角のふた・底板・面一の滑り止め → 組み立て検査（干渉・電池の出し入れ・USB・指・ドライバー）→ スライス → `[暫定]` の確定
- **計画 3**: `projects/cckb/pcb_extra.py`（XIAO・595 ×2・電源経路・電池ホルダ・電源スイッチ、表側は XIAO とホルダだけ）→ 行列の決まった形の配線と Freerouting（OpenJDK を入れる）→ GND・アンテナ直下 → fab-fields・DRC・発注データ → 部品表・組み立て手順書 → `tools/kb cckb gate`
