# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

# NOTE (AR-P2-03): setup.py is kept for legacy compatibility (pip install -e .).
# All project metadata is now defined in pyproject.toml. This file will be
# removed when all CI workflows and documentation reference pyproject.toml.

from setuptools import setup, find_packages

setup(
    name="yuleosh",
    version="4.2.0",
    description="嵌入式AI开发全流程平台 — OpenSpec+Superpowers+Harness Engineering 三位一体",
    packages=find_packages(where=["src"]),
    package_dir={"": "src"},
    python_requires=">=3.12,<3.14",
    install_requires=[
        "pyyaml>=6.0",
        "msgpack>=1.2.1",  # GHSA-6v7p-g79w-8964
        "starlette>=1.3.0",  # PYSEC-2026-161
        "click>=8.3.3",  # PYSEC-2026-2132
        "pillow>=12.3.0",  # Multiple CVEs
        "jinja2>=3.1.0",
        "openpyxl>=3.1.0",  # evidence/excel_writer.py 依赖
        "cryptography>=42.0",  # SEC-PK: 加密存储 API Key（provider_secrets 保险库）
        "tree-sitter>=0.25.2,<1.0",  # B-M1: C AST 扫描器核心库
        "tree-sitter-c>=0.23.0",  # B-M1: C 语言 grammar
    ],
    extras_require={
        "saas": ["bcrypt>=5.0", "pyjwt>=2.13", "psycopg2-binary>=2.9", "pyserial>=3.5", "stripe>=15.0"],
        "dev": ["pytest", "pytest-cov", "pytest-mock"],
    },
    # NOTE: console_scripts entry point is defined in pyproject.toml
    # (yuleosh = yuleosh._entry:main). This file is legacy-only.
    entry_points={
        "console_scripts": ["yuleosh=yuleosh._entry:main"],
    },
)
