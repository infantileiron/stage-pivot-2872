import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from src.config.database import db
from src.models.entities import StandardPlay,AliasRule,NormalizeJob,PlayIsolation,Settlement
from src.schemas.business import StandardPlayInput,AliasRuleInput,RuleStateInput,JobInput
from src.middlewares.auth import current,editor
from src.services.business import audit,dump
from src.services import normalize_service as ns
QUEUE='stage:normalize'
router=APIRouter()

def _enqueue(job_id):
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush(QUEUE,job_id)
 except redis.RedisError:raise HTTPException(503,'队列暂不可用，请恢复后重试该批次')

@router.get('/normalize/meta')
def meta(u=Depends(current),s=Depends(db)):return ns.get_versions(s)

@router.get('/standard-plays')
def standards(u=Depends(current),s=Depends(db)):
 return [dump(p) for p in s.query(StandardPlay).order_by(StandardPlay.id).all()]

@router.post('/standard-plays')
def create_standard(data:StandardPlayInput,u=Depends(editor),s=Depends(db)):
 r=ns.create_standard(s,data);audit(s,u,'新建标准演出 '+r.name);return dump(r)

@router.get('/alias-rules')
def rules(u=Depends(current),s=Depends(db)):
 out=[]
 for r in ns.list_rules(s):
  d=dump(r);d['target_play_name']=s.get(StandardPlay,r.target_play_id).name if r.target_play_id else None
  up=s.get(AliasRule,r.target_rule_id) if r.target_rule_id else None
  d['target_rule_alias']=up.alias_name if up else None
  out.append(d)
 return out

@router.post('/alias-rules')
def create_rule(data:AliasRuleInput,u=Depends(editor),s=Depends(db)):
 r=ns.create_rule(s,data);audit(s,u,f'新建别名规则 #{r.id} {r.alias_name}');return dump(r)

@router.put('/alias-rules/{i}')
def edit_rule(i:int,data:AliasRuleInput,u=Depends(editor),s=Depends(db)):
 r=ns.update_rule(s,i,data);audit(s,u,f'修订别名规则 #{i}');return dump(r)

@router.post('/alias-rules/{i}/state')
def rule_state(i:int,data:RuleStateInput,u=Depends(editor),s=Depends(db)):
 r=ns.set_rule_state(s,i,data.state);audit(s,u,f'规则 #{i} 切换为 {data.state}');return dump(r)

@router.get('/normalize/jobs')
def jobs(u=Depends(current),s=Depends(db)):
 return [dump(j) for j in s.query(NormalizeJob).order_by(NormalizeJob.id.desc()).all()]

@router.get('/normalize/jobs/{i}')
def job_detail(i:int,u=Depends(current),s=Depends(db)):
 j=s.get(NormalizeJob,i)
 if not j:raise HTTPException(404,'归一任务不存在')
 return dump(j)

@router.post('/normalize/jobs')
def create_job(data:JobInput,u=Depends(editor),s=Depends(db)):
 j=ns.create_job(s,data.kind,data.name or ('演出归一批次'));audit(s,u,f'创建归一{ "试算" if j.kind=="trial" else "启用" }批次 #{j.id}')
 _enqueue(j.id);return dump(j)

@router.post('/normalize/jobs/{i}/retry')
def retry_job(i:int,u=Depends(editor),s=Depends(db)):
 j=ns.retry_job(s,i);audit(s,u,f'续跑归一任务 #{i}')
 if j.state=='queued':_enqueue(j.id)
 return dump(j)

@router.get('/normalize/jobs/{i}/isolations')
def isolations(i:int,u=Depends(current),s=Depends(db)):
 j=s.get(NormalizeJob,i)
 if not j:raise HTTPException(404,'归一任务不存在')
 if j.state!='done':raise HTTPException(409,'任务完成后才能查看隔离明细')
 rows=[dump(x) for x in s.query(PlayIsolation).filter_by(job_id=i).order_by(PlayIsolation.id).all()]
 return rows if rows else j.result['isolations']

@router.get('/normalize/jobs/{i}/isolations/export')
def export_isolations(i:int,u=Depends(current),s=Depends(db)):
 j=s.get(NormalizeJob,i)
 if not j:raise HTTPException(404,'归一任务不存在')
 if j.state!='done':raise HTTPException(409,'任务完成后才能下载隔离明细')
 rows=[dump(x) for x in s.query(PlayIsolation).filter_by(job_id=i).order_by(PlayIsolation.id).all()]
 if not rows:rows=j.result['isolations']
 payload={'job_id':i,'kind':j.kind,'summary':j.result['summary'],'isolations':rows}
 return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',
                 headers={'Content-Disposition':f'attachment; filename="play-isolations-{i}.json"'})

@router.get('/settlements/{i}/attribution-chain')
def chain(i:int,u=Depends(current),s=Depends(db)):
 if not s.get(Settlement,i):raise HTTPException(404,'结算场次不存在')
 r=ns.chain_for_settlement(s,i)
 if not r:raise HTTPException(404,'该场次不在当前激活批次的合格归属中（可能被隔离或尚未启用规则）')
 return r
