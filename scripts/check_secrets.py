"""Fail on common committed credential formats and tracked environment files."""

import re
import subprocess
from pathlib import Path

PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "Slack token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
    ).stdout
    return [Path(item.decode()) for item in output.split(b"\0") if item]


def main() -> None:
    findings: list[str] = []
    for path in tracked_files():
        if path.name == ".env":
            findings.append(f"{path}: tracked environment file")
            continue
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        content = path.read_bytes()
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{path}: possible {label}")
    if findings:
        raise SystemExit("Potential committed secrets:\n" + "\n".join(findings))
    print("Secret scan passed: no known credential patterns found.")


if __name__ == "__main__":
    main()
