const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app.js'), 'utf8').replace(/render\(\);\s*$/, '');
const index = JSON.parse(fs.readFileSync(path.join(root, 'data/index.json'), 'utf8'));

function harness(fetchOverride) {
  const storage = new Map(), elements = new Map(), events = {}, requests = [];
  const element = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', setAttribute() {},
      querySelectorAll: () => [], style: {}, click() {}, remove() {} });
    return elements.get(id);
  };
  const app = element('app');
  const ctx = vm.createContext({ console, Blob, URL, setTimeout, clearTimeout,
    window: { addEventListener: (name, fn) => events[name] = fn, scrollTo() {} },
    document: { getElementById: element, querySelectorAll: () => [], createElement: () => element('created'), body: { appendChild() {} } },
    location: { hash: '#/' },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    fetch: url => {
      requests.push(url);
      if (fetchOverride) return fetchOverride(url);
      return Promise.resolve({ ok: true, json: () => JSON.parse(fs.readFileSync(path.join(root, url), 'utf8')) });
    }, alert() {} });
  vm.runInContext(source, ctx);
  return { ctx, run: code => vm.runInContext(code, ctx), app, storage, elements, events, requests };
}

test('failed requests are evicted and retried', async () => {
  let calls = 0;
  const h = harness(() => ++calls === 1 ? Promise.reject(Error('offline')) : Promise.resolve({ ok: true, json: () => ({ ok: 1 }) }));
  await assert.rejects(h.run("loadJSON('data/test.json')"));
  assert.equal((await h.run("loadJSON('data/test.json')")).ok, 1);
  assert.equal(calls, 2);
});

test('failed progress writes do not change status; corrupted records are retained', () => {
  const h = harness();
  h.ctx.localStorage.setItem = () => { throw Error('quota'); };
  assert.equal(h.run("saveStatus('q1', 2)"), false);
  assert.equal(h.run("getStatus('q1')"), -1);
  h.storage.set('cctp2026_progress_v1', '{bad');
  assert.equal(h.run("saveStatus('q1', 2)"), false);
  assert.equal(h.storage.get('cctp2026_progress_v1'), '{bad');
});

test('aliases migrate by latest timestamp and share future scores', async () => {
  const h = harness();
  const [oldId, canonical] = Object.entries(index.aliases)[0];
  h.storage.set('cctp2026_progress_v1', JSON.stringify({ [oldId]: { s: 0, t: 20 }, [canonical]: { s: 1, t: 10 } }));
  await h.run('loadJSON(INDEX_URL)');
  assert.equal(h.ctx.getStatus(canonical), 0);
  assert.equal(h.ctx.saveStatus(oldId, 2), true);
  assert.equal(h.ctx.getStatus(canonical), 2);
  assert.equal(Object.hasOwn(JSON.parse(h.storage.get('cctp2026_progress_v1')), oldId), false);
});

test('save merges newer persisted records from other tabs', () => {
  const h = harness(); h.run('loadProgress()');
  h.storage.set('cctp2026_progress_v1', JSON.stringify({ q2: { s: 1, t: 10 } }));
  h.run("saveStatus('q1', 2)");
  assert.equal(JSON.parse(h.storage.get('cctp2026_progress_v1')).q2.s, 1);
});

test('progress backup validates IDs/schema and merges newer records', async () => {
  const h = harness(); await h.run('loadJSON(INDEX_URL)');
  const id = index.chapters[0].questionIds[0];
  h.ctx.file = { size: 100, text: async () => JSON.stringify({ schema: 1, progress: { [id]: { s: 1, t: 10 } } }) };
  await h.run('importProgress(file)');
  assert.equal(h.ctx.getStatus(id), 1);
  const saved = h.storage.get('cctp2026_progress_v1');
  h.ctx.file.text = async () => JSON.stringify({ schema: 1, progress: { missing: { s: 1, t: 10 } } });
  await h.run('importProgress(file)');
  assert.equal(h.storage.get('cctp2026_progress_v1'), saved);
  assert.throws(() => h.run('validProgress({x:{s:3,t:0}})'));
  assert.throws(() => h.run('validProgress([])'));
});

test('export creates a valid downloadable JSON backup', async () => {
  const h = harness(); let blob, clicked = false;
  h.storage.set('cctp2026_progress_v1', JSON.stringify({ q1: { s: 1, t: 10 } }));
  h.ctx.URL = { createObjectURL: value => { blob = value; return 'blob:test'; }, revokeObjectURL() {} };
  h.ctx.document.createElement = () => ({ click: () => clicked = true, remove() {} });
  h.run('exportProgress()');
  const backup = JSON.parse(await blob.text());
  assert.equal(backup.schema, 1); assert.equal(backup.progress.q1.s, 1); assert.equal(clicked, true);
});

test('home requests only the index', async () => {
  const h = harness(); await h.run('render()');
  assert.deepEqual(h.requests, ['data/index.json']);
  assert.match(h.app.innerHTML, /今日待复习/);
});

test('slow old chapter cannot overwrite the newer exams route', async () => {
  let release;
  const h = harness(url => url === 'data/ch1.json' ? new Promise(resolve => release = () => resolve({ ok: true, json: () => JSON.parse(fs.readFileSync(path.join(root, url), 'utf8')) })) : Promise.resolve({ ok: true, json: () => index }));
  h.ctx.location.hash = '#/ch/1';
  const previous = h.run('render()'); await new Promise(resolve => setImmediate(resolve));
  h.ctx.location.hash = '#/exams'; await h.run('render()'); release(); await previous;
  assert.match(h.app.innerHTML, /历年真题 · 模拟卷/);
  assert.doesNotMatch(h.app.innerHTML, /id="kw"/);
});

test('due dates follow each rating and canonical questions are deduplicated', async () => {
  const h = harness(); await h.run('loadJSON(INDEX_URL)');
  h.storage.set('cctp2026_progress_v1', JSON.stringify({ q1: { s: 0, t: 100 }, q2: { s: 1, t: 100 }, q3: { s: 2, t: 100 } }));
  assert.equal(h.ctx.reviewDue('q1', 100 + 86400000), true);
  assert.equal(h.ctx.reviewDue('q2', 100 + 86400000), false);
  assert.equal(h.ctx.reviewDue('q2', 100 + 3 * 86400000), true);
  assert.equal(h.ctx.reviewDue('q3', 100 + 7 * 86400000), true);
  assert.equal((await h.run('allQuestions()')).length, index.uniqueQuestions);
});

test('sessions persist queue/position/scores and reject ended or malformed sessions', async () => {
  const h = harness(); await h.run('loadJSON(INDEX_URL)');
  h.run("quiz={key:'ch/1/undefined', queue:[{id:'q1'},{id:'q2'}],i:1,marks:{q1:1}};saveSession()");
  const snapshot = h.run("restoreSession('ch/1/undefined',[{id:'q1'},{id:'q2'}])");
  assert.equal(snapshot.i, 1); assert.equal(snapshot.queue[1].id, 'q2'); assert.equal(snapshot.marks.q1, 1);
  h.run('quiz.ended=true;saveSession()');
  assert.equal(h.run("restoreSession('ch/1/undefined',[{id:'q1'},{id:'q2'}])"), null);
  h.run('quiz.ended=false;quiz.i=100;saveSession()');
  assert.equal(h.run("restoreSession('ch/1/undefined',[{id:'q1'},{id:'q2'}])"), null);
});

test('returning to an ended practice creates a fresh round', async () => {
  const h = harness(); await h.run('loadJSON(INDEX_URL)');
  await h.run("pageQuiz(document.getElementById('app'),'exam','zt21')");
  h.run("quiz.i=quiz.queue.length;drawQuizDone(document.getElementById('app'))");
  await h.run("pageQuiz(document.getElementById('app'),'exam','zt21')");
  assert.match(h.app.innerHTML, /1 \/ 13/);
  assert.doesNotMatch(h.app.innerHTML, /本次练习结束/);
});

test('attribute escaping and answer-page rendering are safe', () => {
  const h = harness();
  assert.equal(h.ctx.esc('"<>&\''), '&quot;&lt;&gt;&amp;&#39;');
  assert.match(h.ctx.answerImages({ answerPages: ['pages/a/p1.jpg'] }), /alt="本题原始公式答案页"/);
});

test('storage events update visible statistics', async () => {
  const h = harness(); await h.run('render()');
  const id = index.chapters[0].questionIds[0];
  h.storage.set('cctp2026_progress_v1', JSON.stringify({ [id]: { s: 0, t: 10 } }));
  h.events.storage({ key: 'cctp2026_progress_v1' });
  await new Promise(resolve => setImmediate(resolve));
  assert.match(h.app.innerHTML, /<b>1<\/b><span>已作答/);
});
