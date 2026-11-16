"""演出归一的数据库服务层：规则维护、版本推进、试算/启用批次与原子切换。"""
from datetime import datetime,timezone
from fastapi import HTTPException
from src.models.entities import (StandardPlay,AliasRule,NormalizeJob,PlayAttribution,PlayIsolation,
                                  Meta,Settlement)
from src.constants.enums import (RULE_STATES,JOB_KINDS,META_RULE_VERSION,META_SETTLEMENT_VERSION,
                                 META_ACTIVE_JOB,REASON_TEXT)
from src.services.normalization import resolve,reconcile

def now():return datetime.now(timezone.utc).isoformat()

def _meta_get(s,key,default='0'):
 m=s.query(Meta).filter_by(key=key).first()
 return m.value if m else default

def _meta_set(s,key,value):
 m=s.query(Meta).filter_by(key=key).first()
 if not m:m=Meta(key=key,value=str(value))
 else:m.value=str(value)
 s.add(m)

def get_versions(s):
 return {'rule_version':int(_meta_get(s,META_RULE_VERSION)),'settlement_version':int(_meta_get(s,META_SETTLEMENT_VERSION)),
         'active_job_id':int(_meta_get(s,META_ACTIVE_JOB,'0') or 0)}

def bump_rule_version(s):
 v=int(_meta_get(s,META_RULE_VERSION))+1;_meta_set(s,META_RULE_VERSION,v);s.commit();return v

def bump_settlement_version(s):
 v=int(_meta_get(s,META_SETTLEMENT_VERSION))+1;_meta_set(s,META_SETTLEMENT_VERSION,v);s.commit();return v

# ---------- 标准演出与规则 ----------
def create_standard(s,data):
 if s.query(StandardPlay).filter_by(name=data.name).first():raise HTTPException(409,'标准演出名称已存在')
 r=StandardPlay(name=data.name,note=data.note or '',created=now());s.add(r);s.commit();return r

def list_rules(s):
 return s.query(AliasRule).order_by(AliasRule.id).all()

def _rule_payload(s,data):
 if not data.start_day<=data.end_day:raise HTTPException(422,'生效起始日期不得晚于截止日期')
 if not data.target_play_id and not data.target_rule_id:
  raise HTTPException(422,'规则必须直接指向标准演出，或指向上一级别名规则')
 if data.target_play_id and not s.get(StandardPlay,data.target_play_id):
  raise HTTPException(404,'目标标准演出不存在')
 if data.target_play_id and data.target_rule_id:raise HTTPException(422,'一条规则只能选择一种指向：标准演出或上级规则')
 if data.target_rule_id:
  up=s.get(AliasRule,data.target_rule_id)
  if not up:raise HTTPException(404,'上级别名规则不存在')
  if up.target_rule_id and not up.target_play_id and _chain_depth(s,up)>=15:raise HTTPException(422,'规则链超过最大层级')
 return dict(alias_name=data.alias_name.strip(),venue=data.venue,start_day=data.start_day.isoformat(),
             end_day=data.end_day.isoformat(),target_play_id=data.target_play_id,target_rule_id=data.target_rule_id,
             note=data.note or '')

def _chain_depth(s,rule):
 depth=0;cur=rule;seen=set()
 while cur and cur.target_rule_id and cur.id not in seen:
  seen.add(cur.id);cur=s.get(AliasRule,cur.target_rule_id);depth+=1
  if depth>32:break
 return depth

def create_rule(s,data):
 d=_rule_payload(s,data)
 r=AliasRule(**d,state='draft',version=1,created=now(),updated=now());s.add(r);s.flush()
 _assert_no_overlap(s,r);bump_rule_version(s);s.commit();return r

def update_rule(s,i,data):
 r=s.get(AliasRule,i)
 if not r:raise HTTPException(404,'别名规则不存在')
 if r.state=='active':raise HTTPException(409,'启用中的规则不可直接修改，请先停用或新建版本')
 d=_rule_payload(s,data)
 for k,v in d.items():setattr(r,k,v)
 r.updated=now();r.version+=1;s.flush()
 _assert_no_overlap(s,r);bump_rule_version(s);s.commit();return r

def set_rule_state(s,i,state):
 if state not in RULE_STATES:raise HTTPException(422,'规则状态只能是 draft 或 active')
 r=s.get(AliasRule,i)
 if not r:raise HTTPException(404,'别名规则不存在')
 if state=='active':
  if not (r.target_play_id or r.target_rule_id):raise HTTPException(422,'规则缺少有效指向，不能启用')
  _assert_no_cycle(s,r);_assert_no_overlap(s,r)
 if r.state!=state:
  r.state=state;r.updated=now();r.version+=1;bump_rule_version(s);s.commit()
 return r

def _assert_no_overlap(s,r):
 q=s.query(AliasRule).filter(AliasRule.venue==r.venue,AliasRule.alias_name==r.alias_name,
                             AliasRule.id!=r.id,AliasRule.state=='active')
 for other in q.all():
  if other.start_day<=r.end_day and r.start_day<=other.end_day:
   raise HTTPException(409,f"与启用规则 #{other.id} 的生效日期交叠（{other.start_day}~{other.end_day}），同场馆同名别名在同一日期只能有一条规则")

def _assert_no_cycle(s,r):
 seen=set();cur=r
 while cur and cur.target_rule_id:
  if cur.id in seen:raise HTTPException(409,f"规则指向存在循环（规则 #{cur.id} 重复出现），不能启用")
  seen.add(cur.id);cur=s.get(AliasRule,cur.target_rule_id)
 if cur and not cur.target_play_id:raise HTTPException(409,'规则链终点未落到标准演出，不能启用')

# ---------- 批次 ----------
def _active_rules(s):
 rules=s.query(AliasRule).filter_by(state='active').order_by(AliasRule.id).all()
 return [_rule_dict(r) for r in rules]

def _rule_dict(r):
 return {'id':r.id,'alias_name':r.alias_name,'venue':r.venue,'start_day':r.start_day,'end_day':r.end_day,
         'target_play_id':r.target_play_id,'target_rule_id':r.target_rule_id}

def _settlements(s):
 return [{'id':r.id,'code':r.code,'day':r.day,'venue':r.venue,'play':r.play,'channel':r.channel,
          'gross_cents':r.gross_cents,'refund_cents':r.refund_cents,'fee_cents':r.fee_cents,
          'seats':r.seats,'checked':r.checked} for r in s.query(Settlement).order_by(Settlement.id).all()]

def _standards(s):
 return [{'id':p.id,'name':p.name} for p in s.query(StandardPlay).order_by(StandardPlay.id).all()]

def create_job(s,kind,name):
 if kind not in JOB_KINDS:raise HTTPException(422,'批次类型只能是 trial 或 activate')
 vers=get_versions(s)
 j=NormalizeJob(name=name or ('演出归一批次 #'),kind=kind,state='queued',
                rule_version=vers['rule_version'],settlement_version=vers['settlement_version'],
                current_rule_version=vers['rule_version'],current_settlement_version=vers['settlement_version'],
                created=now())
 s.add(j);s.commit();return j

def process_job(s,job_id):
 """worker 调用：试算只写 result；启用在单事务内清旧归属、写新归属并切换激活指针。"""
 j=s.get(NormalizeJob,job_id)
 if not j:return None
 if j.state not in ('queued','failed'):return j
 vers=get_versions(s)
 j.current_rule_version=vers['rule_version'];j.current_settlement_version=vers['settlement_version']
 stale=(vers['rule_version']!=j.rule_version or vers['settlement_version']!=j.settlement_version)
 if stale and j.kind=='activate':
  j.state='failed';j.error='规则或场次已在排队期间变更（版本过期），请基于最新规则重新试算后再启用';j.finished=now();s.commit();return j
 rows=_settlements(s);rules=_active_rules(s);plays=_standards(s)
 j.state='running';s.commit()
 try:
  attrs,isol=resolve(rows,rules,plays)
  summary=reconcile(rows,attrs,isol)
  result={'summary':summary,'attributions':attrs,'isolations':[dict(x,reason_text=REASON_TEXT[x['reason']]) for x in isol],
          'stale':stale,'rule_version':j.rule_version,'settlement_version':j.settlement_version,
          'current_rule_version':vers['rule_version'],'current_settlement_version':vers['settlement_version']}
  if j.kind=='activate':
   if stale:raise RuntimeError('版本过期，拒绝写入归属')
   _publish(s,j,attrs,isol,result)
  j.result=result;j.state='done';j.error='';j.finished=now();s.commit()
 except Exception as e:
  s.rollback();j=s.get(NormalizeJob,job_id);j.state='failed';j.error=str(e);j.finished=now();s.commit()
 return j

def _publish(s,j,attrs,isol,result):
 """单事务原子切换：删旧归属/隔离 → 写新归属/隔离 → 切激活指针。任一失败整体回滚。"""
 s.query(PlayAttribution).filter_by(job_id=j.id).delete(synchronize_session=False)
 s.query(PlayIsolation).filter_by(job_id=j.id).delete(synchronize_session=False)
 for a in attrs:
  s.add(PlayAttribution(job_id=j.id,settlement_id=a['settlement_id'],code=a['code'],original_play=a['original_play'],
                        standard_play_id=a['standard_play_id'],standard_play=a['standard_play'],chain=a['chain']))
 for x in isol:
  s.add(PlayIsolation(job_id=j.id,settlement_id=x['settlement_id'],code=x['code'],original_play=x['original_play'],
                      venue=x['venue'],day=x['day'],reason=x['reason'],detail=x['detail'],
                      gross_cents=x['gross_cents'],refund_cents=x['refund_cents'],fee_cents=x['fee_cents'],net_cents=x['net_cents']))
 _meta_set(s,META_ACTIVE_JOB,str(j.id))
 result['activated']=True

def retry_job(s,job_id):
 """失败后续跑：仅 queued/failed 可重入；done 直接返回，绝不重复归并。"""
 j=s.get(NormalizeJob,job_id)
 if not j:raise HTTPException(404,'归一任务不存在')
 if j.state=='done':return j
 if j.state=='running':raise HTTPException(409,'任务正在执行，不能重复提交')
 j.state='queued';j.error='';s.commit();return j

# ---------- 透视快照与归属解释 ----------
def snapshot_rows(s,job_id=None):
 """带标准演出视角的快照。job_id 给定时只放该合格批次的场次，并附排除金额说明。"""
 rows=_settlements(s)
 if not job_id:return rows,None
 job=s.get(NormalizeJob,job_id)
 if not job:raise HTTPException(404,'归一任务不存在')
 if job.state!='done':raise HTTPException(409,'仅完成的归一批次可以作为透视口径')
 if job.kind!='activate' or str(get_versions(s)['active_job_id'])!=str(job.id):
  raise HTTPException(409,'该批次不是当前激活批次，请使用最新激活批次')
 attr_map={a.settlement_id:a for a in s.query(PlayAttribution).filter_by(job_id=job.id).all()}
 kept=[]
 for r in rows:
  a=attr_map.get(r['id'])
  if not a:continue
  kept.append({**r,'nplay':a.standard_play,'standard_play_id':a.standard_play_id})
 excluded=job.result['summary']
 note=('透视仅含归一合格批次 #%s 的 %d 场；隔离 %d 场、净额 %d 分（票款 %d / 退款 %d / 渠道费 %d）已排除，'
       '合格与隔离合计等于全部来源场次。')%(job.id,excluded['matched_count'],excluded['isolated_count'],
       excluded['isolated_net_cents'],excluded['isolated_gross_cents'],excluded['isolated_refund_cents'],excluded['isolated_fee_cents'])
 return kept,{'job_id':job.id,'note':note,**excluded}

def chain_for_settlement(s,settlement_id):
 active=int(_meta_get(s,META_ACTIVE_JOB,'0') or 0)
 if not active:return None
 a=s.query(PlayAttribution).filter_by(job_id=active,settlement_id=settlement_id).first()
 if not a:return None
 rules={r.id:r for r in s.query(AliasRule).all()}
 steps=[]
 for step in a.chain:
  r=rules.get(step['rule_id'])
  steps.append({'rule_id':step['rule_id'],'alias_name':step.get('alias_name') or (r.alias_name if r else ''),
                'venue':step['venue'],'start_day':step['start_day'],'end_day':step['end_day'],
                'target_play_id':step.get('to_play_id'),'target_rule_id':step.get('to_rule_id')})
 return {'job_id':active,'code':a.code,'original_play':a.original_play,
         'standard_play':a.standard_play,'standard_play_id':a.standard_play_id,'chain':steps}
