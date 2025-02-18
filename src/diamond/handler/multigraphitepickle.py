# coding=utf-8

"""
Send metrics to a [graphite](http://graphite.wikidot.com/) using the pickle
interface. Unlike GraphitePickleHandler, this one supports multiple graphite
servers. Specify them as a list of hosts divided by comma.
"""

from diamond.handler.Handler import Handler
from diamond.handler.graphitepickle import GraphitePickleHandler
from copy import deepcopy


class MultiGraphitePickleHandler(Handler):
    """
    Implements the abstract Handler class, sending data to multiple
    graphite servers by using two instances of GraphitePickleHandler
    """

    def __init__(self, config=None):
        """
        Create a new instance of the MultiGraphitePickleHandler class
        """
        # Initialize Handler
        Handler.__init__(self, config)

        self.handlers = []

        # Initialize Options
        hosts = self.config['host']
        for host in hosts:
            config = deepcopy(self.config)
            config['host'] = host
            self.handlers.append(GraphitePickleHandler(config))

    def get_default_config_help(self):
        """
        Returns the help text for the configuration options for this handler
        """
        config = super(MultiGraphitePickleHandler,
                       self).get_default_config_help()

        config.update({
            'host': 'Hostname, Hostname, Hostname',
            'port': 'Port',
            'proto': 'udp or tcp',
            'timeout': '',
            'batch': 'How many to store before sending to the graphite server',
            'max_backlog_multiplier': 'how many batches to store before trimming',  # NOQA
            'trim_backlog_multiplier': 'Trim down how many batches',
        })

        return config

    def get_default_config(self):
        """
        Return the default config for the handler
        """
        config = super(MultiGraphitePickleHandler, self).get_default_config()

        config.update({
            'host': ['localhost'],
            'port': 2003,
            'proto': 'tcp',
            'timeout': 15,
            'batch': 1,
            'max_backlog_multiplier': 5,
            'trim_backlog_multiplier': 4,
        })

        return config

    def process(self, metric):
        """
        Process a metric by passing it to GraphitePickleHandler
        instances
        """
        for handler in self.handlers:
            handler.process(metric)

    def flush(self):
        """Flush metrics in queue"""
        for handler in self.handlers:
            handler.flush()
