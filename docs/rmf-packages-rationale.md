# RMF packages — product rationale

## From-scratch design

If RMF authorization boundaries had been a day-one requirement, the app would treat **package assignment** as part of **governance**, not as metadata on individual findings or a late REST add-on.

| Layer | Role |
|-------|------|
| **Catalog** | Typed, unique `package_id` (admin-defined); display `name` need not be unique. System package `unassigned` (`-1`), not deletable, id not editable. |
| **Assignment** | Global per **hostname**: optional host default; optional host×baseline override (explicit wins). Packages **span workspaces**. |
| **Findings** | Each review row carries denormalized **`rmf_package_id`** for reporting; effective value is resolved from assignment, not from `stig_reviews.package_id` (Evaluate-STIG / CKLB only). |
| **Admin UX** | **Governance** wizard (`stig_configuration_ui`) is the home for RMF setup—same nav area as workspaces, not a parallel “RMF packages” screen. **Hosts** shows the effective default package and links to Governance. |
| **UCC Configuration** | Remains **Workspaces and settings** (workspaces, baselines, editor & ingest)—operational setup, not authorization boundaries. |

Resolution order (matches `services/rmf_packages.py` and `ui/src/types/rmf.js`):

1. Host×baseline override when `baseline` is in scope  
2. Else global host default for that hostname  
3. Else system package `-1`

External assignment rows (`host`, optional `baseline`, `package_id`) must reference an existing package; unknown ids error; packages are not auto-created.

**Who may change catalog and assignments:** `stig_admin`, Splunk `admin`, and `sc_admin`. **`stig_write` may not** create packages or assign.

**Id rename:** One bulk update of defaults, overrides, and denormalized `rmf_package_id` on reviews.

**Reporting:** POA&M, metrics export, collection archive export, and reconcile accept optional `rmf_package_id` filter; default is all packages.

## This increment

- **KV client:** Honor explicit `_key` on insert (required for system package `-1` and stable admin ids).  
- **Spec:** RMF entities moved from “proposed” into §1, §6, §7; §20 retained as decision log.  
- **Types:** Shared `ui/src/types/rmf.js` for resolution and labels (UI + future steps).  
- **Nav:** **Governance** entry (`stig_configuration_ui`) under Admin—no separate RMF side nav item.  
- **UI:** Wizard step 1 — RMF package catalog; Hosts table column for effective default package.  

**Next increments (not in this PR):** Governance wizard steps for host defaults, host×baseline overrides, and bulk external ingest; report filters in SplunkUI dashboards.
