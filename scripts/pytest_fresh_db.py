"""Run pytest against a brand-new Postgres database, dropped afterwards.

Integration tests write to the database in TEST_DATABASE_URL and do not clean up after themselves,
so a reused database makes later runs fail with duplicate keys (for example `teacher_phone_hash_key`).
This wrapper creates `abhyas_test_<random>` on the server named by --server (or TEST_DATABASE_URL),
exports TEST_DATABASE_URL pointing at it, runs pytest with the remaining arguments and drops the
database whatever the outcome. The browser tests additionally create and drop their own database.

    python scripts/pytest_fresh_db.py --server postgresql://postgres:@127.0.0.1:5432/postgres
    python scripts/pytest_fresh_db.py -- backend/tests/e2e -x
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid

import psycopg2  # type: ignore[import-untyped]
from psycopg2 import sql  # type: ignore[import-untyped]
from sqlalchemy.engine import make_url


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--server", default=os.environ.get("TEST_DATABASE_URL", ""))
    parser.add_argument("pytest_args", nargs="*")
    args = parser.parse_args()
    if not args.server:
        print("give --server or set TEST_DATABASE_URL", file=sys.stderr)
        return 2
    base = make_url(args.server)
    name = f"abhyas_test_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(
        base.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    fresh = base.set(database=name, drivername="postgresql").render_as_string(hide_password=False)
    print(f"fresh database: {name}", flush=True)
    try:
        env = {**os.environ, "TEST_DATABASE_URL": fresh}
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args.pytest_args], env=env
        ).returncode
    finally:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        admin.close()
        print(f"dropped database: {name}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
