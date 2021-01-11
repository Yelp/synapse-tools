#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pkg_resources import yield_lines
from setuptools import setup, find_packages


def get_install_requires():
    with open('requirements.txt', 'r') as f:
        minimal_reqs = list(yield_lines(f.read()))

    return minimal_reqs


setup(
    name='synapse-tools',
    version='0.18.1',
    provides=['synapse_tools'],
    author='Compute Infra',
    author_email='compute-infra@yelp.com',
    description='Synapse-related tools for use on Yelp machines',
    packages=find_packages(exclude=['tests']),
    setup_requires=['setuptools'],
    include_package_data=True,
    install_requires=get_install_requires(),
    entry_points={
        'console_scripts': [
            'configure_synapse=synapse_tools.configure_synapse:main',
            'generate_container_ip_map=synapse_tools.generate_container_ip_map:main',
            'haproxy_synapse_reaper=synapse_tools.haproxy_synapse_reaper:main',
            'synapse_qdisc_tool=synapse_tools.haproxy.qdisc_tool:main',
        ],
    },
    scripts=[
        "synapse-tools-reload-nginx.sh",
    ],
)
