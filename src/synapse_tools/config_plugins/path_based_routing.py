import os
from typing import Iterable

from synapse_tools.config_plugins.base import HAProxyConfigPlugin
from synapse_tools.config_plugins.base import ServiceInfo
from synapse_tools.config_plugins.base import SynapseToolsConfig


class PathBasedRouting(HAProxyConfigPlugin):
    def __init__(
        self,
        service_name: str,
        service_info: ServiceInfo,
        synapse_tools_config: SynapseToolsConfig,
    ) -> None:
        super(PathBasedRouting, self).__init__(
            service_name, service_info, synapse_tools_config
        )

        global_enabled = self.synapse_tools_config.get('path_based_routing', {}).get('enabled', False)
        svc_enabled = self.plugins.get('path_based_routing', {}).get('enabled', False)
        self.enabled = svc_enabled or global_enabled

    def global_options(self) -> Iterable[str]:
        if not self.enabled:
            return []

        lua_dir = self.synapse_tools_config['lua_dir']
        file_path = os.path.join(lua_dir, 'path_based_routing.lua')
        return ['lua-load %s' % file_path]

    def defaults_options(self) -> Iterable[str]:
        return []

    def frontend_options(self) -> Iterable[str]:
        if not self.enabled:
            return []

        return [
            'http-request set-var(txn.backend_name) lua.get_backend',
            'use_backend %[var(txn.backend_name)]'
        ]

    def backend_options(self) -> Iterable[str]:
        return []
