import logging


from . import BenchmarkBaseClass


logger = logging.getLogger("touchstone")


class Mb(BenchmarkBaseClass):
    def _build_search(self):
        logger.debug("Building search array for Mb")
        return self._search_dict[self._source_type][self._harness_type]

    def _build_search_metadata(self):
        return self._search_dict[self._source_type]["metadata"]

    def _build_compute(self):
        logger.debug("Building compute map")
        _temp_dict = {}
        for index in self._search_map:
            _temp_dict[index] = self._search_map[index]
        return _temp_dict

    def __init__(self, source_type=None, harness_type=None, config=None):
        logger.debug("Initializing Mb instance")
        BenchmarkBaseClass.__init__(
            self, source_type=source_type, harness_type=harness_type, config=config
        )
        self._search_dict = {
            "elasticsearch": {
                "metadata": {
                    "cpuinfo-metadata": {
                        "element": "pod_name",
                        "compare": [
                            "value.Model name",
                            "value.Architecture",
                            "value.CPU(s)",
                        ],
                    },
                    "meminfo-metadata": {
                        "element": "pod_name",
                        "compare": ["value.MemTotal", "value.Active"],
                    },
                },
                "ripsaw": {
                    "router-test-results": [
                        {
                            "filter": {"test_type": "http"},
                            "buckets": ["routes", "conn_per_targetroute", "keepalive"],
                            "aggregations": {
                                "requests_per_second": ["avg"],
                                "latency_95pctl": ["avg"],
                            },
                        },
                        {
                            "filter": {"test_type": "edge"},
                            "buckets": ["routes", "conn_per_targetroute", "keepalive"],
                            "aggregations": {
                                "requests_per_second": ["avg"],
                                "latency_95pctl": ["avg"],
                            },
                        },
                        {
                            "filter": {"test_type": "passthrough"},
                            "buckets": ["routes", "conn_per_targetroute", "keepalive"],
                            "aggregations": {
                                "requests_per_second": ["avg"],
                                "latency_95pctl": ["avg"],
                            },
                        },
                        {
                            "filter": {"test_type": "reencrypt"},
                            "buckets": ["routes", "conn_per_targetroute", "keepalive"],
                            "aggregations": {
                                "requests_per_second": ["avg"],
                                "latency_95pctl": ["avg"],
                            },
                        },
                        {
                            "filter": {"test_type": "mix"},
                            "buckets": ["routes", "conn_per_targetroute", "keepalive"],
                            "aggregations": {
                                "requests_per_second": ["avg"],
                                "latency_95pctl": ["avg"],
                            },
                        },
                    ],
                },
            },
        }
        if self.benchmark_cfg:
            self._search_dict = self.benchmark_cfg
        self._search_map = self._build_search()
        self._search_map_metadata = self._build_search_metadata()
        self._compute_map = self._build_compute()
        logger.debug("Finished initializing Mb instance")

    def emit_compute_map(self):
        logger.debug("Emitting built compute map")
        logger.info(
            "Compute map is {} in the database {}".format(
                self._compute_map, self._source_type
            )
        )
        return self._compute_map

    def emit_indices(self):
        return self._search_map.keys()

    def emit_metadata_search_map(self):
        return self._search_map_metadata
