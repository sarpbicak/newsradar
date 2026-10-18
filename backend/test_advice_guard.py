"""Yatırım tavsiyesi tarayıcısı — doğru yakalıyor, haber dilini yanlış işaretlemiyor mu?

Çalıştır: python test_advice_guard.py
"""
from app.analysis.advice_guard import scan_assessment, scan_text

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


print("== Yakalanmalı ==")
for t in [
    "Tesla is a buy at these levels.",
    "Investors should buy before earnings.",
    "Buy now while it is cheap.",
    "We recommend buying the dip.",
    "This is a strong buy.",
    "My price target is $300.",
    "Bu hisseyi almalısın.",
    "Hisse şu seviyeden alınmalı.",
    "Hemen satın al.",
    "Hedef fiyatım 120 TL.",
    "Pozisyonunuz varsa satmalısınız.",
]:
    check(bool(scan_text(t)), f"yakalandı: {t!r}")

print("== Yakalanmamalı (haber dili / analist verisi aktarımı) ==")
for t in [
    "Analyst consensus is Strong Buy (32 of 45 analysts).",
    "Analist konsensüsü: 'strong buy' ağırlıklı.",
    "Microsoft, Activision'ı satın alma anlaşmasını tamamladı.",
    "Şirket rakibini satın aldı.",
    "Investors bought the dip after earnings.",
    "The stock was a top buy-rated name among analysts.",
    "Satın alma haberi fiyatlanmış görünüyor.",
    "Doğrulanması gereken: alım programının ölçeği.",
]:
    check(not scan_text(t), f"temiz: {t!r}")

print("== scan_assessment alanları ==")
hits = scan_assessment({
    "headline_verdict": "Temkinli olumlu.",
    "ai_take": "Haber akışı karışık.",
    "what_to_verify": ["Bilanço tarihi", "Bu seviyeden alınmalı mı?"],
    "top_drivers": ["Buy now, momentum strong"],
})
fields = sorted({h[0] for h in hits})
check(fields == ["top_drivers", "what_to_verify"], f"liste alanları da taranıyor ({fields})")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
