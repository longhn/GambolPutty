Output modules
==========

#####ElasticSearchOutput

Store the data dictionary in an elasticsearch index.

The elasticsearch module takes care of discovering all nodes of the elasticsearch cluster.
Requests will the be loadbalanced via round robin.

Configuration example:

    - module: ElasticSearchOutput
        configuration:
          nodes: ["es-01.dbap.de:9200"]             # <type: list; is: required>
          index_prefix: agora_access-               # <default: 'gambolputty-'; type: string; is: required if index_name is False else optional>
          index_name: "Fixed index name"            # <default: ""; type: string; is: required if index_prefix is False else optional>
          doc_id: 'data'                            # <default: "data"; type: string; is: optional>
          replication: 'sync'                       # <default: "sync"; type: string; is: optional>
          store_interval_in_secs: 1                 # <default: 1; type: integer; is: optional>
          max_waiting_events: 2500                  # <default: 2500; type: integer; is: optional>
      receivers:
        - NextModule

#####StdOutHandler

Print the data dictionary to stdout.

Configuration example:

    - module: StdOutHandler
      configuration:
        pretty_print: True      # <default: True; type: boolean; is: optional>
      receivers:
        - NextModule

#####DevNullSink

Just discard messages send to this module.BaseThreadedModule

    Configuration example:

    - module: DevNullSink