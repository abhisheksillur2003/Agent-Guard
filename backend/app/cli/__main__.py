import argparse
import asyncio
import os
from getpass import getpass

from backend.app.core.config import get_settings
from backend.app.core.errors import ApplicationError
from backend.app.db.session import get_session_factory
from backend.app.services.authentication import bootstrap_admin
from backend.app.services.local_demo import seed_local_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_admin = subparsers.add_parser(
        "create-admin", description="Create an organization and its initial administrator."
    )
    create_admin.add_argument("--organization", required=True)
    create_admin.add_argument("--slug", required=True)
    create_admin.add_argument("--email", required=True)
    seed_demo = subparsers.add_parser(
        "seed-local-demo",
        description="Create an idempotent local-only AgentGuard demo workspace.",
    )
    seed_demo.add_argument("--admin-email", required=True)
    seed_demo.add_argument(
        "--skip-credential",
        action="store_true",
        help="Populate the dashboard without issuing an agent credential.",
    )
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


async def run_seed_local_demo(args: argparse.Namespace) -> int:
    factory = get_session_factory()
    async with factory() as session:
        try:
            result = await seed_local_demo(
                session,
                admin_email=args.admin_email,
                environment=get_settings().environment,
                issue_credential=not args.skip_credential,
            )
        except ApplicationError as exc:
            print(exc.message)
            return 1
    if result.created:
        print(f"Created local demo resources: {', '.join(result.created)}.")
    else:
        print("Local demo resources already exist; no changes were made.")
    print(f"Agent ID: {result.agent_id}")
    print(f"Tool ID: {result.tool_id}")
    if result.credential is not None:
        print("Agent credential (shown once):")
        print(result.credential)
    elif args.skip_credential:
        print("No agent credential was issued; create one from the dashboard when needed.")
    else:
        print("The agent already has an active credential; rotate it in the dashboard if needed.")
    return 0


async def async_main() -> int:
    args = build_parser().parse_args()
    if args.command == "create-admin":
        return await run_create_admin(args)
    if args.command == "seed-local-demo":
        return await run_seed_local_demo(args)
    return 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
