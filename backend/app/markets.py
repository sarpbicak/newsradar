"""Sembolün borsası, ülkesi ve para birimi — Finnhub sembol son eki kuralından (SAP.DE, ASELS.IS,
7203.T). Son eki olmayan sembol ABD'dir.

Sağlayıcı seçimi buna dayanır: ABD için mevcut kaynaklar (Finnhub fiyat/haber, FMP hedef);
diğer pazarlarda fiyat/analist yuvası BOŞ (ücretli kaynak eklenmedi → "veri yok"), haberler GDELT.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    code: str            # "US" ya da son ek ("DE", "IS", "T")
    exchange: str        # insan-okur borsa adı
    country_tr: str
    country_en: str
    currency: str        # ISO 4217 (fiyat kaynağı geldiğinde gösterim bu birimle; dönüşüm yok)
    news_lang: str       # haber dili ipucu (en/de/tr)

    @property
    def is_us(self) -> bool:
        return self.code == "US"

    def country(self, lang: str) -> str:
        return self.country_en if lang == "en" else self.country_tr


US = Market("US", "NYSE / Nasdaq", "ABD", "United States", "USD", "en")

# Finnhub son eki → pazar. Kaynak: Finnhub sembol biçimi (Ticker.ExchangeCode).
_SUFFIX: dict[str, Market] = {m.code: m for m in (
    Market("IS", "Borsa İstanbul", "Türkiye", "Türkiye", "TRY", "tr"),
    Market("DE", "XETRA", "Almanya", "Germany", "EUR", "de"),
    Market("F", "Frankfurt", "Almanya", "Germany", "EUR", "de"),
    Market("VI", "Wiener Börse", "Avusturya", "Austria", "EUR", "de"),
    Market("SW", "SIX Swiss Exchange", "İsviçre", "Switzerland", "CHF", "de"),
    Market("AS", "Euronext Amsterdam", "Hollanda", "Netherlands", "EUR", "en"),
    Market("PA", "Euronext Paris", "Fransa", "France", "EUR", "en"),
    Market("BR", "Euronext Brüksel", "Belçika", "Belgium", "EUR", "en"),
    Market("LS", "Euronext Lizbon", "Portekiz", "Portugal", "EUR", "en"),
    Market("MI", "Borsa Italiana", "İtalya", "Italy", "EUR", "en"),
    Market("MC", "Bolsa de Madrid", "İspanya", "Spain", "EUR", "en"),
    Market("L", "Londra (LSE)", "Birleşik Krallık", "United Kingdom", "GBP", "en"),
    Market("ST", "Nasdaq Stockholm", "İsveç", "Sweden", "SEK", "en"),
    Market("HE", "Nasdaq Helsinki", "Finlandiya", "Finland", "EUR", "en"),
    Market("CO", "Nasdaq Kopenhag", "Danimarka", "Denmark", "DKK", "en"),
    Market("OL", "Oslo Børs", "Norveç", "Norway", "NOK", "en"),
    Market("WA", "GPW (Varşova)", "Polonya", "Poland", "PLN", "en"),
    Market("AT", "Atina Borsası", "Yunanistan", "Greece", "EUR", "en"),
    Market("TO", "Toronto (TSX)", "Kanada", "Canada", "CAD", "en"),
    Market("V", "TSX Venture", "Kanada", "Canada", "CAD", "en"),
    Market("T", "Tokyo", "Japonya", "Japan", "JPY", "en"),
    Market("HK", "Hong Kong", "Hong Kong", "Hong Kong", "HKD", "en"),
    Market("KS", "Kore Borsası", "Güney Kore", "South Korea", "KRW", "en"),
    Market("SS", "Şanghay", "Çin", "China", "CNY", "en"),
    Market("SZ", "Shenzhen", "Çin", "China", "CNY", "en"),
    Market("TW", "Tayvan", "Tayvan", "Taiwan", "TWD", "en"),
    Market("SI", "Singapur (SGX)", "Singapur", "Singapore", "SGD", "en"),
    Market("AX", "Avustralya (ASX)", "Avustralya", "Australia", "AUD", "en"),
    Market("NS", "Hindistan (NSE)", "Hindistan", "India", "INR", "en"),
    Market("BO", "Bombay (BSE)", "Hindistan", "India", "INR", "en"),
    Market("SA", "B3 (São Paulo)", "Brezilya", "Brazil", "BRL", "en"),
    Market("MX", "Meksika Borsası", "Meksika", "Mexico", "MXN", "en"),
)}


def suffix_of(symbol: str) -> str | None:
    """ABD dışı son ek (ASELS.IS → IS, 7203.T → T); son ek yoksa None (ABD).
    Sınıf harfli ABD sembolleri (BRK.B) ABD sayılır: son ek bilinen bir borsa değilse."""
    s = (symbol or "").strip().upper()
    if "." not in s:
        return None
    suf = s.rsplit(".", 1)[-1]
    return suf if suf in _SUFFIX else None


def market_of(symbol: str) -> Market:
    suf = suffix_of(symbol)
    return _SUFFIX[suf] if suf else US


def base_symbol(symbol: str) -> str:
    """Borsa son eki olmadan sembol (THYAO.IS → THYAO); ABD sembolü olduğu gibi."""
    s = (symbol or "").strip().upper()
    return s.rsplit(".", 1)[0] if suffix_of(s) else s
