"""Close M15.3 walk-forward lineage and cancellation integrity gaps.

Revision ID: 0044_m15_3_1_walk_forward_integrity
Revises: 0043_m15_3_walk_forward_validation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_m15_3_1_walk_forward_integrity"
down_revision = "0043_m15_3_walk_forward_validation"
branch_labels = None
depends_on = None


REPORT = "portfolio_walk_forward_validation_report"
WINDOW = "portfolio_walk_forward_window_validation"
STABILITY = "portfolio_walk_forward_parameter_stability"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_portfolio_experiment_trial_run_owner",
        "portfolio_experiment_trial",
        ["id", "run_id"],
    )

    op.add_column(REPORT, sa.Column("validation_policy_snapshot", postgresql.JSONB()))
    op.add_column(REPORT, sa.Column("validation_policy_hash", sa.String(64)))
    op.add_column(REPORT, sa.Column("transition_count", sa.Integer()))
    op.add_column(REPORT, sa.Column("switch_count", sa.Integer()))
    op.add_column(REPORT, sa.Column("switch_rate", sa.Numeric(60, 18)))

    for name in (
        "selected_train_run_id",
        "train_performance_id",
        "train_risk_id",
        "train_trade_id",
        "train_period_id",
    ):
        op.add_column(WINDOW, sa.Column(name, postgresql.UUID(as_uuid=True)))
    op.add_column(WINDOW, sa.Column("train_date_hash", sa.String(64)))
    op.add_column(WINDOW, sa.Column("test_date_hash", sa.String(64)))
    op.add_column(WINDOW, sa.Column("identity_snapshot", postgresql.JSONB()))

    op.add_column(STABILITY, sa.Column("transition_count", sa.Integer()))
    op.add_column(
        STABILITY, sa.Column("adjacent_value_switch_count", sa.Integer())
    )
    op.add_column(
        STABILITY, sa.Column("adjacent_value_switch_rate", sa.Numeric(60, 18))
    )

    connection = op.get_bind()
    invalid_id = connection.scalar(
        sa.text(
            """
            SELECT wv.validation_id
              FROM portfolio_walk_forward_window_validation AS wv
              JOIN portfolio_walk_forward_window AS w
                ON w.study_id = wv.study_id AND w.window_no = wv.window_no
              LEFT JOIN portfolio_experiment AS e
                ON e.id = wv.train_experiment_id
              LEFT JOIN portfolio_experiment_evaluation_report AS er
                ON er.id = wv.train_evaluation_id
               AND er.experiment_id = wv.train_experiment_id
              LEFT JOIN portfolio_experiment_trial AS t
                ON t.id = wv.selected_trial_id
               AND t.experiment_id = wv.train_experiment_id
              LEFT JOIN portfolio_experiment_trial_evaluation AS te
                ON te.evaluation_id = wv.train_evaluation_id
               AND te.trial_id = wv.selected_trial_id
               AND te.experiment_id = wv.train_experiment_id
               AND te.run_id = t.run_id
              LEFT JOIN portfolio_performance_report AS tp
                ON tp.id = te.performance_id AND tp.run_id = t.run_id
              LEFT JOIN portfolio_performance_risk_report AS tr
                ON tr.id = te.risk_id AND tr.performance_id = tp.id
               AND tr.run_id = t.run_id
              LEFT JOIN portfolio_performance_trade_report AS tt
                ON tt.id = te.trade_id AND tt.performance_id = tp.id
               AND tt.run_id = t.run_id
              LEFT JOIN portfolio_performance_period_report AS tpr
                ON tpr.id = te.period_id AND tpr.performance_id = tp.id
               AND tpr.risk_id = tr.id AND tpr.trade_id = tt.id
               AND tpr.run_id = t.run_id
              LEFT JOIN portfolio_backtest_run AS orun
                ON orun.id = wv.oos_run_id
              LEFT JOIN portfolio_performance_report AS opf
                ON opf.id = wv.oos_performance_id AND opf.run_id = orun.id
              LEFT JOIN portfolio_performance_risk_report AS orisk
                ON orisk.id = wv.oos_risk_id AND orisk.performance_id = opf.id
               AND orisk.run_id = orun.id
              LEFT JOIN portfolio_performance_trade_report AS otrade
                ON otrade.id = wv.oos_trade_id AND otrade.performance_id = opf.id
               AND otrade.run_id = orun.id
              LEFT JOIN portfolio_performance_period_report AS operiod
                ON operiod.id = wv.oos_period_id
               AND operiod.performance_id = opf.id
               AND operiod.risk_id = orisk.id AND operiod.trade_id = otrade.id
               AND operiod.run_id = orun.id
             WHERE e.id IS NULL OR er.id IS NULL OR t.id IS NULL OR t.run_id IS NULL
                OR te.trial_id IS NULL OR tp.id IS NULL OR tr.id IS NULL
                OR tt.id IS NULL OR tpr.id IS NULL OR orun.id IS NULL
                OR opf.id IS NULL OR orisk.id IS NULL OR otrade.id IS NULL
                OR operiod.id IS NULL
                OR er.selected_trial_id IS DISTINCT FROM t.id
                OR er.selected_run_id IS DISTINCT FROM t.run_id
                OR te.performance_id IS DISTINCT FROM tp.id
                OR te.risk_id IS DISTINCT FROM tr.id
                OR te.trade_id IS DISTINCT FROM tt.id
                OR te.period_id IS DISTINCT FROM tpr.id
                OR (SELECT to_jsonb(array_agg(pd.trade_date::text ORDER BY pd.trade_date))
                      FROM portfolio_performance_daily AS pd
                     WHERE pd.performance_id = tp.id)
                   IS DISTINCT FROM w.train_trade_dates
                OR (SELECT to_jsonb(array_agg(pd.trade_date::text ORDER BY pd.trade_date))
                      FROM portfolio_performance_daily AS pd
                     WHERE pd.performance_id = opf.id)
                   IS DISTINCT FROM w.test_trade_dates
                OR (SELECT to_jsonb(array_agg(rd.trade_date::text ORDER BY rd.trade_date))
                      FROM portfolio_performance_risk_daily AS rd
                     WHERE rd.risk_id = orisk.id)
                   IS DISTINCT FROM w.test_trade_dates
             ORDER BY wv.validation_id, wv.window_no
             LIMIT 1
            """
        )
    )
    if invalid_id is not None:
        raise RuntimeError(
            "cannot backfill M15.3.1 lineage for validation_id="
            f"{invalid_id}"
        )

    connection.execute(
        sa.text(
            """
            UPDATE portfolio_walk_forward_validation_report
               SET validation_policy_snapshot = jsonb_build_object(
                       'version', 'walk_forward_validation_policy_v0',
                       'legacy_walk_forward_config_hash', walk_forward_config_hash
                   ),
                   validation_policy_hash = walk_forward_config_hash
            """
        )
    )
    connection.execute(
        sa.text(
            """
            WITH switches AS (
                SELECT validation_id,
                       count(*) - 1 AS transition_count,
                       count(*) FILTER (
                           WHERE previous_hash IS NOT NULL
                             AND selected_parameter_hash <> previous_hash
                       ) AS switch_count
                  FROM (
                      SELECT validation_id, selected_parameter_hash,
                             lag(selected_parameter_hash) OVER (
                                 PARTITION BY validation_id ORDER BY window_no
                             ) AS previous_hash
                        FROM portfolio_walk_forward_window_validation
                  ) AS ordered
                 GROUP BY validation_id
            )
            UPDATE portfolio_walk_forward_validation_report AS report
               SET transition_count = switches.transition_count,
                   switch_count = switches.switch_count,
                   switch_rate = CASE WHEN switches.transition_count = 0 THEN NULL
                       ELSE switches.switch_count::numeric
                            / switches.transition_count END
              FROM switches
             WHERE switches.validation_id = report.id
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE portfolio_walk_forward_window_validation AS wv
               SET selected_train_run_id = t.run_id,
                   train_performance_id = te.performance_id,
                   train_risk_id = te.risk_id,
                   train_trade_id = te.trade_id,
                   train_period_id = te.period_id,
                   train_date_hash = w.train_date_hash,
                   test_date_hash = w.test_date_hash,
                   identity_snapshot = jsonb_build_object(
                       'schema_version', 'walk_forward_window_validation_identity_v1',
                       'window_no', wv.window_no,
                       'train', jsonb_build_object(
                           'dates', jsonb_build_object(
                               'hash', w.train_date_hash,
                               'count', w.train_trade_days
                           ),
                           'experiment', jsonb_build_object(
                               'id', e.id::text,
                               'definition_hash', e.definition_hash
                           ),
                           'evaluation', jsonb_build_object(
                               'id', er.id::text,
                               'policy_hash', er.policy_hash,
                               'source_hash', er.source_hash
                           ),
                           'selection', jsonb_build_object(
                               'trial_id', t.id::text,
                               'run_id', t.run_id::text,
                               'parameter_hash', t.parameter_hash,
                               'portfolio_config_hash', t.portfolio_config_hash
                           ),
                           'm14', jsonb_build_object(
                               'performance', jsonb_build_object(
                                   'id', tp.id::text,
                                   'version', tp.performance_version,
                                   'config_hash', tp.performance_config_hash,
                                   'source_hash', tp.source_hash
                               ),
                               'risk', jsonb_build_object(
                                   'id', tr.id::text,
                                   'version', tr.risk_version,
                                   'config_hash', tr.risk_config_hash,
                                   'source_hash', tr.risk_source_hash,
                                   'benchmark_source_hash', tr.benchmark_source_hash
                               ),
                               'trade', jsonb_build_object(
                                   'id', tt.id::text,
                                   'version', tt.trade_version,
                                   'config_hash', tt.trade_config_hash,
                                   'source_hash', tt.trade_source_hash
                               ),
                               'period', jsonb_build_object(
                                   'id', tpr.id::text,
                                   'version', tpr.period_version,
                                   'config_hash', tpr.period_config_hash,
                                   'source_hash', tpr.period_source_hash
                               )
                           )
                       ),
                       'oos', jsonb_build_object(
                           'dates', jsonb_build_object(
                               'hash', w.test_date_hash,
                               'count', w.test_trade_days
                           ),
                           'run', jsonb_build_object(
                               'id', orun.id::text,
                               'start_date', orun.start_date::text,
                               'end_date', orun.end_date::text,
                               'portfolio_config_hash', orun.portfolio_config_hash,
                               'source_strategy_config_hash',
                                   orun.source_strategy_config_hash,
                               'opportunity_config_hash',
                                   orun.opportunity_config_hash,
                               'execution_config_hash', orun.execution_config_hash,
                               'accounting_config_hash', orun.accounting_config_hash
                           ),
                           'm14', jsonb_build_object(
                               'performance', jsonb_build_object(
                                   'id', opf.id::text,
                                   'version', opf.performance_version,
                                   'config_hash', opf.performance_config_hash,
                                   'source_hash', opf.source_hash
                               ),
                               'risk', jsonb_build_object(
                                   'id', orisk.id::text,
                                   'version', orisk.risk_version,
                                   'config_hash', orisk.risk_config_hash,
                                   'source_hash', orisk.risk_source_hash,
                                   'benchmark_source_hash',
                                       orisk.benchmark_source_hash
                               ),
                               'trade', jsonb_build_object(
                                   'id', otrade.id::text,
                                   'version', otrade.trade_version,
                                   'config_hash', otrade.trade_config_hash,
                                   'source_hash', otrade.trade_source_hash
                               ),
                               'period', jsonb_build_object(
                                   'id', operiod.id::text,
                                   'version', operiod.period_version,
                                   'config_hash', operiod.period_config_hash,
                                   'source_hash', operiod.period_source_hash
                               )
                           )
                       )
                   )
              FROM portfolio_walk_forward_window AS w,
                   portfolio_experiment AS e,
                   portfolio_experiment_evaluation_report AS er,
                   portfolio_experiment_trial AS t,
                   portfolio_experiment_trial_evaluation AS te,
                   portfolio_performance_report AS tp,
                   portfolio_performance_risk_report AS tr,
                   portfolio_performance_trade_report AS tt,
                   portfolio_performance_period_report AS tpr,
                   portfolio_backtest_run AS orun,
                   portfolio_performance_report AS opf,
                   portfolio_performance_risk_report AS orisk,
                   portfolio_performance_trade_report AS otrade,
                   portfolio_performance_period_report AS operiod
             WHERE w.study_id = wv.study_id AND w.window_no = wv.window_no
               AND e.id = wv.train_experiment_id
               AND er.id = wv.train_evaluation_id
               AND t.id = wv.selected_trial_id
               AND te.evaluation_id = er.id AND te.trial_id = t.id
               AND tp.id = te.performance_id
               AND tr.id = te.risk_id AND tt.id = te.trade_id
               AND tpr.id = te.period_id
               AND orun.id = wv.oos_run_id
               AND opf.id = wv.oos_performance_id
               AND orisk.id = wv.oos_risk_id
               AND otrade.id = wv.oos_trade_id
               AND operiod.id = wv.oos_period_id
            """
        )
    )
    connection.execute(
        sa.text(
            """
            WITH values_by_window AS (
                SELECT ps.validation_id, ps.parameter_name, wv.window_no,
                       ((wv.selected_parameter_values ->> ps.parameter_name)::numeric)::text
                           AS parameter_value,
                       lag(((wv.selected_parameter_values ->> ps.parameter_name)::numeric)::text)
                           OVER (PARTITION BY ps.validation_id, ps.parameter_name
                                 ORDER BY wv.window_no) AS previous_value
                  FROM portfolio_walk_forward_parameter_stability AS ps
                  JOIN portfolio_walk_forward_window_validation AS wv
                    ON wv.validation_id = ps.validation_id
                 GROUP BY ps.validation_id, ps.parameter_name, wv.window_no,
                          wv.selected_parameter_values
            ), switches AS (
                SELECT validation_id, parameter_name,
                       count(*) - 1 AS transition_count,
                       count(*) FILTER (
                           WHERE previous_value IS NOT NULL
                             AND parameter_value <> previous_value
                       ) AS switch_count
                  FROM values_by_window
                 GROUP BY validation_id, parameter_name
            )
            UPDATE portfolio_walk_forward_parameter_stability AS ps
               SET transition_count = switches.transition_count,
                   adjacent_value_switch_count = switches.switch_count,
                   adjacent_value_switch_rate = CASE
                       WHEN switches.transition_count = 0 THEN NULL
                       ELSE switches.switch_count::numeric
                            / switches.transition_count END
              FROM switches
             WHERE switches.validation_id = ps.validation_id
               AND switches.parameter_name = ps.parameter_name
            """
        )
    )

    for table, columns in (
        (
            REPORT,
            (
                "validation_policy_snapshot",
                "validation_policy_hash",
                "transition_count",
                "switch_count",
            ),
        ),
        (
            WINDOW,
            (
                "selected_train_run_id",
                "train_performance_id",
                "train_risk_id",
                "train_trade_id",
                "train_period_id",
                "train_date_hash",
                "test_date_hash",
                "identity_snapshot",
            ),
        ),
        (STABILITY, ("transition_count", "adjacent_value_switch_count")),
    ):
        for column in columns:
            op.alter_column(table, column, nullable=False)

    op.create_check_constraint(
        op.f("ck_walk_forward_validation_policy_identity"),
        REPORT,
        "validation_policy_hash = walk_forward_config_hash",
    )
    op.create_check_constraint(
        op.f("ck_walk_forward_validation_switches"),
        REPORT,
        "transition_count = GREATEST(window_count - 1, 0) AND "
        "switch_count >= 0 AND switch_count <= transition_count AND "
        "((transition_count = 0 AND switch_rate IS NULL) OR "
        "(transition_count > 0 AND switch_rate >= 0 AND switch_rate <= 1))",
    )
    op.create_check_constraint(
        op.f("ck_walk_forward_window_validation_identity_schema"),
        WINDOW,
        "jsonb_typeof(identity_snapshot) = 'object' AND "
        "identity_snapshot->>'schema_version' = "
        "'walk_forward_window_validation_identity_v1' AND "
        "jsonb_typeof(identity_snapshot->'train') = 'object' AND "
        "jsonb_typeof(identity_snapshot->'oos') = 'object'",
    )
    op.create_check_constraint(
        op.f("ck_walk_forward_parameter_stability_switches"),
        STABILITY,
        "transition_count >= 0 AND adjacent_value_switch_count >= 0 AND "
        "adjacent_value_switch_count <= transition_count AND "
        "((transition_count = 0 AND adjacent_value_switch_rate IS NULL) OR "
        "(transition_count > 0 AND adjacent_value_switch_rate >= 0 AND "
        "adjacent_value_switch_rate <= 1))",
    )

    _create_lineage_foreign_keys()
    connection.execute(
        sa.text(
            """
            CREATE FUNCTION reject_walk_forward_validation_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION '% is append-only', TG_TABLE_NAME
                    USING ERRCODE = '55000';
            END;
            $$
            """
        )
    )
    for table in (REPORT, WINDOW, STABILITY):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only "
            f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION reject_walk_forward_validation_mutation()"
        )


def _create_lineage_foreign_keys() -> None:
    op.create_foreign_key(
        "fk_walk_forward_window_result_train_evaluation",
        WINDOW,
        "portfolio_experiment_evaluation_report",
        ["train_evaluation_id", "train_experiment_id"],
        ["id", "experiment_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_walk_forward_window_result_selected_trial",
        WINDOW,
        "portfolio_experiment_trial",
        ["selected_trial_id", "train_experiment_id"],
        ["id", "experiment_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_walk_forward_window_result_trial_evaluation",
        WINDOW,
        "portfolio_experiment_trial_evaluation",
        ["train_evaluation_id", "selected_trial_id"],
        ["evaluation_id", "trial_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_walk_forward_window_result_train_run",
        WINDOW,
        "portfolio_experiment_trial",
        ["selected_trial_id", "selected_train_run_id"],
        ["id", "run_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_walk_forward_window_result_train_performance",
        WINDOW,
        "portfolio_performance_report",
        ["train_performance_id", "selected_train_run_id"],
        ["id", "run_id"],
        ondelete="RESTRICT",
    )
    for name, local, remote_table, remote in (
        (
            "fk_walk_forward_window_result_train_risk",
            ["train_risk_id", "train_performance_id", "selected_train_run_id"],
            "portfolio_performance_risk_report",
            ["id", "performance_id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_train_trade",
            ["train_trade_id", "train_performance_id", "selected_train_run_id"],
            "portfolio_performance_trade_report",
            ["id", "performance_id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_train_period",
            [
                "train_period_id",
                "train_performance_id",
                "train_risk_id",
                "train_trade_id",
                "selected_train_run_id",
            ],
            "portfolio_performance_period_report",
            ["id", "performance_id", "risk_id", "trade_id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_oos_performance",
            ["oos_performance_id", "oos_run_id"],
            "portfolio_performance_report",
            ["id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_oos_risk",
            ["oos_risk_id", "oos_performance_id", "oos_run_id"],
            "portfolio_performance_risk_report",
            ["id", "performance_id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_oos_trade",
            ["oos_trade_id", "oos_performance_id", "oos_run_id"],
            "portfolio_performance_trade_report",
            ["id", "performance_id", "run_id"],
        ),
        (
            "fk_walk_forward_window_result_oos_period",
            [
                "oos_period_id",
                "oos_performance_id",
                "oos_risk_id",
                "oos_trade_id",
                "oos_run_id",
            ],
            "portfolio_performance_period_report",
            ["id", "performance_id", "risk_id", "trade_id", "run_id"],
        ),
    ):
        op.create_foreign_key(
            name, WINDOW, remote_table, local, remote, ondelete="RESTRICT"
        )


def downgrade() -> None:
    connection = op.get_bind()
    count = int(
        connection.scalar(sa.text(f"SELECT count(*) FROM {REPORT}")) or 0
    )
    if count:
        raise RuntimeError(
            "cannot downgrade M15.3.1 while validation artifacts require "
            f"immutable lineage (count={count})"
        )

    for table in (REPORT, WINDOW, STABILITY):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_walk_forward_validation_mutation()")

    for name in (
        "fk_walk_forward_window_result_oos_period",
        "fk_walk_forward_window_result_oos_trade",
        "fk_walk_forward_window_result_oos_risk",
        "fk_walk_forward_window_result_oos_performance",
        "fk_walk_forward_window_result_train_period",
        "fk_walk_forward_window_result_train_trade",
        "fk_walk_forward_window_result_train_risk",
        "fk_walk_forward_window_result_train_performance",
        "fk_walk_forward_window_result_train_run",
        "fk_walk_forward_window_result_trial_evaluation",
        "fk_walk_forward_window_result_selected_trial",
        "fk_walk_forward_window_result_train_evaluation",
    ):
        op.drop_constraint(name, WINDOW, type_="foreignkey")
    op.drop_constraint(
        op.f("ck_walk_forward_parameter_stability_switches"),
        STABILITY,
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_walk_forward_window_validation_identity_schema"),
        WINDOW,
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_walk_forward_validation_switches"), REPORT, type_="check"
    )
    op.drop_constraint(
        op.f("ck_walk_forward_validation_policy_identity"),
        REPORT,
        type_="check",
    )

    for name in (
        "identity_snapshot",
        "test_date_hash",
        "train_date_hash",
        "train_period_id",
        "train_trade_id",
        "train_risk_id",
        "train_performance_id",
        "selected_train_run_id",
    ):
        op.drop_column(WINDOW, name)
    for name in (
        "adjacent_value_switch_rate",
        "adjacent_value_switch_count",
        "transition_count",
    ):
        op.drop_column(STABILITY, name)
    for name in (
        "switch_rate",
        "switch_count",
        "transition_count",
        "validation_policy_hash",
        "validation_policy_snapshot",
    ):
        op.drop_column(REPORT, name)
    op.drop_constraint(
        "uq_portfolio_experiment_trial_run_owner",
        "portfolio_experiment_trial",
        type_="unique",
    )
