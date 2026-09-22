import argparse
import asyncio
import os
from getpass import getpass

from backend.app.core.errors import ApplicationError
from backend.app.db.session import get_session_factory
from backend.app.services.authentication import bootstrap_admin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_admin = subparsers.add_parser(
        "create-admin", description="Create an organization and its initial administrator."
    )
    create_admin.add_argument("--organization", required=True)
    create_admin.add_argument("--slug", required=True)
    create_admin.add_argument("--email", required=True)
    return parser


async def run_create_admin(args: argparse.Namespace) -> int:
    password = os.environ.get("AGENTGUARD_BOOTSTRAP_PASSWORD") or getpass(
        "Administrator password: "
    )
    confirmation = os.environ.get("AGENTGUARD_BOOTSTRAP_PASSWORD") or getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 2

    factory = get_session_factory()
    async with factory() as session:
        try:
            organization, user = await bootstrap_admin(
                session,
                organization_name=args.organization,
                organization_slug=args.slug,
                email=args.email,
                password=password,
            )
        except ApplicationError as exc:
            print(exc.message)
            return 1
    print(f"Created administrator {user.email} for organization {organization.slug}.")
    return 0


async def async_main() -> int:
    args = build_parser().parse_args()
    if args.command == "create-admin":
        return await run_create_admin(args)
    return 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
