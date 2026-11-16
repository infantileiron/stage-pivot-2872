import os, tempfile
_tmp=tempfile.NamedTemporaryFile(suffix='.db',delete=False);_tmp.close()
os.environ['JWT_SECRET']='test-secret'
os.environ['DATABASE_URL']='sqlite:///'+_tmp.name
os.environ['REDIS_URL']='redis://fake:6379/0'
import pytest
from fastapi.testclient import TestClient
from src.config.database import Session,Base,engine
from src.models.entities import User,Pivot,NormalizeJob
from src.utils.security import hash_password
from src.services import normalize_service as ns
from src.services.analysis import pivot as run_pivot
import src.routes.normalize as nr
import src.routes.api as ar

class FakeRedis:
 def rpush(self,queue,value):
  with Session() as s:
   if queue=='stage:normalize':ns.process_job(s,int(value))
   elif queue=='stage:pivots':
    r=s.get(Pivot,int(value));payload=r.result or {}
    r.result={**run_pivot(payload['snapshot'],r.row_dim,r.col_dim,payload.get('exclusion')),
              'snapshot':payload['snapshot'],'exclusion':payload.get('exclusion')};r.state='done';s.commit()
 def ping(self):return True

FAKE=FakeRedis()
nr.redis.Redis.from_url=lambda *a,**k:FAKE
ar.redis.Redis.from_url=lambda *a,**k:FAKE
from src.main import app

@pytest.fixture(scope='module')
def client():
 Base.metadata.create_all(engine)
 with Session() as s:
  if not s.query(User).filter_by(email='admin@demo.local').first():
   s.add(User(email='admin@demo.local',role='admin',password=hash_password('Demo123!')))
   s.add(User(email='viewer@demo.local',role='viewer',password=hash_password('Demo123!')));s.commit()
 with TestClient(app) as c:yield c

@pytest.fixture()
def admin(client):
 r=client.post('/auth/login',json={'email':'admin@demo.local','password':'Demo123!'});assert r.status_code==200
 client.headers['Authorization']='Bearer '+r.json()['token'];return client

def test_viewer_cannot_write(client):
 r=client.post('/auth/login',json={'email':'viewer@demo.local','password':'Demo123!'})
 h={'Authorization':'Bearer '+r.json()['token']}
 assert client.post('/standard-plays',json={'name':'X'},headers=h).status_code==403

def test_full_normalize_flow_and_pivot(admin):
 # 标准演出 + 规则（一级 + 多级）
 sp=admin.post('/standard-plays',json={'name':'旗舰大戏'}).json()
 r1=admin.post('/alias-rules',json={'alias_name':'曾用名甲','venue':'云幕大剧场','start_day':'2026-09-01',
   'end_day':'2026-12-31','target_play_id':sp['id']}).json()
 r2=admin.post('/alias-rules',json={'alias_name':'曾用名乙','venue':'云幕大剧场','start_day':'2026-09-01',
   'end_day':'2026-12-31','target_rule_id':r1['id']}).json()
 admin.post(f"/alias-rules/{r1['id']}/state",json={'state':'active'})
 admin.post(f"/alias-rules/{r2['id']}/state",json={'state':'active'})
 # 场次：两个可归一 + 一个无匹配
 base=dict(venue='云幕大剧场',channel='剧院直营',gross_cents=10000,refund_cents=500,fee_cents=300,seats=100,checked=80)
 admin.post('/settlements',json={**base,'code':'T-001','day':'2026-11-01','play':'曾用名甲'})
 admin.post('/settlements',json={**base,'code':'T-002','day':'2026-11-02','play':'曾用名乙'})
 admin.post('/settlements',json={**base,'code':'T-003','day':'2026-11-03','play':'没有规则的戏'})
 # 试算（入队由假 Redis 同步处理，响应体在入队前序列化，故重新拉取最终状态）
 created=admin.post('/normalize/jobs',json={'kind':'trial','name':'试算'}).json()
 trial=admin.get(f"/normalize/jobs/{created['id']}").json()
 assert trial['state']=='done'
 body=trial['result'];assert body['summary']['matched_count']==2 and body['summary']['isolated_count']==1
 assert body['summary']['source_count']==3
 # 启用
 created=admin.post('/normalize/jobs',json={'kind':'activate','name':'启用'}).json()
 job=admin.get(f"/normalize/jobs/{created['id']}").json()
 assert job['state']=='done' and job['result'].get('activated') is True
 assert admin.get('/normalize/meta').json()['active_job_id']==job['id']
 # 归属链解释
 sid=admin.get('/settlements').json()
 t2=next(x for x in sid if x['code']=='T-002')
 chain=admin.get(f"/settlements/{t2['id']}/attribution-chain").json()
 assert chain['standard_play']=='旗舰大戏' and len(chain['chain'])==2
 # 隔离明细与下载
 iso=admin.get(f"/normalize/jobs/{job['id']}/isolations").json()
 assert len(iso)==1 and iso[0]['reason']=='no_match'
 dl=admin.get(f"/normalize/jobs/{job['id']}/isolations/export")
 assert dl.status_code==200 and 'attachment' in dl.headers['content-disposition']
 assert dl.json()['summary']['isolated_net_cents']==10000-500-300
 # 透视只用合格批次并注明排除
 pv0=admin.post('/pivots',json={'name':'归一透视','row_dim':'nplay','col_dim':'channel',
                               'normalize_job_id':job['id']}).json()
 pv=admin.get('/pivots/'+str(pv0['id'])).json()
 assert pv['state']=='done'
 res=pv['result'];assert res['total']['count']==2
 assert '隔离 1 场' in res['method'] and res['exclusion']['isolated_count']==1
 assert res['total']['net_cents']+res['exclusion']['isolated_net_cents']==3*(10000-500-300)
 # 无批次的 nplay 维度被拒绝
 bad=admin.post('/pivots',json={'name':'X','row_dim':'nplay','col_dim':'channel'})
 assert bad.status_code in (422,400)

def test_stale_activate_is_rejected(admin):
 sp=admin.post('/standard-plays',json={'name':'过期戏'}).json()
 r=admin.post('/alias-rules',json={'alias_name':'过期别名','venue':'河畔小剧场','start_day':'2026-09-01',
   'end_day':'2026-12-31','target_play_id':sp['id']}).json()
 admin.post(f"/alias-rules/{r['id']}/state",json={'state':'active'})
 admin.post('/settlements',json={'code':'T-100','day':'2026-11-05','venue':'河畔小剧场','play':'过期别名',
   'channel':'剧院直营','gross_cents':1000,'refund_cents':0,'fee_cents':0,'seats':10,'checked':8})
 # 直接造一个排队任务，再推进规则版本后处理
 with Session() as s:
  j=ns.create_job(s,'activate','过期启用');jid=j.id
  ns.bump_rule_version(s)
  ns.process_job(s,jid)
 got=admin.get(f'/normalize/jobs/{jid}').json()
 assert got['state']=='failed' and '版本过期' in got['error']
 # 续跑：重新入队仍是旧版本 → 仍失败，且无重复归属
 admin.post(f'/normalize/jobs/{jid}/retry')
 rr=admin.get(f'/normalize/jobs/{jid}').json()
 assert rr['state']=='failed'
