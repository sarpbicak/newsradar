"""E-posta gönderimi — tek soyutlama, iki arka uç (EMAIL_BACKEND).

- console: e-postayı log'a yazar (geliştirme ve testler; hiçbir yere gönderilmez).
- ses: Amazon SES v2 (boto3 `sesv2.send_email`). Kimlik bilgileri boto3'ün varsayılan
  zincirinden gelir — EC2'de instance rolü; koda/ortama ANAHTAR konmaz. boto3 yalnızca bu
  arka uç seçilince içe aktarılır (geliştirme ortamında gerekmez).

Gönderim hatası kullanıcı akışını bozmaz: loglanır, çağıran False alır (ör. "tekrar gönder").
Testler `sent` listesinden (console) son gönderilenleri okuyabilir.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from .config import get_settings

logger = logging.getLogger("newsradar.mail")


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class ConsoleBackend:
    """Log'a yazar (bağlantıdaki token log maskelemesiyle *** görünür). Üretim dışında tam ileti
    stderr'e de basılır ki yerelde bağlantı tıklanabilsin. Son 50 ileti bellekte (testler)."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, msg: EmailMessage) -> bool:
        self.sent = [*self.sent[-49:], msg]
        logger.info("[mail:console] alıcı=%s konu=%r\n%s", msg.to, msg.subject, msg.text)
        if get_settings().trusted_proxy != "caddy":  # üretim (Caddy arkası) değil
            print(f"[mail:console] {msg.to} · {msg.subject}\n{msg.text}\n", file=sys.stderr)
        return True


class SesBackend:
    """Amazon SES v2. Gönderen adres EMAIL_FROM, bölge EMAIL_SES_REGION."""

    name = "ses"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3  # noqa: PLC0415 — yalnızca ses arka ucunda gerekir
            except ImportError as exc:
                raise RuntimeError("boto3 kurulu değil (requirements.txt'e ekleyin; DEPLOY_AWS.md Ek C6)") from exc

            self._client = boto3.client("sesv2", region_name=get_settings().email_ses_region)
        return self._client

    def send(self, msg: EmailMessage) -> bool:
        s = get_settings()
        try:
            self._get_client().send_email(
                FromEmailAddress=s.email_from,
                Destination={"ToAddresses": [msg.to]},
                Content={"Simple": {
                    "Subject": {"Data": msg.subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": msg.text, "Charset": "UTF-8"},
                             "Html": {"Data": msg.html, "Charset": "UTF-8"}},
                }},
            )
            logger.info("[mail:ses] gönderildi (konu=%r)", msg.subject)
            return True
        except Exception as exc:  # noqa: BLE001 — gönderim hatası akışı bozmasın
            # Alıcı adresi log'a yazılmaz (kişisel veri); yalnızca hata türü.
            detail = str(exc) if isinstance(exc, RuntimeError) else exc.__class__.__name__
            logger.error("[mail:ses] gönderilemedi: %s", detail)
            return False


_backend = None


def get_mailer():
    """Yapılandırılmış arka ucun tek örneği (EMAIL_BACKEND değişirse yenisi)."""
    global _backend
    want = get_settings().email_backend
    if _backend is None or _backend.name != want:
        _backend = SesBackend() if want == "ses" else ConsoleBackend()
    return _backend


def send_email(msg: EmailMessage) -> bool:
    return get_mailer().send(msg)
