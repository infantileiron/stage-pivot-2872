from pydantic import BaseModel,Field,model_validator
from typing import Literal,Optional
from datetime import date
Dimension=Literal['venue','play','nplay','channel','month']
class Login(BaseModel):email:str;password:str
class SettlementInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 day:date
 venue:Literal['云幕大剧场','河畔小剧场','星光排练厅']
 play:str=Field(min_length=1,max_length=60)
 channel:Literal['剧院直营','票务合作','团体专场']
 gross_cents:int=Field(ge=0,le=100000000)
 refund_cents:int=Field(ge=0,le=100000000)
 fee_cents:int=Field(ge=0,le=100000000)
 seats:int=Field(ge=0,le=10000)
 checked:int=Field(ge=0,le=10000)
 @model_validator(mode='after')
 def consistent(self):
  if self.refund_cents+self.fee_cents>self.gross_cents:raise ValueError('退款与渠道费合计不得超过票款')
  if self.checked>self.seats:raise ValueError('核验人数不得超过座位数')
  return self
class PivotInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 row_dim:Dimension='venue'
 col_dim:Dimension='channel'
 normalize_job_id:Optional[int]=Field(default=None,gt=0)
 @model_validator(mode='after')
 def dimensions_differ(self):
  if self.row_dim==self.col_dim:raise ValueError('行列维度不能相同')
  return self
 @model_validator(mode='after')
 def nplay_needs_batch(self):
  if 'nplay' in (self.row_dim,self.col_dim) and not self.normalize_job_id:
   raise ValueError('标准演出维度必须指定一个已激活的归一批次')
  return self
class StandardPlayInput(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 note:str=Field(default='',max_length=500)
class AliasRuleInput(BaseModel):
 alias_name:str=Field(min_length=1,max_length=120)
 venue:Literal['云幕大剧场','河畔小剧场','星光排练厅']
 start_day:date
 end_day:date
 target_play_id:Optional[int]=Field(default=None,gt=0)
 target_rule_id:Optional[int]=Field(default=None,gt=0)
 note:str=Field(default='',max_length=500)
 @model_validator(mode='after')
 def window_and_target(self):
  if self.start_day>self.end_day:raise ValueError('生效起始日期不得晚于截止日期')
  if bool(self.target_play_id)==bool(self.target_rule_id):raise ValueError('必须且只能选择一种指向：标准演出或上级规则')
  return self
class RuleStateInput(BaseModel):
 state:Literal['draft','active']
class JobInput(BaseModel):
 kind:Literal['trial','activate']='trial'
 name:str=Field(default='',max_length=120)
class ReviewInput(BaseModel):
 pivot_id:int=Field(gt=0)
 row_key:str=Field(min_length=1,max_length=100)
 col_key:str=Field(min_length=1,max_length=100)
 expected_cents:int=Field(ge=0,le=1000000000000)
 note:str=Field(min_length=8,max_length=2000)
class ReviewEdit(BaseModel):
 expected_cents:int=Field(ge=0,le=1000000000000)
 note:str=Field(min_length=8,max_length=2000)
