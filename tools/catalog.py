# -*- coding: utf-8 -*-
"""扫描 text2 全部文本，输出结构目录：文件名、大小、题型标记统计、开头摘要。"""
import os, re, glob, json

DIR = os.environ.get("QUIZ_TEXT2_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "text2"))
report = []
for f in sorted(glob.glob(os.path.join(DIR, "*.txt"))):
    with open(f, encoding="utf-8", errors="replace") as fh:
        t = fh.read()
    name = os.path.basename(f)
    marks = {
        "案": len(re.findall(r"【案例", t)),
        "问": len(re.findall(r"【问题】|问题：", t)),
        "答": len(re.findall(r"【答案】|答：|【正确答案】", t)),
        "试": len(re.findall(r"试题[一二三四五六七八九十]", t)),
        "真题": len(re.findall(r"20[12]\d年.{0,6}真题", t)),
        "解": len(re.findall(r"【解析】|解析[：:]", t)),
    }
    head = re.sub(r"\s+", " ", t[:150])
    report.append((name, len(t), marks, head))

with open(os.path.join(DIR, "_catalog.txt"), "w", encoding="utf-8") as f:
    for name, size, marks, head in report:
        f.write(f"{name}\n  size={size} {marks}\n  {head}\n\n")
print("files:", len(report), "-> catalog written")
