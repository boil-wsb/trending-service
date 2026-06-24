"""拆分 enhanced_report_template.html 为多文件模板（一次性脚本）。

切分边界（1-based 行号，含两端）：
  styles/base.css          9-1520
  styles/analysis.css      1521-1893
  styles/navigation.css    1894-2489
  styles/index_market.css  2490-3117
  layout/body.html         3121-3525
  scripts/core.js          3527-5191
  scripts/source_status.js 5192-5473
  scripts/index_market.js  5474-6252
  scripts/indicators.js    6253-6668

主模板保留骨架行：1-8 / 3118-3120 / 3526 / 6669-6675，
其间用 <!-- INCLUDE: enhanced_report/... --> 标记占位。

运行后验证：include 拼接结果应与原模板逐字节相等。
"""
from pathlib import Path

TEMPLATES = Path(__file__).parent
SRC = TEMPLATES / "enhanced_report_template.html.bak"
PARTS = TEMPLATES / "enhanced_report"

# (相对路径, 起始行, 结束行)
SLICES = [
    ("styles/base.css",          9,    1520),
    ("styles/analysis.css",     1521,  1893),
    ("styles/navigation.css",   1894,  2489),
    ("styles/index_market.css", 2490,  3117),
    ("layout/body.html",        3121,  3525),
    ("scripts/core.js",         3527,  5191),
    ("scripts/source_status.js",5192,  5473),
    ("scripts/index_market.js", 5474,  6252),
    ("scripts/indicators.js",   6253,  6668),
]

# 主模板骨架：保留原文件行 + INCLUDE 标记
# 结构：(类型, 内容)。type=='raw' 表示原样保留；type=='include' 表示 INCLUDE 标记
SKELETON = [
    ("raw",    "lines_1_to_8"),           # DOCTYPE.. <style>
    ("include", "enhanced_report/styles/base.css"),
    ("include", "enhanced_report/styles/analysis.css"),
    ("include", "enhanced_report/styles/navigation.css"),
    ("include", "enhanced_report/styles/index_market.css"),
    ("raw",    "lines_3118_to_3120"),     # </style></head><body>
    ("include", "enhanced_report/layout/body.html"),
    ("raw",    "line_3526"),              # <script>
    ("include", "enhanced_report/scripts/core.js"),
    ("include", "enhanced_report/scripts/source_status.js"),
    ("include", "enhanced_report/scripts/index_market.js"),
    ("include", "enhanced_report/scripts/indicators.js"),
    ("raw",    "lines_6669_to_6675"),     # </script>.. chart.js .. </body></html>
]


def main():
    original = SRC.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)  # 保留换行，0-based
    total = len(lines)
    print(f"原模板行数: {total}")

    # 1) 切分片段
    print("\n=== 切分片段 ===")
    for rel, start, end in SLICES:
        content = "".join(lines[start - 1:end])  # 1-based [start,end] -> 0-based [start-1, end)
        out = PARTS / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        print(f"  {rel:32s} 行 {start:>4}-{end:<4}  -> {out}  ({len(content)} 字节)")

    # 2) 构建主模板骨架
    print("\n=== 构建主模板 ===")
    def raw_lines(name):
        if name == "lines_1_to_8":
            return "".join(lines[0:8])
        if name == "lines_3118_to_3120":
            return "".join(lines[3117:3120])
        if name == "line_3526":
            return lines[3525]
        if name == "lines_6669_to_6675":
            return "".join(lines[6668:6675])
        raise ValueError(name)

    parts = []
    for kind, val in SKELETON:
        if kind == "raw":
            parts.append(raw_lines(val))
        else:
            parts.append(f"<!-- INCLUDE: {val} -->\n")
    skeleton = "".join(parts)
    main_tpl = TEMPLATES / "enhanced_report_template.html"
    main_tpl.write_text(skeleton, encoding="utf-8")
    print(f"  主模板行数: {skeleton.count(chr(10))}  -> {main_tpl}")

    # 3) 验证：用 include 逻辑拼回，与原文件对比
    print("\n=== 等价性验证 ===")
    import re
    def expand(text, base=TEMPLATES, depth=0):
        if depth > 10:
            raise RuntimeError("include 嵌套过深")
        def repl(m):
            p = base / m.group(1).strip()
            return expand(p.read_text(encoding="utf-8"), base, depth + 1)
        return re.sub(r"<!-- INCLUDE: (.*?) -->\n", repl, text)

    rebuilt = expand(skeleton)
    if rebuilt == original:
        print("  ✓ 完全等价：include 拼接结果与原模板逐字节相同")
    else:
        # 找出第一个差异
        for i, (a, b) in enumerate(zip(original, rebuilt)):
            if a != b:
                print(f"  ✗ 首个差异在字符 {i}: 原={a!r} 新={b!r}")
                ctx_o = original[max(0, i - 40):i + 40]
                ctx_n = rebuilt[max(0, i - 40):i + 40]
                print(f"    原上下文: ...{ctx_o!r}")
                print(f"    新上下文: ...{ctx_n!r}")
                break
        if len(original) != len(rebuilt):
            print(f"  长度不同: 原={len(original)} 新={len(rebuilt)}")
        print("  ✗ 不等价，请检查切分边界")
        return 1
    print("\n🎉 拆分完成，等价性验证通过")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
