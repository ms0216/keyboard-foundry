#!/bin/sh
# 基板が変わったら絵を出し直して「見ろ」と突きつける。
#
# 発端（HHKB・2026-08-16）: 「視覚的に確認した？」に「していません」と答え続けた。
# 道具はあった。**呼ぶかどうかが裁量だった**ので呼ばれなかった。ここは裁量の外に置く。
#
# **触ったファイル名では絞らない。**板を書くのは Write ではなく生成器（Bash 経由）。
# 代わりに毎回全部の板の指紋を見る（変化が無ければ黙って終わる）。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python3"
cat >/dev/null
[ -x "$PY" ] || exit 0
ls "$ROOT"/projects/*/pcb >/dev/null 2>&1 || exit 0

OUT="$(cd "$ROOT" && "$PY" -m foundry.render_pcb --all 2>&1)" || true
DREW="$(printf '%s\n' "$OUT" | grep -E '^(描いた|  拡大)' || true)"
BAD="$(printf '%s\n' "$OUT" | grep '^NG' || true)"
[ -n "$BAD" ] && printf '%s\n' "$BAD" >&2          # 描けなかった理由は隠さない
[ -n "$DREW" ] || exit 0
printf '%s\n' "$DREW" >&2

PNGS="$(printf '%s\n' "$DREW" | awk '{printf "%s ", $NF}')"
"$PY" - "$PNGS" <<'PYEOF'
import json, sys
pngs = sys.argv[1].split()
zooms = [p for p in pngs if "__" in p]
msg = ["基板が変わったので絵を出し直した:"] + [f"  {p}" for p in pngs]
if zooms:
    msg += ["", "**動いた部品の拡大図がある。まずこれを見ること:**"] + [f"  {p}" for p in zooms]
msg += ["", "**Read でこの PNG を実際に見ること。**見る前に配線・配置・シルクについて"
        "「問題ない」と書かない。見たなら、絵の中で確かめたことを具体的に書く。"]
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                         "additionalContext": "\n".join(msg)}}))
PYEOF
