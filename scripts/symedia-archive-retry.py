#!/usr/bin/env python3
"""Retry failed Symedia CD2 moves through CloudDrive2's no-overwrite API.

Run this inside the Symedia container, where grpcio, PyYAML, and generated
clouddrive_pb2 modules are available. Dry-run is the default.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import time


ROOT = "/CloudNAS/CloudDrive"
FAIL_SOURCE_ROOT = ROOT + "/GoogleDrive/zero/media/fail/"
DOWNLOAD_SOURCE_ROOT = ROOT + "/GoogleDrive/zero/media/downloads_mp/"
SOURCE_ROOTS = (FAIL_SOURCE_ROOT, DOWNLOAD_SOURCE_ROOT)
DEST_ROOT = ROOT + "/GoogleDrive/zero/media/symedia_gd/"
DELAYS = (0, 30 * 60, 2 * 60 * 60)
FIELDS = "id, src, dest, dest_dir, mode, rule_id, type, status, errmsg, date, file_size"


def now():
    return time.time()


def connect_state(path):
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS retries (
        history_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', last_error TEXT NOT NULL DEFAULT ''
    )""")
    db.commit()
    return db


def history_rows(path):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(
            f"SELECT {FIELDS} FROM transferhistory WHERE status=0 AND mode='cd2_move'"
        )]
    finally:
        db.close()


def mark_history_success(path, history_id):
    """Reconcile a false failure after the destination was verified on disk."""
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute("PRAGMA busy_timeout=30000")
        changed = db.execute(
            "UPDATE transferhistory SET status=1, errmsg='' WHERE id=? AND status=0",
            (history_id,),
        ).rowcount
        db.commit()
        return bool(changed)
    finally:
        db.close()


def classify(row):
    source, target = row["src"], row["dest"]
    if not source or not target or not row["rule_id"]:
        return "invalid"
    if not target.startswith(DEST_ROOT):
        return "out_of_scope"
    source_exists = os.path.isfile(source)
    target_exists = os.path.lexists(target)
    if not source_exists and target_exists:
        expected_size = row.get("file_size")
        if expected_size and (not os.path.isfile(target) or os.stat(target).st_size != int(expected_size)):
            return "size_mismatch"
        return "already_moved"
    if source_exists and target_exists:
        expected_size = row.get("file_size")
        if (
            expected_size
            and os.path.isfile(source)
            and os.path.isfile(target)
            and os.stat(source).st_size == int(expected_size)
            and os.stat(target).st_size == int(expected_size)
        ):
            return "duplicate_source"
        return "both_exist"
    if not any(source.startswith(root) for root in SOURCE_ROOTS):
        return "out_of_scope"
    if not source_exists:
        return "neither_exists"
    renaming = os.path.basename(source) != os.path.basename(target)
    if renaming and os.path.lexists(os.path.join(os.path.dirname(target), os.path.basename(source))):
        return "staging_conflict"
    if source_exists:
        if source.startswith(DOWNLOAD_SOURCE_ROOT):
            try:
                age = now() - time.mktime(datetime.fromisoformat(row["date"]).timetuple())
            except (KeyError, TypeError, ValueError, OverflowError):
                return "invalid"
            if age < 120:
                return "waiting_for_symedia"
        return "rename_retryable" if renaming else "retryable"


def fingerprint(row):
    return json.dumps([row["src"], row["dest"], row["date"]], ensure_ascii=False)


def cd2_move(row, config_path):
    import grpc
    import yaml
    try:
        import clouddrive_pb2 as pb
        import clouddrive_pb2_grpc as pbg
    except ImportError:
        from Symedia.apps.CloudDrive2 import CloudDrive_pb2 as pb
        from Symedia.apps.CloudDrive2 import CloudDrive_pb2_grpc as pbg

    if classify(row) not in ("retryable", "rename_retryable"):
        raise RuntimeError("Preflight changed; transfer not submitted")
    source, target = row["src"], row["dest"]
    size_before = os.stat(source).st_size
    parent = os.path.dirname(target)
    staging = os.path.join(parent, os.path.basename(source))
    renaming = staging != target
    os.makedirs(parent, exist_ok=True)
    if not os.path.isdir(parent) or os.path.lexists(target) or (renaming and os.path.lexists(staging)):
        raise RuntimeError("Target directory invalid or target already exists")
    config = yaml.safe_load(open(config_path, encoding="utf-8"))["cloud_drive_config"]
    token = config.get("api_token")
    if not token:
        raise RuntimeError("CloudDrive2 API token is missing")
    channel = grpc.insecure_channel(f"{config['host']}:{config['port']}")
    stub = pbg.CloudDriveFileSrvStub(channel)
    metadata = (("authorization", "Bearer " + token),)
    cloud_source = source[len(ROOT):]
    cloud_target_parent = parent[len(ROOT):]
    try:
        result = stub.MoveFile(
            pb.MoveFileRequest(
                theFilePaths=[cloud_source],
                destPath=cloud_target_parent,
                conflictPolicy=pb.MoveFileRequest.Skip,
            ),
            metadata=metadata,
            timeout=45,
        )
        if not result.success:
            raise RuntimeError(result.errorMessage or "CloudDrive2 MoveFile returned false")
        if renaming:
            for _ in range(10):
                if not os.path.lexists(source) and os.path.isfile(staging):
                    break
                time.sleep(1)
            if os.path.lexists(source) or not os.path.isfile(staging):
                raise RuntimeError("Staging move not verified")
            if os.stat(staging).st_size != size_before or os.path.lexists(target):
                raise RuntimeError("Staging size mismatch or destination conflict")
            rename_result = stub.RenameFile(
                pb.RenameFileRequest(
                    theFilePath=staging[len(ROOT):], newName=os.path.basename(target)
                ),
                metadata=metadata,
                timeout=45,
            )
            if not rename_result.success:
                raise RuntimeError(rename_result.errorMessage or "CloudDrive2 RenameFile returned false")
    finally:
        channel.close()
    for _ in range(10):
        if not os.path.lexists(source) and os.path.isfile(target):
            if os.stat(target).st_size == size_before:
                return
            raise RuntimeError("Destination size differs from source")
        time.sleep(1)
    raise RuntimeError("Move outcome not verified; next run will inspect both paths")


def run_once(args):
    state = connect_state(args.state)
    rows = sorted(history_rows(args.history), key=lambda row: row["date"] or "", reverse=True)
    counts = {}
    submitted = 0
    for row in rows:
        kind = classify(row)
        counts[kind] = counts.get(kind, 0) + 1
        key = fingerprint(row)
        stored = state.execute(
            "SELECT fingerprint, attempts, next_at, state FROM retries WHERE history_id=?",
            (row["id"],),
        ).fetchone()
        if stored is None or stored[0] != key:
            state.execute(
                "INSERT OR REPLACE INTO retries VALUES (?, ?, 0, ?, 'pending', '')",
                (row["id"], key, now()),
            )
            state.commit()
            stored = (key, 0, now(), "pending")
        _, attempts, due, status = stored
        if kind in ("already_moved", "duplicate_source"):
            try:
                mark_history_success(args.history, row["id"])
            except sqlite3.Error as exc:
                print(f"RECONCILE_FAILED id={row['id']} error={exc!r}")
                continue
            state.execute(
                "UPDATE retries SET state='reconciled', last_error=? WHERE history_id=?",
                (
                    "Destination verified with matching size; source duplicate retained"
                    if kind == "duplicate_source"
                    else "Destination verified with matching size; Symedia false failure reconciled",
                    row["id"],
                ),
            )
            state.commit()
            print(f"RECONCILED id={row['id']} destination verified kind={kind}")
            continue
        if kind not in ("retryable", "rename_retryable") or status in ("done", "held") or attempts >= 3 or now() < due:
            continue
        if args.only_id and row["id"] != args.only_id:
            continue
        if submitted >= args.max_per_run:
            continue
        if not args.execute:
            print(f"WOULD_RETRY id={row['id']} attempt={attempts + 1} src={row['src']!r}")
            submitted += 1
            continue
        error = ""
        try:
            cd2_move(row, args.config)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:250]
        attempts += 1
        outcome = classify(row)
        if outcome in ("already_moved", "duplicate_source"):
            try:
                mark_history_success(args.history, row["id"])
            except sqlite3.Error as exc:
                error = f"History reconcile failed: {exc}"[:250]
                status = "pending"
            else:
                status = "done"
        elif outcome not in ("retryable", "rename_retryable"):
            status = "held"
        elif attempts >= 3:
            status = "exhausted"
        else:
            status = "pending"
        due = now() + (DELAYS[attempts] if attempts < 3 else 0)
        state.execute(
            "UPDATE retries SET attempts=?, next_at=?, state=?, last_error=? WHERE history_id=?",
            (attempts, due, status, error, row["id"]),
        )
        state.commit()
        submitted += 1
        print(f"RESULT id={row['id']} attempt={attempts} state={status} error={error!r}")
    print("SUMMARY " + json.dumps(counts, ensure_ascii=False, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default="/app/config/symedia.db")
    parser.add_argument("--state", default="/app/config/archive_retry/state.db")
    parser.add_argument("--config", default="/app/config/config.yaml")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-per-run", type=int, default=1)
    parser.add_argument("--only-id", type=int)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    while True:
        run_once(args)
        if args.once:
            break
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
