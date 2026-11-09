"""硬件/机器学习工程（HWE.1~HWE.4 / MLE.1~MLE.4）落地测试。

覆盖:
- aspice_hwe_mle_v3.1 profile：8 个过程域，各 4 条 BP，证据路径对齐
- HWE.1：链接脚本/启动代码等客观信号识别；无信号如实记「无硬件范围」；
  人工字段跨轮次保留；登记缺 scan_sources / 条目非法 / 文档缺条目 → RED
- HWE.2：设计文档覆盖每个登记条目；无范围须有明示
- HWE.3：构建产物必须真实存在且摘要一致，篡改即 RED
- HWE.4：「已验证」必须引用含条目 ID 的真实证据文件；报告臆改即 RED
- MLE.1/MLE.2：与 HWE 同构
- MLE.3：训练来源真实存在；人工训练记录跨轮次保留
- MLE.4：「已评估」必须有含非空 metrics 的证据文件；臆改即 RED
- G17/G18 门禁注册与步骤顺序
"""

import os
from pathlib import Path

import pytest
import yaml

from yuleosh.compliance import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_hwe1_requirements,
    step_hwe2_design,
    step_hwe3_implementation,
    step_hwe4_verification,
    step_mle1_requirements,
    step_mle2_approach,
    step_mle3_training,
    step_mle4_evaluation,
    step_review_hwe1,
    step_review_hwe2,
    step_review_hwe3,
    step_review_hwe4,
    step_review_mle1,
    step_review_mle2,
    step_review_mle3,
    step_review_mle4,
)
from yuleosh.pipeline.step_handlers.hwe_mle import (
    HW_DESIGN,
    HW_IMPL,
    HW_REGISTER,
    HW_REQUIREMENTS,
    HW_VERIF,
    ML_APPROACH,
    ML_EVAL,
    ML_REGISTER,
    ML_REQUIREMENTS,
    ML_TRAINING,
)


@pytest.fixture(autouse=True)
def _restore_osh_home():
    before = os.environ.get("OSH_HOME")
    yield
    if before is None:
        os.environ.pop("OSH_HOME", None)
    else:
        os.environ["OSH_HOME"] = before


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("# 产品\n\n## 需求\n\n可度量。\n", encoding="utf-8")
    sess = PipelineSession("hwe-mle-test", str(spec))
    sess.project_dir = str(tmp_path)
    return sess


def _load(tmp_path, rel):
    return yaml.safe_load((tmp_path / rel).read_text(encoding="utf-8"))


def _save(tmp_path, rel, data):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _seed_hw(tmp_path):
    """一个链接脚本 + 一个启动文件 → 两个硬件条目。"""
    (tmp_path / "linker").mkdir(exist_ok=True)
    (tmp_path / "linker" / "app.ld").write_text("MEMORY { }", encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "startup_main.s").write_text(".globl main", encoding="utf-8")


def _seed_ml(tmp_path):
    """一个模型文件 + 一个训练脚本 → 两个机器学习条目。"""
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "models" / "net.onnx").write_bytes(b"onnx-bytes")
    (tmp_path / "train_net.py").write_text("# train\n", encoding="utf-8")


# ── profile ─────────────────────────────────────────────────────────────


class TestProfile:
    def test_profile_has_eight_areas(self):
        profile = load_profile("aspice_hwe_mle_v3.1")
        ids = {a.id for a in profile.areas}
        assert ids == {"HWE.1", "HWE.2", "HWE.3", "HWE.4",
                       "MLE.1", "MLE.2", "MLE.3", "MLE.4"}
        for area in profile.areas:
            assert len(area.base_practices) == 4

    def test_evidence_paths_match_handler_outputs(self):
        profile = load_profile("aspice_hwe_mle_v3.1")
        paths = {
            ev.path
            for area in profile.areas
            for bp in area.base_practices
            for ev in bp.output_evidence
        }
        assert {HW_REGISTER, HW_REQUIREMENTS, HW_DESIGN, HW_IMPL, HW_VERIF,
                ML_REGISTER, ML_REQUIREMENTS, ML_APPROACH, ML_TRAINING,
                ML_EVAL} <= paths


# ── HWE.1 ───────────────────────────────────────────────────────────────


class TestHwe1:
    def test_no_scope_is_honest_zero(self, tmp_path):
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        assert register["items"] == []
        assert register["scan_sources"]  # 扫描来源总是记录
        doc = (tmp_path / HW_REQUIREMENTS).read_text(encoding="utf-8")
        assert "无硬件范围" in doc or "未检测到硬件范围" in doc
        step_review_hwe1(sess)
        marker = yaml.safe_load(
            (Path(sess.session_dir) / "hwe1-requirements.json").read_text())
        assert marker["status"] == "completed"

    def test_scope_detected_from_objective_signals(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        kinds = {i["kind"] for i in register["items"]}
        assert "linker-script" in kinds and "startup-code" in kinds
        assert all(i["status"] == "待分析" for i in register["items"])
        assert all(i["id"].startswith("HWE-") for i in register["items"])
        step_review_hwe1(sess)

    def test_manual_fields_preserved_across_reruns(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        register["items"][0]["owner"] = "张三"
        register["items"][0]["status"] = "done"
        _save(tmp_path, HW_REGISTER, register)
        step_hwe1_requirements(sess)  # 重跑
        rerun = _load(tmp_path, HW_REGISTER)
        first = next(i for i in rerun["items"] if i.get("owner") == "张三")
        assert first["status"] == "done"

    def test_review_red_without_scan_sources(self, tmp_path):
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        register["scan_sources"] = []
        _save(tmp_path, HW_REGISTER, register)
        with pytest.raises(PipelineStepError, match="scan_sources"):
            step_review_hwe1(sess)

    def test_review_red_on_invalid_item(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        register["items"][0]["kind"] = "bogus"
        _save(tmp_path, HW_REGISTER, register)
        with pytest.raises(PipelineStepError, match="kind"):
            step_review_hwe1(sess)

    def test_review_red_when_doc_missing(self, tmp_path):
        sess = _make_session(tmp_path)
        with pytest.raises(PipelineStepError):
            step_review_hwe1(sess)


# ── HWE.2 ───────────────────────────────────────────────────────────────


class TestHwe2:
    def test_design_covers_every_item(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe2_design(sess)
        doc = (tmp_path / HW_DESIGN).read_text(encoding="utf-8")
        for item in _load(tmp_path, HW_REGISTER)["items"]:
            assert item["id"] in doc
        step_review_hwe2(sess)

    def test_no_scope_marker_required(self, tmp_path):
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe2_design(sess)
        doc = (tmp_path / HW_DESIGN).read_text(encoding="utf-8")
        assert "无条目：未检测到硬件范围" in doc
        step_review_hwe2(sess)

    def test_review_red_when_item_not_covered(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe2_design(sess)
        doc = (tmp_path / HW_DESIGN).read_text(encoding="utf-8")
        iid = _load(tmp_path, HW_REGISTER)["items"][0]["id"]
        (tmp_path / HW_DESIGN).write_text(doc.replace(iid, "HWE-XXX"),
                                         encoding="utf-8")
        with pytest.raises(PipelineStepError, match="未覆盖"):
            step_review_hwe2(sess)


# ── HWE.3 ───────────────────────────────────────────────────────────────


class TestHwe3:
    def test_build_outputs_listed_with_digest(self, tmp_path):
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "app.elf").write_bytes(b"elf-bytes")
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe3_implementation(sess)
        doc = (tmp_path / HW_IMPL).read_text(encoding="utf-8")
        assert "out/app.elf" in doc
        step_review_hwe3(sess)

    def test_review_red_when_listed_output_deleted(self, tmp_path):
        (tmp_path / "out").mkdir()
        target = tmp_path / "out" / "app.hex"
        target.write_text("hex", encoding="utf-8")
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe3_implementation(sess)
        target.unlink()
        with pytest.raises(PipelineStepError, match="不存在"):
            step_review_hwe3(sess)

    def test_review_red_when_digest_tampered(self, tmp_path):
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "app.bin").write_bytes(b"bin-bytes")
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe3_implementation(sess)
        doc_path = tmp_path / HW_IMPL
        doc = doc_path.read_text(encoding="utf-8")
        # 篡改摘要（前 16 位换成 0）
        import re
        tampered = re.sub(r"`[0-9a-f]{16}…`", "`0000000000000000…`", doc)
        assert tampered != doc
        doc_path.write_text(tampered, encoding="utf-8")
        with pytest.raises(PipelineStepError, match="摘要不一致"):
            step_review_hwe3(sess)


# ── HWE.4 ───────────────────────────────────────────────────────────────


class TestHwe4:
    def test_unverified_without_evidence_is_green(self, tmp_path):
        """未验证是如实状态，不判红。"""
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe4_verification(sess)
        doc = (tmp_path / HW_VERIF).read_text(encoding="utf-8")
        assert "未验证" in doc
        step_review_hwe4(sess)

    def test_verified_requires_real_evidence(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        register = _load(tmp_path, HW_REGISTER)
        item = register["items"][0]
        evidence = tmp_path / "docs" / f"hw-verify-{item['id']}.md"
        evidence.write_text(f"# 验证记录\n\n{item['id']} 通过。\n",
                            encoding="utf-8")
        register["items"][0]["verification_evidence"] = (
            f"docs/hw-verify-{item['id']}.md")
        _save(tmp_path, HW_REGISTER, register)
        step_hwe4_verification(sess)
        doc = (tmp_path / HW_VERIF).read_text(encoding="utf-8")
        assert f"| {item['id']} " in doc and "| 已验证 |" in doc
        step_review_hwe4(sess)

    def test_review_red_on_fabricated_verified_claim(self, tmp_path):
        _seed_hw(tmp_path)
        sess = _make_session(tmp_path)
        step_hwe1_requirements(sess)
        step_hwe4_verification(sess)
        doc_path = tmp_path / HW_VERIF
        doc = doc_path.read_text(encoding="utf-8")
        doc_path.write_text(doc.replace("| 未验证 |", "| 已验证 |"),
                            encoding="utf-8")
        with pytest.raises(PipelineStepError, match="证据无效"):
            step_review_hwe4(sess)


# ── MLE.1 / MLE.2 ────────────────────────────────────────────────────────


class TestMle1And2:
    def test_no_scope_is_honest_zero(self, tmp_path):
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        register = _load(tmp_path, ML_REGISTER)
        assert register["items"] == []
        assert register["scan_sources"]
        step_review_mle1(sess)

    def test_scope_detected(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        kinds = {i["kind"] for i in _load(tmp_path, ML_REGISTER)["items"]}
        assert "model" in kinds and "training-script" in kinds
        step_review_mle1(sess)

    def test_approach_covers_items(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle2_approach(sess)
        doc = (tmp_path / ML_APPROACH).read_text(encoding="utf-8")
        for item in _load(tmp_path, ML_REGISTER)["items"]:
            assert item["id"] in doc
        step_review_mle2(sess)

    def test_approach_red_when_item_not_covered(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle2_approach(sess)
        doc = (tmp_path / ML_APPROACH).read_text(encoding="utf-8")
        iid = _load(tmp_path, ML_REGISTER)["items"][0]["id"]
        (tmp_path / ML_APPROACH).write_text(doc.replace(iid, "MLE-XXX"),
                                            encoding="utf-8")
        with pytest.raises(PipelineStepError, match="未覆盖"):
            step_review_mle2(sess)


# ── MLE.3 ───────────────────────────────────────────────────────────────


class TestMle3:
    def test_training_sources_must_exist(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle3_training(sess)
        doc = (tmp_path / ML_TRAINING).read_text(encoding="utf-8")
        assert "train_net.py" in doc
        step_review_mle3(sess)
        # 删除来源脚本后重判 RED
        (tmp_path / "train_net.py").unlink()
        with pytest.raises(PipelineStepError, match="不存在"):
            step_review_mle3(sess)

    def test_human_training_records_preserved(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle3_training(sess)
        doc_path = tmp_path / ML_TRAINING
        doc = doc_path.read_text(encoding="utf-8")
        human = ("| MLE-002 | dataset-v1 | cfg-a | accuracy | 0.91 |\n\n"
                 "## 可追溯性")
        doc_path.write_text(
            doc.replace("| 待人工记录 | — | — | — | — |\n\n"
                        "> 训练指标只能由人依据真实训练输出填写；"
                        "本报告不生成任何数值。\n\n## 可追溯性", human),
            encoding="utf-8")
        step_mle3_training(sess)  # 重新生成
        preserved = doc_path.read_text(encoding="utf-8")
        assert "0.91" in preserved
        step_review_mle3(sess)


# ── MLE.4 ───────────────────────────────────────────────────────────────


class TestMle4:
    def test_unevaluated_is_green(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle4_evaluation(sess)
        doc = (tmp_path / ML_EVAL).read_text(encoding="utf-8")
        assert "未评估" in doc
        step_review_mle4(sess)

    def test_evaluated_requires_metrics_evidence(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        model = next(i for i in _load(tmp_path, ML_REGISTER)["items"]
                     if i["kind"] == "model")
        _save(tmp_path, f"docs/ml-eval-{model['id']}.yaml",
              {"metrics": {"accuracy": 0.91}})
        step_mle4_evaluation(sess)
        doc = (tmp_path / ML_EVAL).read_text(encoding="utf-8")
        assert f"| {model['id']} " in doc and "| 已评估 |" in doc
        step_review_mle4(sess)

    def test_review_red_on_fabricated_evaluated_claim(self, tmp_path):
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)
        step_mle1_requirements(sess)
        step_mle4_evaluation(sess)
        doc_path = tmp_path / ML_EVAL
        doc = doc_path.read_text(encoding="utf-8")
        doc_path.write_text(doc.replace("| 未评估 |", "| 已评估 |"),
                            encoding="utf-8")
        with pytest.raises(PipelineStepError, match="证据无效"):
            step_review_mle4(sess)


# ── 合规与注册 ──────────────────────────────────────────────────────────


class TestComplianceProfile:
    def test_green_only_after_artifacts_exist(self, tmp_path):
        """有确定性产物 → 全绿；无产物 → 全红（不假绿）。"""
        _seed_hw(tmp_path)
        _seed_ml(tmp_path)
        sess = _make_session(tmp_path)

        before = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_hwe_mle_v3.1"]
        ).run()["summary"]
        assert before["passed"] == 0 and before["failed"] > 0

        for fn in (step_hwe1_requirements, step_hwe2_design,
                   step_hwe3_implementation, step_hwe4_verification,
                   step_mle1_requirements, step_mle2_approach,
                   step_mle3_training, step_mle4_evaluation):
            fn(sess)
        after = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_hwe_mle_v3.1"]
        ).run()["summary"]
        assert after["failed"] == 0 and after["passed"] > 0


class TestRegistration:
    @pytest.mark.parametrize("gate,steps", [
        ("G17", ["hwe1-requirements", "hwe1-review", "hwe2-design",
                 "hwe2-review", "hwe3-implementation", "hwe3-review",
                 "hwe4-verification", "hwe4-review"]),
        ("G18", ["mle1-requirements", "mle1-review", "mle2-approach",
                 "mle2-review", "mle3-training", "mle3-review",
                 "mle4-evaluation", "mle4-review"]),
    ])
    def test_gates_registered(self, gate, steps):
        registered = next(g for g in GATES if g["gate"] == gate)
        assert registered["step_keys"] == steps

    def test_step_order(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        order = [
            "pim3-review",
            "hwe1-requirements", "hwe4-review",
            "mle1-requirements", "mle4-review",
            "spl2-release", "final-report",
        ]
        positions = [keys.index(k) for k in order]
        assert positions == sorted(positions)
