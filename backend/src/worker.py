import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Pivot
from src.services.analysis import pivot
from src.services.normalize_service import process_job
q=redis.Redis.from_url(os.environ['REDIS_URL'])
def recover():
 with Session() as s:
  for r in s.query(Pivot).filter(Pivot.state.in_(['queued','running'])).all():r.state='queued';q.rpush('stage:pivots',r.id)
  from src.models.entities import NormalizeJob
  for j in s.query(NormalizeJob).filter(NormalizeJob.state.in_(['queued','running'])).all():
   j.state='queued';q.rpush('stage:normalize',j.id)
  s.commit()
recover()
def run_pivot(item):
 with Session() as s:
  r=s.get(Pivot,int(item))
  if not r or r.state!='queued':return
  payload=r.result or {};snapshot=payload.get('snapshot');r.state='running';s.commit()
  try:
   r.result={**pivot(snapshot,r.row_dim,r.col_dim,payload.get('exclusion')),'snapshot':snapshot,'exclusion':payload.get('exclusion')}
   r.state='done';Path('/artifacts/'+str(r.id)+'.json').write_text(json.dumps(r.result,ensure_ascii=False))
  except Exception as e:r.state='failed';r.error=str(e)
  s.commit()
def run_normalize(item):
 with Session() as s:process_job(s,int(item))
HANDLERS={'stage:pivots':run_pivot,'stage:normalize':run_normalize}
while True:
 Path('/tmp/heartbeat').touch()
 try:
  popped=q.blpop(list(HANDLERS.keys()),timeout=3)
  if not popped:continue
  queue,item=popped
  try:HANDLERS[queue](item)
  except Exception:logging.exception('job failed on %s',queue);time.sleep(1)
 except Exception:logging.exception('worker');time.sleep(2)
