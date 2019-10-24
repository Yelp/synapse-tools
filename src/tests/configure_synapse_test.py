import contextlib

import mock
import pytest

from synapse_tools import configure_synapse


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
                    # endpoint timeouts are disabled by default, so this should have no effect
                    'endpoint_timeouts': {
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
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
                    # endpoint timeouts are disabled by default, so this should have no effect
                    'endpoint_timeouts': {
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
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
        services=[]
    )

    assert 'errorfile 404 /etc/haproxy-synapse/errors/404.http' in actual_configuration['haproxy']['defaults']
    assert 'errorfile 503 /etc/haproxy-synapse/errors/503.http' in actual_configuration['haproxy']['defaults']


def test_generate_configuration_single_advertise_per_endpoint_timeouts(mock_get_current_location, mock_available_location_types):
    actual_configuration = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True}),
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
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
    )

    actual_configuration_default_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True}),
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
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True})
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
                    'acl test_service.foo_bar_timeouts_path path_beg /foo/bar',
                    'acl test_service.foo_bar_timeouts_has_connslots connslots(test_service.foo_bar_timeouts) gt 0',
                    'use_backend test_service.foo_bar_timeouts if test_service.foo_bar_timeouts_has_connslots test_service.foo_bar_timeouts_path',
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
        'test_service.foo_bar_timeouts': {
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
                'backend_name': 'test_service.foo_bar_timeouts',
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
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True}),
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
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
    )

    actual_configuration_default_advertise = configure_synapse.generate_configuration(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True}),
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
                        'foo_bar': {
                            'endpoint': '/foo/bar',
                            'endpoint_timeout_ms': 10000,
                        }
                    }
                }
            )
        ]
    )

    expected_configuration = configure_synapse.generate_base_config(
        synapse_tools_config=configure_synapse.set_defaults({'bind_addr': '0.0.0.0', 'enable_per_endpoint_timeouts': True})
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
                    'acl test_service.foo_bar_timeouts_path path_beg /foo/bar',
                    'acl test_service.foo_bar_timeouts_has_connslots connslots(test_service.foo_bar_timeouts) gt 0',
                    'use_backend test_service.foo_bar_timeouts if test_service.foo_bar_timeouts_has_connslots test_service.foo_bar_timeouts_path',
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
        'test_service.foo_bar_timeouts': {
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
                'backend_name': 'test_service.foo_bar_timeouts',
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
        ]
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
        ]
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
        services=[]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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


@contextlib.contextmanager
def setup_mocks_for_main():
    mock_tmp_file = mock.MagicMock()
    mock_file_cmp = mock.Mock()
    mock_copy = mock.Mock()
    mock_subprocess_check_call = mock.Mock()

    patchers = [
        mock.patch('synapse_tools.configure_synapse.get_zookeeper_topology'),
        mock.patch('synapse_tools.configure_synapse.get_all_namespaces'),
        mock.patch('synapse_tools.configure_synapse.generate_configuration'),
        mock.patch(
            'synapse_tools.configure_synapse.get_config',
            return_value=configure_synapse.set_defaults(
                {'bind_addr': '0.0.0.0', 'config_file': '/etc/synapse/synapse.conf.json'}
            ),
        ),
        mock.patch('tempfile.NamedTemporaryFile', return_value=mock_tmp_file),
        mock.patch('synapse_tools.configure_synapse.open', create=True),
        mock.patch('json.dump'),
        mock.patch('os.chmod'),
        mock.patch('filecmp.cmp', mock_file_cmp),
        mock.patch('shutil.copy', mock_copy),
        mock.patch('subprocess.check_call', mock_subprocess_check_call),
    ]

    with contextlib.ExitStack() as stack:
        [stack.enter_context(patch) for patch in patchers]
        yield(mock_tmp_file, mock_file_cmp, mock_copy, mock_subprocess_check_call)


def test_synapse_restarted_when_config_files_differ():
    with setup_mocks_for_main() as (
            mock_tmp_file, mock_file_cmp, mock_copy, mock_subprocess_check_call):

        # New and existing synapse configs differ
        mock_file_cmp.return_value = False

        configure_synapse.main()

        mock_copy.assert_called_with(
            mock_tmp_file.__enter__().name, '/etc/synapse/synapse.conf.json')

        expected_calls = [
            mock.call(['service', 'synapse', 'stop']),
            mock.call(['service', 'synapse', 'start'])
        ]

        assert mock_subprocess_check_call.call_args_list == expected_calls


def test_synapse_not_restarted_when_config_files_are_identical():
    with setup_mocks_for_main() as (
            mock_tmp_file, mock_file_cmp, mock_copy, mock_subprocess_check_call):

        # New and existing synapse configs are identical
        mock_file_cmp.return_value = True

        configure_synapse.main()

        mock_copy.assert_called_with(
            mock_tmp_file.__enter__().name, '/etc/synapse/synapse.conf.json')
        assert not mock_subprocess_check_call.called


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
            ]
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
            ]
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
            ]
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
        ]
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
        ]
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
        ]
    )

    # Check HAProxy binds on both PROXY protocol and regular TCP unix sockets
    frontend = actual_configuration['services']['test_service']['haproxy']['frontend']
    assert 'bind /var/run/synapse/sockets/test_service.sock' in frontend
    assert 'bind /var/run/synapse/sockets/test_service.prxy accept-proxy' in frontend

    # Check nginx sends PROXY protocol traffic to the correct socket when enabled
    nginx = actual_configuration['services']['test_service.nginx_listener']
    assert nginx['default_servers'][0]['port'] == '/var/run/synapse/sockets/test_service.prxy'
    assert 'proxy_protocol on' in nginx['nginx']['server']
