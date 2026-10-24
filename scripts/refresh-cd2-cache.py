#!/usr/bin/env python3
import argparse
import sys
import time
from collections import deque

import grpc
import yaml

from Symedia.apps.CloudDrive2 import CloudDrive_pb2 as pb
from Symedia.apps.CloudDrive2 import CloudDrive_pb2_grpc as pb_grpc


CONFIG_PATH = "/app/config/config.yaml"
CD2_ADDRESS = "127.0.0.1:19798"
MOUNT_PREFIX = "/CloudNAS/CloudDrive"


def cloud_path(media_dir):
    value = str(media_dir or "").rstrip("/")
    if not value.startswith(MOUNT_PREFIX + "/"):
        return ""
    return value[len(MOUNT_PREFIX):]


def list_children(stub, metadata, path, force):
    request = pb.ListSubFileRequest(
        path=path,
        forceRefresh=force,
        checkExpires=True,
    )
    call = stub.GetSubFiles(request, metadata=metadata, timeout=120)
    try:
        reply = next(call)
        return list(reply.subFiles)
    except StopIteration:
        return []
    finally:
        call.cancel()


def refresh_tree(stub, metadata, root, max_depth, max_dirs, delay):
    queue = deque([(root, 0)])
    seen = set()
    refreshed = 0
    failed = 0

    while queue and refreshed < max_dirs:
        path, depth = queue.popleft()
        if path in seen:
            continue
        seen.add(path)

        try:
            stub.ForceExpireDirCache(
                pb.FileRequest(path=path), metadata=metadata, timeout=30
            )
            children = list_children(stub, metadata, path, True)
            refreshed += 1
            print(f"OK depth={depth} children={len(children)} path={path}", flush=True)
        except grpc.RpcError as exc:
            failed += 1
            print(
                f"ERROR depth={depth} path={path} code={exc.code().name} detail={exc.details()}",
                file=sys.stderr,
                flush=True,
            )
            continue

        if depth < max_depth:
            for entry in children:
                if entry.isDirectory:
                    queue.append((entry.fullPathName, depth + 1))

        if delay:
            time.sleep(delay)

    if queue:
        print(f"LIMIT root={root} remaining={len(queue)} max_dirs={max_dirs}", flush=True)
    return refreshed, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("shallow", "deep"), nargs="?", default="shallow")
    args = parser.parse_args()

    with open(CONFIG_PATH, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    token = str(config.get("cloud_drive_config", {}).get("api_token") or "").strip()
    if not token:
        raise SystemExit("CloudDrive2 api_token is not configured")

    roots = []
    for task in config.get("sync_list", []):
        path = cloud_path(task.get("media_dir"))
        if path and path not in roots:
            roots.append(path)
    if not roots:
        raise SystemExit("No CloudDrive2 media roots found in sync_list")

    metadata = (("authorization", "Bearer " + token),)
    stub = pb_grpc.CloudDriveFileSrvStub(grpc.insecure_channel(CD2_ADDRESS))
    total_refreshed = 0
    total_failed = 0
    started = time.time()

    for root in roots:
        is_jav_root = "/jav/" in root.lower()
        if args.mode == "shallow":
            max_depth = 1 if is_jav_root else 2
            max_dirs, delay = 2500, 0.20
        else:
            max_depth = 3 if is_jav_root else 4
            max_dirs, delay = 25000, 0.25
        refreshed, failed = refresh_tree(
            stub, metadata, root, max_depth, max_dirs, delay
        )
        total_refreshed += refreshed
        total_failed += failed

    elapsed = round(time.time() - started, 1)
    print(
        f"DONE mode={args.mode} roots={len(roots)} refreshed={total_refreshed} "
        f"failed={total_failed} elapsed={elapsed}s",
        flush=True,
    )
    return 1 if total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
