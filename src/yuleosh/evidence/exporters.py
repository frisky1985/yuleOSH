# @req RS-006
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""人类可读格式转换：把 ``.osh/evidence/*.md`` 转成 HTML / Excel / PDF。

设计约定
--------
* Markdown 始终是**生成真源**（由 generator 产出），本模块只做格式派生，
  不改写任何证据内容，避免多份真源漂移。
* HTML 与 PDF 共用同一份渲染模板（浅色、可打印），PDF 直接由 HTML 打印生成。
* Excel 面向表格类报告（追溯矩阵 / 覆盖率）：GFM 表格还原为单元格，
  标题与正文按行写入，便于审计方筛选与二次加工。
* 反假绿：任一格式失败只记录到 ``skipped`` 并继续其余格式，不阻断打包；
  PDF 缺少 weasyprint 依赖时显式报「未生成」，不静默假装成功。
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

SUPPORTED_FORMATS = ("md", "html", "xlsx", "pdf")

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
         max-width: 1080px; margin: 24px auto; padding: 0 20px; color: #1f2933; line-height: 1.65; }}
  h1 {{ font-size: 26px; border-bottom: 2px solid #722ed1; padding-bottom: 8px; }}
  h2 {{ font-size: 20px; margin-top: 28px; border-bottom: 1px solid #d9e2ec; padding-bottom: 6px; }}
  h3 {{ font-size: 16px; margin-top: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; font-size: 13px; }}
  th, td {{ border: 1px solid #cbd2d9; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #f0eafd; font-weight: 600; }}
  tr:nth-child(even) td {{ background: #f7f8fa; }}
  code {{ background: #f0f2f5; border-radius: 4px; padding: 1px 5px;
         font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
  pre {{ background: #f0f2f5; border-radius: 6px; padding: 12px; overflow-x: auto; }}
  pre code {{ background: none; padding: 0; }}
  blockquote {{ border-left: 4px solid #722ed1; margin: 12px 0; padding: 4px 14px; color: #52606d; }}
  hr {{ border: none; border-top: 1px solid #d9e2ec; margin: 24px 0; }}
  @media print {{ body {{ margin: 0; max-width: none; }} table {{ font-size: 11px; }} }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class ExportUnavailable(RuntimeError):
    """依赖缺失等导致某格式无法生成（调用方应记录并继续，而非中断）。"""


def parse_formats(raw: object) -> list[str]:
    """把 CLI 字符串 / API 列表规范化为去重后的格式列表，非法项抛 ValueError。"""
    if raw is None:
        return ["md"]
    if isinstance(raw, str):
        items = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        raise ValueError("formats must be a comma-separated string or a list")
    if not items:
        return ["md"]
    bad = [f for f in items if f not in SUPPORTED_FORMATS]
    if bad:
        raise ValueError(
            f"unsupported format(s): {', '.join(bad)}; choose from {', '.join(SUPPORTED_FORMATS)}"
        )
    # md 是真源，始终保留；其余按 SUPPORTED_FORMATS 顺序去重。
    ordered = [f for f in SUPPORTED_FORMATS if f in items]
    if "md" not in ordered:
        ordered.insert(0, "md")
    return ordered


def markdown_to_html(md_text: str, title: str) -> str:
    """GFM → 完整 HTML 文档（含打印样式，PDF 复用同一模板）。"""
    import markdown

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return _HTML_TEMPLATE.format(title=_html.escape(title), body=body)


_SEP_CELL = re.compile(r"^:?-{2,}:?$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _clean_inline(text: str) -> str:
    """去掉行内 Markdown 记号，Excel 单元格只保留纯文本。"""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.replace("**", "").replace("`", "").strip()


def _split_table_row(line: str) -> list[str]:
    return [_clean_inline(c) for c in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(
        _SEP_CELL.match(c.replace(" ", "")) for c in non_empty
    )


def markdown_to_xlsx(md_text: str, title: str, out_path: Path) -> None:
    """把 Markdown 写入 Excel：标题加粗、GFM 表格还原为单元格、代码块等宽字体。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\\/*?\[\]:]", " ", title)[:31] or "Report"

    header_fill = PatternFill("solid", fgColor="F0EAFD")
    widths: dict[int, int] = {}
    row = 1

    def _write_cell(r: int, c: int, value: str, font: Font | None = None, fill=None):
        cell = ws.cell(row=r, column=c, value=value)
        if font is not None:
            cell.font = font
        if fill is not None:
            cell.fill = fill
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        widths[c] = min(60, max(widths.get(c, 0), len(value) + 2))

    lines = md_text.splitlines()
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            _write_cell(row, 1, line, font=Font(name="Consolas", size=10))
            row += 1
            i += 1
            continue

        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            first = True
            for tl in table_lines:
                cells = _split_table_row(tl)
                if _is_separator_row(cells):
                    continue
                for col, value in enumerate(cells, start=1):
                    _write_cell(
                        row, col, value,
                        font=Font(bold=True) if first else None,
                        fill=header_fill if first else None,
                    )
                first = False
                row += 1
            row += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            size = {1: 18, 2: 15, 3: 13}.get(level, 12)
            _write_cell(row, 1, _clean_inline(heading.group(2)), font=Font(bold=True, size=size))
            row += 2
            i += 1
            continue

        if stripped:
            _write_cell(row, 1, _clean_inline(stripped))
        row += 1
        i += 1

    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(10, width)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def html_to_pdf(html_text: str, out_path: Path, base_url: str | None = None) -> None:
    """HTML → PDF。缺少 weasyprint 时抛 ExportUnavailable（不静默跳过）。"""
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - 取决于环境是否装可选依赖
        raise ExportUnavailable(
            "PDF 导出需要可选依赖 weasyprint：pip install 'yuleosh[pdf]'"
        ) from exc
    HTML(string=html_text, base_url=base_url).write_pdf(str(out_path))


def export_formats(evidence_dir: str | Path, formats: object) -> dict:
    """把 evidence_dir 下所有 .md 报告派生成所选格式。

    Returns:
        {"generated": [文件名...], "skipped": [原因...]} — 供 CLI 打印与测试断言。
    """
    ev_dir = Path(evidence_dir)
    selected = parse_formats(formats)
    generated: list[str] = []
    skipped: list[str] = []

    targets = [f for f in selected if f != "md"]
    if not targets:
        return {"generated": generated, "skipped": skipped}

    for md_path in sorted(ev_dir.glob("*.md")):
        md_text = md_path.read_text(encoding="utf-8")
        html_text = None
        if "html" in targets or "pdf" in targets:
            html_text = markdown_to_html(md_text, md_path.stem)

        if "html" in targets:
            out = md_path.with_suffix(".html")
            out.write_text(html_text, encoding="utf-8")
            generated.append(out.name)

        if "xlsx" in targets:
            out = md_path.with_suffix(".xlsx")
            try:
                markdown_to_xlsx(md_text, md_path.stem, out)
                generated.append(out.name)
            except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断其余格式
                skipped.append(f"{out.name}: {exc}")

        if "pdf" in targets:
            out = md_path.with_suffix(".pdf")
            try:
                html_to_pdf(html_text, out, base_url=str(ev_dir))
                generated.append(out.name)
            except Exception as exc:  # noqa: BLE001 - 依赖缺失/渲染失败均记录原因
                skipped.append(f"{out.name}: {exc}")

    return {"generated": generated, "skipped": skipped}
