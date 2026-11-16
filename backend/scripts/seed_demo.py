import random
from datetime import date,timedelta
from src.config.database import Base,engine,Session
from src.models.entities import User,Settlement,StandardPlay,AliasRule,Meta
from src.utils.security import hash_password
from src.constants.enums import VENUES,CHANNELS,META_RULE_VERSION,META_SETTLEMENT_VERSION
from src.services.normalize_service import now,bump_rule_version
# 归一演示：同一巡演的改名、跨场馆同名、多级指向、循环与交叠歧义
# 基础 180 场使用四个演出原名，为每个原名建立“原名→标准演出”的同场馆规则，保证基础场次合格
PLAY_SEED=[
 ('渡口来信',[('渡口来信','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('渡口来信','河畔小剧场','2026-09-01','2026-12-31','play'),
             ('渡口来信','星光排练厅','2026-09-01','2026-12-31','play'),
             ('渡口来信（巡演版）','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('渡口来信·经典回归','云幕大剧场','2026-11-01','2026-12-31','play'),
             ('DU KOU LAIXIN ENCORE','河畔小剧场','2026-09-01','2026-12-31','play')]),
 ('星河漫游',[('星河漫游','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('星河漫游','河畔小剧场','2026-09-01','2026-12-31','play'),
             ('星河漫游','星光排练厅','2026-09-01','2026-12-31','play'),
             ('星河漫游 2026 升级版','云幕大剧场','2026-09-01','2026-12-31','rule:星河漫游·巡演原名'),
             ('星河漫游·巡演原名','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('星河漫游·巡演原名','河畔小剧场','2026-09-01','2026-12-31','play')]),
 ('一间书房',[('一间书房','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('一间书房','河畔小剧场','2026-09-01','2026-12-31','play'),
             ('一间书房','星光排练厅','2026-09-01','2026-12-31','play')]),
 ('冬日序曲',[('冬日序曲','云幕大剧场','2026-09-01','2026-12-31','play'),
             ('冬日序曲','河畔小剧场','2026-09-01','2026-12-31','play'),
             ('冬日序曲','星光排练厅','2026-09-01','2026-12-31','play')]),
]
# (code, day, venue, 原始演出名, channel偏移, 票款, 退款, 渠道费, 座位, 核验)
EXTRA=[
 ('YM-181','2026-11-02','云幕大剧场','渡口来信（巡演版）',0,120000,8000,8400,800,700),
 ('YM-182','2026-11-03','云幕大剧场','渡口来信·经典回归',0,98000,4000,6580,800,610),
 ('YM-183','2026-11-04','河畔小剧场','DU KOU LAIXIN ENCORE',1,36000,2000,0,240,200),
 ('YM-184','2026-11-05','云幕大剧场','星河漫游 2026 升级版',2,150000,10000,4200,800,760),
 ('YM-185','2026-11-06','河畔小剧场','星河漫游·巡演原名',1,42000,3000,2730,240,210),
 ('YM-186','2026-11-07','星光排练厅','渡口来信（巡演版）',0,18000,0,540,120,90),       # 跨场馆无匹配 → 隔离
 ('YM-187','2026-11-08','云幕大剧场','一场没有规则的新戏',0,26000,1000,0,120,80),       # 无匹配 → 隔离
 ('YM-188','2026-11-09','云幕大剧场','循环名称甲',1,30000,0,900,240,150),               # 循环 → 隔离
 ('YM-189','2026-11-10','云幕大剧场','循环名称乙',1,31000,0,930,240,160),               # 循环链
 ('YM-190','2026-11-11','云幕大剧场','交叠别名',2,22000,500,645,120,100),             # 交叠 → 隔离
 ('YM-191','2026-11-12','云幕大剧场','交叠别名',2,24000,500,705,120,110),             # 交叠歧义
 ('YM-192','2026-10-15','云幕大剧场','渡口来信·经典回归',0,0,0,0,0,0),                  # 窗口外（10月）→ 无匹配隔离
]
def seed():
 Base.metadata.create_all(engine);rng=random.Random(3112)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  for i in range(180):
   code=f'YM-{i+1:03}';seats=[800,240,120][i%3];checked=rng.randint(seats//2,seats);gross=checked*rng.choice([8000,12000,18000]);refund=rng.randint(0,checked//10)*8000;fee=int((gross-refund)*[0,.07,.03][i%3])
   if not s.query(Settlement).filter_by(code=code).first():s.add(Settlement(code=code,day=(date(2026,9,1)+timedelta(days=i//3)).isoformat(),venue=VENUES[i%3],play=['渡口来信','星河漫游','一间书房','冬日序曲'][i%4],channel=CHANNELS[(i//3)%3],gross_cents=gross,refund_cents=refund,fee_cents=fee,seats=seats,checked=checked))
  for code,day,venue,play,ch,gross,refund,fee,seats,checked in EXTRA:
   if not s.query(Settlement).filter_by(code=code).first():
    s.add(Settlement(code=code,day=day,venue=venue,play=play,channel=CHANNELS[ch],gross_cents=gross,refund_cents=refund,fee_cents=fee,seats=seats,checked=checked))
  _seed_normalization(s)
  s.commit();print({'users':s.query(User).count(),'settlements':s.query(Settlement).count(),
                    'standard_plays':s.query(StandardPlay).count(),'alias_rules':s.query(AliasRule).count()})
def _seed_normalization(s):
 if s.query(StandardPlay).count():return
 play_ids={}
 for name,_ in PLAY_SEED:
  p=StandardPlay(name=name,note='归一演示标准演出',created=now());s.add(p);s.flush();play_ids[name]=p.id
 rule_index={}
 def add_rule(alias,venue,start,end,target_play=None,target_rule=None,state='active'):
  r=AliasRule(alias_name=alias,venue=venue,start_day=start,end_day=end,target_play_id=target_play,
              target_rule_id=target_rule,state=state,note='种子规则',version=1,created=now(),updated=now())
  s.add(r);s.flush();rule_index[(venue,alias)]=r;return r
 direct=[(std_name,d) for std_name,defs in PLAY_SEED for d in defs if d[4]=='play']
 linked=[(std_name,d) for std_name,defs in PLAY_SEED for d in defs if d[4]!='play']
 for std_name,(alias,venue,start,end,_) in direct:
  add_rule(alias,venue,start,end,target_play=play_ids[std_name])
 for std_name,(alias,venue,start,end,target) in linked:
  up_alias=target.split(':',1)[1];up=rule_index[(venue,up_alias)]
  add_rule(alias,venue,start,end,target_rule=up.id)
 # 循环规则（绕过状态校验直接置 active，用于演示运行期 cycle 隔离）
 ra=add_rule('循环名称甲','云幕大剧场','2026-09-01','2026-12-31',state='draft')
 rb=add_rule('循环名称乙','云幕大剧场','2026-09-01','2026-12-31',state='draft')
 ra.target_rule_id=rb.id;rb.target_rule_id=ra.id
 ra.state='active';rb.state='active'
 # 交叠歧义：同场馆同名两条生效窗口交叠（保存期校验只拦截 active 交叠，故先建后激活）
 o1=add_rule('交叠别名','云幕大剧场','2026-11-01','2026-11-20',target_play=play_ids['一间书房'],state='draft')
 o2=add_rule('交叠别名','云幕大剧场','2026-11-05','2026-11-25',target_play=play_ids['冬日序曲'],state='draft')
 o1.state='active';o2.state='active'
 s.query(Meta).filter_by(key=META_RULE_VERSION).delete()
 s.query(Meta).filter_by(key=META_SETTLEMENT_VERSION).delete()
 s.flush();bump_rule_version(s)
 m=Meta(key=META_SETTLEMENT_VERSION,value='1');s.add(m)
if __name__=='__main__':seed()
