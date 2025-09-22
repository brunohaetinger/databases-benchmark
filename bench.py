# bench.py
import argparse
import os
import csv
import time
from time import perf_counter_ns
import sqlite3
import psycopg2
import redis
from concurrent.futures import ThreadPoolExecutor
import random
import string
import base64

# ---------- helpers ----------


def now_ms(): return perf_counter_ns() / 1_000_000.0


def gen_payload(size):
    return os.urandom(size)


def write_csv(path, rows, header):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def stats_from_list(xs):
    import numpy as np
    arr = np.array(xs)
    return {
        "count": len(xs),
        "mean_ms": float(arr.mean()),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "std_ms": float(arr.std())
    }

# ---------- DB wrappers ----------


class SqliteBench:
    def __init__(self, path="test_sqlite.db"):
        self.path = path

    def connect(self):
        return sqlite3.connect(self.path, timeout=30, check_same_thread=False)

    def setup(self):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v BLOB)")
            conn.commit()

    def write_one(self, conn, key, payload, commit=True):
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO kv (k,v) VALUES (?,?)",
                    (key, payload))
        if commit:
            conn.commit()

    def read_one(self, conn, key):
        cur = conn.cursor()
        cur.execute("SELECT v FROM kv WHERE k=?", (key,))
        return cur.fetchone()


class PostgresBench:
    def __init__(self, host="localhost", port=5432, user="postgres", password="postgres", dbname="postgres"):
        self.dsn = dict(host=host, port=port, user=user,
                        password=password, dbname=dbname)

    def connect(self):
        return psycopg2.connect(**self.dsn)

    def setup(self):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v BYTEA)")
        conn.commit()
        conn.close()

    def write_one(self, conn, key, payload, commit=True):
        cur = conn.cursor()
        cur.execute("INSERT INTO kv (k,v) VALUES (%s,%s) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v",
                    (key, psycopg2.Binary(payload)))
        if commit:
            conn.commit()

    def read_one(self, conn, key):
        cur = conn.cursor()
        cur.execute("SELECT v FROM kv WHERE k=%s", (key,))
        return cur.fetchone()


class RedisBench:
    def __init__(self, host="localhost", port=6379):
        self.pool = redis.ConnectionPool(
            host=host, port=port, decode_responses=False)

    def connect(self):
        return redis.Redis(connection_pool=self.pool)

    def setup(self):
        pass

    def write_one(self, client, key, payload, commit=True):
        client.set(key, payload)

    def read_one(self, client, key):
        return client.get(key)

# ---------- Measurement functions ----------


def run_sequential(bench, dbname, op_count, payload_size, op_type, csv_out, warmup=10):
    # warmup
    for i in range(warmup):
        conn = bench.connect()
        k = f"warmup_{i}"
        if op_type in ("write", "both"):
            bench.write_one(conn, k, gen_payload(payload_size), commit=True)
        if op_type in ("read", "both"):
            bench.read_one(conn, k)
        try:
            conn.close()
        except:
            pass

    rows = []
    latencies = []
    for i in range(op_count):
        key = f"{dbname}_k_{payload_size}_{i}"
        payload = gen_payload(payload_size)
        conn = bench.connect()
        if op_type in ("write", "both"):
            t0 = now_ms()
            bench.write_one(conn, key, payload, commit=True)
            t1 = now_ms()
            latencies.append(t1-t0)
            rows.append([dbname, "write", payload_size, i, t1-t0, key])
        if op_type in ("read", "both"):
            # ensure exists (if read-only test, previously inserted)
            # For simplicity, insert then read in same iteration if needed:
            if op_type == "read":
                bench.write_one(conn, key, payload, commit=True)
            t0 = now_ms()
            _ = bench.read_one(conn, key)
            t1 = now_ms()
            latencies.append(t1-t0)
            rows.append([dbname, "read", payload_size, i, t1-t0, key])
        try:
            conn.close()
        except:
            pass

    header = ["db", "op", "payload_size", "index", "latency_ms", "key"]
    write_csv(csv_out, rows, header)
    return latencies


def run_concurrent(bench, dbname, total_ops, payload_size, threads, op_type, csv_out):
    # split ops per worker
    ops_per = total_ops // threads
    rows = []
    latencies_all = []

    def worker(thread_id):
        conn = bench.connect()
        lats = []
        for i in range(ops_per):
            idx = thread_id*ops_per + i
            key = f"{dbname}_t{thread_id}_k_{payload_size}_{idx}"
            payload = gen_payload(payload_size)
            if op_type in ("write", "both"):
                t0 = now_ms()
                bench.write_one(conn, key, payload, commit=True)
                t1 = now_ms()
                rows.append([dbname, "write", payload_size,
                            idx, t1-t0, key, thread_id])
                lats.append(t1-t0)
            if op_type in ("read", "both"):
                # ensure exists quickly
                bench.write_one(conn, key, payload, commit=True)
                t0 = now_ms()
                _ = bench.read_one(conn, key)
                t1 = now_ms()
                rows.append([dbname, "read", payload_size,
                            idx, t1-t0, key, thread_id])
                lats.append(t1-t0)
        try:
            conn.close()
        except:
            pass
        return lats

    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = [ex.submit(worker, t) for t in range(threads)]
        for f in futures:
            latencies_all.extend(f.result())

    header = ["db", "op", "payload_size",
              "index", "latency_ms", "key", "thread"]
    write_csv(csv_out, rows, header)
    return latencies_all

# ---------- CLI ----------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", choices=["sqlite",
                   "postgres", "redis", "all"], default="all")
    p.add_argument("--ops", type=int, default=2000)
    p.add_argument("--payload", type=int, default=256)
    p.add_argument(
        "--mode", choices=["write", "read", "both"], default="write")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--out", default="results/result.csv")
    args = p.parse_args()

    targets = []
    if args.db in ("sqlite", "all"):
        targets.append(("sqlite", SqliteBench()))
    if args.db in ("postgres", "all"):
        targets.append(("postgres", PostgresBench()))
    if args.db in ("redis", "all"):
        targets.append(("redis", RedisBench()))

    for name, bench in targets:
        print("Setting up", name)
        bench.setup()

    for name, bench in targets:
        print("Running", name)
        if args.concurrency == 1:
            lat = run_sequential(bench, name, args.ops, args.payload,
                                 args.mode, f"results/{name}_seq_{args.payload}.csv")
        else:
            lat = run_concurrent(bench, name, args.ops, args.payload, args.concurrency, args.mode,
                                 f"results/{name}_concurrency_{args.payload}_th{args.concurrency}.csv")
        s = stats_from_list(lat)
        print(f"{name} stats for payload {args.payload}: {s}")


if __name__ == "__main__":
    main()
