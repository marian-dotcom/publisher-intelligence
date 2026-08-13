import json
import subprocess
import sys


def test_browser_worker_placeholder_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.browser_worker", "--once"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload == {
        "next_exec_plan": "EP-002",
        "process": "browser-worker",
        "status": "placeholder",
    }
