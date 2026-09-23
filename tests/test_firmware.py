"""ZMK モジュールの配線。**設定しただけでは効いていない**——3 か所が繋がっているか。

HHKB で状態 LED は「ソースがある・CMake が足す・.conf で =y」の 3 つが揃って初めて
積まれた。どれか 1 つ欠けても**黙って積まれない**（ビルドは通る）。
"""

import re
import subprocess

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
    """**置き換えたら、置き換えられた方の名前で grep する**（HHKB で 4 回踏んだ）。"""
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
