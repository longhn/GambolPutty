# -*- coding: utf-8 -*-
import sys
import Utils
import BaseThreadedModule
import Decorators
import socket
import time


@Decorators.ModuleDocstringParser
class GraphiteSink(BaseThreadedModule.BaseThreadedModule):
    """
    Send metrics to graphite server.

    server: Graphite server to connect to.
    port: Port carbon-cache is listening on.
    formats: Format of messages to send to graphite, e.g.: ['gambolputty.stats.event_rate_%(interval)ds %(event_rate)s'].
    store_interval_in_secs: Send data to graphite in x seconds intervals.
    batch_size: Send data to graphite if event count is above, even if store_interval_in_secs is not reached.
    backlog_size: Send count of events waiting for transmission. Events above count will be dropped.

    Here a simple example to send http_status statistics to graphite:

    ...

    - Statistics:
        interval: 10
        fields: ['http_status']

    - GraphiteSink:
        filter: if %(field_name) == "http_status"
        server: 127.0.0.1
        batch_size: 1
        formats: ['gambolputty.stats.http_200_%(interval)ds %(field_counts.200)d',
                  'gambolputty.stats.http_400_%(interval)ds %(field_counts.400)d',
                  'gambolputty.stats.http_total_%(interval)ds %(total_count)d']

    ...

    Configuration template:

    - GraphiteSink:
        server:                   # <default: 'localhost'; type: string; is: optional>
        port:                     # <default: 2003; type: integer; is: optional>
        formats:                  # <type: list; is: required>
        store_interval_in_secs:   # <default: 5; type: integer; is: optional>
        batch_size:               # <default: 1; type: integer; is: optional>
        backlog_size:             # <default: 50; type: integer; is: optional>
    """

    module_type = "output"
    """Set module type"""

    def configure(self, configuration):
        # Call parent configure method
        BaseThreadedModule.BaseThreadedModule.configure(self, configuration)
        self.formats = self.getConfigurationValue('formats')
        self.connection_data = (self.getConfigurationValue('server'), self.getConfigurationValue('port'))
        self.connection = None

    def connect(self):
        # Connect to server
        connection = socket.socket()
        try:
            connection.connect(self.connection_data)
            return connection
        except:
            etype, evalue, etb = sys.exc_info()
            self.logger.error("Failed to connect to %s. Exception: %s, Error: %s." % (self.connection_data, etype, evalue))
            return False

    def initAfterFork(self):
        self.buffer = Utils.Buffer(self.getConfigurationValue('batch_size'), self.storeData, self.getConfigurationValue('store_interval_in_secs'), maxsize=self.getConfigurationValue('backlog_size'))
        self.connection = self.connect()
        if not self.connection:
            self.gp.shutDown()
            return
        BaseThreadedModule.BaseThreadedModule.initAfterFork(self)

    def handleEvent(self, event):
        for format in self.formats:
            mapped_data = self.mapDynamicValue(format, event)
            if mapped_data:
                self.buffer.append("%s %s" % (mapped_data, int(time.time())))
        yield None

    def storeData(self, events):
        for event in events:
            try:
                if not event.endswith("\n"):
                    event += "\n"
                self.connection.send(event)
                return True
            except:
                etype, evalue, etb = sys.exc_info()
                self.logger.error("Server communication error. Exception: %s, Error: %s." % (etype, evalue))
                tries = 0
                self.connection.close()
                self.connection = None
                while tries < 5 and not self.connection:
                    time.sleep(5)
                    self.logger.warning("Trying to reconnect to %s." % (self.connection_data))
                    # Try to reconnect.
                    self.connection = self.connect()
                    tries += 1
                if not self.connection:
                    self.logger.error("Reconnect failed. Shutting down.")
                    self.gp.shutDown()
                else:
                    self.logger.info("Reconnection to %s successful." % (self.connection_data))

    def shutDown(self):
        try:
            self.connection.close()
        except:
            pass