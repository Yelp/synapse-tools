from typing import Iterable

from synapse_tools.config_plugins.base import HAProxyConfigPlugin


class ProxiedThrough(HAProxyConfigPlugin):
    def global_options(self) -> Iterable[str]:
        return []

    def defaults_options(self) -> Iterable[str]:
        return []

    def frontend_options(self) -> Iterable[str]:
        if self.service_info.get('proxied_through') is None:
            return []

        proxied_through = self.service_info.get('proxied_through')
        healthcheck_uri = self.service_info.get('healthcheck_uri', '/status')

        return [
            'acl is_status_request path {healthcheck_uri}'.format(
                healthcheck_uri=healthcheck_uri,
            ),
            'acl request_from_proxy hdr_beg(X-Smartstack-Source) -i {proxied_through}'.format(
                proxied_through=proxied_through,
            ),
            'acl proxied_through_backend_has_connslots connslots({proxied_through}) gt 0'.format(
                proxied_through=proxied_through,
            ),
            'http-request set-header X-Smartstack-Destination {service_name} if !is_status_request !request_from_proxy proxied_through_backend_has_connslots'.format(
                service_name=self.service_name,
            ),
            'use_backend {proxied_through} if !is_status_request !request_from_proxy proxied_through_backend_has_connslots'.format(
                proxied_through=proxied_through,
            ),
        ]

    def backend_options(self) -> Iterable[str]:
        # We are not a proxy for someone else
        if not self.service_info.get('is_proxy', False):
            return []

        healthcheck_uri = self.service_info.get('healthcheck_uri', '/status')
        service_name = self.service_name

        return [
            'acl is_status_request path {healthcheck_uri}'.format(
                healthcheck_uri=healthcheck_uri
            ),
            'http-request set-header X-Smartstack-Source {service_name} if !is_status_request'.format(
                service_name=service_name,
            ),
        ]
