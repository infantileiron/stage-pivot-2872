import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {badge} from '../components/common/status.js';
import {field,select} from '../components/common/fields.js';
import {table} from '../components/common/table.js';
import {VENUES,DIMENSIONS} from '../constants/enums.js';
import {money} from '../utils/format.js';

const DIM_LABEL=Object.fromEntries(DIMENSIONS);
const reasonText={no_match:'无匹配',cycle:'循环',overlap:'交叠歧义',invalid_chain:'链终点非法'};

export function render(){
 const m=state.normalizeMeta||{rule_version:0,settlement_version:0,active_job_id:0};
 const active=m.active_job_id;
 const latest=state.jobs[0];
 return `<div class="split">
 <section class="panel">
  <h2>演出归一：改名可合，同名不误并</h2>
  <p class="notice">规则按<b>场馆 + 生效日期</b>限定别名，可多级指向标准演出；循环、交叠歧义、无匹配、链终点非法的场次一律隔离。原始名称永久保留，规则变更后重新试算/启用即重算归属。</p>
  <div class="metrics">
   <div><strong>${m.rule_version}</strong>规则版本</div>
   <div><strong>${m.settlement_version}</strong>场次版本</div>
   <div><strong>${active?('#'+active):'未启用'}</strong>激活批次</div>
  </div>

  <h3>标准演出</h3>
  ${table(['ID','标准演出名称','备注'],state.standards.map(p=>[p.id,p.name,p.note]))}

  <h3>别名规则（场馆 / 生效窗口 / 指向）</h3>
  ${table(['#','别名（原始名称）','场馆','生效起','生效止','指向','状态','操作'],state.rules.map(r=>[
    r.id,r.alias_name,r.venue,r.start_day,r.end_day,
    r.target_play_name?('标准演出「'+r.target_play_name+'」'):('上级规则：'+(r.target_rule_alias||('#'+r.target_rule_id))),
    r.state,
    state.user.role==='viewer'?'—':{html:`<button data-rule-state="${r.id}" data-state="${r.state==='active'?'draft':'active'}">${r.state==='active'?'停用':'启用'}</button>`}
  ].map((v,i)=>i===6?badge(v):v)))}

  <h3>归一任务（草稿试算 → 启用）</h3>
  ${state.jobs.map(j=>{
   const summ=j.result?.summary;
   return `<article class="rec">
    <div class="rulehead"><h3>#${j.id} ${esc(j.name)} ${badge(j.kind==='activate'?'启用':'试算')} ${badge(j.state)}</h3>
     <span class="eyebrow">规则v${j.rule_version} / 场次v${j.settlement_version}</span></div>
    ${j.state==='failed'?`<p class="error">${esc(j.error)}${state.user.role!=='viewer'?` <button data-retry="${j.id}">续跑该任务</button>`:''}</p>`:''}
    ${summ?`<p>来源 <b>${summ.source_count}</b> 场 = 合格 <b>${summ.matched_count}</b> + 隔离 <b>${summ.isolated_count}</b>；
      来源净额 ${money(summ.source_net_cents)} 元，隔离净额 <b>${money(summ.isolated_net_cents)} 元</b>（已从合格透视排除）。</p>
      <p class="eyebrow">票款 ${money(summ.isolated_gross_cents)} / 退款 ${money(summ.isolated_refund_cents)} / 渠道费 ${money(summ.isolated_fee_cents)}（隔离，单位元）</p>
      ${j.result?.stale?'<p class="error">该结果基于过期版本，仅供查看，不能启用。</p>':''}
      <p><button data-job="${j.id}">查看归属与隔离明细</button>
      <button data-iso-export="${j.id}">下载隔离明细 JSON</button>
      ${active===j.id?'<span class="tag">当前激活</span>':''}</p>`:''}
   </article>`;
  }).join('')||'<p>尚无任务。先在右侧保存规则并启用，再发起试算。</p>'}

  ${state.jobDetail?renderDetail(active):''}
 </section>

 <aside class="side">
  <h2>维护规则与发起批次</h2>
  <h3>新建标准演出</h3>
  <form id="standard">${field('标准演出名称','name','text','required')}${field('备注（可空）','note','text')}<button class="primary">保存标准演出</button></form>

  <h3>新建 / 修订别名规则</h3>
  <form id="alias">
   ${field('规则ID（修订填写）','rule_id','number','min=1')}
   ${field('别名（场次上的原始演出名）','alias_name','text','required')}
   ${select('限定场馆','venue',VENUES.map(x=>[x,x]))}
   ${field('生效起始日期','start_day','date','required value="2026-09-01"')}
   ${field('生效截止日期','end_day','date','required value="2026-12-31"')}
   <label>指向方式<select name="target_type" id="target_type"><option value="play">直接指向标准演出</option><option value="rule">指向上级规则（多级）</option></select></label>
   <label>标准演出<select name="target_play_id">${state.standards.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('')||'<option value="">请先建标准演出</option>'}</select></label>
   <label>上级规则<select name="target_rule_id" disabled>${state.rules.map(r=>`<option value="${r.id}">#${r.id} ${esc(r.alias_name)}（${esc(r.venue)}）</option>`).join('')}</select></label>
   ${field('备注（可空）','rule_note','text')}
   <button class="primary">保存别名规则</button>
  </form>

  <h3>发起归一</h3>
  <form id="job">
   <label>批次类型<select name="kind"><option value="trial">草稿试算（不改变激活归属）</option><option value="activate">启用（原子切换归属与隔离清单）</option></select></label>
   ${field('批次名称','name','text','value="演出归一"')}
   <button class="primary">提交后台计算</button>
  </form>
  <p class="notice">启用批次完成后，到「透视布局」选择标准演出维度 <b>${esc(DIM_LABEL.nplay)}</b> 并指定该批次；透视只含合格场次，页内注明隔离排除金额。</p>
 </aside>
</div>`;
}

function renderDetail(activeId){
 const j=state.jobDetail;const r=j.result;if(!r)return '';
 return `<h3>批次 #${j.id} 明细</h3>
  <p class="notice">合格 ${r.summary.matched_count} 场、隔离 ${r.summary.isolated_count} 场；场次数与金额合计等于来源 ${r.summary.source_count} 场。归属链展示每条规则的场馆与生效窗口。</p>
  <h4>合格归属（保留原始名称 → 标准演出）</h4>
  ${table(['场次','原始名称','标准演出','归属链解释'],r.attributions.map(a=>[
    a.code,a.original_play,a.standard_play,
    a.chain.map(c=>`#${c.rule_id} ${c.alias_name}@${c.venue}[${c.start_day}~${c.end_day}]${c.to_play_id?(' →「'+a.standard_play+'」'):(' → 规则#'+c.to_rule_id)}`).join('；')
  ]))}
  <h4>隔离明细（不进入合格透视）</h4>
  ${table(['场次','原始名称','场馆/日期','隔离原因','净额 / 元','说明'],(state.jobIsolations||r.isolations).map(x=>[
    x.code,x.original_play,x.venue+' / '+x.day,reasonText[x.reason]||x.reason,money(x.net_cents),x.detail
  ]))}
  ${activeId===j.id?'<p class="tag">该批次为当前激活口径</p>':'<p class="error">该批次不是当前激活批次，透视不会使用。</p>'}`;
}
