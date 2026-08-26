"""CI-enforced regression for the browser benchmark helper scripts.

Covers the two repaired correctness defects: binary memory-unit conversion
(Finding 1) and ordinal-free container limit verification (Finding 2).
"""

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"


@dataclass
class _Result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class _FakeRunner:
    """Deterministic subprocess stand-in recording calls."""

    def __init__(self, results: dict[str, _Result]) -> None:
        self.calls: list[list[str]] = []
        self._results = results

    def __call__(self, args: list[str], **_kwargs: object) -> _Result:
        self.calls.append(args)
        joined = " ".join(args)
        key = next((k for k in self._results if k in joined), None)
        if key is None:
            raise AssertionError(f"unexpected command {args}")
        return self._results[key]


def _load(name: str) -> ModuleType:
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


def test_compose_args_render_one_f_per_file() -> None:
    verify = _load("benchmark_verify")
    assert verify.compose_base_args(["compose.yaml"]) == [
        "docker",
        "compose",
        "-f",
        "compose.yaml",
    ]
    assert verify.compose_base_args(["compose.yaml", "override.yml"]) == [
        "docker",
        "compose",
        "-f",
        "compose.yaml",
        "-f",
        "override.yml",
    ]
    joined = " ".join(verify.compose_base_args(["a.yml", "b.yml"]))
    assert "-f -f" not in joined


def test_failed_compose_ps_fails_loudly() -> None:
    import pytest

    verify = _load("benchmark_verify")
    runner = _FakeRunner({"ps": _Result(1, stderr="boom")})
    with pytest.raises(RuntimeError, match="docker compose ps failed"):
        verify.compose_ps_ids(runner, ["compose.yaml"], "api")


def test_medium_nominal_envelope_matches_contract() -> None:
    verify = _load("benchmark_verify")
    expected = {1: (2.85, 3792), 2: (3.35, 5072), 3: (3.85, 6352)}
    for replicas, (cpus, mem_mib) in expected.items():
        assert verify.nominal_envelope("MEDIUM", replicas) == (cpus, mem_mib), replicas


def test_medium_envelope_arithmetic_components() -> None:
    mib = 1024**2
    verify = _load("benchmark_verify")
    base_cpu = 0.50 + 0.40 + 0.20 + 0.50 + 0.50 + 0.25
    base_mem = 512 * mib + 400 * mib + 256 * mib + 512 * mib + 512 * mib + 320 * mib
    for replicas in (1, 2, 3):
        cpu, mem = verify.nominal_envelope("MEDIUM", replicas)
        assert cpu == round(base_cpu + 0.50 * replicas, 2)
        assert mem == round((base_mem + 1280 * mib * replicas) / mib)
