#!/bin/bash

echo "Installing synapse-tools package"
dpkg -i /work/dist/synapse-tools_*.deb

# Set -e here because the previous install should fail lacking dependencies
# and then we can fix it here
set -e
apt-get -y install -f

echo "Testing that pyyaml uses optimized cyaml parsers if present"
/opt/venvs/synapse-tools/bin/python -c 'import yaml; assert yaml.__with_libyaml__'

source /etc/os-release
if [[  $VERSION = *"Trusty"* ]]; then
    echo "Trusty has issues with backports.functools_lru_cache; installing it"
    /opt/venvs/synapse-tools/bin/pip install backports.functools_lru_cache
fi

echo "Creating directory for unix sockets"
mkdir -p /var/run/synapse/sockets

echo "Starting rsyslog"
rsyslogd -f /etc/rsyslog.conf

echo "Full integration test"
py.test /itest.py
