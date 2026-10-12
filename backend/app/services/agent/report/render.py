from __future__ import annotations

import html

from app.domain.agent.report import ResearchReportSnapshot


def render_markdown(snapshot: ResearchReportSnapshot, snapshot_hash: str) -> str:
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


def render_html(snapshot: ResearchReportSnapshot, snapshot_hash: str) -> str:
    markdown = render_markdown(snapshot, snapshot_hash)
    blocks: list[str] = []
    in_list = False
    for line in markdown.splitlines():
        escaped = html.escape(line)
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
    body = "\n".join(blocks)
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(snapshot.title)}</title></head><body>{body}</body></html>\n"
    )
