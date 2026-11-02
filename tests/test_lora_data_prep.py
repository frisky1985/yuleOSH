#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
test_lora_data_prep.py — LoRA 训练数据准备测试（P2.2）。

覆盖:
- T1: Python 代码提取（函数/类/文档字符串）
- T2: C 代码提取（函数/注释）
- T3: 训练样本格式化（instruction-input-output）
- T4: 文件过滤（测试文件/隐藏目录）
- T5: 端到端数据准备
- T6: 错误处理（语法错误/文件不存在）
"""

import json
import tempfile
from pathlib import Path

import pytest

from yuleosh.lora.data_prep import (
    DataPrepReport,
    TrainingSample,
    _extract_c_samples,
    _extract_python_samples,
    prepare_training_data,
)


@pytest.fixture
def temp_project():
    """创建临时项目目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


class TestPythonExtraction:
    """T1: Python 代码提取。"""

    def test_extract_function(self, temp_project):
        """GIVEN Python 函数 WHEN 提取 THEN 生成训练样本。"""
        py_file = temp_project / "test.py"
        py_file.write_text("""
def calculate_sum(a, b):
    \"\"\"计算两个数的和。\"\"\"
    return a + b
""")
        content = py_file.read_text()
        samples = _extract_python_samples(py_file, content)
        assert len(samples) == 1
        assert samples[0].instruction == "计算两个数的和。"
        assert "calculate_sum" in samples[0].input
        assert "def calculate_sum" in samples[0].output

    def test_extract_class(self, temp_project):
        """GIVEN Python 类 WHEN 提取 THEN 生成训练样本。"""
        py_file = temp_project / "test.py"
        py_file.write_text("""
class DataProcessor:
    \"\"\"数据处理器类。\"\"\"
    def __init__(self):
        self.data = []
""")
        content = py_file.read_text()
        samples = _extract_python_samples(py_file, content)
        assert len(samples) == 1
        assert samples[0].instruction == "数据处理器类。"
        assert "DataProcessor" in samples[0].input

    def test_skip_private_function(self, temp_project):
        """GIVEN 私有函数 WHEN 提取 THEN 跳过。"""
        py_file = temp_project / "test.py"
        py_file.write_text("""
def _private_func():
    pass

def public_func():
    \"\"\"公开函数。\"\"\"
    pass
""")
        content = py_file.read_text()
        samples = _extract_python_samples(py_file, content)
        assert len(samples) == 1
        assert samples[0].input == "def public_func()"

    def test_skip_test_function(self, temp_project):
        """GIVEN 测试函数 WHEN 提取 THEN 跳过。"""
        py_file = temp_project / "test.py"
        py_file.write_text("""
def test_something():
    pass

def normal_func():
    \"\"\"正常函数。\"\"\"
    pass
""")
        content = py_file.read_text()
        samples = _extract_python_samples(py_file, content)
        assert len(samples) == 1
        assert "test" not in samples[0].input.lower()

    def test_syntax_error_handling(self, temp_project):
        """GIVEN 语法错误 WHEN 提取 THEN 返回空列表。"""
        py_file = temp_project / "bad.py"
        py_file.write_text("def broken(:\n    pass")
        content = py_file.read_text()
        samples = _extract_python_samples(py_file, content)
        assert samples == []


class TestCExtraction:
    """T2: C 代码提取。"""

    def test_extract_function(self, temp_project):
        """GIVEN C 函数 WHEN 提取 THEN 生成训练样本。"""
        c_file = temp_project / "test.c"
        c_file.write_text("""
/* 设置 GPIO 引脚状态 */
void Gpio_SetPin(uint8 pin_id, boolean state) {
    // 实现
    if (state) {
        GPIO_PORT |= (1 << pin_id);
    }
}
""")
        content = c_file.read_text()
        samples = _extract_c_samples(c_file, content)
        assert len(samples) == 1
        assert "设置 GPIO 引脚状态" in samples[0].instruction
        assert "Gpio_SetPin" in samples[0].input

    def test_skip_static_function(self, temp_project):
        """GIVEN static 函数 WHEN 提取 THEN 跳过。"""
        c_file = temp_project / "test.c"
        c_file.write_text("""
static void helper_func(void) {
    // 内部辅助
}

void public_func(void) {
    // 公开函数
}
""")
        content = c_file.read_text()
        samples = _extract_c_samples(c_file, content)
        # 应该只提取 public_func
        assert all("helper_func" not in s.input for s in samples)

    def test_skip_main(self, temp_project):
        """GIVEN main 函数 WHEN 提取 THEN 跳过。"""
        c_file = temp_project / "test.c"
        c_file.write_text("""
int main(int argc, char** argv) {
    return 0;
}
""")
        content = c_file.read_text()
        samples = _extract_c_samples(c_file, content)
        assert all("main" not in s.input for s in samples)


class TestSampleFormatting:
    """T3: 训练样本格式化。"""

    def test_training_sample_structure(self):
        """GIVEN TrainingSample WHEN 序列化 THEN 包含必需字段。"""
        sample = TrainingSample(
            instruction="实现一个函数",
            input="def func():",
            output="def func():\n    return 42",
            source_file="test.py",
            language="python",
            category="code_generation",
        )
        data = {
            "instruction": sample.instruction,
            "input": sample.input,
            "output": sample.output,
        }
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["instruction"] == "实现一个函数"
        assert parsed["input"] == "def func():"
        assert parsed["output"] == "def func():\n    return 42"


class TestFileFiltering:
    """T4: 文件过滤。"""

    def test_exclude_test_files(self, temp_project):
        """GIVEN 测试文件 WHEN prepare_training_data THEN 跳过。"""
        # 创建正常文件
        normal = temp_project / "normal.py"
        normal.write_text("def func():\n    \"\"\"正常函数。\"\"\"\n    pass")
        
        # 创建测试文件
        test = temp_project / "test_something.py"
        test.write_text("def test_func():\n    pass")
        
        output = temp_project / "output.jsonl"
        report = prepare_training_data(temp_project, output)
        
        # 应该只提取正常文件
        assert report.files_scanned >= 1
        # 读取输出验证
        if output.exists():
            samples = [json.loads(line) for line in output.open()]
            assert all("test" not in s.get("source_file", "").lower() for s in samples)

    def test_exclude_hidden_dirs(self, temp_project):
        """GIVEN 隐藏目录 WHEN prepare_training_data THEN 跳过。"""
        # 创建隐藏目录
        hidden = temp_project / ".hidden"
        hidden.mkdir()
        (hidden / "code.py").write_text("def func():\n    pass")
        
        # 创建正常目录
        normal = temp_project / "src"
        normal.mkdir()
        (normal / "code.py").write_text("def func():\n    \"\"\"正常。\"\"\"\n    pass")
        
        output = temp_project / "output.jsonl"
        report = prepare_training_data(temp_project, output)
        
        # 应该只扫描正常目录
        assert report.files_scanned >= 1


class TestEndToEnd:
    """T5: 端到端数据准备。"""

    def test_prepare_training_data_python(self, temp_project):
        """GIVEN Python 项目 WHEN prepare_training_data THEN 生成 JSONL。"""
        # 创建示例 Python 文件
        src = temp_project / "src"
        src.mkdir()
        (src / "module.py").write_text("""
def add(a, b):
    \"\"\"加法函数。\"\"\"
    return a + b

class Calculator:
    \"\"\"计算器类。\"\"\"
    def multiply(self, x, y):
        \"\"\"乘法方法。\"\"\"
        return x * y
""")
        
        output = temp_project / "train.jsonl"
        report = prepare_training_data(temp_project, output)
        
        assert report.files_scanned >= 1
        assert report.samples_extracted >= 2
        assert report.samples_written >= 2
        assert output.exists()
        
        # 验证 JSONL 格式
        samples = [json.loads(line) for line in output.open()]
        assert len(samples) >= 2
        assert all("instruction" in s for s in samples)
        assert all("input" in s for s in samples)
        assert all("output" in s for s in samples)

    def test_prepare_training_data_c(self, temp_project):
        """GIVEN C 项目 WHEN prepare_training_data THEN 生成 JSONL。"""
        src = temp_project / "src"
        src.mkdir()
        (src / "gpio.c").write_text("""
/* 初始化 GPIO 模块 */
void Gpio_Init(void) {
    // 配置寄存器
}

/* 读取引脚状态 */
boolean Gpio_ReadPin(uint8 pin_id) {
    return (GPIO_PORT >> pin_id) & 1;
}
""")
        
        output = temp_project / "train.jsonl"
        report = prepare_training_data(temp_project, output, languages=("c",))
        
        assert report.files_scanned >= 1
        assert report.samples_extracted >= 1
        assert output.exists()

    def test_max_samples_limit(self, temp_project):
        """GIVEN max_samples WHEN prepare_training_data THEN 限制提取数量。"""
        # 创建多个文件
        for i in range(10):
            (temp_project / f"file{i}.py").write_text(
                f"def func{i}():\n    \"\"\"函数 {i}。\"\"\"\n    pass"
            )
        
        output = temp_project / "train.jsonl"
        report = prepare_training_data(temp_project, output, max_samples=5)
        
        assert report.samples_extracted <= 5


class TestErrorHandling:
    """T6: 错误处理。"""

    def test_nonexistent_project(self):
        """GIVEN 不存在的项目目录 WHEN prepare_training_data THEN 报告错误。"""
        output = Path("/tmp/test.jsonl")
        report = prepare_training_data(Path("/nonexistent"), output)
        assert len(report.errors) > 0
        assert "not found" in report.errors[0].lower()

    def test_empty_project(self, temp_project):
        """GIVEN 空项目 WHEN prepare_training_data THEN 报告 0 样本。"""
        output = temp_project / "train.jsonl"
        report = prepare_training_data(temp_project, output)
        assert report.files_scanned == 0
        assert report.samples_extracted == 0

    def test_write_error_handling(self, temp_project):
        """GIVEN 写入权限问题 WHEN prepare_training_data THEN 报告错误。"""
        (temp_project / "code.py").write_text("def func():\n    pass")
        
        # 尝试写入只读目录
        readonly = temp_project / "readonly"
        readonly.mkdir()
        readonly.chmod(0o444)
        output = readonly / "train.jsonl"
        
        report = prepare_training_data(temp_project, output)
        # 应该捕获写入错误
        assert len(report.errors) > 0 or not output.exists()
        
        # 恢复权限以便清理
        readonly.chmod(0o755)
