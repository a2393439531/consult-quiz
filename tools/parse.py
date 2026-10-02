# -*- coding: utf-8 -*-
"""解析咨询工程师《实务》题库 PDF 文本，生成网站用 JSON。"""
import json, re, os, glob
from collections import defaultdict

TEXT_DIR = os.environ.get("QUIZ_TEXT_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "text"))
OUT_DIR = os.environ.get("QUIZ_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(OUT_DIR, exist_ok=True)

CHAPTERS = [
    (1, "现代工程咨询方法"), (2, "规划咨询的主要理论与方法"), (3, "能源资源环境分析"),
    (4, "战略分析"), (5, "市场分析"), (6, "重大项目谋划"), (7, "现金流量分析"),
    (8, "工程项目投资估算"), (9, "融资方案分析"), (10, "工程项目财务分析"), (11, "工程项目经济分析"),
]
CN_NUM = "一二三四五六七八九十"
NOISE = [
    re.compile(r"^[科]{2,}.*$"), re.compile(r"^[PTQ=\s　]+$"),
    re.compile(r"^nnL$"), re.compile(r"^QVNT.*$"),
    re.compile(r"第\s*\d+\s*页\s*/?\s*共\s*\d+\s*页"),
    re.compile(r"^学员专用.*$"), re.compile(r"^\d{1,4}$"),
    re.compile(r"^[\s　]*$"),
]

def read(name):
    with open(os.path.join(TEXT_DIR, name), encoding="utf-8", errors="replace") as f:
        return f.read()

def clean_lines(text):
    out = []
    for ln in text.splitlines():
        ln = ln.strip().replace("\x0c", "")
        ln = re.sub(r"\s*[TPQ=]\s*$", "", ln)  # 行尾散落的 P/T/Q/= 噪声
        ln = re.sub(r"[科]{2,}[PTQ=\s]*$", "", ln)  # 行尾水印噪声
        if any(p.match(ln) for p in NOISE):
            continue
        out.append(ln)
    return out

NEW_PARA = re.compile(r"^(①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩|（\d|【|问题[：:]|答[：:]|试题|第[一二三四五六七八九十]+章|表\s*\d|注[：:]|[一二三四五六七八九十]+、)")

def join_paras_str(s):
    return "\n".join(join_paras([l.strip() for l in s.splitlines() if l.strip()]))

def join_paras(lines):
    """把被 PDF 硬换行打断的句子拼回段落。"""
    paras, cur = [], ""
    for ln in lines:
        if not cur:
            cur = ln
        elif cur.endswith(("。", "？", "！", "；", "：")) and NEW_PARA.match(ln):
            paras.append(cur); cur = ln
        else:
            cur += ln
    if cur:
        paras.append(cur)
    return [re.sub(r"[\s]*[TPQ=][\s]*$", "", p) for p in paras]

QMARK = re.compile(r"^(\d{1,2})[.．]\s*(?!\d)")

def split_expected(text, maxn=30):
    """按连续题号 1. 2. 3. ... 顺序切分文本（题号可能出现在行中）。"""
    positions = []
    pos, n = 0, 1
    while n <= maxn:
        m = re.search(rf"(?<![0-9.]){n}[.．](?=\D)", text[pos:])
        if not m:
            break
        s, e = pos + m.start(), pos + m.end()
        positions.append((n, s, e))
        pos, n = e, n + 1
    if not positions:
        return text, {}
    segs = {}
    for i, (num, s, e) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(text)
        segs[num] = text[e:end]
    return text[:positions[0][1]], segs

def parse_jianzhu(fname, source, chapter_no, idp):
    """建工网校练习题：读文件后交给核心解析。"""
    return parse_jianzhu_txt(read(fname), source, chapter_no, idp)

def parse_jianzhu_txt(text, source, chapter_no, idp):
    lines = clean_lines(text)
    # 答案部分起点：显式"答案部分"标记，或同时含"一、简答题"与"【正确答案】"的行
    ans_start = None
    for i, ln in enumerate(lines):
        if "答案部分" in ln or ("一、简答题" in ln and "【正确答案】" in ln):
            ans_start = i
            break
    if ans_start is None:
        raise ValueError("未找到答案部分")
    lines[ans_start] = lines[ans_start].replace("答案部分", "")
    q_lines, a_lines = lines[:ans_start], lines[ans_start:]

    q_text = "\n".join(q_lines)
    _, qsegs = split_expected(q_text)
    qmap = {num: [t] for num, t in qsegs.items()}

    # ---- 答案部分 ----
    a_text = "\n".join(a_lines).replace("二、阅读理解", "\n").replace("一、简答题", "\n")
    # 标记形如 "13. （1）【正确答案】" 或独立的 "（2）【正确答案】" 或 "1.【正确答案】"
    marks = list(re.finditer(r"(?:(\d{1,2})[.．]\s*)?(?:（([1-9])）\s*)?【正确答案】", a_text))
    amap = defaultdict(dict)  # num -> {sub or '': text}
    cur_num = None
    for i, m in enumerate(marks):
        num, sub = m.group(1), m.group(2)
        if not num and not sub:
            continue
        if num:
            cur_num = int(num)
        seg = a_text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(a_text)]
        key = sub if sub else ""
        tgt = amap[cur_num]
        if key in tgt:
            tgt[key] += "\n" + seg
        else:
            tgt[key] = seg
    for num in amap:
        for k in amap[num]:
            amap[num][k] = "\n".join(join_paras([l.strip() for l in amap[num][k].splitlines() if l.strip()]))

    cards = []
    for num in sorted(qmap):
        q = "\n".join(join_paras([l.strip() for l in qmap[num][0].splitlines() if l.strip()]))
        q = q.replace("一、简答题", "").replace("二、阅读理解", "").strip()
        if num == 0 or not q.strip():
            continue
        ans = amap.get(num, {})
        subs = split_subs(q) if re.search(r"（[1-9]）", q) else []
        sub_answers = sorted(k for k in ans if k.isdigit())
        if subs and len(subs) == len(sub_answers) and len(ans) >= len(sub_answers):
            ctx = re.split(r"（[1-9]）", q, 1)[0].strip()
            for sub_text, sub_no in subs:
                cards.append(dict(type="案例", ctx=ctx, q=f"（{sub_no}）{sub_text}", a=ans.get(sub_no, "")))
        else:
            cards.append(dict(type="简答" if len(q) < 120 else "案例", ctx="", q=q,
                              a="\n".join(ans[k] for k in sorted(ans)) if ans else ""))
    out = []
    for i, c in enumerate(cards):
        c["id"] = f"{idp}{chapter_no}-{i+1}"
        c["src"] = source
        if not c["a"].strip():
            c["a"] = "（原资料中未找到本题参考答案，请结合教材核对）"
        out.append(c)
    return out

def split_subs(q):
    parts = re.split(r"（([1-9])）", q)
    # parts: [ctx, '1', text1, '2', text2 ...]
    subs = []
    for i in range(1, len(parts) - 1, 2):
        subs.append((parts[i + 1].strip(), parts[i]))
    return subs

def parse_huanqiu(fname, source):
    """环球精华习题集：第X章标题分段，每段内【案例N】+【问题】，答案段为 第X章...参考答案。"""
    text = read(fname)
    lines = clean_lines(text)
    joined = "\n".join(lines)
    marks = []
    for no, title in CHAPTERS:
        for m in re.finditer(rf"第{int2cn(no)}章\s*{title}\s*(参考答案)?", joined):
            marks.append((m.start(), m.end(), no, bool(m.group(1))))
    marks.sort()
    qmap, amap = defaultdict(dict), defaultdict(dict)
    for i, (pos, mend, no, is_ans) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
        seg = joined[mend:end]  # 只删掉匹配到的标题本身，保留同行后续内容
        parts = re.split(r"【案例\s*(\d+)\s*(?:答案)?】", seg)
        for j in range(1, len(parts) - 1, 2):
            cno = int(parts[j]); body = parts[j + 1]
            body = "\n".join(join_paras([l for l in body.splitlines() if l.strip()]))
            if is_ans:
                amap[no][cno] = body
            else:
                qmap[no][cno] = body
    out = []
    for no, title in CHAPTERS:
        for cno in sorted(qmap.get(no, {})):
            if cno == 0:
                continue
            ctx = qmap[no][cno]
            a = amap.get(no, {}).get(cno, "")
            # 空案例，或有背景无问题无答案的残缺案例
            if not ctx.strip() or (not a.strip() and "问题" not in ctx):
                continue
            out.append(dict(id=f"hq{no}-{cno}", src=source, type="案例",
                            ctx=re.split(r"【问题】", ctx, maxsplit=1)[0].strip() if "【问题】" in ctx else "", q=re.split(r"【问题】", ctx, maxsplit=1)[1].strip() if "【问题】" in ctx else ctx.strip(), a=a if a.strip() else "（原资料中未找到本题参考答案，请结合教材核对）"))
    return out

def int2cn(n):
    nums = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十", 11: "十一"}
    return nums[n]

def split_expected_text(text, maxn=15):
    """在整段文本中按连续题号 1. 2. 3. ... 顺序切分，返回 [(num, start, end)]。"""
    positions = []
    pos, n = 0, 1
    while n <= maxn:
        m = re.search(rf"(?<![0-9.\-]){n}[.．](?=\D)", text[pos:])
        if not m:
            break
        s, e = pos + m.start(), pos + m.end()
        positions.append((n, s, e))
        pos, n = e, n + 1
    return positions

def parse_chuanyang(fname, source, chapters, id_prefix):
    """川杨测试题：试题N 分段，段内按连续题号切分，答：为答案起点。chapters 为归属章节列表。"""
    text = read(fname)
    lines = clean_lines(text)
    # 去掉文件头
    lines = [l for l in lines if "川杨学堂" not in l and "答题时间" not in l
             and not re.match(r"^（第[一二三四五六七八九十]+章", l)
             and "咨询工程师" not in l[:12] and "测试题" not in l[:8]]
    body = "\n".join(lines)
    blocks = re.split(r"试题[一二三四五六七八九十百]+", body)
    cards = []
    qi = 0
    for blk in blocks:
        blines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not blines:
            continue
        btext = "\n".join(blines)
        marks = split_expected_text(btext)
        if not marks:
            continue
        ctx = btext[:marks[0][1]]
        ctx = re.sub(r"问题[^：:]{0,25}[：:]\s*$", "", ctx).strip()
        for i, (num, s, e) in enumerate(marks):
            end = marks[i + 1][1] if i + 1 < len(marks) else len(btext)
            seg = btext[e:end]
            for sep in ("答：", "答:"):
                if sep in seg:
                    seg = seg.split(sep, 1)
                    qtext, atext = seg[0].strip(), seg[1].strip()
                    break
            else:
                # 无"答："分隔：优先按分值标记"（N 分）"切开，否则按第一个句号切
                qtext, atext = seg.strip(), ""
                fm = re.search(r"[（(]\s*\d{1,2}\s*分\s*[）)]", qtext)
                if fm and fm.start() < 120:
                    atext = qtext[fm.end():].strip()
                    qtext = qtext[:fm.end()].strip()
                else:
                    p = qtext.find("。")
                    if 0 < p < len(qtext) - 20:
                        atext = qtext[p + 1:].strip()
                        qtext = qtext[:p + 1].strip()
            qtext = join_paras_str(qtext)
            atext = join_paras_str(atext) if atext else ""
            if not qtext:
                continue
            qi += 1
            cards.append(dict(type="案例" if ctx else "简答", ctx=ctx, q=qtext, a=atext))
    for i, c in enumerate(cards):
        c["id"] = f"{id_prefix}-{i+1}"
        c["src"] = source
    # 过滤表格碎片卡（无句末标点的短行/小数串行，如评分表行），其余无答案的给出占位提示
    cleaned = []
    for c in cards:
        if not re.search(r"[？。！?]", c["q"]) and (len(c["q"]) < 30 or re.search(r"\d\.\d", c["q"])):
            continue
        if not c["a"].strip():
            c["a"] = "（原资料中未找到本题参考答案，请结合教材核对）"
        cleaned.append(c)
    cards = cleaned
    # 归属章节
    by_ch = {no: [] for no in chapters}
    for c in cards:
        for no in chapters:
            d = dict(c); d["id"] = f"{c['id']}c{no}"
            by_ch[no].append(d)
    return by_ch

def parse_heima(fname):
    """黑马逆袭宝典：第X章（X-X分）→ 考点N：内容"""
    text = read(fname)
    lines = clean_lines(text)
    joined = "\n".join(lines)
    chs = {}
    marks = []
    for no, title in CHAPTERS:
        tflex = re.escape(title).replace("与", "与?")
        m = re.search(rf"第{int2cn(no)}章\s*{tflex}", joined)
        if m:
            marks.append((m.start(), no))
    marks.sort()
    for i, (pos, no) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
        seg = joined[pos:end]
        seg = seg[seg.find("\n") + 1:]
        pts = re.split(r"考点\s*(\d+)\s*[：:]", seg)
        items = []
        for j in range(1, len(pts) - 1, 2):
            pno = pts[j]
            body = "\n".join(join_paras([l for l in pts[j + 1].splitlines() if l.strip()]))
            # 标题：在小节标记（一）/换行/行内编号之前的文字；仍过长则在首个空格处截断
            tcut = re.split(r"（[一二三四五六七八九十]+）|\n|(?<![0-9.])\d{1,2}[.．]", body, 1)[0].strip()
            tcut = re.sub(r"[科]{2,}[^\u4e00-\u9fff]*", "", tcut).strip()
            if len(tcut) > 18 and " " in tcut:
                tcut = tcut.split(" ", 1)[0].strip()
            t = tcut[:40] or f"考点{pno}"
            items.append(dict(t=t, c=body.strip()))
        chs[no] = items
    return chs

def fix_garbled_answers(cards):
    """答案为公式图片乱码（如 "P VN="）或建工格式中答案标记后无正文（即图片答案），替换为提示。"""
    for c in cards:
        a = c["a"].strip()
        meaningful = len(re.findall(r"[\u4e00-\u9fff\u2460-\u2473\u24eb-\u24f4]", a))
        is_img = (a and meaningful < 8 and not re.search(r"\d", a)) or not a \
                 or (a.startswith("（原资料中未找到") and "建工" in c.get("src", ""))
        if is_img:
            c["a"] = "（本题答案在原 PDF 中为公式图片，无法提取文字，请对照原资料核对）"

def main():
    chapters = {no: dict(no=no, title=t, questions=[], notes=[]) for no, t in CHAPTERS}
    stats = defaultdict(int)

    # 1. 建工 基础/提高
    for prefix, source in (("jc", "建工网校·基础练习题"), ("tg", "建工网校·提高练习题")):
        for no, title in CHAPTERS:
            f = os.path.join(TEXT_DIR, f"{prefix}__第{int2cn(no)}章　{title}.txt")
            if not os.path.exists(f):
                # 文件名中空格可能是全角/半角差异
                cands = glob.glob(os.path.join(TEXT_DIR, f"{prefix}__第{int2cn(no)}章*{title}*.txt"))
                if not cands:
                    print(f"[MISS] {prefix} ch{no}")
                    continue
                f = cands[0]
            try:
                cards = parse_jianzhu(f, source, no, prefix)
            except Exception as e:
                print(f"[ERR] {f}: {e}")
                continue
            chapters[no]["questions"] += cards
            stats[source] += len(cards)

    # 2. 环球精华习题集
    hq = parse_huanqiu(os.path.join(TEXT_DIR, "hq__2026咨询工程师《现代咨询方法与实务》精华习题集.txt"), "环球网校·精华习题集")
    for c in hq:
        no = int(re.match(r"hq(\d+)-", c["id"]).group(1))
        chapters[no]["questions"].append(c)
    stats["环球网校·精华习题集"] = len(hq)

    # 3. 川杨章节测试
    cy_files = [
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第一章（带参考答案）.txt", [1], "cyt1"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第二章（带参考答案）.txt", [2], "cyt2"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第三、四章（带参考答案）.txt", [3, 4], "cyt34"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第五、六章（带参考答案）.txt", [5, 6], "cyt56"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第七、八章（带参考答案）.txt", [7, 8], "cyt78"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第九章（带参考答案）.txt", [9], "cyt9"),
        ("cy_test__川杨学堂2026咨询工程师-实务测试题第十、十一章（带参考答案）.txt", [10, 11], "cyt1011"),
    ]
    for fname, chs, prefix in cy_files:
        srcname = "川杨学堂·章节测试"
        by_ch = parse_chuanyang(os.path.join(TEXT_DIR, fname), srcname, chs, prefix)
        for no, cards in by_ch.items():
            chapters[no]["questions"] += cards
            stats[f"{srcname}"] += len(cards)

    # 4. 综合卷（全真模拟 + 集训 + 其他三科）
    exams = []
    exam_files = [
        ("*全真模拟考试一（带参考答案）", "川杨·全真模拟卷一"),
        ("*全真模拟考试二（带参考答案）", "川杨·全真模拟卷二"),
        ("*全真模拟考试三（带参考答案）", "川杨·全真模拟卷三"),
        ("*集训内容专题*（带参考答案）", "川杨·集训专题（财务/盈亏平衡/动态指标）"),
        ("*涉及其他三科（带参考答案）", "川杨·跨科专题"),
    ]
    for pattern, label in exam_files:
        cands = sorted(glob.glob(os.path.join(TEXT_DIR, f"cy_exam__{pattern}.txt"))) or \
                sorted(glob.glob(os.path.join(TEXT_DIR, f"cy_jx__{pattern}.txt")))
        f = cands[0] if cands else None
        if not f:
            print(f"[MISS EXAM] {pattern}")
            continue
        by = parse_chuanyang(f, label, [0], f"ex{len(exams)}")
        cards = by[0]
        exams.append(dict(id=f"exam{len(exams)+1}", title=label, questions=cards))
        stats[label] = len(cards)

    # 5. 黑马宝典背诵
    notes = parse_heima(os.path.join(TEXT_DIR, "heimabao__KL-咨询实务-黑马逆袭宝典.txt"))
    for no, items in notes.items():
        chapters[no]["notes"] = items
    stats["黑马宝典考点"] = sum(len(v) for v in notes.values())

    # 输出
    for ch in chapters.values():
        fix_garbled_answers(ch["questions"])
    for e in exams:
        fix_garbled_answers(e["questions"])
    total_q = 0
    index = dict(chapters=[], exams=[dict(id=e["id"], title=e["title"], n=len(e["questions"])) for e in exams],
                 generated="2026-08-31")
    for no in sorted(chapters):
        ch = chapters[no]
        n = len(ch["questions"])
        total_q += n
        src_count = defaultdict(int)
        for c in ch["questions"]:
            src_count[c["src"]] += 1
        index["chapters"].append(dict(no=no, title=ch["title"], n=n, notes=len(ch["notes"]), srcs=dict(src_count)))
        with open(os.path.join(OUT_DIR, f"ch{no}.json"), "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False)
    for e in exams:
        with open(os.path.join(OUT_DIR, f"{e['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(json.dumps(index, ensure_ascii=False, indent=1))
    print("TOTAL questions:", total_q)
    print("STATS:", dict(stats))

    # 无答案题目统计
    noans = [c["id"] for ch in chapters.values() for c in ch["questions"] if not c["a"].strip()]
    noans += [c["id"] for e in exams for c in e["questions"] if not c["a"].strip()]
    print("no-answer:", len(noans), noans[:20])

if __name__ == "__main__":
    main()
