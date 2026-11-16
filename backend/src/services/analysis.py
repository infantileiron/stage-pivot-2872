import json,hashlib
DIMENSIONS={'venue','play','nplay','channel','month'}
SUMS=('gross_cents','refund_cents','fee_cents','seats','checked')
def key(row,dim):
 if dim=='month':return row['day'][:7]
 if dim=='nplay':return row.get('nplay') or '（未归一）'
 return row[dim]
def aggregate(rows):
 out={k:sum(r[k] for r in rows) for k in SUMS};out['count']=len(rows)
 out['net_cents']=out['gross_cents']-out['refund_cents']-out['fee_cents']
 out['occupancy']=out['checked']/out['seats'] if out['seats'] else None
 return out
def pivot(rows,row_dim,col_dim,exclusion=None):
 if row_dim not in DIMENSIONS or col_dim not in DIMENSIONS or row_dim==col_dim:raise ValueError('请选择两个不同的白名单维度')
 if not rows:raise ValueError('没有合格结算记录：归一批次的场次均被隔离，请先处理隔离明细')
 if len({r['code'] for r in rows})!=len(rows):raise ValueError('场次编号重复，无法保证结算守恒')
 row_keys=sorted({key(r,row_dim) for r in rows});col_keys=sorted({key(r,col_dim) for r in rows})
 cells=[{'row_key':a,'col_key':b,**aggregate([r for r in rows if key(r,row_dim)==a and key(r,col_dim)==b])} for a in row_keys for b in col_keys]
 row_totals=[{'key':a,**aggregate([r for r in rows if key(r,row_dim)==a])} for a in row_keys]
 col_totals=[{'key':b,**aggregate([r for r in rows if key(r,col_dim)==b])} for b in col_keys]
 total=aggregate(rows)
 conserved=all(sum(x[k] for x in cells)==sum(x[k] for x in row_totals)==sum(x[k] for x in col_totals)==total[k] for k in (*SUMS,'net_cents','count'))
 if not conserved:raise ValueError('行列总计不守恒，请核对输入')
 method='金额以整数分求和；净结算=票款−退款−渠道费。上座率=总核验人数/总座位，零座位显示未定义；不平均各场百分比。每条为独立场次，渠道是主售票渠道，不拆分同场座位。月份按业务日期YYYY-MM；下钻始终读取冻结快照。'
 if exclusion:
  method+=' 本透视仅使用归一合格批次 #%s 的 %d 场；隔离 %d 场、净额 %d 分已排除（票款 %d / 退款 %d / 渠道费 %d，单位分），合格与隔离合计等于来源。'%(
   exclusion['job_id'],exclusion['matched_count'],exclusion['isolated_count'],exclusion['isolated_net_cents'],
   exclusion['isolated_gross_cents'],exclusion['isolated_refund_cents'],exclusion['isolated_fee_cents'])
 return dict(row_keys=row_keys,col_keys=col_keys,cells=cells,row_totals=row_totals,col_totals=col_totals,total=total,
  conserved=conserved,exclusion=exclusion,
  checksum=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),method=method)
