#!/usr/bin/env python3
"""
Magic Debug Setup Script
"""

from setuptools import setup, find_packages

setup(
    name="magic-debug",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "magic-debug=main:main",
        ],
    },
    python_requires=">=3.8",
)
