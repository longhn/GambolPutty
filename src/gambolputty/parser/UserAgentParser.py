# -*- coding: utf-8 -*-
from uasparser2 import UASParser
import types
import BaseThreadedModule
import Decorators


@Decorators.ModuleDocstringParser
class UserAgentParser(BaseThreadedModule.BaseThreadedModule):
    r"""
    Parse http user agent string

    A string like:

        "Mozilla/5.0 (Linux; U; Android 2.3.5; en-in; HTC_DesireS_S510e Build/GRJ90) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1"

    will produce this dictionary:

        {'dist': {'version': '2.3.5', 'name': 'Android'},
         'os': {'name': 'Linux'},
         'browser': {'version': '4.0', 'name': 'Safari'}}

    source_fields:  Input field to parse.
    target_field: field to update with parsed info fields.

    Configuration template:

    - LineParser:
        source_fields:               # <type: string||list; is: required>
        target_field:                # <default: 'user_agent_info'; type:string; is: optional>
        receivers:
          - NextModule
    """

    module_type = "parser"
    """Set module type"""

    def configure(self, configuration):
        # Call parent configure method
        BaseThreadedModule.BaseThreadedModule.configure(self, configuration)
        self.source_fields = self.getConfigurationValue('source_fields')
        # Allow single string as well.
        if isinstance(self.source_fields, types.StringTypes):
            self.source_fields = [self.source_fields]
        self.target_field = self.getConfigurationValue('target_field')
        self.parser = UASParser(cache_dir='/tmp/', cache_ttl=3600*24*7, mem_cache_size=1000)

    def handleEvent(self, event):
        for source_field in self.source_fields:
            if source_field not in event:
                continue
            event[self.target_field] = self.parser.parse(event[source_field])
        yield event
