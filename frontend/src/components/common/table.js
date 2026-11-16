import {esc} from '../../utils/html.js';
// 单元格传入 {html:'...'} 时原样渲染，其余按文本转义
const cell=v=>v&&typeof v==='object'&&'html' in v?v.html:esc(v);
export function table(headers,rows){return `<div class=scroll><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${cell(v)}</td>`).join('')}</tr>`).join('')||'<tr><td>暂无记录。请在右侧录入首条数据。</td></tr>'}</tbody></table></div>`}
