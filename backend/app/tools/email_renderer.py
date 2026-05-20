"""
LaunchHouse Events — Email HTML Renderer

Produces production-ready, email-client-safe HTML using:
- Table-based layouts (Outlook compatible)
- Fully inline CSS (no external stylesheets, no CSS variables)
- MSO conditional comments for Outlook button rendering
- Plain-text counterpart helper

Design system:  Operations Strip v02 · 2026-05-13
Signature Blue: #0066CC
"""

from __future__ import annotations

import html
import re
from enum import Enum


# ── Brand constants ────────────────────────────────────────────────────────────

BLUE = "#0066CC"
DARK_NAVY = "#141D2B"
LIGHT_BLUE_BG = "#F0F5FF"
DEFAULT_TEXT = "#1E293B"
MUTED_TEXT = "#64748B"
LINE_BORDER = "#CBD5E1"
WHITE = "#FFFFFF"
PAGE_BG = "#F4F6FA"

BRAND_NAME = "LaunchHouse"
BRAND_TAGLINE = "CVENT REGISTRATION &amp; EVENT TECHNOLOGY OPERATIONS"
FOOTER_COMPANY = "LaunchHouse Events"
FOOTER_DESC = "Premium Cvent registration operations support — built around your existing event team&#39;s workflow."

DEFAULT_CALENDAR_LINK = (
    "https://calendar.google.com/calendar/embed"
    "?src=c_95689573c53b45b15f763deb90590f9d46812cfd53b8177bd92aad0d7a5b157a"
    "%40group.calendar.google.com&ctz=Asia%2FKolkata"
)


class HeaderStyle(str, Enum):
    SLIM = "slim"
    PREMIUM = "premium"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _strip_llm_signature(body_text: str) -> str:
    """
    Remove the trailing signature block that the LLM appends to the email body.
    Looks for the last occurrence of a sign-off ("Best,", "Best regards,", etc.)
    in the last 60% of the text and strips from there onwards.
    """
    pattern = re.compile(
        r"\n+\s*Best[,.]?\s*(?:regards[,.]?)?\s*\n",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(body_text))
    if matches:
        last = matches[-1]
        # Only strip if it appears after the first 40% of the body
        if last.start() > len(body_text) * 0.4:
            return body_text[: last.start()].rstrip()
    return body_text


def _paragraphs_to_html(body_text: str) -> str:
    """
    Convert plain-text email body to email-safe paragraph HTML.
    - Blank lines → new paragraph
    - Lines starting with "—" or "-" inside a block → bullet list rows
    - Existing <p>/<a>/<br> tags are passed through unchanged
    - Plain URLs become clickable links
    """
    # If caller already passed HTML paragraphs, return as-is
    if body_text.strip().startswith("<p") or body_text.strip().startswith("<div"):
        return body_text

    URL_RE = re.compile(
        r'(?<!["\'=>])'          # not already inside an attribute
        r'(https?://[^\s<>"\']+)',
        re.I,
    )

    def _linkify(text: str) -> str:
        return URL_RE.sub(
            lambda m: f'<a href="{m.group(1)}" style="color:{BLUE};text-decoration:underline;font-weight:500;">{m.group(1)}</a>',
            text,
        )

    # Split on double newlines into blocks; single newlines within a block kept
    blocks = re.split(r"\n\s*\n", body_text.strip())
    out_parts: list[str] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # Detect bullet block: 3+ lines where most start with —, -, *, or digits
        bullet_lines = [l for l in lines if re.match(r"^\s*(—|-|\*|\d+[\.\)])\s+", l)]
        if len(bullet_lines) >= 2 and len(bullet_lines) >= len(lines) - 1:
            items = "".join(
                f'<li style="font-size:16px;line-height:26px;color:{DEFAULT_TEXT};'
                f'padding:0 0 4px 0;list-style:none;padding-left:18px;position:relative;">'
                f'<span style="position:absolute;left:0;color:{DEFAULT_TEXT};">—</span>'
                f'{_linkify(html.escape(re.sub(r"^\s*(—|-|\*|\d+[\.\)])\s+", "", l.strip())))}</li>'
                for l in lines
                if l.strip()
            )
            out_parts.append(
                f'<ul style="margin:0 0 20px;padding:0;list-style:none;">{items}</ul>'
            )
        else:
            # Regular paragraph — join single-newline lines with <br>
            inner = "<br>".join(_linkify(html.escape(l)) for l in lines if l.strip())
            out_parts.append(
                f'<p style="margin:0 0 20px;font-size:16px;line-height:26px;'
                f'color:{DEFAULT_TEXT};font-family:Arial,Helvetica,sans-serif;">'
                f'{inner}</p>'
            )

    return "\n".join(out_parts)


LOGO_URL = "https://launchhouse.events/favicon.svg"


def _slim_header() -> str:
    return f"""
    <!--[if mso]>
    <table width="640" cellpadding="0" cellspacing="0" border="0" align="center"
           style="background:{BLUE};">
    <tr><td style="padding:0 24px;height:60px;">
    <![endif]-->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:{BLUE};height:60px;">
      <tr>
        <td style="padding:0 0 0 24px;vertical-align:middle;width:1%;white-space:nowrap;">
          <img src="{LOGO_URL}" width="36" height="36" alt="LV"
               style="display:inline-block;vertical-align:middle;border:0;
                      border-radius:7px;" />
        </td>
        <td style="padding:0 0 0 10px;vertical-align:middle;white-space:nowrap;">
          <span style="display:block;color:{WHITE};font-size:15px;font-weight:700;
                       font-family:Arial,Helvetica,sans-serif;line-height:1.15;
                       letter-spacing:-0.2px;">
            Launch House
          </span>
          <span style="display:block;color:{LIGHT_BLUE_BG};font-size:9px;font-weight:600;
                       font-family:Arial,Helvetica,sans-serif;letter-spacing:2px;
                       text-transform:uppercase;line-height:1.3;">
            EVENTS
          </span>
        </td>
        <td style="padding:0 24px;vertical-align:middle;text-align:right;">
          <span style="color:{LIGHT_BLUE_BG};font-size:11px;font-weight:600;
                       font-family:Arial,Helvetica,sans-serif;letter-spacing:1px;">
            {BRAND_TAGLINE}
          </span>
        </td>
      </tr>
    </table>
    <!--[if mso]></td></tr></table><![endif]-->"""


def _premium_header() -> str:
    return f"""
    <!--[if mso]>
    <table width="640" cellpadding="0" cellspacing="0" border="0" align="center"
           style="background:{BLUE};">
    <tr><td style="padding:28px 32px 24px;">
    <![endif]-->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:{BLUE};">
      <tr>
        <td style="padding:28px 32px 24px;vertical-align:top;">
          <div style="color:{WHITE};font-size:22px;font-weight:600;
                      font-family:Arial,Helvetica,sans-serif;margin-bottom:10px;">
            {BRAND_NAME}
          </div>
          <div style="color:{LIGHT_BLUE_BG};font-size:14px;line-height:22px;
                      font-family:Arial,Helvetica,sans-serif;font-weight:400;">
            Cvent Registration &amp; Event Technology Operations
          </div>
        </td>
      </tr>
    </table>
    <!--[if mso]></td></tr></table><![endif]-->"""


def _keyline() -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="height:1px;line-height:1px;font-size:1px;
                   background:{BLUE};">&nbsp;</td>
      </tr>
    </table>"""


def _signature_block(
    sender_name: str,
    sender_company: str,
    sender_role: str,
    sender_site_url: str,
    sender_calendar_link: str,
    compact: bool = False,
) -> str:
    """5-line standard or 3-line compact signature."""
    name_h = html.escape(sender_name)
    company_h = html.escape(sender_company)
    role_h = html.escape(sender_role)
    site_url = sender_site_url or "#"
    cal_url = sender_calendar_link or DEFAULT_CALENDAR_LINK

    # Display-friendly versions
    site_display = re.sub(r"^https?://", "", site_url).rstrip("/")
    # Show friendly label for long calendar URLs
    cal_display = (
        "Book a meeting →"
        if "calendar.google.com" in cal_url or len(cal_url) > 60
        else re.sub(r"^https?://", "", cal_url)
    )

    link_style = f"color:{BLUE};text-decoration:underline;font-weight:500;font-family:Arial,Helvetica,sans-serif;font-size:14px;"
    base_style = f"font-family:Arial,Helvetica,sans-serif;line-height:22px;"
    best_line = f'<div style="font-size:14px;color:{DEFAULT_TEXT};margin-bottom:6px;">Best,</div>'

    if compact:
        return f"""
    <div style="margin-top:28px;{base_style}">
      {best_line}
      <div style="font-size:15px;font-weight:600;color:{DEFAULT_TEXT};margin-top:4px;">{name_h}</div>
      <div style="font-size:14px;font-weight:500;color:{DEFAULT_TEXT};">{company_h}</div>
      <div style="font-size:13px;color:{MUTED_TEXT};">{role_h}</div>
    </div>"""

    calendar_line = (
        f'      <div><a href="{cal_url}" style="{link_style}">{cal_display}</a></div>\n'
        if cal_url
        else ""
    )

    return f"""
    <div style="margin-top:28px;{base_style}">
      {best_line}
      <div style="font-size:15px;font-weight:600;color:{DEFAULT_TEXT};margin-top:4px;">{name_h}</div>
      <div style="font-size:14px;font-weight:500;color:{DEFAULT_TEXT};">{company_h}</div>
      <div style="font-size:13px;color:{MUTED_TEXT};">{role_h}</div>
{calendar_line}      <div><a href="{site_url}" style="{link_style}">{site_display}</a></div>
    </div>"""


def _footer_block(site_url: str) -> str:
    site_url = site_url or "https://launchhouse.events/"
    site_display = re.sub(r"^https?://", "", site_url).rstrip("/")
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="background:{BLUE};border-top:1px solid {LINE_BORDER};
                   padding:18px 24px 16px;">
          <table cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:middle;padding-right:10px;width:36px;">
                <img src="{LOGO_URL}" width="28" height="28" alt="LH"
                     style="display:block;border:0;border-radius:5px;" />
              </td>
              <td style="vertical-align:middle;">
                <span style="display:block;color:{WHITE};font-size:13px;font-weight:700;
                             font-family:Arial,Helvetica,sans-serif;line-height:1.2;">
                  Launch House
                </span>
                <span style="display:block;color:{LIGHT_BLUE_BG};font-size:8px;font-weight:600;
                             font-family:Arial,Helvetica,sans-serif;letter-spacing:2px;
                             text-transform:uppercase;">
                  EVENTS
                </span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="background:{LIGHT_BLUE_BG};border-top:1px solid {LINE_BORDER};
                   padding:18px 40px 16px;">
          <div style="font-size:13px;line-height:20px;color:{DEFAULT_TEXT};
                      font-family:Arial,Helvetica,sans-serif;margin-bottom:10px;">
            {FOOTER_DESC}
          </div>
          <div style="font-size:12px;line-height:18px;color:{MUTED_TEXT};
                      font-family:Arial,Helvetica,sans-serif;">
            <a href="{site_url}"
               style="color:{BLUE};text-decoration:underline;
                      font-family:Arial,Helvetica,sans-serif;">
              {site_display}
            </a>
            &nbsp;&middot;&nbsp;
            If this is not relevant, reply &#34;not now&#34; and we won&#39;t follow up.
          </div>
        </td>
      </tr>
    </table>"""


# ── Public API ─────────────────────────────────────────────────────────────────

def render_email_html(
    body_text: str,
    sender_name: str = "LaunchHouse Team",
    sender_company: str = "LaunchHouse Events",
    sender_role: str = "Cvent Registration & Event Technology Operations",
    sender_site_url: str = "https://launchhouse.events/",
    sender_calendar_link: str = DEFAULT_CALENDAR_LINK,
    header_style: HeaderStyle | str = HeaderStyle.SLIM,
    compact_signature: bool = False,
) -> str:
    """
    Wrap email body text/paragraphs in the LaunchHouse branded HTML template.

    Args:
        body_text:          Plain text or light HTML body (paragraphs only, no wrapper).
                            Blank-line-separated blocks become <p> tags. Lists auto-detected.
        sender_name:        Sender's display name (e.g. "Sneh")
        sender_company:     Company name shown in signature
        sender_role:        Sender's role line in signature
        sender_site_url:    Company website URL (shown in signature + footer)
        sender_calendar_link: Scheduling link (shown in signature when provided)
        header_style:       "slim" (60px blue bar) or "premium" (128px with tagline)
        compact_signature:  Use 3-line compact signature (for Director/VP recipients)

    Returns:
        Full production-ready HTML string, ready for SendGrid body_html.
    """
    style = HeaderStyle(header_style)

    header_html = _slim_header() if style == HeaderStyle.SLIM else _premium_header()
    body_html = _paragraphs_to_html(_strip_llm_signature(body_text))
    sig_html = _signature_block(
        sender_name=sender_name,
        sender_company=sender_company,
        sender_role=sender_role,
        sender_site_url=sender_site_url,
        sender_calendar_link=sender_calendar_link,
        compact=compact_signature,
    )
    footer_html = _footer_block(site_url=sender_site_url)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>LaunchHouse Events</title>
<!--[if mso]>
<noscript>
  <xml>
    <o:OfficeDocumentSettings>
      <o:PixelsPerInch>96</o:PixelsPerInch>
    </o:OfficeDocumentSettings>
  </xml>
</noscript>
<![endif]-->
</head>
<body style="margin:0;padding:0;background:{PAGE_BG};
             font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<!-- Email wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{PAGE_BG};padding:24px 0;">
  <tr>
    <td align="center" valign="top">

      <!-- Email card (max 640px) -->
      <!--[if mso]>
      <table width="640" cellpadding="0" cellspacing="0" border="0" align="center">
      <tr><td>
      <![endif]-->
      <table cellpadding="0" cellspacing="0" border="0"
             width="100%"
             style="max-width:640px;background:{WHITE};
                    border-radius:4px;overflow:hidden;
                    box-shadow:0 1px 0 rgba(20,29,43,0.04),
                               0 12px 36px rgba(20,29,43,0.08);">
        <tr>
          <td>
            <!-- Header -->
            {header_html}

            <!-- Keyline -->
            {_keyline()}

            <!-- Body -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="padding:36px 40px;">
                  {body_html}
                  {sig_html}
                </td>
              </tr>
            </table>

            <!-- Footer -->
            {footer_html}

          </td>
        </tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->

    </td>
  </tr>
</table>

</body>
</html>"""


def render_email_plain(
    body_text: str,
    sender_name: str = "LaunchHouse Team",
    sender_site_url: str = "https://launchhouse.events/",
    sender_calendar_link: str = DEFAULT_CALENDAR_LINK,
) -> str:
    """
    Return a clean plain-text version of the email (for multipart/alternative).
    Strips any HTML tags from body_text if present.
    """
    # Strip HTML tags if body_text contains markup
    clean = re.sub(r"<[^>]+>", "", body_text)
    # Collapse excess blank lines
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    # Strip LLM-appended signature
    clean = _strip_llm_signature(clean)

    cal_url = sender_calendar_link or DEFAULT_CALENDAR_LINK
    cal_display = (
        "Book a meeting: " + cal_url
        if "calendar.google.com" in cal_url or len(cal_url) > 60
        else re.sub(r"^https?://", "", cal_url)
    )

    sig_lines = [
        "Best,",
        "",
        sender_name,
        "LaunchHouse Events",
        "Cvent Registration & Event Technology Operations",
        cal_display,
        re.sub(r"^https?://", "", sender_site_url).rstrip("/"),
    ]
    sig = "\n".join(sig_lines)

    return f"""{clean}

{sig}

--
LaunchHouse Events — {re.sub(r"^https?://", "", sender_site_url).rstrip("/")}
If this is not relevant, reply "not now" and we won't follow up.
"""
