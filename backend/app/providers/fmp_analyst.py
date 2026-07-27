"""FMP (Financial Modeling Prep) analist HEDEF FİYAT sağlayıcısı.

Finnhub ücretsiz katmanda hedef fiyat vermiyor (403 premium). FMP ücretsiz katmanı
`price-target-consensus` ucuyla GERÇEK analist hedef konsensüsünü sağlar:
  { symbol, targetHigh, targetLow, targetConsensus, targetMedian }

ÖNEMLİ (accuracy): Bu YALNIZCA hedef fiyat sağlar (al/tut/sat tavsiyesi Finnhub'dan).
Döndürülen her rakam GERÇEK analist verisidir — NewsRadar/Claude ÜRETMEZ. Veri yoksa
(403/402/401 premium ya da boş) None döner; ASLA tahminle doldurulmaz.

Docs: https://site.financialmodelingprep.com/developer/docs (price-target-consensus)
Uç sürümleri değişebildiği için önce `stable`, sonra `api/v4` denenir.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..db.models import Entity
from .base import AnalystProvider, AnalystRating, AnalystResult

# Denenecek uçlar (sırayla): (insan-okur ad, tam URL şablonu).
_CONSENSUS_ENDPOINTS = [
    ("stable", "https://financialmodelingprep.com/stable/price-target-consensus"),
    ("v4", "https://financialmodelingprep.com/api/v4/price-target-consensus"),
]


def _num(v) -> float | None:
    """Güvenli sayı dönüşümü — 0/negatif/geçersiz → None (hedef fiyat pozitif olmalı)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


class FMPAnalystProvider(AnalystProvider):
    """FMP hedef fiyat konsensüsü. Yalnızca hedef alanlarını doldurur (tavsiye Finnhub'da)."""

    name = "fmp-target"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        return bool(self._settings.fmp_api_key)

    def fetch(self, entity: Entity) -> AnalystResult:
        if not self.is_available():
            return AnalystResult(
                provider=self.name,
                warning="FMP_API_KEY tanımlı değil — hedef fiyat atlandı.",
            )

        symbol = entity.query.upper().strip()
        last_warning = None
        for label, url in _CONSENSUS_ENDPOINTS:
            try:
                resp = httpx.get(
                    url,
                    params={"symbol": symbol, "apikey": self._settings.fmp_api_key},
                    timeout=15.0,
                )
            except httpx.HTTPError as exc:
                last_warning = f"FMP bağlantı hatası ({label}): {exc}"
                continue

            # 401/402/403 → anahtar geçersiz ya da uç premium (ücretsiz katman kapsamıyor).
            if resp.status_code in (401, 402, 403):
                last_warning = (
                    f"FMP hedef fiyat erişilemedi ({resp.status_code}) — ücretsiz katman "
                    f"bu ucu kapsamıyor olabilir ({symbol})."
                )
                continue
            if resp.status_code != 200:
                last_warning = f"FMP hedef fiyat hatası ({resp.status_code}) — {symbol}."
                continue

            try:
                data = resp.json()
            except ValueError:
                last_warning = f"FMP hedef fiyat çözümleme hatası ({symbol})."
                continue

            # Yanıt liste ([{...}]) ya da nesne ({...}) olabilir; ilk kaydı al.
            if isinstance(data, list):
                row = data[0] if data else None
            elif isinstance(data, dict):
                # FMP hata gövdesi de dict olabilir ("Error Message"); hedef alanı yoksa geç.
                row = data if ("targetConsensus" in data or "targetMedian" in data) else None
                if row is None and "Error Message" in data:
                    last_warning = f"FMP: {str(data['Error Message'])[:120]} ({symbol})."
            else:
                row = None

            if not row:
                last_warning = f"{symbol} için FMP hedef verisi yok (kapsam dışı olabilir)."
                continue

            consensus = _num(row.get("targetConsensus"))
            median = _num(row.get("targetMedian"))
            mean = consensus if consensus is not None else median
            if mean is None:
                last_warning = f"{symbol} için FMP hedef değeri boş."
                continue

            return AnalystResult(
                provider=f"{self.name}:{label}",
                rating=AnalystRating(
                    target_high=_num(row.get("targetHigh")),
                    target_low=_num(row.get("targetLow")),
                    target_mean=mean,
                    target_median=median,
                    target_consensus=consensus,
                    # Tavsiye (al/tut/sat) FMP'den DEĞİL — Finnhub'da; burada 0 kalır.
                ),
            )

        return AnalystResult(provider=self.name, warning=last_warning or "FMP hedef yok.")
