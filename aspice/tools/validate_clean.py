#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗结果验收校验。"""
import os, re, sys, warnings
import openpyxl
from clean_templates import derive_name, source_files

warnings.filterwarnings('ignore')
OUT = '/workspace/aspice/templates_clean'
KEY = re.compile(r'XXX|张XX|BCM|SYSM_Init')

files = sorted(source_files())
mapping = {derive_name(p)[0]: p for p in files}
outs = [f for f in os.listdir(OUT) if f.endswith('.xlsx')]
print(f'源文件 {len(files)}，输出文件 {len(outs)}')

ok_open = 0
keyword_hits = []
sheet_diff = []
hidden_count = 0
hwe1_ok = sw4_ok = None
moved_total = 0

for name in sorted(mapping):
    src = mapping[name]
    dst = os.path.join(OUT, name)
    if not os.path.exists(dst):
        print('MISSING', name)
        continue
    try:
        wb = openpyxl.load_workbook(dst)
        ok_open += 1
    except Exception as e:
        print('OPEN FAIL', name, e)
        continue
    # ② 关键词
    for ws in wb.worksheets:
        if ws.sheet_state != 'hidden':
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and KEY.search(c.value):
                        keyword_hits.append((name, ws.title, c.coordinate, c.value[:80]))
    if '示例（勿删）' in wb.sheetnames:
        hidden_count += 1
        moved_total += max(wb['示例（勿删）'].max_row - 1, 0)
    # ③ sheet 清单
    wsrc = openpyxl.load_workbook(src)
    src_visible = [w.title for w in wsrc.worksheets if w.sheet_state == 'visible']
    dst_visible = [w.title for w in wb.worksheets if w.sheet_state == 'visible']
    extra = []
    if name == 'HWE.1_硬件需求规格说明书_V1.0.xlsx':
        if dst_visible == src_visible[:4] + ['3.硬件需求', '3.非功能需求'] + src_visible[5:]:
            extra = ['+3.非功能需求', '4.硬件需求→3.硬件需求']
        else:
            sheet_diff.append((name, src_visible, dst_visible))
    elif dst_visible != src_visible:
        sheet_diff.append((name, src_visible, dst_visible))
    print(f'{name:52s} sheets={len(src_visible)}->{len(dst_visible)} '
          f'{"(HWE.1 修正)" if extra else ""}')

# ④ HWE.1
p = os.path.join(OUT, 'HWE.1_硬件需求规格说明书_V1.0.xlsx')
wb = openpyxl.load_workbook(p)
vis = [w.title for w in wb.worksheets if w.sheet_state == 'visible']
order_ok = vis == ['封面', '变更履历', '1.概要', '2.产品介绍', '3.硬件需求', '3.非功能需求', '4.其他']
hdr = [c.value for c in wb['3.非功能需求'][1][:7]]
expect = ['指标ID', '类别(性能·资源·安全)', '指标值', '上限', '测量方法', '验证阶段', '关联需求ID']
hwe1_ok = order_ok and hdr == expect
print('\nHWE.1 可见 sheet 顺序:', vis)
print('HWE.1 3.非功能需求 表头:', hdr, '=>', 'PASS' if hwe1_ok else 'FAIL')

# ④ SWE.4 附4
p = os.path.join(OUT, 'SWE.4_软件单元验证报告_V1.0.xlsx')
wb = openpyxl.load_workbook(p)
ws = wb['附4.工作量统计']
bad = []
for r in range(3, 19):
    v = ws[f'G{r}'].value
    if isinstance(v, str) and v.startswith('=') and 'IF(' not in v.upper():
        bad.append(f'G{r}={v}')
    if isinstance(v, str) and v.startswith('#DIV'):
        bad.append(f'G{r}={v}')
cached = openpyxl.load_workbook(p, data_only=True)['附4.工作量统计']
badc = [f'G{r}' for r in range(3, 19) if isinstance(cached[f'G{r}'].value, str)
        and cached[f'G{r}'].value.startswith('#DIV')]
sw4_ok = not bad and not badc
print('SWE.4 附4 G3:G18 公式:', [ws[f'G{r}'].value for r in (3, 5, 17, 18)])
print('SWE.4 附4 #DIV/0! 残留:', badc or '无', '=>', 'PASS' if sw4_ok else 'FAIL')

print('\n' + '=' * 70)
print(f'① 可打开：{ok_open}/{len(mapping)}  ' + ('PASS' if ok_open == len(mapping) else 'FAIL'))
print(f'② 正文示例关键词命中：{len(keyword_hits)}  ' + ('PASS' if not keyword_hits else 'FAIL'))
for h in keyword_hits[:20]:
    print('   ', h)
print(f'③ sheet 清单差异：{len(sheet_diff)}  ' + ('PASS' if not sheet_diff else 'FAIL'))
for d in sheet_diff:
    print('   ', d)
print(f'④ HWE.1 修正：{"PASS" if hwe1_ok else "FAIL"}；SWE.4 附4：#{"PASS" if sw4_ok else "FAIL"}')
print(f'隐藏示例页文件数：{hidden_count}，迁出示例单元格：{moved_total}')
