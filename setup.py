# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

from setuptools import setup, find_packages

setup(
    name="yuleosh",
    version="2.1.0",
    description="嵌入式AI开发全流程平台 — OpenSpec+Superpowers+Harness Engineering 三位一体",
    packages=find_packages(where=["src"]),
    package_dir={"": "src"},
    py_modules=["yuleosh_cli"],
    python_requires=">=3.10",
    install_requires=[
        "bcrypt>=4.1",
        "pyjwt>=2.8",
        "psycopg2-binary>=2.9",
        "pyserial>=3.5",
        "pyyaml>=6.0",
        "stripe>=7.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-cov", "pytest-mock"],
    },
    entry_points={
        "console_scripts": ["yuleosh=yuleosh_cli:main"],
    },
)
