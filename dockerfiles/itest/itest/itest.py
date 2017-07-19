import contextlib
import csv
import json
import os
import socket
import subprocess
import time
import urllib2

import kazoo.client
import pytest


ZOOKEEPER_CONNECT_STRING = "zookeeper_1:2181"

MY_IP_ADDRESS = socket.gethostbyname(socket.gethostname())

# Authoritative data for tests
SERVICES = {
    # HTTP service with a custom endpoint
    'service_three.main': {
        'host': 'servicethree_1',
        'ip_address': socket.gethostbyname('servicethree_1'),
        'port': 1024,
        'proxy_port': 20060,
        'mode': 'http',
        'healthcheck_uri': '/my_healthcheck_endpoint',
        'discover': 'habitat',
        'advertise': ['habitat', 'region'],
    },

    # HTTP service with a custom endpoint
    'service_three.logging': {
        'host': 'servicethree_1',
        'ip_address': socket.gethostbyname('servicethree_1'),
        'port': 1024,
        'proxy_port': 20050,
        'mode': 'http',
        'healthcheck_uri': '/my_healthcheck_endpoint',
        'discover': 'habitat',
        'advertise': ['habitat'],
    },

    # TCP service
    'service_one.main': {
        'host': 'serviceone_1',
        'ip_address': socket.gethostbyname('serviceone_1'),
        'port': 1025,
        'proxy_port': 20028,
        'mode': 'tcp',
        'discover': 'region',
        'advertise': ['region'],
    },

    # HTTP service with a custom endpoint and chaos
    'service_three_chaos.main': {
        'host': 'servicethreechaos_1',
        'ip_address': socket.gethostbyname('servicethreechaos_1'),
        'port': 1024,
        'proxy_port': 20061,
        'mode': 'http',
        'healthcheck_uri': '/my_healthcheck_endpoint',
        'chaos': True,
        'discover': 'region',
        'advertise': ['region'],
    },

    # HTTP with headers required for the healthcheck
    'service_two.main': {
        'host': 'servicetwo_1',
        'ip_address': socket.gethostbyname('servicetwo_1'),
        'port': 1999,
        'proxy_port': 20090,
        'mode': 'http',
        'discover': 'habitat',
        'advertise': ['habitat'],
        'healthcheck_uri': '/lil_brudder',
        'extra_healthcheck_headers': {
            'X-Mode': 'ro',
        },
    },
}

# How long Synapse gets to configure HAProxy on startup.  This value is
# intentionally generous to avoid any build flakes.
SETUP_DELAY_S = 30

SOCKET_TIMEOUT = 10

SYNAPSE_ROOT_DIR = '/var/run/synapse'

SYNAPSE_TOOLS_CONFIGURATIONS = {
    'haproxy': ['/etc/synapse/synapse-tools.conf.json'],
    'nginx': [
        '/etc/synapse/synapse-tools-both.conf.json',
        '/etc/synapse/synapse-tools-nginx.conf.json',
    ]
}

YIELD_PARAMS = [
    item for sublist in SYNAPSE_TOOLS_CONFIGURATIONS.values()
    for item in sublist
]


@pytest.yield_fixture(scope='module', params=YIELD_PARAMS)
def setup(request):
    try:
        os.makedirs(SYNAPSE_ROOT_DIR)
    except OSError:
        # Path already exists
        pass

    zk = kazoo.client.KazooClient(hosts=ZOOKEEPER_CONNECT_STRING)
    zk.start()
    try:
        # Fake out a nerve registration in Zookeeper for each service
        for name, data in SERVICES.iteritems():
            labels = dict(
                ('%s:my_%s' % (advertise_typ, advertise_typ), '')
                for advertise_typ in data['advertise']
            )
            zk.create(
                path=('/smartstack/global/%s/itesthost' % name),
                value=(json.dumps({
                    'host': data['ip_address'],
                    'port': data['port'],
                    'name': data['host'],
                    'labels': labels,
                })),
                ephemeral=True,
                sequence=True,
                makepath=True,
            )

        # This is the tool that is installed by the synapse-tools package.
        # Run it to generate a new synapse configuration file.
        subprocess.check_call(
            ['configure_synapse'],
            env=dict(
                os.environ, SYNAPSE_TOOLS_CONFIG_PATH=request.param
            )
        )

        # Normally configure_synapse would start up synapse using 'service synapse start'.
        # However, this silently fails because we don't have an init process in our
        # Docker container.  So instead we manually start up synapse ourselves.
        synapse_process = subprocess.Popen(
            'synapse --config /etc/synapse/synapse.conf.json'.split(),
            env={
                'PATH': '/opt/rbenv/bin:' + os.environ['PATH'],
            }
        )

        time.sleep(SETUP_DELAY_S)

        try:
            yield request.param
        finally:
            synapse_process.kill()
            synapse_process.wait()
    finally:
        zk.stop()


def _sort_lists_in_dict(d):
    for k in d:
        if isinstance(d[k], dict):
            d[k] = _sort_lists_in_dict(d[k])
        elif isinstance(d[k], list):
            d[k] = sorted(d[k])
    return d


def test_haproxy_config_valid(setup):
    subprocess.check_call(['haproxy-synapse', '-c', '-f', '/var/run/synapse/haproxy.cfg'])


def test_haproxy_synapse_reaper(setup):
    # This should run with no errors.  Everything is running as root, so we need
    # to use the --username option here.
    subprocess.check_call(['haproxy_synapse_reaper', '--username', 'root'])


def test_synapse_qdisc_tool(setup):
    # Can't actually manipulate qdisc or iptables in a docker, so this
    # is what we have for now
    subprocess.check_call(['synapse_qdisc_tool', '--help'])


def test_synapse_services(setup):
    expected_services = [
        'service_three.main',
        'service_three.main.region',
        'service_one.main',
        'service_three_chaos.main',
        'service_two.main',
        'service_three.logging',
    ]

    with open('/etc/synapse/synapse.conf.json') as fd:
        synapse_config = json.load(fd)
    actual_services = synapse_config['services'].keys()

    # nginx adds listener "services" which contain the proxy
    # back to HAProxy sockets which actually do the load balancing
    if setup in SYNAPSE_TOOLS_CONFIGURATIONS['nginx']:
        nginx_services = [
            'service_three_chaos.main.nginx_listener',
            'service_one.main.nginx_listener',
            'service_two.main.nginx_listener',
            'service_three.main.nginx_listener',
            'service_three.logging.nginx_listener',
        ]
        expected_services.extend(nginx_services)

    assert set(expected_services) == set(actual_services)


def test_http_synapse_service_config(setup):
    expected_service_entry = {
        'default_servers': [],
        'use_previous_backends': False,
        'discovery': {
            'hosts': [ZOOKEEPER_CONNECT_STRING],
            'method': 'zookeeper',
            'path': '/smartstack/global/service_three.main',
            'label_filters': [
                {
                    'label': 'habitat:my_habitat',
                    'value': '',
                    'condition': 'equals',
                },
            ],
        }
   }

    with open('/etc/synapse/synapse.conf.json') as fd:
        synapse_config = json.load(fd)

    actual_service_entry = synapse_config['services'].get('service_three.main')

    # Unit tests already test the contents of the haproxy and nginx sections
    # itests operate at a higher level of abstraction and need not care about
    # how exactly SmartStack achieves the goal of load balancing
    # So, we just check that the sections are there, but not what's in them!
    assert 'haproxy' in actual_service_entry
    del actual_service_entry['haproxy']
    if setup in SYNAPSE_TOOLS_CONFIGURATIONS['nginx']:
        assert 'nginx' in actual_service_entry
        del actual_service_entry['nginx']

    actual_service_entry = _sort_lists_in_dict(actual_service_entry)
    expected_service_entry = _sort_lists_in_dict(expected_service_entry)

    assert expected_service_entry == actual_service_entry


def test_backup_http_synapse_service_config(setup):
    expected_service_entry = {
        'default_servers': [],
        'use_previous_backends': False,
        'discovery': {
            'hosts': [ZOOKEEPER_CONNECT_STRING],
            'method': 'zookeeper',
            'path': '/smartstack/global/service_three.main',
            'label_filters': [
                {
                    'label': 'region:my_region',
                    'value': '',
                    'condition': 'equals',
                },
            ],
        }
    }

    with open('/etc/synapse/synapse.conf.json') as fd:
        synapse_config = json.load(fd)

    actual_service_entry = synapse_config['services'].get('service_three.main.region')

    # Unit tests already test the contents of the haproxy and nginx sections
    # itests operate at a higher level of abstraction and need not care about
    # how exactly SmartStack achieves the goal of load balancing
    # So, we just check that the sections are there, but not what's in them!
    assert 'haproxy' in actual_service_entry
    del actual_service_entry['haproxy']
    if setup in SYNAPSE_TOOLS_CONFIGURATIONS['nginx']:
        assert 'nginx' in actual_service_entry
        del actual_service_entry['nginx']

    actual_service_entry = _sort_lists_in_dict(actual_service_entry)
    expected_service_entry = _sort_lists_in_dict(expected_service_entry)

    assert expected_service_entry == actual_service_entry


def test_tcp_synapse_service_config(setup):
    expected_service_entry = {
        'default_servers': [],
        'use_previous_backends': False,
        'discovery': {
            'hosts': [ZOOKEEPER_CONNECT_STRING],
            'method': 'zookeeper',
            'path': '/smartstack/global/service_one.main',
            'label_filters': [
                {
                    'label': 'region:my_region',
                    'value': '',
                    'condition': 'equals',
                },
            ],
        },
    }

    with open('/etc/synapse/synapse.conf.json') as fd:
        synapse_config = json.load(fd)
    actual_service_entry = synapse_config['services'].get('service_one.main')

    # Unit tests already test the contents of the haproxy and nginx sections
    # itests operate at a higher level of abstraction and need not care about
    # how exactly SmartStack achieves the goal of load balancing
    # So, we just check that the sections are there, but not what's in them!
    assert 'haproxy' in actual_service_entry
    del actual_service_entry['haproxy']
    if setup in SYNAPSE_TOOLS_CONFIGURATIONS['nginx']:
        assert 'nginx' in actual_service_entry
        del actual_service_entry['nginx']

    actual_service_entry = _sort_lists_in_dict(actual_service_entry)
    expected_service_entry = _sort_lists_in_dict(expected_service_entry)

    assert expected_service_entry == actual_service_entry


def test_hacheck(setup):
    for name, data in SERVICES.iteritems():
        # Just test our HTTP service
        if data['mode'] != 'http':
            continue

        url = 'http://%s:6666/http/%s/0%s' % (
            data['ip_address'], name, data['healthcheck_uri'])

        headers = {
            'X-Haproxy-Server-State':
                'UP 2/3; host=srv2; port=%d; name=bck/srv2;'
                'node=lb1; weight=1/2; scur=13/22; qcur=0' % data['port']
        }
        headers.update(data.get('extra_healthcheck_headers', {}))

        request = urllib2.Request(url=url, headers=headers)

        with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
            assert page.read().strip() == 'OK'


def test_synapse_haproxy_stats_page(setup):
    haproxy_stats_uri = 'http://localhost:32123/;csv'

    with contextlib.closing(
            urllib2.urlopen(haproxy_stats_uri, timeout=SOCKET_TIMEOUT)) as haproxy_stats:
        reader = csv.DictReader(haproxy_stats)
        rows = [(row['# pxname'], row['svname'], row['check_status']) for row in reader]

        for name, data in SERVICES.iteritems():
            if 'chaos' in data:
                continue

            svname = '%s_%s:%d' % (data['host'], data['ip_address'], data['port'])
            check_status = 'L7OK'
            assert (name, svname, check_status) in rows


def test_http_service_is_accessible_using_haproxy(setup):
    for name, data in SERVICES.iteritems():
        if data['mode'] == 'http' and 'chaos' not in data:
            uri = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
            with contextlib.closing(urllib2.urlopen(uri, timeout=SOCKET_TIMEOUT)) as page:
                assert page.read().strip() == 'OK'


def test_tcp_service_is_accessible_using_haproxy(setup):
    for name, data in SERVICES.iteritems():
        if data['mode'] == 'tcp':
            s = socket.create_connection(
                address=(data['ip_address'], data['port']),
                timeout=SOCKET_TIMEOUT)
            s.close()


def test_file_output(setup):
    output_directory = os.path.join(SYNAPSE_ROOT_DIR, 'services')
    for name, data in SERVICES.iteritems():
        with open(os.path.join(output_directory, name + '.json')) as f:
            service_data = json.load(f)
            if 'chaos' in data:
                assert len(service_data) == 0
                continue

            assert len(service_data) == 1

            service_instance = service_data[0]
            assert service_instance['name'] == data['host']
            assert service_instance['port'] == data['port']
            assert service_instance['host'] == data['ip_address']


def test_http_service_returns_503(setup):
    data = SERVICES['service_three_chaos.main']
    uri = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
    with pytest.raises(urllib2.HTTPError) as excinfo:
        with contextlib.closing(urllib2.urlopen(uri, timeout=SOCKET_TIMEOUT)):
            assert False
        assert excinfo.value.getcode() == 503

def test_logging_plugin(setup):
    # Test plugins only with HAProxy
    if 'nginx' not in setup:

        # Send mock requests
        name = 'service_three.logging'
        data = SERVICES[name]
        url = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
        headers_list = [
            {'From': 'Reservations'},
            {'From': 'Search'},
            {'From': 'Geolocator'}
        ]

        for headers in headers_list:
            request = urllib2.Request(url=url, headers=headers)
            with contextlib.closing(
                    urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
                assert page.read().strip() == 'OK'

        # Check that requests were logged
        log_file = '/var/log/demo_log'
        try:
            with open(log_file) as f:
                logs = f.readlines()
                n = len(headers_list)
                assert len(logs) >= n

                logs_tail = logs[-n:]
                for i in xrange(n):
                    expected = 'From: %s' % headers_list[i]['From']
                    assert expected in logs_tail[i]

        except IOError as e:
            assert False
