# -*- coding: utf-8 -*-
"""把引用表格/图形的题目定位到原 PDF 页码，渲染页面图片，并把 pages 字段写回题库 JSON。"""
import os, re, json, glob, base64, hashlib
import pymupdf

BUILD = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("QUIZ_OUTPUT_DIR", os.path.join(BUILD, ".."))
DATA = os.path.join(SITE, "data")
PAGES_DIR = os.path.join(SITE, "pages")
SRC1 = r"E:\BaiduNetdiskDownload\2026年咨询【实务】SVIP\2026年咨询【实务】SVIP\01-精华文档✿电子教材✿历年真题"
SRC2 = r"E:\BaiduNetdiskDownload\2026年咨询【实务】SVIP\2026年咨询【实务】SVIP"

SRC2 = os.environ.get("QUIZ_PDF_DIR", SRC2)
SRC1 = os.path.join(SRC2, "01-精华文档✿电子教材✿历年真题")

ZOOM = 1.6
JPEG_KW = dict(jpg_quality=62)

# 卡片 src → (源根目录, 子目录通配, 文件名通配)
GROUPS = {
    "建工网校·基础练习题": [(SRC1, "03-*", "*.pdf")],
    "建工网校·提高练习题": [(SRC1, "06-*", "*.pdf")],
    "环球网校·精华习题集": [(SRC1, "08-*", "*习题集.pdf")],
    "川杨学堂·章节测试": [(SRC1, "11-*", "*.pdf")],
    "川杨·全真模拟卷一": [(SRC1, "15-*", "*模拟考试一*.pdf")],
    "川杨·全真模拟卷二": [(SRC1, "15-*", "*模拟考试二*.pdf")],
    "川杨·全真模拟卷三": [(SRC1, "15-*", "*模拟考试三*.pdf")],
    "川杨·集训专题（财务/盈亏平衡/动态指标）": [(SRC1, "14-*", "*集训内容专题*.pdf")],
    "川杨·跨科专题": [(SRC1, "14-*", "*其他三科*.pdf")],
    "环球网校·真题解析": [(SRC2, "03-*/*真题解析班*", "*.pdf")],
    "优路教育·甄题详解": [(SRC2, "03-*/*甄题详解班*", "*.pdf")],
    "天一网校·强化母题带练": [(SRC2, "03-*/*强化母题带练*", "*.pdf")],
    "环球网校·专题特训": [(SRC2, "04-*/*专题特训班*", "*.pdf")],
    "环球网校·点睛卷": [(SRC2, "05-*/*点睛卷*", "*.pdf")],
    "环球网校·查缺补漏": [(SRC2, "03-*/*查缺补漏*", "*.pdf")],
    "环球网校·万人模考": [(SRC2, "03-*/*万人模考班*", "*.pdf")],
    "优路教育·集训卷": [(SRC2, "04-*/*考前集训班*", "*.pdf")],
    "天一网校·考前模拟": [(SRC2, "05-*/*模拟AB卷*", "*.pdf")],
    "建工网校·预测全真模拟": [(SRC2, "05-*/*三套卷*", "*.pdf")],
}

def norm(s):
    return re.sub(r"\s+", "", s)

def file_id(path, root):
    rel = os.path.relpath(path, root)
    # 纯 ASCII id，避免浏览器/服务器对中文路径的编码差异
    h = hashlib.md5(rel.encode()).hexdigest()[:12]
    return "g" + h

NEEDLE = re.compile(r"表\s*\d|如表|下表|见表|图\s*\d|如图|下图|矩阵图|现金流量图|层次结构图|复利系数表")

def main():
    os.makedirs(PAGES_DIR, exist_ok=True)
    # 1) 组装每组的 PDF 页面文本索引（惰性缓存到 build/_pagemap_cache.json）
    cache_path = os.path.join(BUILD, "_pagemap_cache.json")
    if os.path.exists(cache_path):
        cache = json.load(open(cache_path, encoding="utf-8"))
    else:
        cache = {}  # fid -> {"pdf": path, "pages": [normalized_text]}
    # 每组的 pdf 文件列表
    group_pdfs = {}
    for src, dirs in GROUPS.items():
        lst = []
        for root, dpat, fpat in dirs:
            base = os.path.join(root, "")
            for d in glob.glob(os.path.join(root, dpat)):
                for f in glob.glob(os.path.join(d, "**", fpat), recursive=True):
                    if "Removed" in f:
                        continue
                    lst.append(f)
        group_pdfs[src] = sorted(set(lst))
    total = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))

    # 2) 逐卡片匹配
    card_pages = {}   # card key (file,id) -> [urls]
    matched_pages = set()  # (fid, pageno)
    unmatched = 0
    files_by_src = {}
    changed_pdfs = set()
    for src, pdfs in group_pdfs.items():
        lst = []
        for f in pdfs:
            fid = file_id(f, SRC2 if f.startswith(SRC2) and not f.startswith(SRC1) else SRC1)
            if fid not in cache or cache[fid].get("mtime") != os.stat(f).st_mtime_ns:
                if fid in cache:
                    changed_pdfs.add(fid)
                doc = pymupdf.open(f)
                cache[fid] = {"pdf": f, "mtime": os.stat(f).st_mtime_ns, "pages": [norm(p.get_text()) for p in doc]}
                doc.close()
            lst.append((fid, f))
        files_by_src[src] = lst
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)

    for f in glob.glob(os.path.join(DATA, "*.json")):
        if f.endswith("index.json"):
            continue
        data = json.load(open(f, encoding="utf-8"))
        changed = False
        for c in data.get("questions", []):
            text = (c.get("ctx") or "") + (c.get("q") or "")
            if not NEEDLE.search(text):
                continue
            src = c["src"]
            cands = files_by_src.get(src, [])
            if not cands:
                continue
            ntext = norm(text)
            # 多窗口取片段匹配
            pages_hit = []
            for off in range(0, min(len(ntext) - 25, 400), 40):
                frag = ntext[off:off + 30]
                if len(frag) < 25:
                    break
                for fid, fpath in cands:
                    for pno, ptext in enumerate(cache[fid]["pages"]):
                        if frag in ptext:
                            pages_hit.append((fid, pno))
                if pages_hit:
                    break
            if not pages_hit:
                unmatched += 1
                continue
            pages_hit = sorted(set(pages_hit))[:3]
            urls = []
            for fid, pno in pages_hit:
                matched_pages.add((fid, pno))
                urls.append(f"pages/{fid}/p{pno + 1}.jpg")
            c["pages"] = urls
            changed = True
        if changed:
            json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False)

    print("引用图表卡片命中页面的组数:", len(matched_pages), "| 未命中:", unmatched)

    # 3) 渲染命中的页面
    n = 0
    for fid, pno in sorted(matched_pages):
        out_dir = os.path.join(PAGES_DIR, fid)
        out = os.path.join(out_dir, f"p{pno + 1}.jpg")
        if os.path.exists(out) and fid not in changed_pdfs:
            continue
        os.makedirs(out_dir, exist_ok=True)
        doc = pymupdf.open(cache[fid]["pdf"])
        pix = doc[pno].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
        pix.save(out, **JPEG_KW)
        doc.close()
        n += 1
    print("渲染新页面:", n)

    # 尺寸统计
    total = sum(os.path.getsize(os.path.join(dp, fn)) for dp, _, fns in os.walk(PAGES_DIR) for fn in fns)
    print(f"pages 目录总大小: {total / 1048576:.1f} MB")

if __name__ == "__main__":
    main()
