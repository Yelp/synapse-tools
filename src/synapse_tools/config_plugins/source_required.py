import os
from typing import Iterable

from synapse_tools.config_plugins.base import HAProxyConfigPlugin
from synapse_tools.config_plugins.base import ServiceInfo
from synapse_tools.config_plugins.base import SynapseToolsConfig


class SourceRequired(HAProxyConfigPlugin):
    def __init__(
        self,
        service_name: str,
        service_info: ServiceInfo,
        synapse_tools_config: SynapseToolsConfig,
    ) -> None:
        super().__init__(service_name, service_info, synapse_tools_config)

        self.enabled = self.plugins.get("source_required", {}).get("enabled", False)
        self.prepend_backend_options = True

    def global_options(self) -> Iterable[str]:
        if not self.enabled:
            return []

        lua_dir = self.synapse_tools_config["lua_dir"]
        lua_file = os.path.join(lua_dir, "add_source_header.lua")
        opts = [
            "lua-load %s" % lua_file,
        ]

        return opts

    def defaults_options(self) -> Iterable[str]:
        return []

    def frontend_options(self) -> Iterable[str]:
        return []

    def backend_options(self) -> Iterable[str]:
        if not self.enabled:
            return []
        return ["http-request lua.add_source_header"]
