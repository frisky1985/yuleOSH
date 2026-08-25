"""Tests for engine/runner_spec.py — K8s runner Job spec (EI-M2C)."""

# @tests src/yuleosh/pipeline/run.py

import pytest

from yuleosh.engine.runner_spec import RunnerSpec, quota_manifest


class TestRunnerSpec:
    def test_job_name(self):
        s = RunnerSpec(tenant="acme", project="proj-a", step_id="spec-check", run_id="r7")
        assert s.job_name() == "yuleosh-runner-acme-r7"

    def test_resolve_pvc_explicit(self):
        s = RunnerSpec(tenant="acme", project="p", step_id="s", pvc_name="my-pvc")
        assert s.resolve_pvc() == "my-pvc"

    def test_resolve_pvc_default(self):
        s = RunnerSpec(tenant="acme", project="p", step_id="s", pvc_prefix="yuleosh-data")
        assert s.resolve_pvc() == "yuleosh-data-acme-data"

    def test_pod_labels_tenant_selector(self):
        """GIVEN spec WHEN pod_labels THEN NetworkPolicy 选择器标签。"""
        s = RunnerSpec(tenant="acme", project="p", step_id="s")
        labels = s.pod_labels()
        assert labels["yuleosh.io/tenant"] == "acme"
        assert labels["app.kubernetes.io/component"] == "runner"

    def test_worker_args(self):
        s = RunnerSpec(tenant="acme", project="proj-a", step_id="spec-check", run_id="r1")
        args = s.worker_args()
        assert args == ["--step-id", "spec-check",
                        "--project-dir", "/work/proj-a",
                        "--run-id", "r1"]

    def test_worker_args_mock(self):
        s = RunnerSpec(tenant="acme", project="p", step_id="s", mock=True)
        assert s.worker_args()[-1] == "--mock"

    def test_resources_mapping(self):
        """GIVEN 限额 WHEN resources THEN 请求/限制分离。"""
        s = RunnerSpec(tenant="acme", project="p", step_id="s",
                       memory_limit="4Gi", cpu_limit="4")
        r = s.resources()
        assert r["limits"] == {"memory": "4Gi", "cpu": "4"}
        assert r["requests"] == {"memory": "128Mi", "cpu": "100m"}

    def test_manifest_structure(self):
        """GIVEN spec WHEN as_manifest THEN Job manifest 完整。"""
        s = RunnerSpec(tenant="acme", project="proj-a", step_id="spec-check")
        m = s.as_manifest()
        assert m["kind"] == "Job"
        assert m["apiVersion"] == "batch/v1"
        pod = m["spec"]["template"]["spec"]
        assert pod["restartPolicy"] == "Never"
        assert pod["securityContext"]["runAsNonRoot"] is True
        container = pod["containers"][0]
        assert container["image"].endswith("yuleosh/server:latest")
        assert "--step-id" in container["args"]
        assert container["volumeMounts"][0]["mountPath"] == "/work"
        assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "yuleosh-data-acme-data"


class TestQuotaManifest:
    def test_quota_manifest(self):
        q = quota_manifest("yuleosh", "acme", max_jobs=5)
        assert q["kind"] == "ResourceQuota"
        assert q["metadata"]["name"] == "yuleosh-quota-acme"
        assert q["spec"]["hard"]["count/jobs.batch"] == "5"
        assert q["spec"]["hard"]["limits.memory"] == "16Gi"
