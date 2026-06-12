from setuptools import setup, find_namespace_packages

setup(
    name="yuleosh",
    version="0.4.0",
    description="嵌入式AI开发全流程平台 — OpenSpec+Superpowers+Harness Engineering 三位一体",
    packages=find_namespace_packages(include=["src", "src.*"]),
    py_modules=["yuleosh_cli"],
    python_requires=">=3.10",
    install_requires=[
        "psycopg2-binary>=2.9",
    ],
    extras_require={
        "dev": ["pytest", "pytest-cov", "pytest-mock"],
    },
    entry_points={
        "console_scripts": ["yuleosh=yuleosh_cli:main"],
    },
)
