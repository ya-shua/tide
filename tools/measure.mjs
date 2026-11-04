// 用 CDP 量面板版式：溢出、字号层级、各块尺寸
const port = process.argv[2] || "9333";
const base = process.argv[3] || "http://127.0.0.1:7880";
const target = base + (base.includes("?") ? "&" : "?") + "v=" + Date.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function list() {
  const r = await fetch(`http://127.0.0.1:${port}/json/list`);
  return r.json();
}

async function openTab() {
  for (const method of ["PUT", "POST", "GET"]) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,
        { method });
      if (r.ok) return r.json();
    } catch (e) {}
  }
  return null;
}

async function main() {
  let tabs = await list();
  let page = tabs.find((t) => t.type === "page" && t.url.includes("7880"));
  if (!page) {
    const created = await openTab();
    if (!created) throw new Error("开不了新标签");
    page = created;
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let seq = 0;
  const send = (method, params) => new Promise((res) => {
    const id = ++seq;
    const onMsg = (ev) => { const m = JSON.parse(ev.data); if (m.id === id) { ws.removeEventListener("message", onMsg); res(m); } };
    ws.addEventListener("message", onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable", {});
  await send("Page.navigate", { url: target });
  await sleep(1500);

  // 等页面把状态拿回来（.now 出现）
  let ready = false;
  for (let i = 0; i < 20 && !ready; i++) {
    const r = await send("Runtime.evaluate", {
      expression: "!!document.querySelector('.now')", returnByValue: true });
    ready = !!(r.result && r.result.result && r.result.result.value);
    if (!ready) await sleep(300);
  }
  if (!ready) throw new Error("页面没渲染出来");

  const expression = `(() => {
    const q = s => document.querySelector(s);
    const box = e => { const r = e.getBoundingClientRect();
      return {y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}; };
    const fs = s => { const e=q(s); return e?getComputedStyle(e).fontSize:null; };
    const clipped = [...document.querySelectorAll('body *')].filter(e => {
      const st = getComputedStyle(e);
      if (st.display === 'none' || st.overflow === 'visible') return false;
      return e.scrollWidth > e.clientWidth + 1;
    }).slice(0, 8).map(e => (e.className||e.tagName) + ':' + (e.textContent||'').slice(0,18));
    return JSON.stringify({
      vw: innerWidth, sw: document.documentElement.scrollWidth,
      sh: document.documentElement.scrollHeight,
      hero: box(q('.now')), heroDoing: fs('.now .doing'),
      metricBig: fs('.m .big'),
      needs: box(q('.needs')), needsRows: document.querySelectorAll('.nd').length,
      tl: box(q('.tl')), hotBars: document.querySelectorAll('.nd.hot').length,
      actOn: q('#act-card').classList.contains('on'),
      clipped,
      orderY: ['.now','.col-side','.needs','.tl'].map(s2 => Math.round(q(s2).getBoundingClientRect().top)),
      palette: ['--bg','--accent','--fg','--dim'].map(k => k + '=' + getComputedStyle(document.documentElement).getPropertyValue(k).trim()),
      text: {doing: q('#doing').textContent, idle: q('#idle').textContent,
             act: q('#act-big').textContent, hint: q('#need-hint').textContent}
    });
  })()`;

  const out = await send("Runtime.evaluate", { expression, returnByValue: true });
  ws.close();
  const v = out.result && out.result.result && out.result.result.value;
  console.log(v ? JSON.stringify(JSON.parse(v), null, 1) : JSON.stringify(out));
}
main().catch((e) => { console.error("ERR", e.message); process.exit(1); });