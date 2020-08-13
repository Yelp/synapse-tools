import contextlib
import json
import os
import subprocess

import mock
import pytest
import yaml

from synapse_tools import configure_synapse


STATUS_QUO_ENVOY_MIGRATION_CONFIG = {
    'migration_enabled': False,
    'namespaces': {},
}


@pytest.yield_fixture
def mock_get_current_location():
    def f(typ):
        return {
            'region': 'my_region',
            'superregion': 'my_superregion',
        }[typ]
    with mock.patch('synapse_tools.configure_synapse.get_current_location',
                    side_effect=f):
        yield


@pytest.yield_fixture
def mock_available_location_types():
    mock_types = [
        'runtimeenv',
        'ecosystem',
        'superregion',
        'region',
        'habitat',
    ]
    patchers = [
        mock.patch(
            'environment_tools.type_utils.available_location_types',
            return_value=mock_types,
        ),
        mock.patch(
            'synapse_tools.configure_synapse.available_location_types',
            return_value=mock_types,
        ),
    ]

    with contextlib.ExitStack() as stack:
        yield tuple(stack.enter_context(patch) for patch in patchers)


def test_get_zookeeper_topology():
    m = mock.mock_open()

    with mock.patch('synapse_tools.configure_synapse.open', m, create=True), mock.patch('yaml.load', return_value=[['foo', 42]]):
        zk_topology = configure_synapse.get_zookeeper_topology('/path/to/fake/file')
    assert zk_topology == ['foo:42']
    m.assert_called_with('/path/to/fake/file')


def test_generate_configuration(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region', 'superregion'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    actual_configuration_reversed_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['superregion', 'region'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                    'acl test_service.superregion_has_connslots connslots(test_service.superregion) gt 0',
                    'use_backend test_service.superregion if test_service.superregion_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
        'test_service.superregion': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'superregion:my_superregion',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.superregion',
            },
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration
    assert actual_configuration_reversed_advertise == expected_configuration


def test_generate_configuration_with_errorfiles(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults(
        {
            'bind_addr': '0.0.0.0',
            'haproxy.defaults.inter': '1234',
            'errorfiles': {
                '404': '/etc/haproxy-synapse/errors/404.http',
                '503': '/etc/haproxy-synapse/errors/503.http',
            }
        }
    )

    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    assert 'errorfile 404 /etc/haproxy-synapse/errors/404.http' in actual_configuration['haproxy']['defaults']
    assert 'errorfile 503 /etc/haproxy-synapse/errors/503.http' in actual_configuration['haproxy']['defaults']


def test_generate_configuration_single_advertise_per_endpoint_timeouts(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'endpoint_timeouts': {
                        '/': 200,
                        '/example/endpoint': 10000,
                        '/example/two/': 100,
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    actual_configuration_default_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'endpoint_timeouts': {
                        '/': 200,
                        '/example/endpoint': 10000,
                        '/example/two/': 100,
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service.___timeouts_path path /',
                    'acl test_service.___timeouts_has_connslots connslots(test_service.___timeouts) gt 0',
                    'use_backend test_service.___timeouts if test_service.___timeouts_has_connslots test_service.___timeouts_path',
                    'acl test_service.__example__endpoint_timeouts_path path_beg /example/endpoint',
                    'acl test_service.__example__endpoint_timeouts_has_connslots connslots(test_service.__example__endpoint_timeouts) gt 0',
                    'use_backend test_service.__example__endpoint_timeouts if test_service.__example__endpoint_timeouts_has_connslots test_service.__example__endpoint_timeouts_path',
                    'acl test_service.__example__two___timeouts_path path_beg /example/two/',
                    'acl test_service.__example__two___timeouts_has_connslots connslots(test_service.__example__two___timeouts) gt 0',
                    'use_backend test_service.__example__two___timeouts if test_service.__example__two___timeouts_has_connslots test_service.__example__two___timeouts_path',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
        'test_service.___timeouts': {
            'default_servers': [],
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout connect 2000ms',
                    'timeout server 200ms',
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.___timeouts',
            },
            'use_previous_backends': False,
        },
        'test_service.__example__endpoint_timeouts': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout connect 2000ms',
                    'timeout server 10000ms',
                    # Note: tarpit options don't work for per-endpoint backends
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.__example__endpoint_timeouts',
            },
        },
        'test_service.__example__two___timeouts': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout connect 2000ms',
                    'timeout server 100ms',
                    # Note: tarpit options don't work for per-endpoint backends
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.__example__two___timeouts',
            },
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration
    assert actual_configuration_default_advertise == expected_configuration


def test_generate_configuration_single_advertise_per_endpoint_timeouts_with_default_timeout(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'endpoint_timeouts': {
                        '/example/endpoint': 10000,
                        '/example/two/': 100,
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    actual_configuration_default_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'endpoint_timeouts': {
                        '/example/endpoint': 10000,
                        '/example/two/': 100,
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service.__example__endpoint_timeouts_path path_beg /example/endpoint',
                    'acl test_service.__example__endpoint_timeouts_has_connslots connslots(test_service.__example__endpoint_timeouts) gt 0',
                    'use_backend test_service.__example__endpoint_timeouts if test_service.__example__endpoint_timeouts_has_connslots test_service.__example__endpoint_timeouts_path',
                    'acl test_service.__example__two___timeouts_path path_beg /example/two/',
                    'acl test_service.__example__two___timeouts_has_connslots connslots(test_service.__example__two___timeouts) gt 0',
                    'use_backend test_service.__example__two___timeouts if test_service.__example__two___timeouts_has_connslots test_service.__example__two___timeouts_path',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
        'test_service.__example__endpoint_timeouts': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout server 10000ms',
                    # Note: tarpit options don't work for per-endpoint backends
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.__example__endpoint_timeouts',
            },
        },
        'test_service.__example__two___timeouts': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout server 100ms',
                    # Note: tarpit options don't work for per-endpoint backends
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.__example__two___timeouts',
            },
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration
    assert actual_configuration_default_advertise == expected_configuration


def test_generate_configuration_single_advertise(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    actual_configuration_default_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 3,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 3',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration
    assert actual_configuration_default_advertise == expected_configuration


def test_generate_configuration_empty(mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )
    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    assert actual_configuration == expected_configuration


def test_generate_configuration_with_proxied_through(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'proxied_through': 'proxy_service',
                }
            ),
            (
                'proxy_service',
                {
                    'proxy_port': 5678,
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'is_proxy': True,
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'proxy_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/proxy_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/proxy_service.sock',
                    'bind /var/run/synapse/sockets/proxy_service.prxy accept-proxy',
                    'acl proxy_service_has_connslots connslots(proxy_service) gt 0',
                    'use_backend proxy_service if proxy_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'option httpchk GET /http/proxy_service/0/status',
                    'http-check send-state',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i proxy_service',
                    'reqtarpit . if to_be_tarpitted',
                    'acl is_status_request path /status',
                    'http-request set-header X-Smartstack-Source proxy_service if !is_status_request',
                ],
                'port': '5678',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'proxy_service',
            },
        },
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [
                ],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl is_status_request path /status',
                    'acl request_from_proxy hdr_beg(X-Smartstack-Source) -i proxy_service',
                    'acl proxied_through_backend_has_connslots connslots(proxy_service) gt 0',
                    'http-request set-header X-Smartstack-Destination test_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'use_backend proxy_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration


def test_generate_configuration_with_nginx(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults({
        'bind_addr': '0.0.0.0',
        'listen_with_nginx': True
    })
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region', 'superregion'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=synapse_tools_config
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                    'acl test_service.superregion_has_connslots connslots(test_service.superregion) gt 0',
                    'use_backend test_service.superregion if test_service.superregion_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
            'nginx': {
                'disabled': True
            },
        },
        'test_service.superregion': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'superregion:my_superregion',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.superregion',
            },
            'nginx': {
                'disabled': True
            },
        },
        'test_service.nginx_listener': {
            'default_servers': [{
                'host': 'unix',
                'port': '/var/run/synapse/sockets/test_service.sock',
            }],
            'discovery': {'method': 'base'},
            'haproxy': {'disabled': True},
            'file_output': {'disabled': True},
            'nginx': {
                'mode': 'tcp',
                'port': 1234,
                'server': [
                    'proxy_timeout 3610s',
                ],
                'listen_options': 'reuseport',
            },
            'use_previous_backends': True
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration


def test_generate_configuration_only_nginx(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults({
        'bind_addr': '0.0.0.0',
        'listen_with_nginx': True,
        'listen_with_haproxy': False,
    })
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region', 'superregion'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=synapse_tools_config
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                    'acl test_service.superregion_has_connslots connslots(test_service.superregion) gt 0',
                    'use_backend test_service.superregion if test_service.superregion_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'bind_address': '/var/run/synapse/sockets/test_service.sock',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
                'port': None,
            },
            'nginx': {
                'disabled': True
            },
        },
        'test_service.superregion': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'superregion:my_superregion',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                ],
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service.superregion',
            },
            'nginx': {
                'disabled': True
            },
        },
        'test_service.nginx_listener': {
            'default_servers': [{
                'host': 'unix',
                'port': '/var/run/synapse/sockets/test_service.sock',
            }],
            'discovery': {'method': 'base'},
            'haproxy': {'disabled': True},
            'file_output': {'disabled': True},
            'nginx': {
                'mode': 'tcp',
                'port': 1234,
                'server': [
                    'proxy_timeout 3610s',
                ]
            },
            'use_previous_backends': True
        },
    }

    expected_configuration['haproxy']['defaults'].extend([
        'timeout tarpit 60s',
    ])

    assert actual_configuration == expected_configuration


def test_generate_configuration_with_source_required_plugin(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'plugins': {
                        'source_required': {
                            'enabled': True,
                        },
                    },
                }
            ),
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'http-request lua.add_source_header',
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
    }

    expected_configuration['haproxy']['global'].extend([
        'lua-load /nail/etc/lua_scripts/add_source_header.lua',
    ])

    # check frontend and backend sections
    assert actual_configuration['services'] == expected_configuration['services']

    # check global section separately because file paths will vary
    actual_global = actual_configuration['haproxy']['global']
    expected_global = expected_configuration['haproxy']['global']
    assert actual_global[:-3] == expected_global[:-3]
    assert 'lua-load' and 'add_source_header' in actual_global[-1]


def test_generate_configuration_with_logging_plugin(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'proxied_through': 'proxy_service',
                }
            ),
            (
                'proxy_service',
                {
                    'proxy_port': 5678,
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'is_proxy': True,
                    'plugins': {
                        'logging': {
                            'enabled': True,
                            'sample_rate': 0.25
                        }
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'proxy_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/proxy_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/proxy_service.sock',
                    'bind /var/run/synapse/sockets/proxy_service.prxy accept-proxy',
                    'acl proxy_service_has_connslots connslots(proxy_service) gt 0',
                    'use_backend proxy_service if proxy_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'option httpchk GET /http/proxy_service/0/status',
                    'http-check send-state',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i proxy_service',
                    'reqtarpit . if to_be_tarpitted',
                    'acl is_status_request path /status',
                    'http-request set-header X-Smartstack-Source proxy_service if !is_status_request',
                    'http-request lua.init_logging',
                    'http-request lua.log_provenance',
                ],
                'port': '5678',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'proxy_service',
            },
        },
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl is_status_request path /status',
                    'acl request_from_proxy hdr_beg(X-Smartstack-Source) -i proxy_service',
                    'acl proxied_through_backend_has_connslots connslots(proxy_service) gt 0',
                    'http-request set-header X-Smartstack-Destination test_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'use_backend proxy_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
    }

    expected_configuration['haproxy']['global'].extend([
        'lua-load /nail/etc/lua_scripts/log_requests.lua',
        'setenv sample_rate 0.25'
    ])

    # check frontend and backend sections
    assert actual_configuration['services'] == expected_configuration['services']

    # check global section separately because file paths will vary
    actual_global = actual_configuration['haproxy']['global']
    expected_global = expected_configuration['haproxy']['global']
    assert actual_global[:-2] == expected_global[:-2]
    assert 'lua-load' and 'log_requests' in actual_global[-2]
    assert 'setenv sample_rate' in actual_global[-1]


def test_generate_configuration_with_multiple_plugins(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': 1234,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'plugins': {
                        'path_based_routing': {
                            'enabled': True
                        },
                        'logging': {
                            'enabled': True
                        }
                    },
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'proxied_through': 'proxy_service',
                }
            ),
            (
                'proxy_service',
                {
                    'proxy_port': 5678,
                    'balance': 'roundrobin',
                    'advertise': ['region'],
                    'discover': 'region',
                    'is_proxy': True,
                    'plugins': {
                        'logging': {
                            'enabled': True
                        }
                    }
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'})
    )
    expected_configuration['services'] = {
        'proxy_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/proxy_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/proxy_service.sock',
                    'bind /var/run/synapse/sockets/proxy_service.prxy accept-proxy',
                    'acl proxy_service_has_connslots connslots(proxy_service) gt 0',
                    'use_backend proxy_service if proxy_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'option httpchk GET /http/proxy_service/0/status',
                    'http-check send-state',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i proxy_service',
                    'reqtarpit . if to_be_tarpitted',
                    'acl is_status_request path /status',
                    'http-request set-header X-Smartstack-Source proxy_service if !is_status_request',
                    'http-request lua.init_logging',
                    'http-request lua.log_provenance',
                ],
                'port': '5678',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'proxy_service',
            },
        },
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'listen': [],
                'frontend': [
                    'timeout client 3000ms',
                    'capture request header X-B3-SpanId len 64',
                    'capture request header X-B3-TraceId len 64',
                    'capture request header X-B3-ParentSpanId len 64',
                    'capture request header X-B3-Flags len 10',
                    'capture request header X-B3-Sampled len 10',
                    'option httplog',
                    'bind /var/run/synapse/sockets/test_service.sock',
                    'bind /var/run/synapse/sockets/test_service.prxy accept-proxy',
                    'acl is_status_request path /status',
                    'acl request_from_proxy hdr_beg(X-Smartstack-Source) -i proxy_service',
                    'acl proxied_through_backend_has_connslots connslots(proxy_service) gt 0',
                    'http-request set-header X-Smartstack-Destination test_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'use_backend proxy_service if !is_status_request !request_from_proxy proxied_through_backend_has_connslots',
                    'http-request set-var(txn.backend_name) lua.get_backend',
                    'use_backend %[var(txn.backend_name)]',
                    'acl test_service_has_connslots connslots(test_service) gt 0',
                    'use_backend test_service if test_service_has_connslots',
                ],
                'backend': [
                    'balance roundrobin',
                    'reqidel ^X-Mode:.*',
                    'reqadd X-Mode:\\ ro',
                    'option httpchk GET /http/test_service/0/status HTTP/1.1\\r\\nX-Mode:\\ ro',
                    'http-check send-state',
                    'retries 2',
                    'timeout connect 2000ms',
                    'timeout server 3000ms',
                    'acl to_be_tarpitted hdr_sub(X-Ctx-Tarpit) -i test_service',
                    'reqtarpit . if to_be_tarpitted',
                    'http-request lua.init_logging',
                    'http-request lua.log_provenance',
                ],
                'port': '1234',
                'server_options': 'check port 6666 observe layer7 maxconn 50 maxqueue 10',
                'backend_name': 'test_service',
            },
        },
    }

    expected_configuration['haproxy']['global'].extend([
        'lua-load /nail/etc/lua_scripts/log_requests.lua',
        'lua-load /nail/etc/lua_scripts/path_based_routing.lua'
    ])

    # check frontend and backend sections
    assert actual_configuration['services'] == expected_configuration['services']

    # check global section separately because file paths will vary
    actual_global = actual_configuration['haproxy']['global']
    expected_global = expected_configuration['haproxy']['global']
    assert actual_global[:-2] == expected_global[:-2]
    assert 'lua-load' and 'log_requests' in actual_global[-2]
    assert 'lua-load' and 'path_based_routing' in actual_global[-1]


def test_generate_configuration_envoy_migration_enabled(mock_get_current_location, mock_available_location_types):
    """When envoy migration is enabled and a namespace is envoy-only, we shouldn't load balance it."""
    config = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({
            'bind_addr': '0.0.0.0',
            'listen_with_nginx': True,
            'listen_with_haproxy': False,
        }),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'service_1',
                {
                    'proxy_port': 1111,
                    'advertise': ['region'],
                    'discover': 'region',
                }
            ),
            (
                'service_2',
                {
                    'proxy_port': 2222,
                    'advertise': ['region'],
                    'discover': 'region',
                }
            ),
            (
                'service_3',
                {
                    'proxy_port': 3333,
                    'advertise': ['region'],
                    'discover': 'region',
                }
            ),
            (
                'service_4',
                {
                    'proxy_port': 4444,
                    'advertise': ['region'],
                    'discover': 'region',
                }
            ),
        ],
        envoy_migration_config={
            'migration_enabled': True,
            'namespaces': {
                # service_1 intentionally omitted to test that the default is "synapse" mode.
                'service_2': {'state': 'synapse'},
                'service_3': {'state': 'dual'},
                'service_4': {'state': 'envoy'},
            },
        },
    )
    # service_1 isn't in the namespace config, so defaults to enabled.
    assert config['services']['service_1.nginx_listener']['nginx']['port'] == 1111
    # service_2 is in "synapse" mode, so is enabled.
    assert config['services']['service_2.nginx_listener']['nginx']['port'] == 2222
    # service_3 is in "dual" mode, so is enabled.
    assert config['services']['service_3.nginx_listener']['nginx']['port'] == 3333
    # service_4 is in "envoy" mode, so the nginx listener is gone but the
    # haproxy backend remains.
    assert 'service_4.nginx_listener' not in config['services']
    assert config['services']['service_4']['haproxy']['bind_address'] == '/var/run/synapse/sockets/service_4.sock'


def test_generate_configuration_envoy_migration_disabled(mock_get_current_location, mock_available_location_types):
    """When envoy migration is disabled, even namespaces in envoy-only mode still use haproxy."""
    config = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'my_service',
                {
                    'proxy_port': 1111,
                    'advertise': ['region'],
                    'discover': 'region',
                }
            ),
        ],
        envoy_migration_config={
            'migration_enabled': False,
            'namespaces': {
                'my_service': {'state': 'envoy'},
            },
        },
    )
    assert 'disabled' not in config['services']['my_service']
    assert config['services']['my_service']['haproxy']['port'] == '1111'


@contextlib.contextmanager
def setup_mocks_for_main(tmpdir, config_file_path):
    """Write out config files and mock enough functions to run main()."""
    synapse_tools_config = tmpdir.join('synapse-tools.conf.json')
    synapse_tools_config.write(json.dumps({
        'config_file': config_file_path,
    }))

    envoy_migration_config = tmpdir.join('envoy_migration.yaml')
    envoy_migration_config.write(yaml.safe_dump(STATUS_QUO_ENVOY_MIGRATION_CONFIG))

    with mock.patch.dict(
        os.environ,
        {
            'SYNAPSE_TOOLS_CONFIG_PATH': synapse_tools_config.strpath,
            'ENVOY_MIGRATION_CONFIG_PATH': envoy_migration_config.strpath,
        },
        clear=True,
    ), mock.patch.object(
        configure_synapse, 'generate_configuration', autospec=True,
    ) as mock_generate_configuration, mock.patch.object(
        configure_synapse, 'get_zookeeper_topology', autospec=True,
    ), mock.patch.object(
        configure_synapse, 'get_all_namespaces', autospec=True,
    ), mock.patch.object(
        subprocess, 'check_call', autospec=True,
    ) as mock_subprocess_check_call:
        yield mock_subprocess_check_call, mock_generate_configuration


def test_synapse_restarted_when_config_files_differ(tmpdir):
    config_path = tmpdir.join('synapse.conf.json')
    config_path.write('{\n    "some": "config"\n}')

    with setup_mocks_for_main(
        tmpdir, config_path.strpath,
    ) as (mock_subprocess_check_call, mock_generate_configuration):
        mock_generate_configuration.return_value = {'some': 'new config'}
        configure_synapse.main()

    # The synapse config file on disk should have been modified.
    assert config_path.read() == '{\n    "some": "new config"\n}'
    # synapse should have been reloaded.
    assert mock_subprocess_check_call.mock_calls == [
        mock.call(['service', 'synapse', 'stop']),
        mock.call(['service', 'synapse', 'start'])
    ]


def test_synapse_not_restarted_when_config_files_are_identical(tmpdir):
    config_path = tmpdir.join('synapse.conf.json')
    config_path.write('{\n    "some": "config"\n}')

    with setup_mocks_for_main(
        tmpdir, config_path.strpath,
    ) as (mock_subprocess_check_call, mock_generate_configuration):
        mock_generate_configuration.return_value = {'some': 'config'}
        configure_synapse.main()

    # The synapse config file on disk should not have been modified.
    assert config_path.read() == '{\n    "some": "config"\n}'
    # synapse should not have been reloaded.
    assert mock_subprocess_check_call.called is False


def test_chaos_delay(mock_get_current_location, mock_available_location_types):
    with mock.patch.object(configure_synapse, 'get_my_grouping') as grouping_mock:
        grouping_mock.return_value = 'my_ecosystem'
        actual_configuration = configure_synapse.generate_configuration(
            synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
            zookeeper_topology=['1.2.3.4'],
            services=[
                (
                    'test_service',
                    {
                        'proxy_port': 1234,
                        'chaos': {'ecosystem': {'my_ecosystem': {'delay': '300ms'}}}
                    }
                )
            ],
            envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
        )
        grouping_mock.assert_called_once_with('ecosystem')
    frontend = actual_configuration['services']['test_service']['haproxy']['frontend']
    assert 'tcp-request inspect-delay 300ms' in frontend
    assert 'tcp-request content accept if WAIT_END' in frontend


def test_chaos_drop(mock_get_current_location, mock_available_location_types):
    with mock.patch.object(configure_synapse, 'get_my_grouping') as grouping_mock:
        grouping_mock.return_value = 'my_ecosystem'
        actual_configuration = configure_synapse.generate_configuration(
            synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
            zookeeper_topology=['1.2.3.4'],
            services=[
                (
                    'test_service',
                    {
                        'proxy_port': 1234,
                        'chaos': {'ecosystem': {'my_ecosystem': {'fail': 'drop'}}}
                    }
                )
            ],
            envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
        )
        grouping_mock.assert_called_once_with('ecosystem')
    frontend = actual_configuration['services']['test_service']['haproxy']['frontend']
    assert 'tcp-request content reject' in frontend


def test_chaos_error_503(mock_get_current_location, mock_available_location_types):
    with mock.patch.object(configure_synapse, 'get_my_grouping') as grouping_mock:
        grouping_mock.return_value = 'my_ecosystem'
        actual_configuration = configure_synapse.generate_configuration(
            synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0'}),
            zookeeper_topology=['1.2.3.4'],
            services=[
                (
                    'test_service',
                    {
                        'proxy_port': 1234,
                        'chaos': {'ecosystem': {'my_ecosystem': {'fail': 'error_503'}}}
                    }
                )
            ],
            envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
        )
        assert actual_configuration['services']['test_service']['discovery']['method'] == 'base'


def test_discovery_only_services(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults({
        'bind_addr': '0.0.0.0',
        'listen_with_nginx': True,
        'listen_with_haproxy': True,
    })
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            (
                'test_service',
                {
                    'proxy_port': None,
                    'healthcheck_uri': '/status',
                    'retries': 2,
                    'timeout_connect_ms': 2000,
                    'timeout_server_ms': 3000,
                    'extra_headers': {
                        'X-Mode': 'ro'
                    },
                    'extra_healthcheck_headers': {
                        'X-Mode': 'ro'
                    },
                    'balance': 'roundrobin',
                    'advertise': ['region', 'superregion'],
                    'discover': 'region',
                }
            )
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=synapse_tools_config
    )
    expected_configuration['services'] = {
        'test_service': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'region:my_region',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'disabled': True
            },
            'nginx': {
                'disabled': True
            },
        },
        'test_service.superregion': {
            'default_servers': [],
            'use_previous_backends': False,
            'discovery': {
                'hosts': ['1.2.3.4', '2.3.4.5'],
                'method': 'zookeeper',
                'path': '/smartstack/global/test_service',
                'label_filters': [
                    {
                        'label': 'superregion:my_superregion',
                        'value': '',
                        'condition': 'equals',
                    },
                ],
            },
            'haproxy': {
                'disabled': True
            },
            'nginx': {
                'disabled': True
            },
        },
    }

    assert actual_configuration == expected_configuration


def test_nginx_no_proxy_proto(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults({
        'listen_with_nginx': True,
        'nginx_proxy_proto': False,
    })
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            ('test_service', {'proxy_port': 1234}),
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    # Check HAProxy binds on both PROXY protocol and regular TCP unix sockets
    frontend = actual_configuration['services']['test_service']['haproxy']['frontend']
    assert 'bind /var/run/synapse/sockets/test_service.sock' in frontend
    assert 'bind /var/run/synapse/sockets/test_service.prxy accept-proxy' in frontend

    # Check nginx doesn't send regular tcp traffic to the proxy socket
    nginx = actual_configuration['services']['test_service.nginx_listener']
    assert nginx['default_servers'][0]['port'] == '/var/run/synapse/sockets/test_service.sock'
    assert 'proxy_protocol on' not in nginx['nginx']['server']


def test_nginx_proxy_proto(mock_get_current_location, mock_available_location_types):
    synapse_tools_config = configure_synapse.set_defaults({
        'listen_with_nginx': True,
        'nginx_proxy_proto': True,
    })
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=synapse_tools_config,
        zookeeper_topology=['1.2.3.4', '2.3.4.5'],
        services=[
            ('test_service', {'proxy_port': 1234}),
        ],
        envoy_migration_config=STATUS_QUO_ENVOY_MIGRATION_CONFIG,
    )

    # Check HAProxy binds on both PROXY protocol and regular TCP unix sockets
    frontend = actual_configuration['services']['test_service']['haproxy']['frontend']
    assert 'bind /var/run/synapse/sockets/test_service.sock' in frontend
    assert 'bind /var/run/synapse/sockets/test_service.prxy accept-proxy' in frontend

    # Check nginx sends PROXY protocol traffic to the correct socket when enabled
    nginx = actual_configuration['services']['test_service.nginx_listener']
    assert nginx['default_servers'][0]['port'] == '/var/run/synapse/sockets/test_service.prxy'
    assert 'proxy_protocol on' in nginx['nginx']['server']
