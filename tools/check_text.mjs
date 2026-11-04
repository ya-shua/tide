// 读页面可见文字，确认没有"她/他"，并列出主要文案
const port = process.argv[2] || "9335";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = tabs.find((t) => t.type === "page");
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
  await send("Page.navigate", { url: "http://127.0.0.1:7880/?v=" + Date.now() });
  await sleep(2200);

  const out = await send("Runtime.evaluate", {
    expression: `JSON.stringify({
      title: document.title,
      pronouns: (document.body.innerText.match(/[她他]/g) || []).length,
      text: document.body.innerText.replace(/\\n{2,}/g, '\\n').slice(0, 1200)
    })`, returnByValue: true });
  ws.close();
  const v = out.result.result.value;
  console.log(v);
}
main().catch((e) => { console.error("ERR", e.message); process.exit(1); });