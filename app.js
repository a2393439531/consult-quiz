/* 咨询工程师《现代咨询方法与实务》刷题应用 */
"use strict";

const INDEX_URL = "data/index.json";
const LS_KEY = "cctp2026_progress_v1";
const SESSION_KEY = "cctp2026_session_v1";
let indexData = null;
let renderVersion = 0;

function notify(message) {
  let el = document.getElementById("notice");
  if (!el) {
    el = document.createElement("div"); el.id = "notice";
    el.setAttribute("role", "status"); document.body.appendChild(el);
  }
  el.textContent = message;
}
function canonicalId(id) { return indexData?.aliases?.[id] || id; }
function validProgress(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("进度格式错误");
  const clean = Object.create(null);
  for (const [id, item] of Object.entries(value)) {
    if (!/^[a-zA-Z0-9_-]+$/.test(id) || !item || !Number.isInteger(item.s) || item.s < 0 || item.s > 2 ||
        !Number.isFinite(item.t) || item.t < 0) throw new Error("进度记录无效");
    const key = canonicalId(id);
    if (!clean[key] || item.t >= clean[key].t) clean[key] = { s: item.s, t: item.t };
  }
  return clean;
}

/* ---------- 进度存储（内存缓存，避免每张卡片重复解析 localStorage） ---------- */
let _progressCache = null;
let _progressReadable = true;
function loadProgress() {
  if (_progressCache) return _progressCache;
  try { _progressCache = validProgress(JSON.parse(localStorage.getItem(LS_KEY) || "{}")); _progressReadable = true; }
  catch (e) { _progressReadable = false; _progressCache = Object.create(null); notify("无法读取学习记录，请检查浏览器存储或导入备份。原记录未被删除。"); }
  return _progressCache;
}
function saveStatus(qid, s) {
  _progressCache = null; // Merge the most recent persisted records from other tabs.
  const latest = loadProgress();
  if (!_progressReadable) return false;
  const p = { ...latest, [canonicalId(qid)]: { s, t: Date.now() } };
  try { localStorage.setItem(LS_KEY, JSON.stringify(p)); }
  catch (e) { notify("保存失败，本题尚未记录。请检查浏览器存储或导出已有进度。"); return false; }
  _progressCache = p;
  return true;
}
function getStatus(qid) {
  const v = loadProgress()[canonicalId(qid)];
  return v ? v.s : -1; // -1 未做, 0 不会, 1 模糊, 2 会
}
function clearProgress() {
  try { localStorage.removeItem(LS_KEY); localStorage.removeItem(SESSION_KEY); }
  catch (e) { notify("清空失败，请检查浏览器存储。"); return; }
  _progressCache = null; quiz = null; render();
}
// 其他标签页修改进度时同步刷新内存缓存
window.addEventListener("storage", event => {
  if (event.key === SESSION_KEY && !location.hash.startsWith("#/quiz/")) quiz = null;
  if (event.key === LS_KEY || event.key === null) { _progressCache = null; if (event.key === null) quiz = null; render(); }
});

function exportProgress() {
  try {
    const raw = localStorage.getItem(LS_KEY) || "{}";
    const data = { schema: 1, exportedAt: new Date().toISOString(), progress: JSON.parse(raw) };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "咨询实务学习进度.json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { notify("导出失败：" + e.message); }
}
async function importProgress(file) {
  try {
    if (!file || file.size > 5 * 1024 * 1024) throw new Error("请选择小于 5 MB 的 JSON 备份");
    const backup = JSON.parse(await file.text());
    if (backup.schema !== 1) throw new Error("不支持的备份版本");
    await loadJSON(INDEX_URL);
    const incoming = validProgress(backup.progress);
    const validIds = new Set([...indexData.chapters, ...indexData.exams].flatMap(m => m.questionIds));
    if (Object.keys(incoming).some(id => !validIds.has(id))) throw new Error("备份包含当前题库不存在的题目");
    _progressCache = null;
    const merged = validProgress(loadProgress());
    for (const [id, item] of Object.entries(incoming)) if (!merged[id] || item.t >= merged[id].t) merged[id] = item;
    localStorage.setItem(LS_KEY, JSON.stringify(merged)); _progressCache = merged; _progressReadable = true;
    notify("进度已导入；重复记录保留较新的评分。"); render();
  } catch (e) { notify("导入失败，已有记录保持不变：" + e.message); }
}

function saveSession() {
  if (!quiz) return;
  const snapshot = { schema: 1, version: indexData.version, key: quiz.key,
    queue: quiz.queue.map(q => q.id), i: quiz.i, marks: quiz.marks, ended: !!quiz.ended };
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(snapshot)); }
  catch (e) { notify("本轮位置保存失败；已成功保存的题目评分仍然保留。"); }
}
function restoreSession(key, questions) {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    if (!s || s.schema !== 1 || s.version !== indexData.version || s.key !== key || s.ended) return null;
    const byId = new Map(questions.map(q => [q.id, q]));
    if (!Array.isArray(s.queue) || !s.queue.length || new Set(s.queue).size !== s.queue.length ||
        s.queue.some(id => !byId.has(id)) || !Number.isInteger(s.i) || s.i < 0 || s.i >= s.queue.length ||
        !s.marks || typeof s.marks !== "object" || Array.isArray(s.marks) ||
        Object.entries(s.marks).some(([id, v]) => !s.queue.includes(id) || !Number.isInteger(v) || v < 0 || v > 2)) return null;
    return { queue: s.queue.map(id => byId.get(id)), i: s.i, marks: s.marks };
  } catch (e) { return null; }
}
function reviewDue(qid, now = Date.now()) {
  const item = loadProgress()[canonicalId(qid)];
  if (!item) return false;
  const delay = [1, 3, 7][item.s] * 86400000;
  return now >= item.t + delay;
}
function uniqueQuestions(questions) {
  const seen = new Set();
  return questions.filter(q => { const id = canonicalId(q.id); if (seen.has(id)) return false; seen.add(id); return true; });
}
function answerImages(q) {
  return q.answerPages?.length ? `<div class="page-imgs answer-pages"><div class="ans-label">原始答案页（点击图片放大）</div>${q.answerPages.map(url => `<a href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" loading="lazy" alt="本题原始公式答案页"></a>`).join("")}</div>` : "";
}

/* ---------- 数据缓存 ---------- */
const dataCache = {};
async function loadJSON(url) {
  if (!dataCache[url]) dataCache[url] = fetch(url).then(r => { if (!r.ok) throw new Error(url); return r.json(); })
    .then(data => {
      if (url === INDEX_URL) {
        indexData = data;
        _progressCache = null; // Re-read old IDs using the newly loaded alias map.
      }
      return data;
    }).catch(error => { delete dataCache[url]; throw error; });
  return dataCache[url];
}
async function loadChapter(no) { return loadJSON(`data/ch${no}.json`); }
async function loadExam(id) { return loadJSON(`data/${id}.json`); }

/* ---------- 工具 ---------- */
function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
const STATUS_NAME = ["不会", "模糊", "会"];

/* ---------- 路由 ---------- */
window.addEventListener("hashchange", render);

async function render() {
  const version = ++renderVersion;
  const hash = location.hash || "#/";
  const app = document.getElementById("app");
  const [_, route, a, b, c] = hash.split("/");
  document.querySelectorAll(".tabbar a").forEach(el => {
    const tab = el.getAttribute("data-tab");
    const on = (route === "" && tab === "home") ||
      (tab === route) || (route === "review" && tab === "wrong") ||
      (route === "ch" && tab === "chapters") ||
      (route === "notes" && tab === "chapters") ||
      (route === "quiz" && tab === (a === "exam" ? "exams" : "chapters"));
    el.classList.toggle("on", on);
  });
  try {
    await loadJSON(INDEX_URL);
    if (version !== renderVersion) return;
    if (!route) await pageHome(app);
    else if (route === "chapters") await pageChapters(app);
    else if (route === "ch") await pageChapter(app, +a);
    else if (route === "quiz") await pageQuiz(app, a, b, c);
    else if (route === "notes") await pageNotes(app, +a);
    else if (route === "exams") await pageExams(app);
    else if (route === "wrong") await pageWrong(app);
    else if (route === "review") await pageReview(app, a || "due");
    else app.innerHTML = '<div class="empty">页面不存在</div>';
  } catch (e) {
  if (version !== renderVersion) return;
    app.innerHTML = `<div class="empty">加载失败：${esc(e.message)}<br><button class="btn" id="retry">重新加载</button></div>`;
    document.getElementById("retry").onclick = render;
  }
  if (version !== renderVersion) return;
  window.scrollTo(0, 0);
}

/* ---------- 首页 ---------- */
async function pageHome(app) {
  const version = renderVersion;
  const idx = await loadJSON(INDEX_URL);
  if (version !== renderVersion) return;
  const p = loadProgress();
  const activeIds = new Set([...idx.chapters, ...idx.exams].flatMap(m => m.questionIds));
  const done = Object.keys(p).filter(id => activeIds.has(id)).length;
  const wrongCnt = Object.entries(p).filter(([id, v]) => activeIds.has(id) && v.s === 0).length;
  const totN = idx.uniqueQuestions;
  app.innerHTML = `
  <div class="header"><div class="header-in">
    <h1>咨询工程师 · 实务刷题</h1>
    <div class="sub">2026《现代咨询方法与实务》章节复习与题库 · 更新于 ${idx.generated}</div>
    <div class="stats-row">
      <div class="stat"><b>${totN}</b><span>题库总题数</span></div>
      <div class="stat"><b>${done}</b><span>已作答</span></div>
      <div class="stat"><b>${wrongCnt}</b><span>待攻克</span></div>
    </div>
    </div>
  </div>
  <div class="wrap">
    <div class="review-links"><a class="btn" href="#/review/due">今日待复习</a><a class="btn ghost" href="#/review/fuzzy">模糊题</a><a class="btn ghost" href="#/review/wrong">不会的题</a></div>
    <div class="backup-row"><button class="btn gray sm" id="export-progress">导出进度</button><label class="btn gray sm">导入进度<input type="file" id="import-progress" accept="application/json,.json"></label></div>
    <div class="section-title">章节刷题<a class="more" href="#/chapters">全部章节 →</a></div>
    <div class="ch-list">${idx.chapters.map(ch => chCard(ch)).join("")}</div>
    <div class="section-title">历年真题<a class="more" href="#/exams">全部 →</a></div>
    <div class="ch-list">${idx.exams.filter(e => e.kind === "zhenti").map(examCard).join("")}</div>
    <div class="section-title">综合模拟卷<a class="more" href="#/exams">全部 →</a></div>
    <div class="ch-list">${idx.exams.filter(e => e.kind !== "zhenti").map(examCard).join("")}</div>
    <div class="footer-note">数据来源于 2026 年备考资料 PDF（建工网校 / 环球网校 / 川杨学堂 / 优路 / 天一等），仅供个人学习使用</div>
  </div>`;
  updateChapterBars(idx);
  const exportBtn = document.getElementById("export-progress");
  if (exportBtn) { exportBtn.onclick = exportProgress; document.getElementById("import-progress").onchange = e => importProgress(e.target.files[0]); }
}

function examCard(e) {
  return `
  <a class="ch-card" href="#/quiz/exam/${e.id}">
    <div class="ch-no" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)">${e.kind === "zhenti" ? "真" : "卷"}</div>
    <div class="ch-info"><div class="t">${esc(e.title)}</div><div class="m">${e.n} 题</div></div>
  </a>`;
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
  const version = renderVersion;
  const idx = await loadJSON(INDEX_URL);
  if (version !== renderVersion) return;
  const p = loadProgress();
  app.innerHTML = `
  <div class="header"><div class="header-in"><h1>全部章节</h1><div class="sub">按章节复习 · 点击章节进入</div></div></div>
  <div class="wrap"><div class="ch-list">
    ${idx.chapters.map(ch => chCard(ch)).join("")}
  </div></div>`;
  updateChapterBars(idx);
}

function updateChapterBars(idx) {
  for (const ch of idx.chapters) {
    const done = ch.questionIds.filter(id => getStatus(id) >= 0).length;
    const ok = ch.questionIds.filter(id => getStatus(id) === 2).length;
    const pct = ch.questionIds.length ? Math.round(ok / ch.questionIds.length * 100) : 0;
    document.querySelectorAll(`a.ch-card[href="#/ch/${ch.no}"]`).forEach(card => {
      card.querySelector(".ch-bar i").style.width = pct + "%";
      card.querySelector(".ch-pct").textContent = done ? pct + "%" : "";
    });
  }
}

/* ---------- 章节详情（浏览 + 入口） ---------- */
let browseState = { no: null, src: "全部", kw: "", expanded: {} };

async function pageChapter(app, no) {
  const version = renderVersion;
  const d = await loadChapter(no);
  if (version !== renderVersion) return;
  const idx = await loadJSON(INDEX_URL);
  if (version !== renderVersion) return;
  browseCache = d.questions;
  const meta = idx.chapters.find(c => c.no === no);
  const srcs = ["全部", ...Object.keys(d.questions.reduce((m, q) => (m[q.src] = 1, m), {}))];
  if (browseState.no !== no) browseState = { no, src: "全部", kw: "", expanded: {} };
  const list = d.questions.filter(q =>
    (browseState.src === "全部" || q.src === browseState.src) &&
    (!browseState.kw || (q.q + q.ctx + q.a).includes(browseState.kw)));
  app.innerHTML = `
  <div class="header"><div class="header-in">
    <h1>第${cn(no)}章 ${esc(d.title)}</h1>
    <div class="sub">共 ${d.questions.length} 题 · ${meta && meta.notes ? meta.notes + " 个背诵考点" : ""}</div>
    <div class="btn-row" style="margin-top:14px">
      <a class="btn" href="#/quiz/ch/${no}" style="flex:1">▶ 开始刷题</a>
      <a class="btn ghost" href="#/quiz/ch/${no}/wrong" style="flex:1">🔁 只刷错题</a>
      ${d.notes && d.notes.length ? `<a class="btn ghost" href="#/notes/${no}" style="flex:1">📖 背诵考点</a>` : ""}
    </div>
    </div>
  </div>
  <div class="wrap">
    <div class="filters">${srcs.map(s => `<button class="chip ${s === browseState.src ? "on" : ""}" aria-pressed="${s === browseState.src}" data-src="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    <input aria-label="搜索题干或答案" class="search" id="kw" placeholder="搜索关键词（题干 / 答案）…" value="${esc(browseState.kw)}">
    <div id="qlist">${list.map((q, i) => qItem(q, i)).join("") || '<div class="empty">没有符合条件的题目</div>'}</div>
  </div>`;
  // 事件
  app.querySelectorAll(".chip").forEach(el => el.onclick = () => { browseState.src = el.dataset.src; render(); });
  const kw = document.getElementById("kw");
  kw.oninput = () => { browseState.kw = kw.value.trim(); refreshList(d); };
  bindToggles();
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
  const pagesOpen = !!browseState.expanded[q.id + ":p"];
  const st = getStatus(q.id);
  const stColor = st === 2 ? "var(--ok)" : st === 1 ? "var(--warn)" : st === 0 ? "var(--bad)" : "#c3cbd9";
  return `<div class="q-item" data-qid="${esc(q.id)}">
    <div class="q-head">
      <span class="q-badge ${q.type === "案例" ? "case" : "short"}">${esc(q.type)}</span>
      <div class="q-text">
        ${q.ctx ? `<div class="q-ctx">${esc(q.ctx)}</div>` : ""}
        ${esc(q.q)}
        <div class="q-src">${esc(q.src)} · <span style="color:${stColor}">${st >= 0 ? STATUS_NAME[st] : "未做"}</span></div>
      </div>
    </div>
    ${pagesOpen && q.pages ? `<div class="page-imgs">${q.pages.map(u => `<img src="${esc(u)}" loading="lazy" alt="原题页面">`).join("")}</div>` : ""}
    ${open ? `<div class="q-body"><div class="ans-label">参考答案</div><div class="ans">${esc(q.a)}</div>${answerImages(q)}</div>` : ""}
    <div class="q-actions">
      ${q.pages && q.pages.length ? `<button class="page-btn" data-pid="${esc(q.id)}">${pagesOpen ? "收起原题图表" : "📄 原题图表"}</button>` : ""}
      <button class="toggle-btn" data-tid="${esc(q.id)}">${open ? "收起答案" : "查看答案"}</button>
    </div>
  </div>`;
}
function bindToggles() {
  document.querySelectorAll(".toggle-btn").forEach(b => b.onclick = () => {
    const id = b.dataset.tid;
    browseState.expanded[id] = !browseState.expanded[id];
    const q = currentBrowseQuestion(id);
    const item = b.closest(".q-item");
    if (!q || !item) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = qItem(q);
    item.replaceWith(tmp.firstElementChild);
    bindToggles();
  });
  document.querySelectorAll(".page-btn").forEach(b => b.onclick = () => {
    const id = b.dataset.pid;
    browseState.expanded[id + ":p"] = !browseState.expanded[id + ":p"];
    const q = currentBrowseQuestion(id);
    const item = b.closest(".q-item");
    if (!q || !item) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = qItem(q);
    const fresh = tmp.firstElementChild;
    item.replaceWith(fresh);
    const imgs = fresh.querySelectorAll(".page-imgs img");
    if (imgs.length) fresh.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
  const version = renderVersion;
  let questions, title, backHref;
  if (kind === "review") {
    questions = await allQuestions();
    if (version !== renderVersion) return;
    title = REVIEW_TITLES[key] || REVIEW_TITLES.due;
    backHref = `#/review/${key}`;
  } else if (kind === "ch") {
    const no = +key;
    const d = await loadChapter(no);
    if (version !== renderVersion) return;
    questions = d.questions;
    title = `第${cn(no)}章 ${d.title}`;
    backHref = `#/ch/${no}`;
    if (!browseCache || browseCache !== questions) browseCache = questions;
  } else if (kind === "exam") {
    const e = await loadExam(key);
    if (version !== renderVersion) return;
    questions = e.questions;
    title = e.title;
    backHref = "#/exams";
  } else { throw new Error("练习入口无效"); }
  questions = uniqueQuestions(questions);
  const sessionKey = `${kind}/${key}/${mode}`;
  if (!quiz || quiz.key !== sessionKey || quiz.ended) {
    const restored = restoreSession(sessionKey, questions);
    const candidates = questions.filter(q => kind === "review" ? reviewMatch(q, key) : mode !== "wrong" || getStatus(q.id) === 0);
    if (!restored && !candidates.length) { app.innerHTML = `<div class="wrap"><div class="empty">没有需要刷的题目 🎉</div><div class="btn-row"><a class="btn block" href="${backHref}">返回</a></div></div>`; return; }
    quiz = { key: sessionKey, queue: shuffle(candidates), i: 0, marks: {}, title, backHref,
      questions, ...restored, ended: false };
    quiz.stats = [0, 0, 0]; Object.values(quiz.marks).forEach(v => quiz.stats[v]++);
    if (restored) {
      app.innerHTML = `<div class="wrap"><div class="quiz-done"><h2>继续上次练习</h2><p>${esc(title)} · 第 ${quiz.i + 1} / ${quiz.queue.length} 题</p><div class="btn-row"><button class="btn" id="continue-session">继续练习</button><button class="btn gray" id="new-session">重新开始</button></div></div></div>`;
      document.getElementById("continue-session").onclick = () => drawQuiz(app);
      document.getElementById("new-session").onclick = () => {
        if (!candidates.length) { notify("目前没有待练习题目。"); return; }
        quiz.queue = shuffle(candidates); quiz.i = 0; quiz.marks = {}; quiz.stats = [0, 0, 0]; quiz.revealed = {}; drawQuiz(app);
      };
      return;
    }
  }
  drawQuiz(app);
}

function drawQuiz(app) {
  const q = quiz.queue[quiz.i];
  const total = quiz.queue.length;
  if (quiz.i >= total) { drawQuizDone(app); return; }
  quiz.ended = false;
  saveSession();
  const revealed = quiz.revealed || (quiz.revealed = {});
  const show = !!revealed[q.id];
  const pagesOpen = !!revealed[q.id + ":p"];
  app.innerHTML = `
  <div class="wrap">
    <div class="quiz-top">
      <a class="back" href="${quiz.backHref}">←</a>
      <span class="pos" style="font-weight:600;color:var(--text)">${esc(quiz.title)}</span>
      <span class="spacer"></span>
      <span class="pos">${quiz.i + 1} / ${total}</span>
    </div>
    <div class="qbar"><i style="width:${quiz.i / total * 100}%"></i></div>
    <div class="quiz-card ${q.ctx ? "split" : ""}">
      ${q.ctx ? `<div class="ctx">${esc(q.ctx)}</div>` : ""}
      <div class="qmain">
      <div class="qq"><span class="qnum">${q.type === "案例" ? "【案例】" : "【简答】"}</span>${esc(q.q)}</div>
      ${q.pages && q.pages.length ? `
        ${pagesOpen ? `<div class="page-imgs">${q.pages.map(u => `<img src="${esc(u)}" loading="lazy" alt="原题页面">`).join("")}</div>` : ""}
        <button class="btn ghost sm page-quiz-btn" id="pagebtn" style="margin-top:10px;width:100%">${pagesOpen ? "收起原题图表" : "📄 查看原题图表（表格/图形）"}</button>` : ""}
      <div class="ans-zone ${show ? "show" : ""}">
        <div class="ans-label">参考答案</div>
        <div class="ans">${esc(q.a)}</div>${answerImages(q)}
      </div>
      ${show ? `
        <div class="mark-row">
          <button class="btn red" data-s="0">😩 不会</button>
          <button class="btn amber" data-s="1">🤔 模糊</button>
          <button class="btn green" data-s="2">😀 会了</button>
        </div>` : `
        <div class="btn-row"><button class="btn block" id="reveal">显示答案</button></div>`}
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:10px">
      <button class="btn gray sm" id="prev" ${quiz.i === 0 ? "disabled" : ""}>← 上一题</button>
      <button class="btn gray sm" id="skip">跳过 →</button>
      <button class="btn gray sm" id="quit">结束本次</button>
    </div>
  </div>`;
  const pageBtn = document.getElementById("pagebtn");
  if (pageBtn) pageBtn.onclick = () => { revealed[q.id + ":p"] = !pagesOpen; drawQuiz(app); };
  if (show) {
    app.querySelectorAll(".mark-row .btn").forEach(b => b.onclick = () => {
      const s = +b.dataset.s;
      if (!saveStatus(q.id, s)) return;
      quiz.marks[q.id] = s; // 按题去重，返回重做不重复计数
      quiz.stats = [0, 0, 0];
      Object.values(quiz.marks).forEach(v => quiz.stats[v]++);
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
  quiz.ended = true; saveSession();
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
    const [kind, key, mode] = quiz.key.split("/");
    const pool = quiz.questions.filter(q => kind === "review" ? reviewMatch(q, key) : mode !== "wrong" || getStatus(q.id) === 0);
    if (!pool.length) { notify("当前没有待练习题目。"); return; }
    quiz.queue = shuffle(pool); quiz.i = 0; quiz.stats = [0, 0, 0]; quiz.marks = {}; quiz.revealed = {}; drawQuiz(app);
  };
  document.getElementById("wrong-again").onclick = () => {
    const wrongs = quiz.questions.filter(q => getStatus(q.id) === 0);
    if (!wrongs.length) { alert("太棒了，没有标记为“不会”的题！"); return; }
    quiz.queue = shuffle(wrongs); quiz.i = 0; quiz.stats = [0, 0, 0]; quiz.marks = {}; quiz.revealed = {}; drawQuiz(app);
  };
}

/* ---------- 背诵考点 ---------- */
async function pageNotes(app, no) {
  const version = renderVersion;
  const d = await loadChapter(no);
  if (version !== renderVersion) return;
  if (!d.notes || !d.notes.length) { app.innerHTML = `<div class="empty">本章暂无背诵考点</div>`; return; }
  app.innerHTML = `
  <div class="header"><div class="header-in"><h1>第${cn(no)}章 ${esc(d.title)} · 背诵考点</h1><div class="sub">共 ${d.notes.length} 个考点 · 点击展开</div></div>
    <div class="btn-row"><button class="btn ghost" id="expand-all" style="flex:1">全部展开</button><button class="btn ghost" id="collapse-all" style="flex:1">全部收起</button></div>
  </div>
  <div class="wrap">
    <div class="notes-list">
    ${d.notes.map((n, i) => `
      <div class="note-item" data-i="${i}">
        <button class="note-title" aria-expanded="false">${esc(n.t)}<span class="arrow" aria-hidden="true">▶</span></button>
        <div class="note-content">${esc(n.c)}</div>
      </div>`).join("")}
    </div>
  </div>`;
  app.querySelectorAll(".note-title").forEach(t => t.onclick = () => { const open = t.closest(".note-item").classList.toggle("open"); t.setAttribute("aria-expanded", String(open)); });
  document.getElementById("expand-all").onclick = () => app.querySelectorAll(".note-item").forEach(n => { n.classList.add("open"); n.querySelector(".note-title").setAttribute("aria-expanded", "true"); });
  document.getElementById("collapse-all").onclick = () => app.querySelectorAll(".note-item").forEach(n => { n.classList.remove("open"); n.querySelector(".note-title").setAttribute("aria-expanded", "false"); });
}

/* ---------- 综合卷 ---------- */
async function pageExams(app) {
  const version = renderVersion;
  const idx = await loadJSON(INDEX_URL);
  if (version !== renderVersion) return;
  const zt = idx.exams.filter(e => e.kind === "zhenti");
  const mn = idx.exams.filter(e => e.kind !== "zhenti");
  const card = e => `
      <div style="display:flex;gap:10px">
        <a class="ch-card" href="#/quiz/exam/${e.id}" style="flex:1">
          <div class="ch-no" style="background:linear-gradient(135deg,#0ea5e9,#6366f1)">${e.kind === "zhenti" ? "真" : "卷"}</div>
          <div class="ch-info"><div class="t">${esc(e.title)}</div><div class="m">${e.n} 题</div></div>
        </a>
        <a class="ch-card" href="#/quiz/exam/${e.id}/wrong" style="flex:0 0 auto;align-self:stretch;padding:14px 14px">
          <div class="ch-info" style="display:flex;align-items:center;color:var(--warn);font-weight:600;font-size:13px">只刷错题</div>
        </a>
      </div>`;
  app.innerHTML = `
  <div class="header"><div class="header-in"><h1>历年真题 · 模拟卷</h1><div class="sub">真题 ${zt.reduce((s, e) => s + e.n, 0)} 题 · 模拟 ${mn.reduce((s, e) => s + e.n, 0)} 题</div></div></div>
  <div class="wrap">
    <div class="section-title">📜 历年真题</div>
    <div class="ch-list">${zt.map(card).join("") || '<div class="empty">暂无</div>'}</div>
    <div class="section-title">📝 模拟冲刺卷</div>
    <div class="ch-list">${mn.map(card).join("")}</div>
  </div>`;
}

/* ---------- 错题本 ---------- */
async function pageWrong(app) {
  const version = renderVersion;
  const idx = await loadJSON(INDEX_URL);
  if (version !== renderVersion) return;
  const p = loadProgress();
  const currentIds = new Set([...idx.chapters, ...idx.exams].flatMap(meta => meta.questionIds));
  const wrongIds = new Set(Object.keys(p).filter(id => currentIds.has(id) && p[id].s === 0));
  if (!wrongIds.size) {
    app.innerHTML = `<div class="header"><div class="header-in"><h1>错题本</h1></div></div><div class="wrap"><div class="empty">暂无错题，继续保持！🎉<br><br><button class="btn sm gray" onclick="if(confirm('确定清空全部作答记录吗？'))clearProgress()">清空全部记录</button></div></div>`;
    return;
  }
  // 按章节分组
  const groups = [];
  await Promise.all(idx.chapters.map(async ch => {
    const d = await loadChapter(ch.no);
    if (version !== renderVersion) return;
    const qs = d.questions.filter(q => wrongIds.has(canonicalId(q.id)));
    if (qs.length) groups.push({ no: ch.no, title: `第${cn(ch.no)}章 ${ch.title}`, qs });
  }));
  const wrongExams = [];
  await Promise.all(idx.exams.map(async e => {
    const d = await loadExam(e.id);
    if (version !== renderVersion) return;
    const qs = d.questions.filter(q => wrongIds.has(canonicalId(q.id)));
    if (qs.length) wrongExams.push({ e, n: qs.length, qs });
  }));
  if (version !== renderVersion) return;
  groups.sort((a, b) => a.no - b.no);
  wrongExams.sort((a, b) => idx.exams.findIndex(e => e.id === a.e.id) - idx.exams.findIndex(e => e.id === b.e.id));
  app.innerHTML = `
  <div class="header"><div class="header-in"><h1>错题本</h1><div class="sub">共 ${wrongIds.size} 道标记为“不会”的题</div></div></div>
  <div class="wrap">
    ${wrongExams.map(x => `
      <div class="section-title">${esc(x.e.title)}（${x.n} 题）<a class="more" href="#/quiz/exam/${x.e.id}/wrong">去重刷 →</a></div>
      ${x.qs.map(q => qItem(q, 0)).join("")}`).join("")}
    ${groups.map(g => `
      <div class="section-title">${esc(g.title)}（${g.qs.length} 题）<a class="more" href="#/quiz/ch/${g.no}/wrong">去重刷 →</a></div>
      ${g.qs.map(q => qItem(q, 0)).join("")}`).join("")}
    <div class="footer-note"><button class="btn sm gray" onclick="if(confirm('确定清空全部作答记录吗？'))clearProgress()">清空全部作答记录</button></div>
  </div>`;
  browseCache = [];
  wrongExams.forEach(x => browseCache.push(...x.qs));
  groups.forEach(g => browseCache.push(...g.qs));
  bindToggles();
}

const REVIEW_TITLES = { due: "今日待复习", fuzzy: "模糊题", wrong: "不会的题" };
function reviewMatch(q, mode) {
  return mode === "fuzzy" ? getStatus(q.id) === 1 : mode === "wrong" ? getStatus(q.id) === 0 : reviewDue(q.id);
}
async function allQuestions() {
  const idx = await loadJSON(INDEX_URL);
  const data = await Promise.all([
    ...idx.chapters.map(ch => loadChapter(ch.no)), ...idx.exams.map(exam => loadExam(exam.id))
  ]);
  return uniqueQuestions(data.flatMap(d => d.questions));
}
async function pageReview(app, mode) {
  const version = renderVersion;
  const questions = await allQuestions();
  if (version !== renderVersion) return;
  const list = questions.filter(q => reviewMatch(q, mode));
  browseCache = list;
  app.innerHTML = `<div class="header"><div class="header-in"><h1>${esc(REVIEW_TITLES[mode] || REVIEW_TITLES.due)}</h1><div class="sub">${list.length} 道独立题目 · 不会 / 模糊 / 会了分别在 1 / 3 / 7 天后复习</div></div></div>
    <div class="wrap"><div class="review-links">${Object.entries(REVIEW_TITLES).map(([key, title]) => `<a class="btn ${key === mode ? "" : "ghost"}" href="#/review/${key}">${title}</a>`).join("")}</div>
    ${list.length ? `<a class="btn block" href="#/quiz/review/${mode}">开始复习</a>` : '<div class="empty">暂时没有待复习题目</div>'}
    ${list.map(q => qItem(q)).join("")}</div>`;
  bindToggles();
}

render();
