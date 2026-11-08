#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASPICE 4.0 CL2 模板清洗：生成可直接填写的 V1.0 填写版。"""
import os, re, shutil, warnings, datetime
from copy import copy
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

warnings.filterwarnings('ignore')

ROOT = '/workspace/aspice/_source_templates'
OUT = '/workspace/aspice/templates_clean'
PLACEHOLDER = '待填写（按 00_文件编号与命名规则 生成）'

# ---------------------------------------------------------------- 文件命名

def derive_name(path):
    """返回 (目标文件名, 过程域, 文档名)。"""
    stem = os.path.basename(path)[:-5]
    parent = os.path.basename(os.path.dirname(path))
    m = re.search(r'_V\d+(?:\.\d+)?$', stem)
    if m:
        stem = stem[:m.start()]
    if stem.startswith('亚远景_'):
        stem = stem[len('亚远景_'):]

    domain, doc = None, stem
    m = re.match(r'^(SYS|SWE|HWE)(\d+)_', stem)
    if m:
        domain = f'{m.group(1)}.{m.group(2)}'
        doc = stem[m.end():]
    else:
        m = re.match(r'^(MAN|SUP)(\.?\d+)_', stem)
        if m:
            domain = f'{m.group(1)}.{m.group(2).lstrip(".")}'
            doc = stem[m.end():]
        elif stem.startswith('ENG_'):
            domain = 'ENG'
            doc = stem[4:]
    if doc.startswith('TP_'):
        doc = doc[3:]
    if domain is None:
        # 无前缀文件按所在目录归档（SUP.10 / SUP.1 等）
        m = re.search(r'(SYS|SWE|HWE|MAN|SUP)\.(\d+)', parent)
        domain = f'{m.group(1)}.{m.group(2)}' if m else 'ENG'
        doc = stem
    return f'{domain}_{doc}_V1.0.xlsx', domain, doc


def source_files():
    for dp, dn, fn in os.walk(ROOT):
        for f in sorted(fn):
            if f.lower().endswith('.xlsx') and not f.startswith('~$'):
                yield os.path.join(dp, f)


# ---------------------------------------------------------------- 示例数据规则

PERSON = re.compile(r'^(张|李|王|赵|刘)[XxＸ]{1,3}$')
DATE_STR = re.compile(r'^\s*(19|20)\d{2}\s*[-/.年]')
DATE_FULL = re.compile(r'^\s*(19|20)\d{2}([-/.]\d{1,2}|年\d{1,2}月?|年\s*$)')
DEMO_MARK = re.compile(r'BCM|RGB模组|无线充电|LIN主节点|LIN总线|LIN命令|DC-AY-|SYSM|'
                       r'12V电源系统|B30平台|PHEV|广汽|银基|AY3_|蓝牙数字钥匙|电池温度保护', re.I)
KEYWORD = re.compile(r'XXX|张XX|李XX|BCM|SYSM_Init', re.I)
PLACEHOLDER_TOKEN = re.compile(r'[XxＸ]{2,}')

# 显式清理范围：文件名 -> {sheet: [range, ...]}
CLEAR_RANGES = {
    'ENG_TP_测试报告_V1.0.xlsx': {
        '2.测试汇总结果': ['B5:S22'],
        '3.测试分析报告': ['B4:G4', 'B8:G8', 'C12:G12', 'F13:G16'],
        '附2.测试结果': ['F4:F5', 'P4:R5', 'Y4:AA5', 'AH4:AJ5', 'AQ4:AS5'],
        '附3.工作量统计': ['D3:H4'],
    },
    '亚远景_SWE4_TP_软件单元验证报告_V1.0.xlsx': {
        '2.单元测试汇总结果': ['B5:S22'],
        '3.单元测试分析报告': ['B10:G10', 'C14:F14', 'F15:F18'],
        '附3.单元测试结果': ['G4:G5', 'Q4:R5', 'Z4:AA5', 'AI4:AJ5', 'AR4:AS5'],
        '附4.工作量统计': ['D3:H4'],
    },
    'SWE1_TP_软件需求规格说明书_V1.0.xlsx': {
        '2.产品介绍': ['B3', 'B19:H22'],
        '3.软件需求': ['B4:T5'],
    },
    'SWE2_TP_软件架构设计说明书_V1.0.xlsx': {
        '4.组件接口设计': ['C2', 'C4:C7', 'D8', 'J8', 'D10', 'D14', 'D17', 'J17',
                         'D23', 'F23', 'H23', 'I23', 'K23'],
        '5.软件动态架构设计': ['C21:C26'],
        '6.非功能性需求设计': ['B4:N4'],
        '7.软件控制策略': ['B13:N13', 'B22', 'D22', 'B33:N33'],
        '9.软件架构评估': ['B3', 'B13:P13', 'B25'],
    },
    'SWE3_TP_软件详细设计说明书_V1.1.xlsx': {
        '3.软件组件设计': ['H23'],
        '4.组件函数设计': ['E14:E15', 'E28:E29'],
    },
    '亚远景_SYS2_TP_系统需求规格说明书_V1.0.xlsx': {
        'Cvoer 封面': ['E3'],
        '2.产品介绍': ['B3', 'B19:H22'],
        '3.系统需求': ['B4:T5'],
    },
    '亚远景_SYS3_TP_系统架构设计说明书_V1.0.xlsx': {
        '2.制约条件': ['J4:M10'],
        '4.接口设计': ['B22:O31'],
        '5.系统动态架构设计': ['B10:C17', 'C21:C29'],
        '7.系统架构分析': ['B3', 'B13:P13', 'B25'],
    },
    '亚远景_HWE1_TP_硬件需求规格说明书_V1.0.xlsx': {
        '2.产品介绍': ['B3', 'B19:H21'],
        '4.硬件需求': ['B4:W9'],
    },
    '亚远景_HWE2_TP_硬件设计说明书_V0.1.xlsx': {
        '2.硬件架构设计': ['B13:H13', 'B21:H21', 'B37:H37', 'B54:C61', 'B63:C63', 'I52'],
        '4.硬件设计评估': ['B3', 'B13:P13', 'B25'],
    },
    '亚远景_MAN3_TP_项目人力资源投入表_V0.1.xlsx': {
        '人力资源投入表': ['D2:S2', 'B4:B6'],
    },
    '亚远景_MAN3_TP_项目管理计划_V1.3.xlsx': {
        '项目管理计划总览': ['B27', 'D27', 'K27', 'E31:E32', 'K41:K43', 'C53:L57'],
    },
    '亚远景_SUP1_TP_不符合项跟踪表_V1.2.xlsx': {
        '不符合项跟踪表': ['C2:P2', 'C4:Q6'],
        '不符合项图表分析': ['C28:I41'],
    },
    '亚远景_SUP1_TP_质量升级报告_V1.2.xlsx': {
        '升级报告': ['C4:N4', 'C5:L5', 'C9:N10'],
    },
    '亚远景_SUP1_TP_质量月报_V1.3.xlsx': {
        '附1-质量审计情况': ['C5', 'C8', 'F6:L10'],
        '附2-工作产品评审情况': ['F5:I35', 'F39:I40'],
        '附3-BUG情况': ['E5:G8'],
        '附4-客诉问题情况': ['C5:C10', 'D5:H10'],
        '附5-NC趋势': ['C6:Z10'],
        '附6-评审问题趋势': ['C6:Z8'],
        '附7-BUG趋势': ['C6:Z9'],
        '附8-客诉问题趋势': ['C6:Z10'],
    },
    '项目变更跟踪表_V0.3.xlsx': {
        '项目变更跟踪表': ['B5:V5', 'L6:M12'],
    },
    '亚远景_SUP8_TP_项目配置管理计划_V1.6.xlsx': {
        '项目配置管理计划': ['N68'],
    },
}

# 显式清空（封面/标题类）单元格
CLEAR_CELLS = {
    '亚远景_SUP1_TP_质量月报_V1.3.xlsx': [('xxx质量月报', 'B58'), ('xxx质量月报', 'B27'),
                                          ('xxx质量月报', 'B33'), ('xxx质量月报', 'B1')],
    '亚远景_SUP9_TP_问题解决管理计划_V1.3.xlsx': [('1.概要', 'L13')],
    '亚远景_SUP8_TP_项目配置管理计划_V1.6.xlsx': [('项目配置管理计划', 'N68')],
}

# 标题/章节占位词：用清理后的标题替换（不搬离）
TITLE_FIXES = {
    'ENG_TP_测试报告_V1.0.xlsx': [('封面', 'B7', '测试报告')],
    '亚远景_ENG_TP_测试规范_V1.0.xlsx': [('封面', 'B7', '测试规范')],
    '亚远景_MAN3_TP_项目周报_V1.0.xlsx': [('周报', 'B2', '项目周报')],
    '亚远景_MAN3_TP_项目里程碑报告_V1.0.xlsx': [('xxx里程碑审查报告', 'B1', '里程碑报告')],
    '亚远景_SUP1_TP_质量月报_V1.3.xlsx': [('xxx质量月报', 'B1', '质量月报')],
}


# ---------------------------------------------------------------- 工具函数

def clear_range(ws, rng, records):
    target = ws[rng]
    if hasattr(target, 'coordinate'):
        cells = [target]
    else:
        cells = [c for row in target for c in (row if isinstance(row, tuple) else (row,))]
    for c in cells:
        if c.value is not None and not (isinstance(c.value, str) and c.value.strip() == ''):
            records.append((ws.title, c.coordinate, c.value))
            c.value = None
            if getattr(c, 'hyperlink', None) is not None:
                c.hyperlink = None


def sanitize_text(text):
    """去除/替换占位符，返回新文本；空串表示应清空。"""
    t = text
    t = re.sub(r'\[[XxＸ]{2,}人名\]', '', t)
    if len(t) > 30:
        t = PLACEHOLDER_TOKEN.sub('待填写', t)
    else:
        t = PLACEHOLDER_TOKEN.sub('', t)
        t = re.sub(r'\s{2,}', ' ', t).strip(' -_、')
    return t


def sanitize_cell(cell):
    if isinstance(cell.value, str):
        new = sanitize_text(cell.value)
        cell.value = new if new else None


def is_sample_value(val):
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return False
        if PERSON.match(s):
            return True
        if DATE_STR.match(s) and len(s) <= 24:
            return True
        if 'DC-AY-' in s or 'SYSM' in s:
            return True
        if KEYWORD.search(s):
            return True
    return False


def set_cover(wb, records):
    for ws in wb.worksheets:
        if '封面' not in ws.title and 'Cvoer' not in ws.title:
            continue
        for row in ws.iter_rows(min_row=1, max_row=12):
            for c in row:
                if not isinstance(c.value, str):
                    continue
                s = c.value.strip()
                if len(s) > 16:
                    continue
                compact = s.replace(' ', '')
                is_no = compact.startswith('文件编号') or 'DucNo' in compact
                is_ver = compact in ('版本：', '版本:', 'Version版本：', 'Version')
                if not (is_no or is_ver):
                    continue
                tgt = ws.cell(row=c.row, column=c.column + 1)
                if tgt.value is not None:
                    records.append((ws.title, tgt.coordinate, tgt.value))
                tgt.value = PLACEHOLDER
        return True
    return False


def add_hidden_examples(wb, records):
    if not records:
        return
    ws = wb.create_sheet('示例（勿删）')
    ws.sheet_state = 'hidden'
    headers = ['原Sheet', '原单元格', '原值']
    ws.append(headers)
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='D9E1F2')
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                             top=Side(style='thin'), bottom=Side(style='thin'))
    for r in records:
        ws.append([r[0], r[1], str(r[2]) if not isinstance(r[2], (int, float)) else r[2]])
    for i, w in enumerate([24, 12, 60], 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def fix_hwe1(wb, records):
    """HWE.1：4.硬件需求 → 3.硬件需求；插入 3.非功能需求。"""
    src = wb['4.硬件需求']
    src.title = '3.硬件需求'
    headers = ['指标ID', '类别(性能·资源·安全)', '指标值', '上限',
               '测量方法', '验证阶段', '关联需求ID']
    ws = wb.create_sheet('3.非功能需求')
    idx = wb.sheetnames.index('3.硬件需求') + 1
    wb._sheets.insert(idx, wb._sheets.pop())
    # 沿用 3.硬件需求 表头样式
    ref = src['B2']
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = copy(ref.font)
        c.fill = copy(ref.fill)
        c.border = copy(ref.border)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = [16, 22, 18, 14, 26, 14, 18][col - 1]
    ws.row_dimensions[1].height = 30
    for r in range(2, 21):
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=r, column=col)
            c.border = copy(ref.border)
            c.alignment = Alignment(vertical='center', wrap_text=True,
                                    horizontal='left' if col > 3 else 'center')
    ws.freeze_panes = 'A2'
    ws.sheet_view.showGridLines = True


def fix_swe4_workload(wb):
    ws = wb['附4.工作量统计']
    for r in range(3, 18):
        ws[f'G{r}'] = f'=IF(D{r}=0,"",(E{r}-D{r})/D{r})'
    ws['G18'] = '=IF(D18=0,"",F18/D18)'


def fix_error_formulas(wb, cached_wb):
    """把缓存值为 #DIV/0! 的公式统一包 IFERROR(...,"")。"""
    for ws in wb.worksheets:
        cws = cached_wb[ws.title] if ws.title in cached_wb.sheetnames else None
        for row in ws.iter_rows():
            for c in row:
                if not isinstance(c.value, str) or not c.value.startswith('='):
                    continue
                cv = cws[c.coordinate].value if cws is not None else None
                if isinstance(cv, str) and cv.startswith('#DIV/0'):
                    c.value = '=IFERROR(' + c.value[1:] + ',"")'


# ---------------------------------------------------------------- 上游列补齐
UPSTREAM_HEADER = '上游元素\nUpstream Element'
_HEADER_KEYWORDS = (
    'id', '标识', '编号', '编码', 'identifier', '下游', 'downstream',
    '测试用例', 'testcase', '上游', 'upstream', '来源', 'source',
    '标题', 'title', '需求', '描述', '类型', '状态', '备注', 'remark', '目标',
)


def _norm_header(value):
    return re.sub(r'\s+', '', str(value)).lower() if value is not None else ''


def _find_header_row(ws):
    best_row, best_score = None, 0
    for r in range(1, min(ws.max_row or 0, 20) + 1):
        score = sum(
            1 for c in range(1, ws.max_column + 1)
            if any(k in _norm_header(ws.cell(row=r, column=c).value)
                   for k in _HEADER_KEYWORDS)
        )
        if score >= 3 and score > best_score:
            best_row, best_score = r, score
    return best_row


def _col_width(ws, index):
    dim = ws.column_dimensions.get(get_column_letter(index))
    return dim.width if dim is not None else None


def add_upstream_column(wb):
    """在「下游元素」左侧插入「上游元素」列，形成双向追溯结构。

    同步处理列宽、合并单元格与数据验证范围；对已存在上游列的清单跳过。
    返回处理的清单数量。
    """
    changed = 0
    for ws in wb.worksheets:
        if ws.sheet_state != 'visible':
            continue
        header_row = _find_header_row(ws)
        if header_row is None:
            continue
        max_col = ws.max_column or 0
        headers = [_norm_header(ws.cell(row=header_row, column=c).value)
                   for c in range(1, max_col + 1)]
        if any('上游' in h or 'upstream' in h for h in headers):
            continue

        downstream_col = next(
            (i + 1 for i, h in enumerate(headers)
             if '下游' in h or 'downstream' in h),
            None,
        )
        if downstream_col is not None:
            insert_at = downstream_col
        elif '详设' in ws.title or '详细设计' in ws.title:
            insert_at = min(4, max_col)
        else:
            insert_at = max_col + 1

        old_widths = {i: _col_width(ws, i) for i in range(insert_at, max_col + 1)}
        merges = [(m.min_row, m.min_col, m.max_row, m.max_col)
                  for m in ws.merged_cells.ranges]
        for min_row, min_col, max_row, max_col_ in merges:
            ws.unmerge_cells(start_row=min_row, start_column=min_col,
                             end_row=max_row, end_column=max_col_)

        ws.insert_cols(insert_at)

        # 列宽随插入列右移
        for i in range(max_col, insert_at - 1, -1):
            letter = get_column_letter(i + 1)
            if old_widths[i] is None:
                ws.column_dimensions.pop(letter, None)
            else:
                ws.column_dimensions[letter].width = old_widths[i]
        if old_widths[insert_at] is None:
            ws.column_dimensions.pop(get_column_letter(insert_at), None)
        else:
            ws.column_dimensions[get_column_letter(insert_at)].width = old_widths[insert_at]

        # 合并范围随插入列扩展
        for min_row, min_col, max_row, max_col_ in merges:
            if min_col >= insert_at:
                min_col += 1
                max_col_ += 1
            elif max_col_ >= insert_at:
                max_col_ += 1
            ws.merge_cells(start_row=min_row, start_column=min_col,
                           end_row=max_row, end_column=max_col_)

        # 数据验证范围随插入列右移
        for dv in list(ws.data_validations.dataValidation):
            parts = []
            for rng in dv.sqref.ranges:
                min_col = rng.min_col + 1 if rng.min_col >= insert_at else rng.min_col
                max_col_ = rng.max_col + 1 if rng.max_col >= insert_at else rng.max_col
                parts.append(
                    f'{get_column_letter(min_col)}{rng.min_row}:'
                    f'{get_column_letter(max_col_)}{rng.max_row}'
                )
            dv.sqref = ' '.join(parts)

        # 表头与数据行样式沿用右侧原列
        ref_col = insert_at + 1 if insert_at <= max_col else insert_at - 1
        for r in range(header_row, (ws.max_row or 0) + 1):
            src = ws.cell(row=r, column=ref_col)
            dst = ws.cell(row=r, column=insert_at)
            dst._style = copy(src._style)
            dst.value = UPSTREAM_HEADER if r == header_row else None
        changed += 1
    return changed


# ---------------------------------------------------------------- 主流程

def clean_file(path, out_path):
    wb = openpyxl.load_workbook(path)
    cached = openpyxl.load_workbook(path, data_only=True)
    rel = os.path.basename(path)
    records = []

    # 1) 显式范围
    for sheet, ranges in CLEAR_RANGES.get(rel, {}).items():
        if sheet not in wb.sheetnames:
            print(f'  !! sheet missing {rel} / {sheet}')
            continue
        for rng in ranges:
            clear_range(wb[sheet], rng, records)

    # 2) 显式单元格
    for sheet, coord in CLEAR_CELLS.get(rel, []):
        if sheet in wb.sheetnames:
            c = wb[sheet][coord]
            if c.value is not None:
                records.append((sheet, coord, c.value))
                c.value = None
                if getattr(c, 'hyperlink', None) is not None:
                    c.hyperlink = None

    # 3) 标题占位词修正
    for sheet, coord, val in TITLE_FIXES.get(rel, []):
        if sheet in wb.sheetnames:
            wb[sheet][coord].value = val

    # 4) 通用样例值 / 占位词处理（仅正文可见页）
    for ws in wb.worksheets:
        if ws.sheet_state == 'hidden':
            continue
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, (datetime.datetime, datetime.date)):
                    records.append((ws.title, c.coordinate, c.value))
                    c.value = None
                    continue
                if not isinstance(c.value, str):
                    continue
                s = c.value
                if DATE_FULL.match(s) and len(s) <= 24:
                    records.append((ws.title, c.coordinate, c.value))
                    c.value = None
                elif PERSON.match(s.strip()) or 'DC-AY-' in s or 'SYSM' in s:
                    records.append((ws.title, c.coordinate, c.value))
                    c.value = None
                    if getattr(c, 'hyperlink', None) is not None:
                        c.hyperlink = None
                elif DEMO_MARK.search(s) and len(s) >= 15:
                    records.append((ws.title, c.coordinate, c.value))
                    c.value = None
                    if getattr(c, 'hyperlink', None) is not None:
                        c.hyperlink = None
                elif PLACEHOLDER_TOKEN.search(s):
                    new = sanitize_text(s)
                    if new:
                        c.value = new
                    else:
                        records.append((ws.title, c.coordinate, c.value))
                        c.value = None

    # 5) 封面
    set_cover(wb, records)

    # 6) 缺陷修复
    if rel == '亚远景_HWE1_TP_硬件需求规格说明书_V1.0.xlsx':
        fix_hwe1(wb, records)
    if rel == '亚远景_SWE4_TP_软件单元验证报告_V1.0.xlsx':
        fix_swe4_workload(wb)
    if rel == '亚远景_ENG_TP_需求追踪表_V1.0.xlsx':
        add_upstream_column(wb)
    fix_error_formulas(wb, cached)

    # 7) 隐藏示例页
    add_hidden_examples(wb, records)

    wb.save(out_path)
    return len(records)


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(source_files())
    assert len(files) == 56, len(files)
    mapping = {}
    total_records = 0
    for p in files:
        name, domain, doc = derive_name(p)
        assert name not in mapping, (name, p, mapping[name])
        mapping[name] = p
        cnt = clean_file(p, os.path.join(OUT, name))
        total_records += cnt
        print(f'{os.path.basename(p):60s} -> {name}  (清理 {cnt})')
    print(f'\n共 {len(mapping)} 个文件，清理示例单元格 {total_records} 个')


if __name__ == '__main__':
    main()
