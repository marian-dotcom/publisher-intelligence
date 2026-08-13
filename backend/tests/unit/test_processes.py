import json
import subprocess
import sys


def test_browser_worker_entrypoint_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.browser_worker", "--check"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload == {"process": "browser-worker", "status": "ready"}
