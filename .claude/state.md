# Phase State

## Phase 1 — COMPLETE (2026-05-29)

### What was built
- Flask app with session-based auth
- 3 roles: engineer, client_admin, client_staff
- Full ticket lifecycle: new → assigned → in_progress → pending_client → resolved → closed
- SLA timers per priority (P1=1h, P2=4h, P3=24h, P4=72h)
- Comments thread with internal notes (engineer-only)
- Engineer dashboard: all tickets, filters, stats bar (open, P1, SLA breaches)
- Client portal: submit tickets, view own tickets, reply to thread
- Client management: add company, edit, AnyDesk ID storage, one-click connect link
- User management: add client_admin or client_staff per company
- Email notifications: new ticket → engineer, status change → client, replies both ways
- Brand UI: #407E3C green throughout
- 9/9 tests passing

### Running
- Port: 5000
- Default login: admin@remoteitsupport.com / changeme123
- DB: SQLite (remote_it.db)

## Phase 2 — COMPLETE (2026-05-29)

### What was built
- RemoteSession model: start/end, duration_minutes, notes, anydesk_id_used
- Session panel on ticket detail: live JS timer, Start/End buttons, notes on end
- Auto-ends any active session when new one starts
- Total time logged shown on ticket header
- Sessions log table per ticket
- Knowledge Base: Article model (title, markdown body, category, global/per-client)
- KB categories: General, Network, Windows Admin, Security, Training, Hardware, How-To
- Engineer: create/edit/unpublish articles, markdown editor with live preview
- Client portal: read public + their private articles
- Markdown rendered server-side (Python markdown lib) with full styling
- `| markdown` Jinja2 filter
- Share link per article for pasting in ticket threads
- KB nav link in engineer dashboard sidebar + client portal header
- 19/19 tests passing

## Phase 3 — COMPLETE (2026-05-29)

### What was built
- Device model: hostname, IP, type, OS, MAC, notes, is_active; CRUD per client
- Credential model: Fernet-encrypted passwords at rest; label, username, service_url, notes; CRUD per client
- VAULT_KEY in config (env var, auto-generates ephemeral key with warning if unset)
- client_detail.html: tabbed layout (Overview | Inventory | Vault), health stats bar
- Health stats: open tickets, SLA compliance %, time logged this month
- Inventory tab: device table, add form, edit modal, soft-delete
- Vault tab: credential table, passwords hidden by default, reveal via POST+JS, copy-to-clipboard, add form, edit modal, delete
- Security: cross-client access blocked (403), vault tab engineer-only, passwords never logged
- PDF report generator: pick month/year → download branded PDF (reportlab)
- PDF content: summary stats, ticket table, sessions log, time totals, SLA compliance
- Report button on client detail header
- 32/32 tests passing (13 new tests: 8 inventory, 5 reports)
