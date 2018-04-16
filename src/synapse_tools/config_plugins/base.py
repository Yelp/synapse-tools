import abc


class HAProxyConfigPlugin(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, service_name, service_info, synapse_tools_config):
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

    def prepend_options(self, block_type):
        """
        Checks to see if the options to a particular HAProxy block
        are to be prepended or appended. This is useful, for example, when
        you want to order your http-request rules above any reqxxx rules.
        """
        return eval('self.prepend_{}_options'.format(block_type))

    @abc.abstractmethod
    def global_options(self):
        """
        Options for HAProxy configuration global section
        :return: list of strings corresponding to distinct
                 lines in HAProxy config global
        """
        return

    @abc.abstractmethod
    def defaults_options(self):
        """
        Options for HAProxy configuration defaults section
        :return: list of strings corresponding to distinct
                 lines in HAProxy config defaults
        """

    @abc.abstractmethod
    def frontend_options(self):
        """
        Options for HAProxy configuration frontend section
        :return: list of strings representing distinct
                 lines in HAProxy config frontend
        """
        return

    @abc.abstractmethod
    def backend_options(self):
        """
        Options for HAProxy configuration backend section
        :return: list of strings representing distinct
                 lines in HAProxy config backend
        """
        return
