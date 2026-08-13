import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser-worker process placeholder")
    parser.add_argument("--once", action="store_true", help="validate the process entry point")
    parser.parse_args()
    print(
        json.dumps(
            {
                "process": "browser-worker",
                "status": "placeholder",
                "next_exec_plan": "EP-002",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
