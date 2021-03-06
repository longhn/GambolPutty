# -*- coding: utf-8 -*-
import BaseThreadedModule
import pprint
import Utils
import Decorators
import time


@Decorators.ModuleDocstringParser
class StdOutSink(BaseThreadedModule.BaseThreadedModule):
    """
    Print the data dictionary to stdout.

    pretty_print: Use pythons pprint function.
    format: Format of messages to send to graphite, e.g.: ['gambolputty.stats.event_rate_%(interval)ds %(event_rate)s'].

    Configuration template:

    - StdOutSink:
        pretty_print:           # <default: True; type: boolean; is: optional>
        format:                 # <default: None; type: None||string; is: optional>
        parser:                 # <default: None; type: None||string; is: optional>
    """

    module_type = "output"
    """Set module type"""

    def configure(self, configuration):
        # Call parent configure method
        BaseThreadedModule.BaseThreadedModule.configure(self, configuration)
        self.format = self.getConfigurationValue('format')
        self.pretty_print = self.getConfigurationValue('pretty_print')
        self.printing = False

    def handleEvent(self, event):
        while self.printing:
            time.sleep(.0001)
        self.printing = True
        if self.format:
            output = Utils.mapDynamicValue(self.format, event)
        else:
            output = event
        if self.pretty_print and not self.format:
            pprint.pprint(output, indent=4)
        else:
            print "%s" % output
        self.printing = False
        yield None
