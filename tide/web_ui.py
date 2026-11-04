r"""Tide · 面板页面（HTML/CSS/JS 全在这）。

设计约束（来自本人的要求）：
- 只用深色底 + 一条沉稳的强调色，不发光、不渐变、不堆阴影
- 强调色只出现在两个地方：此刻那条细线、最要紧的那一条需求
- 重要的先看见：此刻 → 关系/情绪/主动 → 五条需求 → 记忆与时间
"""
HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tide</title>
<style>
  :root{
    --bg:#121115;
    --card:#1a181d;
    --card2:#211e25;
    --line:#2b262e;
    --line-soft:#232028;
    --fg:#ece8ee;
    --dim:#a49daa;
    --faint:#746d79;
    --accent:#cf9db0;       /* 只用在一两处：当前最要紧的地方 */
    --steel:#9db2c6;        /* 数字、次要强调 */
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--fg);
    font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    padding:26px 22px 44px;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1000px;margin:0 auto}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px}

  /* ── 顶栏 ── */
  .top{display:flex;align-items:baseline;gap:10px;margin-bottom:18px}
  .top h1{font-size:16px;font-weight:600;letter-spacing:.02em}
  .top .sub{color:var(--faint);font-size:12px}
  .top .grow{flex:1}
  .top .clock{color:var(--faint);font:12px/1 ui-monospace,Consolas,monospace}
  .chip{background:none;border:1px solid var(--line);color:var(--dim);
    border-radius:7px;padding:3px 9px;font:inherit;font-size:12px;cursor:pointer}
  .chip:hover{color:var(--fg);border-color:#313943}
  .top .ver{color:var(--faint);font:11px/1 ui-monospace,Consolas,monospace;opacity:.75}
  .chip.upd{border-color:#5d3a46;color:#e3b6c4}
  .chip.upd:hover{border-color:#7a4b5a;color:#f0c9d5}
  .chip.upd:disabled{opacity:.6;cursor:default}

  /* ── ① 此刻 ── */
  .now{padding:22px 24px 20px;position:relative}
  .now::before{content:"";position:absolute;left:0;top:18px;bottom:18px;width:2px;
    background:var(--accent);opacity:.65;border-radius:99px}
  .now .lb{font-size:11px;letter-spacing:.14em;color:var(--faint);margin-bottom:9px;
    display:flex;align-items:baseline;gap:12px}
  .now .lb .idle{letter-spacing:0;color:var(--faint);opacity:.9}
  .now .doing{font-size:29px;line-height:1.38;font-weight:650;letter-spacing:.005em}
  .now .why{margin-top:7px;font-size:13.5px;color:var(--dim)}
  .now .say{margin-top:16px;padding-top:14px;border-top:1px solid var(--line-soft);
    display:flex;align-items:baseline;gap:10px}
  .now .say .sl{font-size:11.5px;color:var(--faint);flex:none;letter-spacing:.08em}
  .now .say .txt{font-size:18px;font-weight:600;line-height:1.5;color:#dde5ee}
  .now .say .txt::before{content:"「";color:var(--faint);font-weight:400}
  .now .say .txt::after{content:"」";color:var(--faint);font-weight:400}

  /* ── ② 关系 / 情绪 / 主动 ── */
  .grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;
    align-items:stretch;margin-bottom:14px}
  .col-main{display:flex;flex-direction:column;gap:14px;min-width:0}
  .col-side{display:grid;grid-template-rows:repeat(3,minmax(0,1fr));gap:12px;min-width:0}
  .m{padding:13px 16px 12px;display:flex;flex-direction:column}
  .m .mb{margin:auto 0}
  .m .lb{font-size:11px;letter-spacing:.14em;color:var(--faint);margin-bottom:7px}
  .m .big{font-size:23px;font-weight:650;line-height:1.25;font-variant-numeric:tabular-nums}
  .m .big .n{font-size:15px;font-weight:500;color:var(--dim);margin-left:7px}
  .m .sub{font-size:12.5px;color:var(--dim);margin-top:6px;line-height:1.7}
  .m .sub em{font-style:normal;color:#dce5ef}
  .m .warn{color:#d9a06b}
  .m .dim{color:var(--faint)}
  .m .advice{margin-top:8px;padding-top:8px;border-top:1px solid var(--line-soft);
    font-size:12.5px;color:#b9c9db;line-height:1.6}
  .m .advice::before{content:"→ ";color:var(--faint)}
  .act .big{color:var(--fg)}
  .m.hot .big{color:var(--accent)}
  .m.hot .n{color:#c6aebb}
  .act.on .big{color:var(--accent)}
  .meter{margin-top:10px;height:3px;border-radius:99px;background:#222932;overflow:hidden}
  .meter i{display:block;height:100%;background:var(--steel);border-radius:99px}
  .act.on .meter i{background:var(--accent)}

  /* ── ③ 五条需求 ── */
  .needs{padding:15px 18px 12px;display:flex;flex-direction:column;flex:1}
  .needs #needs{flex:1;display:flex;flex-direction:column;justify-content:space-between;
    padding:2px 0 1px}
  .needs .hd{display:flex;align-items:baseline;gap:10px;margin-bottom:9px}
  .needs h2{font-size:11px;letter-spacing:.14em;color:var(--faint);font-weight:500}
  .needs .hint{font-size:12px;color:var(--faint)}
  .nd{display:grid;grid-template-columns:38px 1fr 34px;gap:10px;align-items:center;
    padding:4px 0}
  .nd .k{font-size:12.5px;color:var(--dim)}
  .nd .t{height:4px;border-radius:99px;background:#20262e;overflow:hidden}
  .nd .t i{display:block;height:100%;border-radius:99px;background:var(--steel);opacity:.85}
  .nd.hot .t i{background:var(--accent);opacity:1}
  .nd.hot .k,.nd.hot .v{color:var(--fg)}
  .nd .v{font-size:12.5px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}

  /* ── ④ 记忆 / 这段时间 / 接下来 ── */
  .tl{padding:15px 18px 10px}
  .tl .hd{display:flex;align-items:baseline;gap:10px;margin-bottom:5px}
  .tl h2{font-size:11px;letter-spacing:.14em;color:var(--faint);font-weight:500}
  .tl .cnt{font-size:11.5px;color:var(--faint)}
  .tl ul{list-style:none}
  .tl li{display:grid;grid-template-columns:64px 1fr auto;gap:12px;align-items:baseline;
    padding:6px 0;border-bottom:1px solid var(--line-soft);font-size:12.5px;color:var(--dim)}
  .tl li:last-child{border-bottom:0}
  .tl li .t{font:11px/1.7 ui-monospace,Consolas,monospace;color:var(--faint)}
  .tl li .who{color:var(--fg);font-weight:500}
  .tl li .tag{font-size:10.5px;padding:0 7px;border-radius:99px;background:var(--card2);
    border:1px solid var(--line);color:var(--faint);white-space:nowrap}
  .tl li.future .t{color:var(--steel)}
  .vlink{color:var(--steel);text-decoration:none;border-bottom:1px solid #2c3a48}
  .vlink:hover{color:#cfe0f2}
  .axis{display:flex;align-items:center;gap:8px;margin:10px 0;font-size:11px;color:var(--faint)}
  .axis .ln{flex:1;height:1px;background:var(--line)}
  .axis .nowp{color:var(--fg);background:var(--card2);border:1px solid var(--line);
    border-radius:99px;padding:0 9px;font-size:11px}

  /* ── 设置抽屉 ── */
  .scrim{position:fixed;inset:0;background:rgba(6,8,11,.66);opacity:0;pointer-events:none;
    transition:opacity .2s;z-index:40}
  .scrim.on{opacity:1;pointer-events:auto}
  .drawer{position:fixed;top:0;right:0;bottom:0;width:372px;max-width:92vw;z-index:41;
    background:#13171c;border-left:1px solid var(--line);
    transform:translateX(102%);transition:transform .24s ease;display:flex;flex-direction:column}
  .drawer.on{transform:none}
  .drawer .dh{display:flex;align-items:center;gap:10px;padding:16px 18px;
    border-bottom:1px solid var(--line-soft)}
  .drawer .dh h3{font-size:14px;font-weight:600}
  .drawer .dh .grow{flex:1}
  .drawer .db{flex:1;overflow:auto;padding:4px 18px 18px}
  .drawer .df{padding:13px 18px;border-top:1px solid var(--line-soft);
    display:flex;align-items:center;gap:12px}
  .drawer .df .msg{font-size:12.5px;color:var(--faint);flex:1}
  .s-grp{padding-top:15px}
  .s-grp h4{font-size:11px;letter-spacing:.14em;color:var(--faint);font-weight:500;margin-bottom:7px}
  .s-row{display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid var(--line-soft)}
  .s-row:last-child{border-bottom:0}
  .s-row span{flex:1;font-size:12.5px;color:var(--dim);line-height:1.45}
  .s-row input{width:104px;flex:none;background:var(--card2);color:var(--fg);
    border:1px solid var(--line);border-radius:7px;padding:4px 8px;font:inherit;
    font-size:12.5px;text-align:right}
  .s-row input:focus{outline:none;border-color:#3a4553}
  .btn{background:var(--card2);color:var(--dim);border:1px solid var(--line);
    border-radius:7px;padding:6px 13px;font:inherit;font-size:12.5px;cursor:pointer}
  .btn:hover{color:var(--fg);border-color:#313943}
  .btn.primary{background:#233040;border-color:#38495c;color:#d6e3f2}
  .btn.primary:hover{background:#28374a}
  .btn.ghost{background:none;border-color:transparent;color:var(--faint);padding:3px 8px}

  details{background:none;border:0;margin-top:8px}
  details summary{cursor:pointer;color:var(--faint);font-size:12px;padding:4px 0}
  details summary:hover{color:var(--dim)}
  details .body{padding-top:8px}
  pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;
    font:12px/1.8 ui-monospace,Consolas,monospace;color:#aebbc9}
  .controls{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}
  .controls button{background:none;color:var(--dim);border:1px solid var(--line);
    border-radius:7px;padding:5px 11px;font:inherit;font-size:12px;cursor:pointer}
  .controls button:hover{color:var(--fg);border-color:#313943}
  .controls button.hot{color:#d3a0a0;border-color:#3a2c30}
  .controls button.soft{color:#a3c3ae;border-color:#2b3a31}

  @media(max-width:900px){
    body{padding:18px 13px 30px}
    .grid{grid-template-columns:1fr}
    .col-side{grid-template-rows:auto}
    .now .doing{font-size:23px}
  }
</style>
</head>
<body>
<div class="wrap">

  <div class="top">
    <h1>Tide</h1><span class="sub">此刻</span><span class="ver" id="ver"></span>
    <div class="grow"></div>
    <span class="clock" id="clock">—</span>
    <button class="chip upd" id="upd" style="display:none"></button>
    <button class="chip" id="refresh">刷新</button>
    <button class="chip" id="gear">设置</button>
  </div>

  <div class="grid">
  <div class="col-main">
  <section class="card now">
    <div class="lb"><span>此刻</span><span class="idle" id="idle"></span></div>
    <div class="doing" id="doing">—</div>
    <div class="why" id="why">—</div>
    <div class="say">
      <span class="sl">心里在想</span>
      <span class="txt" id="say">—</span>
    </div>
  </section>

  <section class="card needs">
    <div class="hd"><h2>缺什么</h2><span class="hint" id="need-hint"></span></div>
    <div id="needs"></div>
  </section>
  </div>

  <aside class="col-side">
    <section class="card m" id="rel-card">
      <div class="lb">关系</div>
      <div class="mb">
        <div class="big" id="rel-big">—</div>
        <div class="sub" id="rel-sub">—</div>
      </div>
      <div class="advice" id="rel-advice" style="display:none"></div>
    </section>

    <section class="card m" id="emo-card">
      <div class="lb">情绪</div>
      <div class="mb">
        <div class="big" id="emo-big">—</div>
        <div class="sub" id="emo-sub">—</div>
      </div>
    </section>

    <section class="card m act" id="act-card">
      <div class="lb">会不会来找你</div>
      <div class="mb">
        <div class="big" id="act-big">—</div>
        <div class="sub" id="act-sub">—</div>
      </div>
      <div class="meter"><i id="act-bar" style="width:0%"></i></div>
    </section>
  </aside>
  </div>

  <section class="card tl">
    <div class="hd"><h2>记得</h2><span class="cnt">越久越模糊</span></div>
    <ul id="mem"></ul>
    <div class="hd" style="margin-top:14px"><h2>这段时间</h2>
      <span class="cnt" id="cnt"></span></div>
    <ul id="past"></ul>
    <div class="axis"><span>过去</span><span class="ln"></span><span class="nowp">现在</span><span class="ln"></span><span>接下来</span></div>
    <ul id="future"></ul>
  </section>

  <div class="scrim" id="scrim"></div>
  <aside class="drawer" id="drawer">
    <div class="dh">
      <h3>设置</h3><span class="grow"></span>
      <button class="btn ghost" id="s-close">关闭</button>
    </div>
    <div class="db" id="s-body"></div>
    <div class="df">
      <span class="msg" id="s-msg"></span>
      <button class="btn primary" id="s-save">保存</button>
    </div>
  </aside>

  <details>
    <summary>给 LLM 的软约束 · 机器看的，不是你读的</summary>
    <div class="body"><pre id="prompt">—</pre></div>
  </details>

  <details>
    <summary>测试工具 · 正式版不会出现</summary>
    <div class="body">
      <p style="font-size:12px;color:var(--faint)">等价于"有人说了这句话"，只在本地改状态。真跑起来以后输入来自 QQ。</p>
      <div class="controls" id="controls"></div>
    </div>
  </details>

</div>

<script>
const LABEL={calm:'平静',joyful:'开心',excited:'兴奋',playful:'俏皮',affectionate:'黏人',shy:'害羞',
  sad:'难过',disappointed:'失望',angry:'生气',annoyed:'闷闷的',tired:'困',bored:'无聊',
  worried:'担心',nostalgic:'怀念'};
const TONE={warm:'暖',neutral:'平',cool:'冷'};
const TOPIC={active:'还在聊',winding_down:'在收尾',closed:'聊完了'};
const TAG={praise:'被夸',hostile:'被凶',dismissive:'被敷衍',apology:'道歉',feeding:'喂饭',
  care:'哄/关心',tease:'被逗',self_message:'自己说的'};
let data=null;

const el=id=>document.getElementById(id);
const fmt=v=>v==null?'—':String(Math.round(v));
const pct=v=>Math.round((v||0)*100)+'%';
const fmtT=m=>{if(!isFinite(m))return '刚才';if(m<1)return '刚刚';if(m<60)return Math.round(m)+' 分钟';return (m/60).toFixed(1).replace(/\.0$/,'')+' 小时';};
function tagName(t){
  if(TAG[t]) return TAG[t];
  if(t.indexOf('mood:')===0){ const k=t.slice(5); return '你'+(LABEL[k]||k); }
  return t;
}

async function load(){ const r=await fetch('/api/state'); data=await r.json(); render(); maybeProbe(); }
async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  data=await r.json(); render();
}
el('refresh').onclick=load;
el('upd').onclick=async()=>{
  const b=el('upd');
  const ok=confirm('现在更新到最新版本？面板会自己重启一次。');
  if(!ok) return;
  b.disabled=true; b.textContent='正在更新…';
  try{
    const r=await fetch('/api/update',{method:'POST'});
    const j=await r.json();
    if(!r.ok||(j&&j.error)){ b.textContent='更新失败'; b.disabled=false;
      alert((j&&j.error)||'更新失败'); return; }
    b.textContent='更新中，面板马上重启';
  }catch(e){
    b.disabled=false; b.textContent='更新失败';
  }
};

const ACTIONS=[
  {t:'夸一句',p:'/api/observe',b:{text:'你今天好可爱呀'}},
  {t:'凶一句',p:'/api/observe',b:{text:'你真笨'},cls:'hot'},
  {t:'敷衍一句',p:'/api/observe',b:{text:'嗯'},cls:'hot'},
  {t:'问「你在干嘛呀」',p:'/api/observe',b:{text:'你在干嘛呀？',speaker:'self'}},
  {t:'说「晚安」',p:'/api/observe',b:{text:'那我先睡啦，晚安',speaker:'self'}},
  {t:'喂饭',p:'/api/event',b:{name:'feed'},cls:'soft'},
  {t:'倒水',p:'/api/event',b:{name:'drink'},cls:'soft'},
  {t:'哄一句',p:'/api/observe',b:{text:'抱抱，别生气啦'},cls:'soft'},
  {t:'道歉',p:'/api/observe',b:{text:'对不起，是我不好'},cls:'soft'},
  {t:'不理 2 小时',p:'/api/advance',b:{hours:2}},
  {t:'不理 6 小时',p:'/api/advance',b:{hours:6}},
  {t:'通宵不理 12 小时',p:'/api/advance',b:{hours:12}},
  {t:'重置',p:'/api/reset',b:{},cls:'hot'}
];
for(const a of ACTIONS){
  const b=document.createElement('button');
  b.textContent=a.t; if(a.cls) b.className=a.cls;
  b.onclick=()=>post(a.p,a.b);
  el('controls').appendChild(b);
}

function crossing(series,key,threshold){
  for(const p of series) if(p[key]>=threshold) return p.h;
  return null;
}

/* 此刻在做什么：现在进行时，不是数值 */
function doingLine(s,plan){
  const b=s.bond,n=s.needs,e=s.emotion.label,pv=plan.proactive||{};
  const h=new Date(s.now).getHours();
  const auto=s.auto||{},ck=s.clock||{};
  if(ck.asleep) return ck.is_nap?'累得不行，正在眯一会儿'
    :('睡着了'+(ck.slept_h&&ck.slept_h>=0.3?('，睡了 '+fmt(ck.slept_h)+' 小时'):''));
  if(s.just_woken&&s.just_woken.at&&(Date.parse(s.now)/1000-s.just_woken.at)<1200)
    return (s.just_woken.hard||b.tier!=='none')?'刚被吵醒，脾气不太好':'刚被吵醒，迷迷糊糊的';
  if(b.tier==='big') return '在生闷气，不太想理人';
  if(auto.note&&auto.ago_min!=null&&auto.ago_min<50)
    return '刚'+auto.note;
  if(b.tier==='mid') return '有点赌气，话变少了';
  if(n.energy>=78&&(h>=22||h<6)) return '困得不行，还撑着没去睡';
  if(n.hunger>=72) return '饿了，在翻箱倒柜找吃的';
  if(n.longing>=72) return '在等你，隔一会儿看一次手机';
  if(s.topic.waiting_reply) return '在等你回话，等到有点烦了';
  if(n.boredom>=70) return '无聊，想找人聊两句';
  if(pv.should_send) return '想主动跟你说点什么，正犹豫';
  if(n.energy>=70) return '有点撑不住，想躺一会儿';
  if(e==='affectionate') return '在想你，心情软软的';
  if(e==='joyful'||e==='excited'||e==='playful') return '心情不错，在等你来聊';
  if(e==='sad'||e==='disappointed') return '情绪有点低，安静待着';
  return '没什么事，自己在待着';
}

/* 为什么：读记忆库（可能比这几十条 log 更久远），久远的只留概括不留原话 */
function whyLine(s){
  const b=s.bond,n=s.needs,m=s.memory||{};
  const neg=m.last_neg, pos=m.last_pos;
  if(b.tier!=='none'&&neg){
    return '因为'+neg.when+'你'+neg.verb
      +(neg.quote?'（「'+neg.quote+'」）':'')+'，到现在还记着。';
  }
  if(b.tier==='big') return '气还没过去，'+(b.hint||'要等时间')+'。';
  if(b.tier==='mid') return '心里那点事还搁着：'+(b.hint||'还差点')+'。';
  if(b.tier==='mild') return '还有点小情绪，'+(b.hint||'哄一下就好')+'。';
  if(s.topic.waiting_reply) return '上一句话还悬在那儿，没人接。';
  if(pos) return '因为'+pos.when+'你'+pos.verb+'，心里还是暖的。';
  if(n.longing>=60) return (m.talk&&m.talk.phrase?m.talk.phrase:'有一阵没说话')+'，就有点想你了。';
  if(n.hunger>=70) return '上一顿隔得有点久了。';
  return '没什么特别的原因，就是这会儿的样子。';
}

/* 缺得最厉害的那一样，该怎么办 */
function adviceNeed(s,topKey){
  const n=s.needs;
  if(Math.max(n.thirst,n.hunger,n.energy,n.boredom,n.longing)<65) return '';
  if(topKey==='渴')   return '倒杯水，或者问一句「渴不渴」。';
  if(topKey==='饿')   return '喂点吃的：问「吃饭了吗」，或发个零食图。';
  if(topKey==='累')   return '催去睡：「早点睡，明天再聊」。';
  if(topKey==='无聊') return '陪聊会儿，或者发个视频、好玩的图过去。';
  if(topKey==='想你') return '主动找一下，别一直等着。';
  return '';
}

/* 关系这一档，该怎么办 */
function adviceBond(s){
  const b=s.bond;
  if(b.tier==='big')  return '别急着哄。说一句「对不起」，然后留时间。';
  if(b.tier==='mid')  return '先认错，再哄一句就够，别连发。';
  if(b.tier==='mild') return '哄一句就好：「别生气啦，我错了」。';
  return '';
}

/* 心里话：第一人称，按优先级取第一条成立的 */
function innerVoice(s){
  const b=s.bond,n=s.needs,e=s.emotion.label;
  if(b.tier==='big')   return '我现在不想说话，等我缓过来。';
  if(b.tier==='mid')   return '刚才那句话我还记着，你打算什么时候认错。';
  if(b.tier==='mild')  return '哼，我还没消气呢。';
  if(n.longing>=72)    return '怎么还不来找我。';
  if(n.thirst>=72)     return '渴了，想喝水。';
  if(n.hunger>=72)     return '我饿了，想吃东西了。';
  if(n.energy>=72)     return '困死了，能不能让我睡一会儿。';
  if(n.boredom>=70)    return '好无聊，你陪我说说话嘛。';
  if(n.longing>=45)    return '你在忙什么呀，也不说一声。';
  if(e==='affectionate') return '想黏着你一会儿。';
  if(e==='joyful'||e==='excited'||e==='playful') return '今天心情很好，想跟你聊会儿。';
  if(e==='sad'||e==='disappointed') return '有点失落，不过我说不上来为什么。';
  if(s.topic.waiting_reply) return '我还在等你回我呢。';
  return '没什么事，就这么待着也挺好。';
}

function render(){
  if(!data) return;
  const s=data.snapshot, plan=data.plan, b=s.bond, n=s.needs, series=data.series||[];
  const lv=s.emotion.raw||{};
  const p2=v=>String(v).padStart(2,'0');
  const dt=s.now?new Date(s.now):null;
  el('clock').textContent=(dt?(dt.getMonth()+1)+'月'+p2(dt.getDate())+'日 '+p2(dt.getHours())+':'+p2(dt.getMinutes()):'—')
    +((s.clock&&s.clock.asleep)?' · 睡着中':(s.quiet?' · 勿扰中':''));

  const talk=(s.memory&&s.memory.talk)||{};
  el('idle').textContent=(talk.phrase&&talk.phrase!=='还没说过话')?('· '+talk.phrase):'';
  el('ver').textContent=s.version?('v'+s.version):'';
  const up=s.update||{};
  const upd=el('upd');
  if(up.has_update){
    upd.style.display='';
    upd.disabled=false;
    upd.textContent='新版本 '+up.latest+' · 更新';
  }else if(up.applying){
    upd.style.display='';
    upd.disabled=true;
    upd.textContent='正在更新…';
  }else{
    upd.style.display='none';
  }
  el('doing').textContent=doingLine(s,plan);
  el('why').textContent=whyLine(s);
  el('say').textContent=innerVoice(s);

  /* 关系 */
  const relMain=b.tier==='none'?'没事':b.tier_name;
  el('rel-card').classList.toggle('hot',b.tier!=='none');
  el('rel-big').innerHTML=relMain+'<span class="n">委屈 '+fmt(b.grievance)+'</span>';
  el('rel-sub').innerHTML='地板 '+fmt(b.floor)
    +(b.tier==='none'?'　不欠着什么事':'　<span class="warn">'+(b.hint||'')+'</span>');
  const ab=adviceBond(s);
  el('rel-advice').style.display=ab?'block':'none';
  el('rel-advice').textContent=ab;

  /* 情绪 */
  const emoName=(LABEL[s.emotion.label]||s.emotion.label);
  el('emo-big').innerHTML=emoName+'<span class="n">强度 '+pct(s.emotion.intensity)+'</span>';
  const rest=Object.keys(lv).filter(k=>k!==s.emotion.label&&(lv[k]||0)>0.05)
    .sort((a,c)=>(lv[c]||0)-(lv[a]||0));
  el('emo-sub').innerHTML=rest.length
    ? '其次 '+rest.slice(0,3).map(k=>'<em>'+(LABEL[k]||k)+' '+pct(lv[k])+'</em>').join('、')
    : '<span class="dim">没有别的情绪了，语气'+TONE[b.tone]+'</span>';

  /* 会不会来找你（主动） */
  const pv=plan.proactive||{};
  const urg=pv.urgency||0, th=pv.threshold||60;
  const on=!!pv.should_send;
  el('act-card').classList.toggle('on',on);
  el('act-big').textContent=on?(pv.craving?'想你想得厉害':'想去找你'):'还没想开口';
  const why=(pv.reason||'').replace(/（[^）]*）/g,'');
  el('act-sub').innerHTML=(on?'已经够 '+fmt(th)+' 分了':fmt(urg)+' / '+fmt(th)+' 分')
    +'<br><span class="dim">'+why+'</span>';
  el('act-bar').style.width=Math.min(100,Math.round(urg/th*100))+'%';

  /* 五条需求 */
  const needs=[['渴',n.thirst],['饿',n.hunger],['累',n.energy],['无聊',n.boredom],['想你',n.longing]]
    .sort((a,c)=>c[1]-a[1]);
  const top=needs[0];
  el('need-hint').textContent=adviceNeed(s,top[0])||'都还撑得住';
  el('needs').innerHTML=needs.map(([k,v],i)=>(
    '<div class="nd'+(i===0&&v>=60?' hot':'')+'">'
    +'<span class="k">'+k+'</span>'
    +'<span class="t"><i style="width:'+Math.max(0,Math.min(100,v))+'%"></i></span>'
    +'<span class="v">'+fmt(v)+'</span></div>')).join('');

  /* 记得的事 */
  const mem=el('mem'); mem.innerHTML='';
  const dig=((s.memory&&s.memory.digest)||[]).slice(0,2);
  if(!dig.length){
    const li=document.createElement('li');
    li.innerHTML='<span class="t">—</span><span class="dim" style="color:var(--faint)">'
      +'还没有值得记的事</span><span></span>';
    mem.appendChild(li);
  }
  dig.forEach(d=>{
    const li=document.createElement('li');
    const tm=document.createElement('span'); tm.className='t'; tm.textContent=d.when;
    const body=document.createElement('span');
    body.textContent=(d.by==='you'?'你':'')+d.verb;
    if(d.quote){
      const q=document.createElement('span');
      q.style.color='var(--dim)';
      q.textContent='（「'+d.quote+'」）';
      body.appendChild(q);
    }
    const tg=document.createElement('span'); tg.className='tag';
    tg.textContent=d.vague?'记不太清':'记得清楚';
    li.appendChild(tm); li.appendChild(body); li.appendChild(tg);
    mem.appendChild(li);
  });

  /* 这段时间 */
  const allLog=(s.log||[]);
  const logs=[]; let autoRows=0; let mediaRows=0;
  for(let i=allLog.length-1;i>=0&&logs.length<4;i--){
    const e=allLog[i];
    if(e.media&&e.media.url){
      if(mediaRows>=1) continue; mediaRows++;
    }else if(e.kind==='auto'){
      if(autoRows>=2) continue; autoRows++;
    }
    logs.unshift(e);
  }
  el('cnt').textContent=(s.memory&&s.memory.talk?s.memory.talk.phrase:'');
  const ul=el('past'); ul.innerHTML='';
  logs.forEach(e=>{
    const t=new Date(e.at*1000);
    const li=document.createElement('li');
    const tm=document.createElement('span'); tm.className='t';
    tm.textContent=p2(t.getHours())+':'+p2(t.getMinutes());
    const body=document.createElement('span');
    const who=document.createElement('b'); who.className='who';
    who.textContent=(e.kind==='auto'||e.speaker==='self')?'自己：':'对方：';
    body.appendChild(who);
    if(e.media&&e.media.url){
      const a=document.createElement('a');
      a.href=e.media.url; a.target='_blank'; a.rel='noreferrer';
      a.className='vlink'; a.textContent=(e.text||e.kind)+'  B站 ↗';
      body.appendChild(a);
    }else{
      body.appendChild(document.createTextNode(e.text||e.kind));
    }
    const tg=document.createElement('span');
    if(e.tags&&e.tags.length){ tg.className='tag'; tg.textContent=e.tags.slice(0,2).map(tagName).join(' · '); }
    li.appendChild(tm); li.appendChild(body); li.appendChild(tg);
    ul.appendChild(li);
  });

  /* 接下来 */
  const marks=[];
  const tT=crossing(series,'thirst',70),
        tH=crossing(series,'hunger',70), tL=crossing(series,'longing',60),
        tB=crossing(series,'boredom',70), tE=crossing(series,'energy',70),
        tG=crossing(series,'grievance',b.tier==='big'?100:65);
  if(tT!=null) marks.push({h:tT,what:'渴到 70，该倒水了'});
  if(tH!=null) marks.push({h:tH,what:'饿到 70，该喂点东西'});
  if(tE!=null) marks.push({h:tE,what:'累到 70，该去睡了'});
  if(tB!=null) marks.push({h:tB,what:'无聊到 70，会想找事做'});
  if(tL!=null) marks.push({h:tL,what:'想你到 60，会想主动找你'});
  if(tG!=null&&b.tier==='none') marks.push({h:tG,what:'开始委屈'});
  if(b.tier==='big'&&b.cool_left_h>0) marks.push({h:b.cool_left_h,what:'冷静完，气才真正消'});
  marks.sort((a,c)=>a.h-c.h);
  const fu=el('future'); fu.innerHTML='';
  if(!marks.length){
    const li=document.createElement('li'); li.className='future';
    li.innerHTML='<span class="t">+24h</span><span>没什么事，一直这样也行</span><span></span>';
    fu.appendChild(li);
  }
  marks.slice(0,3).forEach(m=>{
    const li=document.createElement('li'); li.className='future';
    const tm=document.createElement('span'); tm.className='t'; tm.textContent='+'+fmt(m.h)+'h';
    const body=document.createElement('span'); body.className='who'; body.textContent=m.what;
    const tg=document.createElement('span'); tg.className='tag'; tg.textContent='预计';
    li.appendChild(tm); li.appendChild(body); li.appendChild(tg);
    fu.appendChild(li);
  });

  el('prompt').textContent=plan.prompt;
}

/* ── 设置抽屉 ── */
const scrim=el('scrim'), drawer=el('drawer'), sbody=el('s-body'), smsg=el('s-msg');
let SCFG=null;

async function openSettings(){
  const r=await fetch('/api/settings'); SCFG=await r.json();
  renderSettings();
  scrim.classList.add('on'); drawer.classList.add('on');
}
function closeSettings(){
  scrim.classList.remove('on'); drawer.classList.remove('on'); smsg.textContent='';
}
function renderSettings(){
  const groups={};
  (SCFG.fields||[]).forEach(f=>{(groups[f.group]=groups[f.group]||[]).push(f);});
  sbody.innerHTML=Object.keys(groups).map(g=>
    '<div class="s-grp"><h4>'+g+'</h4>'+groups[g].map(f=>{
      const v=SCFG.values[f.key];
      let input;
      if(f.kind==='num'){
        input='<input type="number" data-k="'+f.key+'" value="'+v+'" min="'+f.min
          +'" max="'+f.max+'" step="'+f.step+'">';
      }else if(f.kind==='time'){
        input='<input type="time" data-k="'+f.key+'" value="'+v+'">';
      }else{
        input='<input type="text" data-k="'+f.key+'" value="'
          +String(v).replace(/"/g,'&quot;')+'">';
      }
      return '<label class="s-row"><span>'+f.label
        +(f.unit?'（'+f.unit+'）':'')+'</span>'+input+'</label>';
    }).join('')+'</div>').join('');
}
async function saveSettings(){
  const patch={};
  sbody.querySelectorAll('input[data-k]').forEach(i=>{patch[i.dataset.k]=i.value;});
  const r=await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});
  const j=await r.json();
  if(!r.ok){
    smsg.textContent=j.error||'保存失败'; smsg.style.color='#d3a0a0'; return;
  }
  SCFG=j;
  smsg.textContent='已保存'; smsg.style.color='#a3c3ae';
  await load();
  setTimeout(()=>{ if(smsg.textContent==='已保存') smsg.textContent=''; },1600);
}
el('gear').onclick=openSettings;
el('s-close').onclick=closeSettings;
el('s-save').onclick=saveSettings;
scrim.onclick=closeSettings;
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeSettings(); });

if(location.hash==='#settings') openSettings();

/* 量一下版式：?probe=1 时把各块的位置尺寸塞进标题，方便 headless 检查 */
function probe(){
  const rows=[...document.querySelectorAll('.now,.m,.needs,.tl')].map(e=>{
    const r=e.getBoundingClientRect();
    return {c:(e.className||'').split(' ')[0],
            y:Math.round(r.top),h:Math.round(r.height),w:Math.round(r.width)};
  });
  const out={vw:innerWidth,sw:document.documentElement.scrollWidth,
             sh:document.documentElement.scrollHeight,rows:rows};
  document.title='PROBE '+JSON.stringify(out);
}
let probed=false;
function maybeProbe(){
  if(probed||location.search.indexOf('probe')<0) return;
  probed=true; requestAnimationFrame(probe);
}

/* 刷新间隔由设置决定 */
function tick(){
  load().catch(()=>{}).then(()=>{
    const st=(data&&data.snapshot&&data.snapshot.settings)||{};
    setTimeout(tick, Math.max(500, st.refresh_ms||2000));
  });
}
tick();
</script>
</body>
</html>"""