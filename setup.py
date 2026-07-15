# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

# NOTE (AR-P2-03): setup.py is kept for legacy compatibility (pip install -e .).
# All project metadata is now defined in pyproject.toml. This file will be
# removed when all CI workflows and documentation reference pyproject.toml.

from setuptools import setup, find_packages

setup(
    name="yuleosh",
    version="2.2.0",
    description="嵌入式AI开发全流程平台 — OpenSpec+Superpowers+Harness Engineering 三位一体",
    packages=find_packages(where=["src"]),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "bcrypt>=4.1",
        "pyjwt>=2.8",
        "psycopg2-binary>=2.9",
        "pyserial>=3.5",
        "pyyaml>=6.0",
        "stripe>=7.0",
        # CVE-2026 transitive dep constraints
        "msgpack>=1.2.1",  # GHSA-6v7p-g79w-8964
        "starlette>=1.0.1",  # PYSEC-2026-161
    ],
    extras_require={
        "dev": ["pytest", "pytest-cov", "pytest-mock"],
    },
    # NOTE: console_scripts entry point is defined in pyproject.toml
    # (yuleosh = yuleosh._entry:main). This file is legacy-only.
    entry_points={
        "console_scripts": ["yuleosh=yuleosh._entry:main"],
    },
)
