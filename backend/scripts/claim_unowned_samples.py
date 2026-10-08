"""Assign pre-ownership research Samples to an account.

Research Samples created before Milestone 5A have no owner and are invisible to
every account (nothing is deleted). Run this once to adopt them:

    cd backend
    PYTHONPATH=. ./venv/bin/python3 scripts/claim_unowned_samples.py --user-id <JWT userId>

Only Samples with no owner are touched; owned Samples are never reassigned.
Use --dry-run to see how many would be claimed.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from models.research import Sample
from services.db import get_db_session_factory_for_cli
from services.experiment_records import claim_unowned_samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="JWT userId that should own the samples")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    session = get_db_session_factory_for_cli()()
    try:
        pending = session.scalar(
            select(func.count()).select_from(Sample).where(Sample.owner_user_id.is_(None))
        )
        if args.dry_run:
            print(f"{pending} unowned sample(s) would be assigned.")
            return 0
        claimed = claim_unowned_samples(session, args.user_id)
        print(f"Assigned {claimed} unowned sample(s) to the given account.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
