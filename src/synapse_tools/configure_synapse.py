"""Update the synapse configuration file and restart synapse if anything has
changed."""

import copy
import filecmp
import json
import os
import shutil
import socket
import subprocess
import tempfile

import yaml
from environment_tools.type_utils import available_location_types
from environment_tools.type_utils import compare_types
from environment_tools.type_utils import get_current_location
from paasta_tools.marathon_tools import get_all_namespaces
from synapse_tools.haproxy_synapse_reaper import DEFAULT_REAP_AGE_S
from yaml import CLoader


def get_config(synapse_tools_config_path):
    with open(synapse_tools_config_path) as synapse_config:
        return set_defaults(json.load(synapse_config))


def set_defaults(config):
    # Backwards compatibility for haproxy_reload_cmd_fmt
    if 'reload_cmd_fmt' in config:
        config['haproxy_reload_cmd_fmt'] = config['reload_cmd_fmt']

    defaults = [
        ('bind_addr', '0.0.0.0'),
        # HAProxy related options
        ('listen_with_haproxy', True),
        ('haproxy.defaults.inter', '10m'),
        ('haproxy_socket_file_path', '/var/run/synapse/haproxy.sock'),
        ('haproxy_captured_req_headers', 'X-B3-SpanId,X-B3-TraceId,X-B3-ParentSpanId,X-B3-Flags:10,X-B3-Sampled:10'),
        ('haproxy_config_path', '/var/run/synapse/haproxy.cfg'),
        ('haproxy_path', '/usr/bin/haproxy-synapse'),
        ('haproxy_pid_file_path', '/var/run/synapse/haproxy.pid'),
        ('haproxy_state_file_path', None),
        ('haproxy_respect_allredisp', True),
        ('haproxy_reload_cmd_fmt', """touch {haproxy_pid_file_path} && PID=$(cat {haproxy_pid_file_path}) && {haproxy_path} -f {haproxy_config_path} -p {haproxy_pid_file_path} -sf $PID"""),
        ('haproxy_service_sockets_path_fmt',
            '/var/run/synapse/sockets/{service_name}.sock'),
        ('haproxy_service_proxy_sockets_path_fmt',
            '/var/run/synapse/sockets/{service_name}.proxy_sock'),
        ('haproxy_restart_interval_s', 60),
        # Misc options
        ('file_output_path', '/var/run/synapse/services'),
        ('maximum_connections', 10000),
        ('maxconn_per_server', 50),
        ('maxqueue_per_server', 10),
        ('synapse_restart_command', ['service', 'synapse', 'restart']),
        ('zookeeper_topology_path',
            '/nail/etc/zookeeper_discovery/infrastructure/local.yaml'),
        ('hacheck_port', 6666),
        ('stats_port', 3212),
        ('proxy_proto', False),
        # NGINX related options
        ('listen_with_nginx', False),
        ('nginx_path', '/usr/sbin/nginx'),
        ('nginx_prefix', '/var/run/synapse/nginx_temp'),
        ('nginx_config_path', '/var/run/synapse/nginx.cfg'),
        ('nginx_pid_file_path', '/var/run/synapse/nginx.pid'),
        # http://nginx.org/en/docs/control.html#upgrade
        # This is apparently how you gracefully reload the binary ...
        ('nginx_reload_cmd_fmt',
            'kill -USR2 $(cat {nginx_pid_file_path}) && sleep 2 && '
            'kill -WINCH $(cat {nginx_pid_file_path}.oldbin) && '
            'kill -QUIT $(cat {nginx_pid_file_path}.oldbin)'),
        ('nginx_start_cmd_fmt',
            'mkdir -p {nginx_prefix} && (kill -0 $(cat {nginx_pid_file_path}) || '
            '{nginx_path} -c {nginx_config_path} -p {nginx_prefix})'),
        ('nginx_check_cmd_fmt',
            '{nginx_path} -t -c {nginx_config_path}'),
        # Nginx only has to restart for adding or removing new listeners
        # (aka services) This should be relatively rare so we crank up the
        # restart_interval to limit memory consumption.
        ('nginx_restart_interval_s', 600),
    ]

    for k, v in defaults:
        config.setdefault(k, v)

    return config


def get_zookeeper_topology(zookeeper_topology_path):
    with open(zookeeper_topology_path) as fp:
        zookeeper_topology = yaml.load(fp, Loader=CLoader)
    zookeeper_topology = [
        '%s:%d' % (entry[0], entry[1]) for entry in zookeeper_topology]
    return zookeeper_topology


def _generate_nginx_top_level(synapse_tools_config):
    return {
        'contexts': {
            'main': [
                'worker_processes 1',
                'worker_rlimit_nofile {0}'.format(
                    int(synapse_tools_config['maximum_connections']) * 4
                ),
                'pid {0}'.format(synapse_tools_config['nginx_pid_file_path']),
                'error_log /dev/null crit',
            ],
            'stream': [
                'tcp_nodelay on'
            ],
            'events': [
                'worker_connections {0}'.format(
                    synapse_tools_config['maximum_connections']
                ),
                'multi_accept on',
                'use epoll',
            ],
        },
        'config_file_path': synapse_tools_config['nginx_config_path'],
        'check_command': synapse_tools_config['nginx_check_cmd_fmt'].format(
            **synapse_tools_config
        ),
        'reload_command': synapse_tools_config['nginx_reload_cmd_fmt'].format(
            **synapse_tools_config
        ),
        'start_command': synapse_tools_config['nginx_start_cmd_fmt'].format(
            **synapse_tools_config
        ),
        'do_writes': True,
        'do_reloads': True,
        'restart_interval': synapse_tools_config['nginx_restart_interval_s'],
        'restart_jitter': 0.1,
        'listen_address': synapse_tools_config['bind_addr'],
    }


def _generate_haproxy_top_level(synapse_tools_config):
    haproxy_inter = synapse_tools_config['haproxy.defaults.inter']
    top_level = {
        'bind_address': synapse_tools_config['bind_addr'],
        'restart_interval': synapse_tools_config['haproxy_restart_interval_s'],
        'restart_jitter': 0.1,
        'state_file_path': '/var/run/synapse/state.json',
        'state_file_ttl': 30 * 60,
        'reload_command': synapse_tools_config['haproxy_reload_cmd_fmt'].format(**synapse_tools_config),
        'socket_file_path': synapse_tools_config['haproxy_socket_file_path'],
        'config_file_path': synapse_tools_config['haproxy_config_path'],
        'do_writes': True,
        'do_reloads': True,
        'do_socket': True,
        'server_order_seed': hash(socket.gethostname()),

        'global': [
            'daemon',
            'maxconn %d' % synapse_tools_config['maximum_connections'],
            'stats socket {0} level admin'.format(
                synapse_tools_config['haproxy_socket_file_path']
            ),

            # Default of 16k is too small and causes HTTP 400 errors
            'tune.bufsize 32768',

            # Add random jitter to checks
            'spread-checks 50',

            # Send syslog output to syslog2scribe
            'log 127.0.0.1:1514 daemon info',
            'log-send-hostname',
            'unix-bind mode 666'

        ],

        'defaults': [
            # Various timeout values
            'timeout connect 200ms',
            'timeout client 1000ms',
            'timeout server 1000ms',

            # On failure, try a different server
            'retries 1',
            'option redispatch 1',

            # The server with the lowest number of connections receives the
            # connection by default
            'balance leastconn',

            # Assume it's an HTTP service
            'mode http',

            # Actively close connections to prevent old HAProxy instances
            # from hanging around after restarts
            'option forceclose',

            # Sometimes our headers contain invalid characters which would
            # otherwise cause HTTP 400 errors
            'option accept-invalid-http-request',

            # Use the global logging defaults
            'log global',

            # Log any abnormal connections at 'error' severity
            'option log-separate-errors',

            # Normally just check at <inter> period in order to minimize load
            # on individual services.  However, if we get anything other than
            # a 100 -- 499, 501 or 505 response code on user traffic then
            # force <fastinter> check period.
            #
            # NOTES
            #
            # * This also requires 'check observe layer7' on the server
            #   options.
            # * When 'on-error' triggers a check, it will only occur after
            #   <fastinter> delay.
            # * Under the assumption of 100 client machines each
            #   healthchecking a service instance:
            #
            #     10 minute <inter>     -> 0.2qps
            #     30 second <downinter> -> 3.3qps
            #     30 second <fastinter> -> 3.3qps
            #
            # * The <downinter> checks should only occur when Zookeeper is
            #   down; ordinarily Nerve will quickly remove a backend if it
            #   fails its local healthcheck.
            # * The <fastinter> checks may occur when a service is generating
            #   errors but is still passing its healthchecks.
            ('default-server on-error fastinter error-limit 1'
             ' inter {inter} downinter 30s fastinter 30s'
             ' rise 1 fall 2'.format(inter=haproxy_inter)),
        ],

        'extra_sections': {
            'listen stats': [
                'bind :%d' % synapse_tools_config['stats_port'],
                'mode http',
                'stats enable',
                'stats uri /',
                'stats refresh 1m',
                'stats show-node',
            ]
        }
    }

    # Just for the migration to HAProxy 1.7, when SMTSTK-190 is done
    # always have this enabled and set the default to a sane default instead
    # of None
    if synapse_tools_config.get('haproxy_state_file_path'):
        top_level['global'].append(
            'server-state-file {0}'.format(
                synapse_tools_config.get('haproxy_state_file_path')
            )
        )
        top_level['defaults'].append('load-server-state-from-file global')

    return top_level


def generate_base_config(synapse_tools_config):
    synapse_tools_config = synapse_tools_config
    base_config = {
        # We'll fill this section in
        'services': {},
        'file_output': {'output_directory': synapse_tools_config['file_output_path']},
        'haproxy': _generate_haproxy_top_level(synapse_tools_config)
    }

    if synapse_tools_config['listen_with_nginx']:
        base_config['nginx'] = _generate_nginx_top_level(synapse_tools_config)

    # This allows us to add optional non-default error file directives; they
    # should be a nested JSON object within the synapse-tools config of this
    # sort:
    # {
    #   'errorfiles': {
    #     '404': '/etc/haproxy-synapse/errors/404.http',
    #     '503': '/etc/haproxy-synapse/errors/503.http'
    #   }
    # }
    #
    # This will add the following lines to the 'defaults' section of the
    # haproxy config:
    # errorfile 404 /etc/haproxy-synapse/errors/404.http
    # errorfile 503 /etc/haproxy-synapse/errors/503.http
    error_list = [
        "errorfile {} {}".format(error, errorfile)
        for error, errorfile in synapse_tools_config.get('errorfiles', {}).iteritems()
    ]
    base_config['haproxy']['defaults'].extend(error_list)

    return base_config


def get_backend_name(service_name, discover_type, advertise_type):
    if advertise_type == discover_type:
        return service_name
    else:
        return '%s.%s' % (service_name, advertise_type)


def _get_socket_path(synapse_tools_config, service_name, proxy_proto=False):
    if proxy_proto:
        socket_fmt_option = 'haproxy_service_proxy_sockets_path_fmt'
    else:
        socket_fmt_option = 'haproxy_service_sockets_path_fmt'

    socket_path = synapse_tools_config[socket_fmt_option].format(
        service_name=service_name
    )
    return socket_path


def generate_acls_for_service(
        service_name,
        discover_type,
        advertise_types,
        proxied_through,
        healthcheck_uri):
    frontend_acl_configs = []

    # check for proxied_through first, use_backend ordering matters
    if proxied_through:
        frontend_acl_configs.extend([
            'acl is_status_request path {healthcheck_uri}'.format(
                healthcheck_uri=healthcheck_uri,
            ),
            'acl request_from_proxy hdr_beg(X-Smartstack-Source) -i {proxied_through}'.format(
                proxied_through=proxied_through,
            ),
            'acl proxied_through_backend_has_connslots connslots({proxied_through}) gt 0'.format(
                proxied_through=proxied_through,
            ),
            'use_backend {proxied_through} if !is_status_request !request_from_proxy proxied_through_backend_has_connslots'.format(
                proxied_through=proxied_through,
            ),
            'reqadd X-Smartstack-Destination:\ {service_name} if !is_status_request !request_from_proxy proxied_through_backend_has_connslots'.format(
                service_name=service_name,
            ),
        ])

    for advertise_type in advertise_types:
        if compare_types(discover_type, advertise_type) < 0:
            # don't create acls that downcast requests
            continue

        backend_identifier = get_backend_name(
            service_name=service_name,
            discover_type=discover_type,
            advertise_type=advertise_type,
        )

        # use connslots acl condition
        frontend_acl_configs.extend(
            [
                'acl {backend_identifier}_has_connslots connslots({backend_identifier}) gt 0'.format(
                    backend_identifier=backend_identifier,
                ),
                'use_backend {backend_identifier} if {backend_identifier}_has_connslots'.format(
                    backend_identifier=backend_identifier,
                ),
            ]
        )
    return frontend_acl_configs


def generate_configuration(synapse_tools_config, zookeeper_topology, services):
    synapse_config = generate_base_config(synapse_tools_config)
    available_locations = available_location_types()
    location_depth_mapping = {
        loc: depth
        for depth, loc in enumerate(available_locations)
    }
    available_locations = set(available_locations)
    proxies = [
        service_info['proxied_through']
        for _, service_info in services
        if service_info.get('proxied_through') is not None
    ]

    for (service_name, service_info) in services:
        proxy_port = service_info.get('proxy_port', -1)
        # If we end up with the default value or a negative number in general,
        # then we know that the service does not want to be in SmartStack
        if proxy_port is not None and proxy_port < 0:
            continue
        # Note that at this point proxy_port can be:
        # * valid number: Wants Load balancing (HAProxy/Nginx)
        # * None: Wants discovery, but no load balancing (files)

        discover_type = service_info.get('discover', 'region')
        advertise_types = sorted(
            [
                advertise_typ
                for advertise_typ in service_info.get('advertise', ['region'])
                # don't consider invalid advertise types
                if advertise_typ in available_locations
            ],
            key=lambda typ: location_depth_mapping[typ],
            reverse=True,  # consider the most specific types first
        )
        if discover_type not in advertise_types:
            return {}

        base_watcher_cfg = base_watcher_cfg_for_service(
            service_name=service_name,
            service_info=service_info,
            zookeeper_topology=zookeeper_topology,
            synapse_tools_config=synapse_tools_config,
            is_proxy=service_name in proxies,
        )

        socket_path = _get_socket_path(
            synapse_tools_config, service_name
        )

        socket_proxy_path = _get_socket_path(
            synapse_tools_config, service_name, proxy_proto=True
        )

        for advertise_type in advertise_types:
            backend_identifier = get_backend_name(
                service_name, discover_type, advertise_type
            )
            config = copy.deepcopy(base_watcher_cfg)

            config['discovery']['label_filters'] = [
                {
                    'label': '%s:%s' % (advertise_type, get_current_location(advertise_type)),
                    'value': '',
                    'condition': 'equals',
                },
            ]

            if proxy_port is None:
                config['haproxy'] = {'disabled': True}
                if synapse_tools_config['listen_with_nginx']:
                    config['nginx'] = {'disabled': True}
            else:
                if advertise_type == discover_type:
                    # Specify a proxy port to create a frontend for this service
                    if synapse_tools_config['listen_with_haproxy']:
                        config['haproxy']['port'] = str(proxy_port)
                        config['haproxy']['frontend'].extend(
                            [
                                'bind {0}'.format(socket_path),
                                'bind {0} accept-proxy'.format(socket_proxy_path),
                            ]
                        )
                    # If listen_with_haproxy is False, then have
                    # HAProxy bind only to the socket. Nginx may or may not
                    # be listening on ports based on listen_with_nginx values
                    # at this stage.
                    else:
                        config['haproxy']['port'] = None
                        config['haproxy']['bind_address'] = socket_path
                        config['haproxy']['frontend'].append(
                            'bind {0} accept-proxy'.format(socket_proxy_path)
                        )
                else:
                    # The backend only watchers don't need frontend
                    # because they have no listen port, so Synapse doens't
                    # generate a frontend section for them at all
                    del config['haproxy']['frontend']
                config['haproxy']['backend_name'] = backend_identifier

            synapse_config['services'][backend_identifier] = config

        if proxy_port is not None:
            proxied_through = service_info.get('proxied_through')
            healthcheck_uri = service_info.get('healthcheck_uri', '/status')

            # populate the ACLs to route to the service backends
            synapse_config['services'][service_name]['haproxy']['frontend'].extend(
                generate_acls_for_service(
                    service_name=service_name,
                    discover_type=discover_type,
                    advertise_types=advertise_types,
                    proxied_through=proxied_through,
                    healthcheck_uri=healthcheck_uri,
                )
            )

            # If nginx is supported, include a single additional static
            # service watcher per service that listens on the right port and
            # proxies back to the unix socket exposed by HAProxy
            if synapse_tools_config['listen_with_nginx']:
                listener_name = '{0}.nginx_listener'.format(service_name)
                synapse_config['services'][listener_name] = (
                    _generate_nginx_for_watcher(
                        service_name, service_info, synapse_tools_config
                    )
                )

    return synapse_config


def base_watcher_cfg_for_service(service_name, service_info, zookeeper_topology, synapse_tools_config, is_proxy):
    discovery = {
        'method': 'zookeeper',
        'path': '/smartstack/global/%s' % service_name,
        'hosts': zookeeper_topology,
    }

    haproxy = _generate_haproxy_for_watcher(
        service_name, service_info, synapse_tools_config, is_proxy
    )

    chaos = service_info.get('chaos')
    if chaos:
        frontend_chaos, discovery = chaos_options(chaos, discovery)
        haproxy['frontend'].extend(frontend_chaos)

    # Now write the actual synapse service entry
    service = {
        'default_servers': [],
        # See SRV-1190
        'use_previous_backends': False,
        'discovery': discovery,
        'haproxy': haproxy,
    }

    if synapse_tools_config['listen_with_nginx']:
        # The dynamic service watchers do not want nginx to react to their
        # changes
        service['nginx'] = {
            'disabled': True
        }

    return service


def _generate_captured_request_headers(synapse_tools_config):
    header_pairs = [
        pair.strip().partition(":") for pair in
        synapse_tools_config['haproxy_captured_req_headers'].split(',')
    ]
    headers = ["capture request header %s len %s" % (pair[0], pair[2] or '64')
               for pair in header_pairs]
    return headers


def _generate_haproxy_for_watcher(service_name, service_info, synapse_tools_config, is_proxy):
    # Note that validations of all the following config options are done in
    # config post-receive so invalid config should never get here

    # If the service sets one timeout but not the other, set both
    # as per haproxy best practices.
    default_timeout = max(
        service_info.get('timeout_client_ms'),
        service_info.get('timeout_server_ms')
    )

    # Server options
    # Things that get appended to each server line in HAProxy
    mode = service_info.get('mode', 'http')
    if mode == 'http':
        server_options = 'check port %d observe layer7 maxconn %d maxqueue %d'
    else:
        server_options = 'check port %d observe layer4 maxconn %d maxqueue %d'
    server_options = server_options % (
        synapse_tools_config['hacheck_port'],
        synapse_tools_config['maxconn_per_server'],
        synapse_tools_config['maxqueue_per_server'],
    )

    # Frontend options
    # All things related to the listening sockets on HAProxy
    # These are what clients connect to
    frontend_options = []
    timeout_client_ms = service_info.get(
        'timeout_client_ms', default_timeout
    )
    if timeout_client_ms is not None:
        frontend_options.append('timeout client %dms' % timeout_client_ms)

    if mode == 'http':
        frontend_options.extend(_generate_captured_request_headers(synapse_tools_config))
        frontend_options.append('option httplog')
    elif mode == 'tcp':
        frontend_options.append('no option accept-invalid-http-request')
        frontend_options.append('option tcplog')

    # Backend options
    # All things related to load balancing to backend servers
    backend_options = []

    balance = service_info.get('balance')
    if balance is not None and balance in ('leastconn', 'roundrobin'):
        backend_options.append('balance %s' % balance)

    keepalive = service_info.get('keepalive', False)
    if keepalive and mode == 'http':
        backend_options.extend([
            'no option forceclose',
            'option http-keep-alive'
        ])

    if mode == 'tcp':
        # We need to put the frontend and backend into tcp mode
        frontend_options.append('mode tcp')
        backend_options.append('mode tcp')

    if is_proxy:
        backend_options.extend(
            [
                'acl is_status_request path {healthcheck_uri}'.format(
                    healthcheck_uri=service_info.get('healthcheck_uri', '/status'),
                ),
                'reqadd X-Smartstack-Source:\ {service_name} if !is_status_request'.format(
                    service_name=service_name,
                ),
            ]
        )

    extra_headers = service_info.get('extra_headers', {})
    for header, value in extra_headers.iteritems():
        backend_options.append('reqidel ^%s:.*' % (header))
    for header, value in extra_headers.iteritems():
        backend_options.append('reqadd %s:\ %s' % (header, value))

    # hacheck healthchecking
    # Note that we use a dummy port value of '0' here because HAProxy is
    # passing in the real port using the X-Haproxy-Server-State header.
    # See SRV-1492 / SRV-1498 for more details.
    port = 0
    extra_healthcheck_headers = service_info.get('extra_healthcheck_headers', {})

    if len(extra_healthcheck_headers) > 0:
        healthcheck_base = 'HTTP/1.1'
        headers_string = healthcheck_base + ''.join(r'\r\n%s:\ %s' % (k, v) for (k, v) in extra_healthcheck_headers.iteritems())
    else:
        headers_string = ""

    healthcheck_uri = service_info.get('healthcheck_uri', '/status')
    healthcheck_string = r'option httpchk GET /%s/%s/%d/%s %s' % \
        (mode, service_name, port, healthcheck_uri.lstrip('/'), headers_string)

    healthcheck_string = healthcheck_string.strip()
    backend_options.append(healthcheck_string)

    backend_options.append('http-check send-state')

    retries = service_info.get('retries')
    if retries is not None:
        backend_options.append('retries %d' % retries)

    # Once we are on 1.7, we can remove this entirely
    if synapse_tools_config['haproxy_respect_allredisp']:
        allredisp = service_info.get('allredisp')
        if allredisp is not None and allredisp:
            backend_options.append('option allredisp')

    timeout_connect_ms = service_info.get('timeout_connect_ms')

    if timeout_connect_ms is not None:
        backend_options.append('timeout connect %dms' % timeout_connect_ms)

    timeout_server_ms = service_info.get(
        'timeout_server_ms', default_timeout
    )
    if timeout_server_ms is not None:
        backend_options.append('timeout server %dms' % timeout_server_ms)

    return {
        'server_options': server_options,
        'frontend': frontend_options,
        'backend': backend_options,
        # We don't actually want to use listen, it's confusing and unclear
        # what is happening (e.g. these directives are not actually going
        # into HAProxy listen sections, instead Synapse is automatically
        # routing them to backend or frontend based on its understanding
        # of HAProxy's options ... let's just do that ourselves)
        'listen': [],
    }


def _generate_nginx_for_watcher(service_name, service_info, synapse_tools_config):
    socket_path = _get_socket_path(
        synapse_tools_config,
        service_name,
        proxy_proto=synapse_tools_config['proxy_proto'],
    )

    # For the nginx listener, we just want the highest possible timeout.
    # To limit memory usage we set this to the max reap age (so HAProxy will
    # always time out the connection, not NGINX). We add an epsilon of 10
    # just to really really make sure that HAProxy does the error codes
    timeout = int(DEFAULT_REAP_AGE_S) + 10
    server = ['proxy_timeout {0}s'.format(timeout)]

    # Send PROXY protocol to HAProxy proxy sockets only if enabled
    if synapse_tools_config['proxy_proto']:
        server.append('proxy_protocol on')

    # All we want from nginx is TCP termination, no http even for
    # http services. HAProxy is responsible for all layer7 choices
    nginx_config = {
        'mode': 'tcp',
        'port': service_info['proxy_port'],
        'server': server,
    }

    # When both nginx and haproxy are listening on ports, nginx
    # has to have the reuseport option enabled. However with just nginx
    # we want this **OFF** because otherwise nginx reloads are not hitless
    # on Linux < 4.4
    both_listen = (
        synapse_tools_config['listen_with_haproxy'] and
        synapse_tools_config['listen_with_nginx']
    )
    if both_listen:
        nginx_config['listen_options'] = 'reuseport'

    service = {
        'default_servers': [
            {'host': 'unix', 'port': socket_path}
        ],
        'use_previous_backends': True,
        'discovery': {
            'method': 'base'
        },
        'haproxy': {
            'disabled': True
        },
        'file_output': {
            'disabled': True
        },
        'nginx': nginx_config
    }
    return service


def chaos_options(chaos_dict, discovery_dict):
    """ Return a tuple of
    (additional_frontend_options, replacement_discovery_dict) """

    chaos_entries = merge_dict_for_my_grouping(chaos_dict)
    fail = chaos_entries.get('fail')
    delay = chaos_entries.get('delay')

    if fail == 'drop':
        return ['tcp-request content reject'], discovery_dict

    if fail == 'error_503':
        # No additional frontend_options, but use the
        # base (no-op) discovery method
        discovery_dict = {'method': 'base'}
        return [], discovery_dict

    if delay:
        return [
            'tcp-request inspect-delay {0}'.format(delay),
            'tcp-request content accept if WAIT_END'
        ], discovery_dict

    return [], discovery_dict


def merge_dict_for_my_grouping(chaos_dict):
    """ Given a dictionary where the top-level keys are
    groupings (ecosystem, habitat, etc), merge the subdictionaries
    whose values match the grouping that this host is in.
    e.g.

    habitat:
        sfo2:
            some_key: some_value
    runtimeenv:
        prod:
            another_key: another_value
        devc:
            foo_key: bar_value

    for a host in sfo2/prod, would return
        {'some_key': some_value, 'another_key': another_value}
    """
    result = {}
    for grouping_type, grouping_dict in chaos_dict.iteritems():
        my_grouping = get_my_grouping(grouping_type)
        entry = grouping_dict.get(my_grouping, {})
        result.update(entry)
    return result


def get_my_grouping(grouping_type):
    with open('/nail/etc/{0}'.format(grouping_type)) as fd:
        return fd.read().strip()


def main():
    my_config = get_config(
        os.environ.get(
            'SYNAPSE_TOOLS_CONFIG_PATH', '/etc/synapse/synapse-tools.conf.json'
        )
    )

    new_synapse_config = generate_configuration(
        my_config,
        get_zookeeper_topology(
            my_config['zookeeper_topology_path']
        ), get_all_namespaces()
    )

    with tempfile.NamedTemporaryFile() as tmp_file:
        new_synapse_config_path = tmp_file.name
        with open(new_synapse_config_path, 'w') as fp:
            json.dump(new_synapse_config, fp, sort_keys=True, indent=4, separators=(',', ': '))

        # Match permissions that puppet expects
        os.chmod(new_synapse_config_path, 0644)

        # Restart synapse if the config files differ
        should_restart = not filecmp.cmp(new_synapse_config_path, my_config['config_file'])

        # Always swap new config file into place.  Our monitoring system
        # checks the config['config_file'] file age to ensure that it is
        # continually being updated.
        shutil.copy(new_synapse_config_path, my_config['config_file'])

        if should_restart:
            subprocess.check_call(my_config['synapse_restart_command'])


if __name__ == '__main__':
    main()
