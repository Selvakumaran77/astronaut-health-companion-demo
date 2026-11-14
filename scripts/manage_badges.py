"""Issue or revoke an astronaut's scannable badge barcode."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

import barcode
from barcode.writer import SVGWriter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from healthmon.auth import AuthStore  # noqa: E402

DEFAULT_DATA = os.path.join(ROOT, "data", "synthetic", "crew_vitals_simulated.csv")
DEFAULT_AUTH_DB = os.path.join(ROOT, "data", "astronaut_badges.sqlite3")
DEFAULT_BADGE_DIR = os.path.join(ROOT, "data", "badges")
DEFAULT_CODES_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.join(ROOT, "data"),
    "SpaceAppsHealthMonitor",
    "mission_numbers.csv",
)


def save_barcode(crew_id: str, code: str, badge_dir: str) -> str:
    os.makedirs(badge_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{crew_id}-{stamp}"
    image = barcode.get("code128", code, writer=SVGWriter())
    return image.save(
        os.path.join(badge_dir, filename),
        options={
            "module_width": 0.35,
            "module_height": 28,
            "quiet_zone": 4,
            "write_text": False,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage astronaut barcode badges")
    parser.add_argument("--auth-db", default=DEFAULT_AUTH_DB)
    parser.add_argument("--data", default=DEFAULT_DATA)
    parser.add_argument("--badge-dir", default=DEFAULT_BADGE_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser(
        "issue-mission-number",
        aliases=["issue-badge"],
        help="create a private mission number; previous number is revoked",
    )
    issue.add_argument("crew_id")
    issue_all = commands.add_parser(
        "issue-all",
        help="issue private mission numbers for all crew members and save them locally",
    )
    issue_all.add_argument("--codes-file", default=DEFAULT_CODES_FILE)
    revoke = commands.add_parser("revoke-badge", help="revoke the current badge for a crew ID")
    revoke.add_argument("crew_id")
    args = parser.parse_args()

    try:
        with open(args.data, encoding="utf-8", newline="") as file:
            crew_ids = {row["crew_id"] for row in csv.DictReader(file)}

        store = AuthStore(args.auth_db)
        if args.command == "revoke-badge":
            if args.crew_id not in crew_ids:
                raise ValueError(f"Unknown crew ID: {args.crew_id}")
            count = store.revoke_badges(args.crew_id)
            print(f"Revoked {count} badge(s) for {args.crew_id}.")
            return 0

        if args.command == "issue-all":
            records = []
            for crew_id in sorted(crew_ids):
                code = store.issue_mission_number(crew_id)
                barcode_path = save_barcode(crew_id, code, args.badge_dir)
                records.append({
                    "crew_id": crew_id,
                    "mission_number": code,
                    "barcode_file": os.path.relpath(barcode_path, ROOT),
                })
            codes_path = os.path.abspath(args.codes_file)
            os.makedirs(os.path.dirname(codes_path), exist_ok=True)
            with open(codes_path, "w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=("crew_id", "mission_number", "barcode_file")
                )
                writer.writeheader()
                writer.writerows(records)
            print(f"Issued {len(records)} private mission numbers. Saved to: {codes_path}")
            print("This file contains bearer credentials; keep it private.")
            return 0

        if args.crew_id not in crew_ids:
            raise ValueError(f"Unknown crew ID: {args.crew_id}")
        code = store.issue_mission_number(args.crew_id)
        output = save_barcode(args.crew_id, code, args.badge_dir)
        print(f"Mission number issued for {args.crew_id}. Barcode: {output}")
        print(f"Private mission number (store securely): {code}")
        print("Issuing another number or revoking access disables this one.")
    except (OSError, ValueError) as exc:
        print(f"Could not manage badge: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
