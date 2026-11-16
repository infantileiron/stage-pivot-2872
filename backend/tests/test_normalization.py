import os
os.environ.setdefault('JWT_SECRET','test-secret')
os.environ.setdefault('DATABASE_URL','sqlite://')
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config.database import Base
from src.models import entities
from src.models.entities import (Settlement,StandardPlay,AliasRule,NormalizeJob,PlayAttribution,
                                 PlayIsolation,Meta)
from src.services import normalize_service as ns
from src.services.normalization import resolve,reconcile
from src.services.analysis import pivot

@pytest.fixture()
def s():
 engine=create_engine('sqlite://')
 Base.metadata.create_all(engine)
 S=sessionmaker(bind=engine,expire_on_commit=False)
 session=S()
 yield session
 session.close()

def settle(s,i,code,day,venue,play,gross=10000,refund=500,fee=300):
 r=Settlement(id=i,code=code,day=day,venue=venue,play=play,channel='剧院直营',
              gross_cents=gross,refund_cents=refund,fee_cents=fee,seats=100,checked=80)
 s.add(r);s.commit();return r

def standard(s,name='标准大戏'):
 p=StandardPlay(name=name,created=ns.now());s.add(p);s.commit();return p

def rule(s,alias,venue,start,end,target_play=None,target_rule=None,state='active'):
 r=AliasRule(alias_name=alias,venue=venue,start_day=start,end_day=end,
             target_play_id=target_play,target_rule_id=target_rule,state=state,
             version=1,created=ns.now(),updated=ns.now())
 s.add(r);s.commit();return r

def rows(s):return ns._settlements(s)

# ---------- 纯引擎 ----------
def test_basic_match_and_original_name_kept(s):
 p=standard(s);settle(s,1,'YM-001','2026-11-01','云幕大剧场','旧名字')
 rule(s,'旧名字','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id)
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert len(attrs)==1 and not isol
 assert attrs[0]['original_play']=='旧名字' and attrs[0]['standard_play']=='标准大戏'

def test_venue_and_date_window_scoping(s):
 p=standard(s)
 rule(s,'同名戏','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id)
 settle(s,1,'YM-001','2026-11-02','云幕大剧场','同名戏')          # 命中
 settle(s,2,'YM-002','2026-11-02','河畔小剧场','同名戏')          # 场馆不符 → 无匹配
 settle(s,3,'YM-003','2026-10-02','云幕大剧场','同名戏')          # 窗口外 → 无匹配
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert {x['code'] for x in attrs}=={'YM-001'}
 assert {x['reason'] for x in isol}=={'no_match'} and len(isol)==2

def test_multilevel_chain(s):
 p=standard(s)
 r1=rule(s,'中间名','河畔小剧场','2026-09-01','2026-12-31',target_play=p.id)
 r2=rule(s,'曾用名','河畔小剧场','2026-09-01','2026-12-31',target_rule=r1.id)
 settle(s,1,'YM-001','2026-11-01','河畔小剧场','曾用名')
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert len(attrs)==1 and attrs[0]['standard_play']=='标准大戏'
 assert [c['rule_id'] for c in attrs[0]['chain']]==[r2.id,r1.id]
 assert '规则 #%d'%r2.id in attrs[0]['chain_text']

def test_cycle_is_isolated(s):
 p=standard(s)
 ra=rule(s,'甲','云幕大剧场','2026-09-01','2026-12-31',state='draft')
 rb=rule(s,'乙','云幕大剧场','2026-09-01','2026-12-31',state='draft')
 ra.target_rule_id=rb.id;rb.target_rule_id=ra.id;s.commit()
 for r in (ra,rb):r.state='active'
 s.commit()
 settle(s,1,'YM-001','2026-11-01','云幕大剧场','甲')
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert not attrs and isol[0]['reason']=='cycle'

def test_overlap_is_isolated(s):
 p=standard(s);p2=standard(s,'另一部戏')
 rule(s,'撞名','云幕大剧场','2026-11-01','2026-11-20',target_play=p.id)
 rule(s,'撞名','云幕大剧场','2026-11-10','2026-11-30',target_play=p2.id)
 settle(s,1,'YM-001','2026-11-11','云幕大剧场','撞名')
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert not attrs and isol[0]['reason']=='overlap'

def test_invalid_chain_endpoint(s):
 r1=rule(s,'悬空','云幕大剧场','2026-09-01','2026-12-31',state='draft')
 r2=rule(s,'入口','云幕大剧场','2026-09-01','2026-12-31',target_rule=r1.id)
 r1.state='active';r2.state='active';s.commit()
 settle(s,1,'YM-001','2026-11-01','云幕大剧场','入口')
 attrs,isol=resolve(rows(s),ns._active_rules(s),ns._standards(s))
 assert not attrs and isol[0]['reason']=='invalid_chain'

def test_reconcile_conservation(s):
 p=standard(s)
 rule(s,'旧名字','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id)
 settle(s,1,'YM-001','2026-11-01','云幕大剧场','旧名字',gross=10000,refund=500,fee=300)
 settle(s,2,'YM-002','2026-11-01','云幕大剧场','无规则戏',gross=20000,refund=1000,fee=600)
 src=rows(s);attrs,isol=resolve(src,ns._active_rules(s),ns._standards(s))
 rep=reconcile(src,attrs,isol)
 assert rep['source_count']==2 and rep['matched_count']==1 and rep['isolated_count']==1
 assert rep['isolated_net_cents']==20000-1000-600
 assert rep['source_net_cents']==(10000-500-300)+(20000-1000-600)

# ---------- 服务层：版本、批次、原子切换 ----------
def _ready(s):
 p=standard(s)
 rule(s,'旧名字','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id)
 settle(s,1,'YM-001','2026-11-01','云幕大剧场','旧名字',gross=10000,refund=500,fee=300)
 settle(s,2,'YM-002','2026-11-01','云幕大剧场','孤戏',gross=20000,refund=1000,fee=600)
 return p

def test_trial_then_activate_publishes_and_switches(s):
 p=_ready(s)
 trial=ns.create_job(s,'trial','试算');ns.process_job(s,trial.id)
 trial=s.get(NormalizeJob,trial.id)
 assert trial.state=='done' and trial.result['summary']['isolated_count']==1
 assert s.query(PlayAttribution).count()==0  # 试算不落归属表
 job=ns.create_job(s,'activate','启用');ns.process_job(s,job.id)
 assert s.get(NormalizeJob,job.id).state=='done'
 assert s.query(PlayAttribution).filter_by(job_id=job.id).count()==1
 assert s.query(PlayIsolation).filter_by(job_id=job.id).count()==1
 assert ns.get_versions(s)['active_job_id']==job.id
 chain=ns.chain_for_settlement(s,1)
 assert chain['standard_play']=='标准大戏' and chain['original_play']=='旧名字' and len(chain['chain'])==1

def test_stale_activate_rejected(s):
 _ready(s)
 job=ns.create_job(s,'activate','启用')
 # 排队期间规则变更 → 版本推进
 ns.bump_rule_version(s)
 ns.process_job(s,job.id)
 j=s.get(NormalizeJob,job.id)
 assert j.state=='failed' and '版本过期' in j.error
 assert s.query(PlayAttribution).count()==0 and ns.get_versions(s)['active_job_id']==0

def test_settlement_revision_makes_activate_stale(s):
 _ready(s)
 job=ns.create_job(s,'activate','启用')
 ns.bump_settlement_version(s)
 ns.process_job(s,job.id)
 assert s.get(NormalizeJob,job.id).state=='failed'

def test_retry_does_not_duplicate(s):
 _ready(s)
 job=ns.create_job(s,'activate','启用');ns.bump_rule_version(s);ns.process_job(s,job.id)
 assert s.get(NormalizeJob,job.id).state=='failed'
 # 重试旧批次仍然过期 → 失败，且无归属
 ns.retry_job(s,job.id);ns.process_job(s,job.id)
 assert s.get(NormalizeJob,job.id).state=='failed' and s.query(PlayAttribution).count()==0
 # done 批次重试直接返回，不重复归并
 good=ns.create_job(s,'activate','启用二');ns.process_job(s,good.id)
 before=s.query(PlayAttribution).count()
 assert ns.retry_job(s,good.id).state=='done'
 ns.process_job(s,good.id)
 assert s.query(PlayAttribution).count()==before

def test_atomic_switch_replaces_old_batch(s):
 p=_ready(s)
 j1=ns.create_job(s,'activate','v1');ns.process_job(s,j1.id)
 assert s.query(PlayAttribution).filter_by(job_id=j1.id).count()==1
 # 新增可匹配规则后再启用，归属表整体切换
 r2=rule(s,'孤戏','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id)
 j2=ns.create_job(s,'activate','v2');ns.process_job(s,j2.id)
 assert s.query(PlayAttribution).filter_by(job_id=j2.id).count()==2
 assert s.query(PlayIsolation).filter_by(job_id=j2.id).count()==0
 assert ns.get_versions(s)['active_job_id']==j2.id
 # 旧批次明细仍保留可追溯
 assert s.query(PlayAttribution).filter_by(job_id=j1.id).count()==1

def test_rule_crud_guards(s):
 from fastapi import HTTPException
 p=standard(s)
 r1=rule(s,'戏','云幕大剧场','2026-11-01','2026-11-30',target_play=p.id,state='draft')
 r2=rule(s,'戏','云幕大剧场','2026-12-01','2026-12-31',target_play=p.id,state='draft')
 r1.target_rule_id=r2.id;r2.target_rule_id=r1.id
 with pytest.raises(HTTPException) as e:ns.set_rule_state(s,r1.id,'active')
 assert '循环' in e.value.detail
 r1.target_rule_id=None
 from src.schemas.business import AliasRuleInput
 from datetime import date
 ns.set_rule_state(s,r1.id,'active')
 with pytest.raises(HTTPException) as e:
  ns.create_rule(s,AliasRuleInput(alias_name='戏',venue='云幕大剧场',start_day=date(2026,11,15),
                                  end_day=date(2026,12,15),target_play_id=p.id))
 assert '交叠' in e.value.detail
 with pytest.raises(HTTPException):ns.update_rule(s,r1.id,AliasRuleInput(
  alias_name='戏',venue='云幕大剧场',start_day=date(2026,11,1),end_day=date(2026,11,30),target_play_id=p.id))

# ---------- 透视：合格批次与排除金额 ----------
def test_pivot_uses_only_qualified_batch_and_notes_exclusion(s):
 _ready(s)
 job=ns.create_job(s,'activate','启用');ns.process_job(s,job.id)
 kept,excl=ns.snapshot_rows(s,job.id)
 assert len(kept)==1 and kept[0]['nplay']=='标准大戏'
 assert excl['isolated_count']==1 and '排除' in excl['note']
 res=pivot(kept,'nplay','channel',excl)
 assert res['total']['count']==1 and res['conserved']
 assert '隔离 1 场' in res['method'] and res['exclusion']['isolated_net_cents']==20000-1000-600

def test_pivot_snapshot_requires_active_job(s):
 from fastapi import HTTPException
 _ready(s)
 trial=ns.create_job(s,'trial','试算');ns.process_job(s,trial.id)
 with pytest.raises(HTTPException):ns.snapshot_rows(s,trial.id)

def test_full_source_conservation_across_pivot(s):
 _ready(s)
 job=ns.create_job(s,'activate','启用');ns.process_job(s,job.id)
 kept,excl=ns.snapshot_rows(s,job.id)
 res=pivot(kept,'venue','channel',excl)
 src_net=sum((r.gross_cents-r.refund_cents-r.fee_cents) for r in s.query(Settlement).all())
 assert res['total']['net_cents']+excl['isolated_net_cents']==src_net
 assert res['total']['count']+excl['isolated_count']==excl['source_count']

def test_old_pivot_without_batch_keeps_original_behavior(s):
 settle(s,1,'YM-001','2026-11-01','云幕大剧场','原始名')
 rows_all,_=ns.snapshot_rows(s,None)
 res=pivot(rows_all,'play','channel')
 assert res['total']['count']==1 and res['exclusion'] is None

def test_concurrent_activates_second_stale_and_first_wins(s):
 p=_ready(s)
 j1=ns.create_job(s,'activate','并发一')
 j2=ns.create_job(s,'activate','并发二')
 # 两个批次排队期间规则被并发启用 → 规则版本推进
 ns.bump_rule_version(s)
 ns.process_job(s,j1.id);ns.process_job(s,j2.id)
 assert s.get(NormalizeJob,j1.id).state=='failed'
 assert s.get(NormalizeJob,j2.id).state=='failed'
 assert ns.get_versions(s)['active_job_id']==0 and s.query(PlayAttribution).count()==0
 # 基于最新版本重新试算再启用，成功并原子激活
 fresh=ns.create_job(s,'activate','最新启用');ns.process_job(s,fresh.id)
 assert s.get(NormalizeJob,fresh.id).state=='done'
 assert ns.get_versions(s)['active_job_id']==fresh.id
 assert s.query(PlayAttribution).filter_by(job_id=fresh.id).count()==1

def test_trial_never_publishes_and_keeps_active_intact(s):
 j0=_ready(s)
 first=ns.create_job(s,'activate','基线启用');ns.process_job(s,first.id)
 assert ns.get_versions(s)['active_job_id']==first.id
 # 之后任意试算都不能改变激活指针与归属
 t=ns.create_job(s,'trial','再试算');ns.process_job(s,t.id)
 assert ns.get_versions(s)['active_job_id']==first.id
 assert s.query(PlayAttribution).filter_by(job_id=t.id).count()==0
 assert s.query(PlayIsolation).filter_by(job_id=t.id).count()==0
