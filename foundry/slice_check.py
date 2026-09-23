"""OrcaSlicer の CLI で実際にスライスし、印刷可能性を機械的に確認する。

自作の検査（inspect_mesh.py）は近似でしかない。最終的に形状を解釈するのは
スライサーなので、スライサー自身に通させるのが一番確実な物理検証になる。

確認するもの:
  - スライスがエラー無く完了するか（形状がスライサーに受理されるか）
  - 警告の有無（サポートが要る、薄すぎる、ベッドからはみ出す等）
  - 生成された G-code から推定所要時間と材料使用量

プロファイル（プリンタ／フィラメント／プロセス）はアプリのバンドル内から
実行時に探す。K1 Max / PLA / 0.2mm を優先して選ぶ。

    .venv/bin/python3 -m foundry.slice_check <機種> [--printer k1max|a1mini] [部品名...]

対象は build/<機種>/*.stl。**生成器や spec.py より古い STL は刷れると言わない。**
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from .paths import BUILD, ORCA

TOOLS = Path(__file__).resolve().parent
BIN_CANDIDATES = [Path(ORCA), Path(ORCA).with_name("orca-slicer")]
PROFILES = Path(ORCA).parent.parent / "Resources/profiles"

# プロファイル名の表記はバンドル内で揺れている（machine は "K1 Max"、
# process は "K1Max" と空白の有無が違う）。ヒントは実際の綴りに合わせる。
#
# `bed` は造形できる大きさ（mm）。inspect_mesh も同じ値を読む。
# ⚠️ A1 mini の CLI は必ず自動配置を通り、実効は約 168.4mm 角（bed_shrink 3.4 +
# brim_skirt_distance 2.4）。GUI で手で端に置けば 180 弱まで刷れる（HHKB で
# 177.6mm の試し板を実機で完走）。CLI の NG は「CLI では置けない」の意味。
PRINTERS = {
    "k1max": dict(
        vendor="Creality", key="K1", bed=(300.0, 300.0, 300.0),
        machine=["K1 Max (0.4 nozzle)", "K1 Max", "K1"],
        filament=["Creality Generic PLA @K1-all", "Generic PLA @K1",
                  "Generic PLA"],
        process=["0.20mm Standard @Creality K1Max (0.4 nozzle)",
                 "0.20mm Standard @Creality K1", "0.20mm Standard"],
    ),
    "a1mini": dict(
        vendor="BBL", key="A1 mini", bed=(180.0, 180.0, 180.0),
        machine=["Bambu Lab A1 mini 0.4 nozzle", "Bambu Lab A1 mini"],
        filament=["Generic PLA @BBL A1M", "Generic PLA"],
        process=["0.20mm Standard @BBL A1M", "0.20mm Standard"],
    ),
}


def find_binary():
    for b in BIN_CANDIDATES:
        if b.exists():
            return b
    raise SystemExit(f"OrcaSlicer が見つからない。探した場所: {BIN_CANDIDATES}")


def pick(paths, hints, label):
    """ヒントに合うプロファイルを 1 つ選ぶ。優先順位はヒントの並び順。

    **完全一致を部分一致より先に見る。**部分一致だけだと
    "Generic PLA @BBL A1M" が辞書順で先に並ぶ
    "Generic PLA @BBL A1M 0.2 nozzle" に吸われ、0.2mm ノズル用の
    吐出上限（≈2mm³/s）で全部品の推定時間が 4〜5 倍に化けた（2026-08-24）。
    """
    for hint in hints:
        for p in paths:
            if hint.lower() == p.stem.lower():
                return p
    for hint in hints:
        for p in paths:
            if hint.lower() in p.stem.lower():
                return p
    if paths:
        print(f"   ! {label}: ヒントに合うものが無いので {paths[0].stem} を使う")
        return paths[0]
    raise SystemExit(f"{label} のプロファイルが見つからない")


def find_profiles(printer="k1max"):
    cfg = PRINTERS[printer]
    base = PROFILES / cfg["vendor"]
    if not base.exists():
        raise SystemExit(f"{base} が無い。導入されている vendor: "
                         f"{[p.name for p in PROFILES.iterdir()][:10]}")
    machines = sorted((base / "machine").glob("*.json"))
    filaments = sorted((base / "filament").glob("*.json"))
    processes = sorted((base / "process").glob("*.json"))
    key = cfg["key"]
    m = pick([p for p in machines if key in p.stem] or machines,
             cfg["machine"], "プリンタ")
    f = pick(filaments, cfg["filament"], "フィラメント")
    pr = pick([p for p in processes if key in p.stem or "A1M" in p.stem]
              or processes, cfg["process"], "プロセス")
    return m, f, pr


def slice_one(binary, stl, machine, filament, process, printer, out):
    # 出力名は入力名によらず plate_N.gcode になるので、部品ごとに別の
    # ディレクトリへ出す（同じ場所に出すと上書きされて区別できない）。
    # **プリンタごとにも分ける**——分けないと a1mini の失敗ディレクトリに
    # k1max の古い gcode が残り、「gcode がある＝成功」の判定を騙す
    # （2026-08-23 に実際に紛らわしかった）。
    outdir = out / printer / stl.stem
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(binary),
        "--load-settings", f"{machine};{process}",
        "--load-filaments", str(filament),
        "--slice", "0",
        "--outputdir", str(outdir),
        str(stl),
    ]
    # OrcaSlicer は CWD に 00000.log を吐く。リポジトリを汚さないよう outdir で走らせる
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                       cwd=outdir)
    return r, outdir


def summarize_gcode(gcode):
    """G-code から所要時間と材料使用量を拾う。

    OrcaSlicer はサマリを**末尾**に書く。先頭だけ読んでいたため、
    大きい部品（3.9MB、14万行）で時間と材料が取れていなかった。
    先頭と末尾の両方を見る。
    """
    info = {}
    try:
        raw = gcode.read_bytes()
        head = raw[:200_000].decode(errors="replace")
        tail = raw[-300_000:].decode(errors="replace")
    except Exception:
        return info
    head = head + "\n" + tail
    for key, pat in [
        ("時間", r";\s*(?:model printing time|estimated printing time[^:=]*)\s*[:=]\s*([^\n;]+)"),
        ("材料", r";\s*filament used \[cm3\]\s*[:=]\s*([\d.]+)"),
        ("層数", r";\s*total layer number\s*[:=]\s*(\d+)"),
    ]:
        m = re.search(pat, head, re.IGNORECASE)
        if m:
            info[key] = m.group(1).strip()
    return info


def main(project, names=None, printer="k1max"):
    from .project import load
    p = load(project)
    build = p.build
    binary = find_binary()
    machine, filament, process = find_profiles(printer)
    print(f"プリンタ     {machine.stem}")
    print(f"フィラメント {filament.stem}")
    print(f"プロセス     {process.stem}\n")

    stls = sorted(q for q in build.glob("*.stl") if not q.stem.startswith("_"))

    # **古い STL を黙って「刷れます」と言わない。**
    #
    # ⚠️ 2026-08-12。底面の電池蓋を廃止したのに build/battery_lid_*.stl が
    # 残り、ここが拾って合格を出していた。**存在しない部品を刷らせる。**
    # 調査中に出した残骸（lid.stl / c.stl）も同じように拾っていた。
    # 生成器側でも片付けるようにしたが、警告だけでは誰も読まず、
    # 廃止済みの tilt_foot_3.stl / tilt_foot_6.stl（改名前の残骸。
    # **正体は test_case.py が pytest のたびに同名で書き戻していたこと。**
    # 2026-08-23 に `_` 始まりへ変えて根を断った）を
    # 8 か月「刷れます」と言い続けた（2026-08-13）。
    # **古い STL はスライスせず、検査を赤にする。**
    # slice_check.py 自身は形状を作らないので比較から外す
    # （外さないと、この検査を編集しただけで全 STL が「古い」になる）。
    newest = max([q.stat().st_mtime for q in TOOLS.glob("*.py")
                  if q.name != "slice_check.py"]
                 + [q.stat().st_mtime for q in p.root.glob("*.py")])
    stale = [q for q in stls if q.stat().st_mtime < newest]
    if stale:
        print("!! foundry/*.py か spec.py より古い STL がある。作り直すか、消すこと"
              "（どの生成器も出さない残骸なら消す）:")
        for q in stale:
            print(f"     {q.name}")
        print()
        stls = [q for q in stls if q not in stale]
    if names:
        stls = [q for q in stls if q.stem in names]

    failed = []
    for stl in stls:
        r, outdir = slice_one(binary, stl, machine, filament, process, printer,
                              build / "slice")
        out = (r.stdout or "") + (r.stderr or "")
        warns = sorted(set(
            line.strip() for line in out.splitlines()
            if re.search(r"warn|error|fail|cannot|invalid", line, re.I)
        ))
        gcodes = sorted(outdir.glob("*.gcode"))
        ok = r.returncode == 0 and gcodes
        mark = "OK " if ok else "NG "
        print(f"{mark}{stl.stem}")
        if gcodes:
            info = summarize_gcode(gcodes[-1])
            if info:
                unit = {"材料": "cm3"}
                print("      " + "  ".join(
                    f"{k} {v}{unit.get(k, '')}" for k, v in info.items()))
        for w in warns[:6]:
            print(f"      ! {w[:150]}")
        if not ok:
            failed.append(stl.stem)
            if not warns:
                print(f"      終了コード {r.returncode}")
                print(f"      {out.strip()[-400:]}")

    print(f"\n{len(stls) - len(failed)}/{len(stls)} 件がスライス成功")
    if failed:
        print("失敗: " + ", ".join(failed))
    if stale:
        print(f"古い STL {len(stale)} 件（上記）。合格にしない")
    return 1 if failed or stale else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    printer = "k1max"
    if "--printer" in args:
        i = args.index("--printer")
        printer = args[i + 1]
        del args[i:i + 2]
    if printer not in PRINTERS:
        raise SystemExit(f"--printer は {sorted(PRINTERS)} のどれか")
    if not args:
        raise SystemExit("使い方: python -m foundry.slice_check <機種> [--printer ...] [部品...]")
    sys.exit(main(args[0], args[1:] or None, printer))
