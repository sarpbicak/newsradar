// Basit i18n katmanı: tr/en sözlükleri + useI18n() hook + dil-farkında tarih/zaman.
// Kodda sabit metin kalmasın diye tüm arayüz metinleri buradan t(key) ile çekilir.
import React, { createContext, useContext } from "react";

// Modül-düzeyi geçerli dil — hook kullanamayan yardımcılar (timeAgo/fmtDate) buradan okur.
let _lang = "tr";
export function getLang() {
  return _lang;
}

const STR = {
  // ---- Header / genel ----
  "app.subtitle": { tr: "haber akışı · risk paneli", en: "news feed · risk panel" },
  "header.refresh": { tr: "Yenile", en: "Refresh" },
  "header.refreshing": { tr: "Yenileniyor… ({done}/{total})", en: "Refreshing… ({done}/{total})" },
  "header.starting": { tr: "Başlatılıyor…", en: "Starting…" },
  "header.howItWorks": { tr: "Nasıl çalışır?", en: "How it works?" },
  "header.admin": { tr: "Admin", en: "Admin" },
  "header.dashboard": { tr: "Pano", en: "Dashboard" },
  "header.createAccount": { tr: "Hesap oluştur", en: "Create account" },
  "header.login": { tr: "Giriş yap", en: "Log in" },
  "header.logout": { tr: "Çıkış (misafire dön)", en: "Log out (back to guest)" },
  "header.guest": { tr: "Misafir", en: "Guest" },
  "header.menu": { tr: "menü", en: "menu" },
  "header.home": { tr: "Ana sayfaya dön", en: "Go to home" },

  // ---- Pano / genel görünüm ----
  "ov.todayImportant": { tr: "Bugün önemli", en: "Today's highlights" },
  "ov.following": { tr: "Takip ettiklerin", en: "Your watchlist" },
  "ov.noChangeToday": { tr: "Bugün önemli bir değişiklik yok — tüm varlıklar aşağıdaki listede.", en: "Nothing major today — all items are in the list below." },
  "ov.list": { tr: "Liste ({n})", en: "List ({n})" },
  "ov.sort": { tr: "Sırala:", en: "Sort:" },
  "ov.sortRisk": { tr: "Risk", en: "Risk" },
  "ov.sortAlpha": { tr: "Alfabetik", en: "Alphabetical" },
  "ov.suggestions": { tr: "Öneriler ({n})", en: "Suggestions ({n})" },
  "ov.watchlist": { tr: "İzleme listesi ({n})", en: "Watchlist ({n})" },
  "ov.emptyTitle": { tr: "Henüz takip ettiğin şirket yok", en: "You're not following any company yet" },
  "ov.emptyBody": { tr: "İzleme listene şirket ekleyerek başla. Aşağıdakilerden biriyle hemen deneyebilir ya da aşağıdaki formdan istediğini ekleyebilirsin.", en: "Start by adding a company to your watchlist. Try one below, or add your own with the form." },
  "ov.emptyNote": { tr: "Eklediğin şirketler bir sonraki yenilemede analiz edilir.", en: "Companies you add are analyzed on the next refresh." },

  // ---- Kart ----
  "card.noAnalysis": { tr: "analiz yok", en: "no analysis" },
  "card.noAnalysisYet": { tr: "Henüz analiz yok", en: "No analysis yet" },
  "card.pressRefresh": { tr: "Henüz analiz yok — {refresh}'e basın.", en: "No analysis yet — press {refresh}." },
  "card.now": { tr: "şimdi", en: "now" },
  "card.analystTarget": { tr: "analist hedefi", en: "analyst target" },
  "card.noTarget": { tr: "hedef yok", en: "no target" },
  "card.noPrice": { tr: "Fiyat verisi yok", en: "No price data" },
  "card.newsOnly": { tr: "sadece haber analizi", en: "news analysis only" },
  "card.privateShort": { tr: "Özel şirket — sadece haber analizi", en: "Private company — news analysis only" },
  "card.private": { tr: "Özel şirket — borsada işlem görmüyor", en: "Private company — not publicly traded" },
  "card.privateBody": { tr: "Halka açık olmadığı için fiyat ve analist hedefi yok. Değerlendirme yalnızca haber akışına dayanıyor.", en: "Not public, so no price or analyst target. The assessment is based only on the news flow." },
  "card.topDriver": { tr: "Öne çıkan:", en: "Top driver:" },
  "card.analysts": { tr: "{n} analist", en: "{n} analysts" },
  "card.buyLean": { tr: "Al ağırlıklı", en: "Buy-leaning" },
  "card.sellLean": { tr: "Sat ağırlıklı", en: "Sell-leaning" },
  "card.holdLean": { tr: "Tut ağırlıklı", en: "Hold-leaning" },
  "card.horizon": { tr: "{h} vade", en: "{h} horizon" },
  "card.newsCount": { tr: "{n} haber", en: "{n} news" },
  "card.stanceChanged": { tr: "yön değişti", en: "stance changed" },
  // Katman 1 kartındaki "neden önemli" rozeti (backend kanonik anahtar döndürür)
  "pr.stance_reversed": { tr: "yön değişti", en: "stance reversed" },
  "pr.stance_clarified": { tr: "yön netleşti", en: "stance clarified" },
  "pr.risk_jump": { tr: "risk sıçraması", en: "risk jump" },
  "pr.sharp_move": { tr: "sert hareket", en: "sharp move" },
  "pr.divergence": { tr: "ayrışma", en: "divergence" },

  // ---- Etiketler (yön/vade/kanıt/trend) ----
  "stance.bullish": { tr: "YÜKSELİŞ", en: "BULLISH" },
  "stance.neutral": { tr: "NÖTR", en: "NEUTRAL" },
  "stance.bearish": { tr: "DÜŞÜŞ", en: "BEARISH" },
  "horizon.short": { tr: "Kısa", en: "Short" },
  "horizon.medium": { tr: "Orta", en: "Medium" },
  "horizon.long": { tr: "Uzun", en: "Long" },
  "evidence.strong": { tr: "Güçlü", en: "Strong" },
  "evidence.medium": { tr: "Orta", en: "Medium" },
  "evidence.weak": { tr: "Zayıf", en: "Weak" },
  "conviction.low": { tr: "düşük", en: "low" },
  "conviction.medium": { tr: "orta", en: "medium" },
  "conviction.high": { tr: "yüksek", en: "high" },
  "conviction.suffix": { tr: "kanaat", en: "conviction" },
  "gauge.sentiment": { tr: "duygu", en: "sentiment" },
  "trend.improving": { tr: "iyileşiyor", en: "improving" },
  "trend.stable": { tr: "stabil", en: "stable" },
  "trend.deteriorating": { tr: "kötüleşiyor", en: "deteriorating" },
  "sig.strongNeg": { tr: "Güçlü olumsuz", en: "Strongly negative" },
  "sig.neg": { tr: "Olumsuz", en: "Negative" },
  "sig.neutral": { tr: "Nötr", en: "Neutral" },
  "sig.pos": { tr: "Olumlu", en: "Positive" },
  "sig.strongPos": { tr: "Güçlü olumlu", en: "Strongly positive" },
  "sig.overall": { tr: "Genel sinyal", en: "Overall signal" },

  // ---- Detay ----
  "detail.back": { tr: "genel görünüm", en: "overview" },
  "detail.tabSummary": { tr: "Özet", en: "Summary" },
  "detail.tabCharts": { tr: "Grafikler", en: "Charts" },
  "detail.tabNews": { tr: "Haberler", en: "News" },
  "detail.tabAnalysts": { tr: "Analistler", en: "Analysts" },
  "detail.dir": { tr: "Yön", en: "Direction" },
  "detail.horizon": { tr: "Vade", en: "Horizon" },
  "detail.evidence": { tr: "Kanıt", en: "Evidence" },
  "detail.target": { tr: "hedef", en: "target" },
  "detail.noPrice": { tr: "Fiyat verisi yok (ABD dışı borsa olabilir).", en: "No price data (may be a non-US exchange)." },
  "detail.notPublic": { tr: "Borsada işlem görmüyor (özel şirket).", en: "Not publicly traded (private company)." },
  "detail.loading": { tr: "Yükleniyor…", en: "Loading…" },
  "detail.error": { tr: "Hata: {msg}", en: "Error: {msg}" },
  "detail.noAnalysisBox": { tr: "Bu varlık için henüz analiz yok. Üstteki {refresh} düğmesine basın.", en: "No analysis for this item yet. Press the {refresh} button above." },
  "detail.langNote": { tr: "Bu değerlendirme {lang} üretildi.", en: "This assessment was generated in {lang}." },
  "lang.tr.name": { tr: "Türkçe", en: "Turkish" },
  "lang.en.name": { tr: "İngilizce", en: "English" },
  "detail.articlesN": { tr: "{n} makale", en: "{n} articles" },
  "detail.analyzedN": { tr: "{n} analiz", en: "{n} analyzed" },
  "detail.prefilteredN": { tr: "{n} elenen", en: "{n} filtered" },
  "detail.pendingN": { tr: "{n} bekliyor", en: "{n} pending" },

  // ---- Özet sekmesi ----
  "sum.aiTake": { tr: "AI ne düşünüyor?", en: "What the AI thinks" },
  "sum.aiDisclaimer": { tr: "Bu bir yorum, yatırım tavsiyesi değil — kararlar sana ait.", en: "This is a view, not investment advice — decisions are yours." },
  "sum.basedOn": { tr: "{n} habere dayalı", en: "based on {n} news" },
  "sum.previous": { tr: "önceki: {v}", en: "previous: {v}" },
  "sum.drivers": { tr: "Ana etkenler", en: "Key drivers" },
  "sum.verify": { tr: "✓ Harekete geçmeden önce doğrula", en: "✓ Verify before acting" },
  "sum.invalidation": { tr: "Görüşü çürütecek olay", en: "What would invalidate this" },
  "sum.riskLabel": { tr: "Risk", en: "Risk" },
  "sum.riskScale": { tr: "0–100", en: "0–100" },
  "sum.riskNone": { tr: "analiz yok", en: "no analysis" },

  // ---- Grafikler ----
  "chart.range": { tr: "Aralık:", en: "Range:" },
  "chart.r7": { tr: "7g", en: "7d" },
  "chart.r30": { tr: "30g", en: "30d" },
  "chart.r90": { tr: "90g", en: "90d" },
  "chart.rangeAll": { tr: "Tümü", en: "All" },
  "chart.riskSent": { tr: "Risk ve haber havası", en: "Risk & news sentiment" },
  "chart.risk": { tr: "risk", en: "risk" },
  "chart.newsMood": { tr: "haber havası", en: "news sentiment" },
  "chart.price": { tr: "Fiyat geçmişi", en: "Price history" },
  "chart.priceNote": { tr: "Not: Fiyat yalnızca haberin fiyatlanıp fiyatlanmadığını görmek için — hedef/tahmin değil.", en: "Note: Price only shows whether the news is priced in — not a target/forecast." },
  "chart.need2days": { tr: "Grafik için en az 2 gün veri gerekli — bir sonraki yenilemelerde dolacak.", en: "At least 2 days of data are needed — it fills in on upcoming refreshes." },
  "chart.noDataRange": { tr: "Bu aralıkta veri yok, daha geniş bir aralık seçin.", en: "No data in this range — pick a wider range." },
  "chart.riskNeed2": { tr: "Risk verisi için en az 2 tarama gerekir.", en: "Risk needs at least 2 scans." },
  "chart.showRiskSent": { tr: "Risk ve haber havasını göster", en: "Show risk & news sentiment" },
  "chart.hideRiskSent": { tr: "Risk ve haber havasını gizle", en: "Hide risk & news sentiment" },
  "chart.tipRisk": { tr: "risk {v}", en: "risk {v}" },
  "chart.tipMood": { tr: "havası {v}", en: "mood {v}" },

  // ---- Sohbet ----
  "chat.title": { tr: "{name} — haberleri AI ile konuş", en: "{name} — discuss the news with AI" },
  "chat.placeholderHint": { tr: "Bu varlığın haber akışını sor: “Şu an nasıl konumlanmalıyım?”, “En büyük risk ne?”", en: "Ask about this item's news: “How should I position now?”, “What's the biggest risk?”" },
  "chat.send": { tr: "Gönder", en: "Send" },
  "chat.thinking": { tr: "Düşünüyor…", en: "Thinking…" },
  "chat.ask": { tr: "Bir soru sor…", en: "Ask a question…" },

  // ---- İzleme listesi formu ----
  "wl.title": { tr: "İzleme Listesi", en: "Watchlist" },
  "wl.type": { tr: "Tip", en: "Type" },
  "wl.typeTicker": { tr: "ticker (ABD hissesi)", en: "ticker (US stock)" },
  "wl.typeKeyword": { tr: "keyword (şirket/konu)", en: "keyword (company/topic)" },
  "wl.fieldName": { tr: "Ad", en: "Name" },
  "wl.nameSearch": { tr: "Ad (ara)", en: "Name (search)" },
  "wl.nameTerm": { tr: "Ad / arama terimi", en: "Name / search term" },
  "wl.symbol": { tr: "Sembol", en: "Symbol" },
  "wl.language": { tr: "Dil", en: "Language" },
  "wl.add": { tr: "Ekle", en: "Add" },
  "wl.adding": { tr: "Ekleniyor…", en: "Adding…" },
  "wl.searching": { tr: "Aranıyor…", en: "Searching…" },
  "wl.missing": { tr: "Eksik: {fields}", en: "Missing: {fields}" },
  "wl.notFound": { tr: "Bulunamadı — Türk/Avrupa şirketleri için tip olarak keyword seçip dili ayarlayın.", en: "Not found — for Turkish/European companies pick keyword and set the language." },
  "wl.remove": { tr: "Kaldır", en: "Remove" },
  "lang.en": { tr: "İngilizce", en: "English" },
  "lang.tr": { tr: "Türkçe", en: "Turkish" },
  "lang.de": { tr: "Almanca", en: "German" },
  "lang.fr": { tr: "Fransızca", en: "French" },

  // ---- Bildirimler / hatalar ----
  "notice.refreshed": { tr: "Yenilendi: {parts}.", en: "Refreshed: {parts}." },
  "notice.newArticles": { tr: "{n} yeni makale", en: "{n} new articles" },
  "notice.newArticles_one": { tr: "1 yeni makale", en: "1 new article" },
  "notice.analyzedRun": { tr: "bu taramada {n} analiz", en: "{n} analyzed this run" },
  "notice.filteredOut": { tr: "{n} elendi", en: "{n} filtered out" },
  "notice.queued": { tr: "{n} makale sonraki taramada", en: "{n} queued for next refresh" },
  "notice.queued_one": { tr: "1 makale sonraki taramada", en: "1 queued for next refresh" },
  "notice.warnings": { tr: " {n} uyarı.", en: " {n} warnings." },
  "notice.warnings_one": { tr: " 1 uyarı.", en: " 1 warning." },
  "notice.infos": { tr: "{n} bilgi (kota koruması)", en: "{n} notes (quota protection)" },
  "notice.infos_one": { tr: "1 bilgi (kota koruması)", en: "1 note (quota protection)" },
  "notice.refreshFail": { tr: "Yenileme başlatılamadı: {msg}", en: "Couldn't start refresh: {msg}" },
  "notice.scanRunning": { tr: "Tarama sürüyor… {done}/{total} şirket işlendi. İlk yenileme birikmiş haberler nedeniyle uzun sürebilir; bittiğinde pano otomatik güncellenecek — sayfayı kapatabilirsiniz.", en: "Scan in progress… {done}/{total} companies processed. The first refresh can take a while due to accumulated news; the panel updates automatically when done — you can close the page." },
  "notice.scanStarting": { tr: "Yenileme başlatılıyor…", en: "Starting refresh…" },
  "notice.analyzing": { tr: "{name} analiz ediliyor…", en: "Analyzing {name}…" },
  "notice.scanWorking": { tr: "Haberler taranıyor…", en: "Scanning news…" },
  "notice.scanDone": { tr: "Tamamlandı · {parts}", en: "Done · {parts}" },
  "notice.budgetExceeded": { tr: "Günlük analiz kapasitesi doldu — yeni analiz bugünlük durduruldu, yarın tekrar deneyin. Mevcut değerlendirmeler görüntülenmeye devam eder.", en: "Daily analysis capacity is full — new analysis is paused for today, try tomorrow. Existing assessments remain visible." },
  "notice.analysisUnavailable": { tr: "Analiz servisi geçici olarak kullanılamıyor (kapasite limiti). Mevcut veriler gösteriliyor.", en: "The analysis service is temporarily unavailable (capacity limit). Showing existing data." },
  "notice.sessionFail": { tr: "Oturum başlatılamadı: {msg}", en: "Couldn't start session: {msg}" },
  "notice.sessionFailShort": { tr: "Oturum başlatılamadı. Sayfayı yenileyin.", en: "Couldn't start session. Refresh the page." },
  "notice.apiFail": { tr: "API'ye bağlanılamadı: {msg}. Backend çalışıyor mu?", en: "Couldn't reach the API: {msg}. Is the backend running?" },
  "notice.refreshQuotaFull": { tr: "Günlük yenileme hakkın doldu {label}. Yarın tekrar deneyebilirsin.", en: "Your daily refresh limit is used up {label}. Try again tomorrow." },
  "notice.entityAdded": { tr: "{name} izleme listesine eklendi — bir sonraki yenilemede analiz edilecek.", en: "{name} added to your watchlist — it'll be analyzed on the next refresh." },
  "pull.pull": { tr: "Yenilemek için çek", en: "Pull to refresh" },
  "pull.release": { tr: "Bırak → yenile", en: "Release → refresh" },

  // ---- Backend mesajları (kod + parametre; backend/app/messages.py ile birebir) ----
  "src.finnhub_news": { tr: "Finnhub", en: "Finnhub" },
  "src.finnhub_price": { tr: "Finnhub fiyat", en: "Finnhub price" },
  "src.finnhub_analyst": { tr: "Finnhub analist", en: "Finnhub analyst" },
  "src.fmp_target": { tr: "FMP hedef fiyat", en: "FMP price target" },
  "src.newsapi": { tr: "NewsAPI", en: "NewsAPI" },
  "msg.refresh_running": { tr: "Yenileme zaten çalışıyor.", en: "A refresh is already running." },
  "msg.llm_key_missing": { tr: "Analiz motorunun anahtarı tanımlı değil.", en: "The analysis engine's API key is not set." },
  "msg.budget_exceeded": { tr: "Günlük analiz bütçesi dolu — yeni analiz yapılmadı, yarın tekrar deneyin.", en: "The daily analysis budget is used up — no new analysis was run; try again tomorrow." },
  "msg.budget_stopped": { tr: "Günlük analiz bütçesi tarama sırasında doldu — kalan analizler yarın yapılacak.", en: "The daily analysis budget ran out during the scan — the rest will be analyzed tomorrow." },
  "msg.analysis_unavailable": { tr: "Analiz servisi geçici olarak kullanılamıyor — çekilen haberler kaydedildi.", en: "The analysis service is temporarily unavailable — fetched news was saved." },
  "msg.no_provider": { tr: "'{type}' tipi için haber kaynağı yok.", en: "No news source for type '{type}'." },
  "msg.news_fresh_skip": { tr: "Son {hours} saatte çekildi — NewsAPI atlandı (mevcut veri kullanılıyor).", en: "Fetched in the last {hours} hours — NewsAPI skipped (using existing data)." },
  "msg.newsapi_quota": { tr: "NewsAPI kotası doldu ({used}/{limit}), {hours} saat sonra sıfırlanır.", en: "NewsAPI quota used up ({used}/{limit}), resets in {hours} hours." },
  "msg.db_write_error": { tr: "Kaydetme hatası, bu şirket atlandı ({error}).", en: "Save error, this company was skipped ({error})." },
  "msg.key_missing": { tr: "{key} tanımlı değil — atlandı.", en: "{key} is not set — skipped." },
  "msg.http_error": { tr: "{source} hatası ({status}) — {symbol} atlandı.", en: "{source} error ({status}) — {symbol} skipped." },
  "msg.connection_error": { tr: "{source} bağlantı hatası.", en: "{source} connection error." },
  "msg.no_data": { tr: "{symbol} için {source} verisi yok.", en: "No {source} data for {symbol}." },
  "msg.bad_response": { tr: "{source} beklenmeyen yanıt döndü ({symbol}).", en: "{source} returned an unexpected response ({symbol})." },
  "msg.newsapi_status": { tr: "NewsAPI hatası: {message}", en: "NewsAPI error: {message}" },
  "msg.provider_error": { tr: "{source} beklenmeyen hata.", en: "{source} unexpected error." },
  "msg.prefilter_error": { tr: "Ön-filtre hatası, bu şirket atlandı.", en: "Pre-filter error, this company was skipped." },
  "msg.llm_zero": { tr: "Analiz motoru hiç sonuç döndürmedi ({batches} grup gönderildi).", en: "The analysis engine returned no results ({batches} batches sent)." },
  "msg.llm_zero_one": { tr: "Analiz motoru hiç sonuç döndürmedi (1 grup gönderildi).", en: "The analysis engine returned no results (1 batch sent)." },
  "msg.article_truncated": { tr: "Bir makale analiz edilemedi (yanıt kesildi).", en: "One article couldn't be analyzed (response cut off)." },
  "msg.split_limit": { tr: "{count} makale atlandı (yanıt hâlâ kesiliyor).", en: "{count} articles skipped (response still cut off)." },
  "msg.split_limit_one": { tr: "1 makale atlandı (yanıt hâlâ kesiliyor).", en: "1 article skipped (response still cut off)." },
  "msg.batch_error": { tr: "Bir makale grubu analiz edilemedi.", en: "One batch of articles couldn't be analyzed." },
  "msg.assessment_failed": { tr: "Değerlendirme üretilemedi ({lang}).", en: "Couldn't generate the assessment ({lang})." },
  "msg.entity_error": { tr: "Analiz sırasında beklenmeyen hata, bu şirket atlandı.", en: "Unexpected error during analysis, this company was skipped." },

  // ---- Footer / gizlilik ----
  "footer.disclaimer": { tr: "Haber akışı bazlı sinyal — değerleme veya fiyat tahmini değil. Analist hedefleri Finnhub konsensüs verisidir. Kararlar size aittir.", en: "News-based signal — not a valuation or price forecast. Analyst targets are Finnhub consensus data. Decisions are yours." },
  "footer.privacy": { tr: "Gizlilik", en: "Privacy" },
  "privacy.intro": { tr: "NewsRadar kişisel veriyi en aza indirir. Misafir kullanımda hesap ya da e-posta istemeyiz.", en: "NewsRadar minimizes personal data. In guest use we ask for no account or email." },
  "privacy.collectTitle": { tr: "Ne topluyoruz?", en: "What we collect" },
  "privacy.c1": { tr: "Cihaz kimliği: tarayıcına yazılan rastgele bir kimlik (HttpOnly cookie). Kim olduğunu söylemez; yalnızca aynı cihazda listeni hatırlamak için.", en: "Device ID: a random identifier stored in your browser (HttpOnly cookie). It doesn't say who you are; it only remembers your list on this device." },
  "privacy.cIp": { tr: "IP adresin yalnızca kötüye kullanımı önlemek için (hız sınırı, giriş kilidi, başarısız giriş kaydı) en fazla {days} gün tutulur, kimlik olarak kullanılmaz; süre dolunca otomatik silinir.", en: "Your IP address is kept for at most {days} days and only to prevent abuse (rate limiting, login lockout, failed-login records); it is not used as identity and is deleted automatically afterwards." },
  "privacy.c2": { tr: "İzleme listen ve kullanım olayların (hangi şirketleri ekledin, ne zaman yeniledin) — hizmeti sağlamak ve kötüye kullanımı önlemek için.", en: "Your watchlist and usage events (which companies you added, when you refreshed) — to run the service and prevent abuse." },
  "privacy.c3": { tr: "Hesap oluşturursan: seçtiğin kullanıcı adı ve şifrenin güvenli özeti (düz şifre asla saklanmaz).", en: "If you create an account: your chosen username and a secure hash of your password (the plain password is never stored)." },
  "privacy.retainTitle": { tr: "Ne kadar saklıyoruz?", en: "How long we keep it" },
  "privacy.retainBody": { tr: "Cihaz kimliği cookie'si ~1 yıl. Kötüye kullanım önleme kayıtlarındaki IP adresleri {days} gün sonra otomatik silinir. Misafir verilerini silmek için hesap menüsünden çıkış yapıp cookie'yi silmen yeterli.", en: "The device-ID cookie lasts ~1 year. IP addresses in abuse-prevention records are deleted automatically after {days} days. To erase guest data, log out and clear the cookie." },
  "privacy.contactPre": { tr: "Kayıtlı hesabını ya da verilerini sildirmek için", en: "To delete your registered account or your data, write to" },
  "privacy.contactPost": { tr: " adresine yazabilirsin.", en: "." },
  "privacy.contactNone": { tr: "Kayıtlı hesabını sildirmek için site yöneticisiyle iletişime geçebilirsin.", en: "To delete your registered account, contact the site admin." },
  "privacy.llmGeneric": { tr: "LLM sağlayıcımız", en: "our LLM provider" },
  "privacy.hostingGeneric": { tr: "bir bulut sağlayıcı", en: "a cloud provider" },
  "privacy.thirdParty": { tr: "Üçüncü taraflar: haber ve analist verisi Finnhub/NewsAPI/FMP'den gelir; analiz için metin {llm} üzerinden işlenir. Site {hosting} üzerinde barındırılır; sunucu kayıtları (istek IP'leri dahil) barındırma sağlayıcısının saklama kurallarına tabidir. Verini reklam için kullanmayız, satmayız.", en: "Third parties: news and analyst data come from Finnhub/NewsAPI/FMP; text is processed for analysis via {llm}. The site is hosted on {hosting}; server logs (including request IPs) follow the hosting provider's retention rules. We don't use your data for ads, and we don't sell it." },

  // ---- Geri bildirim ----
  "fb.button": { tr: "Geri bildirim", en: "Feedback" },
  "fb.title": { tr: "Düşüncelerin benim için değerli", en: "Your thoughts matter to me" },
  "fb.body": { tr: "NewsRadar'ı geliştirmek için geri bildirime ihtiyacım var. Ne işe yaradı, ne eksik, ne kafa karıştırıcı — hepsini duymak isterim.", en: "I need feedback to improve NewsRadar. What worked, what's missing, what's confusing — I'd love to hear it all." },
  "fb.placeholder": { tr: "Ne düşünüyorsun?", en: "What do you think?" },
  "fb.contact": { tr: "E-posta / kullanıcı adı (zorunlu değil)", en: "Email / username (optional)" },
  "fb.contactNote": { tr: "Cevap istersen iletişim bırak — zorunlu değil.", en: "Leave contact if you'd like a reply — optional." },
  "fb.send": { tr: "Gönder", en: "Send" },
  "fb.sending": { tr: "Gönderiliyor…", en: "Sending…" },
  "fb.thanks": { tr: "Teşekkürler, okuyacağım.", en: "Thanks, I'll read it." },
  "fb.builtBy": { tr: "Bu aracı {name} yaptı.", en: "{name} built this tool." },
  "fb.fail": { tr: "Gönderilemedi, lütfen tekrar deneyin.", en: "Couldn't send, please try again." },

  // ---- Dil modalı ----
  "langmodal.title": { tr: "Dil / Language", en: "Dil / Language" },
  "langmodal.subtitle": { tr: "Arayüz ve değerlendirmeler bu dilde gösterilir.", en: "The interface and assessments are shown in this language." },

  // ---- Tutorial ----
  "tut.skip": { tr: "Geç", en: "Skip" },
  "tut.back": { tr: "Geri", en: "Back" },
  "tut.next": { tr: "İleri", en: "Next" },
  "tut.start": { tr: "Başla", en: "Start" },
  "tut.writeFeedback": { tr: "Geri bildirim yaz", en: "Write feedback" },
  "tut.s1.title": { tr: "NewsRadar'a hoş geldin!", en: "Welcome to NewsRadar!" },
  "tut.s1.body": { tr: "Takip etmek istediğin şirketleri ekle; gerisini biz hallederiz. Haberleri toplar, yapay zekâ ile analiz eder ve sana özetleriz.", en: "Add the companies you want to follow; we'll handle the rest. We gather the news, analyze it with AI, and summarize it for you." },
  "tut.s2.title": { tr: "Şirketleri nasıl eklersin?", en: "How do you add companies?" },
  "tut.s2.body": { tr: "Halka açık şirketler için ticker seç (Tesla → TSLA). Özel şirketler ya da konular için keyword kullan (SpaceX, OpenAI). Arama kutusu sembolü senin için bulur.", en: "For public companies pick a ticker (Tesla → TSLA). For private companies or topics use a keyword (SpaceX, OpenAI). The search box finds the symbol for you." },
  "tut.s3.title": { tr: "Yapay zekâ ne yapar?", en: "What does the AI do?" },
  "tut.s3.body": { tr: "Her şirket için haberleri okur ve tek bir değerlendirme üretir: haberlerin genel havası (olumlu/olumsuz), ne kadar güvenilir olduğu ve — borsadakiler için — analist hedef fiyatı.", en: "For each company it reads the news and produces a single assessment: the overall mood (positive/negative), how reliable it is, and — for public ones — the analyst target price." },
  "tut.note.title": { tr: "Önemli not", en: "Important note" },
  "tut.s4.title": { tr: "Düşüncelerini merak ediyorum", en: "I'd love your thoughts" },
  "tut.s4.builtBy": { tr: "Bu aracı {name} yaptı.", en: "{name} built this tool." },
  "tut.s4.feedbackInvite": { tr: "NewsRadar'ı geliştirmek için geri bildirime ihtiyacım var. Sağ alttaki Geri bildirim butonundan ne düşündüğünü yazabilirsin — ne işe yaradı, ne eksik, ne kafa karıştırıcı.", en: "I need feedback to improve NewsRadar. Use the Feedback button at the bottom right to tell me what you think — what worked, what's missing, what's confusing." },
  "tut.s4.disclaimer": { tr: "Bu bir yatırım tavsiyesi değil, haber akışının özetidir. Hedef fiyatlar gerçek analistlerden gelir, bizim tahminimiz değildir. Kararlar sana aittir.", en: "This is not investment advice — it's a summary of the news flow. Target prices come from real analysts, not our forecast. Decisions are yours." },

  // ---- Hesap modalı ----
  "acc.upgradeTitle": { tr: "Hesap oluştur", en: "Create account" },
  "acc.loginTitle": { tr: "Giriş yap", en: "Log in" },
  "acc.upgradeBody": { tr: "Listeni kaybetmeden kalıcı bir hesaba geç. Kullanıcı adı + şifre belirle.", en: "Turn your session into a permanent account without losing your list. Set a username + password." },
  "acc.loginBody": { tr: "Mevcut hesabınla giriş yap.", en: "Log in with your existing account." },
  "acc.username": { tr: "Kullanıcı adı", en: "Username" },
  "acc.password": { tr: "Şifre", en: "Password" },
  "acc.submitUpgrade": { tr: "Hesap oluştur", en: "Create account" },
  "acc.submitLogin": { tr: "Giriş yap", en: "Log in" },
  "acc.working": { tr: "İşleniyor…", en: "Working…" },
  "acc.toLogin": { tr: "Zaten hesabın var mı? Giriş yap", en: "Already have an account? Log in" },
  "acc.toUpgrade": { tr: "Hesabın yok mu? Oluştur", en: "No account? Create one" },
  "common.close": { tr: "Kapat", en: "Close" },

  // ---- Öneriler ----
  "sug.title": { tr: "Bunları da izlemek ister misin?", en: "Want to watch these too?" },
  "sug.subtitle": { tr: "Haberlerinde sık geçen, izleme listende olmayan şirketler.", en: "Companies often mentioned in your news that aren't on your watchlist." },
  "sug.mentioned": { tr: "{n} haberde geçti", en: "seen in {n} news" },
  "sug.inNews": { tr: "{names} haberlerinde", en: "in {names} news" },
  "sug.addTicker": { tr: "↳ ticker olarak eklenecek (ABD borsası)", en: "↳ will be added as ticker (US exchange)" },
  "sug.addKeyword": { tr: "↳ keyword{lang} olarak eklenecek", en: "↳ will be added as keyword{lang}" },
  "sug.add": { tr: "+ Ekle", en: "+ Add" },
  "sug.hide": { tr: "Gizle", en: "Hide" },

  // ---- Haber tablosu ----
  "art.filter": { tr: "Filtre:", en: "Filter:" },
  "art.allFlags": { tr: "tüm risk bayrakları", en: "all risk flags" },
  "art.allEvents": { tr: "tüm olay tipleri", en: "all event types" },
  "art.clear": { tr: "temizle", en: "clear" },
  "art.count": { tr: "{n} haber", en: "{n} news" },
  "art.none": { tr: "Bu filtreyle haber yok.", en: "No news with this filter." },
  "art.title": { tr: "Başlık", en: "Title" },
  "art.source": { tr: "Kaynak", en: "Source" },
  "art.sentiment": { tr: "Duygu", en: "Sentiment" },
  "art.event": { tr: "Olay", en: "Event" },
  "art.risks": { tr: "Riskler", en: "Risks" },
  "art.rationale": { tr: "Gerekçe", en: "Rationale" },
  "art.noSource": { tr: "kaynak yok", en: "no source" },
  "art.sources": { tr: "{n} kaynak", en: "{n} sources" },
  "sent.pos": { tr: "olumlu", en: "positive" },
  "sent.neg": { tr: "olumsuz", en: "negative" },
  "sent.neu": { tr: "nötr", en: "neutral" },

  // ---- Analist verisi ----
  "an.title": { tr: "Analist verisi", en: "Analyst data" },
  "an.segStrongBuy": { tr: "Güçlü Al", en: "Strong Buy" },
  "an.segBuy": { tr: "Al", en: "Buy" },
  "an.segHold": { tr: "Tut", en: "Hold" },
  "an.segSell": { tr: "Sat", en: "Sell" },
  "an.segStrongSell": { tr: "Güçlü Sat", en: "Strong Sell" },
  "an.targetConsensus": { tr: "hedef konsensüsü (FMP)", en: "target consensus (FMP)" },
  "an.low": { tr: "düşük", en: "low" },
  "an.avg": { tr: "ort", en: "avg" },
  "an.high": { tr: "yüksek", en: "high" },
  "an.curPrice": { tr: "Güncel fiyat", en: "Current price" },
  "an.avgTarget": { tr: "Ortalama hedef", en: "Average target" },
  "an.source": { tr: "Analist tavsiyesi Finnhub, hedef fiyat FMP verisidir{period} — NewsRadar'ın tahmini değildir.", en: "Analyst ratings from Finnhub, target price from FMP{period} — not a NewsRadar forecast." },
  "an.noKeyword": { tr: "Bu şirket borsada işlem görmüyor (özel şirket) — hedef fiyat ve analist verisi yok. Değerlendirme sadece haber akışına dayanıyor.", en: "This company is not publicly traded (private) — no target price or analyst data. The assessment relies only on the news flow." },
  "an.noExchange": { tr: "Bu borsa için fiyat ve analist verisi kaynağımızda yok (ör. Türkiye/Avrupa borsaları). Değerlendirme haber akışına dayanıyor.", en: "We don't have price or analyst data for this exchange (e.g. Turkish/European exchanges). The assessment relies on the news flow." },
  "an.noAnalyst": { tr: "Bu şirket için analist tavsiyesi ve hedef fiyatı şu an kaynağımızda yok. Değerlendirme haber akışına dayanıyor.", en: "We currently have no analyst ratings or target price for this company. The assessment relies on the news flow." },

  // ---- Admin paneli ----
  "adm.loading": { tr: "Kullanım verileri yükleniyor…", en: "Loading usage data…" },
  "adm.title": { tr: "Kullanım paneli", en: "Usage panel" },
  "adm.userLimit": { tr: "Kullanıcı (kayıt/limit)", en: "Users (count/limit)" },
  "adm.limitReached": { tr: "⚠ limit aşıldı!", en: "⚠ limit exceeded!" },
  "adm.regLimit": { tr: "kayıt sınırı", en: "registration limit" },
  "adm.unlimited": { tr: "sınırsız", en: "unlimited" },
  "adm.activeToday": { tr: "Bugün aktif", en: "Active today" },
  "adm.atLeast1": { tr: "en az 1 eylem", en: "at least 1 action" },
  "adm.refreshesToday": { tr: "Bugünkü yenileme", en: "Refreshes today" },
  "adm.mostPopular": { tr: "En popüler", en: "Most popular" },
  "adm.views": { tr: "{n} görüntüleme", en: "{n} views" },
  "adm.unreadFb": { tr: "Okunmamış geri bildirim", en: "Unread feedback" },
  "adm.unreadWaiting": { tr: "okunmayı bekliyor", en: "waiting to be read" },
  "adm.allRead": { tr: "hepsi okundu", en: "all read" },
  "adm.costBudget": { tr: "Bugünkü harcama (bütçe)", en: "Spend today (budget)" },
  "adm.budgetFull": { tr: "⚠ günlük kapasite doldu", en: "⚠ daily capacity full" },
  "adm.dailyCap": { tr: "günlük tavan", en: "daily cap" },
  "adm.cacheHit": { tr: "Önbellek isabeti", en: "Cache hit rate" },
  "adm.cacheHitHint": { tr: "son 7 gün, girdi token'ları", en: "last 7 days, input tokens" },
  "adm.modelBreakdown": { tr: "Model kırılımı (son 30 gün)", en: "Model breakdown (last 30 days)" },
  "adm.mbModel": { tr: "Model", en: "Model" },
  "adm.mbCalls": { tr: "Çağrı", en: "Calls" },
  "adm.mbInOut": { tr: "Girdi / çıktı", en: "Input / output" },
  "adm.cost7": { tr: "7 günlük maliyet", en: "7-day cost" },
  "adm.cost30": { tr: "30 günlük maliyet", en: "30-day cost" },
  "adm.tokenK": { tr: "{n}K token", en: "{n}K tokens" },
  // Sistem sağlığı (LLM)
  "adm.healthTitle": { tr: "Sistem sağlığı (analiz motoru)", en: "System health (analysis engine)" },
  "adm.healthOk": { tr: "Çalışıyor — son analiz çağrısı başarılı.", en: "Operational — last analysis call succeeded." },
  "adm.healthQuota": { tr: "Kota/bakiye limiti — analiz servisi geçici olarak durdu.", en: "Quota/balance limit — analysis service is temporarily down." },
  "adm.healthErrors": { tr: "Son analizde hata var — logları kontrol edin.", en: "Errors in the last analysis — check the logs." },
  "adm.healthNoData": { tr: "Henüz analiz çağrısı yapılmadı.", en: "No analysis calls yet." },
  "adm.healthLastOk": { tr: "Son başarılı çağrı", en: "Last successful call" },
  "adm.healthNever": { tr: "hiç", en: "never" },
  "adm.healthQuota24h": { tr: "Son 24s kota hatası", en: "Quota errors (24h)" },
  "adm.healthErr24h": { tr: "Son 24s diğer hata", en: "Other errors (24h)" },
  "adm.healthCode": { tr: "Son kod", en: "Last code" },
  "adm.totalEntities": { tr: "Toplam şirket", en: "Total companies" },
  "adm.poolUnique": { tr: "havuzda benzersiz", en: "unique in pool" },
  "adm.mostFollowed": { tr: "En çok takip edilen şirketler", en: "Most followed companies" },
  "adm.poolUniqueN": { tr: "Havuzda {n} benzersiz şirket", en: "{n} unique companies in pool" },
  "adm.noneFollow": { tr: "Henüz kimse şirket takip etmiyor.", en: "No one follows any company yet." },
  "adm.person": { tr: "{n} kişi", en: "{n} people" },
  "adm.mostViewed": { tr: "En çok görüntülenen şirketler", en: "Most viewed companies" },
  "adm.thUser": { tr: "Kullanıcı", en: "User" },
  "adm.thReg": { tr: "Kayıt", en: "Registered" },
  "adm.thLastLogin": { tr: "Son giriş", en: "Last login" },
  "adm.thLogin": { tr: "Giriş", en: "Logins" },
  "adm.thRefresh": { tr: "Yenileme", en: "Refreshes" },
  "adm.thTotal": { tr: "Toplam eylem", en: "Total actions" },
  "adm.thActive": { tr: "Son aktiflik", en: "Last active" },
  "adm.thAction": { tr: "İşlem", en: "Action" },
  "adm.pwReset": { tr: "Şifre", en: "Password" },
  "adm.pwResetTitle": { tr: "Şifre sıfırla (geçici şifre üret)", en: "Reset password (generate temp)" },
  "adm.you": { tr: "siz", en: "you" },
  "adm.delete": { tr: "Sil", en: "Delete" },
  "adm.deleting": { tr: "Siliniyor…", en: "Deleting…" },
  "adm.deleteTitle": { tr: "Kullanıcıyı ve tüm verilerini sil", en: "Delete user and all their data" },
  "adm.never": { tr: "hiç", en: "never" },
  "adm.feedbackTitle": { tr: "Geri bildirimler", en: "Feedback" },
  "adm.unread": { tr: "{n} okunmamış", en: "{n} unread" },
  "adm.totalN": { tr: "{n} toplam", en: "{n} total" },
  "adm.noFeedback": { tr: "Henüz geri bildirim yok.", en: "No feedback yet." },
  "adm.anon": { tr: "anonim", en: "anonymous" },
  "adm.read": { tr: "Okundu", en: "Read" },
  "adm.readMark": { tr: "okundu", en: "read" },
  "adm.eventBreakdown": { tr: "Eylem dökümü", en: "Action breakdown" },
  "adm.noActions": { tr: "Henüz eylem yok.", en: "No actions yet." },
  "adm.topViewed": { tr: "En çok baktığı şirketler", en: "Most viewed companies" },
  "adm.watchlistN": { tr: "İzleme listesi ({n})", en: "Watchlist ({n})" },
  "adm.noWatch": { tr: "Takip ettiği şirket yok.", en: "Follows no company." },
  "adm.registered": { tr: "Kayıt: {d}", en: "Registered: {d}" },
  "adm.lastLoginLine": { tr: "Son giriş: {d}", en: "Last login: {d}" },
  "adm.recentActions": { tr: "Son eylemler", en: "Recent actions" },
  "adm.noRecords": { tr: "Kayıt yok.", en: "No records." },
  "adm.close": { tr: "✕ kapat", en: "✕ close" },
  "adm.confirmDelete": { tr: "{u} kullanıcısını ve tüm verilerini silmek istediğinize emin misiniz?", en: "Delete user {u} and all their data?" },
  "adm.confirmReset": { tr: "{u} kullanıcısının şifresi sıfırlansın mı? Geçici bir şifre üretilecek.", en: "Reset {u}'s password? A temporary password will be generated." },
  "adm.tempPrompt": { tr: "{u} için geçici şifre (kopyalayın, kullanıcıya iletin — bir daha gösterilmez):", en: "Temporary password for {u} (copy and share — shown once):" },
  "adm.deleteFail": { tr: "Silinemedi: {m}", en: "Couldn't delete: {m}" },
  "adm.resetFail": { tr: "Sıfırlanamadı: {m}", en: "Couldn't reset: {m}" },
  "adm.markFail": { tr: "İşaretlenemedi: {m}", en: "Couldn't mark: {m}" },
  "adm.errPrefix": { tr: "Hata: {m}", en: "Error: {m}" },
  // Eylem tipleri
  "ev.login": { tr: "giriş", en: "login" },
  "ev.login_failed": { tr: "başarısız giriş", en: "failed login" },
  "ev.register_failed": { tr: "başarısız kayıt", en: "failed registration" },
  "ev.refresh": { tr: "yenileme", en: "refresh" },
  "ev.view_entity": { tr: "görüntüleme", en: "view" },
  "ev.add_entity": { tr: "şirket ekleme", en: "add company" },
  "ev.remove_entity": { tr: "şirket çıkarma", en: "remove company" },
  "ev.chat": { tr: "sohbet", en: "chat" },
  "ev.add_suggestion": { tr: "öneri ekleme", en: "add suggestion" },
  "ev.dismiss_suggestion": { tr: "öneri gizleme", en: "dismiss suggestion" },
  "ev.delete_user": { tr: "kullanıcı silme", en: "delete user" },
  "ev.password_reset": { tr: "şifre sıfırlama", en: "password reset" },
  "ev.feedback_sent": { tr: "geri bildirim", en: "feedback" },
};

const Ctx = createContext({ lang: "tr", t: (k) => k, setLang: () => {} });

export function I18nProvider({ lang, setLang, children }) {
  _lang = lang;
  // <html lang> UI diliyle eşleşsin — CSS text-transform:uppercase Türkçe kuralını
  // (i→İ) yalnızca lang=tr'de uygulasın; İngilizce'de "RİSK" değil "RISK" görünsün.
  if (typeof document !== "undefined") document.documentElement.lang = lang;
  const t = (key, vars) => {
    const entry = STR[key];
    return render(key, lang, vars);
  };
  return <Ctx.Provider value={{ lang, t, setLang }}>{children}</Ctx.Provider>;
}

export function useI18n() {
  return useContext(Ctx);
}

// Hook KULLANMAYAN çevirici (ui.jsx gibi düz fonksiyonlar için) — geçerli dili
// getLang()'dan okur. React ağacı yeniden render olduğunda güncel dili yansıtır.
export function tt(key, vars) {
  return render(key, _lang, vars);
}

// Ortak çeviri: TEKİL/ÇOĞUL — vars.n === 1 ise ve "<anahtar>_one" tanımlıysa o kullanılır
// ("1 warning" / "2 warnings"; Türkçe'de çoğul eki olmadığından _one çoğu zaman gereksiz).
function render(key, lang, vars) {
  const one = vars && vars.n === 1 ? STR[`${key}_one`] : null;
  const entry = one || STR[key];
  let s = entry ? entry[lang] ?? entry.tr : key;
  if (vars) for (const k in vars) s = s.split(`{${k}}`).join(String(vars[k]));
  return s;
}

// Yenileme özeti sayaçları → metin parçaları ("X yeni makale · bu taramada Y analiz ·
// Z elendi · W sonraki taramada"). Y = LLM'e gidip yanıtı alınan makale (kuyruktan gelenler
// dahil — "0 yeni" iken "Y analiz" olabilmesinin sebebi); Z = kopya/ön-filtre + ilgisiz.
export function refreshParts(sm, t) {
  if (!sm) return [];
  const llm = sm.llm_articles ?? (sm.analyzed || 0) + (sm.discarded || 0);
  const filtered = (sm.prefiltered || 0) + (sm.discarded || 0);
  const parts = [t("notice.newArticles", { n: sm.fetched_new || 0 }), t("notice.analyzedRun", { n: llm })];
  if (filtered) parts.push(t("notice.filteredOut", { n: filtered }));
  if (sm.queued) parts.push(t("notice.queued", { n: sm.queued }));
  return parts;
}

// Backend mesajı ({code, entity, params}) → kullanıcının dilinde metin. Kodlar:
// backend/app/messages.py. `source` parametresi src.<kod> ile çevrilir. Bilinmeyen kod
// ham haliyle gösterilir (sessizce kaybolmaz). Eski düz string mesajlar olduğu gibi döner.
export function fmtMsg(m, t) {
  if (m == null) return "";
  if (typeof m === "string") return m;
  const p = { ...(m.params || {}) };
  if (p.source != null) {
    const k = `src.${p.source}`;
    const v = t(k);
    if (v !== k) p.source = v;
  }
  if (p.lang != null) p.lang = String(p.lang).toUpperCase();
  // Tekil/çoğul seçimi için sayıyı n'e taşı (count / batches).
  if (p.n == null) {
    const c = p.count ?? p.batches;
    if (typeof c === "number") p.n = c;
  }
  const key = `msg.${m.code}`;
  let s = t(key, p);
  if (s === key) s = `${m.code} ${JSON.stringify(m.params || {})}`;
  return m.entity ? `[${m.entity}] ${s}` : s;
}

// API zaman damgası → Date. Backend UTC-aware ("+00:00") gönderir; eski/ekisiz bir değer
// gelirse UTC KABUL EDİLİR (tarayıcı ekisiz ISO'yu yerel saat sanıyordu → Berlin'de 2 sa fark).
export function parseUtc(v) {
  if (v == null || v instanceof Date || typeof v === "number") return new Date(v);
  const s = String(v);
  const hasTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(hasTz || !s.includes("T") ? s : `${s}Z`);
}

// Dil-farkında tarih/zaman yardımcıları (locale'e göre biçim).
const LOCALE = () => (_lang === "tr" ? "tr-TR" : "en-US");
export function fmtDate(iso) {
  if (!iso) return "—";
  return parseUtc(iso).toLocaleDateString(LOCALE(), { day: "2-digit", month: "short" });
}
export function fmtDateTime(iso) {
  if (!iso) return "—";
  return parseUtc(iso).toLocaleString(LOCALE());
}
export function timeAgo(iso) {
  if (!iso) return _lang === "tr" ? "hiç" : "never";
  const diff = (Date.now() - parseUtc(iso).getTime()) / 1000;
  const tr = _lang === "tr";
  if (diff < 60) return tr ? "az önce" : "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}${tr ? " dk önce" : "m ago"}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}${tr ? " sa önce" : "h ago"}`;
  return `${Math.floor(diff / 86400)}${tr ? " gün önce" : "d ago"}`;
}
