#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
LoRA 训练数据准备（P2.2）。

从项目代码库提取训练样本，格式化为 LoRA 微调所需的 instruction-input-output 三元组。

设计要点:
- 支持 Python 和 C 代码（AUTOSAR 嵌入式场景）
- 提取函数/类签名 + 文档字符串 + 实现作为训练样本
- 生成 instruction（任务描述）+ input（上下文）+ output（代码）
- 支持 MISRA 合规样本（带注释的合规代码）
- 输出 JSONL 格式，兼容 Hugging Face datasets 和 Ollama

训练数据格式（Alpaca-style）:
{
  "instruction": "实现一个 GPIO 控制函数，符合 AUTOSAR 规范",
  "input": "// 函数签名\nvoid Gpio_SetPin(uint8 pin_id, boolean state);",
  "output": "void Gpio_SetPin(uint8 pin_id, boolean state) {\n    // 实现...\n}"
}

使用场景:
- 项目特定代码风格微调（如 AUTOSAR 命名规范）
- 领域知识增强（如 MISRA 规则）
- 降低幻觉（项目代码库锚定）
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("lora.data_prep")


# ═══════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TrainingSample:
    """LoRA 训练样本（Alpaca-style）。"""

    instruction: str  # 任务描述
    input: str  # 上下文（代码签名/注释）
    output: str  # 期望输出（完整代码）
    source_file: str = ""  # 源文件路径（溯源）
    language: str = "python"  # python | c
    category: str = "code_generation"  # code_generation | misra_compliance | review


@dataclass
class DataPrepReport:
    """数据准备报告。"""

    files_scanned: int = 0
    samples_extracted: int = 0
    samples_written: int = 0
    # 2026-11-02 (隐私): 因疑似含密钥被跳过的文件数
    files_skipped_secret: int = 0
    errors: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# 密钥扫描 (2026-11-02, 隐私红线)
# ═══════════════════════════════════════════════════════════════════════

# 训练数据会落盘 JSONL 并进入模型权重 — 含硬编码密钥的源码必须剔除,
# 否则推理时模型可能复述密钥。宁可漏杀 (误报跳过), 不可放过。
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                       # OpenAI-style
    re.compile(r"AKIA[0-9A-Z]{16}"),                           # AWS access key
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),        # PEM
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[=:]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                        # GitHub PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),               # Slack
]


def _contains_secret(content: str) -> str | None:
    """Return the matched pattern name if content looks like it holds a secret."""
    for pat in _SECRET_PATTERNS:
        if pat.search(content):
            return pat.pattern[:40]
    return None


# ═══════════════════════════════════════════════════════════════════════
# Python 代码提取
# ═══════════════════════════════════════════════════════════════════════

def _extract_python_samples(filepath: Path, content: str) -> list[TrainingSample]:
    """从 Python 文件提取训练样本。"""
    samples = []
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        log.debug("Failed to parse %s: %s", filepath, e)
        return samples

    for node in ast.walk(tree):
        # 函数定义
        if isinstance(node, ast.FunctionDef):
            sample = _extract_python_function(filepath, node, content)
            if sample:
                samples.append(sample)
        # 类定义
        elif isinstance(node, ast.ClassDef):
            sample = _extract_python_class(filepath, node, content)
            if sample:
                samples.append(sample)

    return samples


def _extract_python_function(
    filepath: Path, node: ast.FunctionDef, content: str
) -> Optional[TrainingSample]:
    """提取 Python 函数作为训练样本。"""
    # 跳过私有函数（_开头）和测试函数
    if node.name.startswith("_") or "test" in node.name.lower():
        return None

    # 提取函数源码
    start_line = node.lineno - 1
    end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 10
    func_code = "\n".join(content.split("\n")[start_line:end_line])

    # 提取文档字符串作为 instruction
    docstring = ast.get_docstring(node) or ""
    if docstring:
        instruction = docstring.split("\n")[0]  # 取第一行作为 instruction
    else:
        instruction = f"实现 {node.name} 函数"

    # 提取函数签名作为 input
    args = [arg.arg for arg in node.args.args if arg.arg != "self"]
    signature = f"def {node.name}({', '.join(args)})"

    return TrainingSample(
        instruction=instruction,
        input=signature,
        output=func_code,
        source_file=str(filepath),
        language="python",
        category="code_generation",
    )


def _extract_python_class(
    filepath: Path, node: ast.ClassDef, content: str
) -> Optional[TrainingSample]:
    """提取 Python 类作为训练样本。"""
    # 跳过私有类
    if node.name.startswith("_"):
        return None

    # 提取类源码
    start_line = node.lineno - 1
    end_line = node.end_lineno if hasattr(node, "end_lineno") else start_line + 20
    class_code = "\n".join(content.split("\n")[start_line:end_line])

    # 提取文档字符串
    docstring = ast.get_docstring(node) or ""
    if docstring:
        instruction = docstring.split("\n")[0]
    else:
        instruction = f"实现 {node.name} 类"

    # 类签名
    bases = [ast.unparse(base) for base in node.bases] if node.bases else []
    signature = f"class {node.name}"
    if bases:
        signature += f"({', '.join(bases)})"

    return TrainingSample(
        instruction=instruction,
        input=signature,
        output=class_code,
        source_file=str(filepath),
        language="python",
        category="code_generation",
    )


# ═══════════════════════════════════════════════════════════════════════
# C 代码提取
# ═══════════════════════════════════════════════════════════════════════

# C 函数定义正则（简化版，覆盖常见场景）
_C_FUNC_PATTERN = re.compile(
    r"^(\w[\w\s\*]+?)\s+(\w+)\s*\(([^)]*)\)\s*\{",
    re.MULTILINE,
)

# C 注释提取
_C_COMMENT_PATTERN = re.compile(r"/\*\s*(.*?)\s*\*/", re.DOTALL)


def _extract_c_samples(filepath: Path, content: str) -> list[TrainingSample]:
    """从 C 文件提取训练样本。"""
    samples = []

    # 提取函数定义
    for match in _C_FUNC_PATTERN.finditer(content):
        return_type = match.group(1).strip()
        func_name = match.group(2)
        params = match.group(3).strip()

        # 跳过静态函数和 main
        if "static" in return_type or func_name == "main":
            continue

        # 提取函数体（简化：取后续 50 行）
        start_pos = match.start()
        end_pos = min(start_pos + 2000, len(content))
        func_code = content[start_pos:end_pos].split("\n}")[0] + "\n}"

        # 提取函数前的注释作为 instruction
        preceding_text = content[max(0, start_pos - 500):start_pos]
        comment_match = _C_COMMENT_PATTERN.findall(preceding_text)
        if comment_match:
            instruction = comment_match[-1].split("\n")[0].strip()
        else:
            instruction = f"实现 {func_name} 函数"

        # 函数签名作为 input
        signature = f"{return_type} {func_name}({params});"

        samples.append(
            TrainingSample(
                instruction=instruction,
                input=signature,
                output=func_code,
                source_file=str(filepath),
                language="c",
                category="code_generation",
            )
        )

    return samples


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

def prepare_training_data(
    project_dir: Path,
    output_path: Path,
    languages: tuple[str, ...] = ("python", "c"),
    max_samples: int = 1000,
) -> DataPrepReport:
    """从项目代码库准备 LoRA 训练数据。

    Args:
        project_dir: 项目根目录
        output_path: 输出 JSONL 文件路径
        languages: 支持的语言（python, c）
        max_samples: 最大样本数（防止内存溢出）

    Returns:
        DataPrepReport: 数据准备报告
    """
    report = DataPrepReport()

    if not project_dir.exists():
        report.errors.append(f"Project directory not found: {project_dir}")
        return report

    # 收集所有源文件
    source_files = []
    for lang in languages:
        if lang == "python":
            source_files.extend(project_dir.rglob("*.py"))
        elif lang == "c":
            source_files.extend(project_dir.rglob("*.c"))
            source_files.extend(project_dir.rglob("*.h"))

    # 过滤测试文件和隐藏目录
    source_files = [
        f for f in source_files
        if not any(part.startswith(".") or part == "__pycache__" for part in f.parts)
        and "test" not in f.name.lower()
    ]

    log.info("Scanning %d source files in %s", len(source_files), project_dir)

    # 提取训练样本
    all_samples: list[TrainingSample] = []
    for filepath in source_files:
        report.files_scanned += 1
        try:
            content = filepath.read_text(encoding="utf-8")
            # 2026-11-02 (隐私红线): 疑似含密钥的源码不进训练数据
            hit = _contains_secret(content)
            if hit:
                report.files_skipped_secret += 1
                report.errors.append(
                    f"{filepath}: skipped — possible hardcoded secret ({hit}...)"
                )
                log.warning("Skipping %s — possible hardcoded secret", filepath)
                continue
            if filepath.suffix == ".py":
                samples = _extract_python_samples(filepath, content)
            elif filepath.suffix in (".c", ".h"):
                samples = _extract_c_samples(filepath, content)
            else:
                continue

            # source_file 统一相对化 — 不含本地用户名/绝对路径
            try:
                rel = filepath.resolve().relative_to(project_dir.resolve()).as_posix()
            except ValueError:
                rel = filepath.name
            for s in samples:
                s.source_file = rel

            all_samples.extend(samples)
            if len(all_samples) >= max_samples:
                log.info("Reached max_samples=%d, stopping extraction", max_samples)
                all_samples = all_samples[:max_samples]
                break

        except Exception as e:
            log.warning("Failed to extract samples from %s: %s", filepath, e)
            report.errors.append(f"{filepath}: {e}")

    report.samples_extracted = len(all_samples)
    log.info("Extracted %d training samples from %d files", len(all_samples), report.files_scanned)

    # 写入 JSONL
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for sample in all_samples:
                f.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
        report.samples_written = len(all_samples)
        log.info("Written %d samples to %s", report.samples_written, output_path)
    except Exception as e:
        log.error("Failed to write training data to %s: %s", output_path, e)
        report.errors.append(f"Write failed: {e}")

    return report


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 3:
        print("Usage: python -m yuleosh.lora.data_prep <project_dir> <output.jsonl>")
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    report = prepare_training_data(project_dir, output_path)
    print(f"\nData preparation complete:")
    print(f"  Files scanned: {report.files_scanned}")
    print(f"  Samples extracted: {report.samples_extracted}")
    print(f"  Samples written: {report.samples_written}")
    if report.errors:
        print(f"  Errors: {len(report.errors)}")
        for err in report.errors[:5]:
            print(f"    - {err}")
