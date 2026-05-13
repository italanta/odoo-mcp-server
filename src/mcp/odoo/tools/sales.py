"""Sales & Pre-Sales domain tools.

CRM pipeline management, lead enrichment, contact search, and solution design tracking.
Designed for the salesperson/solution designer who wears both hats.
"""

import html
import json
from datetime import datetime, timedelta
from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.mcp.odoo.utils.client import OdooClient

# ── Shared ──

# Re-used by projects and other domains; defined here as original home.
from src.mcp.odoo.tools._shared import ResponseFormat

# ── Pydantic Input Models ──


class SearchOpportunitiesInput(BaseModel):
    """Search CRM opportunities with flexible filters."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: Optional[str] = Field(default=None, description="Free text search across opportunity name, contact, and notes")
    stage: Optional[str] = Field(default=None, description="Filter by stage name (e.g. 'Qualified', 'Proposition', 'Negotiation')")
    tag: Optional[str] = Field(default=None, description="Filter by tag (e.g. 'iTalanta', 'GIZ Trade Fair')")
    salesperson: Optional[str] = Field(default=None, description="Filter by salesperson name")
    company_id: Optional[int] = Field(default=None, description="Filter by Odoo company ID (multi-company)")
    stale_days: Optional[int] = Field(default=None, description="Find opportunities with no activity in N+ days", ge=1)
    limit: int = Field(default=20, description="Max results", ge=1, le=100)
    offset: int = Field(default=0, description="Pagination offset", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetOpportunityInput(BaseModel):
    """Get full details for a specific opportunity."""

    model_config = ConfigDict(extra="forbid")

    opportunity_id: int = Field(..., description="Odoo CRM opportunity ID", ge=1)
    include_messages: bool = Field(default=True, description="Include chatter messages/log notes")
    include_activities: bool = Field(default=True, description="Include scheduled activities")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ProposeStageChangeInput(BaseModel):
    """Propose moving an opportunity to a different pipeline stage."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    opportunity_id: int = Field(..., description="Odoo CRM opportunity ID", ge=1)
    new_stage: str = Field(..., description="Target stage name (e.g. 'Qualified', 'Proposition', 'Won')", min_length=1)
    reason: str = Field(..., description="Why this stage change is being proposed (based on email/communication evidence)", min_length=10)


class ProposeLogNoteInput(BaseModel):
    """Propose adding an internal log note to an opportunity."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    opportunity_id: int = Field(..., description="Odoo CRM opportunity ID", ge=1)
    note: str = Field(..., description="Internal note content (plain text or HTML). Never sent externally.", min_length=5)
    source: str = Field(default="email_scan", description="What triggered this note (e.g. 'email_scan', 'meeting_debrief', 'manual')")


class ProposeActivityInput(BaseModel):
    """Propose scheduling a follow-up activity on an opportunity."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    opportunity_id: int = Field(..., description="Odoo CRM opportunity ID", ge=1)
    summary: str = Field(..., description="Short description of the activity", min_length=3, max_length=200)
    date_deadline: str = Field(..., description="Due date in YYYY-MM-DD format")
    activity_type: str = Field(default="todo", description="Type: 'todo', 'call', or 'meeting' (meeting = internal only, no invites)")
    note: str = Field(default="", description="Optional longer description")

    @field_validator("date_deadline")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD.")
        return v


class ProposeFieldUpdateInput(BaseModel):
    """Propose updating fields on an opportunity (revenue, closing date, name, etc.)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    opportunity_id: int = Field(..., description="Odoo CRM opportunity ID", ge=1)
    updates: dict = Field(
        ...,
        description=(
            "Dictionary of field:value pairs to update. "
            "Safe fields: name, expected_revenue, date_deadline, description, priority, tag_ids. "
            "Example: {'expected_revenue': 50000, 'date_deadline': '2026-06-30'}"
        ),
    )
    reason: str = Field(..., description="Why these updates are proposed", min_length=10)


class SearchContactsInput(BaseModel):
    """Search contacts/companies in Odoo."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Search by name, email, or company name", min_length=2)
    is_company: Optional[bool] = Field(default=None, description="True for companies only, False for individuals only")
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetPipelineSummaryInput(BaseModel):
    """Get a summary of the entire pipeline or a specific stage."""

    model_config = ConfigDict(extra="forbid")

    company_id: Optional[int] = Field(default=None, description="Filter by company ID")
    stage: Optional[str] = Field(default=None, description="Focus on a specific stage")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ── Safe field allowlist for updates ──

SAFE_OPPORTUNITY_FIELDS = frozenset({
    "name",
    "expected_revenue",
    "date_deadline",
    "description",
    "priority",
    "tag_ids",
    "referred",
    "date_closed",
    "probability",
})


# ── Registration ──


def register(mcp: FastMCP, get_odoo: Any) -> None:
    """Register all sales & pre-sales tools on the shared MCP server.

    Args:
        mcp: The FastMCP server instance.
        get_odoo: Callable(ctx) -> OdooClient to extract the shared client from context.
    """

    @mcp.tool(
        name="odoo_search_opportunities",
        annotations={
            "title": "Search CRM Opportunities",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_opportunities(params: SearchOpportunitiesInput, ctx: Context) -> str:
        """Search Odoo CRM opportunities with flexible filters.

        Searches across opportunity names, contacts, stages, and tags.
        Supports finding stale deals (no activity in N days).
        Multi-company aware.

        Returns a list of matching opportunities with key details:
        name, stage, expected revenue, closing date, salesperson, tags, and last activity.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        domain: list = [("type", "=", "opportunity")]

        if params.query:
            domain.append("|")
            domain.append(("name", "ilike", params.query))
            domain.append(("partner_id.name", "ilike", params.query))

        if params.stage:
            domain.append(("stage_id.name", "ilike", params.stage))

        if params.tag:
            domain.append(("tag_ids.name", "ilike", params.tag))

        if params.salesperson:
            domain.append(("user_id.name", "ilike", params.salesperson))

        if params.company_id:
            domain.append(("company_id", "=", params.company_id))

        if params.stale_days:
            cutoff = (datetime.now() - timedelta(days=params.stale_days)).strftime("%Y-%m-%d %H:%M:%S")
            domain.append(("write_date", "<=", cutoff))

        fields = [
            "name", "stage_id", "partner_id", "expected_revenue", "date_deadline",
            "user_id", "tag_ids", "priority", "probability", "activity_date_deadline",
            "create_date", "write_date", "company_id",
        ]

        results = await odoo.search_read(
            "crm.lead", domain, fields,
            limit=params.limit, offset=params.offset, order="write_date desc",
        )
        total = await odoo.search_count("crm.lead", domain)

        if not results:
            return "No opportunities found matching your criteria."

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"total": total, "count": len(results), "opportunities": results}, indent=2, default=str)

        lines = [f"# CRM Opportunities ({len(results)} of {total})", ""]
        for opp in results:
            stage = opp["stage_id"][1] if opp.get("stage_id") else "No stage"
            partner = opp["partner_id"][1] if opp.get("partner_id") else "No contact"
            revenue = f"{opp.get('expected_revenue', 0):,.0f} KSh" if opp.get("expected_revenue") else "No revenue set"
            closing = opp.get("date_deadline", "No closing date")
            salesperson = opp["user_id"][1] if opp.get("user_id") else "Unassigned"
            tags = ", ".join(t[1] if isinstance(t, list) else str(t) for t in (opp.get("tag_ids") or []))
            priority_map = {"0": "", "1": " *", "2": " **", "3": " ***"}
            priority = priority_map.get(str(opp.get("priority", "0")), "")

            lines.append(f"## {opp['name']}{priority} (ID: {opp['id']})")
            lines.append(f"- **Stage:** {stage}")
            lines.append(f"- **Contact:** {partner}")
            lines.append(f"- **Revenue:** {revenue}")
            lines.append(f"- **Closing:** {closing}")
            lines.append(f"- **Salesperson:** {salesperson}")
            if tags:
                lines.append(f"- **Tags:** {tags}")
            lines.append(f"- **Last updated:** {opp.get('write_date', 'unknown')}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool(
        name="odoo_get_opportunity",
        annotations={
            "title": "Get Opportunity Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_opportunity(params: GetOpportunityInput, ctx: Context) -> str:
        """Get full details for a specific CRM opportunity including chatter history and activities.

        Returns complete opportunity data: all fields, log notes, messages, and scheduled activities.
        Use this to understand the full context of a deal before proposing updates.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        fields = [
            "name", "stage_id", "partner_id", "partner_name", "contact_name",
            "email_from", "phone", "expected_revenue", "date_deadline", "date_open",
            "date_closed", "user_id", "team_id", "tag_ids", "priority", "probability",
            "description", "referred", "company_id", "create_date", "write_date",
            "activity_ids", "activity_date_deadline", "activity_summary",
            "type", "lost_reason_id",
        ]

        records = await odoo.read("crm.lead", [params.opportunity_id], fields)
        if not records:
            return f"Error: Opportunity ID {params.opportunity_id} not found."

        opp = records[0]

        messages = []
        if params.include_messages:
            messages = await odoo.search_read(
                "mail.message",
                [("res_id", "=", params.opportunity_id), ("model", "=", "crm.lead")],
                ["body", "date", "author_id", "message_type", "subtype_id"],
                limit=20, order="date desc",
            )

        activities = []
        if params.include_activities and opp.get("activity_ids"):
            activities = await odoo.read(
                "mail.activity", opp["activity_ids"],
                ["summary", "date_deadline", "activity_type_id", "user_id", "note", "state"],
            )

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"opportunity": opp, "messages": messages, "activities": activities}, indent=2, default=str)

        stage = opp["stage_id"][1] if opp.get("stage_id") else "No stage"
        partner = opp["partner_id"][1] if opp.get("partner_id") else "No contact"

        lines = [
            f"# {opp['name']} (ID: {opp['id']})",
            "",
            f"**Stage:** {stage} | **Probability:** {opp.get('probability', 0)}%",
            f"**Contact:** {partner} ({opp.get('email_from', 'no email')})",
            f"**Revenue:** {opp.get('expected_revenue', 0):,.0f} KSh",
            f"**Expected close:** {opp.get('date_deadline', 'not set')}",
            f"**Salesperson:** {opp['user_id'][1] if opp.get('user_id') else 'Unassigned'}",
            f"**Created:** {opp.get('create_date')} | **Last updated:** {opp.get('write_date')}",
        ]

        if opp.get("description"):
            lines.extend(["", "## Internal Notes", opp["description"]])

        if activities:
            lines.extend(["", "## Scheduled Activities"])
            for act in activities:
                atype = act["activity_type_id"][1] if act.get("activity_type_id") else "Activity"
                user = act["user_id"][1] if act.get("user_id") else "Unassigned"
                lines.append(f"- **{atype}:** {act.get('summary', 'No summary')} (due: {act.get('date_deadline')}, assigned: {user})")

        if messages:
            lines.extend(["", "## Recent Chatter (last 20)"])
            for msg in messages:
                author = msg["author_id"][1] if msg.get("author_id") else "System"
                mtype = msg.get("message_type", "")
                body = msg.get("body", "").replace("<p>", "").replace("</p>", "").strip()
                if body:
                    lines.append(f"- **{author}** ({msg.get('date')}) [{mtype}]: {body[:200]}")

        return "\n".join(lines)

    @mcp.tool(
        name="odoo_propose_stage_change",
        annotations={
            "title": "Propose Stage Change",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def propose_stage_change(params: ProposeStageChangeInput, ctx: Context) -> str:
        """Propose moving a CRM opportunity to a different pipeline stage.

        IMPORTANT: This executes the stage change. It should only be called after
        the human has reviewed and approved the proposal.

        The stage change is safe — it updates a field and logs an internal note.
        No emails are sent.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo

        stages = await odoo.search_read(
            "crm.stage", [("name", "ilike", params.new_stage)], ["name", "id"], limit=5,
        )
        if not stages:
            return f"Error: Stage '{params.new_stage}' not found. Available stages can be found with odoo_get_pipeline_summary."

        if len(stages) > 1:
            stage_names = ", ".join(f"'{s['name']}' (ID: {s['id']})" for s in stages)
            return f"Multiple stages match '{params.new_stage}': {stage_names}. Please be more specific."

        target_stage = stages[0]

        await odoo.write("crm.lead", [params.opportunity_id], {"stage_id": target_stage["id"]})

        note_body = (
            f"<p><strong>AI-proposed stage change</strong></p>"
            f"<p>Moved to <strong>{html.escape(target_stage['name'])}</strong></p>"
            f"<p><em>Reason:</em> {html.escape(params.reason)}</p>"
        )
        await odoo.log_note("crm.lead", params.opportunity_id, note_body)

        return f"Stage changed to '{target_stage['name']}' for opportunity {params.opportunity_id}. Internal note logged with reason."

    @mcp.tool(
        name="odoo_propose_log_note",
        annotations={
            "title": "Add Internal Log Note",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def propose_log_note(params: ProposeLogNoteInput, ctx: Context) -> str:
        """Add an internal log note to a CRM opportunity.

        SAFE: Log notes (message_type='note') are purely internal.
        They appear in the chatter but NEVER send emails to anyone.

        Use this for recording email scan findings, meeting debriefs,
        deal analysis, and any AI-generated context.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        body = f"<p><strong>[{html.escape(params.source)}]</strong></p>{params.note}"
        msg_id = await odoo.log_note("crm.lead", params.opportunity_id, body)
        return f"Internal note posted on opportunity {params.opportunity_id} (message ID: {msg_id}). No external notification sent."

    @mcp.tool(
        name="odoo_propose_activity",
        annotations={
            "title": "Schedule Follow-up Activity",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def propose_activity(params: ProposeActivityInput, ctx: Context) -> str:
        """Schedule a follow-up activity (to-do, call, or meeting reminder) on an opportunity.

        SAFE: Activities are internal reminders that appear in the user's Odoo
        activity feed. They do NOT send emails or calendar invitations.

        Note: 'meeting' here means an internal reminder to schedule a meeting,
        NOT a calendar event with attendees. Calendar invites require separate
        express approval.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        type_map = {"todo": 4, "call": 2, "meeting": 3}
        activity_type_id = type_map.get(params.activity_type, 4)

        act_id = await odoo.schedule_activity(
            "crm.lead",
            params.opportunity_id,
            summary=params.summary,
            date_deadline=params.date_deadline,
            activity_type_id=activity_type_id,
            note=params.note,
        )
        return f"Activity '{params.summary}' scheduled for {params.date_deadline} on opportunity {params.opportunity_id} (activity ID: {act_id})."

    @mcp.tool(
        name="odoo_propose_field_update",
        annotations={
            "title": "Update Opportunity Fields",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def propose_field_update(params: ProposeFieldUpdateInput, ctx: Context) -> str:
        """Update fields on a CRM opportunity (revenue, closing date, name, etc.).

        Only safe fields are allowed — see SAFE_OPPORTUNITY_FIELDS.
        Stage changes go through odoo_propose_stage_change instead.

        IMPORTANT: This executes the update. Call only after human approval.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        unsafe = set(params.updates.keys()) - SAFE_OPPORTUNITY_FIELDS
        if unsafe:
            return f"Error: Cannot update these fields via AI: {', '.join(unsafe)}. Safe fields: {', '.join(sorted(SAFE_OPPORTUNITY_FIELDS))}"

        await odoo.write("crm.lead", [params.opportunity_id], params.updates)

        changes = ", ".join(f"{k}={v}" for k, v in params.updates.items())
        note_body = (
            f"<p><strong>AI-proposed field update</strong></p>"
            f"<p>Updated: {html.escape(changes)}</p>"
            f"<p><em>Reason:</em> {html.escape(params.reason)}</p>"
        )
        await odoo.log_note("crm.lead", params.opportunity_id, note_body)

        return f"Updated {len(params.updates)} field(s) on opportunity {params.opportunity_id}: {changes}. Internal note logged."

    @mcp.tool(
        name="odoo_search_contacts",
        annotations={
            "title": "Search Contacts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_contacts(params: SearchContactsInput, ctx: Context) -> str:
        """Search for contacts and companies in Odoo.

        Searches across name, email, phone, and company name.
        Use to find existing contacts before proposing CRM updates.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        domain: list = [
            "|", "|", "|",
            ("name", "ilike", params.query),
            ("email", "ilike", params.query),
            ("phone", "ilike", params.query),
            ("parent_id.name", "ilike", params.query),
        ]

        if params.is_company is not None:
            domain.append(("is_company", "=", params.is_company))

        fields = ["name", "email", "phone", "is_company", "parent_id", "city", "country_id", "function"]
        results = await odoo.search_read("res.partner", domain, fields, limit=params.limit)

        if not results:
            return f"No contacts found matching '{params.query}'."

        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"contacts": results}, indent=2, default=str)

        lines = [f"# Contacts matching '{params.query}' ({len(results)} results)", ""]
        for c in results:
            ctype = "Company" if c.get("is_company") else "Person"
            company = f" @ {c['parent_id'][1]}" if c.get("parent_id") else ""
            lines.append(f"- **{c['name']}** ({ctype}{company}) — {c.get('email', 'no email')} | {c.get('function', '')}")

        return "\n".join(lines)

    @mcp.tool(
        name="odoo_get_pipeline_summary",
        annotations={
            "title": "Pipeline Summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_pipeline_summary(params: GetPipelineSummaryInput, ctx: Context) -> str:
        """Get a summary of the CRM pipeline: stages, deal counts, and total revenue.

        Useful for understanding the current state of the pipeline and finding
        stale or stuck deals. Multi-company aware.
        """
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        stages = await odoo.search_read("crm.stage", [], ["name", "sequence"], order="sequence asc")

        lines = ["# CRM Pipeline Summary", ""]

        for stage in stages:
            domain: list = [("type", "=", "opportunity"), ("stage_id", "=", stage["id"])]
            if params.company_id:
                domain.append(("company_id", "=", params.company_id))

            opps = await odoo.search_read(
                "crm.lead", domain,
                ["name", "expected_revenue", "write_date", "partner_id"],
                order="expected_revenue desc", limit=100,
            )

            total_revenue = sum(o.get("expected_revenue", 0) for o in opps)
            lines.append(f"## {stage['name']} — {len(opps)} deals | {total_revenue:,.0f} KSh")

            if params.stage and params.stage.lower() in stage["name"].lower():
                for o in opps:
                    partner = o["partner_id"][1] if o.get("partner_id") else "No contact"
                    rev = f"{o.get('expected_revenue', 0):,.0f} KSh"
                    lines.append(f"  - {o['name']} ({partner}) — {rev} — last updated: {o.get('write_date')}")

            lines.append("")

        return "\n".join(lines)
