import setuptools

VERSION = "0.2.0"

setuptools.setup(
    name="dotfilelink",
    version=VERSION,
    author="sndv",
    author_email="sndv@mailbox.org",
    description="A tool to link or copy dotfiles",
    url="https://github.com/sndv/dotfilelink",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
    packages=["dotfilelink"],
    python_requires=">=3.8",
    install_requires=[
        "PyYAML>=5.4",
    ],
    entry_points = {
        "console_scripts": [
            "dotfilelink = dotfilelink.dotfilelink:main",
        ],
    },
)
