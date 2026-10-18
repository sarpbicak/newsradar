"""Sır maskeleme — log/hata metinlerinde anahtar sızmaz.

Doğrular:
  (A) Anthropic anahtarı TÜRÜNDEN bağımsız maskelenir (sk-ant-api03-…, sk-ant-usr-…,
      sk-ant-admin01-…, türsüz sk-ant-…); tür öneki görünür kalır
  (B) OpenRouter (sk-or-v1-) ve NVIDIA (nvapi-) anahtarları
  (C) URL query parametreleri (token=, apiKey=, apikey=)
  (D) normal metin değişmez
  (E) install_log_masking: başka logger'dan (alt logger, httpx) yayılan kayıtlar ve
      %-args ile biçimlenen mesajlar da maskelenir; httpx/httpx2 WARNING'e çekilir
Çalıştır: python test_secret_masking.py
"""
import io
import logging

from app.security import install_log_masking, mask_secrets, mask_url_secrets

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


TAIL = "AbCdEf0123456789_xyz-QwErTy9876543210abcdEFGH"  # sahte anahtar gövdesi

print("== A: Anthropic anahtar türleri ==")
for prefix in ("sk-ant-usr-", "sk-ant-api03-", "sk-ant-admin01-"):
    key = prefix + TAIL
    out = mask_secrets(f"auth failed for {key} (401)")
    check(TAIL not in out and f"{prefix}***" in out, f"{prefix}… maskelendi → {out!r}")
out = mask_secrets("key=sk-ant-" + TAIL)
check(TAIL not in out, f"türsüz sk-ant-… maskelendi → {out!r}")

print("== B: diğer sağlayıcılar ==")
for prefix in ("sk-or-v1-", "nvapi-"):
    out = mask_secrets(f"Bearer {prefix}{TAIL}")
    check(TAIL not in out and f"{prefix}***" in out, f"{prefix}… maskelendi")

print("== C: URL query parametreleri ==")
url = "GET https://finnhub.io/api/v1/quote?symbol=TSLA&token=d9fSECRET123&x=1"
check(mask_secrets(url) == "GET https://finnhub.io/api/v1/quote?symbol=TSLA&token=***&x=1", "token=")
check("SECRET" not in mask_secrets("https://newsapi.org/v2/everything?q=a&apiKey=557SECRET"), "apiKey=")
check(mask_url_secrets is mask_secrets, "eski ad (mask_url_secrets) aynı fonksiyon")

print("== D: normal metin ==")
for t in ("Tesla Q3 teslimatı 486.532 araç.", "task-ant-colony and sk-antenna", "", None):
    check(mask_secrets(t) == t, f"değişmedi: {t!r}")

print("== E: log filtresi ==")
buf = io.StringIO()
root = logging.getLogger()
for h in list(root.handlers):
    root.removeHandler(h)
handler = logging.StreamHandler(buf)
root.addHandler(handler)
root.setLevel(logging.INFO)
install_log_masking()
install_log_masking()  # idempotent
check(sum(1 for f in handler.filters if type(f).__name__ == "SecretMaskingFilter") == 1,
      "filtre handler'a bir kez eklendi")
logging.getLogger("newsradar.claude").error("Claude hatası: key %s geçersiz", "sk-ant-usr-" + TAIL)
logging.getLogger("newsradar.providers").warning("URL: %s", "https://x.io/a?apikey=BqtSECRET")
out = buf.getvalue()
check(TAIL not in out and "sk-ant-usr-***" in out, "alt logger + %-args: sk-ant-usr maskelendi")
check("BqtSECRET" not in out and "apikey=***" in out, "alt logger: query anahtarı maskelendi")
check(logging.getLogger("httpx").level == logging.WARNING
      and logging.getLogger("httpx2").level == logging.WARNING, "httpx ve httpx2 WARNING'de")
logging.getLogger("httpx").info("HTTP Request: GET https://finnhub.io/?token=d9fLEAK")
check("d9fLEAK" not in buf.getvalue(), "httpx INFO URL logu hiç yazılmadı")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
