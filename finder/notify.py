"""Alertas por email (SMTP). Configuración por variables de entorno:

SMTP_HOST (default smtp.gmail.com), SMTP_PORT (465), SMTP_USER, SMTP_PASSWORD, ALERT_TO.
Con Gmail, SMTP_PASSWORD es una "contraseña de aplicación", no la contraseña de la cuenta.
"""
import html
import os
import smtplib
from email.message import EmailMessage


def _money(v):
    return "—" if v is None else "$" + f"{v:,.0f}".replace(",", ".")


def _card(item):
    l = item["listing"]
    tags = [item["zone"]]
    if item.get("cochera"):
        tags.append("cochera")
    if item.get("pileta"):
        tags.append("pileta")
    tags += item.get("notes", [])
    img = l["images"][0] if l.get("images") else ""
    m2 = f'{l["m2_cubiertos"]:.0f} m²' if l.get("m2_cubiertos") else "? m²"
    dorm = f'{l["dormitorios"]} dorm.' if l.get("dormitorios") is not None else ""
    return f"""
<tr><td style="padding:12px 0;border-bottom:1px solid #e5e5e5">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:top;padding-right:12px">
      {'<img src="%s" width="140" style="border-radius:6px;display:block">' % html.escape(img) if img else ''}
    </td>
    <td style="vertical-align:top;font-family:Arial,sans-serif;font-size:14px;color:#222">
      <div style="font-size:16px;font-weight:bold">
        <a href="{html.escape(l['url'])}" style="color:#0b57d0;text-decoration:none">{html.escape(l['title'] or l['address'])}</a>
      </div>
      <div style="margin:4px 0">{html.escape(l['address'])}</div>
      <div><b>{_money(item['total_ars'])}</b> total · {m2} · {dorm}</div>
      <div style="color:#666;margin-top:4px">{html.escape(' · '.join(t for t in tags if t))}</div>
      <div style="color:#666">Puntaje {item['score']}/100 · {html.escape(l['source'].upper())} · {html.escape(l.get('publisher') or '')}</div>
    </td>
  </tr></table>
</td></tr>"""


def render(items):
    rows = "".join(_card(i) for i in items)
    return f"""<html><body style="margin:0;padding:16px;background:#fff">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px">
<tr><td style="font-family:Arial,sans-serif;font-size:18px;font-weight:bold;padding-bottom:8px">
{len(items)} {'departamento nuevo' if len(items) == 1 else 'departamentos nuevos'}
</td></tr>{rows}</table></body></html>"""


def send(items):
    user, pwd, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"), os.environ.get("ALERT_TO")
    if not (user and pwd and to):
        raise RuntimeError("Faltan SMTP_USER, SMTP_PASSWORD o ALERT_TO para mandar el mail")
    best = items[0]
    msg = EmailMessage()
    subject = f"🏠 {_money(best['total_ars'])} · {best['listing']['address']}"
    if len(items) > 1:
        subject += f" y {len(items) - 1} más"
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content("\n\n".join(f"{i['listing']['title']}\n{i['listing']['url']}" for i in items))
    msg.add_alternative(render(items), subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pwd)
        s.send_message(msg)
