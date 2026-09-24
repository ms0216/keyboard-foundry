"""ZMK モジュールの配線。**設定しただけでは効いていない**——3 か所が繋がっているか。

HHKB で状態 LED は「ソースがある・CMake が足す・.conf で =y」の 3 つが揃って初めて
積まれた。どれか 1 つ欠けても**黙って積まれない**（ビルドは通る）。
"""

import re
import subprocess

import pytest
import yaml

from conftest import ROOT

FW = ROOT / "firmware"


def _kconfig_symbols():
    return set(re.findall(r"^config (\w+)", (FW / "Kconfig").read_text(), re.M))


def test_every_config_cmake_reads_is_declared_in_kconfig():
    used = set(re.findall(r"CONFIG_(\w+)", (FW / "CMakeLists.txt").read_text()))
    assert used and used <= _kconfig_symbols(), used - _kconfig_symbols()


def test_every_source_cmake_adds_exists():
    srcs = re.findall(r"^\s+([\w/]+\.c)\)?\s*$", (FW / "CMakeLists.txt").read_text(), re.M)
    assert len(srcs) == 3 and all((FW / s).exists() for s in srcs), srcs


def test_the_driver_and_the_binding_agree_on_the_compatible():
    binding = next((FW / "dts" / "bindings").rglob("*.yaml"))
    compat = yaml.safe_load(binding.read_text())["compatible"]
    drv = re.search(r"#define DT_DRV_COMPAT (\w+)", (FW / "drivers" / "battery_alkaline.c").read_text())
    assert drv.group(1) == re.sub(r"[,-]", "_", compat)
    assert binding.stem == compat
    kc = (FW / "Kconfig").read_text()
    assert f"DT_HAS_{re.sub(r'[,-]', '_', compat).upper()}_ENABLED" in kc


def test_the_module_is_registered():
    m = yaml.safe_load((ROOT / "zephyr" / "module.yml").read_text())
    assert m["build"]["cmake"] == "firmware" and m["build"]["settings"]["dts_root"] == "firmware"


def test_no_hhkb_identifier_is_left_after_the_rename():
    """**置き換えたら、置き換えられた方の名前で grep する**（HHKB で 4 回踏んだ）。

    `git ls-files` で追跡ファイルだけを見る（.DS_Store のような未追跡ファイルは除外）。
    `.git` の無いチェックアウト（`git archive` で書き出した監査用の作業ツリーなど）では
    `git ls-files` 自体が使えないので、その場合はこの検査だけ skip する
    （tracked files を全部スキャンする、という前提が成り立たないと分かった上で飛ばす。
    監査 audit-psw.md「git archive で /tmp に出したら git ls-files が失敗した」への対応）。
    """
    if not (ROOT / ".git").exists():
        pytest.skip(".git が無いチェックアウト（git archive など）。git ls-files が使えない")
    # git が追跡するファイルだけをスキャン（.DS_Store のような未追跡ファイルは除外）
    result = subprocess.run(
        ["git", "ls-files", "firmware"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True
    )
    tracked_files = [ROOT / p for p in result.stdout.strip().split("\n") if p]
    assert tracked_files, "firmware/ に追跡ファイルがない"

    left = [f"{p.relative_to(ROOT)}:{i}"
            for p in tracked_files
            if p.suffix in (".c", ".h", ".yaml", ".txt", "")
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if re.search(r"hhkb[,_]|HHKB_|hhkb-", line)]
    assert not left, left


# ---------------------------------------------------------------------------
# 打ち止めの判定（firmware/src/low_battery_off.c）をホストで回す
# ---------------------------------------------------------------------------

def _run_low_battery_harness(tmp_path, source=None):
    """low_battery_off.c を代役の Zephyr/ZMK（tests/fixtures/zmk_host）でコンパイルして回す。
    {場面: (soft off の回数, fetch の回数)}。source を渡すとそのファイルを代わりに使う（壊す検査）。"""
    import shutil

    from conftest import FIXTURES, require

    cc = shutil.which("cc") or "/usr/bin/cc"
    require(cc, "C コンパイラ（打ち止めの判定をホストで回す）")
    host = FIXTURES / "zmk_host"
    harness = host / "harness.c"
    if source is not None:
        text = harness.read_text().replace('"../../../firmware/src/low_battery_off.c"', f'"{source}"')
        harness = tmp_path / "harness.c"
        harness.write_text(text)
    exe = tmp_path / "harness"
    r = subprocess.run([cc, "-std=c11", "-Wall", "-Werror", "-I", str(host / "include"),
                        "-DHOST_EMPTY_MV=2400", "-DCONFIG_ZMK_USB=1",
                        "-DCONFIG_FOUNDRY_LOW_BATTERY_SOFT_OFF_SAMPLES=2",
                        "-DCONFIG_ZMK_BATTERY_REPORT_INTERVAL=60", "-DCONFIG_APPLICATION_INIT_PRIORITY=90",
                        "-o", str(exe), str(harness)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr          # 出力を捨てない
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    res = {}
    for line in out.splitlines():
        name, so, fe = re.fullmatch(r"(\w+) soft_off=(\d+) fetch=(\d+)", line).groups()
        res[name] = (int(so), int(fe))
    return res


def test_low_battery_off_counts_only_fresh_samples(tmp_path):
    """アイドル中は ZMK が電池を測らない（ZMK app/src/battery.c の battery_event_listener が
    ZMK_ACTIVITY_IDLE・SLEEP で k_timer_stop）。キャッシュを読むだけだと、最後の 1 回の低い読みを
    「2 回続けて」と数えて止まる（4 回目の監査 F 重要 1）。**毎回測ってから数える**ことを見る。"""
    res = _run_low_battery_harness(tmp_path)
    assert res == {
        "stale_low": (0, 3),        # 最後の測定だけ低く、いまは十分 → 止まらない
        "empty_once": (0, 1),       # 1 回では止めない（BLE 送信中の降下）
        "empty_twice": (1, 2),      # 2 回続けて下回ったら止まる
        "drained_idle": (1, 2),     # アイドルの間に尽きても気づく
        "usb": (0, 0),              # USB 給電中は数えない（測りもしない）
    }, res


def test_the_fresh_sample_check_notices_the_cached_read(tmp_path):
    """**壊して落ちることを示す。**測り直しの 1 行を消した low_battery_off.c（2026-09-25 までの形）は
    最後の低い読みを 2 回数えて止まる。"""
    src = (FW / "src" / "low_battery_off.c").read_text()
    call = re.search(r"\n[^\n]*sensor_sample_fetch_chan\(battery, SENSOR_CHAN_GAUGE_VOLTAGE\);", src)
    assert call, "測り直しの呼び出しが見つからない"
    broken = tmp_path / "low_battery_off.c"
    broken.write_text(src.replace(call.group(0), "\n    int rc = 0;"))
    res = _run_low_battery_harness(tmp_path, source=broken)
    assert res["stale_low"][0] > 0, res
