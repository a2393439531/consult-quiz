# -*- coding: utf-8 -*-
"""用 PyMuPDF 批量转换 02~05 文件夹的 PDF 为文本。"""
import os, re, glob
import pymupdf

SRC = r"E:\BaiduNetdiskDownload\2026年咨询【实务】SVIP\2026年咨询【实务】SVIP"
SRC = os.environ.get("QUIZ_PDF_DIR", SRC)
OUT = os.environ.get("QUIZ_TEXT2_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "text2"))
os.makedirs(OUT, exist_ok=True)

pdfs = []
for grp in sorted(glob.glob(os.path.join(SRC, "0[2-5]*"))):
    gname = os.path.basename(grp)[:2]
    for root, dirs, files in os.walk(grp):
        for fn in files:
            if fn.lower().endswith(".pdf"):
                rel = os.path.relpath(os.path.join(root, fn), grp)
                pdfs.append((gname, rel, os.path.join(root, fn)))

ok = fail = 0
for gname, rel, path in pdfs:
    key = re.sub(r"[^\w\u4e00-\u9fff（）()【】《》.、-]+", "_", rel)[:180]
    out = os.path.join(OUT, f"{gname}__{key}.txt")
    try:
        doc = pymupdf.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        ok += 1
    except Exception as e:
        fail += 1
        print("FAIL", rel, e)
print(f"converted {ok}, failed {fail}, total {len(pdfs)}")
