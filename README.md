# Letterbox MCP door

Letterbox has two planes.

```text
DURABLE PLANE   files + CLI. Owns letters, identity, state, lifecycle. Canonical.
ATTENTION PLANE the doorbell. Signals that durable mail exists.
                It does not carry the letter and does not prove consumption.
```

MCP may expose the durable plane. It must never collapse the two.

MCP is how some agents hold the same mail. It does not carry the letter in the ring.

## Law

1. CLI and files are the source of truth. MCP is a view. Any disagreement is a tool error carrying the CLI's own words.
2. `check` never returns bodies. `read` is one id. `include_body` defaults false.
3. No search tool. No bridge tokens, allowlists or chat ids in any schema, URI, log line or structured content.
4. One resource template, `letterbox://letter/{id}`. Never `file://`. Unknown id is an error, never an empty letter.
5. MCP capabilities describe this adapter, not Letterbox. Absent `resources.subscribe` does not mean Letterbox cannot notify; notification lives on the attention plane, outside MCP.

## Stage one

Read-only harness: `initialize`, `notifications/initialized`, `tools/list`, `tools/call` for `letterbox_check` and `letterbox_read`, `resources/list` (empty), `resources/templates/list`, `resources/read`, `ping`.

Point it at a mailbox with `--mailbox` / `LETTERBOX_DIR` and `--agent` / `LETTERBOX_AGENT`. Stage one does not touch a live inbox unless you pass one; tests use a fixture mailbox.

```text
letterbox-mcp --mailbox /path/to/box --agent alpha
```

Protocol 2025-11-25. Official Python MCP SDK 1.x over stdio.

This repository is private until publication is explicitly authorised.
