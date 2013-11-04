# -*- coding: utf-8 -*-
import Utils
import itertools
import BaseThreadedModule
import Decorators

@Decorators.ModuleDocstringParser
class Permutate(BaseThreadedModule.BaseThreadedModule):
    """

    Configuration example:

    - module: Permutate
      configuration:
        source_field: facets                # <type: string; is: required>
        target_fields: ['field1', 'field2'] # <type: list; is: required>
        length: 2                           # <default: None; type: None||integer; is: optional>
        context_data_field: context_data    # <default: ""; type:string; is: optional>
      receivers:
        - NextModule
    """

    def handleData(self, event):
        """
        Process the event.

        @param event: dictionary
        @return data: dictionary
        """

        try:
            context_data = event[self.getConfigurationValue('context_data_field')]
        except KeyError:
            context_data = False
        try:
            permutation_data = event[self.getConfigurationValue('source_field')]
        except KeyError:
            yield event
            return
        if type(permutation_data) is not list:
            yield event
            return
        length = self.getConfigurationValue('length')
        if length > len(permutation_data):
            yield event
            return
        target_field_names = self.getConfigurationValue('target_fields')
        ctx_data_idx = -1
        ctx_data_last = ""
        current_ctx_data = {}
        for permutation in itertools.permutations(permutation_data, r=length):
            event_copy = event.copy()
            if context_data:
                if ctx_data_last != permutation[0]:
                    ctx_data_idx += 1
                    ctx_data_last = permutation[0]
                try:
                    current_ctx_data = context_data[ctx_data_idx]
                except KeyError:
                    current_ctx_data = {}
                event_copy.update(current_ctx_data)
            perm = dict(zip(target_field_names, permutation))
            event_copy.update(perm)
            yield event_copy
