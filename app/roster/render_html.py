# app/roster/render_html.py
from __future__ import annotations
"""
HTML renderer for team roster preview/PDF.

Manual-pagination variant: renders multiple small tables so the masthead +
column headers + footer appear at the top/bottom of every page, without
relying on renderer `<thead>` repetition.

Columns (display): Photo | # | Name | Birthday | Comments
Backed by SQL field names (data): Profile_Pic, Jersey_Num, Name, Birthday

Public API:
    render_team(
        team: dict,
        coach: dict | None = None,
        partner_logo_url: str | None = None,
        partner_logo_path: str | None = None,
        footer_logo_src: str | None = None,
    ) -> str (full HTML document)

Deterministic behaviors / safe defaults:
- FIRST_PAGE_MAX_ROWS = 12 (conservative, tall masthead)
- NEXT_PAGES_MAX_ROWS = 14
- Zebra striping via :nth-child(even) per table (no continuity requirement)
- Bootstrap CSS: inline if found locally via env/known paths; else CDN link
- Images: partner logo and footer logo use provided src; profile pics normalized
  to files.sportsthread.com per spec.
"""

from typing import Any, Dict, Optional, List
import base64
import html
import os
from pathlib import Path

# --------------------------- small utilities -------------------------------

def _safe(val: Any) -> str:
    return "" if val is None else html.escape(str(val))


def _read_bytes(path: os.PathLike[str] | str) -> Optional[bytes]:
    try:
        p = Path(path)
        if p.is_file():
            return p.read_bytes()
    except Exception:
        pass
    return None


def _read_text(path: os.PathLike[str] | str) -> Optional[str]:
    try:
        p = Path(path)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    return None


def _data_uri_from_path(path: os.PathLike[str] | str, mime: Optional[str] = None) -> Optional[str]:
    b = _read_bytes(path)
    if not b:
        return None
    if mime is None:
        # naive guess from suffix
        suffix = str(path).lower()
        if suffix.endswith(".png"):
            mime = "image/png"
        elif suffix.endswith(".jpg") or suffix.endswith(".jpeg"):
            mime = "image/jpeg"
        elif suffix.endswith(".gif"):
            mime = "image/gif"
        else:
            mime = "application/octet-stream"
    enc = base64.b64encode(b).decode("ascii")
    return f"data:{mime};base64,{enc}"


def normalize_cdn_url(url: Optional[str]) -> Optional[str]:
    """Normalize avatar/asset URLs to files.sportsthread.com per spec."""
    if not url:
        return None
    url = str(url)
    if url.startswith("/"):
        return f"https://files.sportsthread.com{url}"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://files.sportsthread.com/{url}"


def _img_src(url: Optional[str] = None, path: Optional[str] = None) -> Optional[str]:
    """Prefer local path (inline as data URI) for reliability; else normalized URL."""
    # Prefer an explicitly provided local path (e.g., uploaded partner logo)
    if path:
        di = _data_uri_from_path(path)
        if di:
            return di
        # fallback to plain file path; WebEngine often resolves it, IronPDF too
        return str(path)
    # Else, try URL normalization
    if url:
        return normalize_cdn_url(url)
    return None


def _img_tag(src: Optional[str], alt: str = "", classes: str = "", style: str = "") -> str:
    if not src:
        return ""
    cls = f' class="{classes}"' if classes else ""
    sty = f' style="{style}"' if style else ""
    return f'<img src="{_safe(src)}" alt="{_safe(alt)}"{cls}{sty} />'


def _bootstrap_css_inline() -> Optional[str]:
    """Try to read bootstrap from env/known paths; else return None for CDN usage."""
    p = os.getenv("BOOTSTRAP_CSS_PATH")
    if p:
        if css := _read_text(p):
            return css
    here = Path(__file__).resolve().parent
    for cand in [
        here / "assets" / "bootstrap.min.css",
        here.parent / "assets" / "bootstrap.min.css",
        Path.cwd() / "assets" / "bootstrap.min.css",
    ]:
        if css := _read_text(cand):
            return css
    return None

# ------------------------------ pagination ---------------------------------

def paginate_rows(rows: List[Dict[str, Any]], first_page_max: int, next_pages_max: int) -> List[List[Dict[str, Any]]]:
    """Split athlete rows into page-sized chunks (simple, conservative)."""
    if not rows:
        return []
    out: List[List[Dict[str, Any]]] = []
    i = 0
    out.append(rows[i : i + first_page_max])
    i += first_page_max
    while i < len(rows):
        out.append(rows[i : i + next_pages_max])
        i += next_pages_max
    return out

# ------------------------------ HTML pieces --------------------------------

def _tbody_rows_html(rows: List[Dict[str, Any]]) -> str:
    """Build the <tbody> rows."""
    tr_list: List[str] = []
    for r in rows:
        pic = normalize_cdn_url(r.get("Profile_Pic"))
        num = _safe(r.get("Jersey_Num"))
        name = _safe(r.get("Name"))
        bday = _safe(r.get("Birthday"))
        tr_list.append(
            "<tr>"
            f"<td class=\"text-center\">{_img_tag(pic, alt='Photo', classes='avatar-img')}"
            "</td>"
            f"<td class=\"text-start num-col\">{num}</td>"
            f"<td class=\"text-start name-col\">{name}</td>"
            f"<td class=\"text-start bday-col\">{bday}</td>"
            f"<td class=\"text-start comments-col\"><div class=\"comments-box\" aria-label=\"Write comments here\"></div></td>"
            "</tr>"
        )
    return "".join(tr_list)


def _thead_html(team_name: str, coach_name: str, division: str, coach_phone: str,
                event_name: str, partner_logo: Optional[str]) -> str:
    return f"""
      <thead>
        <!-- Masthead row (present at start of every table) -->
        <tr class="masthead">
          <th colspan="5">
            <div class="doc-header">
              <div class="logo-wrap">
                {f'<img class="logo-img" alt="Partner logo" src="{_safe(partner_logo)}" loading="eager" />' if partner_logo else ''}
              </div>
              <div>
                <div class="doc-title">{_safe(event_name) if event_name else _safe(team_name)}</div>
                <div class="info-list" role="presentation">
                  <div class="info-row"><div class="info-label">Team:</div><div>{_safe(team_name)}</div></div>
                  <div class="info-row"><div class="info-label">Coach:</div><div>{_safe(coach_name)}</div></div>
                  <div class="info-row"><div class="info-label">Division:</div><div>{_safe(division)}</div></div>
                  <div class="info-row"><div class="info-label">Phone:</div><div>{_safe(coach_phone)}</div></div>
                </div>
              </div>
            </div>
          </th>
        </tr>
        <!-- Column labels -->
        <tr class="cols">
          <th class="text-center">Photo</th>
          <th class="text-start">#</th>
          <th class="text-start name-col">Name</th>
          <th class="text-start bday-col">Birthday</th>
          <th class="text-start comments-col">Comments</th>
        </tr>
      </thead>
    """


def _tfoot_html(footer_logo: Optional[str]) -> str:
    return f"""
      <tfoot>
        <tr>
          <td colspan="5">
            <div class="pdf-footer">
              <span>Powered by</span>
              {f'<img class="footer-logo" alt="Sports Thread" src="{_safe(footer_logo)}" />' if footer_logo else ''}
            </div>
          </td>
        </tr>
      </tfoot>
    """

# ------------------------------ main API ----------------------------------

def render_team(
    team: Dict[str, Any],
    coach: Optional[Dict[str, Any]] = None,
    partner_logo_url: Optional[str] = None,
    partner_logo_path: Optional[str] = None,
    footer_logo_src: Optional[str] = None,
) -> str:
    """Build the FULL HTML document for a team's roster.

    `team` is expected to include at least: Team_Name, Event_Name, Division, Coach_Name,
    Coach_Phone, and a list of `athletes` with the display fields.
    """

    team_name = str(team.get("Team_Name", "")).strip()
    event_name = str(team.get("Event_Name", "")).strip()
    division = str(team.get("Division", "")).strip()
    # Accept either SQL field names (Name/Phone) from the coach row OR legacy Coach_* keys on the team dict.
    if coach:
        coach_name = str(coach.get("Name", "")).strip() or str(team.get("Coach_Name", "")).strip()
        coach_phone = str(coach.get("Phone", "")).strip() or str(team.get("Coach_Phone", "")).strip()
    else:
        coach_name = str(team.get("Coach_Name", "")).strip()
        coach_phone = str(team.get("Coach_Phone", "")).strip()

    # Resolve assets (prefer uploaded local partner logo path)
    partner_logo = _img_src(url=partner_logo_url, path=partner_logo_path)
    # Footer logo: prefer explicit src; else auto-discover bundled ST logo.
    footer_logo = footer_logo_src
    if not footer_logo:
        # Allow override via env, else look in known locations (repo root).
        env_p = os.getenv("FOOTER_LOGO_PATH")
        candidates = []
        if env_p:
            candidates.append(Path(env_p))
        # repo root = app/roster/../../
        candidates.append(Path(__file__).resolve().parents[2] / "sportsthread_logo.png")
        candidates.append(Path.cwd() / "sportsthread_logo.png")
        for cand in candidates:
            di = _data_uri_from_path(cand)
            if di:
                footer_logo = di
                break

    # Bootstrap: inline if local CSS found; else fall back to CDN link
    _bootstrap = _bootstrap_css_inline()
    if _bootstrap:
        bootstrap_tag = f"<style>\n{_bootstrap}\n</style>"
    else:
        bootstrap_tag = (
            '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" '
            'rel="stylesheet" crossorigin="anonymous" />'
        )

    # Pagination: simple conservative limits; adjust if you need tighter pages
    FIRST_PAGE_MAX_ROWS = 7
    NEXT_PAGES_MAX_ROWS = 7

    athletes: List[Dict[str, Any]] = list(team.get("athletes") or [])
    slices = paginate_rows(athletes, FIRST_PAGE_MAX_ROWS, NEXT_PAGES_MAX_ROWS)

    tables_html: List[str] = []
    for chunk in slices:
        thead = _thead_html(team_name, coach_name, division, coach_phone, event_name, partner_logo)
        tbody = f"<tbody>{_tbody_rows_html(chunk)}</tbody>"
        tfoot = _tfoot_html(footer_logo)
        # Define a stable column model for fixed layout:
        #   col1 Photo  = 70px
        #   col2 #      = 60px
        #   col3 Name   = 24%
        #   col4 Bday   = 10%
        #   col5 Comments = auto (fills the rest)
        colgroup = (
            "<colgroup>"
            "<col style=\"width:70px;\" />"
            "<col style=\"width:60px;\" />"
            "<col style=\"width:24%;\" />"
            "<col style=\"width:20%;\" />"
            "<col />"
            "</colgroup>"
        )
        tables_html.append(f'<table class="roster table table-sm">{colgroup}{thead}{tbody}{tfoot}</table>')

    # Full HTML document (double braces in CSS for f-string literal braces)
    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  {bootstrap_tag}
  <style>
    :root {{ --brand: #e44115; --rule-strong: #111; --rule-soft: #e5e7eb; --row-alt: #f8fafc; --ink: rgba(0,0,0,.15); --row-h: 56px; }}
    html, body {{ background: #fff; }}
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}

    .brand {{ color: var(--brand); font-weight: 700; }}
    .doc {{ padding: 28px; }}

    /* We render multiple tables, so we are not relying on header repetition. */
    thead {{ display: table-header-group !important; }}
    tfoot {{ display: table-footer-group !important; }}
    thead tr {{ break-inside: avoid; page-break-inside: avoid; }}

    /* Masthead layout */
    .doc-header {{ display: grid; grid-template-columns: 3fr 2fr; gap: 18px; align-items: center; margin: 0; }}
    .doc-header .logo-wrap {{ text-align: center; }}
    .doc-header .logo-img {{ display: block; height: 200px; width: auto; max-width: 100%; object-fit: contain; margin: 0 auto; }}
    .doc-title {{ font-size: 1.45rem; font-weight: 900; line-height: 1.15; margin: 0 0 8px; }}
    .info-list {{ font-size: 0.95rem; }}
    .info-row {{ display: flex; gap: 8px; line-height: 1.35; }}
    .info-label {{ font-weight: 700; color: #555; width: 92px; flex: 0 0 92px; }}

    /* Table look — sleek: single bottom rules on body rows, bold rule under column labels */
    table.roster {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
    table.roster th, table.roster td {{ padding: 8px 10px; vertical-align: middle; line-height: 1.25; }}

    /* No boxy grid in masthead */
    thead tr.masthead th {{ border: 0 !important; padding-bottom: 12px; }}
    /* Column labels: strong underline, no side/top borders */
    thead tr.cols th {{ border: 0; border-bottom: 2px solid var(--rule-strong); background: #fff; }}
    /* Body rows: single subtle bottom rule only */
    table.roster tbody td {{ border: 0; border-bottom: 1px solid var(--rule-soft); }}

    /* Ensure the Comments cell shows its grid borders above the lined overlay */
    td.comments-col {{
      position: relative;           /* already set below, keep here for clarity */
      border-top: 1px solid var(--rule-soft);
      border-bottom: 1px solid var(--rule-soft);
      z-index: 1;                   /* put the cell (and its borders) above the overlay */
    }}

    /* Columns (weights only; exact widths come from <colgroup>) */
    .name-col {{ font-weight: 500; }}
    .num-col {{ font-weight: 500; }}
    .bday-col {{}}
    .comments-col {{}}

    /* Photo/avatar */
    .avatar-img {{ display: block; height: var(--row-h); width: var(--row-h); object-fit: cover; border-radius: 4px; }}
    /* Zebra striping (restarts per table, as requested) */
    table.roster > tbody > tr:nth-child(even) > td {{ background-color: var(--row-alt); }}

    /* Comments cell: full-height ruling regardless of wraps in other columns */
    td.comments-col {{ position: relative; }}
    /* Invisible box establishes a minimum row height (baseline writing space) */
    .comments-box {{ min-height: var(--row-h); border-radius: 2px; }}
    /* Draw the lines on the cell itself so they always match the cell's height */
    td.comments-col::after {{
      content: "";
      position: absolute;
      /* inset matches cell padding for a nice gutter */
      inset: 8px 10px;
      background-image: repeating-linear-gradient(
        to bottom,
        transparent 0, transparent 13px,
        var(--ink) 13px, var(--ink) 14px
      );
      pointer-events: none;
      /* keep lines visible in PDF */
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
      border-radius: 2px;
      z-index: 0;    
    }}


    /* Footer */
    .pdf-footer {{ display: flex; flex-direction: column; align-items: center; gap: 6px; padding-top: 10px; }}
    .footer-logo {{ height: 22px; width: auto; object-fit: contain; }}

    @media print {{
      .doc {{ padding: 22px; }}
      .doc-header .logo-img {{ height: 240px; }}
    }}
  </style>
</head>
<body>
  <div class="doc">
    {''.join(tables_html)}
  </div>
</body>
</html>"""

    return html_doc

__all__ = ["render_team"]
