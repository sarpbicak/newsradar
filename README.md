# NewsRadar 📡 — Haber Akışı Bazlı Hisse Risk Analizi

Bir izleme listesindeki şirketler (public ticker + özel startup) için finansal
haberleri çeker, **her makaleyi Claude API ile analiz eder** ve bir web
panosunda risk skorları, duygu (sentiment) ve sinyalleri gösterir.

> **İlke:** Araç net bir yön belirtir (yükseliş / nötr / düşüş) + kanaat seviyesi,
> ama **haber-akışı sinyalini fiyat tahmininden ayırır**. Haberin söyleyemediğini
> (değerleme, hareketin zaten fiyatlanıp fiyatlanmadığı) açıkça belirtir ve her
> konum görüşüne bir **"önce doğrula" kontrol listesi** ekler. Gerekçesiz AL/SAT yok.

Kişisel, tek kullanıcılık bir araçtır.

---

## Mimari

```
newsradar/
├── backend/                      FastAPI + SQLite + APScheduler + Claude
│   ├── app/
│   │   ├── config.py             .env tabanlı ayarlar (anahtarlar koda gömülmez)
│   │   ├── db/                   SQLAlchemy modelleri (Entity, Article, EntityAnalysis)
│   │   ├── providers/            NewsProvider arayüzü + Finnhub (ticker) + NewsAPI (keyword)
│   │   ├── analysis/             Claude hattı: makale-başı + entity-başı yapılandırılmış çıktı
│   │   ├── api/                  FastAPI uçları (entities, refresh, dashboard, chat SSE)
│   │   ├── ingest.py             çekme + URL-hash dedupe + kalıcılaştırma
│   │   ├── refresh.py            çek→analiz orkestrasyonu
│   │   ├── scheduler.py          saatlik otomatik yenileme (aç/kapat)
│   │   ├── seed.py               varsayılan izleme listesi
│   │   └── cli.py                adım adım test CLI'ı
│   ├── requirements.txt
│   └── .env.example
└── frontend/                     React (Vite) + Tailwind + recharts
    └── src/                      Overview, EntityDetail, ArticleTable, ChatPanel, ...
```

### Temel kavramlar

- **Entity** iki tiptedir: `ticker` (public — Finnhub `/company-news`) ve `keyword`
  (startup/özel — NewsAPI `/v2/everything`). Çekme, takas edilebilir bir
  `NewsProvider` arayüzü arkasındadır.
- **Dedupe:** makaleler URL hash'e göre `(entity_id, url_hash)` çiftiyle tekilleştirilir.
  Aynı makale iki kez analiz edilmez (token tasarrufu).
- **Anahtar eksikse** o sağlayıcı zarifçe atlanır ve UI'da uyarı gösterilir — uygulama çökmez.
- **LLM:** Anthropic Claude, model `claude-sonnet-4-6`. Yapılandırılmış çıktı, zorunlu
  **tool-use** ile alınır (Sonnet 4.6 katı structured-outputs desteklemez).

### Claude analiz hattı

1. Her entity için son 48s haber çekilir (ayarlanabilir).
2. Zaten analiz edilmiş makaleler atlanır (URL hash ile) — aynı makaleye iki kez ödeme yok.
3. Yeni makaleler 10'arlı gruplar halinde tek Claude çağrısında analiz edilir.
4. **Makale-başı** yapılandırılmış JSON: `sentiment (-1..1)`, `event_type`, `risk_flags[]`,
   `impact_horizon`, `relevance (0..1; <0.3 elenir)`, `rationale (TR)`.
5. **Entity-başı** toplu değerlendirme: `risk_score (0..100)`, `sentiment_trend`,
   `top_drivers[3]`, `summary`, `stance`, `conviction`, `what_to_verify[2-4]`, `invalidation`.

---

## Kurulum & Çalıştırma

### 1) Backend (FastAPI)

```bash
cd newsradar/backend
python3 -m venv .venv && source .venv/bin/activate     # opsiyonel ama önerilir
pip install -r requirements.txt

cp .env.example .env
# .env dosyasını açıp anahtarları girin:
#   ANTHROPIC_API_KEY=sk-ant-...     (analiz için ZORUNLU)
#   FINNHUB_API_KEY=...              (ticker haberleri; yoksa atlanır)
#   NEWSAPI_KEY=...                  (keyword haberleri; yoksa atlanır)

python -m app.seed                  # varsayılan izleme listesi (TSLA, NVDA, MSFT, Anthropic, SpaceX)
uvicorn app.api.main:app --reload   # http://localhost:8000  (docs: /docs)
```

**CLI ile adım adım test (sunucu gerekmez):**

```bash
python -m app.cli status            # sağlayıcı anahtarları + izleme listesi
python -m app.cli fetch TSLA        # tek entity için haber çek + yazdır
python -m app.cli analyze TSLA      # Claude ile analiz et + JSON yazdır
```

### 2) Frontend (React + Vite)

```bash
cd newsradar/frontend
npm install
npm run dev                          # http://localhost:5173
```

Backend farklı bir adresteyse `cp .env.example .env` ile `VITE_API_BASE`'i ayarlayın.

---

## API Uçları

| Yöntem | Yol | Açıklama |
|--------|-----|----------|
| `GET/POST/DELETE` | `/entities` | İzleme listesi CRUD |
| `POST` | `/refresh` | Çek + analiz tetikle (ayrıca saatlik APScheduler; `?scheduler_enabled=` ile aç/kapat) |
| `GET` | `/entities/{id}/dashboard` | Toplu sonuç + son analiz edilmiş makaleler |
| `POST` | `/chat` | SSE streaming. Gövde: `{entity_id, messages[]}` — entity'nin son ~15 makalesi bağlam olarak enjekte edilir |
| `GET` | `/status` | Sağlayıcı anahtarı durumu + Claude + zamanlayıcı (UI uyarıları) |

---

## Frontend özellikleri

- **Genel görünüm:** entity kartları ızgarası — yön rozeti (yükseliş/nötr/düşüş) +
  kanaat, renk kodlu risk skoru (0–100), duygu göstergesi, trend oku, risk bayrağı
  çipleri, son güncelleme.
- **Entity detay:** özet, yön + kanaat, ana etkenler, **"önce doğrula" kontrol listesi**,
  invalidation satırı, duygu grafiği (recharts) ve makale tablosu (risk_flag / event_type
  filtreli, tıklanabilir başlık).
- **Sohbet paneli:** o entity'nin haberleri hakkında Claude ile streaming konuşma.
- **İzleme listesi yöneticisi:** ticker/keyword tip seçiciyle ekle/çıkar.
- Global **Yenile** düğmesi (yükleniyor durumuyla), footer notu:
  *"Haber akışı bazlı sinyal — fiyat tahmini değil, önce doğrula."*
- Koyu, sade fintech estetiği.

---

## Kalite / dayanıklılık

- Hat, tek tek API hatalarında hayatta kalır: hata loglanır, gerisi devam eder
  (bir kaynak/entity çökse bile yenileme tamamlanır).
- `.env` yoksa/eksikse ilgili adım zarifçe atlanır; UI uyarı gösterir.
- Type hint'ler ve docstring'ler; küçük modüller (`providers/`, `analysis/`, `api/`, `db/`).
- Seed script'i varsayılan izleme listesini ekler.

## Notlar

- NewsAPI ücretsiz katmanı ~24s gecikmelidir — v1 için kabul edilebilir; analiz bunu
  dikkate alır ve "haber zaten fiyatlanmış olabilir" uyarısını üretir.
- Bu bir yatırım tavsiyesi değildir; haber akışı sinyalidir. Önce doğrulayın.
