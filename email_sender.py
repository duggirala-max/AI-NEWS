import os
import smtplib
import tempfile
from html import escape as _esc
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── Helpers ──────────────────────────────────────────────────────────────────

def _score_bar(score: int, max_score: int = 10) -> str:
    filled = round(score / max_score * 8)
    return "█" * filled + "░" * (8 - filled) + f"  {score}/10"

def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y")

def _split_by_category(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split articles into AI and SAP categories."""
    ai_list = []
    sap_list = []
    for a in articles:
        category = a.get("category", "AI")
        if category == "SAP":
            sap_list.append(a)
        else:
            ai_list.append(a)
    return ai_list, sap_list

# ── PDF builder ───────────────────────────────────────────────────────────────

def build_pdf(articles: list[dict], executive_summary: str = "") -> bytes:
    styles = getSampleStyleSheet()

    # Define compact, lightweight styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=18,
        textColor=colors.HexColor("#e10075"),  # Telekom Magenta
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#444444"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    section_header = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#e10075"),
        spaceBefore=8,
        spaceAfter=2,
    )
    section_banner = ParagraphStyle(
        "SectionBanner",
        parent=styles["Heading1"],
        fontSize=12,
        textColor=colors.white,
        backColor=colors.HexColor("#111111"),  # Dark header for contrast
        spaceBefore=10,
        spaceAfter=6,
        leftIndent=6,
        borderPad=4,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
    )
    label = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
        spaceAfter=1,
    )
    relevance_style = ParagraphStyle(
        "RelevanceNote",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111111"),
        backColor=colors.HexColor("#f9f9f9"),
        spaceAfter=6,
        leftIndent=6,
        rightIndent=6,
        borderPad=4,
    )
    link_style = ParagraphStyle(
        "Link",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#1155cc"),
        spaceAfter=1,
    )
    takeaway_style = ParagraphStyle(
        "Takeaway",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#e10075"),
        backColor=colors.HexColor("#fff0f6"),
        spaceAfter=6,
        leftIndent=6,
        rightIndent=6,
        borderPad=4,
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    # Set up compact document template (2cm margins for clean print and small file size)
    doc = SimpleDocTemplate(
        tmp_path,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = []

    story.append(Paragraph("🤖 AI & SAP News Intelligence Digest", title_style))
    story.append(Paragraph(f"Deutsche Telekom Manager Briefing | {_date_str()}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e10075")))
    story.append(Spacer(1, 0.2 * cm))

    if executive_summary:
        exec_header = ParagraphStyle(
            "ExecHeader",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#e10075"),
            fontName="Helvetica-Bold",
            spaceAfter=2,
        )
        exec_body = ParagraphStyle(
            "ExecBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#111111"),
            backColor=colors.HexColor("#f3f3f3"),
            leftIndent=8,
            rightIndent=8,
            spaceBefore=2,
            spaceAfter=8,
            borderPad=6,
        )
        story.append(Paragraph("📋 Executive Briefing", exec_header))
        for line in executive_summary.split("\n"):
            line = line.strip()
            if line:
                story.append(Paragraph(_esc(line), exec_body))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 0.1 * cm))

    ai_articles, sap_articles = _split_by_category(articles)

    def _render_articles(article_list: list[dict], start_rank: int) -> None:
        for rank, article in enumerate(article_list, start=start_rank):
            # Normalize fields to string
            for _f in ("title", "source", "published_at", "description", "category",
                       "summary", "telekom_relevance", "key_takeaway"):
                if isinstance(article.get(_f), list):
                    article[_f] = "\n".join(str(x) for x in article[_f])

            story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e2e2e2")))
            story.append(Spacer(1, 0.1 * cm))

            story.append(Paragraph(
                f"#{rank} — {_esc(article.get('title', 'No title'))}",
                section_header,
            ))

            story.append(Paragraph(
                f"Source: <b>{_esc(article.get('source', 'Unknown'))}</b> &nbsp;|&nbsp; "
                f"Published: {_esc(article.get('published_at', 'N/A')[:10])} &nbsp;|&nbsp; "
                f"Category: <b>{_esc(article.get('category', 'AI'))}</b>",
                label,
            ))

            url = article.get("url", "")
            if url:
                story.append(Paragraph(f'<link href="{_esc(url)}">{_esc(url)}</link>', link_style))

            # Score Table
            score_data = [
                ["Relevance", "Credibility", "Impact", "Composite"],
                [
                    _score_bar(article.get("relevance_score", 0)),
                    _score_bar(article.get("credibility_score", 0)),
                    _score_bar(article.get("impact_score", 0)),
                    str(article.get("composite_score", 0)),
                ],
            ]
            score_table = Table(score_data, colWidths=[4 * cm, 4 * cm, 4 * cm, 3 * cm])
            score_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e10075")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#e2e2e2")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(Spacer(1, 0.1 * cm))
            story.append(score_table)
            story.append(Spacer(1, 0.1 * cm))

            summary = article.get("summary", article.get("description", ""))
            if summary:
                story.append(Paragraph("<b>Summary:</b>", label))
                story.append(Paragraph(_esc(summary), body))

            relevance = article.get("telekom_relevance", "")
            if relevance:
                story.append(Paragraph("<b>Telekom Relevance:</b>", label))
                story.append(Paragraph(_esc(relevance), relevance_style))

            takeaway = article.get("key_takeaway", "")
            if takeaway:
                story.append(Paragraph("<b>Key Takeaway for Executive Meeting:</b>", label))
                story.append(Paragraph(_esc(takeaway), takeaway_style))

            story.append(Spacer(1, 0.15 * cm))

    # Section 1: AI News
    story.append(Paragraph("🤖 Top AI Intelligence News", section_banner))
    if ai_articles:
        _render_articles(ai_articles, start_rank=1)
    else:
        story.append(Paragraph("No AI articles matched today's criteria.", body))

    # Section 2: SAP News
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("💼 Top SAP Enterprise News", section_banner))
    if sap_articles:
        _render_articles(sap_articles, start_rank=len(ai_articles) + 1)
    else:
        story.append(Paragraph("No SAP articles matched today's criteria.", body))

    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e10075")))
    story.append(Spacer(1, 0.2 * cm))
    
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                                  textColor=colors.HexColor("#333333"), alignment=TA_LEFT, leading=11)
    footer_muted = ParagraphStyle("FooterMuted", parent=styles["Normal"], fontSize=7,
                                  textColor=colors.HexColor("#999999"), alignment=TA_LEFT)
    story.append(Paragraph("With Best Regards,", footer_style))
    story.append(Paragraph("<b>Your Telekom Team</b>", footer_style))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph("Generated automatically by Telekom AI & SAP News Intelligence | Powered by Groq AI", footer_muted))

    doc.build(story)

    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()

    os.unlink(tmp_path)
    return pdf_bytes

# ── HTML email body ───────────────────────────────────────────────────────────

def _render_article_rows(article_list: list[dict], start_rank: int) -> str:
    rows = ""
    for rank, a in enumerate(article_list, start=start_rank):
        url = a.get("url", "#")
        _summary = a.get("summary", a.get("description", ""))
        _relevance = a.get("telekom_relevance", "")
        _takeaway = a.get("key_takeaway", "")

        relevance_html = (
            f'<div style="background:#f9f9f9;border-left:3px solid #e10075;'
            f'padding:6px 10px;margin-top:6px;color:#111;font-size:12px;">'
            f'<b>Telekom Relevance:</b><br>{_relevance}</div>'
            if _relevance else ""
        )
        takeaway_html = (
            f'<div style="background:#fff0f6;border-left:3px solid #e10075;'
            f'padding:6px 10px;margin-top:6px;color:#e10075;font-size:12px;font-style:italic;">'
            f'<b>Key Takeaway for Executive Meeting:</b><br>{_takeaway}</div>'
            if _takeaway else ""
        )

        rows += f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #eee;vertical-align:top;font-family:Arial,sans-serif;">
            <div style="font-size:10px;color:#888;">#{rank} &nbsp;|&nbsp; {a.get('source','')} &nbsp;|&nbsp; {a.get('published_at','')[:10]}</div>
            <div style="font-size:14px;font-weight:bold;margin:2px 0;">
              <a href="{url}" style="color:#e10075;text-decoration:none;">{a.get('title','')}</a>
            </div>
            <div style="font-size:12px;color:#444;margin-bottom:4px;">{_summary}</div>
            <table style="font-size:10px;border-collapse:collapse;margin-top:4px;">
              <tr>
                <td style="padding:2px 6px;background:#e10075;color:#fff;border-radius:2px 0 0 2px;">Relevance {a.get('relevance_score',0)}/10</td>
                <td style="padding:2px 6px;background:#555;color:#fff;">Credibility {a.get('credibility_score',0)}/10</td>
                <td style="padding:2px 6px;background:#222;color:#fff;border-radius:0 2px 2px 0;">Impact {a.get('impact_score',0)}/10</td>
              </tr>
            </table>
            {relevance_html}
            {takeaway_html}
            <div style="margin-top:6px;font-size:10px;">
              <a href="{url}" style="color:#e10075;text-decoration:underline;">Read full article →</a>
            </div>
          </td>
        </tr>"""
    return rows

def _build_html(articles: list[dict], executive_summary: str = "") -> str:
    ai_articles, sap_articles = _split_by_category(articles)

    ai_rows = _render_article_rows(ai_articles, start_rank=1)
    sap_rows = _render_article_rows(sap_articles, start_rank=len(ai_articles) + 1)

    ai_html = f"""
        <tr><td style="padding:10px 24px;background:#e10075;font-family:Arial,sans-serif;">
          <div style="color:#fff;font-size:15px;font-weight:bold;">🤖 Top AI Intelligence News</div>
        </td></tr>
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0">{ai_rows if ai_rows else '<tr><td style="padding:12px;color:#888;">No AI articles found today.</td></tr>'}</table>
        </td></tr>"""

    sap_html = f"""
        <tr><td style="padding:10px 24px;background:#111;font-family:Arial,sans-serif;">
          <div style="color:#fff;font-size:15px;font-weight:bold;">💼 Top SAP Enterprise News</div>
        </td></tr>
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0">{sap_rows if sap_rows else '<tr><td style="padding:12px;color:#888;">No SAP articles found today.</td></tr>'}</table>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:20px 10px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 5px rgba(0,0,0,0.08);">
        <tr><td style="background:#e10075;padding:20px 24px;font-family:Arial,sans-serif;">
          <div style="color:#fff;font-size:20px;font-weight:bold;">🤖 AI & SAP News Intelligence Digest</div>
          <div style="color:#fdf0f6;font-size:12px;margin-top:2px;">Deutsche Telekom Manager Briefing &nbsp;|&nbsp; {_date_str()}</div>
        </td></tr>
        <tr><td style="padding:12px 24px;background:#fcfcfc;font-size:12px;color:#555;font-family:Arial,sans-serif;">
          Curated briefing on latest AI and SAP news scored for Telekom relevance. Full report attached as PDF.
        </td></tr>
        {f'''<tr><td style="padding:12px 24px;background:#f9f9f9;border-left:4px solid #e10075;font-family:Arial,sans-serif;">
          <div style="font-size:12px;font-weight:bold;color:#e10075;margin-bottom:6px;">📋 Executive Briefing</div>
          <div style="font-size:12px;color:#222;line-height:1.6;white-space:pre-line;">{executive_summary}</div>
        </td></tr>''' if executive_summary else ''}
        {ai_html}
        {sap_html}
        <tr><td style="padding:20px 24px;background:#f9f9f9;border-top:1px solid #eee;font-family:Arial,sans-serif;">
          <div style="font-size:12px;color:#333;line-height:1.7;">
            With Best Regards,<br>
            <strong>Your trusted team member "Sai"</strong>
          </div>
          <div style="margin-top:10px;font-size:9px;color:#aaa;">
            Generated automatically · Powered by Groq AI · See attached PDF for full report
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

# ── Sender ────────────────────────────────────────────────────────────────────

def get_cc_recipients() -> list[str]:
    """Find all environment variables starting with RECIPIENT_CC and return unique emails."""
    cc_list = []
    for key, val in os.environ.items():
        if key.upper().startswith("RECIPIENT_CC") and val.strip():
            # Support comma-separated emails within one secret as well
            parts = [e.strip() for e in val.split(",") if e.strip()]
            cc_list.extend(parts)
    return list(sorted(set(cc_list)))

def send_digest(articles: list[dict], executive_summary: str = "") -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]
    cc_list = get_cc_recipients()

    subject = f"Telekom AI & SAP Intelligence Digest — {_date_str()}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    html_body = _build_html(articles, executive_summary)
    msg.attach(MIMEText(html_body, "html"))

    print("[Email] Building PDF...")
    pdf_bytes = build_pdf(articles, executive_summary)
    pdf_filename = f"telekom_digest_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
    msg.attach(attachment)

    all_recipients = [recipient] + cc_list
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_password)
        smtp.sendmail(gmail_user, all_recipients, msg.as_string())

    print(f"[Email] Digest sent to {recipient} (CC: {', '.join(cc_list)}) with PDF attachment '{pdf_filename}'.")
