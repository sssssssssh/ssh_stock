"""Discardable E1/E2 counterexamples and E3 events; NEVER production credentials."""

import os
from datetime import timedelta


class UnsafeFingerprintMemo:
    """E1 REJECTED: demonstrates why root-local cached SHA is not evidence."""

    def __init__(self, original):
        self.original, self.values = original, {}

    def __call__(self, db, lo, hi):
        key = (lo, hi)
        if key not in self.values:
            self.values[key] = self.original(db, lo, hi)
        return dict(self.values[key])


class UnsafeCandidateCertificate:
    """E2 REJECTED: caller-owned generation misses direct SQL/rollback paths."""

    def __init__(self):
        self.values = {}

    def check(self, scalar, statement, params, generation=0):
        key = (params["root"], generation)
        if key not in self.values:
            self.values[key] = scalar(statement, params)
        return self.values[key]


def laboratory_only(db):
    from sqlalchemy import text

    from scripts.v14_test_database import verified_test_url

    verified_test_url()
    actual = db.execute(text("SELECT current_database(),"
        "current_setting('v14.test_instance',true),"
        "system_identifier::text FROM pg_control_system()")).one()
    if (not actual[0].startswith("v14_") or not actual[0].endswith("_test")
            or actual[1] != os.environ.get("V14_TEST_INSTANCE")
            or actual[2] != os.environ.get("V14_TEST_SYSTEM_IDENTIFIER")):
        raise ValueError("A42_DDL_REQUIRES_UUID_CHILD_ON_OWNED_PHYSICAL_INSTANCE")


def install_events(db):
    """E3: fixture-only statement counters; rollback is transactional, not sequence-based."""
    from sqlalchemy import text

    laboratory_only(db)  # Physical proof BEFORE the first schema/trigger statement.
    db.execute(text("CREATE SCHEMA a42_lab"))
    db.execute(text("CREATE TABLE a42_lab.generation(kind text PRIMARY KEY,n bigint NOT NULL)"))
    db.execute(text("INSERT INTO a42_lab.generation VALUES ('A',0),('B',0)"))
    db.execute(text("""CREATE FUNCTION a42_lab.changed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN UPDATE a42_lab.generation SET n=n+1 WHERE kind=TG_ARGV[0];
        RETURN NULL; END $$"""))
    for table, kind in (("stock_trade_status_daily", "A"), ("data_publication_row", "B")):
        db.execute(text(f"""CREATE TRIGGER a42_event AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
            ON public.{table} FOR EACH STATEMENT EXECUTE FUNCTION a42_lab.changed('{kind}')"""))
    db.commit()


def generations(db):
    from sqlalchemy import text

    return dict(db.execute(text("SELECT kind,n FROM a42_lab.generation")).all())


class EventEvidence:
    """SAFE_WITH_NEW_CONTRACT only: trusted enabled triggers, immutable counters.

    Global counters deliberately fail closed on outside-read-set A changes.
    Owners/superusers can bypass/reset them: NOT equivalent to today's contract.
    """

    def __init__(self):
        self.seen, self.root = None, None

    def prepare(self, db, current, window):
        from app.repositories import ab_merge_read as ab
        from app.services.job_execution import JobOwnershipLost, checkpoint
        from sqlalchemy import text

        if not current.ready or db.get_bind() is not current.connection:
            raise JobOwnershipLost("AB_READ_WORKSPACE_NOT_PINNED")
        checkpoint()
        db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
        db.execute(text("LOCK TABLE public.data_publication_row IN SHARE MODE"))
        actual = generations(db)
        if self.root is not None and self.root != (current.job_id, current.token):
            raise ValueError("A42_CERTIFICATE_ROOT_CHANGED")
        if self.seen is None:
            ab._prepare_candidate_read(db, current, window)
        else:
            if self.seen["A"] != actual["A"]:
                raise ValueError("A42_SOURCE_EVENT_CHANGED")
            if self.seen["B"] != actual["B"]:
                # Re-run the exact existing whole-B guard, including tombstones,
                # before accepting an INSERT/UPDATE/DELETE/ON CONFLICT generation.
                ab._prepare_candidate_read(db, current, window)
            else:
                evidence = current.ab_public_read_evidence
                missing = []
                day = window.start
                while day <= window.end:
                    if day not in evidence:
                        missing.append(day)
                    day += timedelta(days=1)
                # New dates only; old dates are justified by event continuity.
                if missing:
                    actual_rows = ab._public_fingerprints(db, min(missing), max(missing))
                    evidence.update({day: actual_rows.get(day) for day in missing})
        self.root, self.seen = (current.job_id, current.token), actual

    def verify(self, db):
        from sqlalchemy import text

        db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
        if self.seen is None or generations(db)["A"] != self.seen["A"]:
            raise ValueError("A42_SOURCE_EVENT_CHANGED")
