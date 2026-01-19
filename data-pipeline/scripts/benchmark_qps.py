#!/usr/bin/env python3
"""
Benchmark script to test Supabase backend QPS limits.

Tests various database operations to identify performance bottlenecks:
- Simple SELECT queries (REST API)
- Simple SELECT queries (Direct PostgreSQL)
- Bulk SELECT queries
- INSERT operations
- Concurrent connections

Usage:
    python scripts/benchmark_qps.py
    python scripts/benchmark_qps.py --output exports/benchmark_results.md
"""

import argparse
import os
import sys
import time
import statistics
from pathlib import Path
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple
import uuid

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_supabase_client, get_db_connection, close_connections
import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    total_operations: int
    successful: int
    failed: int
    total_time_sec: float
    qps: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    errors: List[str]


def percentile(data: List[float], p: float) -> float:
    """Calculate percentile of a sorted list."""
    if not data:
        return 0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f]) if c != f else sorted_data[f]


def run_benchmark(
    name: str,
    operation_func,
    num_operations: int,
    concurrency: int = 1,
    setup_func=None,
    teardown_func=None
) -> BenchmarkResult:
    """
    Run a benchmark with the given operation function.

    Args:
        name: Name of the benchmark
        operation_func: Function to execute (should return latency in seconds or None on failure)
        num_operations: Number of operations to run
        concurrency: Number of concurrent workers
        setup_func: Optional setup function
        teardown_func: Optional teardown function
    """
    if setup_func:
        setup_func()

    latencies = []
    errors = []

    start_time = time.perf_counter()

    if concurrency == 1:
        # Sequential execution
        for i in range(num_operations):
            try:
                latency = operation_func(i)
                if latency is not None:
                    latencies.append(latency)
                else:
                    errors.append(f"Operation {i} returned None")
            except Exception as e:
                errors.append(str(e)[:100])
    else:
        # Concurrent execution
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(operation_func, i): i for i in range(num_operations)}
            for future in as_completed(futures):
                try:
                    latency = future.result(timeout=30)
                    if latency is not None:
                        latencies.append(latency)
                    else:
                        errors.append(f"Operation returned None")
                except Exception as e:
                    errors.append(str(e)[:100])

    total_time = time.perf_counter() - start_time

    if teardown_func:
        teardown_func()

    successful = len(latencies)
    failed = len(errors)

    # Calculate statistics
    if latencies:
        avg_latency = statistics.mean(latencies) * 1000
        p50 = percentile(latencies, 50) * 1000
        p95 = percentile(latencies, 95) * 1000
        p99 = percentile(latencies, 99) * 1000
        min_lat = min(latencies) * 1000
        max_lat = max(latencies) * 1000
    else:
        avg_latency = p50 = p95 = p99 = min_lat = max_lat = 0

    qps = successful / total_time if total_time > 0 else 0

    return BenchmarkResult(
        name=name,
        total_operations=num_operations,
        successful=successful,
        failed=failed,
        total_time_sec=total_time,
        qps=qps,
        avg_latency_ms=avg_latency,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        min_latency_ms=min_lat,
        max_latency_ms=max_lat,
        errors=errors[:10]  # Keep only first 10 errors
    )


# ============== Benchmark Operations ==============

def create_rest_select_operation():
    """Create a REST API select operation."""
    client = get_supabase_client()

    def operation(i):
        start = time.perf_counter()
        client.table('processed_prices').select('id').limit(1).execute()
        return time.perf_counter() - start

    return operation


def create_rest_select_bulk_operation(limit=100):
    """Create a REST API bulk select operation."""
    client = get_supabase_client()

    def operation(i):
        start = time.perf_counter()
        client.table('processed_prices').select('*').limit(limit).execute()
        return time.perf_counter() - start

    return operation


def create_postgres_select_operation():
    """Create a direct PostgreSQL select operation (new connection each time)."""
    db_url = os.getenv("SUPABASE_DB_URL")

    def operation(i):
        start = time.perf_counter()
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM processed_prices LIMIT 1")
            cursor.fetchone()
            cursor.close()
        finally:
            conn.close()
        return time.perf_counter() - start

    return operation


def create_postgres_select_pooled_operation():
    """Create a direct PostgreSQL select operation (connection reuse)."""
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)

    def operation(i):
        start = time.perf_counter()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM processed_prices LIMIT 1")
        cursor.fetchone()
        cursor.close()
        return time.perf_counter() - start

    def teardown():
        conn.close()

    return operation, teardown


def create_postgres_count_operation():
    """Create a PostgreSQL count operation."""
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)

    def operation(i):
        start = time.perf_counter()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_prices")
        cursor.fetchone()
        cursor.close()
        return time.perf_counter() - start

    def teardown():
        conn.close()

    return operation, teardown


def create_rest_insert_operation():
    """Create a REST API insert operation (to a test table or with rollback)."""
    client = get_supabase_client()

    def operation(i):
        start = time.perf_counter()
        # Insert into processing_errors as a test (we can clean up later)
        test_id = str(uuid.uuid4())
        client.table('processing_errors').insert({
            'id': test_id,
            'error_type': 'benchmark_test',
            'error_message': f'Benchmark test {i}',
            'source_path': 'benchmark/test',
            'source_type': 'benchmark'
        }).execute()
        # Immediately delete to clean up
        client.table('processing_errors').delete().eq('id', test_id).execute()
        return time.perf_counter() - start

    return operation


def create_postgres_insert_operation():
    """Create a PostgreSQL insert operation with rollback."""
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    conn.autocommit = False

    def operation(i):
        start = time.perf_counter()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO processing_errors (error_type, error_message, source_path, source_type)
            VALUES ('benchmark_test', 'Benchmark test', 'benchmark/test', 'benchmark')
        """)
        conn.rollback()  # Don't actually insert
        cursor.close()
        return time.perf_counter() - start

    def teardown():
        conn.close()

    return operation, teardown


def create_concurrent_connection_operation():
    """Create an operation that tests concurrent connection handling."""
    db_url = os.getenv("SUPABASE_DB_URL")

    def operation(i):
        start = time.perf_counter()
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            time.sleep(0.1)  # Hold connection briefly
        finally:
            conn.close()
        return time.perf_counter() - start

    return operation


def run_all_benchmarks() -> List[BenchmarkResult]:
    """Run all benchmark tests."""
    results = []

    print("=" * 70)
    print("AgroAmigo Supabase Backend QPS Benchmark")
    print("=" * 70)
    print(f"Started: {datetime.now().isoformat()}")
    print()

    # Test 1: REST API Simple SELECT (Sequential)
    print("Running: REST API Simple SELECT (Sequential)...")
    results.append(run_benchmark(
        "REST API SELECT (sequential)",
        create_rest_select_operation(),
        num_operations=50,
        concurrency=1
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 2: REST API Simple SELECT (Concurrent)
    for concurrency in [5, 10, 20]:
        print(f"Running: REST API Simple SELECT (concurrency={concurrency})...")
        results.append(run_benchmark(
            f"REST API SELECT (c={concurrency})",
            create_rest_select_operation(),
            num_operations=100,
            concurrency=concurrency
        ))
        print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms, Failed: {results[-1].failed}")

    # Test 3: REST API Bulk SELECT
    print("Running: REST API Bulk SELECT (100 rows)...")
    results.append(run_benchmark(
        "REST API SELECT 100 rows",
        create_rest_select_bulk_operation(100),
        num_operations=30,
        concurrency=1
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 4: PostgreSQL Direct (New Connection Each Time)
    print("Running: PostgreSQL SELECT (new connection each)...")
    results.append(run_benchmark(
        "PostgreSQL SELECT (new conn)",
        create_postgres_select_operation(),
        num_operations=30,
        concurrency=1
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 5: PostgreSQL Direct (Connection Reuse)
    print("Running: PostgreSQL SELECT (pooled connection)...")
    op, teardown = create_postgres_select_pooled_operation()
    results.append(run_benchmark(
        "PostgreSQL SELECT (pooled)",
        op,
        num_operations=100,
        concurrency=1,
        teardown_func=teardown
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 6: PostgreSQL COUNT (heavier query)
    print("Running: PostgreSQL COUNT (full table scan)...")
    op, teardown = create_postgres_count_operation()
    results.append(run_benchmark(
        "PostgreSQL COUNT(*)",
        op,
        num_operations=20,
        concurrency=1,
        teardown_func=teardown
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 7: REST API INSERT + DELETE
    print("Running: REST API INSERT + DELETE...")
    results.append(run_benchmark(
        "REST API INSERT+DELETE",
        create_rest_insert_operation(),
        num_operations=20,
        concurrency=1
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 8: PostgreSQL INSERT (with rollback)
    print("Running: PostgreSQL INSERT (rollback)...")
    op, teardown = create_postgres_insert_operation()
    results.append(run_benchmark(
        "PostgreSQL INSERT (rollback)",
        op,
        num_operations=100,
        concurrency=1,
        teardown_func=teardown
    ))
    print(f"  QPS: {results[-1].qps:.1f}, Avg Latency: {results[-1].avg_latency_ms:.1f}ms")

    # Test 9: Concurrent Connections Stress Test
    for concurrency in [10, 20, 30, 40]:
        print(f"Running: Concurrent Connections (c={concurrency})...")
        results.append(run_benchmark(
            f"Concurrent Connections (c={concurrency})",
            create_concurrent_connection_operation(),
            num_operations=concurrency * 2,
            concurrency=concurrency
        ))
        print(f"  QPS: {results[-1].qps:.1f}, Failed: {results[-1].failed}")
        if results[-1].failed > results[-1].total_operations * 0.1:
            print(f"  ⚠️  High failure rate - likely hitting connection limit")
            break

    print()
    print("=" * 70)
    print("Benchmark Complete")
    print("=" * 70)

    return results


def generate_report(results: List[BenchmarkResult]) -> str:
    """Generate a markdown report from benchmark results."""
    lines = [
        "# Supabase Backend Performance Benchmark",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Instance:** Micro (1 GB RAM, 2-core ARM CPU)",
        "",
        "## Summary",
        "",
        "This benchmark tests the QPS (queries per second) capabilities of the Supabase backend",
        "to identify performance bottlenecks for the AgroAmigo data pipeline.",
        "",
        "## Results",
        "",
        "| Test | Operations | Success | Failed | QPS | Avg (ms) | P95 (ms) | P99 (ms) |",
        "|------|------------|---------|--------|-----|----------|----------|----------|",
    ]

    for r in results:
        lines.append(
            f"| {r.name} | {r.total_operations} | {r.successful} | {r.failed} | "
            f"{r.qps:.1f} | {r.avg_latency_ms:.1f} | {r.p95_latency_ms:.1f} | {r.p99_latency_ms:.1f} |"
        )

    lines.extend([
        "",
        "## Detailed Analysis",
        "",
        "### Read Operations",
        "",
    ])

    # Analyze read operations
    rest_reads = [r for r in results if "REST API SELECT" in r.name and "INSERT" not in r.name]
    if rest_reads:
        best_rest = max(rest_reads, key=lambda r: r.qps)
        lines.append(f"- **Best REST API read throughput:** {best_rest.qps:.1f} QPS ({best_rest.name})")

    pg_reads = [r for r in results if "PostgreSQL SELECT" in r.name]
    if pg_reads:
        best_pg = max(pg_reads, key=lambda r: r.qps)
        lines.append(f"- **Best PostgreSQL read throughput:** {best_pg.qps:.1f} QPS ({best_pg.name})")

    lines.extend([
        "",
        "### Write Operations",
        "",
    ])

    writes = [r for r in results if "INSERT" in r.name]
    if writes:
        for w in writes:
            lines.append(f"- **{w.name}:** {w.qps:.1f} QPS, {w.avg_latency_ms:.1f}ms avg latency")

    lines.extend([
        "",
        "### Connection Limits",
        "",
    ])

    conn_tests = [r for r in results if "Concurrent Connections" in r.name]
    if conn_tests:
        max_successful = max(conn_tests, key=lambda r: r.successful if r.failed == 0 else 0)
        failing = [r for r in conn_tests if r.failed > 0]

        if failing:
            first_fail = min(failing, key=lambda r: int(r.name.split("=")[1].rstrip(")")))
            lines.append(f"- **Connection failures started at:** {first_fail.name}")
        else:
            lines.append(f"- **All connection tests passed** (tested up to {conn_tests[-1].name})")

    lines.extend([
        "",
        "## Bottleneck Analysis",
        "",
    ])

    # Determine primary bottleneck
    bottlenecks = []

    # Check for connection limits
    conn_failures = [r for r in conn_tests if r.failed > r.total_operations * 0.1]
    if conn_failures:
        bottlenecks.append("**Connection Pool**: Connection failures observed at higher concurrency levels.")

    # Check REST vs PostgreSQL
    if rest_reads and pg_reads:
        best_rest_qps = max(r.qps for r in rest_reads)
        best_pg_qps = max(r.qps for r in pg_reads)
        if best_pg_qps > best_rest_qps * 2:
            bottlenecks.append("**REST API Overhead**: Direct PostgreSQL is significantly faster than REST API.")

    # Check write performance
    if writes:
        avg_write_qps = statistics.mean(w.qps for w in writes)
        if rest_reads:
            avg_read_qps = statistics.mean(r.qps for r in rest_reads)
            if avg_write_qps < avg_read_qps * 0.3:
                bottlenecks.append("**Write Performance**: Writes are significantly slower than reads (expected).")

    if bottlenecks:
        for b in bottlenecks:
            lines.append(f"- {b}")
    else:
        lines.append("- No significant bottlenecks identified at current test levels.")

    lines.extend([
        "",
        "## Recommendations",
        "",
        "Based on the benchmark results:",
        "",
    ])

    # Generate recommendations
    recommendations = []

    if pg_reads and rest_reads:
        best_pg_qps = max(r.qps for r in pg_reads)
        best_rest_qps = max(r.qps for r in rest_reads)
        if best_pg_qps > best_rest_qps * 1.5:
            recommendations.append("1. **Use direct PostgreSQL connections** for bulk operations instead of REST API")

    recommendations.extend([
        "2. **Implement connection pooling** (e.g., PgBouncer) for higher concurrency",
        "3. **Batch operations** when possible to reduce round-trip overhead",
        "4. **Consider upgrading to Small tier** (2 GB RAM) if connection limits are hit frequently",
    ])

    for rec in recommendations:
        lines.append(rec)

    lines.extend([
        "",
        "## Raw Data",
        "",
        "### Latency Distribution",
        "",
        "| Test | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) |",
        "|------|----------|----------|----------|----------|----------|",
    ])

    for r in results:
        lines.append(
            f"| {r.name} | {r.min_latency_ms:.1f} | {r.p50_latency_ms:.1f} | "
            f"{r.p95_latency_ms:.1f} | {r.p99_latency_ms:.1f} | {r.max_latency_ms:.1f} |"
        )

    # Add errors section if any
    errors_found = [r for r in results if r.errors]
    if errors_found:
        lines.extend([
            "",
            "### Errors Encountered",
            "",
        ])
        for r in errors_found:
            lines.append(f"**{r.name}:** {r.failed} failures")
            for err in r.errors[:3]:
                lines.append(f"  - `{err}`")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Benchmark Supabase backend QPS")
    parser.add_argument("--output", type=str, default="exports/benchmark_results.md",
                        help="Output file path for the report")
    args = parser.parse_args()

    try:
        results = run_all_benchmarks()

        # Generate report
        report = generate_report(results)

        # Write to file
        output_path = Path(__file__).parent.parent / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(report)

        print(f"\nReport written to: {output_path}")
        print("\n" + report)

    finally:
        close_connections()


if __name__ == "__main__":
    main()
