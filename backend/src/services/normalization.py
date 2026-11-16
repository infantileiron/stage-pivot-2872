"""演出归一纯计算引擎。

输入场次、生效规则与标准演出，输出归属与隔离。不触碰数据库，便于单测与试算复用。
原始名称始终保留在 original_play / chain 中，归一只产出标准演出视角。

规则指向二选一：
- target_play_id 直接指向标准演出（一级）
- target_rule_id 指向另一条别名规则（多级），链尾必须落到标准演出
循环、交叠歧义、无匹配、链终点非法均进入隔离，不参与合格透视。
"""
from src.constants.enums import ISOLATION_REASONS,MAX_CHAIN_DEPTH

def net(row):
 return (row.get('gross_cents') or 0)-(row.get('refund_cents') or 0)-(row.get('fee_cents') or 0)

def candidates(rules,venue,alias,day):
 """同场馆、别名精确一致、生效日期覆盖场次日期的规则。"""
 return [r for r in rules
         if r['venue']==venue and r['alias_name']==alias
         and r['start_day']<=day<=r['end_day']]

def chain_text(chain,play_by_id):
 """把规则链渲染成可读的归属解释。"""
 parts=[]
 for step in chain:
  arrow='→ 标准演出「%s」'%play_by_id[step['to_play_id']]['name'] if step.get('to_play_id') else '→ 规则 #%s'%step.get('to_rule_id')
  parts.append('规则 #%s（%s / %s~%s）%s'%(step['rule_id'],step['venue'],step['start_day'],step['end_day'],arrow))
 return '；'.join(parts)

def resolve(settlements,rules,standard_plays):
 """返回 (attributions,isolations)。

 rules: dict 列表，含 id/alias_name/venue/start_day/end_day/target_play_id/target_rule_id
 standard_plays: dict 列表，含 id/name
 """
 play_by_id={p['id']:p for p in standard_plays}
 rule_by_id={r['id']:r for r in rules}
 attributions=[];isolations=[]
 for row in settlements:
  venue=row['venue'];alias=row['play'];day=row['day']
  hit=candidates(rules,venue,alias,day)
  if not hit:
   isolations.append(_isolate(row,'no_match',f"{venue} 在 {day} 没有覆盖别名「{alias}」的生效规则"))
   continue
  if len(hit)>1:
   ids='、'.join('#'+str(r['id']) for r in hit)
   isolations.append(_isolate(row,'overlap',f"别名「{alias}」在 {venue} / {day} 命中交叠规则 {ids}，无法确定唯一指向"))
   continue
  first=hit[0]
  chain=[{'rule_id':first['id'],'alias_name':first['alias_name'],'venue':venue,
          'start_day':first['start_day'],'end_day':first['end_day'],
          'to_play_id':first.get('target_play_id'),'to_rule_id':first.get('target_rule_id')}]
  visited={first['id']};cur=first;reason=None;detail=''
  while not cur.get('target_play_id'):
   nxt_id=cur.get('target_rule_id')
   nxt=rule_by_id.get(nxt_id)
   if not nxt:
    reason='invalid_chain';detail=f"规则 #{cur['id']} 的下一级规则 #{nxt_id} 不存在或未生效，链终点不是标准演出";break
   if nxt['id'] in visited or len(chain)>=MAX_CHAIN_DEPTH:
    reason='cycle';detail=f"规则链经过规则 #{nxt['id']} 时出现循环或超过 {MAX_CHAIN_DEPTH} 级，停止解析";break
   visited.add(nxt['id'])
   chain.append({'rule_id':nxt['id'],'alias_name':nxt['alias_name'],'venue':nxt['venue'],
                 'start_day':nxt['start_day'],'end_day':nxt['end_day'],
                 'to_play_id':nxt.get('target_play_id'),'to_rule_id':nxt.get('target_rule_id')})
   cur=nxt
  if reason:
   isolations.append(_isolate(row,reason,detail));continue
  standard=play_by_id.get(cur['target_play_id'])
  if not standard:
   isolations.append(_isolate(row,'invalid_chain',f"规则链终点指向的标准演出 #{cur['target_play_id']} 不存在"));continue
  attributions.append({'settlement_id':row['id'],'code':row['code'],'original_play':alias,
                       'standard_play_id':standard['id'],'standard_play':standard['name'],
                       'chain':chain,'chain_text':chain_text(chain,play_by_id)})
 return attributions,isolations

def _isolate(row,reason,detail):
 assert reason in ISOLATION_REASONS
 return {'settlement_id':row['id'],'code':row['code'],'original_play':row['play'],'venue':row['venue'],'day':row['day'],
         'reason':reason,'detail':detail,
         'gross_cents':row.get('gross_cents') or 0,'refund_cents':row.get('refund_cents') or 0,
         'fee_cents':row.get('fee_cents') or 0,'net_cents':net(row)}

def reconcile(settlements,attributions,isolations):
 """守恒校验：合格 + 隔离的场次数与各金额合计必须等于来源。"""
 src_count=len(settlements)
 out_count=len(attributions)+len(isolations)
 if src_count!=out_count:
  raise ValueError(f"归一不守恒：来源 {src_count} 场，合格 {len(attributions)} 场 + 隔离 {len(isolations)} 场")
 src_ids={r['id'] for r in settlements}
 out_ids=[r['settlement_id'] for r in attributions]+[r['settlement_id'] for r in isolations]
 if set(out_ids)!=src_ids:raise ValueError('归一不守恒：场次集合与来源不一致（遗漏或重复归并）')
 if len(set(out_ids))!=len(out_ids):raise ValueError('归一不守恒：同一场次被重复归并')
 src_net=sum(net(r) for r in settlements)
 iso={f:sum(r[f] for r in isolations) for f in ('gross_cents','refund_cents','fee_cents','net_cents')}
 attr_rows=[next(x for x in settlements if x['id']==a['settlement_id']) for a in attributions]
 attr_net=sum(net(r) for r in attr_rows)
 if attr_net+iso['net_cents']!=src_net:raise ValueError('归一不守恒：净额合计不等于来源')
 return {'source_count':src_count,'matched_count':len(attributions),'isolated_count':len(isolations),
         'source_gross_cents':sum((r.get('gross_cents') or 0) for r in settlements),
         'source_refund_cents':sum((r.get('refund_cents') or 0) for r in settlements),
         'source_fee_cents':sum((r.get('fee_cents') or 0) for r in settlements),
         'source_net_cents':src_net,
         'isolated_gross_cents':iso['gross_cents'],'isolated_refund_cents':iso['refund_cents'],
         'isolated_fee_cents':iso['fee_cents'],'isolated_net_cents':iso['net_cents']}
