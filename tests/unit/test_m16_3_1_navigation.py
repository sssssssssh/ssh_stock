import json

import pytest
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolResultContext


@pytest.mark.parametrize(
    ("tool_name", "entity", "field", "identity", "record", "expected"),
    [
        (
            "sector.top",
            "123",
            "heat_score",
            {},
            {"heat_score": 7},
            {"sector_id": "123", "view": "long"},
        ),
        (
            "opportunity.list",
            "000001.SZ",
            "score",
            {},
            {"score": 7},
            {"ts_code": "000001.SZ", "view": "long"},
        ),
        (
            "backtest.summary",
            "run-a",
            "latest_nav",
            {},
            {"latest_nav": 7},
            {"run_id": "run-a", "view": "analytics"},
        ),
        (
            "walk_forward.window_lineage",
            "study-a:window:301",
            "window_no",
            {"study_id": "study-a", "validation_id": "validation-a"},
            {"window_no": 301},
            {
                "study_id": "study-a",
                "validation_id": "validation-a",
                "window_no": 301,
                "view": "walk_forward",
            },
        ),
    ],
)
def test_navigation_is_derived_from_verified_tool_identity(
    tool_name, entity, field, identity, record, expected
) -> None:
    value = record[field]
    context = ToolResultContext(
        tool_call_id="call-1",
        tool_name=tool_name,
        payload={
            "records": [record],
            "identity": identity,
            "evidence": [
                {
                    "evidence_id": "evidence-1",
                    "evidence_version": "v2",
                    "entity_id": entity,
                    "trade_date": "2026-01-02",
                    "quality_status": "PASS",
                }
            ],
        },
    )
    compiled = EvidenceCompiler(max_answer_chars=8000).compile(
        final_text=json.dumps(
            {
                "answer": "free model text study-fake window 99",
                "claims": [
                    {
                        "claim_id": "verified",
                        "claim_type": "FACT",
                        "text": "free model text run-fake",
                        "evidence_ids": ["evidence-1"],
                        "structured_facts": [
                            {
                                "path": f"records.0.{field}",
                                "value": value,
                                "unit": "decimal"
                                if field == "window_no"
                                else "nav"
                                if field == "latest_nav"
                                else "score",
                                "trade_date": "2026-01-02",
                                "entity": entity,
                            }
                        ],
                    }
                ],
            }
        ),
        tool_results=[context],
        inherited_warnings=[],
    )
    assert compiled.answer_status == "COMPLETED"
    navigation = compiled.citations[0].navigation.model_dump(mode="json", exclude_none=True)
    assert navigation == {**expected, "trade_date": "2026-01-02", "source_tool": tool_name}
    assert "fake" not in json.dumps(navigation)
