# -*- coding: utf-8 -*-
"""解析 02~05 文件夹的新题源：历年真题、机构模拟卷、专题特训、母题带练、考点讲义。"""
import json, re, os, glob
from collections import defaultdict
import parse as P

TEXT2 = os.environ.get("QUIZ_TEXT2_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "text2"))
OUT_DIR = P.OUT_DIR

AD_SUBSTR = ("押题联系", "名师面授精华", "精准押题", "唯一联系微信", "学员专用 请勿外泄",
             "扫码关注", "环球网校学员专用", "官方网址：www.youlu.com", "优路教育·点亮职业人生",
             "点亮职业人生", "[注：天一文化", "课程咨询：", "导 学 课", "点击查看入群方式")

def clean2(text):
    """text2 专用清洗：在 parse.clean_lines 基础上过滤广告行。"""
    lines = P.clean_lines(text)
    return [l for l in lines if not any(s in l for s in AD_SUBSTR)]

def one(patterns, text):
    """取多种 case 标记中先匹配到的切分点。"""
    ms = []
    for pat in patterns:
        ms += [(m.start(), m.end(), m) for m in re.finditer(pat, text)]
    ms.sort()
    return ms

Q_PAT = r"【问题】|问题[：:]\s*\d"
A_PAT = r"【答案】|【参考答案】|【解析】|【注释】|【解答】"

def interleave_cards(body, ctx_max=0):
    """问题/答案交错格式 → [(q, a)]；ctx 返回第一问之前的内容。"""
    ms = one([Q_PAT, A_PAT], body)
    if not ms:
        return "", []
    ctx = body[:ms[0][0]]
    cards, cur_q, cur_a = [], None, None
    for i, (s, e, m) in enumerate(ms):
        seg_end = ms[i + 1][0] if i + 1 < len(ms) else len(body)
        seg = body[e:seg_end]
        is_q = re.match(Q_PAT + r"$", m.group(0)) or m.group(0).startswith("【问题】") or m.group(0).startswith("问题")
        if is_q:
            if cur_q is not None and cur_q.strip():
                cards.append([cur_q, cur_a or ""])
            cur_q, cur_a = seg, ""
        else:
            if cur_a is None:
                cur_a = seg
            else:
                cur_a += seg
    if cur_q is not None and cur_q.strip():
        cards.append([cur_q, cur_a or ""])
    return "\n".join(P.join_paras([l for l in ctx.splitlines() if l.strip()])), cards

def norm_card(c, ctx):
    q = P.join_paras_str(c[0]).strip()
    a = P.join_paras_str(c[1]).strip()
    if not a:
        a = "（原资料未提供本题参考答案）"
    return dict(type="案例" if ctx else "简答", ctx=ctx, q=q, a=a)

# ---------------- 环球真题解析 ----------------
def parse_zhenti():
    exams = []
    files = sorted(glob.glob(os.path.join(TEXT2, "03__03-*真题解析班*.txt")))
    by_year = defaultdict(list)
    for f in files:
        m = re.search(r"(2\d)年真题解析", os.path.basename(f))
        if not m:
            continue
        if "Removed" in os.path.basename(f):
            continue
        by_year["20" + m.group(1)].append(f)
    for year in sorted(by_year):
        cards = []
        for f in by_year[year]:
            text = "\n".join(clean2(P.read(os.path.basename(f)) if False else open(f, encoding="utf-8", errors="replace").read()))
            # 按大题切分
            ms = one([r"第[一二三四五六七八九十]+题\s*[（(]\d+\s*分[）)]?",
                      r"【试题[一二三四五六七八九十]+】",
                      r"试题[一二三四五六七八九十]+[（(]\d+\s*分[）)]"], text)
            if not ms:
                continue
            for i, (s, e, m) in enumerate(ms):
                end = ms[i + 1][0] if i + 1 < len(ms) else len(text)
                title = re.sub(r"\s+", "", m.group(0))
                ctx, pairs = interleave_cards(text[e:end])
                if not pairs:
                    continue
            for j, (q, a) in enumerate(pairs):
                c = norm_card([q, a], ctx)
                tag = re.sub(r"[【】]", "", title)
                tag = re.split(r"[（(]", tag)[0]
                c["q"] = f"（{tag}·问{j+1}）{c['q']}" if len(pairs) > 1 else f"（{tag}）{c['q']}"
                c["ctx"] = ctx
                cards.append(c)
        eid = f"zt{year[2:]}"
        for i, c in enumerate(cards):
            c["id"] = f"{eid}-{i+1}"; c["src"] = "环球网校·真题解析"
        exams.append(dict(id=eid, title=f"{year}年历年真题（环球解析版）", kind="zhenti", questions=cards))
    return exams

# ---------------- 优路甄题详解 ----------------
def parse_youlu():
    f = os.path.join(TEXT2, "03__01-2026年咨询实务-优路教育-甄题详解班-刘老师_讲义_2026咨询甄题详解《方法与实务》打印版.pdf.txt")
    text = open(f, encoding="utf-8", errors="replace").read()
    split = re.search(r"甄题详解[—\s-]{1,4}模拟卷", text)
    parts = [("zt", text[:split.start()]), ("mn", text[split.start():])] if split else [("zt", text)]
    exams = []
    for kind, body in parts:
        # 案例分组：按【案例N】的首个出现位置分段（重复出现的作为页眉忽略）
        seen = {}
        for m in re.finditer(r"【案例([一二三四五六七八九十]+)】", body):
            seen.setdefault(m.group(1), m.start())
        bounds = sorted((pos, num) for num, pos in seen.items())
        cards = []
        for i, (pos, num) in enumerate(bounds):
            end = bounds[i + 1][0] if i + 1 < len(bounds) else len(body)
            seg = body[pos:end]
            ctx, pairs = interleave_cards(seg)
            if not pairs:
                continue
            for j, (q, a) in enumerate(pairs):
                c = norm_card([q, a], ctx)
                c["ctx"] = ctx
                cards.append(c)
        # 去掉"问题总览"幽灵卡（无答案且为多问编号列表）
        cards = [c for c in cards if not (c["a"].startswith("（原资料未提供") and re.match(r"^\s*\d[.．]", c["q"]) and re.search(r"\d[.．].*\d[.．]", c["q"], re.S))]
        eid = "ylzt" if kind == "zt" else "ylmn"
        title = "优路·历年真题案例详解" if kind == "zt" else "优路·甄题模拟案例"
        for i, c in enumerate(cards):
            c["id"] = f"{eid}-{i+1}"; c["src"] = "优路教育·甄题详解"
        exams.append(dict(id=eid, title=title, kind="zhenti" if kind == "zt" else "mock", questions=cards))
    return exams

# ---------------- 天一强化母题带练 ----------------
MODULE_CH = {"模块一": [1, 2], "模块二": [4], "模块三": [8], "模块四": [9], "模块五": [10], "模块六": [11]}

def parse_tianyi_muti():
    files = sorted(glob.glob(os.path.join(TEXT2, "03__05-*强化母题带练*.txt")))
    by_ch = defaultdict(list)
    n = 0
    for f in files:
        base = os.path.basename(f)
        mod = next((k for k in MODULE_CH if k in base), None)
        if not mod or "Removed" in base:
            continue
        text = "\n".join(clean2(open(f, encoding="utf-8", errors="replace").read()))
        # 去掉"题后总结"等非题目小节，防止编号要点被误认为问题
        text = re.split(r"【题后总结】", text)[0]
        blocks = re.split(r"习题[（(][一二三四五六七八九十]+[）)]", text)
        for blk in blocks[1:]:
            # 先按【解析】切开题目区/答案区，再在题目区内按编号切问题（小数 6.63 不再误判）
            parts = re.split(r"【解析】", blk, 1)
            qpart = parts[0]
            apart = parts[1] if len(parts) > 1 else ""
            qm2 = re.search(r"(?m)^\s*问题[：:]?\s*$|^\s*问题[：:]", qpart)
            if qm2:
                ctx = P.join_paras_str(qpart[:qm2.start()]).strip()
                qtext = qpart[qm2.end():]
            else:
                ctx, qtext = "", qpart
            qlist = []
            for seg in re.split(r"(?m)^(?=[1-9][.．](?!\d))", qtext)[1:]:
                q = P.join_paras_str(seg).strip()
                q = re.sub(r"[（(](计算|要求)[^）)]*[）)]\s*$", "", q).strip()
                if len(q) >= 6 and re.search(r"[\u4e00-\u9fff]", q):
                    qlist.append(q)
            ans = {}
            for m in re.finditer(r"问题\s*([1-9])\s*[：:；]", apart):
                num = int(m.group(1))
                nxt = re.search(r"问题\s*[1-9]\s*[：:；]", apart[m.end():])
                a_end = m.end() + nxt.start() if nxt else len(apart)
                ans[num] = P.join_paras_str(apart[m.end():a_end]).strip()
            for j, q in enumerate(qlist):
                n += 1
                c = dict(type="案例" if ctx else "简答", ctx=ctx, q=q,
                         a=ans.get(j + 1, "（原资料未提供本题参考答案）"),
                         id=f"tym{n}", src="天一网校·强化母题带练")
                for ch in MODULE_CH[mod]:
                    d = dict(c); d["id"] = f"tym{n}c{ch}"
                    by_ch[ch].append(d)
    return by_ch

# ---------------- 环球专题特训（按章） ----------------
def parse_hq_texun():
    files = sorted(glob.glob(os.path.join(TEXT2, "04__03-*实务特训*.txt")))
    by_ch = defaultdict(list)
    n = 0
    for f in files:
        if "Removed" in f:
            continue
        text = "\n".join(clean2(open(f, encoding="utf-8", errors="replace").read()))
        m = re.search(r"第([一二三四五六七八九十]+)章", text[:300])
        ch_no = P.int2cn.__class__ and next((no for no, t in P.CHAPTERS if f"第{P.int2cn(no)}章" == f"第{m.group(1)}章"), None) if m else None
        if not ch_no:
            continue
        cases = re.split(r"【案例\s*\d+】", text)
        for seg in cases[1:]:
            ctx, pairs = interleave_cards(seg)
            if not pairs:
                continue
            for q, a in pairs:
                # 无答案标记时，问号后的内容是内联答案
                if not a.strip():
                    m2 = re.search(r"\?|？", q)
                    if m2 and len(q) - m2.end() >= 30:
                        q, a = q[:m2.end()], q[m2.end():]
                n += 1
                c = norm_card([q, a], ctx)
                c["id"] = f"hqt{n}c{ch_no}"; c["src"] = "环球网校·专题特训"
                by_ch[ch_no].append(c)
    return by_ch

# ---------------- 综合模拟卷（通用交错格式） ----------------
def make_exam(eid, title, kind, segments, src):
    """segments: [(title_tag, body)] → exam dict"""
    cards = []
    for tag, body in segments:
        ctx, pairs = interleave_cards(body)
        if not pairs:
            # 试题里可能没有【问题】标记，整段作为案例卡
            txt = P.join_paras_str(body).strip()
            if len(txt) > 60:
                cards.append(dict(type="案例", ctx="", q=txt, a="（原资料未提供本题参考答案）"))
            continue
        for j, (q, a) in enumerate(pairs):
            c = norm_card([q, a], ctx)
            if tag:
                c["q"] = f"（{tag}）{c['q']}"
            cards.append(c)
    for i, c in enumerate(cards):
        c["id"] = f"{eid}-{i+1}"; c["src"] = src
    return dict(id=eid, title=title, kind=kind, questions=cards)

def split_cases(text, pats):
    ms = one(pats, text)
    segs = []
    for i, (s, e, m) in enumerate(ms):
        end = ms[i + 1][0] if i + 1 < len(ms) else len(text)
        segs.append((re.sub(r"\s+", "", m.group(0))[:24], text[e:end]))
    return segs

def parse_two_section(path_glob, eid, title, src, case_pat=r"【第[一二三四五六七八九十]+题】"):
    """题目区 + 独立参考答案区（按 题号+问题号 配对），适用于环观点睛卷/查缺补漏卷。"""
    import os as _os
    fs = sorted(glob.glob(_os.path.join(TEXT2, path_glob)))
    fs = [f for f in fs if "Removed" not in f]
    if not fs:
        print("[MISS]", path_glob)
        return None
    t = "\n".join(clean2(open(fs[0], encoding="utf-8", errors="replace").read()))
    sp = re.search(r"参考答案", t)
    if not sp:
        return None
    qpart, apart = t[:sp.start()], t[sp.start():]
    # 题目区：题号 → (标签, ctx, [(qno, qtext)])
    qs = {}
    cms = list(re.finditer(case_pat + r"[^\n]{0,60}", qpart))
    for i, cm in enumerate(cms):
        end = cms[i + 1].start() if i + 1 < len(cms) else len(qpart)
        cn = i + 1
        seg = qpart[cm.end():end]
        qm = re.search(r"【背景资料\d?】", seg)
        if not qm:
            qm = re.search(r"【问题】", seg)
        ctx = P.join_paras_str(seg[:qm.start()]).strip() if qm else ""
        qtext = seg[qm.end():] if qm else seg
        pairs = []
        pm = list(re.finditer(r"【问题】\s*([1-9]\d?)[.．、]?", qtext))
        for j, p in enumerate(pm):
            pe = pm[j + 1].start() if j + 1 < len(pm) else len(qtext)
            pairs.append((int(p.group(1)), P.join_paras_str(qtext[p.end():pe]).strip()))
        if not pairs and qtext.strip():
            pairs.append((1, P.join_paras_str(qtext).strip()))
        qs[cn] = dict(tag=re.sub(r"\s+", "", cm.group(0))[:30], ctx=ctx, pairs=pairs)
    # 答案区：题号 → [(qno, atext)]（用去掉行尾通配的“裸”题号模式，避免吞掉首个【问题】）
    bare_pat = case_pat.split("[^\\n]")[0]
    ans = {}
    ams = list(re.finditer(bare_pat, apart))
    for i, am in enumerate(ams):
        end = ams[i + 1].start() if i + 1 < len(ams) else len(apart)
        cn = i + 1
        seg = apart[am.end():end]
        alist = []
        pm = list(re.finditer(r"【问题】\s*([1-9]\d?)[.．、]?", seg))
        for j, p in enumerate(pm):
            pe = pm[j + 1].start() if j + 1 < len(pm) else len(seg)
            alist.append((int(p.group(1)), P.join_paras_str(seg[p.end():pe]).strip()))
        ans[cn] = alist
    cards = []
    for cn, d in qs.items():
        for j, (qno, qtext) in enumerate(d["pairs"]):
            a = ""
            for (ano, atext) in ans.get(cn, []):
                if ano == qno:
                    a = atext
                    break
            if not a and ans.get(cn) and len(ans[cn]) == len(d["pairs"]):
                a = ans[cn][j][1]
            tag = re.sub(r"[【】]", "", d["tag"])
            tag = re.sub(r"^第[一二三四五六七八九十]+题\s*", "", tag)
            tag = re.sub(r"^[^（(]*[（(]", "", tag).rstrip("）()") or f"题{cn}"
            tag = re.split(r"[（(]", tag)[0] or f"题{cn}"
            a = a.strip()
            a = re.sub(r"^【答案】\s*", "", a)
            cards.append(dict(type="案例", ctx=d["ctx"],
                              q=f"（第{cn}题·{tag[:20]}）{qtext}",
                              a=a or "（原资料未提供本题参考答案）"))
    for i, c in enumerate(cards):
        c["id"] = f"{eid}-{i+1}"; c["src"] = src
    return dict(id=eid, title=title, kind="mock", questions=cards)

def parse_hqwr():
    """环球万人模考：题目区（每题一个【问题】头+编号小问列表）+ 参考答案区（【试题N】【问题】N.【答案】）。"""
    fs = sorted(glob.glob(os.path.join(TEXT2, "03__08-*万人模考解析（一）*.txt")))
    fs = [f for f in fs if "Removed" not in f]
    if not fs:
        print("[MISS] hqwr")
        return None
    t = "\n".join(clean2(open(fs[-1], encoding="utf-8", errors="replace").read()))
    sp = re.search(r"参考答案", t)
    if not sp:
        return None
    qpart, apart = t[:sp.start()], t[sp.start():]
    # 答案区：题号 → {小问号: 答案}
    ans = {}
    ams = list(re.finditer(r"【试题([一二三四五六七八九十]+)】", apart))
    for i, am in enumerate(ams):
        end = ams[i + 1].start() if i + 1 < len(ams) else len(apart)
        seg = apart[am.end():end]
        lst = {}
        pm = list(re.finditer(r"【问题】\s*([1-9]\d?)\s*[.．]?", seg))
        for j, p in enumerate(pm):
            pe = pm[j + 1].start() if j + 1 < len(pm) else len(seg)
            body = P.join_paras_str(seg[p.end():pe]).strip()
            lst[int(p.group(1))] = re.sub(r"^【答案】\s*", "", body).strip()
        ans[am.group(1)] = lst
    cards = []
    qms = list(re.finditer(r"【试题([一二三四五六七八九十]+)】([^\n]{0,60})", qpart))
    for i, qm in enumerate(qms):
        end = qms[i + 1].start() if i + 1 < len(qms) else len(qpart)
        seg = qpart[qm.end():end]
        cn = qm.group(1)
        tag = re.sub(r"[()（）]", "", qm.group(2)).strip()[:24]
        pm = re.search(r"【问题】", seg)
        ctx = P.join_paras_str(seg[:pm.start()]).strip() if pm else ""
        qtext = seg[pm.end():] if pm else seg
        qlist = [P.join_paras_str(s).strip() for s in
                 re.split(r"(?m)^(?=[1-9][.．](?!\d))", qtext)[1:]]
        qlist = [q for q in qlist if len(q) >= 6]
        alst = ans.get(cn, {})
        for j, qt in enumerate(qlist):
            a = alst.get(j + 1, "")
            if not a and len(alst) == len(qlist):
                a = list(alst.values())[j]
            cards.append(dict(type="案例", ctx=ctx, q=f"（试题{cn}·{tag}·问{j+1}）{qt}",
                              a=a or "（原资料未提供本题参考答案）"))
    for i, c in enumerate(cards):
        c["id"] = f"hqwr-{i+1}"; c["src"] = "环球网校·万人模考"
    return dict(id="hqwr", title="环球网校·万人模考卷（含解析）", kind="mock", questions=cards)

def parse_mocks():
    exams = []
    CASE_PATS = [r"【第[一二三四五六七八九十]+题】",
                 r"第[一二三四五六七八九十]+题\s*[（(]?[^，。]{0,30}分?[）)]?",
                 r"【试题[一二三四五六七八九十]+】",
                 r"试题[一二三四五六七八九十]+[（(]\d+\s*分[）)]"]

    def load(pat):
        fs = sorted(glob.glob(os.path.join(TEXT2, pat)))
        if not fs:
            print("[MISS]", pat)
            return None
        return "\n".join(clean2(open(fs[0], encoding="utf-8", errors="replace").read()))

    # 环观点睛卷 / 查缺补漏卷（题目区+答案区配对结构）
    e = parse_two_section("05__11-*临考点睛卷*.txt", "hqdj", "环球网校·临考点睛卷", "环球网校·点睛卷")
    if e:
        exams.append(e)
    e = parse_two_section("03__12-*查缺补漏*.txt", "hqcx", "环球网校·查缺补漏卷", "环球网校·查缺补漏",
                          case_pat=r"第[一二三四五六七八九十]+题\s*[^\n]{0,40}")
    if e:
        exams.append(e)
    # 环球万人模考解析（题目区+参考答案区，题目区为编号小问列表）
    e = parse_hqwr()
    if e:
        exams.append(e)
    # 优路考前集训试卷（题目在前，答案集中附后按试题分组）
    t = load("04__06-*集训-试卷*.txt")
    if t:
        sp = re.search(r"参考答案\s*试题[一二三四五六七八九十]+\s*【?参考答案】?", t)
        if sp:
            qpart, apart = t[:sp.start()], t[sp.start():]
            ans = {}
            ams = list(re.finditer(r"试题([一二三四五六七八九十]+)\s*【?参考答案】?", apart))
            for i, a in enumerate(ams):
                a_end = ams[i + 1].start() if i + 1 < len(ams) else len(apart)
                seg = apart[a.end():a_end]
                am = list(re.finditer(r"(?<![0-9.])([1-9])[.．、]\s*【答案】", seg))
                lst = {}
                for j, b in enumerate(am):
                    b_end = am[j + 1].start() if j + 1 < len(am) else len(seg)
                    lst[int(b.group(1))] = P.join_paras_str(seg[b.end():b_end]).strip()
                ans[a.group(1)] = lst
            cards = []
            cms = list(re.finditer(r"试题([一二三四五六七八九十]+)[（(]?\d*\s*分?[）)]?", qpart))
            for i, cm in enumerate(cms):
                seg_end = cms[i + 1].start() if i + 1 < len(cms) else len(qpart)
                body = qpart[cm.end():seg_end]
                qm = re.search(r"【问题】", body)
                if not qm:
                    continue
                ctx = P.join_paras_str(body[:qm.start()]).strip()
                qlines = re.split(r"(?m)^(?=[1-9][.．])", body[qm.end():])
                pairs = [(k + 1, P.join_paras_str(s).strip()) for k, s in enumerate(qlines[1:])
                         if len(P.join_paras_str(s).strip()) >= 6]
                alst = ans.get(cm.group(1), {})
                for j, (qno, qt) in enumerate(pairs):
                    a = alst.get(qno, "") or (alst.get(j + 1, "") if len(alst) == len(pairs) else "")
                    cards.append(dict(type="案例", ctx=ctx,
                                      q=f"（试题{cm.group(1)}·问{j+1}）{qt}",
                                      a=a.strip() or "（原资料未提供本题参考答案）"))
            for i, c in enumerate(cards):
                c["id"] = f"yljs-{i+1}"; c["src"] = "优路教育·集训卷"
            if cards:
                exams.append(dict(id="yljs", title="优路教育·考前集训卷", kind="mock", questions=cards))
    # 环球专题特训兜底（若按章解析为空则并入综合卷）
    # 天一AB卷（两套卷+独立答案解析）
    t = load("05__13-*AB卷*.txt")
    if t:
        papers = [(r"考前模拟卷（一）(.*?)考前模拟试卷（一）答案解析", r"考前模拟试卷（一）答案解析(.*?)考前模拟卷（二）", "A"),
                  (r"考前模拟卷（二）(.*?)考前模拟试卷（二）答案解析", r"考前模拟试卷（二）答案解析(.*)$", "B")]
        for pat, apat, ptag in papers:
            m = re.search(pat, t, re.S)
            if not m:
                print(f"[MISS] tyab 试卷{ptag}")
                continue
            body = m.group(1)
            answers = {}
            ans_m = re.search(apat, t, re.S)
            if ans_m:
                seg_all = ans_m.group(1)
                for am in re.finditer(r"【试题([一二三四五六七八九十]+)[·.]?\s*参考答案】", seg_all):
                    seg_start = am.end()
                    nxt = re.search(r"【试题[一二三四五六七八九十]+[·.]?\s*参考答案】", seg_all[seg_start:])
                    seg_end = seg_start + nxt.start() if nxt else len(seg_all)
                    answers[am.group(1)] = P.join_paras_str(seg_all[seg_start:seg_end]).strip()
            segs = []
            for cm in re.finditer(r"试题([一二三四五六七八九十]+)", body):
                nxt = re.search(r"试题[一二三四五六七八九十]+", body[cm.end():])
                seg_end = cm.end() + nxt.start() if nxt else len(body)
                seg = body[cm.end():seg_end]
                cn = cm.group(1)
                if cn in answers:
                    seg = seg + "\n【答案】" + answers[cn]
                segs.append((f"试题{cn}", seg))
            eid = "tyabA" if ptag == "A" else "tyabB"
            exams.append(make_exam(eid, f"天一网校·考前模拟卷{ptag}", "mock", segs, "天一网校·考前模拟"))
    # 建工预测全真模拟 3 套（建工练习题格式）
    for i, pat in enumerate(["（一）", "（二）", "（三）"]):
        fs = glob.glob(os.path.join(TEXT2, f"05__10-*预测全真模拟卷{pat}*.txt"))
        if not fs:
            print(f"[MISS] 建工三套卷{pat}")
            continue
        cards = P.parse_jianzhu_txt(open(fs[0], encoding="utf-8", errors="replace").read(),
                                    "建工网校·预测全真模拟", 0, f"jg3{i+1}")
        for c in cards:
            c["id"] = f"jg3{i+1}-{c['id'].split('-')[-1]}"
        exams.append(dict(id=f"jg3{i+1}", title=f"建工网校·预测全真模拟卷{pat}", kind="mock", questions=cards))
    # 环球专题特训合并为一张综合卷（若按章解析无结果时使用）
    return [e for e in exams if e["questions"]]

# ---------------- 天一考点讲义 → 背诵 ----------------
def parse_tianyi_notes():
    files = sorted(glob.glob(os.path.join(TEXT2, "04__01-*.txt")))
    by_ch = defaultdict(list)
    for f in files:
        base = os.path.basename(f)
        m = re.search(r"第([一二三四五六七八九十]+)章", base)
        if not m:
            continue
        ch_no = next((no for no, t in P.CHAPTERS if P.int2cn(no) == m.group(1)), None)
        if not ch_no:
            continue
        text = "\n".join(clean2(open(f, encoding="utf-8", errors="replace").read()))
        # 标题：文件名里 考点N-名称 部分
        title_m = re.findall(r"考点\d[-_]([^_.]+?)(?:-考点\d[-_]|\.pdf)?", base)
        title = "冲刺考点：" + "、".join(dict.fromkeys(title_m)) if title_m else "天一冲刺讲义"
        body = P.join_paras_str(text).strip()
        if len(body) > 100:
            by_ch[ch_no].append(dict(t=title[:50], c=body))
    return by_ch

def main():
    from collections import Counter
    all_zhenti, all_exams = [], []
    chapters = {no: dict(no=no, title=t, questions=[], notes=[]) for no, t in P.CHAPTERS}

    zt = parse_zhenti()
    print("真题:", [(e["id"], len(e["questions"])) for e in zt])
    yl = parse_youlu()
    print("优路:", [(e["id"], len(e["questions"])) for e in yl])
    mocks = parse_mocks()
    print("综合卷:", [(e["id"], len(e["questions"])) for e in mocks])

    tym = parse_tianyi_muti()
    print("天一母题:", {k: len(v) for k, v in sorted(tym.items())})
    hqt = parse_hq_texun()
    print("专题特训:", {k: len(v) for k, v in sorted(hqt.items())})
    tyn = parse_tianyi_notes()
    print("天一考点讲义:", {k: len(v) for k, v in sorted(tyn.items())})

    # 合并进现有章节 JSON（幂等：先移除本脚本负责的来源再追加）
    NEW_SRCS = {"天一网校·强化母题带练", "环球网校·专题特训"}
    for no in sorted(chapters):
        path = os.path.join(OUT_DIR, f"ch{no}.json")
        data = json.load(open(path, encoding="utf-8"))
        data["questions"] = [c for c in data["questions"] if c["src"] not in NEW_SRCS]
        data["notes"] = [n for n in data["notes"] if not n["t"].startswith("冲刺考点：")]
        data["questions"] += tym.get(no, []) + hqt.get(no, [])
        data["notes"] += tyn.get(no, [])
        ids = [c["id"] for c in data["questions"]]
        assert len(ids) == len(set(ids)), f"dup ids ch{no}"
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)

    # 更新 index.json
    idx = json.load(open(os.path.join(OUT_DIR, "index.json"), encoding="utf-8"))
    for ch in idx["chapters"]:
        d = json.load(open(os.path.join(OUT_DIR, f"ch{ch['no']}.json"), encoding="utf-8"))
        ch["n"] = len(d["questions"])
        ch["notes"] = len(d["notes"])
        srcs = defaultdict(int)
        for c in d["questions"]:
            srcs[c["src"]] += 1
        ch["srcs"] = dict(srcs)
    kind = {e["id"]: e.get("kind", "mock") for e in idx.get("exams", [])}
    new_exams = zt + yl + mocks
    new_ids = {e["id"] for e in new_exams}
    all_exams = [e for e in idx.get("exams", []) if e["id"] not in new_ids] + [
        dict(id=e["id"], title=e["title"], n=len(e["questions"]), kind=e["kind"]) for e in new_exams
    ]
    idx["exams"] = all_exams
    idx["generated"] = "2026-08-31"
    json.dump(idx, open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8"), ensure_ascii=False)

    for e in zt + yl + mocks:
        json.dump(e, open(os.path.join(OUT_DIR, f"{e['id']}.json"), "w", encoding="utf-8"), ensure_ascii=False)

    noans = [c["id"] for e in zt + yl + mocks for c in e["questions"] if "未提供" not in c["a"] and len(c["a"]) < 8]
    print("no-answer:", noans[:10])

if __name__ == "__main__":
    main()
