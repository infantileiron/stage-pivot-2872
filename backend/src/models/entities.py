from sqlalchemy import Column,Integer,BigInteger,String,JSON,Text,ForeignKey,UniqueConstraint,Index
from src.config.database import Base

class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True,nullable=False);password=Column(String(200));role=Column(String(20))

class Settlement(Base):
 __tablename__='settlements'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);day=Column(String(10));venue=Column(String(40));play=Column(String(60));channel=Column(String(30));gross_cents=Column(BigInteger);refund_cents=Column(BigInteger);fee_cents=Column(BigInteger);seats=Column(Integer);checked=Column(Integer);updated_at=Column(String(40))

class Pivot(Base):
 __tablename__='pivots'
 id=Column(Integer,primary_key=True);name=Column(String(100));row_dim=Column(String(30));col_dim=Column(String(30));state=Column(String(20),default='queued');result=Column(JSON,nullable=True);error=Column(Text,default='');normalize_job_id=Column(Integer,nullable=True)

class Review(Base):
 __tablename__='reviews'
 id=Column(Integer,primary_key=True);pivot_id=Column(Integer,ForeignKey('pivots.id'));row_key=Column(String(100));col_key=Column(String(100));book_cents=Column(BigInteger);expected_cents=Column(BigInteger);difference_cents=Column(BigInteger);note=Column(Text);status=Column(String(20),default='draft')

class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))

class StandardPlay(Base):
 __tablename__='standard_plays'
 id=Column(Integer,primary_key=True);name=Column(String(120),unique=True,nullable=False);note=Column(Text,default='');created=Column(String(40))

class AliasRule(Base):
 __tablename__='alias_rules'
 id=Column(Integer,primary_key=True)
 alias_name=Column(String(120),nullable=False)
 venue=Column(String(40),nullable=False)
 start_day=Column(String(10),nullable=False)
 end_day=Column(String(10),nullable=False)
 target_play_id=Column(Integer,ForeignKey('standard_plays.id'),nullable=True)
 target_rule_id=Column(Integer,ForeignKey('alias_rules.id'),nullable=True)
 state=Column(String(20),default='draft')
 note=Column(Text,default='')
 version=Column(Integer,default=1)
 created=Column(String(40));updated=Column(String(40))
 __table_args__=(Index('ix_alias_lookup','venue','alias_name'),)

class NormalizeJob(Base):
 __tablename__='normalize_jobs'
 id=Column(Integer,primary_key=True)
 name=Column(String(120))
 kind=Column(String(20),default='trial')
 state=Column(String(20),default='queued')
 rule_version=Column(BigInteger,default=0)
 settlement_version=Column(BigInteger,default=0)
 current_rule_version=Column(BigInteger,default=0)
 current_settlement_version=Column(BigInteger,default=0)
 result=Column(JSON,nullable=True)
 error=Column(Text,default='')
 created=Column(String(40));finished=Column(String(40),nullable=True)

class PlayAttribution(Base):
 __tablename__='play_attributions'
 id=Column(Integer,primary_key=True)
 job_id=Column(Integer,ForeignKey('normalize_jobs.id'),nullable=False)
 settlement_id=Column(Integer,ForeignKey('settlements.id'),nullable=False)
 code=Column(String(60),nullable=False)
 original_play=Column(String(120),nullable=False)
 standard_play_id=Column(Integer,ForeignKey('standard_plays.id'),nullable=False)
 standard_play=Column(String(120),nullable=False)
 chain=Column(JSON,nullable=False)
 __table_args__=(UniqueConstraint('job_id','settlement_id',name='uq_attr_job_settlement'),)

class PlayIsolation(Base):
 __tablename__='play_isolations'
 id=Column(Integer,primary_key=True)
 job_id=Column(Integer,ForeignKey('normalize_jobs.id'),nullable=False)
 settlement_id=Column(Integer,ForeignKey('settlements.id'),nullable=False)
 code=Column(String(60),nullable=False)
 original_play=Column(String(120),nullable=False)
 venue=Column(String(40));day=Column(String(10))
 reason=Column(String(30),nullable=False)
 detail=Column(Text,default='')
 gross_cents=Column(BigInteger,default=0);refund_cents=Column(BigInteger,default=0);fee_cents=Column(BigInteger,default=0);net_cents=Column(BigInteger,default=0)
 __table_args__=(UniqueConstraint('job_id','settlement_id',name='uq_iso_job_settlement'),)

class Meta(Base):
 __tablename__='meta_kv'
 id=Column(Integer,primary_key=True)
 key=Column(String(60),unique=True,nullable=False)
 value=Column(String(120),default='')
