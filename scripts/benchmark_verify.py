"""EP-026 benchmark harness: resource-limit verification helpers.

Container lookup must NEVER assume Compose replica ordinals (observed on a
real Mac: the single live browser-worker was named
``publisher-intelligence-browser-worker-2``). Callers resolve containers via
Compose service identity (e.g. ``docker compose ps -q <service>``) and pass
the resolved containers here; this module verifies limits and counts purely
from the provided data.
"""

import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Container:
    name: str
    service: str
    nano_cpus: int
    memory: int


def collect_errors(
    *,
    expected: dict[str, tuple[float, int, int]],
    containers: list[Container],
) -> list[str]:
    """Verify resolved containers against expected (cpu, mem_bytes, count).

    ``expected`` is keyed by service name; ``count`` is the requested number of
    replicas. Returns human-readable error strings; empty list = verified.
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
            errors.append(
                f"{container.name}: cpu={actual_cpu} expected={expected_cpu}"
            )
        if container.memory != expected_mem:
            errors.append(
                f"{container.name}: mem={container.memory} expected={expected_mem}"
            )
    for service, (_cpu, _mem, count) in sorted(expected.items()):
        actual = counts.get(service, 0)
        if actual != count:
            errors.append(
                f"{service}: resolved {actual} container(s), expected {count}"
            )
    return errors


def resolve_service_container_ids(
    compose_files: list[str], service: str
) -> tuple[list[str], list[str]]:
    """Resolve live container IDs + names for one Compose service.

    Uses ``docker compose ps -q <service>`` (service identity, never ordinals).
    """
    files: list[str] = []
    for path in compose_files:
        files.extend(["-f", path])
    ids_raw = subprocess.run(
        ["docker", "compose", *files, "ps", "-q", service],
        capture_output=True,
        text=True,
        check=False,
    )
    ids = [line.strip() for line in ids_raw.stdout.splitlines() if line.strip()]
    names: list[str] = []
    for container_id in ids:
        probe = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}}", container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        names.append(probe.stdout.strip().lstrip("/"))
    return ids, names


def inspect_containers(container_ids: list[str]) -> list[Container]:
    """Inspect resolved IDs into Container records via docker inspect."""
    containers: list[Container] = []
    for container_id in container_ids:
        raw = subprocess.run(
            [
                "docker",
                "inspect",
                container_id,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if raw.returncode != 0:
            raise RuntimeError(f"docker inspect failed for {container_id}")
        data = json.loads(raw.stdout)[0]
        containers.append(
            Container(
                name=data["Name"].lstrip("/"),
                service=data["Config"]["Labels"]["com.docker.compose.service"],
                nano_cpus=int(data["HostConfig"]["NanoCpus"]),
                memory=int(data["HostConfig"]["Memory"]),
            )
        )
    return containers


def main(argv: list[str]) -> int:
    """CLI: benchmark_verify.py PROFILE REPLICAS [-f COMPOSE_FILE]...

    Resolves live containers per Compose service (service identity, never
    ordinals), verifies replica counts and profile limits, prints the nominal
    envelope. Exit 0 = verified.
    """
    profile = argv[0]
    replicas = int(argv[1])
    compose_files = argv[2:]

    presets: dict[str, dict[str, tuple[float, int]]] = {
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
    if profile not in presets:
        print(f"unknown BENCHMARK_PROFILE {profile!r}", file=sys.stderr)
        return 2

    limits = presets[profile]
    expected = {
        service: (cpu, memory, replicas if service == "browser-worker" else 1)
        for service, (cpu, memory) in limits.items()
    }

    ids: list[str] = []
    names_by_id: dict[str, str] = {}
    for service in sorted(limits):
        raw = subprocess.run(
            ["docker", "compose", *(flag for path in compose_files for flag in ("-f", path)),
             "--profile", "browser", "ps", "-q", service],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in raw.stdout.splitlines():
            container_id = line.strip()
            if not container_id:
                continue
            ids.append(container_id)
            name_raw = subprocess.run(
                ["docker", "inspect", "--format", "{{.Name}}", container_id],
                capture_output=True,
                text=True,
                check=False,
            )
            names_by_id[container_id] = name_raw.stdout.strip().lstrip("/")

    containers = inspect_containers(ids)
    errors = collect_errors(expected=expected, containers=containers)

    total_cpu = sum(cpu * count for cpu, _mem, count in expected.values())
    total_mem_mib = sum(mem / 1024**2 for _cpu, mem, count in expected.values())
    if errors:
        for error in errors:
            print(f"LIMIT-VERIFY ERROR {error}")
        return 1
    resolved = ", ".join(sorted(names_by_id.get(cid, cid) for cid in ids))
    print(f"limits verified against BENCHMARK_PROFILE={profile}")
    print(f"resolved_containers=[{resolved}]")
    print(f"nominal_envelope_cpus={total_cpu:.2f}")
    print(f"nominal_envelope_mem_mib={round(total_mem_mib)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
