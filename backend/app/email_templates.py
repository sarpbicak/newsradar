"""E-posta şablonları (TR/EN/DE) — sade HTML + düz metin. Almanca metinler app/locales'ten.

Sitenin açık temasıyla uyumlu: beyaz kart, ince kenar, vurgu rengi tek düğmede; logo METİN
("NewsRadar"), görsel/izleme pikseli yok. Kullanıcı girdisi (kullanıcı adı) HTML'e kaçışlı girer.
"""

from __future__ import annotations

from html import escape

from .locales import email_de
from .mailer import EmailMessage

_ACCENT = "#0E7490"   # açık temadaki vurgu (AA, beyaz zeminde)
_INK = "#0B0F14"
_MUTED = "#5B6573"
_LINE = "#E3E7EC"

TEXTS = {
    "verify": {
        "tr": {
            "subject": "NewsRadar: e-posta adresini doğrula",
            "hello": "Merhaba {name},",
            "body": "NewsRadar hesabına bu e-posta adresini ekledin. Adresinin sana ait olduğunu doğrulamak için düğmeye bas.",
            "button": "E-postamı doğrula",
            "expires": "Bağlantı 24 saat geçerli ve yalnızca bir kez kullanılabilir.",
            "ignore": "Bu isteği sen yapmadıysan bu e-postayı yok sayabilirsin; hesabında bir şey değişmez.",
        },
        "en": {
            "subject": "NewsRadar: verify your email address",
            "hello": "Hi {name},",
            "body": "You added this email address to your NewsRadar account. Press the button to confirm it's yours.",
            "button": "Verify my email",
            "expires": "The link is valid for 24 hours and can be used once.",
            "ignore": "If you didn't request this, you can ignore this email; nothing changes on your account.",
        },
    },
    "reset": {
        "tr": {
            "subject": "NewsRadar: şifre sıfırlama",
            "hello": "Merhaba {name},",
            "body": "Hesabın için şifre sıfırlama istendi. Yeni şifre belirlemek için düğmeye bas.",
            "button": "Yeni şifre belirle",
            "expires": "Bağlantı 1 saat geçerli ve yalnızca bir kez kullanılabilir. Şifre değişince diğer cihazlardaki oturumların kapanır.",
            "ignore": "Bu isteği sen yapmadıysan bu e-postayı yok sayabilirsin; şifren değişmez.",
        },
        "en": {
            "subject": "NewsRadar: reset your password",
            "hello": "Hi {name},",
            "body": "A password reset was requested for your account. Press the button to set a new password.",
            "button": "Set a new password",
            "expires": "The link is valid for 1 hour and can be used once. Changing your password signs you out on other devices.",
            "ignore": "If you didn't request this, you can ignore this email; your password stays the same.",
        },
    },
}
_FOOTER = {
    "tr": "Bu e-posta NewsRadar hesabınla ilgili olduğu için gönderildi. Pazarlama e-postası göndermiyoruz.",
    "en": "You're receiving this because it concerns your NewsRadar account. We don't send marketing email.",
}


_FIELDS = ("subject", "hello", "body", "button", "expires", "ignore")


def _texts(kind: str, lang: str) -> tuple[dict, str]:
    """(şablon metinleri, alt not). DE: app/locales/email.de.json (tek kaynak: frontend de.json)."""
    if lang == "de":
        de = email_de()
        return {f: de[f"email.{kind}.{f}"] for f in _FIELDS}, de["email.footer"]
    lang = "en" if lang == "en" else "tr"
    return TEXTS[kind][lang], _FOOTER[lang]


def render(kind: str, lang: str, name: str, link: str) -> tuple[str, str, str]:
    """(konu, düz metin, html)."""
    lang = lang if lang in ("tr", "en", "de") else "tr"
    t, footer = _texts(kind, lang)
    hello = t["hello"].format(name=name)
    text = "\n\n".join([
        "NewsRadar", hello, t["body"], link, t["expires"], t["ignore"], "—", footer,
    ])
    e = escape
    html = f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{e(t["subject"])}</title></head>
<body style="margin:0;padding:24px 12px;background:#F7F8FA;font-family:-apple-system,Segoe UI,Inter,Helvetica,Arial,sans-serif;color:{_INK};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#FFFFFF;border:1px solid {_LINE};border-radius:12px;">
<tr><td style="padding:28px 28px 8px;font-size:18px;font-weight:600;letter-spacing:-0.01em;">News<span style="color:{_ACCENT};">Radar</span></td></tr>
<tr><td style="padding:8px 28px 0;font-size:15px;line-height:1.6;">
<p style="margin:0 0 12px;">{e(hello)}</p>
<p style="margin:0 0 20px;">{e(t["body"])}</p>
<p style="margin:0 0 20px;"><a href="{e(link)}" style="display:inline-block;background:{_ACCENT};color:#FFFFFF;text-decoration:none;font-weight:600;padding:11px 18px;border-radius:8px;">{e(t["button"])}</a></p>
<p style="margin:0 0 8px;font-size:13px;color:{_MUTED};">{e(t["expires"])}</p>
<p style="margin:0 0 20px;font-size:13px;color:{_MUTED};">{e(t["ignore"])}</p>
<p style="margin:0 0 4px;font-size:12px;color:{_MUTED};word-break:break-all;">{e(link)}</p>
</td></tr>
<tr><td style="padding:16px 28px 24px;border-top:1px solid {_LINE};font-size:12px;color:{_MUTED};">{e(footer)}</td></tr>
</table></td></tr></table></body></html>"""
    return t["subject"], text, html


def message(kind: str, lang: str, to: str, name: str, link: str) -> EmailMessage:
    subject, text, html = render(kind, lang, name, link)
    return EmailMessage(to=to, subject=subject, text=text, html=html)
