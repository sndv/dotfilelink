import os
import re

import setuptools


def get_version() -> str:
    init_path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "dotfilelink/dotfilelink.py",
    )
    with open(init_path, "r") as fh:
        init_file = fh.read()
    match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", init_file, re.M)
    if not match:
        raise RuntimeError("Cannot find package version")
    return match.group(1)


setuptools.setup(
    name="dotfilelink",
    version=get_version(),
    author="sndv",
    author_email="sndv@mailbox.org",
    description="A tool to link or copy dotfiles",
    url="https://github.com/sndv/dotfilelink",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
    packages=["dotfilelink"],
    python_requires=">=3.10",
    install_requires=[
        "PyYAML>=6.0",
        "requests>=2.29.0",
        "requests-cache>=1.0.1",
    ],
    entry_points={
        "console_scripts": [
            "dotfilelink = dotfilelink.dotfilelink:main",
        ],
    },
)
