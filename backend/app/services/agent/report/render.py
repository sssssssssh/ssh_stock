from __future__ import annotations

import html
import json

from app.domain.agent.report import ResearchReportSnapshot


def render_markdown(snapshot: ResearchReportSnapshot, snapshot_hash: str, contracts=None) -> str:
    lines = [
        f"# {snapshot.title}",
        "",
        f"- 报告类型：`{snapshot.report_type}`",
        f"- 截止日期：`{snapshot.as_of_date.isoformat() if snapshot.as_of_date else '未提供'}`",
        f"- 来源状态：`{snapshot.source_answer_status}`",
        f"- 快照级别：`{snapshot.snapshot_level}`",
        f"- 快照哈希：`{snapshot_hash}`",
        "",
    ]
    if snapshot.archive_reference is not None:
        ref = snapshot.archive_reference
        lines.extend(
            [
                f"- 归档状态：`{ref.archive_status}`",
                f"- 归档 Manifest：`{ref.manifest_id}` · `{ref.manifest_hash}`",
                f"- 复核等级：`{ref.reproduction_level}`（不是原算法重跑）",
                "",
            ]
        )
    if snapshot.contract_reference is not None:
        ref = snapshot.contract_reference
        lines.extend(
            [
                f"- 合同 Manifest：`{ref.manifest_id}` · `{ref.manifest_hash}`",
                f"- 合同政策：`{ref.policy_version}` · `{ref.reproduction_level}`",
                f"- 冻结范围：`{', '.join(ref.contract_scope) or '无完整合同'}`",
                f"- 合同缺口：`{', '.join(ref.gap_codes) or '无'}`",
                "- 算法重跑：否",
                "",
            ]
        )
        for item in contracts or []:
            metadata = item["metadata"]
            lines.extend(
                [
                    f"## 冻结合同 {metadata['role']} · {metadata['contract_kind']}",
                    "",
                    f"- 合同 ID：`{metadata['contract_id']}`",
                    f"- 合同 Hash：`{metadata['contract_hash']}`",
                    f"- 来源：`{metadata['subject_id']}` · `{metadata['schema_version']}`",
                    f"- 核验：`{metadata['status']}`",
                    "",
                    "```json",
                    json.dumps(item["projection"], ensure_ascii=False, sort_keys=True, indent=2),
                    "```",
                    "",
                ]
            )
    claims = {claim.claim_id: claim for claim in snapshot.claims}
    for section in snapshot.sections:
        lines.extend([f"## {section.title}", ""])
        lines.extend(f"- {item}" for item in section.items)
        for claim_id in section.claim_ids:
            claim = claims.get(claim_id)
            if claim is not None:
                refs = ", ".join(f"`{item}`" for item in claim.evidence_ids)
                lines.append(f"- {claim.text}（证据：{refs}）")
        lines.append("")
    lines.extend(["## 证据索引", ""])
    for citation in snapshot.citations:
        lines.append(
            f"- `{citation.evidence_id}` · `{citation.tool_name}` · "
            f"`{citation.entity_id}` · `{citation.as_of_date or '日期未提供'}`"
        )
    if snapshot.rejected_claims:
        lines.extend(["", "## 未纳入的主张", ""])
        for claim in snapshot.rejected_claims:
            lines.append(f"- `{claim.claim_id}`：{', '.join(claim.reason_codes)}")
    lines.extend(["", "## 限制与警告", ""])
    lines.extend(f"- `{warning}`" for warning in snapshot.warnings)
    return "\n".join(lines).rstrip() + "\n"


def render_html(snapshot: ResearchReportSnapshot, snapshot_hash: str, contracts=None) -> str:
    return _markdown_html(render_markdown(snapshot, snapshot_hash, contracts), snapshot.title)


def _markdown_html(markdown: str, title: str) -> str:
    blocks: list[str] = []
    in_list = False
    in_code = False
    for line in markdown.splitlines():
        escaped = html.escape(line)
        if line.startswith("```"):
            if in_list:
                blocks.append("</ul>")
                in_list = False
            blocks.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            blocks.append(escaped)
            continue
        if line.startswith("# "):
            if in_list:
                blocks.append("</ul>")
                in_list = False
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                blocks.append("</ul>")
                in_list = False
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{html.escape(line[2:])}</li>")
        elif line:
            if in_list:
                blocks.append("</ul>")
                in_list = False
            blocks.append(f"<p>{escaped}</p>")
    if in_list:
        blocks.append("</ul>")
    if in_code:
        blocks.append("</code></pre>")
    body = "\n".join(blocks)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title></head><body>{body}</body></html>\n"
    )


def render_comparison(view, export_format):
    data = view.display_result or {}
    allowed = (
        view.state == "COMPARABLE"
        and view.policy_version in {"m16.5-report-comparison-v3", "m16.6-report-comparison-v4"}
        and view.display_safety is not None
        and view.display_safety.get("legacy_policy") is False
        and view.display_safety.get("delta_allowed") is True
    )
    lines = [
        "# 研究报告比较",
        "",
        f"- 政策：`{view.policy_version}`",
        f"- 判定：`{view.state}`",
        f"- 左报告：`{view.left_report_id}` · `{view.left_snapshot_hash}`",
        f"- 右报告：`{view.right_report_id}` · `{view.right_snapshot_hash}`",
        f"- 模式：`{data.get('comparison_mode') or data.get('comparison_intent', '历史口径')}`",
        "- 原算法未重跑；仅使用冻结证据与合同 · FROZEN_CONTRACT_RECHECK",
        "",
        "## 样本与口径",
        "",
        "```json",
        json.dumps(data.get("sample_context", {}), ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
        "## 指标事实",
        "",
    ]
    for fact in data.get("facts", []):
        lines.append(f"- `{fact['metric_key']}`：左 `{fact['left']}`；右 `{fact['right']}`")
        pair_allowed = (
            allowed
            and fact.get("pair_status") == "COMPARABLE"
            and (
                view.policy_version != "m16.6-report-comparison-v4"
                or (
                    data.get("comparison_permissions", {}).get("allowed") is True
                    and fact.get("comparison_permission", {}).get("allowed") is True
                    and fact.get("formula")
                    in {"RIGHT_MINUS_LEFT", "TRAIN_MINUS_OOS", "OOS_MINUS_TRAIN"}
                )
            )
        )
        if pair_allowed and "delta" in fact:
            unit = fact.get("left_fact", {}).get("metric_identity", {}).get("unit", "未提供")
            delta_unit = "百分点" if unit == "percent" else unit
            semantics = fact.get("delta_semantics", "RIGHT_MINUS_LEFT_SAME_UNIT")
            lines.append(
                f"  授权公式 `{fact.get('formula', 'RIGHT_MINUS_LEFT')}`：`{fact['delta']}`；"
                f"单位 `{delta_unit}`；语义 `{semantics}`"
            )
        else:
            lines.append("  未授权差值；不提供优劣排序")
        for side in ("left", "right"):
            provenance = fact.get(side + "_fact", {}).get("provenance", {})
            role = (
                fact.get(side + "_fact", {}).get("metric_identity", {}).get("sample_role", "未提供")
            )
            lines.append(
                f"  `{side}` 来源报告 `{provenance.get('report_id', '未提供')}` · 样本 `{role}`"
            )
    if data.get("explain_reasons"):
        lines.extend(
            [
                "",
                "## 口径差异",
                "",
                "```json",
                json.dumps(data["explain_reasons"], ensure_ascii=False, sort_keys=True, indent=2),
                "```",
            ]
        )
    lines.extend(["", "## 合同身份与限制", ""])
    for side, refs in data.get("contract_refs", {}).items():
        for ref in refs:
            lines.append(
                f"- `{side}` · `{ref['role']}` · `{ref['subject_id']}` · `{ref['contract_hash']}`"
            )
            if ref.get("source_ids"):
                lines.extend(
                    [
                        "```json",
                        json.dumps(ref["source_ids"], ensure_ascii=False, sort_keys=True),
                        "```",
                    ]
                )
    lines.extend(f"- `{code}`" for code in view.reason_codes)
    content = "\n".join(lines).rstrip() + "\n"
    return _markdown_html(content, "研究报告比较") if export_format == "html" else content
