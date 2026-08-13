import argparse
import asyncio
import json

from app.browser.service import CheckpointService
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue


async def register_and_enqueue(args: argparse.Namespace) -> None:
    settings = get_settings()
    factory = get_session_factory()
    service = CheckpointService(factory, JobQueue(factory), settings)
    result = await service.register_and_enqueue(
        tenant_slug=args.tenant_slug,
        tenant_name=args.tenant_name,
        publisher_name=args.publisher_name,
        site_name=args.site_name,
        url=args.url,
    )
    print(
        json.dumps(
            {
                "tenant_id": str(result.tenant_id),
                "checkpoint_run_id": str(result.checkpoint_run_id),
                "job_id": str(result.job_id),
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage explicit browser checkpoint configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser(
        "register-and-enqueue",
        description="Register one pilot URL and enqueue one immediate diagnostic checkpoint",
    )
    register.add_argument("--tenant-slug", required=True)
    register.add_argument("--tenant-name", required=True)
    register.add_argument("--publisher-name", required=True)
    register.add_argument("--site-name", required=True)
    register.add_argument("--url", required=True)
    args = parser.parse_args()
    if args.command == "register-and-enqueue":
        asyncio.run(register_and_enqueue(args))


if __name__ == "__main__":
    main()
