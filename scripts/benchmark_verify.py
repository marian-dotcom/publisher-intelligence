"""EP-026 benchmark harness: resource-limit verification helpers.

Container lookup must NEVER assume Compose replica ordinals (observed on a
real Mac: the single live browser-worker was named
``publisher-intelligence-browser-worker-2``). Containers are resolved by
Compose SERVICE identity and verified here purely from inspected data.

CLI contract (paths only — this module renders its own ``-f`` flags):

    benchmark_verify.py PROFILE REPLICAS [COMPOSE_FILE ...]

Example:

    benchmark_verify.py MEDIUM 3 compose.yaml override.yml
"""

import json
import subprocess
import sys
from dataclasses import dataclass

PRESETS: dict[str, dict[str, tuple[float, int]]] = {
    "SMALL": {
        "api": (0.30, 512 * 1024**2),
        "frontend": (0.25, 384 * 1024**2),
        "scheduler": (0.10, 192 * 1024**2),
        "worker": (0.30, 320 * 1024**2),
        "postgres": (0.20, 512 * 1024**2),
        "minio": (0.10, 256 * 1024**2),
        "browser-worker": (0.70, 1536 * 1024**2),
    },
    "MEDIUM": {
        "api": (0.50, 512 * 1024**2),
        "frontend": (0.40, 400 * 1024**2),
        "scheduler": (0.20, 256 * 1024**2),
        "worker": (0.50, 512 * 1024**2),
        "postgres": (0.50, 512 * 1024**2),
        "minio": (0.25, 320 * 1024**2),
        "browser-worker": (0.50, 1280 * 1024**2),
    },
    "ORACLE_FREE": {
        "api": (0.30, 512 * 1024**2),
        "frontend": (0.25, 384 * 1024**2),
        "scheduler": (0.10, 192 * 1024**2),
        "worker": (0.30, 320 * 1024**2),
        "postgres": (0.20, 1024 * 1024**2),
        "minio": (0.10, 256 * 1024**2),
        "browser-worker": (0.70, 2048 * 1024**2),
    },
}

_runner = subprocess.run


@dataclass(frozen=True)
class Container:
    name: str
    service: str
    nano_cpus: int
    memory: int


def compose_base_args(compose_paths: list[str]) -> list[str]:
    """Render exactly one ``-f PATH`` pair per Compose file path."""
    args: list[str] = ["docker", "compose"]
    for path in compose_paths:
        args.extend(["-f", path])
    return args


def compose_ps_ids(
    runner,
    compose_paths: list[str],
    service: str,
) -> list[str]:
    """Resolve live container IDs for one Compose service.

    Fails loudly if the Compose invocation itself fails.
    """
    args = [*compose_base_args(compose_paths), "--profile", "browser", "ps", "-q", service]
    raw = runner(args, capture_output=True, text=True)
    if raw.returncode != 0:
        raise RuntimeError(
            f"docker compose ps failed for service {service!r}: "
            f"rc={raw.returncode} stderr={raw.stderr.strip()}"
        )
    return [line.strip() for line in raw.stdout.splitlines() if line.strip()]


def inspect_container(runner, container_id: str) -> Container:
    raw = runner(["docker", "inspect", container_id], capture_output=True, text=True)
    if raw.returncode != 0:
        raise RuntimeError(
            f"docker inspect failed for {container_id}: {raw.stderr.strip()}"
        )
    data = json.loads(raw.stdout)[0]
    return Container(
        name=data["Name"].lstrip("/"),
        service=data["Config"]["Labels"]["com.docker.compose.service"],
        nano_cpus=int(data["HostConfig"]["NanoCpus"]),
        memory=int(data["HostConfig"]["Memory"]),
    )


def resolve_service_containers(
    runner,
    compose_paths: list[str],
    *,
    expected_services: dict[str, tuple[float, int]],
) -> list[Container]:
    """Resolve + inspect every live container for the given services."""
    containers: list[Container] = []
    for service in sorted(expected_services):
        container_ids = compose_ps_ids(runner, compose_paths, service)
        for container_id in container_ids:
            containers.append(inspect_container(runner, container_id))
    return containers


def collect_errors(
    *,
    expected: dict[str, tuple[float, int, int]],
    containers: list[Container],
) -> list[str]:
    """Verify resolved containers against expected (cpu, mem_bytes, count).

    Returns human-readable error strings; empty list = verified. Identity is
    the Compose service label; names/ordinals are never used as keys.
    """
    errors: list[str] = []
    counts: dict[str, int] = {}
    for container in containers:
        counts[container.service] = counts.get(container.service, 0) + 1
        if container.service not in expected:
            errors.append(f"unexpected service {container.service!r} ({container.name})")
            continue
        expected_cpu, expected_mem, _count = expected[container.service]
        actual_cpu = container.nano_cpus / 1e9
        if abs(actual_cpu - expected_cpu) > 0.001:
            errors.append(f"{container.name}: cpu={actual_cpu} expected={expected_cpu}")
        if container.memory != expected_mem:
            errors.append(f"{container.name}: mem={container.memory} expected={expected_mem}")
    for service, (_cpu, _mem, count) in sorted(expected.items()):
        actual = counts.get(service, 0)
        if actual != count:
            errors.append(
                f"{service}: resolved {actual} container(s), expected {count}"
            )
    return errors


def nominal_envelope(profile: str, replicas: int) -> tuple[float, int]:
    """Nominal totals (CPUs, MiB) for a profile at N browser-worker replicas.

    Memory is counted per replica: browser-worker RAM scales with N.
    """
    limits = PRESETS[profile]
    total_cpu = 0.0
    total_mem_bytes = 0
    for service, (cpu, mem_bytes) in limits.items():
        count = replicas if service == "browser-worker" else 1
        total_cpu += cpu * count
        total_mem_bytes += mem_bytes * count
    total_mem_mib = round(total_mem_bytes / 1024**2)
    return round(total_cpu, 2), total_mem_mib


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: benchmark_verify.py PROFILE REPLICAS COMPOSE_FILE [...]",
            file=sys.stderr,
        )
        return 2
    profile = argv[0]
    try:
        replicas = int(argv[1])
    except ValueError:
        print(f"invalid replica count {argv[1]!r}", file=sys.stderr)
        return 2
    compose_paths = argv[2:]
    if profile not in PRESETS:
        print(
            f"unknown BENCHMARK_PROFILE {profile!r}; "
            "expected SMALL|MEDIUM|ORACLE_FREE",
            file=sys.stderr,
        )
        return 2

    limits = PRESETS[profile]
    expected = {
        service: (cpu, memory, replicas if service == "browser-worker" else 1)
        for service, (cpu, memory) in limits.items()
    }

    try:
        containers = resolve_service_containers(
            _runner, compose_paths, expected_services=limits
        )
    except RuntimeError as error:
        print(f"LIMIT-VERIFY ERROR {error}")
        return 1

    errors = collect_errors(expected=expected, containers=containers)
    resolved_names = sorted(container.name for container in containers)

    total_cpu, total_mem_mib = nominal_envelope(profile, replicas)
    if errors:
        for error in errors:
            print(f"LIMIT-VERIFY ERROR {error}")
        print(f"resolved_containers=[{', '.join(resolved_names)}]")
        return 1
    print(f"limits verified against BENCHMARK_PROFILE={profile}")
    print(f"resolved_containers=[{', '.join(resolved_names)}]")
    print(f"nominal_envelope_cpus={total_cpu:.2f}")
    print(f"nominal_envelope_mem_mib={total_mem_mib}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
