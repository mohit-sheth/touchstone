# -*- coding: utf-8 -*-
import argparse
import sys
import logging
import json
import yaml
import csv
from tabulate import tabulate

from touchstone import __version__
from . import benchmarks
from . import databases
from .utils.lib import mergedicts, flatten_and_discard

__author__ = "red-hat-perfscale"
__copyright__ = "red-hat-perfscale"
__license__ = "mit"

logger = logging.getLogger("touchstone")


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(description="compare results from benchmarks")
    parser.add_argument(
        "--version",
        action="version",
        version="touchstone {ver}".format(ver=__version__),
    )
    parser.add_argument(
        dest="benchmark",
        help="which type of benchmark to compare",
        type=str,
        choices=["uperf", "ycsb", "pgbench", "vegeta", "mb", "kubeburner", "scaledata"],
        metavar="benchmark",
    )
    parser.add_argument(
        dest="database",
        help="the type of database data is stored in",
        type=str,
        choices=["elasticsearch"],
        metavar="database",
    )
    parser.add_argument(
        dest="harness",
        help="the test harness that was used to run the benchmark",
        type=str,
        choices=["ripsaw"],
        metavar="harness",
    )
    parser.add_argument(
        "--id",
        "--identifier-key",
        dest="identifier",
        help="identifier key name(default: uuid)",
        type=str,
        metavar="identifier",
        default="uuid",
    )
    parser.add_argument(
        "-u",
        "--uuid",
        dest="uuid",
        help="identifier values to fetch results and compare",
        type=str,
        nargs="+",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="How should touchstone output the result",
        type=str,
        choices=["json", "yaml", "csv"],
    )
    parser.add_argument(
        "--metadata-config",
        dest="metadata_config",
        help="Metadata configuration file",
        type=argparse.FileType("r", encoding="utf-8"),
    )
    parser.add_argument(
        "--config",
        dest="config",
        help="Touchstone configuration file",
        type=argparse.FileType("r", encoding="utf-8"),
    )
    parser.add_argument(
        "--output-file",
        dest="output_file",
        help="Redirect output of json/csv/yaml to file",
        type=argparse.FileType("w"),
    )
    parser.add_argument(
        "-url",
        "--connection-url",
        dest="conn_url",
        help="the database connection strings in the same order as the uuids",
        type=str,
        nargs="+",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        help="set loglevel to INFO",
        action="store_const",
        const=logging.INFO,
    )
    parser.add_argument(
        "-vv",
        "--very-verbose",
        dest="loglevel",
        help="set loglevel to DEBUG",
        action="store_const",
        const=logging.DEBUG,
    )
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(
        level=loglevel, stream=sys.stdout, format=logformat, datefmt="%Y-%m-%d %H:%M:%S"
    )


def update(dict1, dict2):
    copy = dict1.copy()
    for key in dict2:
        if key in dict1:
            copy[key].update(dict2[key])
        else:
            copy[key] = dict2[key]
    return copy


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    setup_logging(args.loglevel)
    metadata_json = {}
    main_json = {}
    compare_uuid_dict_metadata = {}
    logger.debug("Instantiating the benchmark instance")
    benchmark_instance = benchmarks.grab(
        args.benchmark,
        source_type=args.database,
        harness_type=args.harness,
        config=args.config,
    )
    if len(args.conn_url) < len(args.uuid):
        args.conn_url = [args.conn_url[0]] * len(args.uuid)
    if args.metadata_config:
        config_file_metadata = json.load(args.metadata_config)
    output_file = args.output_file if args.output_file else sys.stdout
    # Indices from metadata map
    for uuid_index, uuid in enumerate(args.uuid):
        super_header = "\n{} UUID: {} {}".format(("=" * 67), uuid, ("=" * 67))
        compare_uuid_dict_metadata[uuid] = {}
        # Create database connection instance
        database_instance = databases.grab(
            args.database, conn_url=args.conn_url[uuid_index]
        )
        # Set metadata search map based on existence of config file
        if args.metadata_config:
            metadata_search_map = config_file_metadata["metadata"]
        else:
            metadata_search_map = benchmark_instance.emit_metadata_search_map()
        index_dict = {}
        for index in metadata_search_map.keys():
            tmp_dict = {}
            # Adding emit_compare_metadata_dict to elasticsearch class
            database_instance.emit_compare_metadata_dict(
                uuid, metadata_search_map[index], index, tmp_dict
            )
            compare_uuid_dict_metadata[uuid] = tmp_dict
            index_dict = update(tmp_dict, index_dict)
        stockpile_metadata = {}
        stockpile_metadata["where"] = []
        for where in index_dict.keys():
            # Skip if there is no associated metadata
            if not index_dict[where].items():
                continue
            stockpile_metadata["where"].append(where)
            for k, v in index_dict[where].items():
                if k not in stockpile_metadata:
                    stockpile_metadata[k] = []
                stockpile_metadata[k].append(v)
        # Check that metadata exists to be printed
        if stockpile_metadata["where"]:
            if args.output in ["csv"]:
                # Print to output file if argument present
                row_list = [["uuid", "where", "field", "value"]]
                flatten_and_discard(compare_uuid_dict_metadata, [], row_list)
                writer = csv.writer(output_file, delimiter=",")
                list(map(writer.writerow, row_list))
            elif args.output in ["json", "yaml"]:
                mergedicts(compare_uuid_dict_metadata, metadata_json)
            else:
                print(super_header, file=output_file)
                print(
                    tabulate(stockpile_metadata, headers="keys", tablefmt="pretty"),
                    file=output_file,
                )

    # Indices from entered harness (ex: ripsaw)
    for index in benchmark_instance.emit_indices():
        for compute in benchmark_instance.emit_compute_map()[index]:
            # index_json is used for csv and standard output. Since the heeader may be different in each index
            # we need to print csv or stdout for each index
            index_json = {}
            # Iterate through UUIDs
            for uuid_index, uuid in enumerate(args.uuid):
                # Create database connection instance
                database_instance = databases.grab(
                    args.database, conn_url=args.conn_url[uuid_index]
                )
                # Add method emit_compute_dict to the elasticsearch class
                result = database_instance.emit_compute_dict(
                    uuid=uuid,
                    compute_map=compute,
                    index=index,
                    identifier=args.identifier,
                )
                mergedicts(result, main_json)
                mergedicts(result, index_json)
                compute_header = []
                for key in compute["filter"]:
                    compute_header.append(key.split(".keyword")[0])
                for bucket in compute["buckets"]:
                    compute_header.append(bucket.split(".keyword")[0])
                for extra_h in ["key", "uuid", "value"]:
                    compute_header.append(extra_h)
            if index_json:
                row_list = []
                if args.output == "csv":
                    row_list.append(compute_header)
                    flatten_and_discard(index_json, compute_header, row_list)
                    writer = csv.writer(output_file, delimiter=",")
                    list(map(writer.writerow, row_list))
                elif args.output not in ["json", "yaml"]:
                    flatten_and_discard(index_json, compute_header, row_list)
                    print(
                        tabulate(row_list, headers=compute_header, tablefmt="pretty"),
                        file=output_file,
                    )
    if args.output == "json":
        if metadata_json:
            output_file.write(json.dumps(metadata_json, indent=4))
        output_file.write(json.dumps(main_json, indent=4))
    elif args.output == "yaml":
        if metadata_json:
            output_file.write(yaml.dump(metadata_json, allow_unicode=True))
        output_file.write(yaml.dump(main_json, allow_unicode=True))
    logger.info("Script ends here")


def render():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    render()
