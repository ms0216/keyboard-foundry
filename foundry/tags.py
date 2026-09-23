"""定数のタグ（[確定] / [暫定] / [記録のみ]）を読む。検査と mutate が共有する。

  [暫定]     推定で置いた値。実測で差し替える。projects/<機種>/docs/provisional-values.md
             に一覧が要る（tests/test_constants.py が数値まで突き合わせる）
  [記録のみ] 誰も読まない歴史の記録。mutate は変異させない
  タグ無し   読まれている値。読まれていなければ検査が落ちる

**タグは代入の行に書く**（直上のコメントでもよいのは [記録のみ] だけ）。
走査は行単位なので、離れた場所に書くと見落とす。
"""

import ast
import re


def marked_record_only(path, lineno):
    """定義行、または直上の連続したコメント行に [記録のみ] があるか。"""
    lines = path.read_text().split("\n")
    if "[記録のみ]" in lines[lineno - 1]:
        return True
    i = lineno - 2
    while i >= 0 and lines[i].lstrip().startswith("#"):
        if "[記録のみ]" in lines[i]:
            return True
        i -= 1
    return False


def provisional(path):
    """[暫定] の付いた代入行の (行番号, 名前の並び)。"""
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if "[暫定]" in line:
            m = re.match(r"\s*([A-Z_][A-Z0-9_,\s]*)\s*=", line)
            if m:
                out.append((i, [n.strip() for n in m.group(1).split(",")]))
    return out


def module_constants(path):
    """モジュール直下の大文字の定数 → 行番号。タプル代入も拾う。"""
    out = {}
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            names = ([t] if isinstance(t, ast.Name) else getattr(t, "elts", []))
            for n in names:
                if isinstance(n, ast.Name) and n.id.isupper():
                    out.setdefault(n.id, node.lineno)
    return out


def names_read(path):
    """そのファイルで読まれている名前（`X` と `something.X` の両方）。"""
    out = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)         # getattr(spec, "NAME") も読んだことにする
    return out


def provisional_mismatches(spec_path, doc_path):
    """[暫定] の値と provisional-values.md の表の食い違い（無ければ空）。

    文書を見て部品を買うので、名前が載っているだけでは足りない。数値まで見る。
    """
    rows = {}
    if doc_path.exists():
        for name, value in re.findall(r"^\|\s*`([A-Z_][A-Z0-9_]*)`\s*\|([^|]*)\|",
                                      doc_path.read_text(), re.M):
            nums = re.findall(r"-?\d+(?:\.\d+)?", value)
            rows[name] = float(nums[0]) if nums else None
    ns = {}
    exec(compile(spec_path.read_text(), str(spec_path), "exec"), ns)
    bad, live = [], set()
    for _, names in provisional(spec_path):
        for n in names:
            live.add(n)
            if n not in rows:
                bad.append(f"{n}: 文書に無い")
            elif isinstance(ns.get(n), (int, float)) and rows[n] is not None \
                    and abs(ns[n] - rows[n]) > 1e-6:
                bad.append(f"{n}: コード {ns[n]} / 文書 {rows[n]}")
    return bad + [f"{n}: もう暫定ではないのに文書に残っている" for n in sorted(set(rows) - live)]
