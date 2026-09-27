# STIG in Splunk — onboarding user guide

Operator-focused guide for Splunk admins standing up the app without reading developer build docs. The in-app **Documentation** view (nav → **Get started → Documentation**) mirrors this content with clickable links inside Splunk Web.

For webpack/UCC developer workflows, see the root [README.md](../README.md).

---

## In-app documentation sections

The Documentation page covers these topics (also in `package/appserver/static/docs/onboarding.html` for offline reference):

1. **Overview** — What the app does (KV review state, not STIG Manager).
2. **Before you begin** — Splunk 9.x, KV, indexes, admin access.
3. **Install** — Tarball / Manage Apps; **`chown -R splunk:splunk`** after root install.
4. **Access control** — Capabilities and `stig_user` / `stig_admin` roles (`authorize.conf`).
5. **HEC** — Input `stig_findings`, index `stig`, sourcetype `stig:finding`; token only in Splunk Data inputs.
6. **Quick start (~15 min)** — Numbered path below.
7. **Import reference** — Baselines vs Checklists; automation summary (`docs/automation.md`).
8. **Multi-user** — Grants, Submit/Accept/Reject, `stig_review_accept`.
9. **Troubleshooting** — Blank Workspaces (UCC build), 403, empty editor, cascade delete 409, HEC.
10. **Further reading** — `docs/automation.md`, `docs/api.md`, `docs/audit-index.md`.

### Default workspace

The app creates a **Default** workspace on first use. Checklist imports without a workspace id use Default until you designate another workspace as the default import target under **Workspaces**.

---

## Quick start (primary operator path)

1. **Workspaces** — **Get started → Workspaces**; create a workspace or use Default.
2. **Import baselines** — **Get started → Import** → **Baselines** tab (not Checklists first on greenfield).
3. **Hosts** — **Get started → Hosts**; select workspace, add a host.
4. **Assign STIG** — **Work → STIG Editor**; select workspace and host, then **Assign STIG** (or **STIG library → Create checklist**).
5. **Review findings** — Editor: update status/details → **Write** → **Submit** if your process requires review.
6. **Collection dashboard** — **Review → Collection dashboard** for metrics and POA&M after findings exist.

---

## Manual QA checklist (organization journey)

Use this script to validate onboarding without reading Playwright tests. Mirrors `e2e/org/organization.spec.js`. Allow 30–60 minutes on a lab Splunk with `stig_admin` and two test users (assessor + reviewer).

| Step | Actor | Action | Pass criteria |
|------|-------|--------|---------------|
| 1 | Admin | **Workspaces** → Add workspace (name, description) | Row appears in Workspaces table |
| 2 | Admin | **Workspace grants** → add member + manager grants for test users | Grants listed for workspace |
| 3 | Admin | **Asset labels** → create label; **Hosts** → add host, assign label | Host visible in workspace |
| 4 | Admin | **Import → Baselines** → import minimal XCCDF or test baseline | Baseline appears in catalog |
| 5 | Admin | **STIG Editor** → select workspace/host → **Assign STIG** to imported baseline | Finding rows appear for host |
| 6 | Assessor | Log in → Editor → select finding → **Write** status/details | Save succeeds |
| 7 | Assessor | **Submit** finding | Status shows submitted |
| 8 | Reviewer | **Accept** or **Reject** (with feedback on reject) | Governance state updates |
| 9 | Reviewer | Repeat write/submit/accept for a second rule if required by policy | — |
| 10 | Admin | **Collection dashboard**, **All workspaces**, **Export** | Dashboards load; export download contains host |

**Navigation checks (this slice)**

- **Get started** group shows Documentation, Import, Workspaces, Hosts (≤5 items).
- Nav label **Workspaces** opens UCC configuration (not hunting for “Configuration”).
- **Classic** nav collection is absent.
- **Documentation** page renders all numbered sections without external network.

---

## Multi-user notes (grants)

- **Workspace grants** define who can see which hosts/baselines in a workspace.
- **Member** role still requires Splunk **`stig_write`** to save reviews.
- **Accept/Reject** requires **`stig_review_accept`** or an owner/manager grant on that workspace.
- Configure grants before assessors report “permission denied” on Submit.

---

## Troubleshooting (short)

| Symptom | Likely fix |
|---------|------------|
| Blank **Workspaces** page | Install built tarball; dev git trees need `./scripts/build_ucc.sh` |
| REST 403 / empty data | Assign `stig_user` + `edit_kvstore` |
| Empty editor | Import baselines; assign STIG to selected host |
| UCC cannot save settings | `chown -R splunk:splunk` on app directory |
| Cannot delete workspace | Remove hosts/checklists/grants or REST `?cascade=true` with `stig_admin` |
| Import OK, search empty | HEC token on `stig_findings`; wait for reconcile (~5 min) |

---

## Related repository docs

- [docs/automation.md](automation.md) — REST/HEC automation
- [docs/api.md](api.md) — REST index
- [docs/audit-index.md](audit-index.md) — audit dashboard
- Project UX audit: `docs/onboarding-ux.md` (maintained in project documentation store)
