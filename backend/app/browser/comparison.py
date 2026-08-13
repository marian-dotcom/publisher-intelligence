from typing import Any

MAX_CHANGES = 200


def _keys(items: object, field: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {
        str(item[field])
        for item in items
        if isinstance(item, dict) and isinstance(item.get(field), str)
    }


def _by_key(items: object, field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item[field]): item
        for item in items
        if isinstance(item, dict) and isinstance(item.get(field), str)
    }


def compare_normalized_state(
    current: dict[str, Any],
    previous_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous_manifest is None:
        return {"status": "NOT_COMPARABLE", "reason": "NO_PREDECESSOR", "changes": []}
    previous = previous_manifest.get("normalized_state")
    if not isinstance(previous, dict):
        return {
            "status": "NOT_COMPARABLE",
            "reason": "PREDECESSOR_HAS_NO_NORMALIZED_STATE",
            "changes": [],
        }

    components = ("dom", "scripts", "network", "javascript_errors")
    for component in components:
        current_component = current.get(component)
        previous_component = previous.get(component)
        if not isinstance(current_component, dict) or not isinstance(previous_component, dict):
            return {
                "status": "NOT_COMPARABLE",
                "reason": f"MISSING_{component.upper()}_STATE",
                "changes": [],
            }
        if current_component.get("normalizer_version") != previous_component.get(
            "normalizer_version"
        ):
            return {
                "status": "NOT_COMPARABLE",
                "reason": f"INCOMPATIBLE_{component.upper()}_NORMALIZER",
                "changes": [],
            }

    changes: list[dict[str, object]] = []
    if current["dom"].get("sha256") != previous["dom"].get("sha256"):
        changes.append(
            {
                "kind": "STRUCTURAL_CHANGE",
                "component": "DOM",
                "before_sha256": previous["dom"].get("sha256"),
                "after_sha256": current["dom"].get("sha256"),
            }
        )

    _append_set_changes(
        changes,
        component="SCRIPT",
        current=_keys(current["scripts"].get("identities"), "stable_key"),
        previous=_keys(previous["scripts"].get("identities"), "stable_key"),
    )
    _append_set_changes(
        changes,
        component="NETWORK_DEPENDENCY",
        current=_keys(current["network"].get("dependencies"), "stable_key"),
        previous=_keys(previous["network"].get("dependencies"), "stable_key"),
    )
    _append_network_status_changes(
        changes,
        current=_by_key(current["network"].get("dependencies"), "stable_key"),
        previous=_by_key(previous["network"].get("dependencies"), "stable_key"),
    )
    _append_set_changes(
        changes,
        component="JAVASCRIPT_ERROR",
        current=_keys(current["javascript_errors"].get("errors"), "fingerprint"),
        previous=_keys(previous["javascript_errors"].get("errors"), "fingerprint"),
    )
    return {
        "status": "COMPARABLE",
        "reason": None,
        "change_count": len(changes),
        "changes": changes[:MAX_CHANGES],
        "truncated": len(changes) > MAX_CHANGES,
    }


def _append_set_changes(
    changes: list[dict[str, object]],
    *,
    component: str,
    current: set[str],
    previous: set[str],
) -> None:
    for identity in sorted(current - previous):
        changes.append({"kind": "PRESENCE_ADDED", "component": component, "stable_key": identity})
    for identity in sorted(previous - current):
        changes.append({"kind": "PRESENCE_REMOVED", "component": component, "stable_key": identity})


def _append_network_status_changes(
    changes: list[dict[str, object]],
    *,
    current: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]],
) -> None:
    status_fields = ("failure_count", "status_4xx", "status_5xx")
    for identity in sorted(current.keys() & previous.keys()):
        before = {field: int(previous[identity].get(field, 0)) for field in status_fields}
        after = {field: int(current[identity].get(field, 0)) for field in status_fields}
        if before != after:
            changes.append(
                {
                    "kind": "STATUS_CHANGE",
                    "component": "NETWORK_DEPENDENCY",
                    "stable_key": identity,
                    "before": before,
                    "after": after,
                }
            )
