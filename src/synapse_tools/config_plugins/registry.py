from collections import OrderedDict
from typing import Mapping
from typing import Type

from synapse_tools.config_plugins.base import HAProxyConfigPlugin
from synapse_tools.config_plugins.fault_injection import FaultInjection
from synapse_tools.config_plugins.logging import Logging
from synapse_tools.config_plugins.path_based_routing import PathBasedRouting
from synapse_tools.config_plugins.proxied_through import ProxiedThrough
from synapse_tools.config_plugins.source_required import SourceRequired

PLUGIN_REGISTRY: Mapping[str, Type[HAProxyConfigPlugin]] = OrderedDict(
    [
        ("fault_injection", FaultInjection),
        ("proxied_through", ProxiedThrough),
        ("logging", Logging),
        ("path_based_routing", PathBasedRouting),
        ("source_required", SourceRequired),
    ]
)
