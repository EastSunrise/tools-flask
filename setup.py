""" setup

@Author Kingen
@Date 2020/5/14
"""
import setuptools

with open("README.md", "r") as fp:
    long_description = fp.read()

setuptools.setup(
    name="tools-flask",
    version="1.0.0",
    author="Kingen",
    author_email="wsg787@126.com",
    description="A tools kit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EastSunrise/tools-flask",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
