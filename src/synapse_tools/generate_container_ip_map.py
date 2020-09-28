#!/usr/bin/env python
import argparse
import os
import socket
import sys
from typing import Iterable
from typing import Mapping
from typing import Optional
from typing import Tuple

import requests
from paasta_tools.utils import atomic_file_write
from paasta_tools.utils import Client
from paasta_tools.utils import get_docker_client

HAPROXY_STATS_SOCKET = "/var/run/synapse/haproxy.sock"


def get_prev_file_contents(filename: str,) -> Mapping[str, str]:
    if os.path.isfile(filename):
        with open(filename, "r") as fp:
            prev_lines = [
                # Remove any empty strings, since split could leave empty
                # strings if there is any extra whitespace in the file
                list(filter(None, line.strip().split(" ")))
                for line in fp.readlines()
            ]
            return {line[0]: line[1] for line in prev_lines}
    return {}


def extract_taskid_and_ip_mesos(docker_client: Client,) -> Iterable[Tuple[str, str]]:
    service_ips_and_ids = []
    for container in docker_client.containers():
        networks = container["NetworkSettings"]["Networks"]
        labels = container["Labels"]

        # Only add containers that are using bridged networking and are
        # running as Mesos tasks
        if "bridge" in networks:
            ip_addr = networks["bridge"]["IPAddress"]
            if "MESOS_TASK_ID" in labels:
                task_id = labels["MESOS_TASK_ID"]
                service_ips_and_ids.append((ip_addr, task_id))
            # For compatibility with tron/batch services.
            elif "paasta_instance" in labels and "paasta_service" in labels:
                task_id = "{}.{}".format(
                    labels["paasta_service"], labels["paasta_instance"],
                )
                # For compatibility with MESOS_TASK_ID format.
                task_id = task_id.replace("_", "--")
                service_ips_and_ids.append((ip_addr, task_id))

    return service_ips_and_ids


def extract_taskid_and_ip_k8s() -> Iterable[Tuple[str, str]]:
    service_ips_and_ids = []

    node_info = requests.get("http://169.254.255.254:10255/pods/").json()

    for pod in node_info["items"]:
        labels = pod["metadata"]["labels"]
        service = labels.get("paasta.yelp.com/service")
        instance = labels.get("paasta.yelp.com/instance")
        status = pod["status"].get("phase")

        if (
            service is not None
            and instance is not None
            and status != "Failed"
            and "podIP" in pod["status"]
        ):
            task_id = f"{service}.{instance}".replace("_", "--")
            pod_ip = pod["status"]["podIP"]
            service_ips_and_ids.append((pod_ip, task_id))

    return service_ips_and_ids


def send_to_haproxy(command: str, timeout: int,) -> None:
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    s.connect(HAPROXY_STATS_SOCKET)
    s.send((command + "\n").encode())
    s.close()


def update_haproxy_mapping(
    ip_addr: str,
    task_id: str,
    prev_ip_to_task_id: Mapping[str, str],
    filename: str,
    timeout: int,
) -> None:
    # Check if this IP was in the file previously, if so, we want
    # to send an update to the HAProxy map instead of adding a new
    # entry (new additions to the map don't overwrite old entries
    # and instead create duplicate keys with different values).
    method: Optional[str]
    if ip_addr in prev_ip_to_task_id:
        if prev_ip_to_task_id[ip_addr] != task_id:
            method = "set"
        else:
            method = None
    else:
        # The IP was not added previously, add it as a new entry
        method = "add"

    if method:
        send_to_haproxy(f"{method} map {filename} {ip_addr} {task_id}", timeout)


def remove_stopped_container_entries(
    prev_ips: Iterable[str], curr_ips: Iterable[str], filename: str, timeout: int,
) -> None:
    for ip in prev_ips:
        if ip not in curr_ips:
            send_to_haproxy(f"del map {filename} {ip}", timeout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Script to dump a HAProxy map between container IPs and task IDs."
        ),
    )
    parser.add_argument(
        "--update-haproxy",
        "-U",
        action="store_true",
        help="Whether to update haproxy for map updates",
    )
    parser.add_argument(
        "--haproxy-timeout",
        "-T",
        type=int,
        default=1,
        help="Timeout for haproxy socket connections",
    )
    parser.add_argument(
        "--k8s",
        action="store_true",
        help="Use kubernetes api pod extraction rather than default mesos method",
    )
    parser.add_argument(
        "map_file",
        nargs="?",
        default="/var/run/synapse/maps/ip_to_service.map",
        help="Where to write the output map file",
    )
    args = parser.parse_args()

    if args.update_haproxy:
        prev_ip_to_task_id = get_prev_file_contents(args.map_file)

    new_lines = []
    ip_addrs = []
    if args.k8s:
        try:
            service_ips_and_ids = extract_taskid_and_ip_k8s()
        except Exception as e:
            print(e, file=sys.stderr)
            return
    else:
        service_ips_and_ids = extract_taskid_and_ip_mesos(get_docker_client())

    for ip_addr, task_id in service_ips_and_ids:
        ip_addrs.append(ip_addr)
        if args.update_haproxy:
            update_haproxy_mapping(
                ip_addr,
                task_id,
                prev_ip_to_task_id,
                args.map_file,
                args.haproxy_timeout,
            )
        new_lines.append(f"{ip_addr} {task_id}")

    if args.update_haproxy:
        remove_stopped_container_entries(
            prev_ip_to_task_id.keys(), ip_addrs, args.map_file, args.haproxy_timeout,
        )

    # Replace the file contents with the new map
    with atomic_file_write(args.map_file) as fp:
        fp.write("\n".join(new_lines))


if __name__ == "__main__":
    main()
