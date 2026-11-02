from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from cloud.feedback.service import (
    FeedbackStatus,
    SQLiteFeedbackStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review edge prompt suggestions")
    parser.add_argument("--db", required=True, help="Path to Cloud Agent feedback SQLite DB")
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_command = subcommands.add_parser("list")
    list_command.add_argument(
        "--status", choices=tuple(status.value for status in FeedbackStatus)
    )
    list_command.add_argument("--limit", type=int, default=100)

    review_command = subcommands.add_parser("review")
    review_command.add_argument("suggestion_id")
    decision = review_command.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    review_command.add_argument("--reviewer", required=True)
    review_command.add_argument("--note", default="")

    publish_command = subcommands.add_parser("publish")
    publish_command.add_argument("suggestion_id")

    subcommands.add_parser("weekly-report")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = SQLiteFeedbackStore(args.db)
    if args.command == "list":
        status = FeedbackStatus(args.status) if args.status else None
        result = store.list(status=status, limit=args.limit)
        print(json.dumps([asdict(item) for item in result], ensure_ascii=False))
    elif args.command == "review":
        item = store.review(
            args.suggestion_id,
            approve=args.approve,
            reviewer=args.reviewer,
            note=args.note,
        )
        print(json.dumps(asdict(item), ensure_ascii=False))
    elif args.command == "publish":
        item = store.mark_published(args.suggestion_id)
        print(json.dumps(asdict(item), ensure_ascii=False))
    else:
        report = store.weekly_report()
        print(json.dumps(asdict(report), ensure_ascii=False))


if __name__ == "__main__":
    main()