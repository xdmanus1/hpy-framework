# setup.py
from setuptools import setup, find_packages

# Most configuration is in pyproject.toml, but this helps setuptools
# find the package structure correctly.
setup(
    # Automatically find the 'hpy_core' package
    packages=find_packages(include=["hpy_core", "hpy_core.*"])
    # remove py_modules=["hpy_tool"] if it was present before
)
