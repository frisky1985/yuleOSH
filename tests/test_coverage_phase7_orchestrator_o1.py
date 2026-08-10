"""Phase 7 coverage boost — orchestrator.py O1 函数组（L44-129）。

Target functions (src/yuleosh/pipeline/orchestrator.py):
  - _detect_project_type            (L44-72)
  - _ensure_autosar_pipeline_config (L75-99)
  - _detect_and_bootstrap           (L102-129)

策略：
  - 文件系统探测用 pytest tmp_path 真实文件 + 真实 PyYAML（含畸形 YAML 触发异常分支）；
  - 内置模板路径分支通过 monkeypatch 模块 ``__file__`` 定向到 tmp_path 周边，
    不依赖仓库真实 templates/ 布局，也不触碰 src/；
  - 无 subprocess / 网络 / 时间依赖。
"""

import logging

from yuleosh.pipeline import orchestrator as orch


def _point_module_file(monkeypatch, fake_pkg_dir):
    """把 orchestrator.__file__ 指到 fake_pkg_dir/pipeline/orchestrator.py。

    使函数内 ``os.path.dirname(__file__)`` 派生出的内置模板路径全部落在
    fake_pkg_dir 附近（L87/L89/L114/L116），从而用 tmp_path 精确控制存在性。
    """
    monkeypatch.setattr(
        orch, "__file__", str(fake_pkg_dir / "pipeline" / "orchestrator.py")
    )


# =====================================================================
# _detect_project_type (L44-72)
# =====================================================================


def test_detect_no_config_file_returns_none(tmp_path):
    assert orch._detect_project_type(str(tmp_path)) is None


def test_detect_top_level_type_name_template(tmp_path):
    cfg = tmp_path / ".yuleosh.yaml"
    cfg.write_text("type: autosar\nname: myproj\ntemplate: tpl\n", encoding="utf-8")
    info = orch._detect_project_type(str(tmp_path))
    assert info == {
        "type": "autosar",
        "name": "myproj",
        "template_name": "tpl",
        "config_source": str(cfg),
    }


def test_detect_skips_type_less_first_candidate(tmp_path):
    # 候选 1 存在但无 type（name/template 均回退到 ptype）→ 继续候选 2
    (tmp_path / ".yuleosh.yaml").write_text("name: no-type\n", encoding="utf-8")
    cfg2 = tmp_path / "yuleosh.yaml"
    cfg2.write_text("type: autosar\n", encoding="utf-8")
    info = orch._detect_project_type(str(tmp_path))
    assert info["type"] == "autosar"
    assert info["name"] == "autosar"
    assert info["template_name"] == "autosar"
    assert info["config_source"] == str(cfg2)


def test_detect_nested_project_type(tmp_path):
    cfg = tmp_path / "yuleosh.yaml"
    cfg.write_text(
        "project:\n  type: autosar\n  name: nested\n  template: ntpl\n",
        encoding="utf-8",
    )
    info = orch._detect_project_type(str(tmp_path))
    assert info["type"] == "autosar"
    assert info["name"] == "nested"
    assert info["template_name"] == "ntpl"


def test_detect_third_candidate_nested_type_with_fallbacks(tmp_path):
    cfg_dir = tmp_path / ".yuleosh"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.yml"
    cfg.write_text("project:\n  type: autosar\n", encoding="utf-8")
    info = orch._detect_project_type(str(tmp_path))
    assert info["type"] == "autosar"
    assert info["name"] == "autosar"
    assert info["template_name"] == "autosar"
    assert info["config_source"] == str(cfg)


def test_detect_top_level_type_with_nested_name_template(tmp_path):
    cfg = tmp_path / ".yuleosh.yaml"
    cfg.write_text(
        "type: autosar\nproject:\n  name: pname\n  template: ptpl\n",
        encoding="utf-8",
    )
    info = orch._detect_project_type(str(tmp_path))
    assert info == {
        "type": "autosar",
        "name": "pname",
        "template_name": "ptpl",
        "config_source": str(cfg),
    }


def test_detect_config_without_type_returns_none(tmp_path):
    (tmp_path / ".yuleosh.yaml").write_text("name: nope\n", encoding="utf-8")
    assert orch._detect_project_type(str(tmp_path)) is None


def test_detect_non_dict_yaml_returns_none(tmp_path):
    (tmp_path / ".yuleosh.yaml").write_text("- a\n- b\n", encoding="utf-8")
    assert orch._detect_project_type(str(tmp_path)) is None


def test_detect_empty_yaml_returns_none(tmp_path):
    (tmp_path / ".yuleosh.yaml").write_text("# comment only\n", encoding="utf-8")
    assert orch._detect_project_type(str(tmp_path)) is None


def test_detect_malformed_yaml_logs_debug_and_returns_none(tmp_path, caplog):
    (tmp_path / ".yuleosh.yaml").write_text("type: [unclosed\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="pipeline.orchestrator"):
        assert orch._detect_project_type(str(tmp_path)) is None
    assert "Could not parse" in caplog.text


# =====================================================================
# _ensure_autosar_pipeline_config (L75-99)
# =====================================================================


def test_ensure_config_already_exists_returns_false(tmp_path):
    cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("existing\n", encoding="utf-8")
    assert orch._ensure_autosar_pipeline_config(str(tmp_path)) is False


def test_ensure_config_copies_explicit_template(tmp_path):
    pcfg = tmp_path / "tpl" / "pipeline" / "config.yaml"
    pcfg.parent.mkdir(parents=True)
    pcfg.write_text("pipeline: cfg\n", encoding="utf-8")

    assert orch._ensure_autosar_pipeline_config(str(tmp_path), tmp_path / "tpl") is True

    out = tmp_path / ".yuleosh" / "ci-config.yaml"
    assert out.read_text(encoding="utf-8") == "pipeline: cfg\n"


def test_ensure_config_explicit_template_missing_pipeline_cfg(tmp_path):
    (tmp_path / "tpl").mkdir(parents=True)
    assert orch._ensure_autosar_pipeline_config(str(tmp_path), tmp_path / "tpl") is False


def test_ensure_config_builtin_first_template_path(tmp_path, monkeypatch):
    # __file__ = tmp_path/a/b/pipeline/orchestrator.py
    #   L87  → tmp_path/templates/autosar（存在）→ 不走 L89 回退
    tpl = tmp_path / "templates" / "autosar" / "pipeline" / "config.yaml"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("tpl: cfg\n", encoding="utf-8")
    _point_module_file(monkeypatch, tmp_path / "a" / "b")

    assert orch._ensure_autosar_pipeline_config(str(tmp_path / "proj")) is True
    assert (tmp_path / "proj" / ".yuleosh" / "ci-config.yaml").read_text(
        encoding="utf-8"
    ) == "tpl: cfg\n"


def test_ensure_config_builtin_fallback_template_path(tmp_path, monkeypatch):
    # __file__ = tmp_path/fake-pkg/pipeline/orchestrator.py
    #   L87 → parent(tmp_path)/templates/autosar（不存在）→ L89 回退到
    #   tmp_path/templates/autosar（存在）
    tpl = tmp_path / "templates" / "autosar" / "pipeline" / "config.yaml"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("tpl: cfg\n", encoding="utf-8")
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")

    assert orch._ensure_autosar_pipeline_config(str(tmp_path / "proj")) is True
    assert (tmp_path / "proj" / ".yuleosh" / "ci-config.yaml").read_text(
        encoding="utf-8"
    ) == "tpl: cfg\n"


def test_ensure_config_builtin_no_template_found(tmp_path, monkeypatch):
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    assert orch._ensure_autosar_pipeline_config(str(tmp_path / "proj")) is False


# =====================================================================
# _detect_and_bootstrap (L102-129)
# =====================================================================


def test_bootstrap_no_project_returns_none(tmp_path, monkeypatch):
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    assert orch._detect_and_bootstrap(str(tmp_path)) is None


def test_bootstrap_non_autosar_type(tmp_path, monkeypatch):
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    (tmp_path / ".yuleosh.yaml").write_text("type: qemu\nname: q\n", encoding="utf-8")
    info = orch._detect_and_bootstrap(str(tmp_path))
    assert info["type"] == "qemu"
    assert info["name"] == "q"


def test_bootstrap_autosar_full_template(tmp_path, monkeypatch, caplog):
    # templates_base 存在（L115 False），autosar-classic 存在且含 template.yaml
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    (tmp_path / ".yuleosh.yaml").write_text(
        "type: autosar\nname: demo\n", encoding="utf-8"
    )
    # templates_base = dirname.parent.parent / "templates" = tmp_path/templates
    classic = tmp_path / "templates" / "autosar-classic"
    classic.mkdir(parents=True)
    (classic / "template.yaml").write_text("tpl\n", encoding="utf-8")
    pcfg = classic / "pipeline" / "config.yaml"
    pcfg.parent.mkdir(parents=True)
    pcfg.write_text("pipeline: cfg\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="pipeline.orchestrator"):
        info = orch._detect_and_bootstrap(str(tmp_path))

    assert info["type"] == "autosar"
    assert "AUTOSAR template found" in caplog.text
    assert (tmp_path / ".yuleosh" / "ci-config.yaml").read_text(
        encoding="utf-8"
    ) == "pipeline: cfg\n"


def test_bootstrap_autosar_without_template_yaml(tmp_path, monkeypatch):
    # autosar-classic 存在但缺 template.yaml → L123 False，仍执行 bootstrap
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    (tmp_path / ".yuleosh.yaml").write_text(
        "type: autosar\nname: demo\n", encoding="utf-8"
    )
    classic = tmp_path / "templates" / "autosar-classic"
    pcfg = classic / "pipeline" / "config.yaml"
    pcfg.parent.mkdir(parents=True)
    pcfg.write_text("pipeline: cfg\n", encoding="utf-8")

    info = orch._detect_and_bootstrap(str(tmp_path))

    assert info["type"] == "autosar"
    assert (tmp_path / ".yuleosh" / "ci-config.yaml").read_text(
        encoding="utf-8"
    ) == "pipeline: cfg\n"


def test_bootstrap_autosar_classic_dir_missing(tmp_path, monkeypatch, caplog):
    # templates_base 存在但无 autosar-classic → L120 False → 跳过 bootstrap
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    (tmp_path / ".yuleosh.yaml").write_text(
        "type: autosar\nname: demo\n", encoding="utf-8"
    )
    (tmp_path / "templates").mkdir(parents=True)

    with caplog.at_level(logging.INFO, logger="pipeline.orchestrator"):
        info = orch._detect_and_bootstrap(str(tmp_path))

    assert info["type"] == "autosar"
    assert "AUTOSAR template dir not found, skipping bootstrap" in caplog.text
    assert not (tmp_path / ".yuleosh" / "ci-config.yaml").exists()


def test_bootstrap_autosar_templates_base_missing(tmp_path, monkeypatch, caplog):
    # templates_base 不存在 → L115 True → L116 回退仍不存在 → tdir=None → 跳过
    _point_module_file(monkeypatch, tmp_path / "fake-pkg")
    (tmp_path / ".yuleosh.yaml").write_text(
        "type: autosar\nname: demo\n", encoding="utf-8"
    )

    with caplog.at_level(logging.INFO, logger="pipeline.orchestrator"):
        info = orch._detect_and_bootstrap(str(tmp_path))

    assert info["type"] == "autosar"
    assert "AUTOSAR template dir not found, skipping bootstrap" in caplog.text
