# DB Benchmarks: SQLite vs Postgres vs Redis

This project is a **Proof of Concept (PoC)** to compare read and write performance between three popular databases:

- [SQLite](https://sqlite.org) — embedded, file-based relational DB.
- [Postgres](https://www.postgresql.org/) — production-grade relational DB server.
- [Redis](https://redis.io/) — in-memory key–value store.

The goal is to measure **latency** and **throughput** for simple key/value operations under different conditions:
- Sequential writes and reads
- Concurrent access with multiple threads
- Different payload sizes

---

## 🚀 Features
- Spin up Postgres and Redis easily with **Docker Compose**
- Benchmark script in **Python** (`bench.py`)
- Supports:
  - SQLite (local file)
  - Postgres (via psycopg2)
  - Redis (via redis-py)
- Measures latency per operation (ms)
- Saves raw results to CSV files for later analysis
- Reports aggregate stats (mean, median, p95, p99, std)
- Optional multi-threaded benchmarks

---

## 📦 Project Structure


```
db-bench/
├─ docker-compose.yml # Postgres + Redis containers
├─ requirements.txt # Python dependencies
├─ bench.py # Main benchmarking script
├─ utils.py # (optional) helper functions
├─ results/ # Benchmark output CSVs
└─ README.md # This file
```
```
```


---

## ⚙️ Setup

### 1. Start services (Postgres & Redis)

```bash
docker-compose up -d
```

### 2. Create virtual environment & install dependencies

```
```
python -m venv .venv        # or `uv venv`
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows PowerShell

pip install -r requirements.txt
```

---

▶️ Usage

Run the benchmark script with various options.

Basic: write test, 2000 operations, 256-byte payload

> python bench.py --db all --ops 2000 --payload 256 --mode write

Read test only

> python bench.py --db all --ops 2000 --payload 256 --mode read

Concurrent test with 4 threads

> python bench.py --db all --ops 4000 --payload 256 --mode write --concurrency 4


Options

```
--db [sqlite|postgres|redis|all]   Which DB(s) to test (default=all)
--ops N                            Number of operations (default=2000)
--payload BYTES                    Payload size in bytes (default=256)
--mode [write|read|both]           Operation type (default=write)
--concurrency N                    Number of threads (default=1)
--out PATH                         Output CSV path (default=results/result.csv)

```
```
```
