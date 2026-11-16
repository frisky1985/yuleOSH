#!/usr/bin/env python3
"""
yuleOSH · 真实 LLM 流水线验证（DeepSeek 云端 / Ollama 本地通用）
================================================================

目的：用真实模型（非 mock）跑通核心流水线步骤，验证：
  1. Provider 路由与 API Key 生效（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）
  2. 每一步的真实 LLM 调用次数 / token 用量 / 耗时
  3. 产物落盘且内容来自模型（非模板占位符）
  4. 编排器并行组、检查点、会话记录工作正常

默认只跑核心链路（--core-only）：spec-check → super-analysis → prd →
prd-review → architecture → arch-review → development，避免 102 个子步骤的
完整流水线（真实 LLM 下成本与时间不可控）。要跑全部步骤加 --full。

用法：
  export DEEPSEEK_API_KEY=sk-xxx
  python3 scripts/llm_verify_pipeline.py

  # 本地 Ollama
  python3 scripts/llm_verify_pipeline.py --provider ollama --model qwen2.5-coder:7b

  # 保留工程目录供人工查看产物
  python3 scripts/llm_verify_pipeline.py --keep
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORE_STEPS = [
    "spec-check",
    "super-analysis",
    "prd",
    "prd-review",
    "architecture",
    "arch-review",
    "development",
]

MINIMAL_SPEC = """\
# 最小演示工程 · 裸机 ARM Cortex-M 的 LED/UART 子系统

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
"""

ARTIFACT_SIGNALS = {
    "prd": ["SHALL", "LED", "UART", "看门狗", "需求"],
    "architecture": ["模块", "UART", "GPIO", "架构", "分层"],
    "development": ["#include", "int main", "GPIO", "UART"],
}


# ── Provider 准备 ───────────────────────────────────────────────────────────

def probe_ollama(base_url: str) -> dict:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return {"ok": True, "models": [m["name"] for m in data.get("models", [])]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def configure_env(args) -> None:
    provider = args.provider
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
    if provider == "deepseek":
        if not api_key:
            raise SystemExit("❌ 未提供 DeepSeek API Key（--api-key 或 DEEPSEEK_API_KEY）")
        os.environ.update({
            "YULEOSH_LLM_PROVIDER": "deepseek",
            "LLM_BASE_URL": args.base_url or "https://api.deepseek.com",
            "LLM_API_KEY": api_key,
            "LLM_MODEL": args.model,
        })
    else:  # ollama
        os.environ.update({
            "YULEOSH_LLM_PROVIDER": "deepseek",  # OpenAI 兼容路径
            "LLM_BASE_URL": args.base_url or "http://localhost:11434",
            "LLM_API_KEY": api_key or "ollama",
            "LLM_MODEL": args.model,
        })
    workdir = str(Path(args.workdir).resolve())
    # OSH_HOME 同时决定 repo_facts 的扫描根（默认回退到 cwd），必须显式指向
    # 演示工程目录，否则架构分析会把启动脚本所在的仓库当成目标工程。
    os.environ.setdefault("OSH_HOME", workdir)
    os.environ.setdefault("OSH_SESSIONS_DIR", str(Path(workdir) / ".osh" / "sessions"))
    if args.codegen:
        # D3: development 步骤改为真实代码生成（而非仅输出计划）
        os.environ["OSH_DEVELOPMENT_MODE"] = "generate-code"


# ── 流水线执行 ───────────────────────────────────────────────────────────────

class LLMRecorder:
    """包装真实 chat_completion，记录调用次数、耗时与 token 用量。"""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, system_prompt, user_prompt, **kwargs):
        from yuleosh.llm.client import chat_completion

        t0 = time.time()
        resp = chat_completion(system_prompt, user_prompt, **kwargs)
        elapsed = time.time() - t0
        usage = (resp or {}).get("usage") or {}
        self.calls.append({
            "elapsed": round(elapsed, 1),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "system_chars": len(system_prompt or ""),
            "user_chars": len(user_prompt or ""),
            "model": (resp or {}).get("model"),
        })
        print(f"    ↳ LLM 调用 #{len(self.calls)}  {elapsed:.1f}s  "
              f"prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}",
              flush=True)
        return resp


def run_core_pipeline(spec_path: Path, workdir: Path, full: bool,
                      steps: list[str] | None = None) -> dict:
    from yuleosh.pipeline import step_handlers
    from yuleosh.pipeline.orchestrator import run_pipeline

    if not full:
        wanted = set(steps or CORE_STEPS)
        original = list(step_handlers.PIPELINE_STEPS)
        subset = [s for s in original if s[0] in wanted]
        missing = wanted - {s[0] for s in subset}
        if missing:
            raise SystemExit(f"❌ 未知步骤：{', '.join(sorted(missing))}")
        step_handlers.PIPELINE_STEPS[:] = subset  # 原地修改，run shim 共享同一 list 对象
        print(f"🎯 子集模式：{len(subset)}/{len(original)} 步 "
              f"({', '.join(s[0] for s in subset)})\n", flush=True)

    recorder = LLMRecorder()
    t0 = time.time()
    session = run_pipeline(
        str(spec_path),
        name=f"llm-verify-{time.strftime('%Y%m%d-%H%M%S')}",
        llm_client=recorder,
        mock=False,
    )
    elapsed = time.time() - t0
    return {"session": session, "recorder": recorder, "elapsed": elapsed}


# ── 产物校验 ─────────────────────────────────────────────────────────────────

def verify_artifacts(session_dir: Path, steps_run: set[str] | None = None) -> list[dict]:
    results = []
    for key, signals in ARTIFACT_SIGNALS.items():
        if steps_run is not None and key not in steps_run:
            continue
        candidates = [p for p in session_dir.rglob("*") if p.is_file() and key in p.name.lower()]
        if not candidates:
            candidates = [p for p in session_dir.rglob("*.md") if key in p.read_text(errors="ignore").lower()]
        if not candidates:
            results.append({"step": key, "path": None, "status": "MISSING"})
            continue
        p = max(candidates, key=lambda x: x.stat().st_size)
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = sum(1 for s in signals if s.lower() in text.lower())
        results.append({
            "step": key,
            "path": str(p.relative_to(session_dir)),
            "status": "OK" if hits >= 2 else "SUSPICIOUS",
            "hits": hits,
            "chars": len(text),
        })
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["deepseek", "ollama"], default="deepseek")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--workdir", default="/tmp/yuleosh-llm-verify")
    ap.add_argument("--spec", default=None, help="使用既有工程规格（不重建工作目录）")
    ap.add_argument("--steps", default=None, help="逗号分隔的步骤名，覆盖默认核心链路")
    ap.add_argument("--codegen", action="store_true", help="development 步骤真实生成代码")
    ap.add_argument("--full", action="store_true", help="跑完整 102 步（默认仅核心链路）")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    steps = [s.strip() for s in args.steps.split(",") if s.strip()] if args.steps else None

    if args.model is None:
        args.model = "deepseek-chat" if args.provider == "deepseek" else "qwen2.5-coder:7b"

    print("🔎  yuleOSH · 真实 LLM 流水线验证")
    print(f"   provider : {args.provider}")
    print(f"   model    : {args.model}")
    print(f"   base_url : {args.base_url or ('https://api.deepseek.com' if args.provider == 'deepseek' else 'http://localhost:11434')}")
    print(f"   workdir  : {args.workdir}\n")

    if args.provider == "ollama":
        probe = probe_ollama(args.base_url or "http://localhost:11434")
        if not probe["ok"]:
            print(f"❌ Ollama 不可用：{probe['error']}\n   请先执行 ollama serve")
            return 2
        print(f"✅ Ollama 可达，模型：{', '.join(probe['models']) or '(空)'}")

    configure_env(args)

    workdir = Path(args.workdir).resolve()
    if args.spec:
        spec = Path(args.spec).resolve()
        if not spec.is_file():
            raise SystemExit(f"❌ spec 不存在：{spec}")
        print(f"✅ 使用既有 spec：{spec}（{spec.stat().st_size} bytes）\n", flush=True)
    else:
        if workdir.exists():
            shutil.rmtree(workdir)
        (workdir / "docs").mkdir(parents=True)
        spec = workdir / "docs" / "minimal-demo-spec.md"
        spec.write_text(MINIMAL_SPEC, encoding="utf-8")
        print(f"✅ 最小 spec：{spec}（{len(MINIMAL_SPEC)} chars）\n", flush=True)

    try:
        out = run_core_pipeline(spec, workdir, args.full, steps)
    except SystemExit as e:
        print(f"❌ 流水线提前退出：{e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"\n❌ 流水线异常：{e}")
        return 1

    session = out["session"]
    recorder = out["recorder"]
    session_dir = Path(session.session_dir)

    print("\n" + "=" * 72)
    print("📊  真实 LLM 流水线验证报告")
    print("=" * 72)
    print(f"  会话        : {session.name}  ({session.run_id})")
    print(f"  最终状态    : {session.status}")
    print(f"  总耗时      : {out['elapsed']:.1f}s")
    print(f"  LLM 调用    : {len(recorder.calls)} 次")
    pt = sum(c["prompt_tokens"] or 0 for c in recorder.calls)
    ct = sum(c["completion_tokens"] or 0 for c in recorder.calls)
    print(f"  Token 用量  : prompt={pt} completion={ct} total={pt + ct}")
    models = {c["model"] for c in recorder.calls if c["model"]}
    if models:
        print(f"  实际模型    : {', '.join(sorted(models))}")
    print()
    print("  步骤状态：")
    for s in session.steps:
        print(f"    {s.get('status', '?'):<10} {s.get('name', ''):<18} {s.get('action', '')}")
    print()
    print("  产物验证：")
    steps_run = {s.get("action", "") for s in session.steps}
    artifacts = verify_artifacts(session_dir, steps_run)
    for a in artifacts:
        if a["status"] == "MISSING":
            print(f"    ❌ {a['step']:<14} 未找到产物")
        else:
            mark = "✅" if a["status"] == "OK" else "⚠️ "
            print(f"    {mark} {a['step']:<14} {a['path']:<40} {a['chars']:>6} chars")

    if args.codegen:
        code_root = workdir / "artifacts" / "generated-code"
        generated = sorted(code_root.rglob("*.c")) + sorted(code_root.rglob("*.h"))
        print(f"\n  生成代码：{len(generated)} 个文件（{code_root}）")
        for p in generated[:12]:
            print(f"    • {p.relative_to(code_root)}  {p.stat().st_size:>6} bytes")
        if not generated:
            print("    ❌ 未找到生成代码")
    print()
    ok = (
        session.status == "completed"
        and all(a["status"] == "OK" for a in artifacts)
        and (not args.codegen or bool(list((workdir / "artifacts" / "generated-code").rglob("*.c"))))
    )
    print(f"  🎯 结论：{'真实 LLM 流水线跑通' if ok else '存在未通过项，见上方明细'}")
    print(f"  会话目录：{session_dir}")
    print("=" * 72 + "\n")

    if not args.keep and ok:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
