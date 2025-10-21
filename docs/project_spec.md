# Sports Thread Internal App — Roster PDF Spec (v1.0.1)

**Scope:** Single source of truth for the roster PDF export feature. This version embeds the exact SQL used by the app and preserves all previously agreed decisions.

---

## 1) Data Contract (Authoritative)

We only use the exact fields returned by our SQL. **No renames. No inferred fields.**

**Columns (exact spelling/case, including spaces and underscores):**

* `Event_ID`
* `Event_Name`
* `Team_Name`
* `Team_ID`
* `Division`
* `User_ID`
* `Name` *(CONCAT of first + last name)*
* `Usertype_ID` *(1 = athlete, 2 = coach)*
* `Phone`
* `Email`
* `Profile_Pic`
* `Jersey_Num`
* `Birthday`

**SQL (authoritative and embedded in code):**

```python
base_select = (
    """
    SELECT
        e.ID as Event_ID,
        e.name as Event_Name,
        t.name as Team_Name,
        t.id as "Team_ID",
        ld.name as Division,
        u.id as User_ID,
        CONCAT(u.firstName, " ", u.lastName) as Name,
        u.userTypeID as Usertype_ID,
        u.phone as Phone,
        u.email as Email,
        u.avatarURL as Profile_Pic,
        etr.jerseyNumber as Jersey_Num,
        u.birthday as Birthday
    FROM
        sportsthreadprod.Events e
    INNER JOIN sportsthreadprod.EventTeamRoster etr ON etr.eventId = e.ID
    INNER JOIN sportsthreadprod.Teams t ON etr.teamId = t.id
    INNER JOIN sportsthreadprod.`User` u ON etr.userId = u.id
    INNER JOIN sportsthreadprod.LookupDivisions ld ON t.divisionID = ld.id
    """
)

# If a specific team was requested, filter for that team only
if team_id is not None:
    query = base_select + f" WHERE e.id={event_id} AND etr.teamId={team_id} ORDER BY etr.teamId, u.id;"
else:
    query = base_select + f" WHERE e.id={event_id} ORDER BY etr.teamId, u.id;"
```

> **Note:** Keep the `ORDER BY etr.teamId, u.id` for deterministic coach selection and stable roster output. If supported, a parameterized variant is recommended to avoid string interpolation issues.

**Guarantees:** `Team_Name` and `Team_ID` are always present (never null). All other fields are best-effort; logic must gracefully handle null/missing values.

---

## 2) Role Mapping & Coach Selection

* **Roles:** `Usertype_ID = 1` → athlete, `Usertype_ID = 2` → coach.
* **Coach selection (single coach card):** Choose the coach with the **lowest `User_ID`** among rows where `Usertype_ID = 2` for the team. If no coach rows exist, omit the coach card entirely (no error).

Rationale: Deterministic, aligns with current ordering (`ORDER BY etr.teamId, u.id`).

---

## 3) PDF Content & Layout

### 3.1 Header

* **Line 1:** Prefer `Event_Name` if present; otherwise `Team_Name`.
* **Line 2 (subhead):** If both available, render `Team_Name • Division`. If only one is available, render that one. If neither (edge case), omit.

### 3.2 Roster Table

* **Columns (left → right):**

  1. `Profile_Pic` — display `—` when null/empty
  2. `Jersey_Num` — display `—` when null/empty/non-numeric (but still sort; see §5)
  3. `Name` — display exactly as provided; no splitting or normalization
  4. `Birthday` — display exactly as provided; no splitting or normalization
  5. `Comments` — provide ample writing space


### 3.3 Coach Card (optional)

* Render a small card above or beside the table when a coach is identified per §2.
* Fields shown (if present): `Name`, `Phone`, `Email`.
* If `Phone` or `Email` are missing, omit that line; do not show placeholders.

### 3.4 Page & Print Behavior

* Paper: Letter and A4 supported; layout auto-fits.
* Margins: 0.5" on all sides.
* Table header repeats on each page; avoid orphan/widow rows.
* Footer with Sports Thread branding/logo on **every** page.
* Page numbers: **Off by default** (toggle planned for v1.x).

---

## 4) PII Policy

* **Roster table:** Names only.
* **Coach card:** May include `Phone`/`Email` if present.
* **Birthdate:** Collected by query but **not displayed** in v1.
* **Retention:** PDFs generated locally; the app does not upload or retain server copies.

---

## 5) Sorting & Row Order

* **Base order:** Preserve SQL order for team grouping and coach determinism.
* **Within a team (athletes only):** Sort by `Jersey_Num` ascending using numeric comparison; treat empty/non-numeric as `∞` (i.e., they appear last). Ties break by `Name` ascending.
* **Coaches:** Do not appear in the table.

Formatting notes:

* Display `Jersey_Num` exactly as provided (trimmed). Sorting uses the leading integer if present.
* Display `Name` exactly as provided (`CONCAT(...)`).

---

## 6) Filenames & Paths

* **Pattern (locked):** `Team_Name_Team_ID.pdf`
* **Examples:**

  * `Tigers 14U` + `8735` → `Tigers_14U_8735.pdf`
  * `ACME Elite – Blue` + `42` → `ACME_Elite_Blue_42.pdf`

**Sanitization:**

* Replace spaces with `_`.
* Strip characters outside `[A-Za-z0-9._-]`.
* Collapse multiple `_` to a single `_`.
* Truncate to 120 chars (preserving `.pdf`).
* If collision: append `-1`, `-2`, … until unique.

**Assumptions:** `Team_Name` and `Team_ID` are always present; no fallbacks.

---

## 7) UX & Workflow

* **Preview modes:**

  * *Dummy Preview* (default): uses fixtures for quick visual checks.
  * *Live Preview* (optional): fetches from the same SQL and shows exactly the available columns; no assumptions.
* **Batch console:** per-team status (Pending → Rendering → Done/Failed), with a **Cancel All** that stops queuing new renders and lets the current render finish.
* **Post-run actions:** per-team buttons for **Open file** and **Reveal in Finder/Explorer**.

---

## 8) Implementation Details

* **Data access:** Always access via dict keys, e.g., `row['Team_ID']`, `row['Jersey_Num']` (keys are case/space-sensitive).
* **No key normalization:** Remove any prior camelCase or aliasing layers.
* **Team grouping:** Use `row['Team_ID']` as the team key; aggregate members, separating athletes (1) from coaches (2).
* **Coach pick:** During aggregation, track the minimum `User_ID` among coaches for the team; render that single coach card if found.
* **Renderer:** Stream HTML → PDF per team to keep memory bounded; embed branding assets as base64.

---

## 9) Errors & Messages (exact wording)

* **Empty roster (no athletes for a team):** “This team has no athletes yet. Nothing to export.”
* **DB connection lost mid-run:** “We lost connection to the database. Your finished PDFs are safe.”
* **Missing partner logo:** “Partner logo unavailable; continuing with default branding.”
* **PDF engine failure:** “PDF engine failed on this team. Saved log for support.”
* **Disk full:** “Not enough disk space to save the PDF. Free up space and retry.”

*(We do not warn about missing `Team_Name`/`Team_ID` since they’re guaranteed.)*

---

## 10) Engineering & Ops

* **Secrets:** No keys in code. Read `IRONPDF_LICENSE` and DB credentials from environment (or `.env` in dev only). If license missing/invalid, disable export and show a single in-app banner.
* **DB:** 30s connect timeout; 60s query timeout; 3 retries with exponential backoff. Run a health check at app start and before batch jobs.
* **Concurrency:** Fixed worker pool of **3** parallel renders. Queue is unbounded; ensure each render streams to avoid large memory spikes.
* **Assets:** Sports Thread + optional partner logo embedded as base64. If partner logo missing, center Sports Thread logo in footer.
* **Cross-platform:**

  * Logs: `~/Library/Logs/SportsThread` (macOS), `%AppData%/SportsThread/Logs` (Windows).
  * Ship notarized (macOS) and signed (Windows).
* **Versioning & telemetry:** SemVer in UI (e.g., `v1.0.0`). Anonymous crash/error telemetry **off by default** with an opt-in toggle linking to policy.

---

## 11) Quality Gates & Testing

* **Golden PDFs:** Three fixtures (small team, long names, multi-page). CI compares DOM (HTML) and rasterized images at 150 DPI with ≤0.5% pixel tolerance.
* **Sorting tests:** Mixed numeric/blank `Jersey_Num`; assert numeric sort with blanks last; tie-break by `Name`.
* **Accessibility (desktop app):** Keyboard navigable, visible focus ring, AA contrast, 40px min hit targets.
* **Smoke tests:**

  * Coach present vs absent.
  * Team with only one page vs multi-page.
  * Filenames with special characters and long names (sanitization & collision).

---

## 12) Roadmap (Nice-to-haves for v1.x)

1. **Page numbers toggle** (defaults off).
2. **Staff section** listing additional coaches/staff (if identifiable via existing fields).
3. **CSV/JSON export** alongside each PDF.
4. **CLI mode**: `sports-thread export --event <id> --team <id>`.

---

## 13) Acceptance Criteria (v1.0)

* Given a dataset matching the SQL, the app produces a PDF per team named `Team_Name_Team_ID.pdf`, sanitized and unique per rules.
* The roster table shows only `Jersey_Num` and `Name`, sorted as specified; coaches do not appear in the table.
* If a coach exists, a single coach card is shown using the lowest `User_ID` coach, with `Phone`/`Email` if present.
* Multi-page tables repeat headers; the footer logo appears on every page; there are no orphan header rows.
* All error messages match the wording in §9.

---

# Prototype Readiness Checklist — Roster PDF (Go/No‑Go)

**Conclusion:** *We can ship a working prototype once the Must‑Haves below are complete.* This checklist maps directly to the v1.0.1 spec and keeps scope tight.

---

## A. Must‑Haves (prototype)

1. **Query in code = spec**

   * Use the embedded SQL exactly (with `ORDER BY etr.teamId, u.id`).
   * Prefer the parameterized variant.

2. **Data wiring**

   * Access result rows by dict key (case/space sensitive).
   * Group by `row['Team ID']`.
   * Split athletes (`Usertype_ID == 1`) vs coaches (`== 2`).
   * Pick coach: **lowest `User_ID`** among coaches.

3. **Template MVP**

   * Header: `Event_Name` (fallback `Team_Name`), subhead `Team_Name • Division` when present.
   * Table with five columns: `Pic`, `Jersey_Num` ("—" when blank), `Name`, `Birthday`, and `Comments`.
   * Coaches **not** in table.
   * Optional coach card (Name, Phone, Email if present).
   * Footer branding on every page.
   * Table header repeats across pages; avoid widows/orphans.

4. **Sorting**

   * Within a team (athletes only): numeric sort by `Jersey_Num`, blanks last; tie by `Name`.

5. **Filename rule**

   * `Team_Name_Team_ID.pdf` with sanitizer and collision handling.

6. **Config & secrets**

   * Read `IRONPDF_LICENSE` + DB creds from env / `.env` (dev only).
   * If missing/invalid license → disable export with banner.

7. **Basic UX**

   * Batch console: Pending → Rendering → Done/Failed.
   * Buttons: **Open file** and **Reveal in Finder/Explorer** per team.
   * Cancel All: stop queueing new jobs; let current render finish.

8. **Error messages (exact text)**

   * Empty roster, DB lost, missing partner logo, PDF engine failure, disk full (per spec §9).

9. **Assets**

   * Sports Thread logo embedded (base64).
   * Partner logo optional; if absent, center default branding.

10. **Fixtures for demo**

* Three JSON fixtures mirroring SQL columns:
  a) Small team (single page)
  b) Long names / special chars
  c) Multi‑page roster
* One fixture with no coach (coach card omitted).

---

## B. Nice‑to‑Have (can defer post‑prototype)

* Live Preview toggle (keep Dummy Preview for demo).
* CI golden PDF diffs.
* Notarization/signing (prototype can run unsigned in dev).
* Telemetry opt‑in UI.

---

## C. Open Risks (mitigations)

* **IronPDF quirks**: multi‑page header repetition → verify with fixture (c).
* **Non‑numeric jerseys**: ensure sort extracts leading integer; display unchanged.
* **String sanitation**: confirm sanitizer doesn’t strip valid unicode dashes in names; test examples.

---

## D. Quick Test Plan (demo‑ready)

1. Run with each fixture and visually confirm: header/subhead, table columns, footer every page.
2. Verify coach card appears only when a coach exists; Phone/Email lines only if present.
3. Confirm file names are `Team_Name_Team_ID.pdf`, sanitized and unique.
4. Force disk‑full and license‑missing code paths to show correct banners/messages.
5. Sort checks: 7, 12, "", 3 → order: 3, 7, 12, —.

---

## E. Demo Script (3 minutes)

1. Launch app → Dummy Preview of Fixture (a).
2. Batch export 3 teams; show console states, Cancel All once.
3. Open exports folder; show filenames.
4. Open multi‑page PDF; scroll to see repeating header + footer.
5. Swap to Fixture (no coach) → export → point out coach card omission.

---

**Go/No‑Go Gate:** Mark items A1–A10 complete. If all checked, we’re Go for prototype delivery.
