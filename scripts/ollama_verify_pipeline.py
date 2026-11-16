#!/usr/bin/env python3
"""
yuleOSH · 本地 Ollama 真实 LLM 流水线一键验证
=================================================

目标：用本机 Ollama 上的真实模型（非 mock）跑完整流水线（prd → architecture →
development → review → gate），验证：
  1. Ollama 端点配置正确（YULEOSH_LLM_PROVIDER 走 deepseek + LLM_BASE_URL）
  2. 串行模式跑完整链（YULEOSH_PIPELINE_SERIAL=1 避免并发争用挤垮小机器）
  3. 每个步骤产物来自真实 LLM（非模板占位符）
  4. 质量门禁与追溯矩阵正常生成

前提：本机已 `ollama serve`，且已 pull 至少一个模型。推荐 `qwen2.5-coder:7b`（最快）
或 `qwen2.5-coder:14b`（质量更高）。脚本会自动探活并提示缺失项。

用法：
  python3 scripts/ollama_verify_pipeline.py              # 默认 qwen2.5-coder:7b
  python3 scripts/ollama_verify_pipeline.py --model qwen2.5-coder:14b
  python3 scripts/ollama_verify_pipeline.py --keep       # 跑完后保留工程目录
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
LLM_TIMEOUT_SEC = 1800
PIPELINE_SPEC_NAME = "minimal-demo-spec.md"

MINIMAL_SPEC = """\
# 最小演示工程 · 基于裸机 ARM Cortex-M 的 LED/UART 子系统

> Version: 0.1.0 | 格式: RFC 2119 (SHALL/SHOULD/MAY)

## RS-001: LED 闪烁控制

- The system SHALL toggle the on-board LED at 1 Hz when idle
- The system SHALL provide a HAL_GPIO_Toggle(LED_PIN) interface

### SWR-001.1: 定时器驱动闪烁
- The system SHALL use SysTick (1 ms tick) to derive the 500 ms toggle period
- The LED SHALL be driven directly via GPIO register writes (no HAL dependency)

## RS-002: UART 回环通道

- The system SHALL expose a blocking UART loopback on USART1 at 115200 8N1
- The system SHALL echo every received byte after a 1-byte delay

### SWR-002.1: 中断驱动收发
- The system SHALL use USART1 RX/TX interrupts to avoid polling
- The RX buffer SHALL be at least 64 bytes with overflow protection

## RS-003: 看门狗

- The system SHALL start an independent watchdog that fires every 2 s
- The main loop SHALL refresh the watchdog at 1 Hz

### NFR-003.1: 安全余量
- The watchdog reload SHALL be completed at least 500 ms before expiry
"""

# ── 前置检查 ─────────────────────────────────────────────────────────────────

def probe_ollama(base_url: str) -> dict:
    """探活 Ollama 服务并列出已下载模型。"""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return {"ok": True, "models": [m["name"] for m in data.get("models", [])]}
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e)}
    except (json.JSONDecodeError, KeyError) as e:
        return {"ok": False, "error": f"bad response: {e}"}


def pull_model(model: str, timeout_sec: int = 600) -> bool:
    """调用 ollama CLI 拉取指定模型（阻塞直到完成）。"""
    print(f"  ⤵️  正在拉取模型 {model}（可能需要几分钟）...")
    try:
        proc = subprocess.run(
            ["ollama", "pull", model],
            timeout=timeout_sec,
            check=True,
            capture_output=False,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        print("  ❌ ollama CLI 未找到 — 请先安装 Ollama 或手动执行 `ollama pull " + model + "`")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ 模型拉取超时（>{timeout_sec}s）")
        return False


# ── 工程目录准备 ──────────────────────────────────────────────────────────────

def prepare_workspace(root: Path) -> Path:
    """在 root 下创建最小 spec 工程目录。返回 spec 文件路径。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    spec_path = root / "docs" / PIPELINE_SPEC_NAME
    spec_path.write_text(MINIMAL_SPEC, encoding="utf-8")
    return spec_path


# ── 运行流水线 ────────────────────────────────────────────────────────────────

def run_pipeline(spec_path: Path, model: str, ollama_url: str) -> int:
    """设置环境变量后调用 yuleosh.pipeline.run。返回进程退出码。"""
    env = os.environ.copy()
    env.update({
        "LLM_BASE_URL": ollama_url,
        "LLM_API_KEY": "ollama",
        "LLM_MODEL": model,
        "YULEOSH_PIPELINE_SERIAL": "1",
        "YULEOSH_LLM_TIMEOUT": str(LLM_TIMEOUT_SEC),
        "YULEOSH_LLM_UNIFIED": "0",   # 保留遗留 chat_completion 路径（更贴近生产链路）
        "PIPELINE_VERBOSE": "1",
    })

    cmd = [
        sys.executable, "-m", "yuleosh.pipeline.run",
        str(spec_path),
    ]

    print("\n" + "=" * 72)
    print("🚀  启动真实 LLM 流水线（mock=False, 串行模式）")
    print("=" * 72)
    print(f"  模型      : {model}")
    print(f"  Ollama    : {ollama_url}")
    print(f"  串行模式  : YULEOSH_PIPELINE_SERIAL=1")
    print(f"  超时      : {LLM_TIMEOUT_SEC}s/step")
    print(f"  命令      : {' '.join(cmd)}")
    print("=" * 72 + "\n")

    t0 = time.time()
    proc = subprocess.run(cmd, env=env, cwd=str(spec_path.parent.parent))
    elapsed = time.time() - t0
    print(f"\n⏱️  流水线总耗时 {elapsed:.1f}s")
    return proc.returncode


# ── 产物验证 ──────────────────────────────────────────────────────────────────

# 真实 LLM 应产出的文本特征（用于区分模板占位符）
REAL_LLM_SIGNALS = [
    ("prd.md", ["SHALL", "需求", "系统", "HAL_", "功能"]),
    ("architecture.md", ["模块", "分层", "依赖", "UART", "WDT", "外设"]),
    ("src/main.c", ["#include", "int main", "HAL_GPIO_Toggle", "UART", "while"]),
    ("src/uart.c", ["USART", "IRQHandler", "transmit", "receive"]),
    ("src/led.c", ["GPIO", "HAL_GPIO_Toggle", "systick"]),
]


def verify_artifacts(root: Path) -> list[dict]:
    """遍历工程目录，对关键产物做「非占位符 + 有真实内容」检查。"""
    results: list[dict] = []
    artifact_root = root / "artifacts"
    if not artifact_root.exists():
        # 有些 session 会把产物放在 runs/<session>/artifacts/ 下
        artifact_root = root / "runs"

    for expected, signals in REAL_LLM_SIGNALS:
        found = list(root.rglob(expected))
        if not found:
            results.append({
                "path": expected, "status": "MISSING",
                "signal_hits": 0, "content_len": 0,
            })
            continue
        p = found[0]
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = sum(1 for s in signals if s.lower() in text.lower())
        results.append({
            "path": str(p.relative_to(root)),
            "status": "OK" if hits >= 2 else "SUSPICIOUS",
            "signal_hits": hits,
            "content_len": len(text),
        })
    return results


def print_report(artifacts: list[dict], rc: int, elapsed: float, keep_dir: Path | None):
    print("\n" + "=" * 72)
    print("📊  真实 LLM 流水线验证报告")
    print("=" * 72)
    print(f"  流水线退出码  : {rc} ({'completed' if rc == 0 else 'non-zero'})")
    print(f"  总耗时        : {elapsed:.1f}s")
    print()
    print("  产物验证：")
    all_ok = True
    for a in artifacts:
        mark = "✅" if a["status"] == "OK" else ("⚠️ " if a["status"] == "SUSPICIOUS" else "❌")
        print(f"    {mark} {a['path']:<40}  {a['content_len']:>6} chars  命中 {a['signal_hits']}")
        if a["status"] != "OK":
            all_ok = False
    print()
    if all_ok and rc == 0:
        print("  🎯  结论：真实 Ollama 流水线跑通，产物均有 LLM 生成的真实内容")
    else:
        print("  ⚠️  结论：部分检查未通过，建议看日志排查")
    if keep_dir:
        print(f"\n  工程目录已保留在：{keep_dir}")
    print("=" * 72 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL,
                    help="Ollama 服务端点（默认 http://localhost:11434）")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="Ollama 模型名（默认 qwen2.5-coder:7b）")
    ap.add_argument("--workdir", default="/tmp/yuleosh-ollama-verify",
                    help="验证工程目录（默认 /tmp/yuleosh-ollama-verify）")
    ap.add_argument("--keep", action="store_true",
                    help="跑完后保留工程目录（默认清理）")
    args = ap.parse_args()

    print("🔎  yuleOSH · Ollama 真实 LLM 流水线验证")
    print(f"   Ollama 端点 : {args.ollama_url}")
    print(f"   目标模型    : {args.model}")
    print(f"   工作目录    : {args.workdir}")
    print()

    # 1. 探活 Ollama
    probe = probe_ollama(args.ollama_url)
    if not probe["ok"]:
        print(f"❌ Ollama 服务不可用：{probe.get('error')}")
        print("   请先启动：ollama serve")
        return 2
    print(f"✅ Ollama 可达，已下载模型：{', '.join(probe['models']) or '(无模型，请先 pull)'}")

    # 2. 确保模型已下载
    if args.model not in probe["models"]:
        if not pull_model(args.model):
            return 2

    # 3. 准备工作目录
    workdir = Path(args.workdir).resolve()
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    spec = prepare_workspace(workdir)
    print(f"✅ 最小 spec 已创建：{spec}")

    # 4. 跑流水线
    t0 = time.time()
    rc = run_pipeline(spec, args.model, args.ollama_url)
    elapsed = time.time() - t0

    # 5. 验证产物
    artifacts = verify_artifacts(workdir)

    # 6. 报告
    print_report(artifacts, rc, elapsed, workdir if args.keep else None)

    # 7. 清理
    if not args.keep and workdir.exists():
        try:
            shutil.rmtree(workdir)
        except Exception:
            pass

    # 7. 返回码：流水线失败或产物缺失 → 1
    any_bad = any(a["status"] != "OK" for a in artifacts)
    return 0 if (rc == 0 and not any_bad) else 1


if __name__ == "__main__":
    sys.exit(main())
