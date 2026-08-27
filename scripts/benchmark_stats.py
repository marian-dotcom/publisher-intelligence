"""EP-026 browser benchmark: resource-sample analysis + unit self-test.

Sample file format (one row PER CONTAINER per snapshot, written by
scripts/browser_benchmark.sh):

    HH:MM:SS|container-name|CPU%|mem_used/mem_limit

Memory values may arrive in any Docker binary unit (B/KiB/MiB/GiB); everything
is normalized to MiB here. Unknown units fail loudly instead of producing
wrong peaks.
"""

import sys

# Binary-unit conversion to MiB: B -> 1/(1024*1024), KiB -> 1/1024.
UNITS_TO_MIB = {"B": 1 / (1024 * 1024), "KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0}


def mem_to_mib(raw: str) -> float:
    import re

    match = re.fullmatch(r"([0-9.]+)([A-Za-z]+)", raw.split("/")[0].strip())
    if match is None:
        raise ValueError(f"unparseable memory value {raw!r}")
    value, unit = float(match.group(1)), match.group(2)
    if unit not in UNITS_TO_MIB:
        raise ValueError(
            f"unknown memory unit in {raw!r}; expected one of B/KiB/MiB/GiB"
        )
    return value * UNITS_TO_MIB[unit]


def parse_line(line: str):
    parts = line.rstrip("\n").split("|")
    if len(parts) != 4:
        return None
    ts, name, cpu_raw, mem_raw = parts
    return ts, name, float(cpu_raw.rstrip("%")), mem_to_mib(mem_raw)


def summarize(samples_path: str) -> None:
    rows = [r for r in (parse_line(l) for l in open(samples_path)) if r]
    snapshots = {ts for ts, _name, _cpu, _mem in rows}
    print(f"resource_rows={len(rows)}")
    print(f"resource_snapshots={len(snapshots)}")

    per_container_peak_mib: dict[str, float] = {}
    per_browser_peak_mib: dict[str, float] = {}
    browser_cpu_per_snapshot: dict[str, float] = {}
    browser_mem_per_snapshot: dict[str, float] = {}
    all_mem_per_snapshot: dict[str, float] = {}
    for ts, name, cpu, mem in rows:
        per_container_peak_mib[name] = max(per_container_peak_mib.get(name, 0.0), mem)
        all_mem_per_snapshot[ts] = all_mem_per_snapshot.get(ts, 0.0) + mem
        if "browser-worker" in name:
            per_browser_peak_mib[name] = max(per_browser_peak_mib.get(name, 0.0), mem)
            browser_cpu_per_snapshot[ts] = browser_cpu_per_snapshot.get(ts, 0.0) + cpu
            browser_mem_per_snapshot[ts] = browser_mem_per_snapshot.get(ts, 0.0) + mem

    for name, peak in sorted(per_container_peak_mib.items()):
        print(f"per_container_peak_mib {name}: {peak:.1f}")
    if not per_browser_peak_mib:
        print("no browser-worker samples captured")
        return
    for name, peak in sorted(per_browser_peak_mib.items()):
        print(f"peak_browser_replica_mem_mib {name}: {peak:.1f}")
    print(f"peak_aggregate_browser_mem_mib: {max(browser_mem_per_snapshot.values()):.1f}")
    print(f"peak_aggregate_browser_cpu_pct: {max(browser_cpu_per_snapshot.values()):.2f}")
    print(f"peak_aggregate_app_mem_mib: {max(all_mem_per_snapshot.values()):.1f}")


def self_test() -> None:
    assert mem_to_mib("512B") == 512 / (1024 * 1024)
    assert abs(mem_to_mib("512B") - 0.00048828125) < 1e-12
    assert mem_to_mib("64KiB") == 0.0625
    assert abs(mem_to_mib("249.7MiB") - 249.7) < 1e-9
    assert mem_to_mib("1.25GiB") == 1280.0
    try:
        mem_to_mib("3MB")
    except ValueError as error:
        assert "unknown memory unit" in str(error)
    else:
        raise AssertionError("decimal-unit memory value must fail loudly")
    print("benchmark_stats self-test: OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) > 1:
        summarize(sys.argv[1])
    else:
        print("usage: benchmark_stats.py [--self-test | SAMPLES_FILE]", file=sys.stderr)
        sys.exit(2)
