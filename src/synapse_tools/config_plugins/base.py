import abc
from typing import List
from typing import Iterable
from typing import Mapping

from mypy_extensions import TypedDict


class LoggingDict(TypedDict):
    enabled: bool
    sample_rate: int


class PathBasedRoutingDict(TypedDict):
    enabled: bool


class SourceRequiredDict(TypedDict):
    enabled: bool


class PluginsDict(TypedDict, total=False):
    logging: LoggingDict
    path_based_routing: PathBasedRoutingDict
    source_required: SourceRequiredDict


class ServiceInfo(TypedDict):  # TODO: castable from ServiceNAmespaceConfig
    timeout_connect_ms: int
    timeout_client_ms: int
    timeout_server_ms: int
    mode: str
    balance: str
    keepalive: bool
    extra_headers: Mapping[str, str]
    extra_healthcheck_headers: Mapping[str, str]
    healthcheck_uri: str
    retries: int
    allredisp: bool
    proxy_port: int
    chaos: Mapping[str, Mapping[str, Mapping[str, str]]]
    plugins: PluginsDict
    proxied_through: str
    is_proxy: bool


SynapseToolsConfig = TypedDict(
    'SynapseToolsConfig',
    {
        'bind_addr': str,
        'config_file': str,
        'enable_map_debug': bool,
        'errorfiles': Mapping[str, str],
        'file_output_path': str,
        'hacheck_port': int,
        'haproxy_captured_req_headers': str,
        'haproxy_config_path': str,
        'haproxy.defaults.inter': str,
        'haproxy_reload_cmd_fmt': str,
        'haproxy_respect_allredisp': bool,
        'haproxy_restart_interval_s': int,
        'haproxy_service_proxy_sockets_path_fmt': str,
        'haproxy_service_sockets_path_fmt': str,
        'haproxy_socket_file_path': str,
        'haproxy_socket_file_path': str,
        'haproxy_state_file_path': str,
        'listen_with_haproxy': bool,
        'listen_with_nginx': bool,
        'logging': LoggingDict,
        'lua_dir': str,
        'map_debug_port': int,
        'map_dir': str,
        'map_refresh_interval': int,
        'maxconn_per_server': int,
        'maximum_connections': int,
        'maxqueue_per_server': int,
        'nginx_proxy_proto': bool,
        'reload_cmd_fmt': str,
        'stats_port': int,
        'synapse_command': List[str],
        'synapse_restart_command': str,
        'zookeeper_topology_path': str,
        'path_based_routing': PathBasedRoutingDict,
        # 'source_required': SourceRequiredDict,
        'nginx_pid_file_path': str,
        'nginx_config_path': str,
        'nginx_check_cmd_fmt': str,
        'nginx_reload_cmd_fmt': str,
        'nginx_start_cmd_fmt': str,
        'nginx_restart_interval_s': int,
        'nginx_log_error_target': str,
        'nginx_log_error_level': str,
    },
)


class HAProxyConfigPlugin(metaclass=abc.ABCMeta):
    def __init__(
        self,
        service_name: str,
        service_info: ServiceInfo,
        synapse_tools_config: SynapseToolsConfig,
    ) -> None:
        """
        Initializes plugin base class
        :param str service_name: name of service
        :param dict service_info: dictionary of service config info
        :param dict synapse_tools_config: dictionary of synapse tools
                 config options
        """
        self.service_name = service_name
        self.service_info = service_info
        self.synapse_tools_config = synapse_tools_config
        self.plugins = service_info.get('plugins', {})
        self.prepend_frontend_options = False
        self.prepend_backend_options = False
        self.prepend_global_options = False
        self.prepend_defaults_options = False

    def prepend_options(
        self,
        block_type: str,
    ) -> bool:
        """
        Checks to see if the options to a particular HAProxy block
        are to be prepended or appended. This is useful, for example, when
        you want to order your http-request rules above any reqxxx rules.
        """
        return eval('self.prepend_{}_options'.format(block_type))

    @abc.abstractmethod
    def global_options(self) -> Iterable[str]:
        """
        Options for HAProxy configuration global section
        :return: list of strings corresponding to distinct
                 lines in HAProxy config global
        """

    @abc.abstractmethod
    def defaults_options(self) -> Iterable[str]:
        """
        Options for HAProxy configuration defaults section
        :return: list of strings corresponding to distinct
                 lines in HAProxy config defaults
        """

    @abc.abstractmethod
    def frontend_options(self) -> Iterable[str]:
        """
        Options for HAProxy configuration frontend section
        :return: list of strings representing distinct
                 lines in HAProxy config frontend
        """

    @abc.abstractmethod
    def backend_options(self) -> Iterable[str]:
        """
        Options for HAProxy configuration backend section
        :return: list of strings representing distinct
                 lines in HAProxy config backend
        """
