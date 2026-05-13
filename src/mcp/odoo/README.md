# Odoo MCP Server — Operational Concepts

## What is an MCP Server?

An MCP (Model Context Protocol) server is a small program that exposes tools and resources to Claude via JSON-RPC over stdio. Claude can call these tools in a conversation, and the server responds with data or performs actions.

```
Claude (client) ←→ [stdio] ←→ Odoo MCP Server (this repo) ←→ Odoo API
```

## Credential Model: Per-User, Local

Each Claude user has their own credentials file at `~/.config/my-odoo/credentials.json` (Unix/macOS) or similar on Windows. This file is:

- Created by the user running `odoo_setup_credentials` tool (in Claude)
- Stored with mode `600` (owner-only read/write)
- Never synced, uploaded, or shared
- Encrypted at rest is the OS's responsibility (use FileVault, BitLocker, etc.)

## Human-in-the-Loop Approval

Write operations (stage changes, field updates, notes) execute immediately when called. The approval gate is **upstream** in the Claude conversation:

1. Claude proposes an action (e.g., "Move deal XYZ to Negotiation stage")
2. Human reviews and approves in the chat
3. Human says "Do it" or presses a button
4. Claude calls the MCP tool → it executes immediately

The tool itself is the execution layer **after** approval, not the approval mechanism.

## Safety Guarantees: Three Layers

### Layer 1: Code — SafetyGuard

`src/mcp/odoo/utils/safety.py` blocks dangerous Odoo models and methods:

- ❌ Models: `mail.mail`, `sms.sms`, `calendar.attendee`, mailing lists
- ❌ Methods: `action_send_mail`, `message_subscribe`, `action_send_sms`, etc.
- ❌ Message types: bare `comment`, `email`, `notification` (only `note` + subtype_id=2 or `comment` + subtype_id=2 allowed)
- ❌ Calendar events with attendees

### Layer 2: Human — Claude Conversation

Claude (and the human using Claude) decide whether to call a tool at all. Tools are proposed before execution.

### Layer 3: Odoo — Permissions

Even if Layers 1 & 2 fail, Odoo's own permissions prevent unauthorized writes.

## Key Design Decisions

### 1. Shared OdooClient via Lifespan

All tools reuse a single `OdooClient` instance created at server startup. This avoids duplicate connections and keeps state (cached model IDs) in one place.

```python
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    client = OdooClient()  # Single instance, shared by all tools
    await client.authenticate()
    yield AppContext(odoo=client)
```

### 2. Pydantic Input Validation

All tool inputs use strict Pydantic models with `extra='forbid'`:

```python
class SearchOpportunitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Optional[str] = Field(...)
    # ...
```

This prevents accidental/malicious injection of unexpected fields.

### 3. Async XML-RPC in Thread Executor

Odoo's XML-RPC is synchronous, but MCP tools are async. We use `loop.run_in_executor()` to avoid blocking the event loop:

```python
async def _execute(self, model: str, method: str, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(self._models.execute_kw, ...),
    )
```

### 4. Multi-Company Support

Most tools accept an optional `company_id` parameter to filter by Odoo company. This supports multi-company Odoo instances (Elewa has three companies).

### 5. Domain Tool Modules

Instead of one massive server file, domain tools (sales, projects, etc.) are separate modules that `register()` their tools on the shared MCP instance:

```python
# In src/mcp/odoo/tools/sales.py
def register(mcp: FastMCP, get_odoo: Any) -> None:
    @mcp.tool(name="odoo_search_opportunities", ...)
    async def search_opportunities(...):
        odoo = get_odoo(ctx)
        # ...
```

This pattern makes it easy to add new domains without modifying the core server.

## Outbound Communication Safety — The Why

**Scenario**: An AI mistakenly calls `action_quotation_send` instead of logging an internal note. This sends an unfinished quotation to a client via email, damaging the deal.

To prevent this, **SafetyGuard** blocks ALL operations that touch email, SMS, or calendar invites. If an AI tool needs to do something that *looks* like a send operation, it must go through explicit human approval *upstream* (in the Claude conversation), never in the tool itself.

## Extending with New Domains

To add support for Support & Retainers, Finance, or ERP Implementation:

1. Create `src/mcp/odoo/tools/my_domain.py`
2. Define input Pydantic models
3. Implement `register(mcp, get_odoo)` function with `@mcp.tool()` decorated functions
4. Add tests
5. Import & register in `src/mcp/odoo/server.py`

Example:

```python
# src/mcp/odoo/tools/support_retainers.py
class SearchTicketsInput(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    limit: int = 20

def register(mcp: FastMCP, get_odoo: Any) -> None:
    @mcp.tool(name="odoo_search_tickets")
    async def search_tickets(params: SearchTicketsInput, ctx: Context) -> str:
        odoo = get_odoo(ctx)
        if isinstance(odoo, str):
            return odoo
        # ...implementation
```

Then in `src/mcp/odoo/server.py`:

```python
from src.mcp.odoo.tools import support_retainers
support_retainers.register(mcp, _odoo)
```

## Testing Philosophy

**Safety tests are non-negotiable.** Before any release or commit:

```bash
pytest src/mcp/odoo/tests/test_safety.py -v
```

If any safety test fails, **do not merge**. SafetyGuard is the first line of defense.

All new write tools should have corresponding tests that verify:
1. The operation is correctly safety-checked
2. Dangerous model/method combinations are blocked
3. Safe operations pass through

## Performance Notes

- **Read operations**: `search_read` is fastest (combines search + read in one RPC call)
- **Caching**: Model IDs are cached in `OdooClient._model_id_cache` to avoid repeated lookups
- **Pagination**: Large result sets default to 80 records; use `limit` and `offset` for pagination
- **Async**: All I/O is async; the server can handle concurrent Claude requests

## Future: Orchestration Pipelines

This server provides individual tools. Future work will add orchestration pipelines that coordinate across tools:

- **Daily Report**: Scan emails → enrich in Odoo → prioritize → send Teams update
- **Approval Flow**: Tool proposes write → human approves → tool executes
- **Debrief**: Post-meeting notes → extract entities → structure into Odoo proposals

These pipelines will use the same tools and SafetyGuard, but add workflow logic.
