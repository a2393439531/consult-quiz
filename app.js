/* 咨询工程师《现代咨询方法与实务》刷题应用 */
"use strict";

const INDEX_URL = "data/index.json";
const LS_KEY = "cctp2026_progress_v1";

/* ---------- 进度存储 ---------- */
function loadProgress() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { return {}; }
}
function saveStatus(qid, s) {
  const p = loadProgress();
  p[qid] = { s, t: Date.now() };
  localStorage.setItem(LS_KEY, JSON.stringify(p));
}
function getStatus(qid) {
  const v = loadProgress()[qid];
  return v ? v.s : -1; // -1 未做, 0 不会, 1 模糊, 2 会
}
function clearProgress() { localStorage.removeItem(LS_KEY); render(); }

/* ---------- 数据缓存 ---------- */
const dataCache = {};
async function loadJSON(url) {
  if (!dataCache[url]) dataCache[url] = fetch(url).then(r => { if (!r.ok) throw new Error(url); return r.json(); });
  return dataCache[url];
}
async function loadChapter(no) { return loadJSON(`data/ch${no}.json`); }
async function loadExam(id) { return loadJSON(`data/${id}.json`); }

/* ---------- 工具 ---------- */
function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
const STATUS_NAME = ["不会", "模糊", "会"];

/* ---------- 路由 ---------- */
window.addEventListener("hashchange", render);

async function render() {
  const hash = location.hash || "#/";
  const app = document.getElementById("app");
  const [_, route, a, b, c] = hash.split("/");
  document.querySelectorAll(".tabbar a").forEach(el => {
    el.classList.toggle("on", el.getAttribute("data-tab") === route || (route === "" && el.dataset.tab === "home") || (route === "ch" && el.dataset.tab === "chapters") || (route === "notes" && el.dataset.tab === "chapters") || (route === "quiz" && el.dataset.tab === "chapters"));
  });
  try {
    if (!route) await pageHome(app);
    else if (route === "chapters") await pageChapters(app);
    else if (route === "ch") await pageChapter(app, +a);
    else if (route === "quiz") await pageQuiz(app, a, b, c);
    else if (route === "notes") await pageNotes(app, +a);
    else if (route === "exams") await pageExams(app);
    else if (route === "wrong") await pageWrong(app);
    else app.innerHTML = '<div class="empty">页面不存在</div>';
  } catch (e) {
    app.innerHTML = `<div class="empty">加载失败：${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

/* ---------- 首页 ---------- */
async function pageHome(app) {
  const idx = await loadJSON(INDEX_URL);
  const p = loadProgress();
  const done = Object.keys(p).length;
  const wrongCnt = Object.values(p).filter(v => v.s === 0).length;
  const totN = idx.chapters.reduce((s, ch) => s + ch.n, 0) + idx.exams.reduce((s, e) => s + e.n, 0);
  app.innerHTML = `
  <div class="header">
    <h1>咨询工程师 · 实务刷题</h1>
    <div class="sub">2026《现代咨询方法与实务》章节复习与题库 · 更新于 ${idx.generated}</div>
    <div class="stats-row">
      <div class="stat"><b>${totN}</b><span>题库总题数</span></div>
      <div class="stat"><b>${done}</b><span>已作答</span></div>
      <div class="stat"><b>${wrongCnt}</b><span>待攻克</span></div>
    </div>
  </div>
  <div class="wrap">
    <div class="section-title">章节刷题<a class="more" href="#/chapters">全部章节 →</a></div>
    <div class="ch-list">${idx.chapters.map(ch => chCard(ch)).join("")}</div>
    <div class="section-title">综合模拟卷<a class="more" href="#/exams">全部 →</a></div>
    <div class="ch-list">${idx.exams.map(e => `
      <a class="ch-card" href="#/quiz/exam/${e.id}">
        <div class="ch-no" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)">卷</div>
        <div class="ch-info"><div class="t">${esc(e.title)}</div><div class="m">${e.n} 题</div></div>
      </a>`).join("")}</div>
    <div class="footer-note">数据来源于 2026 年备考资料 PDF（建工网校 / 环球网校 / 川杨学堂），仅供个人学习使用</div>
  </div>`;
  updateChapterBars(idx);
}

function chCard(ch) {
  return `
  <a class="ch-card" href="#/ch/${ch.no}">
    <div class="ch-no">${ch.no}</div>
    <div class="ch-info">
      <div class="t">第${cn(ch.no)}章 ${esc(ch.title)}</div>
      <div class="m">${ch.n} 题 · ${ch.notes ? ch.notes + " 个背诵考点 · " : ""}${Object.keys(ch.srcs).length} 个题源</div>
      <div class="ch-bar"><i style="width:0%"></i></div>
    </div>
    <div class="ch-pct"></div>
  </a>`;
}

function cn(n) { return ["一","二","三","四","五","六","七","八","九","十","十一"][n-1] || n; }

/* ---------- 章节列表 ---------- */
async function pageChapters(app) {
  const idx = await loadJSON(INDEX_URL);
  const p = loadProgress();
  app.innerHTML = `
  <div class="header"><h1>全部章节</h1><div class="sub">按章节复习 · 点击章节进入</div></div>
  <div class="wrap"><div class="ch-list">
    ${idx.chapters.map(ch => chCard(ch)).join("")}
  </div></div>`;
  updateChapterBars(idx);
}

async function updateChapterBars(idx) {
  // 载入各章题 id 计算进度（并行）
  await Promise.all(idx.chapters.map(async ch => {
    const d = await loadChapter(ch.no);
    let done = 0, ok = 0;
    d.questions.forEach(q => { const s = getStatus(q.id); if (s >= 0) done++; if (s === 2) ok++; });
    const pct = d.questions.length ? Math.round(ok / d.questions.length * 100) : 0;
    const cards = document.querySelectorAll(`a.ch-card[href="#/ch/${ch.no}"]`);
    cards.forEach(card => {
      const bar = card.querySelector(".ch-bar i");
      const pctEl = card.querySelector(".ch-pct");
      if (bar) bar.style.width = pct + "%";
      if (pctEl) { pctEl.textContent = done ? pct + "%" : ""; pctEl.style.color = pct >= 80 ? "var(--ok)" : pct >= 40 ? "var(--warn)" : "var(--bad)"; }
    });
  }));
}

/* ---------- 章节详情（浏览 + 入口） ---------- */
let browseState = { no: null, src: "全部", kw: "", expanded: {} };

async function pageChapter(app, no) {
  const d = await loadChapter(no);
  const idx = await loadJSON(INDEX_URL);
  browseCache = d.questions;
  const meta = idx.chapters.find(c => c.no === no);
  const srcs = ["全部", ...Object.keys(d.questions.reduce((m, q) => (m[q.src] = 1, m), {}))];
  if (browseState.no !== no) browseState = { no, src: "全部", kw: "", expanded: {} };
  const list = d.questions.filter(q =>
    (browseState.src === "全部" || q.src === browseState.src) &&
    (!browseState.kw || (q.q + q.ctx + q.a).includes(browseState.kw)));
  app.innerHTML = `
  <div class="header">
    <h1>第${cn(no)}章 ${esc(d.title)}</h1>
    <div class="sub">共 ${d.questions.length} 题 · ${meta && meta.notes ? meta.notes + " 个背诵考点" : ""}</div>
    <div class="btn-row" style="margin-top:14px">
      <a class="btn" href="#/quiz/ch/${no}" style="flex:1">▶ 开始刷题</a>
      <a class="btn ghost" href="#/quiz/ch/${no}/wrong" style="flex:1">🔁 只刷错题</a>
      ${d.notes && d.notes.length ? `<a class="btn ghost" href="#/notes/${no}" style="flex:1">📖 背诵考点</a>` : ""}
    </div>
  </div>
  <div class="wrap">
    <div class="filters">${srcs.map(s => `<span class="chip ${s === browseState.src ? "on" : ""}" data-src="${esc(s)}">${esc(s)}</span>`).join("")}</div>
    <input class="search" id="kw" placeholder="搜索关键词（题干 / 答案）…" value="${esc(browseState.kw)}">
    <div id="qlist">${list.map((q, i) => qItem(q, i)).join("") || '<div class="empty">没有符合条件的题目</div>'}</div>
  </div>`;
  // 事件
  app.querySelectorAll(".chip").forEach(el => el.onclick = () => { browseState.src = el.dataset.src; render(); });
  const kw = document.getElementById("kw");
  kw.oninput = () => { browseState.kw = kw.value.trim(); refreshList(d); };
}
function refreshList(d) {
  const list = d.questions.filter(q =>
    (browseState.src === "全部" || q.src === browseState.src) &&
    (!browseState.kw || (q.q + q.ctx + q.a).includes(browseState.kw)));
  document.getElementById("qlist").innerHTML = list.map((q, i) => qItem(q, i)).join("") || '<div class="empty">没有符合条件的题目</div>';
  bindToggles();
}
function qItem(q, i) {
  const open = !!browseState.expanded[q.id];
  const st = getStatus(q.id);
  const stColor = st === 2 ? "var(--ok)" : st === 1 ? "var(--warn)" : st === 0 ? "var(--bad)" : "#c3cbd9";
  return `<div class="q-item" data-qid="${esc(q.id)}">
    <div class="q-head">
      <span class="q-badge ${q.type === "案例" ? "case" : "short"}">${q.type}</span>
      <div class="q-text">
        ${q.ctx ? `<div class="q-ctx">${esc(q.ctx)}</div>` : ""}
        ${esc(q.q)}
        <div class="q-src">${esc(q.src)} · <span style="color:${stColor}">${st >= 0 ? STATUS_NAME[st] : "未做"}</span></div>
      </div>
    </div>
    ${open ? `<div class="q-body"><div class="ans-label">参考答案</div><div class="ans">${esc(q.a)}</div></div>` : ""}
    <button class="toggle-btn" data-tid="${esc(q.id)}">${open ? "收起答案" : "查看答案"}</button>
  </div>`;
}
function bindToggles() {
  document.querySelectorAll(".toggle-btn").forEach(b => b.onclick = () => {
    const id = b.dataset.tid;
    browseState.expanded[id] = !browseState.expanded[id];
    const item = b.closest(".q-item");
    const open = browseState.expanded[id];
    const q = currentBrowseQuestion(id);
    if (!q) return;
    item.querySelector(".q-body, .toggle-btn").remove();
    item.insertAdjacentHTML("beforeend", (open ? `<div class="q-body"><div class="ans-label">参考答案</div><div class="ans">${esc(q.a)}</div></div>` : "") + `<button class="toggle-btn" data-tid="${esc(id)}">${open ? "收起答案" : "查看答案"}</button>`);
    bindToggles();
  });
}
let browseCache = null;
function currentBrowseQuestion(id) {
  return browseCache && browseCache.find(q => q.id === id);
}

/* ---------- 刷题模式 ---------- */
let quiz = null;
async function pageQuiz(app, kind, key, mode) {
  let questions, title, backHref;
  if (kind === "ch") {
    const no = +key;
    const d = await loadChapter(no);
    questions = d.questions;
    title = `第${cn(no)}章 ${d.title}`;
    backHref = `#/ch/${no}`;
    if (!browseCache || browseCache !== questions) browseCache = questions;
  } else {
    const e = await loadExam(key);
    questions = e.questions;
    title = e.title;
    backHref = "#/exams";
  }
  const p = loadProgress();
  if (mode === "wrong") questions = questions.filter(q => getStatus(q.id) === 0);
  if (!questions.length) { app.innerHTML = `<div class="wrap"><div class="empty">没有需要刷的题目 🎉</div><div class="btn-row"><a class="btn block" href="${backHref}">返回</a></div></div>`; return; }
  if (!quiz || quiz.key !== `${kind}/${key}/${mode}`) {
    quiz = { key: `${kind}/${key}/${mode}`, queue: shuffle(questions), i: 0, stats: [0, 0, 0], title, backHref, questions };
  }
  drawQuiz(app);
}

function drawQuiz(app) {
  const q = quiz.queue[quiz.i];
  const total = quiz.queue.length;
  if (quiz.i >= total) { drawQuizDone(app); return; }
  const revealed = quiz.revealed || (quiz.revealed = {});
  const show = !!revealed[q.id];
  app.innerHTML = `
  <div class="wrap">
    <div class="quiz-top">
      <a class="back" href="${quiz.backHref}">←</a>
      <span class="pos" style="font-weight:600;color:var(--text)">${esc(quiz.title)}</span>
      <span class="spacer"></span>
      <span class="pos">${quiz.i + 1} / ${total}</span>
    </div>
    <div class="qbar"><i style="width:${quiz.i / total * 100}%"></i></div>
    <div class="quiz-card">
      ${q.ctx ? `<div class="ctx">${esc(q.ctx)}</div>` : ""}
      <div class="qq"><span class="qnum">${q.type === "案例" ? "【案例】" : "【简答】"}</span>${esc(q.q)}</div>
      <div class="ans-zone ${show ? "show" : ""}">
        <div class="ans-label">参考答案</div>
        <div class="ans">${esc(q.a)}</div>
      </div>
      ${show ? `
        <div class="mark-row">
          <button class="btn red" data-s="0">😩 不会</button>
          <button class="btn amber" data-s="1">🤔 模糊</button>
          <button class="btn green" data-s="2">😀 会了</button>
        </div>` : `
        <div class="btn-row"><button class="btn block" id="reveal">显示答案</button></div>`}
    </div>
    <div style="margin-top:12px;display:flex;gap:10px">
      <button class="btn gray sm" id="prev" ${quiz.i === 0 ? "disabled" : ""}>← 上一题</button>
      <button class="btn gray sm" id="skip">跳过 →</button>
      <button class="btn gray sm" id="quit">结束本次</button>
    </div>
  </div>`;
  if (show) {
    app.querySelectorAll(".mark-row .btn").forEach(b => b.onclick = () => {
      const s = +b.dataset.s;
      saveStatus(q.id, s);
      quiz.stats[s]++;
      quiz.i++;
      quiz.revealed = {};
      drawQuiz(app);
    });
  } else {
    document.getElementById("reveal").onclick = () => { quiz.revealed[q.id] = true; drawQuiz(app); };
  }
  document.getElementById("prev").onclick = () => { if (quiz.i > 0) { quiz.i--; quiz.revealed = {}; drawQuiz(app); } };
  document.getElementById("skip").onclick = () => { quiz.i++; quiz.revealed = {}; drawQuiz(app); };
  document.getElementById("quit").onclick = () => { drawQuizDone(app); };
}

function drawQuizDone(app) {
  const [w, m, k] = quiz.stats;
  const answered = w + m + k;
  app.innerHTML = `
  <div class="wrap" style="padding-top:40px">
    <div class="quiz-done">
      <div class="big">🎯</div>
      <h2>本次练习结束</h2>
      <div style="color:var(--muted);font-size:13px">${esc(quiz.title)}</div>
      <div class="done-stats">
        <div class="s2"><b>${k}</b><span>会了</span></div>
        <div class="s1"><b>${m}</b><span>模糊</span></div>
        <div class="s0"><b>${w}</b><span>不会</span></div>
      </div>
      <div style="color:var(--muted);font-size:12px;margin-bottom:6px">已作答 ${answered} / ${quiz.queue.length} 题</div>
      <div class="btn-row">
        <button class="btn ghost" id="wrong-again">🔁 重刷不会的题</button>
      </div>
      <div class="btn-row">
        <button class="btn" id="restart">再来一轮（乱序）</button>
        <a class="btn gray" href="${quiz.backHref}">返回</a>
      </div>
    </div>
  </div>`;
  document.getElementById("restart").onclick = () => {
    quiz.queue = shuffle(quiz.questions); quiz.i = 0; quiz.stats = [0, 0, 0]; quiz.revealed = {}; drawQuiz(app);
  };
  document.getElementById("wrong-again").onclick = () => {
    const wrongs = quiz.questions.filter(q => getStatus(q.id) === 0);
    if (!wrongs.length) { alert("太棒了，没有标记为“不会”的题！"); return; }
    quiz.queue = shuffle(wrongs); quiz.i = 0; quiz.stats = [0, 0, 0]; quiz.revealed = {}; drawQuiz(app);
  };
}

/* ---------- 背诵考点 ---------- */
async function pageNotes(app, no) {
  const d = await loadChapter(no);
  if (!d.notes || !d.notes.length) { app.innerHTML = `<div class="empty">本章暂无背诵考点</div>`; return; }
  app.innerHTML = `
  <div class="header"><h1>第${cn(no)}章 ${esc(d.title)} · 背诵考点</h1><div class="sub">共 ${d.notes.length} 个考点 · 点击展开</div>
    <div class="btn-row"><button class="btn ghost" id="expand-all" style="flex:1">全部展开</button><button class="btn ghost" id="collapse-all" style="flex:1">全部收起</button></div>
  </div>
  <div class="wrap">
    ${d.notes.map((n, i) => `
      <div class="note-item" data-i="${i}">
        <div class="note-title">${esc(n.t)}<span class="arrow">▶</span></div>
        <div class="note-content">${esc(n.c)}</div>
      </div>`).join("")}
  </div>`;
  app.querySelectorAll(".note-title").forEach(t => t.onclick = () => t.closest(".note-item").classList.toggle("open"));
  document.getElementById("expand-all").onclick = () => app.querySelectorAll(".note-item").forEach(n => n.classList.add("open"));
  document.getElementById("collapse-all").onclick = () => app.querySelectorAll(".note-item").forEach(n => n.classList.remove("open"));
}

/* ---------- 综合卷 ---------- */
async function pageExams(app) {
  const idx = await loadJSON(INDEX_URL);
  app.innerHTML = `
  <div class="header"><h1>综合模拟卷</h1><div class="sub">全真模拟 + 专题集训 · 共 ${idx.exams.reduce((s, e) => s + e.n, 0)} 题</div></div>
  <div class="wrap"><div class="ch-list">
    ${idx.exams.map(e => `
      <div style="display:flex;gap:10px">
        <a class="ch-card" href="#/quiz/exam/${e.id}" style="flex:1">
          <div class="ch-no" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)">卷</div>
          <div class="ch-info"><div class="t">${esc(e.title)}</div><div class="m">${e.n} 题</div></div>
        </a>
        <a class="ch-card" href="#/quiz/exam/${e.id}/wrong" style="flex:0 0 auto;align-self:stretch;padding:14px 14px">
          <div class="ch-info" style="display:flex;align-items:center;color:var(--warn);font-weight:600;font-size:13px">只刷错题</div>
        </a>
      </div>`).join("")}
  </div></div>`;
}

/* ---------- 错题本 ---------- */
async function pageWrong(app) {
  const idx = await loadJSON(INDEX_URL);
  const p = loadProgress();
  const wrongIds = Object.keys(p).filter(id => p[id].s === 0);
  if (!wrongIds.length) {
    app.innerHTML = `<div class="header"><h1>错题本</h1></div><div class="wrap"><div class="empty">暂无错题，继续保持！🎉<br><br><button class="btn sm gray" onclick="if(confirm('确定清空全部作答记录吗？'))clearProgress()">清空全部记录</button></div></div>`;
    return;
  }
  // 按章节分组
  const groups = [];
  await Promise.all(idx.chapters.map(async ch => {
    const d = await loadChapter(ch.no);
    const qs = d.questions.filter(q => wrongIds.includes(q.id));
    if (qs.length) groups.push({ no: ch.no, title: `第${cn(ch.no)}章 ${ch.title}`, qs });
  }));
  const wrongExams = [];
  await Promise.all(idx.exams.map(async e => {
    const d = await loadExam(e.id);
    const qs = d.questions.filter(q => wrongIds.includes(q.id));
    if (qs.length) wrongExams.push({ e, n: qs.length });
  }));
  app.innerHTML = `
  <div class="header"><h1>错题本</h1><div class="sub">共 ${wrongIds.length} 道标记为“不会”的题</div></div>
  <div class="wrap">
    ${wrongExams.map(x => `<div class="section-title">${esc(x.e.title)}（${x.n} 题）<a class="more" href="#/quiz/exam/${x.e.id}/wrong">去重刷 →</a></div>`).join("")}
    ${groups.map(g => `
      <div class="section-title">${esc(g.title)}（${g.qs.length} 题）<a class="more" href="#/quiz/ch/${g.no}/wrong">去重刷 →</a></div>
      ${g.qs.map(q => qItem(q, 0)).join("")}`).join("")}
    <div class="footer-note"><button class="btn sm gray" onclick="if(confirm('确定清空全部作答记录吗？'))clearProgress()">清空全部作答记录</button></div>
  </div>`;
  bindToggles();
  // 缓存题目供展开
  browseCache = [];
  groups.forEach(g => browseCache.push(...g.qs));
}

render();
