# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
K8s runner spec builder — 生成 pipeline runner Job 的 k8s 对象（EI-M2C）。

与 Helm 模板互补：Helm 用于集群安装时静态渲染；本模块提供 Python 侧
spec 生成（调度器/API 动态提交任务时用），并承担单元可测逻辑
（限额映射 / 名称构造 / PVC 解析）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunnerSpec:
    """单次 pipeline 步骤的 k8s Job 配置。"""

    tenant: str
    project: str
    step_id: str
    run_id: str = "r0"
    image: str = "yuleosh/server:latest"
    memory_limit: str = "2Gi"
    cpu_limit: str = "2"
    memory_request: str = "128Mi"
    cpu_request: str = "100m"
    pvc_name: Optional[str] = None
    pvc_prefix: str = "yuleosh-data"
    mock: bool = False
    labels: dict[str, str] = field(default_factory=dict)

    def job_name(self) -> str:
        """Job 名称（EI-M2C.1 命名规则）。"""
        return f"yuleosh-runner-{self.tenant}-{self.run_id}"

    def resolve_pvc(self) -> str:
        """租户 PVC 名（EI-M2C.2）：显式优先，否则 <prefix>-<tenant>-data。"""
        return self.pvc_name or f"{self.pvc_prefix}-{self.tenant}-data"

    def pod_labels(self) -> dict[str, str]:
        """Pod 标签（NetworkPolicy 选择器用，EI-M2C.3）。"""
        labels = {
            "app.kubernetes.io/component": "runner",
            "yuleosh.io/tenant": self.tenant,
        }
        labels.update(self.labels)
        return labels

    def worker_args(self) -> list[str]:
        """worker 命令参数。"""
        args = [
            "--step-id", self.step_id,
            "--project-dir", f"/work/{self.project}",
            "--run-id", self.run_id,
        ]
        if self.mock:
            args.append("--mock")
        return args

    def resources(self) -> dict:
        """容器资源声明（限额映射）。"""
        return {
            "requests": {
                "memory": self.memory_request,
                "cpu": self.cpu_request,
            },
            "limits": {
                "memory": self.memory_limit,
                "cpu": self.cpu_limit,
            },
        }

    def as_manifest(self) -> dict:
        """生成 Job manifest dict（供 kubectl/客户端提交）。"""
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": self.job_name(),
                "labels": self.pod_labels(),
            },
            "spec": {
                "backoffLimit": 1,
                "ttlSecondsAfterFinished": 3600,
                "template": {
                    "metadata": {"labels": self.pod_labels()},
                    "spec": {
                        "restartPolicy": "Never",
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "fsGroup": 1000,
                        },
                        "containers": [{
                            "name": "runner",
                            "image": self.image,
                            "command": [
                                "python", "-m",
                                "yuleosh.engine.subprocess_executor", "worker",
                            ],
                            "args": self.worker_args(),
                            "env": [{"name": "OSH_HOME", "value": f"/work/{self.project}"}],
                            "resources": self.resources(),
                            "volumeMounts": [{
                                "name": "tenant-data",
                                "mountPath": "/work",
                            }],
                        }],
                        "volumes": [{
                            "name": "tenant-data",
                            "persistentVolumeClaim": {
                                "claimName": self.resolve_pvc(),
                            },
                        }],
                    },
                },
            },
        }


def quota_manifest(prefix: str, tenant: str,
                   requests_mem: str = "8Gi", limits_mem: str = "16Gi",
                   max_jobs: int = 10) -> dict:
    """per-tenant ResourceQuota manifest（EI-M2C.3）。"""
    return {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {
            "name": f"{prefix}-quota-{tenant}",
            "labels": {"yuleosh.io/tenant": tenant},
        },
        "spec": {
            "hard": {
                "requests.cpu": "4",
                "requests.memory": requests_mem,
                "limits.cpu": "8",
                "limits.memory": limits_mem,
                "count/jobs.batch": str(max_jobs),
            },
        },
    }
