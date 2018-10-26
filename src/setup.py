#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='synapse-tools',
    version='0.13.26',
    provides=['synapse_tools'],
    author='John Billings',
    author_email='billings@yelp.com',
    description='Synapse-related tools for use on Yelp machines',
    packages=find_packages(exclude=['tests']),
    setup_requires=['setuptools'],
    include_package_data=True,
    install_requires=[
        # paasta tools pins this so we really can't have anything higher
        # if paasta tools ever does a >= we can relax this constraint
        'argparse==1.2.1',
        'environment_tools>=1.1.0,<1.2.0',
        'plumbum>=1.6.0,<1.7.0',
        'protobuf==2.6.1',
        'psutil>=2.1.1,<2.2.0',
        'PyYAML>=3.11,<4.0.0',
        'pyroute2>=0.3.4,<0.4.0',
        'paasta-tools==0.81.3',
        'setuptools==37.0.0',
    ],
    entry_points={
        'console_scripts': [
            'configure_synapse=synapse_tools.configure_synapse:main',
            'haproxy_synapse_reaper=synapse_tools.haproxy_synapse_reaper:main',
            'synapse_qdisc_tool=synapse_tools.haproxy.qdisc_tool:main',
        ],
    },
)
