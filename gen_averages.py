import argparse
import sys
import json
import yaml
import elasticsearch
import uuid
import time

from collections import defaultdict, deque
import itertools
from copy import deepcopy
import datetime
import pytz

def _parse_data(inputdict, my_uuid):
    new_dict = {}
    total = 0
    for key in inputdict.keys():
        if type(inputdict[key]) == dict:
            new_dict[key] =  _parse_data(inputdict[key], my_uuid)
        else:
            total += inputdict[key]
    if total != 0:        
        new_dict = { my_uuid: total/len(inputdict.keys()) }
    return new_dict

def _upload_to_es(my_dict, my_uuid, es_server, es_port, index, es_ssl):
    _es_connection_string = str(es_server) + ':' + str(es_port)
    if es_ssl == "true":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        es = elasticsearch.Elasticsearch([_es_connection_string], send_get_body_as='POST',
                                         ssl_context=ssl_ctx, use_ssl=True)
    else:
        es = elasticsearch.Elasticsearch([_es_connection_string], send_get_body_as='POST')

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    data = {"uuid": my_uuid, "timestamp": timestamp}
    data.update(my_dict)
    try:
        es.index(index=index, body=data)
    except Exception as err:
        print("Uploading to elasticsearch failed")
        print(err)
        exit(1)

def populate_result_dict(path, k, v, result_to_push):
    result_dict = result_to_push[tuple(path[i] for i in range(0, 8, 2))]
    if "rr" in path and "avg(norm_ltcy)" in path:
        result_dict["test_type"] = "rr"
        result_dict["norm_ltcy"] = v
    elif "stream" in path and "avg(norm_byte)" in path:
        result_dict["test_type"] = "stream"
        result_dict["norm_byte"] = v
    result_dict["protocol"] = path[2]
    result_dict["message_size"] = int(path[4])
    result_dict["num_threads"] = int(path[6])

def index_result(index, server, port, payload):
    _es_connection_string = str(server) + ":" + str(port)
    es = elasticsearch.Elasticsearch([_es_connection_string], send_get_body_as="POST")
    for result in payload.values():
        res = es.index(index=index, body=result)

def main():
    server = "search-cloud-perf-lqrf3jjtaqo7727m7ynd2xyt4y.us-west-2.es.amazonaws.com"
    port = 80
    local = pytz.timezone ("Etc/UTC")
    local_dt = local.localize(datetime.datetime.now(), is_dst=None)
    utc_dt = local_dt.astimezone(pytz.utc)
    parser = argparse.ArgumentParser(description="Gen averages of data given and upload to ES",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    reference_dict = {
        "workload": "uperf",
        "uuid": "xx-yy-zz",
        "user": "",
        "cluster_name": "",
        "hostnetwork": "",
        "iteration": 0,
        "remote_ip": "",
        "client_ips": "",
        "uperf_ts": utc_dt.isoformat(),
        "test_type": "",
        "protocol": "",
        "service_ip": "",
        "message_size": 0,
        "num_threads": 0,
        "duration": 0,
        "bytes": 0,
        "norm_byte": 0.0,
        "ops": 0,
        "norm_ops": 1,
        "norm_ltcy": 0.0,
        "kind": "",
        "client_node": "",
        "server_node": ""
      }

    parser.add_argument(
        '-f', '--file',
        required=True,
        help='Imput json file to iterate over')
    parser.add_argument(
        '-u', '--uuid',
        help='UUID to use for uploading to ES')
    parser.add_argument(
        '-s', '--server',
        help='Provide elastic server information')
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=9200,
        help='Provide elastic port information')
    parser.add_argument(
        '--sslskipverify',
        help='If es is setup with ssl, but can disable tls cert verification',
        default=False)
    parser.add_argument(
        '-i', '--index',
        help='What index to upload to ES',
        default=False)
    parser.add_argument(
        '-o', '--output',
        choices=['yaml', 'json'],
        default='yaml',
        help='What format to print output to stdout')
    parser.add_argument(
        '--output-file',
        help='Where to print the output. Mutually exclusive with loading to elasticsearch.')
    
    args = parser.parse_args()
    
    my_uuid = args.uuid
    if my_uuid is None:
        my_uuid = str(uuid.uuid4())

    try:
        inputdict = json.load(open(args.file))
    except:
        print("Could not load input as json. Trying yaml.")
        try_yaml = True
    else:
        print("Input loaded from json.")
        try_yaml = False

    if try_yaml:
        try:
            inputdict = yaml.safe_load(open(args.file))
        except Exception as err:
            print("Could not open input file as json or yaml. Exiting.")
            print(err)
            exit(1)
        else:
            print("Input loaded from yaml.")

    print("Generating averages for UUID",my_uuid)
    new_dict = _parse_data(inputdict, my_uuid)

    # If not ES info is given dump the new dictionary to stdout or output-file if given
    if args.server is None or args.port is None or args.index is None:
        print("No elasticsearch information provided.")
        if args.output_file is None:
            print("No output file given. Printing to STDOUT.")
            if args.output == "json":
                print(json.dumps(new_dict, indent=4))
            else:
                print(yaml.dump(new_dict))
        else:
            try:
                file_out = open(args.output_file, 'w')
            except Exception as err:
                print("Failed to open file for printing")
                exit(1)
            else:
                print("Printing to file",args.output_file)

            if args.output == "json":
                json.dumps(new_dict,file_out, indent=4)
            else:
                yaml.dump(new_dict,file_out)

            file_out.close()
    else:
        print("Attempting to upload to elasticsearch index",args.index)
        _upload_to_es(new_dict, my_uuid, args.server, args.port, args.index, args.sslskipverify)


    result_to_push = defaultdict(lambda: deepcopy(reference_dict))
    with open("output.yaml", "r") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    data = data["test_type.keyword"]
    queue = deque()
    queue.extend([([k], v) for k, v in data.items()])
    while queue:
        path, current = queue.popleft()
        for k, v in current.items():
            if type(v) == float:
                if ("rr" in path and "avg(norm_ltcy)" in path) or (
                    "stream" in path and "avg(norm_byte)" in path
                ):
                    populate_result_dict(path, k, v, result_to_push)
            else:
                queue.append((path + [str(k)], v))

    index_result("ripsaw-uperf-results", server, port, result_to_push)

if __name__ == '__main__':
    sys.exit(main())
