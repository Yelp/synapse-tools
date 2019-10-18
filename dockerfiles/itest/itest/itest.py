import contextlib
import csv
import json
import os
import subprocess
import time
import urllib2
import socket

import kazoo.client
import pytest


CONTAINER_PREFIX = os.environ.get('CONTAINER_PREFIX', 'na')
ZOOKEEPER_CONNECT_STRING = CONTAINER_PREFIX + "zookeeper_1:2181"


# Authoritative data for tests
SERVICES = {
    # HTTP service with a custom endpoint
    'service_three.main': {
        'host': 'servicethree_1',
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'servicethree_1'),
        'port': 1024,
        'proxy_port': 20060,
        'mode': 'http',
        'healthcheck_uri': '/my_healthcheck_endpoint',
        'discover': 'habitat',
        'advertise': ['habitat', 'region'],
    },

    'service_three_endpoint_timeout.main': {
        'host': 'servicethree_endpoint_timeout_1',
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'servicethree_endpoint_timeout_1'),
        'port': 1024,
        'proxy_port': 20070,
        'mode': 'http',
        'healthcheck_uri': '/my_healthcheck_endpoint',
        'discover': 'habitat',
        'advertise': ['habitat', 'region'],
        'endpoint_timeouts': {
            'foo_bar': {
                'endpoint': '/foo/bar',
                'endpoint_timeout_ms': 1000,
            },
        }
    },

    # HTTP service with a custom endpoint
    'service_three.logging': {
        'host': 'servicethree_1',
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'servicethree_1'),
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
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'serviceone_1'),
        'port': 1025,
        'proxy_port': 20028,
        'mode': 'tcp',
        'discover': 'region',
        'advertise': ['region'],
    },

    # HTTP service with a custom endpoint and chaos
    'service_three_chaos.main': {
        'host': 'servicethreechaos_1',
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'servicethreechaos_1'),
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
        'ip_address': socket.gethostbyname(CONTAINER_PREFIX + 'servicetwo_1'),
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

MAP_FILE = '/var/run/synapse/maps/ip_to_service.map'

INITIAL_MAP_FILE_CONTENTS = ''
with open(MAP_FILE, 'r') as f:
    INITIAL_MAP_FILE_CONTENTS = f.read()


def reset_map_file():
    """To avoid flakiness, reset the map file
    before tests that depend on it.
    """
    with open(MAP_FILE, 'w+') as f:
        f.seek(0)
        f.write(INITIAL_MAP_FILE_CONTENTS)


@pytest.yield_fixture(scope='class', params=YIELD_PARAMS)
def setup(request):
    pre_setup = getattr(request.node._obj, "pre_setup", None)
    if callable(pre_setup):
        pre_setup()

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


class TestGroupOne(object):
    def test_haproxy_config_valid(self, setup):
        subprocess.check_call(['haproxy-synapse', '-c', '-f', '/var/run/synapse/haproxy.cfg'])


    def test_haproxy_synapse_reaper(self, setup):
        # This should run with no errors.  Everything is running as root, so we need
        # to use the --username option here.
        subprocess.check_call(['haproxy_synapse_reaper', '--username', 'root'])


    def test_synapse_qdisc_tool(self, setup):
        # Can't actually manipulate qdisc or iptables in a docker, so this
        # is what we have for now
        subprocess.check_call(['synapse_qdisc_tool', '--help'])

    def test_generate_map(self, setup):
        # generate_container_ip_map needs docker client but since this
        # runs inside docker itself, we need to add one separately.
        subprocess.check_call(['generate_container_ip_map', '--help'])


    def test_synapse_services(self, setup):
        expected_services = [
            'service_three.main',
            'service_three.main.region',
            'service_one.main',
            'service_three_chaos.main',
            'service_two.main',
            'service_three.logging',
            'service_three_endpoint_timeout.main.foo_bar_timeouts',
            'service_three_endpoint_timeout.main',
            'service_three_endpoint_timeout.main.region.foo_bar_timeouts',
            'service_three_endpoint_timeout.main.region',
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
                'service_three_endpoint_timeout.main.nginx_listener',
            ]
            expected_services.extend(nginx_services)

        assert set(expected_services) == set(actual_services)


    def test_http_synapse_service_config(self, setup):
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


    def test_backup_http_synapse_service_config(self, setup):
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


    def test_tcp_synapse_service_config(self, setup):
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


    def test_hacheck(self, setup):
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


    def test_synapse_haproxy_stats_page(self, setup):
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


    def test_http_service_is_accessible_using_haproxy(self, setup):
        for name, data in SERVICES.iteritems():
            if data['mode'] == 'http' and 'chaos' not in data:
                uri = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
                with contextlib.closing(urllib2.urlopen(uri, timeout=SOCKET_TIMEOUT)) as page:
                    assert page.read().strip() == 'OK'


    def test_tcp_service_is_accessible_using_haproxy(self, setup):
        for name, data in SERVICES.iteritems():
            if data['mode'] == 'tcp':
                s = socket.create_connection(
                    address=(data['ip_address'], data['port']),
                    timeout=SOCKET_TIMEOUT)
                s.close()


    def test_file_output(self, setup):
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


    def test_http_service_returns_503(self, setup):
        data = SERVICES['service_three_chaos.main']
        uri = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
        with pytest.raises(urllib2.HTTPError) as excinfo:
            with contextlib.closing(urllib2.urlopen(uri, timeout=SOCKET_TIMEOUT)):
                assert False
            assert excinfo.value.getcode() == 503


    def test_logging_plugin(self, setup):
        # Test plugins with only HAProxy
        if 'nginx' not in setup and 'both' not in setup:

            # Send mock requests
            name = 'service_three.logging'
            data = SERVICES[name]
            url = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])
            self.send_requests(urls=[url])

            # Check for requests in log file
            log_file = '/var/log/haproxy.log'
            expected = 'provenance Test service_three.logging'
            self. check_plugin_logs(log_file, expected)


    def test_source_required_plugin(self, setup):
        # Test plugins with only HAProxy
        if 'nginx' not in setup and 'both' not in setup:

            name = 'service_two.main'
            data = SERVICES[name]
            url = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])

            # First, test with the service IP present in the map file
            request = urllib2.Request(url=url, headers={'X-Smartstack-Origin': 'Spoof-Value'})
            with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
                assert page.info().dict['x-smartstack-origin'] == 'Test'

    # Helper for sending requests
    def send_requests(self, urls, headers=None):
        for url in urls:
            request = urllib2.Request(url=url)
            with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
                assert page.read().strip() == 'OK'


    # Helper for checking requests logged by logging plugin
    def check_plugin_logs(self, log_file, expected):
        try:
            with open(log_file) as f:
                logs = f.readlines()
                matching_logs = filter(lambda x: expected in x, logs)
                assert len(matching_logs) >= 1

        except IOError:
            assert False


class TestGroupTwo(object):
    @staticmethod
    def pre_setup():
        """Remove the entry for 127.0.0.1
        from the maps file to simulate a call
        from an unknown service.
        """
        reset_map_file()
        map_file = '/var/run/synapse/maps/ip_to_service.map'
        f = open(map_file, "r+")
        lines = f.readlines()
        f.seek(0)
        for l in lines:
            if not l.startswith('127.0.0.1'):
                f.write(l)
        f.truncate()
        f.close()

    def test_source_required_plugin_without_map_entry(self, setup):
        # Test plugins with only HAProxy
        if 'nginx' not in setup and 'both' not in setup:

            name = 'service_two.main'
            data = SERVICES[name]
            url = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])

            # First, test with the service IP present in the map file
            request = urllib2.Request(url=url, headers={'X-Smartstack-Origin': 'Spoof-Value'})
            with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
                assert page.info().dict['x-smartstack-origin'] == '0'

    def test_map_debug(self):
        reset_map_file()
        """We want to make sure that the process
        to update the map every 5 seconds. For this,
        we will add an entry to the map and see if it
        is reflected in 5s.
        """
        test_ip = '169.254.255.254'
        test_svc = 'new-service-just-added'
        map_file = '/var/run/synapse/maps/ip_to_service.map'
        f = open(map_file, 'a')
        f.write('\n' + test_ip + ' ' + test_svc)
        f.close()

        time.sleep(5)

        map_url = 'http://localhost:32124/'
        request = urllib2.Request(url=map_url)
        with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
            raw = page.read()
            svc_map = json.loads(raw)
            assert test_ip in svc_map
            assert svc_map[test_ip] == test_svc


class TestGroupThree(object):
    @staticmethod
    def pre_setup():
        """Remove the map file to simulate what happens
        on boxes (such as role::devbox) where the map file
        is not generated at all.
        """
        reset_map_file()
        map_file = '/var/run/synapse/maps/ip_to_service.map'
        if os.path.isfile(map_file):
            os.remove(map_file)

    def test_source_required_plugin_without_map_entry(self, setup):
        # Test plugins with only HAProxy
        if 'nginx' not in setup and 'both' not in setup:

            name = 'service_two.main'
            data = SERVICES[name]
            url = 'http://localhost:%d%s' % (data['proxy_port'], data['healthcheck_uri'])

            # First, test with the service IP present in the map file
            request = urllib2.Request(url=url, headers={'X-Smartstack-Origin': 'Spoof-Value'})
            with contextlib.closing(
                urllib2.urlopen(request, timeout=SOCKET_TIMEOUT)) as page:
                assert page.info().dict['x-smartstack-origin'] == '0'
