# Phase 3 Implementation Plan

## Goal
Network inventory per client, encrypted credentials vault, PDF report generator, client health dashboard.

---

## Models (models.py additions)

### Device
| Field | Type | Notes |
|-------|------|-------|
| id | PK | |
| client_id | FK → clients | |
| hostname | String(100) | |
| ip_address | String(45) | IPv4/IPv6 |
| device_type | String(30) | router/switch/server/workstation/laptop/printer/other |
| os | String(100) | optional |
| mac_address | String(20) | optional |
| notes | Text | optional |
| is_active | Boolean | default True |
| created_at | DateTime | |

### Credential
| Field | Type | Notes |
|-------|------|-------|
| id | PK | |
| client_id | FK → clients | |
| label | String(100) | e.g. "Main Router", "Domain Admin" |
| username | String(100) | |
| password_enc | LargeBinary | Fernet-encrypted bytes |
| service_url | String(200) | optional |
| notes | Text | optional |
| created_at | DateTime | |
| updated_at | DateTime | |

Encryption: `cryptography.fernet.Fernet` with key from `VAULT_KEY` env var (generated + stored in .env).  
`.get_password(app_key)` → decrypt and return plaintext.  
`.set_password(plaintext, app_key)` → encrypt and store.

---

## Routes (routes/engineer.py additions)

### Devices (under /engineer/clients/<id>/devices)
- `GET /clients/<id>/devices` — list page (same as client_detail but "Inventory" tab active)
- `POST /clients/<id>/devices/new` — create device
- `POST /clients/<id>/devices/<dev_id>/edit` — update device
- `POST /clients/<id>/devices/<dev_id>/delete` — soft delete (is_active=False)

### Credentials (under /engineer/clients/<id>/vault)
- `GET /clients/<id>/vault` — list credentials (passwords hidden by default, reveal on click via JS)
- `POST /clients/<id>/vault/new` — add credential (encrypt password)
- `POST /clients/<id>/vault/<cred_id>/edit` — update credential
- `POST /clients/<id>/vault/<cred_id>/delete` — delete

### Reports (under /engineer/clients/<id>/report)
- `GET /clients/<id>/report` — form: pick month/year
- `GET /clients/<id>/report/pdf?month=MM&year=YYYY` — generate + stream PDF

---

## UI Changes

### client_detail.html — tabbed layout
Add 3 tabs to client detail page:
1. **Overview** (existing users + tickets)
2. **Inventory** (devices table + add form)
3. **Vault** (credentials table + add form, passwords hidden)

Add health stats bar at top of client detail:
- Open Tickets count
- SLA Compliance % (closed tickets where resolved_at < sla_deadline)
- Time Logged this month (sum of remote session minutes)
- Generate Report button (→ report form)

### New templates
- `engineer/device_form.html` — add/edit device (modal or inline)
- `engineer/credential_form.html` — add/edit credential
- `engineer/report_preview.html` — rendered HTML report (printable / PDF)

### Dashboard additions
- Client list table gains a "Health" column: green/amber/red dot based on SLA compliance %

---

## Report PDF Content (per client, per month)
- Header: client name, month, generated date
- Summary: tickets opened, tickets resolved, SLA compliance %, total remote time
- Ticket table: ticket#, title, priority, status, time logged
- Sessions table: date, duration, notes
- Footer: engineer contact info

Library: `reportlab` (pure Python, no OS deps).

---

## Config (config.py)
Add `VAULT_KEY` — read from env. If absent on startup: generate, print to console, warn to save it.

---

## Tests
- `tests/test_inventory.py`: add device, edit device, delete device, add credential, credential encryption round-trip
- `tests/test_reports.py`: report route returns 200, PDF content-type header

---

## Tasks (ordered)
1. Add `Device` + `Credential` models, `VAULT_KEY` to config
2. Add device CRUD routes + templates
3. Add credential vault routes + templates (encrypt/decrypt)  
4. Refactor `client_detail.html` to tabbed layout + health stats bar
5. Add report route + PDF generation (reportlab)
6. Add CSS for new components
7. Write tests
8. Update `.claude/state.md`

---

## Dependencies to install
```
pip install cryptography reportlab
```
