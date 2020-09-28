from typing import Iterable

from synapse_tools.config_plugins.base import HAProxyConfigPlugin


MAX_TARPIT_TIMEOUT = "60s"
TARPIT_HEADER = "X-Ctx-Tarpit"


class FaultInjection(HAProxyConfigPlugin):
    def global_options(self) -> Iterable[str]:
        return []

    def defaults_options(self) -> Iterable[str]:
        return ["timeout tarpit %s" % MAX_TARPIT_TIMEOUT]

    def frontend_options(self) -> Iterable[str]:
        return []

    def backend_options(self) -> Iterable[str]:
        return [
            "acl to_be_tarpitted hdr_sub({header_name}) -i {service_name}".format(
                header_name=TARPIT_HEADER, service_name=self.service_name,
            ),
            "reqtarpit . if to_be_tarpitted",
        ]
