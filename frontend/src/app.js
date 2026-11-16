import {api,post} from './api/client.js';import {state} from './stores/session.js';import {routes,page} from './router/index.js';import {values,feedback} from './hooks/form.js';import {esc} from './utils/html.js';import * as settlements from './pages/settlements.js';import * as layout from './pages/layout.js';import * as pivot from './pages/pivot.js';import * as reviews from './pages/reviews.js';import * as normalization from './pages/normalization.js';
const root=document.querySelector('#app');
const PAGES=[settlements,layout,pivot,reviews,normalization];
async function loadNormalize(){
 [state.standards,state.rules,state.jobs,state.normalizeMeta]=await Promise.all(
  ['/standard-plays','/alias-rules','/normalize/jobs','/normalize/meta'].map(x=>api(x)));
}
async function load(){
 [state.settlements,state.pivots,state.reviews]=await Promise.all(['/settlements','/pivots','/reviews'].map(x=>api(x)));
 await loadNormalize();
 state.selected=state.pivots.find(r=>r.id===state.selected?.id)||state.pivots[0]||null;
}
function login(){root.innerHTML=`<div class="login"><section class="cover"><div class="eyebrow">YUN MU / SETTLEMENT PROGRAMME 012</div><h1>散场之后，<br>每一笔都有回声。</h1><p>云幕剧院 · 场次结算节目单<br>明细 → 归一 → 透视 → 冻结下钻 → 差异签核<br>三处场馆 / 演出改名归一 / 分币守恒</p></section><section><div class="eyebrow">STAGE PIVOT</div><h2>登录结算节目单</h2><form id="login"><label>工作邮箱<input name="email" type="email" value="analyst@demo.local" required></label><label>密码<input name="password" type="password" value="Demo123!" required></label><button class="primary">进入场次结算</button></form><p id="error" class="error"></p><p>admin / analyst / viewer @demo.local<br>密码：Demo123!</p></section></div>`;document.querySelector('form').onsubmit=e=>{e.preventDefault();run(async()=>{let d=await post('/auth/login',values(e.target));localStorage.setItem('token',d.token);state.user=d.user;await load();render()})}}
function render(){let n=Math.min(PAGES.length-1,Math.max(0,page()));root.innerHTML=`<header><div class="brand">云幕 / 场次结算节目单 <span class="eyebrow">STAGE PIVOT</span></div><div>${esc(state.user.email)} · ${esc(state.user.role)} <button id="logout">退出</button></div></header><div class="layout"><nav>${routes.map((r,i)=>`<button data-nav="${i}" class="${i===n?'active':''}">0${i+1} ${r}</button>`).join('')}<span class="eyebrow">THEATRE ACCOUNTS / 2026</span></nav><main><div class="intro"><div><div class="eyebrow">SETTLEMENT PROGRAMME / 0${n+1}</div><h1>${routes[n]}</h1><p>让票款、退款与渠道费回到具体场次。演出按场馆与生效窗口归一，每份透视保留原始明细，差异由财务负责人签核。</p></div><span class="tag">3 场馆 / 散场结算</span></div><p id="error" class="error"></p>${PAGES[n].render()}</main></div>`;bind();if(state.user.role==='viewer')document.querySelectorAll('form button,#draft-review').forEach(b=>{b.disabled=true;b.textContent='观察员只读'});}
async function run(fn){try{await fn()}catch(e){feedback(e.message)}}
function numFields(d){for(let k of ['gross_cents','refund_cents','fee_cents','seats','checked','pivot_id','expected_cents','target_play_id','target_rule_id','rule_id'])if(k in d&&d[k]!=='')d[k]=Number(d[k]);return d}
function bind(){
 document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>location.hash=b.dataset.nav);
 document.querySelector('#logout').onclick=()=>{localStorage.removeItem('token');state.user=null;login()};
 for(let [id,path] of [['settlement','/settlements'],['pivot','/pivots'],['review','/reviews']]){const f=document.querySelector('#'+id);if(f)f.onsubmit=e=>{e.preventDefault();run(async()=>{let d=numFields(values(f));for(let k of ['target_play_id','target_rule_id','normalize_job_id'])if(k in d&&!d[k])delete d[k];let record=d.record_id;delete d.record_id;let created=record?await api(path+'/'+record,{method:'PUT',body:JSON.stringify(d)}):await post(path,d);if(id==='pivot'){state.selected=created;state.drill=null;state.chosen=null}await load();if(id==='pivot'&&location.hash!=='#2')location.hash='2';else render()})}}
 // 归一：标准演出
 const sf=document.querySelector('#standard');if(sf)sf.onsubmit=e=>{e.preventDefault();run(async()=>{await post('/standard-plays',values(e.target));await load();render()})};
 // 归一：别名规则（指向方式二选一）
 const af=document.querySelector('#alias');if(af)af.onsubmit=e=>{e.preventDefault();run(async()=>{
  let d=values(e.target);const isRule=d.target_type==='rule';
  let body={alias_name:d.alias_name,venue:d.venue,start_day:d.start_day,end_day:d.end_day,note:d.rule_note||''};
  if(isRule){if(!d.target_rule_id)throw Error('请选择上级别名规则');body.target_rule_id=Number(d.target_rule_id)}
  else{if(!d.target_play_id)throw Error('请选择目标标准演出');body.target_play_id=Number(d.target_play_id)}
  if(d.rule_id)await api('/alias-rules/'+d.rule_id,{method:'PUT',body:JSON.stringify(body)});
  else await post('/alias-rules',body);
  await load();render();
 })};
 const tt=document.querySelector('#target_type');if(tt)tt.onchange=e=>{
  const isRule=e.target.value==='rule';
  af.querySelector('[name=target_play_id]').disabled=isRule;
  af.querySelector('[name=target_rule_id]').disabled=!isRule;
 };
 // 归一：发起批次
 const jf=document.querySelector('#job');if(jf)jf.onsubmit=e=>{e.preventDefault();run(async()=>{await post('/normalize/jobs',values(e.target));await load();render()})};
 document.querySelectorAll('[data-rule-state]').forEach(b=>b.onclick=()=>run(async()=>{await post('/alias-rules/'+b.dataset.ruleState+'/state',{state:b.dataset.state});await load();render()}));
 document.querySelectorAll('[data-retry]').forEach(b=>b.onclick=()=>run(async()=>{await post('/normalize/jobs/'+b.dataset.retry+'/retry',{});await load();render()}));
 document.querySelectorAll('[data-job]').forEach(b=>b.onclick=()=>run(async()=>{
  const [detail,iso]=await Promise.all([api('/normalize/jobs/'+b.dataset.job),api('/normalize/jobs/'+b.dataset.job+'/isolations').catch(()=>[])]);
  state.jobDetail=detail;state.jobIsolations=iso;render();document.querySelector('.panel')?.scrollIntoView({block:'start'});
 }));
 document.querySelectorAll('[data-iso-export]').forEach(b=>b.onclick=()=>run(async()=>{
  let d=await api('/normalize/jobs/'+b.dataset.isoExport+'/isolations/export');
  let u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));
  let a=document.createElement('a');a.href=u;a.download='play-isolations-'+b.dataset.isoExport+'.json';a.click();URL.revokeObjectURL(u);
 }));
 document.querySelectorAll('[data-chain]').forEach(b=>b.onclick=()=>run(async()=>{
  state.chain=await api('/settlements/'+b.dataset.chain+'/attribution-chain');render();
 }));
 document.querySelectorAll('[data-pivot]').forEach(b=>b.onclick=()=>run(async()=>{state.selected=await api('/pivots/'+b.dataset.pivot);state.drill=null;state.chosen=null;if(location.hash!=='#2')location.hash='2';else render()}));
 document.querySelectorAll('[data-drill-row]').forEach(b=>b.onclick=()=>run(async()=>{state.drill=await api('/pivots/'+state.selected.id+'/drill?'+new URLSearchParams({row_key:b.dataset.drillRow,col_key:b.dataset.drillCol}));render();document.querySelector('#draft-review')?.scrollIntoView({block:'center'})}));
 const draft=document.querySelector('#draft-review');if(draft)draft.onclick=()=>{state.chosen=state.drill.cell;location.hash='3'};
 document.querySelectorAll('[data-approve]').forEach(b=>b.onclick=()=>run(async()=>{await post('/reviews/'+b.dataset.approve+'/approve',{});await load();render()}));
 const refresh=document.querySelector('#refresh');if(refresh)refresh.onclick=()=>run(async()=>{await load();render()});
 const download=document.querySelector('#download');if(download)download.onclick=()=>run(async()=>{let d=await api('/pivots/'+state.selected.id+'/export');let u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));let a=document.createElement('a');a.href=u;a.download='stage-pivot-'+d.id+'.json';a.click();URL.revokeObjectURL(u)});
}
window.onhashchange=()=>{if(state.user){render();window.scrollTo(0,0)}};if(localStorage.getItem('token'))run(async()=>{try{state.user=await api('/me');await load();render()}catch(e){localStorage.removeItem('token');login();feedback(e.message)}});else login();
