# -*- coding: utf-8 -*-
"""Set up aiida-nwchem distribution."""
import json

from setuptools import find_packages, setup

if __name__ == '__main__':
    with open('setup.json', 'r', encoding='utf-8') as handle:
        kwargs = json.load(handle)
    setup(
        include_package_data=True,
        packages=find_packages(),
        setup_requires=['reentry'],
        reentry_register=True,
        **kwargs
    )
