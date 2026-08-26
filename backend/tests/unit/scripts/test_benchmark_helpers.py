"""CI-enforced regression for the browser benchmark helper scripts.

Covers the two repaired correctness defects: binary memory-unit conversion
(Finding 1) and ordinal-free container limit verification (Finding 2).
"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"


def _load(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_stats_self_test_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "benchmark_stats.py"), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "self-test: OK" in result.stdout


def test_memory_conversion_factors_are_mathematically_correct() -> None:
    stats = _load("benchmark_stats")
    assert stats.mem_to_mib("512B") == 512 / (1024 * 1024)
    assert stats.mem_to_mib("64KiB") == 0.0625
    assert stats.mem_to_mib("249.7MiB") == 249.7
    assert stats.mem_to_mib("1.25GiB") == 1280.0


def test_unsupported_decimal_unit_fails_loudly() -> None:

    stats = _load("benchmark_stats")
    with pytest.raises(ValueError, match="unknown memory unit"):
        stats.mem_to_mib("3MB")


def test_verification_is_ordinal_free() -> None:
    verify = _load("benchmark_verify")
    containers = [
        verify.Container(
            name="publisher-intelligence-browser-worker-2",  # valid N=1, NOT -1
            service="browser-worker",
            nano_cpus=int(0.50 * 1e9),
            memory=1280 * 1024**2,
        ),
        verify.Container(
            name="publisher-intelligence-api-1",
            service="api",
            nano_cpus=int(0.50 * 1e9),
            memory=512 * 1024**2,
        ),
    ]
    expected = {
        "api": (0.50, 512 * 1024**2, 1),
        "browser-worker": (0.50, 1280 * 1024**2, 1),
    }
    assert verify.collect_errors(expected=expected, containers=containers) == []


def test_verification_requires_exact_live_replica_count() -> None:
    verify = _load("benchmark_verify")
    containers = [
        verify.Container(
            name=f"publisher-intelligence-browser-worker-{ordinal}",
            service="browser-worker",
            nano_cpus=int(0.50 * 1e9),
            memory=1280 * 1024**2,
        )
        for ordinal in (3, 7)  # arbitrary non-contiguous ordinals
    ]
    expected = {"browser-worker": (0.50, 1280 * 1024**2, 2)}
    assert verify.collect_errors(expected=expected, containers=containers) == []

    too_many = [*containers, containers[0]]
    errors = verify.collect_errors(expected=expected, containers=too_many)
    assert any("resolved 3 container(s), expected 2" in error for error in errors)


def test_verification_flags_limit_mismatch() -> None:
    verify = _load("benchmark_verify")
    containers = [
        verify.Container(
            name="publisher-intelligence-browser-worker-5",
            service="browser-worker",
            nano_cpus=int(0.70 * 1e9),
            memory=2048 * 1024**2,
        )
    ]
    expected = {"browser-worker": (0.50, 1280 * 1024**2, 1)}
    errors = verify.collect_errors(expected=expected, containers=containers)
    assert any("cpu=0.7" in error for error in errors)
    assert any(f"mem={2048 * 1024**2}" in error for error in errors)
