# @req RS-006
"""evidence/exporters.py — md → html/xlsx/pdf 派生格式测试。"""

from pathlib import Path

import pytest

from yuleosh.evidence.exporters import (
    CACHE_DIRNAME,
    ExportUnavailable,
    convert_markdown,
    export_formats,
    html_to_pdf,
    markdown_to_html,
    markdown_to_xlsx,
    parse_formats,
)

SAMPLE_MD = """# Traceability Matrix

Generated: 2026-11-12

| Req | Test | Status |
| --- | ---- | ------ |
| RS-001 | test_alpha | ✅ |
| RS-002 | test_beta | ❌ |

## Notes

Some **bold** text with `code`.

```c
int main(void) { return 0; }
```
"""


class TestParseFormats:
    def test_default_is_markdown_only(self):
        assert parse_formats(None) == ["md"]
        assert parse_formats("") == ["md"]
        assert parse_formats([]) == ["md"]

    def test_comma_string(self):
        assert parse_formats("md,html,xlsx") == ["md", "html", "xlsx"]
        assert parse_formats(" HTML , PDF ") == ["md", "html", "pdf"]

    def test_list_input(self):
        assert parse_formats(["html", "xlsx"]) == ["md", "html", "xlsx"]

    def test_deduplicates_and_orders(self):
        assert parse_formats("pdf,html,pdf,md") == ["md", "html", "pdf"]

    def test_rejects_unknown_format(self):
        with pytest.raises(ValueError, match="unsupported format"):
            parse_formats("md,docx")

    def test_rejects_wrong_type(self):
        with pytest.raises(ValueError, match="formats must be"):
            parse_formats(123)


class TestMarkdownToHtml:
    def test_rejects_raw_md_and_renders_table(self):
        html = markdown_to_html(SAMPLE_MD, "traceability-matrix")
        assert "<h1>Traceability Matrix</h1>" in html
        assert "<table>" in html
        assert "<td>RS-001</td>" in html
        assert "<strong>bold</strong>" in html
        # 分隔行不应成为数据行
        assert "---" not in html.split("<table>")[1].split("</table>")[0]

    def test_escapes_title(self):
        html = markdown_to_html("# x", "<script>alert(1)</script>")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestMarkdownToXlsx:
    def test_table_becomes_cells(self, tmp_path):
        out = tmp_path / "report.xlsx"
        markdown_to_xlsx(SAMPLE_MD, "traceability-matrix", out)
        from openpyxl import load_workbook

        ws = load_workbook(out).active
        values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
        assert "Traceability Matrix" in values
        assert "RS-001" in values
        assert "test_beta" in values
        # 表头与数据在不同行、同列对齐
        header_row = next(r for r in ws.iter_rows() if r[0].value == "Req")
        data_row = next(r for r in ws.iter_rows() if r[0].value == "RS-001")
        assert header_row[1].value == "Test"
        assert data_row[1].value == "test_alpha"
        # Markdown 分隔行不写入 Excel
        assert not any(v and set(str(v)) <= {"-", ":"} for v in values)

    def test_inline_marks_stripped(self, tmp_path):
        out = tmp_path / "notes.xlsx"
        markdown_to_xlsx("Some **bold** text with `code`.", "notes", out)
        from openpyxl import load_workbook

        ws = load_workbook(out).active
        assert ws["A1"].value == "Some bold text with code."


class TestExportFormats:
    def test_html_and_xlsx_generated_for_each_md(self, tmp_path):
        (tmp_path / "a.md").write_text(SAMPLE_MD, encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\n| x |\n| --- |\n| 1 |\n", encoding="utf-8")
        # 机器真源不参与派生
        (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

        result = export_formats(tmp_path, ["md", "html", "xlsx"])
        assert sorted(result["generated"]) == ["a.html", "a.xlsx", "b.html", "b.xlsx"]
        assert result["skipped"] == []
        assert "<table>" in (tmp_path / "a.html").read_text(encoding="utf-8")

    def test_md_only_is_noop(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        result = export_formats(tmp_path, None)
        assert result == {"generated": [], "skipped": []}

    def test_pdf_generated_when_weasyprint_available(self, tmp_path):
        pytest.importorskip("weasyprint")
        (tmp_path / "a.md").write_text(SAMPLE_MD, encoding="utf-8")
        result = export_formats(tmp_path, ["md", "pdf"])
        assert result["generated"] == ["a.pdf"]
        assert result["skipped"] == []
        assert (tmp_path / "a.pdf").read_bytes().startswith(b"%PDF")

    def test_pdf_dependency_missing_is_reported_not_silent(self, tmp_path, monkeypatch):
        # 模拟 weasyprint 未安装：html_to_pdf 抛 ExportUnavailable，
        # export_formats 必须把原因写进 skipped，而不是假装成功。
        def _unavailable(*args, **kwargs):
            raise ExportUnavailable("PDF 导出需要可选依赖 weasyprint")

        monkeypatch.setattr(
            "yuleosh.evidence.exporters.html_to_pdf", _unavailable
        )
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        result = export_formats(tmp_path, ["md", "html", "pdf"])
        assert result["generated"] == ["a.html"]  # HTML 不受影响
        assert len(result["skipped"]) == 1
        assert "weasyprint" in result["skipped"][0]
        assert not (tmp_path / "a.pdf").exists()


class TestConvertMarkdown:
    """按需转换：单文件 + 内容哈希缓存（重新生成 md 后旧缓存不再命中）。"""

    def test_passthrough_for_md(self, tmp_path):
        src = tmp_path / "a.md"
        src.write_text("# A\n", encoding="utf-8")
        assert convert_markdown(src, "md") == src

    def test_html_conversion_is_cached(self, tmp_path):
        src = tmp_path / "a.md"
        src.write_text(SAMPLE_MD, encoding="utf-8")
        first = convert_markdown(src, "html")
        assert first.is_file() and first.parent.name == CACHE_DIRNAME
        mtime = first.stat().st_mtime_ns
        assert convert_markdown(src, "html") == first
        assert first.stat().st_mtime_ns == mtime  # 命中缓存，未重写

    def test_cache_invalidated_when_md_changes(self, tmp_path):
        src = tmp_path / "a.md"
        src.write_text(SAMPLE_MD, encoding="utf-8")
        first = convert_markdown(src, "html")
        src.write_text(SAMPLE_MD + "\n\n新增段落\n", encoding="utf-8")
        second = convert_markdown(src, "html")
        assert second != first
        assert "新增段落" in second.read_text(encoding="utf-8")

    def test_rejects_unknown_format(self, tmp_path):
        src = tmp_path / "a.md"
        src.write_text("# A\n", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported format"):
            convert_markdown(src, "docx")

    def test_xlsx_conversion(self, tmp_path):
        src = tmp_path / "a.md"
        src.write_text(SAMPLE_MD, encoding="utf-8")
        out = convert_markdown(src, "xlsx")
        assert out.suffix == ".xlsx"
        from openpyxl import load_workbook

        assert load_workbook(out).active["A1"].value == "Traceability Matrix"


class TestPackVariant:
    """整包下载附加格式：从 ZIP 内部取 md 转换，并同步更新 manifest。"""

    def test_appends_formats_and_updates_manifest(self, tmp_path):
        import json
        import zipfile

        from yuleosh.api.evidence import _build_pack_variant

        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        base = ev_dir / "compliance-pack.zip"
        with zipfile.ZipFile(base, "w") as zf:
            zf.writestr("a.md", SAMPLE_MD)
            zf.writestr("manifest.json", json.dumps({"files": [], "total_files": 0}))

        out = _build_pack_variant(base, ev_dir, ["html", "xlsx"])
        assert out.is_file()
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
        assert {"a.md", "a.html", "a.xlsx", "manifest.json"} <= names
        tracked = {e["path"] for e in manifest["files"]}
        assert {"a.html", "a.xlsx"} <= tracked
        assert manifest["total_files"] == 2
        assert manifest["derived_formats"] == ["html", "xlsx"]
        # 二次下载命中缓存，不重复转换
        assert _build_pack_variant(base, ev_dir, ["html", "xlsx"]) == out


def test_html_to_pdf_roundtrip(tmp_path):
    pytest.importorskip("weasyprint")
    out = tmp_path / "x.pdf"
    html_to_pdf(markdown_to_html(SAMPLE_MD, "x"), out)
    assert out.stat().st_size > 500


class TestComplianceZipIncludesDerivedFormats:
    def test_zip_and_manifest_cover_html_xlsx(self, tmp_path):
        import json
        import zipfile

        from yuleosh.evidence.compliance import pack_compliance_zip

        class _Collector:
            project_dir = str(tmp_path)
            evidence_dir = tmp_path / ".osh" / "evidence"

        _Collector.evidence_dir.mkdir(parents=True)
        (_Collector.evidence_dir / "a.md").write_text(SAMPLE_MD, encoding="utf-8")
        zip_path = Path(pack_compliance_zip(_Collector(), formats="md,html,xlsx"))

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            assert {"a.md", "a.html", "a.xlsx"} <= names
            manifest = json.loads(zf.read("manifest.json"))
        tracked = {e["path"] for e in manifest["files"]}
        assert {"a.html", "a.xlsx"} <= tracked

    def test_default_formats_keep_markdown_only(self, tmp_path):
        import zipfile

        from yuleosh.evidence.compliance import pack_compliance_zip

        class _Collector:
            project_dir = str(tmp_path)
            evidence_dir = tmp_path / ".osh" / "evidence"

        _Collector.evidence_dir.mkdir(parents=True)
        (_Collector.evidence_dir / "a.md").write_text("# A\n", encoding="utf-8")
        zip_path = Path(pack_compliance_zip(_Collector()))

        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "a.md" in names
        assert not any(n.endswith((".html", ".xlsx", ".pdf")) for n in names)
