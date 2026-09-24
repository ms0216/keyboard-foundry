"""基板の設計規則の数値と、それを `.kicad_pro` に書く関数。**pcbnew を import しない**（検査は venv から読む）。

HHKB で「違反 0」を「JLCPCB で作れる」と取り違えた（KiCad 既定の規則のまま
だった・#3）。製造者の能力を規則として板と `.kicad_pro` の両方に書き込む
（`kicad-cli` の DRC は**隣の .kicad_pro から**規則を読む・#50）。
"""

import json
from pathlib import Path

# JLCPCB の製造能力（2 層・1oz・標準工程）。
JLC = {
    "track_min": 0.127,       # 最小線幅 5mil
    "clearance_min": 0.127,   # 最小クリアランス 5mil
    "via_dia_min": 0.45,      # 最小ビア外径
    "via_drill_min": 0.20,    # 最小ビアドリル
    "hole_min": 0.20,         # 最小 PTH ドリル
    # 公式は 0.45。HHKB は根拠なく 0.50 にしていて、Kailh ホットスワップ内部の
    # 0.4398（フットプリント固有・直せない）が実際より深刻に見えた。
    # **根拠のない厳しさは本当の問題を隠す**（#50）
    "hole_to_hole": 0.45,
    "edge_clearance": 0.30,   # 銅から外形まで
    # シルクの最小線幅（pcb.py が文字の太さの下限に使う）。KiCad 標準の 0.12 はかすれる。
    # `.kicad_pro` では min_silk_clearance（シルクと外形・パッドの**距離**）に流用している——線幅の規則ではない
    "silk_width": 0.15,
    # シルクの文字の高さ・太さの下限（JLC の PCB Capabilities: 文字の高さ 1.0 以上・線 0.15 以上）。
    # 前は KiCad の既定（0.8・0.08）のままで、1 段小さい字を置いても DRC が黙った（CCKB 4 回目の監査 C 軽微 3）
    "text_height_min": 1.0,
    "text_thickness_min": 0.15,
    # 穴と銅の距離（min_hole_clearance）は KiCad の既定 0.25 のまま。JLC は PTH と線 0.28・NPTH と銅 0.2 と分けて
    # いるが、KiCad の規則は 1 つの値で両方を見る。0.28 にすると NPTH のまわりのベタ（CCKB で 0.25）まで違反に
    # なり、塗り直すと銅が変わる。CCKB の PTH と線の最小は 0.742（4 回目の監査 C）
    "annular_ring": 0.13,     # KiCad 既定 0.1 では足りない
}

# 実際に引く寸法。**自動配線器はネットクラスしか見ない**ので、最小値とは別に
# ネットクラスへ明示する（HHKB では KiCad 既定と偶然一致していただけだった）。
TRACK_W = 0.2
VIA_D, VIA_DRILL = 0.6, 0.3    # φ0.5/0.3 はアニュラ 0.10 で規則 0.13 を割る（#49）

# NPTH（スタビの大穴など）の縁から基板外形まで。スペースのスタビを素の向きで
# 置くと 0.381mm しか残らず、外形公差 ±0.2 で 0.18mm の橋になった（#53）
NPTH_EDGE_MIN = 1.0

# 機種が spec.DRC_SEVERITY で**警告に下げてよい**種類。製造・電気に効かないもの（コートヤード・
# シルク・ライブラリとの差）だけ。clearance・hole_to_hole・copper_edge_clearance などは下げさせない
# （最終レビュー M3。CCKB は npth_inside_courtyard だけを下げている）
DOWNGRADABLE = frozenset({
    "npth_inside_courtyard", "pth_inside_courtyard", "courtyards_overlap",
    "silk_overlap", "silk_over_copper", "silk_edge_clearance",
    "lib_footprint_issues", "lib_footprint_mismatch",
})


def sync_project_rules(pcb_path, severities=None):
    """`.kicad_pro` の規則を JLC に揃える。**kicad-cli の DRC はここを読む。**

    HHKB で JLC の値を直しても DRC が古い規則で判定し続けた（#50）。
    規則以外（利用者が KiCad で設定した重大度など）は触らない。

    severities: 機種が spec.DRC_SEVERITY で**理由を書いて**変える重大度（例: 違反 → 警告）。
    **消す（ignore）ことはさせない**——警告に下げたものも drc.py が種類ごとに数えて出す。
    警告に下げてよいのは DOWNGRADABLE の種類だけ（clearance などを下げさせない）。
    """
    pro = Path(str(pcb_path)[:-len(".kicad_pcb")] + ".kicad_pro")
    doc = json.loads(pro.read_text())
    rules = doc.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules.update({
        "min_track_width": JLC["track_min"],
        "min_clearance": JLC["clearance_min"],
        "min_via_diameter": JLC["via_dia_min"],
        "min_through_hole_diameter": JLC["hole_min"],
        "min_hole_to_hole": JLC["hole_to_hole"],
        "min_copper_edge_clearance": JLC["edge_clearance"],
        "min_silk_clearance": JLC["silk_width"],
        "min_text_height": JLC["text_height_min"],
        "min_text_thickness": JLC["text_thickness_min"],
        "min_via_annular_width": JLC["annular_ring"],
    })
    for kind, sev in (severities or {}).items():
        if sev not in ("error", "warning"):
            raise ValueError(f"{kind}: 重大度 {sev!r} は error / warning だけ（ignore で隠さない）")
        if sev == "warning" and kind not in DOWNGRADABLE:
            raise ValueError(f"{kind} は警告に下げられない（下げてよいのは {sorted(DOWNGRADABLE)}。"
                             "製造・電気に効く種類を機種が黙って軽くしない）")
        doc["board"]["design_settings"].setdefault("rule_severities", {})[kind] = sev
    pro.write_text(json.dumps(doc, indent=2) + "\n")
