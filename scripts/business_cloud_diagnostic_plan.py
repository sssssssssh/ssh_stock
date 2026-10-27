"""Print an unexecuted read-only plan. No DB driver/settings/.env imports."""

import json


def main():
    plan = dict(status="REAL_CLOUD_RECALC_NOT_AUTHORIZED", connects=False,
        requires=["separate explicit read-only approval", "explicit dedicated read-only DSN",
                  "separate approval for any real job or deployment"],
        proposed_queries=[
            "BEGIN READ ONLY",
            "SELECT 1",
            "SHOW server_version_num",
            "SHOW statement_timeout",
            "SHOW lock_timeout",
            "SELECT state,wait_event_type,wait_event,count(*) FROM pg_stat_activity "
            "WHERE application_name=:approved_worker_name GROUP BY 1,2,3",
            "ROLLBACK",
        ],
        forbidden_exports=["query text", "bind parameters", "DSN", "credentials", "business rows"],
        limits=["SELECT 1 is RTT plus driver/server time, not pure network latency",
                "pg_stat_activity requires reviewed privileges; never auto-grant",
                "no production task, EXPLAIN ANALYZE, deploy or migration authorization"])
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
