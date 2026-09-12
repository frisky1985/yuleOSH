"""A1-03 StandardProfile loader + 校验测试（单测 ≥12）。

覆盖：正常无损加载、profile 不存在、缺字段、未知字段三类报错的字段路径与提示。
"""

import textwrap
from pathlib import Path

import pytest
import yaml

from yuleosh.compliance.profile import (
    ProfileError,
    ProfileNotFoundError,
    StandardProfile,
    load_profile,
)


def test_load_aspice_v3_1_success():
    prof = load_profile("aspice_v3.1")
    assert isinstance(prof, StandardProfile)
    assert prof.meta.standard == "ASPICE"
    assert prof.meta.version == "3.1"
    # 6 个过程域 swe.1~swe.6
    assert len(prof.areas) == 6
    assert [a.id for a in prof.areas] == [
        "SWE.1", "SWE.2", "SWE.3", "SWE.4", "SWE.5", "SWE.6"
    ]


def test_lossless_mapping_evidence():
    prof = load_profile("aspice_v3.1")
    swe1 = prof.area_by_id("SWE.1")
    assert swe1 is not None
    assert swe1.title == "Software Requirements Analysis"
    # 第一个 base practice
    bp1 = swe1.base_practices[0]
    assert bp1.id == "SWE.1.BP1"
    # output_evidence 无损
    ev = bp1.output_evidence[0]
    assert ev.type == "document"
    assert ev.path == "docs/software-requirements.md"
    # check 文本列表
    assert any("unique identifier" in c for c in bp1.check)


def test_profile_not_found_lists_available():
    with pytest.raises(ProfileNotFoundError) as exc:
        load_profile("does_not_exist_xyz")
    assert "aspice_v3.1" in exc.value.available
    assert exc.value.name == "does_not_exist_xyz"


def test_missing_meta_standard_reports_path():
    yaml_text = "meta:\n  version: '3.1'\nswe.1:\n  id: SWE.1\n  base_practices: []\n"
    with _tmp_profile("nometa", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("nometa", profile_dir=d)
    assert exc.value.field_path == "nometa.meta.standard"
    assert "修复" in str(exc.value) or "标准名" in str(exc.value)


def test_missing_base_practice_id_reports_path():
    yaml_text = textwrap.dedent(
        """
        meta:
          standard: ASPICE
          version: "3.1"
        swe.1:
          id: SWE.1
          base_practices:
            - title: "no id here"
              output_evidence: []
        """
    )
    with _tmp_profile("nobpid", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("nobpid", profile_dir=d)
    assert "base_practices[0].id" in exc.value.field_path


def test_unknown_area_key_reports_path():
    yaml_text = textwrap.dedent(
        """
        meta:
          standard: ASPICE
          version: "3.1"
        swe.1:
          id: SWE.1
          bogus_field: 1
          base_practices: []
        """
    )
    with _tmp_profile("unkarea", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("unkarea", profile_dir=d)
    assert "bogus_field" in exc.value.field_path


def test_unknown_base_practice_key_reports_path():
    yaml_text = textwrap.dedent(
        """
        meta:
          standard: ASPICE
          version: "3.1"
        swe.1:
          id: SWE.1
          base_practices:
            - id: SWE.1.BP1
              weird: true
        """
    )
    with _tmp_profile("unkbp", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("unkbp", profile_dir=d)
    assert "weird" in exc.value.field_path


def test_unknown_evidence_key_reports_path():
    yaml_text = textwrap.dedent(
        """
        meta:
          standard: ASPICE
          version: "3.1"
        swe.1:
          id: SWE.1
          base_practices:
            - id: SWE.1.BP1
              output_evidence:
                - type: document
                  path: docs/x.md
                  surprise: yes
        """
    )
    with _tmp_profile("unkev", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("unkev", profile_dir=d)
    assert "surprise" in exc.value.field_path


def test_unknown_meta_key_reports_path():
    yaml_text = textwrap.dedent(
        """
        meta:
          standard: ASPICE
          version: "3.1"
          whoami: bad
        swe.1:
          id: SWE.1
          base_practices: []
        """
    )
    with _tmp_profile("unkmeta", yaml_text) as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("unkmeta", profile_dir=d)
    assert "whoami" in exc.value.field_path


def test_empty_yaml_raises():
    with _tmp_profile("empty", "") as d:
        with pytest.raises(ProfileError) as exc:
            load_profile("empty", profile_dir=d)
    assert "meta" in exc.value.field_path


def test_area_by_id_lookup():
    prof = load_profile("aspice_v3.1")
    assert prof.area_by_id("SWE.3").title == "Software Detailed Design and Unit Construction"
    assert prof.area_by_id("NOPE") is None


def test_all_base_practice_ids_ordered():
    prof = load_profile("aspice_v3.1")
    ids = prof.all_base_practice_ids()
    assert ids[0] == "SWE.1.BP1"
    assert len(ids) == 18  # 6 域 × 3 BP
    assert ids == sorted(ids, key=lambda x: (x.split(".")[1], x.split(".")[2]))


def test_profile_dir_search_order():
    # profiles/ 子目录也应被搜到（A1-06 迁移兼容）
    import tempfile

    base = Path(tempfile.mkdtemp())
    profiles_dir = base / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "custom_std.yaml").write_text(
        "meta:\n  standard: CUSTOM\n  version: '1.0'\nswe.1:\n  id: SWE.1\n  base_practices: []\n",
        encoding="utf-8",
    )
    prof = load_profile("custom_std", profile_dir=base)
    assert prof.meta.standard == "CUSTOM"


# ------------------------------------------------------------------
# 测试辅助
# ------------------------------------------------------------------
import contextlib
import tempfile as _tf


@contextlib.contextmanager
def _tmp_profile(name: str, yaml_text: str):
    d = Path(_tf.mkdtemp())
    (d / f"{name}.yaml").write_text(yaml_text, encoding="utf-8")
    try:
        yield d
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)
