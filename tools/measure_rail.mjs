// 量右栏三块是否等分、底边是否与左栏对齐
const port = process.argv[2] || "9335";
const base = process.argv[3] || "http://127.0.0.1:7880";
const target = base + (base.includes("?") ? "&" : "?") + "v=" + Date.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = tabs.find((t) => t.type === "page") || tabs[0];
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let seq = 0;
  const send = (method, params) => new Promise((res) => {
    const id = ++seq;
    const onMsg = (ev) => { const m = JSON.parse(ev.data);
      if (m.id === id) { ws.removeEventListener("message", onMsg); res(m); } };
    ws.addEventListener("message", onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });

  await send("Page.enable", {});
  await send("Page.navigate", { url: target });
  await sleep(1500);
  for (let i = 0; i < 20; i++) {
    const r = await send("Runtime.evaluate", {
      expression: "!!document.querySelector('.now')", returnByValue: true });
    if (r.result && r.result.result && r.result.result.value) break;
    await sleep(300);
  }

  const expr = `(() => {
    const r = (sel) => { const e = document.querySelector(sel);
      if (!e) return null; const b = e.getBoundingClientRect();
      return {y: Math.round(b.top), h: Math.round(b.height), b: Math.round(b.bottom),
              w: Math.round(b.width)}; };
    const cards = [...document.querySelectorAll('.col-side .m')].map(e => {
      const b = e.getBoundingClientRect();
      return {h: Math.round(b.height), bottom: Math.round(b.bottom)};
    });
    const clipped = [...document.querySelectorAll('body *')].filter(e => {
      const st = getComputedStyle(e);
      if (st.display === 'none' || st.overflow === 'visible') return false;
      return e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1;
    }).slice(0, 6).map(e => (e.className || e.tagName) + ':' + (e.textContent||'').slice(0,16));
    return JSON.stringify({
      main: r('.col-main'), side: r('.col-side'), needs: r('.needs'), now: r('.now'),
      cards, clipped, pageH: document.documentElement.scrollHeight,
      sideRows: getComputedStyle(document.querySelector('.col-side')).gridTemplateRows
    });
  })()`;

  const out = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
  ws.close();
  const v = out.result && out.result.result && out.result.result.value;
  console.log(v ? JSON.stringify(JSON.parse(v), null, 1) : JSON.stringify(out));
}
main().catch((e) => { console.error("ERR", e.message); process.exit(1); });