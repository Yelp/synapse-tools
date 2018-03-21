import os
from base import HAProxyConfigPlugin


class SourceRequired(HAProxyConfigPlugin):
    def __init__(self, service_name, service_info, synapse_tools_config):
        super(SourceRequired, self).__init__(
            service_name, service_info, synapse_tools_config
        )

        self.enabled = self.plugins.get('source_required', {}).get('enabled', False)

    def global_options(self):
        if not self.enabled:
            return []

        lua_dir = self.synapse_tools_config['lua_dir']
        lua_file = os.path.join(lua_dir, 'add_source_header.lua')
        opts = [
            'lua-load %s' % lua_file,
        ]

        return opts

    def defaults_options(self):
        return []

    def frontend_options(self):
        return []

    def backend_options(self):
        if not self.enabled:
            return []
        return [
            'http-request lua.init_add_source',
            'http-request lua.add_source_header'
        ]
