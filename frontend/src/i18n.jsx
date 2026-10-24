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
  "header.refreshing": { tr: "Yenileniyor {done}/{total}", en: "Refreshing {done}/{total}" },
  "header.refreshLeft": { tr: "Yenile · {n} hak", en: "Refresh · {n} left" },
  "header.resetsTomorrow": { tr: "Yarın yenilenir", en: "Resets tomorrow" },
  "header.resetsAt": { tr: "{time} itibarıyla yenilenir", en: "Resets at {time}" },
  "header.refreshTipAnon": { tr: "Günde {a} yenileme hakkın var. Hesap oluşturursan günde {r} olur.", en: "{a} refreshes a day. Create an account for {r}." },
  "header.refreshTipAnon_one": { tr: "Günde 1 yenileme hakkın var. Hesap oluşturursan günde {r} olur.", en: "1 refresh a day. Create an account for {r}." },
  "header.refreshTipReg": { tr: "Günde {r} yenileme hakkın var.", en: "{r} refreshes a day." },
  "header.refreshTipReg_one": { tr: "Günde 1 yenileme hakkın var.", en: "1 refresh a day." },
  "header.starting": { tr: "Başlatılıyor…", en: "Starting…" },
  "header.howItWorks": { tr: "Nasıl çalışır", en: "How it works" },
  "header.admin": { tr: "Admin", en: "Admin" },
  "header.dashboard": { tr: "Pano", en: "Dashboard" },
  "header.createAccount": { tr: "Hesap oluştur", en: "Create account" },
  "header.login": { tr: "Giriş yap", en: "Log in" },
  "header.logout": { tr: "Çıkış yap", en: "Log out" },
  "header.guest": { tr: "Misafir", en: "Guest" },
  "header.menu": { tr: "Menü", en: "Menu" },
  "header.adminPanel": { tr: "Admin paneli", en: "Admin panel" },
  "header.backToDashboard": { tr: "Panoya dön", en: "Back to dashboard" },
  "header.userMenu": { tr: "Hesap menüsü: {name}", en: "Account menu: {name}" },
  "header.accountMenu": { tr: "hesap menüsü", en: "account menu" },
  "header.roleAdmin": { tr: "admin", en: "admin" },
  "header.language": { tr: "Dil", en: "Language" },
  "header.home": { tr: "Ana sayfaya dön", en: "Go to home" },
  // ---- Tema ----
  "theme.title": { tr: "Tema", en: "Theme" },
  "theme.label": { tr: "Tema: {name}", en: "Theme: {name}" },
  "theme.system": { tr: "Sistem", en: "System" },
  "theme.light": { tr: "Açık", en: "Light" },
  "theme.dark": { tr: "Koyu", en: "Dark" },

  // ---- Pano / genel görünüm ----
  "ov.todayImportant": { tr: "Bugün önemli", en: "Today's highlights" },
  "ov.following": { tr: "Takip ettiklerin", en: "Your watchlist" },
  "ov.noChangeToday": { tr: "Bugün öne çıkan bir değişiklik yok. Tüm şirketler aşağıdaki listede.", en: "Nothing stands out today. All companies are in the list below." },
  "ov.list": { tr: "Tüm liste ({n})", en: "Full list ({n})" },
  "ov.title": { tr: "Pano", en: "Dashboard" },
  "ov.count": { tr: "{n} şirket takipte", en: "Following {n} companies" },
  "ov.count_one": { tr: "1 şirket takipte", en: "Following 1 company" },
  "ov.sortLabel": { tr: "Sıralama", en: "Sort" },
  "ov.sort": { tr: "Sırala:", en: "Sort:" },
  "ov.sortRisk": { tr: "Risk", en: "Risk" },
  "ov.sortAlpha": { tr: "Alfabetik", en: "Alphabetical" },
  "ov.suggestions": { tr: "Öneriler ({n})", en: "Suggestions ({n})" },
  "ov.watchlist": { tr: "İzleme listesi ({n})", en: "Watchlist ({n})" },
  "ov.emptyTitle": { tr: "Henüz şirket eklemedin.", en: "You haven't added a company yet." },
  "ov.emptyBody": { tr: "Bir şirket ekle, haberlerini senin için okuyalım.", en: "Add a company and we'll read its news for you." },
  "ov.suggestionsTitle": { tr: "Öneriler", en: "Suggestions" },
  "ov.watchlistTitle": { tr: "İzleme listesi", en: "Watchlist" },
  "ov.hintCreate": { tr: "Hesap oluşturursan", en: "Create an account" },
  "ov.hintRest": { tr: "listeni her cihazda görürsün.", en: "to see your list on every device." },
  "ov.hintDismiss": { tr: "İpucunu kapat", en: "Dismiss tip" },
  "ov.moreTitle": { tr: "Birkaç şirket daha ekle", en: "Add a few more companies" },
  "ov.moreDismiss": { tr: "Önerileri kapat", en: "Close suggestions" },
  "ov.emptyNote": { tr: "Eklediğin şirketler bir sonraki yenilemede analiz edilir.", en: "Companies you add are analyzed on the next refresh." },

  // ---- Kart ----
  "card.noAnalysis": { tr: "analiz yok", en: "no analysis" },
  "card.langMissingShort": { tr: "bu dilde yok", en: "not in this language" },
  "card.langMissing": { tr: "Bu dilde henüz analiz yok, bir sonraki yenilemede gelecek.", en: "No analysis in this language yet; it'll arrive with the next refresh." },
  "card.noAnalysisYet": { tr: "Henüz analiz yok", en: "No analysis yet" },
  "card.pressRefresh": { tr: "Henüz analiz edilmedi. {refresh}’ye bas.", en: "Not analyzed yet. Press {refresh}." },
  "card.now": { tr: "şimdi", en: "now" },
  "card.analystTarget": { tr: "analist hedefi", en: "analyst target" },
  "card.noTarget": { tr: "hedef yok", en: "no target" },
  "card.noPrice": { tr: "Fiyat verisi yok", en: "No price data" },
  "card.newsOnly": { tr: "yalnızca haber analizi", en: "news analysis only" },
  "card.privateShort": { tr: "Halka açık değil · yalnızca haber analizi", en: "Not public · news analysis only" },
  "card.private": { tr: "Özel şirket, borsada işlem görmüyor", en: "Private company, not publicly traded" },
  "card.privateBody": { tr: "Halka açık olmadığı için fiyat ve analist hedefi yok. Değerlendirme sadece haberlere dayanıyor.", en: "It isn't public, so there's no price or analyst target. The assessment is based only on the news." },
  "card.topDriver": { tr: "Öne çıkan:", en: "Top driver:" },
  "card.analysts": { tr: "{n} analist", en: "{n} analysts" },
  "card.buyLean": { tr: "Analistler: alım yönlü", en: "Analysts: buy-leaning" },
  "card.sellLean": { tr: "Analistler: satış yönlü", en: "Analysts: sell-leaning" },
  "card.holdLean": { tr: "Analistler: karışık", en: "Analysts: mixed" },
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
  "stance.bullish": { tr: "Yükseliş", en: "Bullish" },
  "stance.neutral": { tr: "Nötr", en: "Neutral" },
  "stance.bearish": { tr: "Düşüş", en: "Bearish" },
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
  "trend.stable": { tr: "sabit", en: "stable" },
  "trend.deteriorating": { tr: "kötüleşiyor", en: "deteriorating" },
  "sig.strongNeg": { tr: "Güçlü olumsuz", en: "Strongly negative" },
  "sig.neg": { tr: "Olumsuz", en: "Negative" },
  "sig.neutral": { tr: "Nötr", en: "Neutral" },
  "sig.pos": { tr: "Olumlu", en: "Positive" },
  "sig.strongPos": { tr: "Güçlü olumlu", en: "Strongly positive" },
  "sig.overall": { tr: "Genel sinyal", en: "Overall signal" },

  // ---- Detay ----
  "detail.back": { tr: "Pano", en: "Dashboard" },
  "detail.errorBody": { tr: "Bu şirketin ayrıntıları yüklenemedi.", en: "Couldn't load this company's details." },
  "detail.tabsLabel": { tr: "Ayrıntı sekmeleri", en: "Detail tabs" },
  "detail.tabSummary": { tr: "Özet", en: "Summary" },
  "detail.tabCharts": { tr: "Grafikler", en: "Charts" },
  "detail.tabNews": { tr: "Haberler", en: "News" },
  "detail.tabAnalysts": { tr: "Analistler", en: "Analysts" },
  "detail.dir": { tr: "Yön", en: "Direction" },
  "detail.horizon": { tr: "Vade", en: "Horizon" },
  "detail.evidence": { tr: "Kanıt", en: "Evidence" },
  "detail.target": { tr: "hedef", en: "target" },
  "detail.noPrice": { tr: "Fiyat verisi yok. ABD dışı bir borsa olabilir.", en: "No price data. It may be a non-US exchange." },
  "detail.notPublic": { tr: "Borsada işlem görmüyor, özel şirket.", en: "Not publicly traded, private company." },
  "detail.loading": { tr: "Yükleniyor…", en: "Loading…" },
  "detail.error": { tr: "Hata: {msg}", en: "Error: {msg}" },
  "detail.noAnalysisBox": { tr: "Bu şirket için henüz analiz yok. Üstteki {refresh} düğmesine bas.", en: "No analysis for this company yet. Press the {refresh} button above." },
  "detail.langNote": { tr: "Bu değerlendirme {lang} üretildi.", en: "This assessment was generated in {lang}." },
  "lang.tr.name": { tr: "Türkçe", en: "Turkish" },
  "lang.en.name": { tr: "İngilizce", en: "English" },
  "detail.articlesN": { tr: "{n} makale", en: "{n} articles" },
  "detail.analyzedN": { tr: "{n} analiz", en: "{n} analyzed" },
  "detail.prefilteredN": { tr: "{n} elenen", en: "{n} filtered" },
  "detail.pendingN": { tr: "{n} bekliyor", en: "{n} pending" },

  // ---- Özet sekmesi ----
  "sum.aiTake": { tr: "AI ne düşünüyor?", en: "What the AI thinks" },
  "sum.aiDisclaimer": { tr: "Bu bir görüş, yatırım tavsiyesi değil.", en: "This is an opinion, not investment advice." },
  "sum.basedOn": { tr: "{n} habere dayalı", en: "based on {n} news" },
  "sum.previous": { tr: "önceki: {v}", en: "previous: {v}" },
  "sum.drivers": { tr: "Ana etkenler", en: "Key drivers" },
  "sum.verify": { tr: "Harekete geçmeden önce kontrol et", en: "Check before acting" },
  "sum.invalidation": { tr: "Bu görüşü ne değiştirir", en: "What would change this view" },
  "sum.riskLabel": { tr: "Risk", en: "Risk" },
  "sum.riskDeltaTitle": { tr: "son taramaya göre risk değişimi", en: "risk change since the last scan" },
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
  "chart.priceNote": { tr: "Fiyat sadece haberin fiyatlanıp fiyatlanmadığını görmek için. Hedef ya da tahmin değil.", en: "Price is only here to see whether the news is priced in. It isn't a target or a forecast." },
  "chart.need2days": { tr: "Grafik için en az 2 günlük veri gerekiyor. Sonraki yenilemelerle dolacak.", en: "The chart needs at least 2 days of data. It fills in with the next refreshes." },
  "chart.noDataRange": { tr: "Bu aralıkta veri yok. Daha geniş bir aralık seç.", en: "No data in this range. Pick a wider one." },
  "chart.riskNeed2": { tr: "Risk verisi için en az 2 tarama gerekir.", en: "Risk needs at least 2 scans." },
  "chart.showRiskSent": { tr: "Risk ve haber havasını göster", en: "Show risk & news sentiment" },
  "chart.hideRiskSent": { tr: "Risk ve haber havasını gizle", en: "Hide risk & news sentiment" },
  "chart.tipRisk": { tr: "risk {v}", en: "risk {v}" },
  "chart.tipMood": { tr: "havası {v}", en: "mood {v}" },

  // ---- Sohbet ----
  "chat.title": { tr: "AI'ya sor · {name}", en: "Ask AI · {name}" },
  "chat.placeholderHint": { tr: "Bu şirketin haberlerini sor. Örneğin: “En büyük risk ne?”", en: "Ask about this company's news. For example: “What's the biggest risk?”" },
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
  "wl.notFound": { tr: "Bulunamadı. Türk ya da Avrupa şirketleri için tip olarak keyword seç ve dili ayarla.", en: "Not found. For Turkish or European companies, choose keyword as the type and set the language." },
  "wl.nonUsShort": { tr: "haber/fiyat yok, keyword önerilir", en: "no news/price data, keyword recommended" },
  "wl.nonUsTitle": { tr: "{symbol} keyword olarak eklensin mi?", en: "Add {symbol} as a keyword?" },
  "wl.nonUsBody": { tr: "{exchange} için haber ve fiyat verisi (Finnhub) yok. Keyword olarak eklersen haber akışı yine takip edilir.", en: "There's no news or price data (Finnhub) for {exchange}. Added as a keyword, its news is still tracked." },
  "wl.nonUsConfirm": { tr: "Keyword olarak devam et", en: "Continue as keyword" },
  "wl.duplicate": { tr: "Bu şirket zaten listende: {name}", en: "This company is already on your list: {name}" },
  "wl.alreadyIn": { tr: "Bu şirket zaten listende: {name}", en: "This company is already on your list: {name}" },
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
  "notice.refreshEmpty": { tr: "izleme listen boş, önce bir şirket ekle.", en: "your watchlist is empty, add a company first." },
  "notice.refreshBusy": { tr: "şu an başka bir yenileme sürüyor, birazdan tekrar dene.", en: "another refresh is running right now; try again in a moment." },
  "notice.refreshNotStarted": { tr: "sunucu taramayı başlatmadı.", en: "the server didn't start the scan." },
  "notice.refreshNetwork": { tr: "sunucuya ulaşılamadı, bağlantını kontrol et.", en: "couldn't reach the server; check your connection." },
  "notice.refreshQuotaShort": { tr: "günlük yenileme hakkın doldu. {when}.", en: "you're out of refreshes for today. {when}." },
  "notice.scanRunning": { tr: "Tarama sürüyor: {done}/{total} şirket bitti. İlk yenileme biriken haberler yüzünden uzun sürebilir. Bitince pano kendiliğinden güncellenir, sayfayı kapatabilirsin.", en: "Scan in progress: {done}/{total} companies done. The first refresh can take a while because of older news. The dashboard updates by itself when it's done, so you can close the page." },
  "notice.scanStarting": { tr: "Yenileme başlatılıyor…", en: "Starting refresh…" },
  "notice.analyzing": { tr: "{name} analiz ediliyor…", en: "Analyzing {name}…" },
  "notice.stepPrices": { tr: "Fiyatlar güncelleniyor…", en: "Updating prices…" },
  "notice.stepFetch": { tr: "{name} için haberler çekiliyor…", en: "Fetching news for {name}…" },
  "notice.stepFilter": { tr: "{name} için {n} haber filtreleniyor…", en: "Filtering {n} articles for {name}…" },
  "notice.stepFilter_one": { tr: "{name} için 1 haber filtreleniyor…", en: "Filtering 1 article for {name}…" },
  "notice.stepAnalyze": { tr: "{name} için {n} yeni haber analiz ediliyor…", en: "Analyzing {n} new articles for {name}…" },
  "notice.stepAnalyze_one": { tr: "{name} için 1 yeni haber analiz ediliyor…", en: "Analyzing 1 new article for {name}…" },
  "notice.stepAssess": { tr: "{name} için değerlendirme yazılıyor…", en: "Writing assessment for {name}…" },
  "notice.stepSkipped": { tr: "{name} atlandı, yeni veri yok", en: "Skipped {name}, no new data" },
  "notice.scanWorking": { tr: "Haberler taranıyor…", en: "Scanning news…" },
  "notice.scanDone": { tr: "Tamamlandı · {parts}", en: "Done · {parts}" },
  "notice.budgetExceeded": { tr: "Günlük analiz kapasitesi doldu. Yeni analizler yarın devam edecek, mevcut değerlendirmeler görünmeye devam eder.", en: "The daily analysis capacity is used up. New analysis continues tomorrow and existing assessments stay visible." },
  "notice.analysisUnavailable": { tr: "Analiz servisi şu an kullanılamıyor (kapasite sınırı). Mevcut veriler gösteriliyor.", en: "The analysis service is unavailable right now (capacity limit). Showing existing data." },
  "notice.sessionFail": { tr: "Oturum başlatılamadı: {msg}", en: "Couldn't start session: {msg}" },
  "notice.sessionFailShort": { tr: "Oturum başlatılamadı. Sayfayı yenile.", en: "Couldn't start a session. Reload the page." },
  "notice.apiFail": { tr: "API'ye bağlanılamadı: {msg}. Backend çalışıyor mu?", en: "Couldn't reach the API: {msg}. Is the backend running?" },
  "notice.refreshQuotaFull": { tr: "Yenileme hakkın doldu. {when}.", en: "You're out of refreshes. {when}." },
  "notice.entityAdded": { tr: "{name} izleme listene eklendi. Bir sonraki yenilemede analiz edilecek.", en: "{name} was added to your watchlist. It'll be analyzed on the next refresh." },
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
  "msg.budget_exceeded": { tr: "Günlük analiz bütçesi doldu. Yeni analiz yapılmadı, yarın tekrar dene.", en: "The daily analysis budget is used up. No new analysis was run, try again tomorrow." },
  "msg.budget_stopped": { tr: "Günlük analiz bütçesi tarama sırasında doldu. Kalan analizler yarın yapılacak.", en: "The daily analysis budget ran out during the scan. The rest will be analyzed tomorrow." },
  "msg.analysis_unavailable": { tr: "Analiz servisi şu an kullanılamıyor. Çekilen haberler kaydedildi.", en: "The analysis service is unavailable right now. The fetched news was saved." },
  "msg.no_provider": { tr: "'{type}' tipi için haber kaynağı yok.", en: "No news source for type '{type}'." },
  "msg.news_fresh_skip": { tr: "Son {hours} saatte çekildi, NewsAPI atlandı (mevcut veri kullanılıyor).", en: "Fetched in the last {hours} hours, so NewsAPI was skipped (using existing data)." },
  "msg.newsapi_quota": { tr: "NewsAPI kotası doldu ({used}/{limit}), {hours} saat sonra sıfırlanır.", en: "NewsAPI quota used up ({used}/{limit}), resets in {hours} hours." },
  "msg.db_write_error": { tr: "Kaydetme hatası, bu şirket atlandı ({error}).", en: "Save error, this company was skipped ({error})." },
  "msg.key_missing": { tr: "{key} tanımlı değil, atlandı.", en: "{key} is not set, skipped." },
  "msg.http_error": { tr: "{source} hatası ({status}): {symbol} atlandı.", en: "{source} error ({status}): {symbol} skipped." },
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

  // ---- Detay başlığı + sohbet yan paneli ----
  "detail.targetAsOf": { tr: "analist hedefi, {date}", en: "analyst target, {date}" },
  "detail.targetStale": { tr: "Analist hedefi 30 günden eski", en: "Analyst target is older than 30 days" },
  "detail.metaHorizon": { tr: "{h} vade", en: "{h} horizon" },
  "detail.metaArticles": { tr: "{count} haber analiz edildi", en: "{count} articles analyzed" },
  "detail.metaArticles_one": { tr: "1 haber analiz edildi", en: "1 article analyzed" },
  "detail.pipelineAdmin": { tr: "Hat (yalnızca admin)", en: "Pipeline (admin only)" },
  "detail.expiredN": { tr: "{n} süresi geçmiş", en: "{n} expired" },
  "chat.askAi": { tr: "AI'ya sor", en: "Ask AI" },
  "chat.open": { tr: "Sohbeti aç", en: "Open chat" },
  "chat.hide": { tr: "Sohbeti gizle", en: "Hide chat" },
  "chat.qWhy": { tr: "{name} için hüküm neden {stance}?", en: "Why is the verdict on {name} {stance}?" },
  "chat.qGap": { tr: "Analist hedefi ile haberler neden ayrışıyor?", en: "Why do analyst targets and the news disagree?" },
  "chat.qRisk": { tr: "{name} için en büyük risk ne?", en: "What's the biggest risk for {name}?" },
  "chat.qWatch": { tr: "Önümüzdeki haftalarda neyi takip etmeliyim?", en: "What should I watch in the coming weeks?" },

  // ---- Footer / gizlilik ----
  "footer.disclaimer": { tr: "Değerlendirmeler haberlere dayanır, fiyat tahmini ya da değerleme sunmaz. Analist hedefleri Finnhub konsensüs verisidir. Kararlar sana aittir.", en: "Assessments are based on the news and don't predict prices or valuations. Analyst targets are Finnhub consensus data. Decisions are yours." },
  "footer.privacy": { tr: "Gizlilik", en: "Privacy" },
  "privacy.intro": { tr: "NewsRadar kişisel veriyi en aza indirir. Misafir kullanımda hesap ya da e-posta istemeyiz.", en: "NewsRadar minimizes personal data. In guest use we ask for no account or email." },
  "privacy.collectTitle": { tr: "Ne topluyoruz?", en: "What we collect" },
  "privacy.c1": { tr: "Cihaz kimliği: tarayıcına yazılan rastgele bir kimlik (HttpOnly cookie). Kim olduğunu söylemez; yalnızca aynı cihazda listeni hatırlamak için.", en: "Device ID: a random identifier stored in your browser (HttpOnly cookie). It doesn't say who you are; it only remembers your list on this device." },
  "privacy.cIp": { tr: "IP adresin yalnızca kötüye kullanımı önlemek için (hız sınırı, giriş kilidi, başarısız giriş kaydı) en fazla {days} gün tutulur, kimlik olarak kullanılmaz; süre dolunca otomatik silinir.", en: "Your IP address is kept for at most {days} days and only to prevent abuse (rate limiting, login lockout, failed-login records); it is not used as identity and is deleted automatically afterwards." },
  "privacy.c2": { tr: "İzleme listen ve kullanım olayların (hangi şirketleri ekledin, ne zaman yeniledin). Hizmeti sağlamak ve kötüye kullanımı önlemek için.", en: "Your watchlist and usage events (which companies you added, when you refreshed). Used to run the service and prevent abuse." },
  "privacy.c3": { tr: "Hesap oluşturursan: seçtiğin kullanıcı adı ve şifrenin güvenli özeti (düz şifre asla saklanmaz).", en: "If you create an account: your chosen username and a secure hash of your password (the plain password is never stored)." },
  "privacy.cFeedback": { tr: "Geri bildirim gönderirsen: mesajın, isteğe bağlı yazdığın e-posta/kullanıcı adı ve tarayıcı türün (mobil/masaüstü ayrımı için). Yalnızca site yöneticisi okur, e-postanı sadece sana yanıt vermek için kullanırız; IP adresin geri bildirimle saklanmaz. Silinmesini istediğinde silinir.", en: "If you send feedback: your message, the email/username you optionally enter, and your browser type (to tell mobile from desktop). Only the site admin reads it; we use your email only to reply to you, and your IP address is not stored with feedback. It is deleted when you ask." },
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
  "fb.title": { tr: "Ne düşündüğünü merak ediyorum", en: "I'd like to hear what you think" },
  "fb.body": { tr: "NewsRadar'ı tek başıma geliştiriyorum. Neyin işe yaradığını, neyin eksik ya da kafa karıştırıcı olduğunu yazarsan çok yardımcı olur.", en: "I'm building NewsRadar on my own. It really helps if you tell me what worked and what's missing or confusing." },
  "fb.placeholder": { tr: "Ne düşünüyorsun?", en: "What do you think?" },
  "fb.contact": { tr: "E-posta / kullanıcı adı (zorunlu değil)", en: "Email / username (optional)" },
  "fb.contactNote": { tr: "Cevap istersen iletişim bilgisi bırakabilirsin.", en: "Leave a contact if you'd like a reply." },
  "fb.send": { tr: "Gönder", en: "Send" },
  "fb.sending": { tr: "Gönderiliyor…", en: "Sending…" },
  "fb.thanks": { tr: "Teşekkürler, okuyacağım.", en: "Thanks, I'll read it." },
  "fb.builtBy": { tr: "Bu aracı {name} yaptı.", en: "{name} built this tool." },
  "fb.fail": { tr: "Gönderilemedi, tekrar dene.", en: "Couldn't send it, try again." },

  // ---- Dil modalı ----
  "langmodal.title": { tr: "Dil / Language", en: "Dil / Language" },
  "langmodal.subtitle": { tr: "Arayüz ve değerlendirmeler bu dilde gösterilir.", en: "The interface and assessments are shown in this language." },

  // ---- Gezinme (Geri / İleri) ----
  // ---- "Nasıl çalışır?" (gerçek veriyle 4 adım) ----
  "hiw.dialog": { tr: "Nasıl çalışır?", en: "How it works" },
  "hiw.link": { tr: "Nasıl çalışır? (30 sn)", en: "How it works? (30 sec)" },
  "hiw.stepOf": { tr: "Adım {n} / {total}", en: "Step {n} of {total}" },
  "hiw.loading": { tr: "Örnek hazırlanıyor…", en: "Preparing the example…" },
  "hiw.noData": { tr: "Şu an gösterilecek güncel bir örnek yok. Bir şirket ekleyip yenilediğinde aynı adımları kendi verinle görürsün.", en: "There's no fresh example to show right now. Add a company and refresh to see these steps with your own data." },
  "hiw.s1.title": { tr: "Haberleri biz topluyoruz.", en: "We collect the news." },
  "hiw.s1.caption": { tr: "{sources} kaynaklarından. Bu hafta {count} haber.", en: "From {sources}. {count} articles this week." },
  "hiw.s1.caption_one": { tr: "{sources} kaynaklarından. Bu hafta 1 haber.", en: "From {sources}. 1 article this week." },
  "hiw.s2.title": { tr: "Yapay zekâ her haberi okur.", en: "AI reads every article." },
  "hiw.s2.caption": { tr: "Konuyla ilgisi olmayan haberler ayıklanır.", en: "Off-topic articles are dropped." },
  "hiw.s3.title": { tr: "Tabloyu özetler.", en: "It sums up the picture." },
  "hiw.s3.caption": { tr: "Tek bir değerlendirme, gerekçesi ve analistlerin beklentisi.", en: "One assessment, the reasoning and what analysts expect." },
  "hiw.s4.title": { tr: "Kararı sen verirsin.", en: "You decide." },
  "hiw.s4.caption": { tr: "Soru sor, kaynaklara bak. Bu bir görüş; yatırım tavsiyesi olarak görme.", en: "Ask questions and check the sources. It's an opinion, so don't treat it as investment advice." },
  "hiw.try": { tr: "Kendi şirketlerinle dene", en: "Try it with your own companies" },
  "hiw.more": { tr: "Ayrıntılı anlatım: gerçek ekranlarla 4 adım", en: "Full walkthrough: 4 steps with real screens" },
  "app.about": { tr: "NewsRadar hakkında", en: "About NewsRadar" },

  // ---- Landing (/) ----
  // ── Landing ("/") — kısa, kendinden emin; "Claude" yalnızca mimari bölümünde. TR ayrı yazıldı.
  "land.nav.how": { tr: "Nasıl çalışır", en: "How it works" },
  "land.nav.stack": { tr: "Altında ne var", en: "Under the hood" },
  "land.openApp": { tr: "Uygulamayı aç", en: "Open the app" },
  "land.openAppShort": { tr: "Aç", en: "Open" },
  "land.hero.l1": { tr: "Haberler şirketlerin hakkında ne diyor?", en: "What's the news saying about your companies?" },
  "land.hero.l2": { tr: "", en: "" },
  "land.hero.l3": { tr: "", en: "" },
  "land.hero.sub": { tr: "NewsRadar takip ettiğin şirketlerin haberlerini okur ve kısa bir değerlendirme yazar. Hangi başlıklara dayandığını da gösterir.", en: "NewsRadar reads the news on the companies you follow and writes a short assessment. It also shows which headlines it's based on." },
  "land.hero.how": { tr: "Nasıl çalışır", en: "How it works" },
  "land.hero.scroll": { tr: "Kaydır", en: "Scroll" },
  "land.hero.live": { tr: "Canlı örnek: {name}", en: "Live example: {name}" },
  "land.hero.risk": { tr: "Risk", en: "Risk" },
  "land.manifesto": { tr: "Bir şirket hakkında günde onlarca haber çıkabiliyor. Hepsini okumak yerine [kısa bir özet] ve dayandığı başlıklar çoğu zaman yetiyor.", en: "A single company can get dozens of headlines a day. Instead of reading them all, [a short summary] and the headlines behind it usually do the job." },
  "land.how.title": { tr: "Nasıl çalışıyor", en: "How it works" },
  "land.step1.title": { tr: "Şirketini ekle", en: "Add a company" },
  "land.step1.body": { tr: "Şirketin adını ya da borsa kodunu yaz. Hesap açman gerekmiyor.", en: "Type the company name or ticker. You don't need an account." },
  "land.step2.title": { tr: "Haberler gelir", en: "The news comes in" },
  "land.step2.body": { tr: "Finnhub ve NewsAPI'den yeni haberler gün boyu gelir.", en: "Fresh articles arrive from Finnhub and NewsAPI around the clock." },
  "land.step3.title": { tr: "AI hepsini okur", en: "AI reads every one" },
  "land.step3.body": { tr: "Her haber olumlu ya da olumsuz olarak işaretlenir. Konuyla ilgisi olmayanlar ayıklanır.", en: "Each article is marked positive or negative. The off-topic ones are dropped." },
  "land.step4.title": { tr: "Değerlendirmeyi okursun", en: "You read the assessment" },
  "land.step4.body": { tr: "Kısa bir değerlendirme, dayandığı başlıklar ve sorular için bir sohbet. Kararı sen verirsin.", en: "A short assessment, the headlines behind it and a chat for your questions. You make the call." },
  "land.window": { tr: "NewsRadar uygulaması, adım {n}: {title}", en: "NewsRadar app, step {n}: {title}" },
  "land.stats.title": { tr: "Gerçek rakamlar", en: "Real numbers" },
  "land.stats.sub": { tr: "Bu rakamlar canlı veritabanından geliyor.", en: "These numbers come from the live database." },
  "land.stats.articles": { tr: "analiz edilen makale", en: "articles analyzed" },
  "land.stats.assessments": { tr: "AI değerlendirmesi", en: "AI assessments" },
  "land.stats.sources": { tr: "haber kaynağı", en: "news sources" },
  "land.stats.languages": { tr: "dil", en: "languages" },
  "land.stack.title": { tr: "Altında ne var", en: "Under the hood" },
  "land.stack.sub": { tr: "Teknik tarafı merak edenler için: ön yüz statik, API tek bir küçük sunucuda çalışıyor ve her push otomatik olarak yayına çıkıyor.", en: "If you're curious about the tech: the front end is static, the API runs on one small server and every push deploys automatically." },
  "land.stack.repo": { tr: "Kaynak kodu GitHub'da", en: "Source on GitHub" },
  "land.stack.frontend": { tr: "Ön yüz", en: "Front end" },
  "land.stack.api": { tr: "API", en: "API" },
  "land.stack.ai": { tr: "AI", en: "AI" },
  "land.stack.data": { tr: "Veri", en: "Data" },
  "land.stack.delivery": { tr: "Teslimat", en: "Delivery" },
  "land.stack.nightly": { tr: "Gece yedeği", en: "Nightly backup" },
  "land.stack.verdict": { tr: "Değerlendirme", en: "Verdict" },
  "land.stack.deploy": { tr: "Yayın + geri alma", en: "Deploy + rollback" },
  "land.cta.title": { tr: "Takip ettiğin bir şirketle dene.", en: "Try it with a company you follow." },
  "land.footer.built": { tr: "Geliştiren: {name}", en: "Built by {name}" },
  "land.footer.note": {
    tr: "Portfolyo projesi. Yatırım tavsiyesi değildir. newsradar.com.tr ile bağlantısı yoktur.",
    en: "Portfolio project. Not investment advice. Not affiliated with newsradar.com.tr.",
  },
  "land.sc.newsCount": { tr: "haber · son 7 gün", en: "articles · last 7 days" },
  "land.sc.newsCount_one": { tr: "haber · son 7 gün", en: "article · last 7 days" },
  "land.sc.sources": { tr: "Kaynak:", en: "Source:" },
  "land.sc.reading": { tr: "AI başlıkları tek tek okuyor", en: "AI reads the headlines one by one" },
  "land.sc.verdict": { tr: "Değerlendirme", en: "Verdict" },
  "land.sc.filtered": { tr: "{n} konu dışı haber ayıklandı", en: "{n} off-topic articles dropped" },
  "land.sc.filtered_one": { tr: "1 konu dışı haber ayıklandı", en: "1 off-topic article dropped" },
  "land.footer.privacy": { tr: "Gizlilik", en: "Privacy" },
  "hiw.label.positive": { tr: "olumlu", en: "positive" },
  "hiw.label.negative": { tr: "olumsuz", en: "negative" },
  "hiw.label.neutral": { tr: "nötr", en: "neutral" },
  "hiw.label.irrelevant": { tr: "alakasız", en: "irrelevant" },
  "tut.back": { tr: "Geri", en: "Back" },
  "tut.next": { tr: "İleri", en: "Next" },

  // ---- Hesap modalı ----
  "acc.upgradeTitle": { tr: "Hesap oluştur", en: "Create account" },
  "acc.loginTitle": { tr: "Giriş yap", en: "Log in" },
  "acc.upgradeBody": { tr: "Listeni kaybetmeden kalıcı bir hesap aç. Bir kullanıcı adı ve şifre belirlemen yeterli.", en: "Keep your list and get a permanent account. Just pick a username and a password." },
  "acc.loginBody": { tr: "Mevcut hesabınla giriş yap.", en: "Log in with your existing account." },
  "acc.username": { tr: "Kullanıcı adı", en: "Username" },
  "acc.password": { tr: "Şifre", en: "Password" },
  "acc.submitUpgrade": { tr: "Hesap oluştur", en: "Create account" },
  "acc.submitLogin": { tr: "Giriş yap", en: "Log in" },
  "acc.working": { tr: "İşleniyor…", en: "Working…" },
  "acc.toLogin": { tr: "Zaten hesabın var mı? Giriş yap", en: "Already have an account? Log in" },
  "acc.toUpgrade": { tr: "Hesabın yok mu? Oluştur", en: "No account? Create one" },
  "state.errorBody": { tr: "Bir şeyler ters gitti. Bağlantını kontrol edip tekrar dene.", en: "Something went wrong. Check your connection and try again." },
  "state.loadFail": { tr: "Panon yüklenemedi. Bağlantını kontrol edip tekrar dene.", en: "Couldn't load your dashboard. Check your connection and try again." },
  "state.syncFail": { tr: "Son güncelleme alınamadı. Gördüğün veriler biraz eski olabilir.", en: "Couldn't get the latest update. What you see may be a little out of date." },
  "sys.newsapiExhausted": { tr: "NewsAPI kotası doldu ({used}/{limit}), {hours} saat sonra sıfırlanır. Keyword haberleri bu süre güncellenmez; ticker'lar etkilenmez.", en: "NewsAPI quota used up ({used}/{limit}); resets in {hours} h. Keyword news won't update until then; tickers are unaffected." },
  "sys.newsapiLow": { tr: "NewsAPI kotası doluyor: {used}/{limit} kullanıldı, {left} istek kaldı.", en: "NewsAPI quota running low: {used}/{limit} used, {left} requests left." },
  "sys.missingKeys": { tr: "Eksik anahtar: {keys}. Bu kaynaklar atlanır; uygulama çalışmaya devam eder.", en: "Missing keys: {keys}. These sources are skipped; the app keeps running." },
  "footer.nav": { tr: "Alt bağlantılar", en: "Footer links" },
  "state.retry": { tr: "Tekrar dene", en: "Try again" },
  "common.cancel": { tr: "Vazgeç", en: "Cancel" },
  "common.close": { tr: "Kapat", en: "Close" },

  // ---- Öneriler ----
  "sug.title": { tr: "Bunları da izlemek ister misin?", en: "Want to watch these too?" },
  "sug.subtitle": { tr: "Haberlerinde sık geçen, izleme listende olmayan şirketler.", en: "Companies often mentioned in your news that aren't on your watchlist." },
  "sug.mentioned": { tr: "{n} haberde geçti", en: "seen in {n} news" },
  "sug.inNews": { tr: "{names} haberlerinde", en: "in {names} news" },
  "sug.addTicker": { tr: "ticker olarak eklenecek (ABD borsası)", en: "will be added as a ticker (US exchange)" },
  "sug.addKeyword": { tr: "keyword{lang} olarak eklenecek", en: "will be added as a keyword{lang}" },
  "sug.add": { tr: "Ekle", en: "Add" },
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
  "art.sourcesTitle": { tr: "Bu haber {n} kaynakta çıktı. Ne kadar çok kaynak, o kadar önemli (kopyalar bir kez sayıldı).", en: "This story ran in {n} sources. More sources usually means it matters more (copies counted once)." },
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
  "an.source": { tr: "Analist tavsiyeleri Finnhub, hedef fiyat FMP verisidir{period}. NewsRadar tahmini değildir.", en: "Analyst ratings come from Finnhub and the target price from FMP{period}. This isn't a NewsRadar forecast." },
  "an.noKeyword": { tr: "Bu şirket borsada işlem görmüyor (özel şirket), bu yüzden hedef fiyat ve analist verisi yok. Değerlendirme sadece haberlere dayanıyor.", en: "This company isn't publicly traded (private), so there's no target price or analyst data. The assessment relies only on the news." },
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
  "adm.healthOk": { tr: "Çalışıyor, son analiz çağrısı başarılı.", en: "Operational, the last analysis call succeeded." },
  "adm.healthQuota": { tr: "Kota/bakiye sınırı: analiz servisi geçici olarak durdu.", en: "Quota/balance limit: the analysis service is temporarily down." },
  "adm.healthErrors": { tr: "Son analizde hata var, logları kontrol et.", en: "Errors in the last analysis, check the logs." },
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
  "adm.deleteFb": { tr: "Geri bildirimi sil", en: "Delete feedback" },
  "adm.deleteFbConfirm": { tr: "Bu geri bildirim kalıcı olarak silinsin mi? Bu işlem geri alınamaz.", en: "Delete this feedback permanently? This can't be undone." },
  "adm.deleteFbFail": { tr: "Silinemedi: {m}", en: "Couldn't delete: {m}" },
  "adm.eventBreakdown": { tr: "Eylem dökümü", en: "Action breakdown" },
  "adm.noActions": { tr: "Henüz eylem yok.", en: "No actions yet." },
  "adm.topViewed": { tr: "En çok baktığı şirketler", en: "Most viewed companies" },
  "adm.watchlistN": { tr: "İzleme listesi ({n})", en: "Watchlist ({n})" },
  "adm.noWatch": { tr: "Takip ettiği şirket yok.", en: "Follows no company." },
  "adm.registered": { tr: "Kayıt: {d}", en: "Registered: {d}" },
  "adm.lastLoginLine": { tr: "Son giriş: {d}", en: "Last login: {d}" },
  "adm.recentActions": { tr: "Son eylemler", en: "Recent actions" },
  "adm.noRecords": { tr: "Kayıt yok.", en: "No records." },
  "adm.close": { tr: "Kapat", en: "Close" },
  "adm.errorBody": { tr: "Admin verileri yüklenemedi.", en: "Couldn't load admin data." },
  "adm.copy": { tr: "Kopyala", en: "Copy" },
  "adm.copied": { tr: "Kopyalandı", en: "Copied" },
  "adm.confirmDelete": { tr: "{u} kullanıcısını ve tüm verilerini silmek istediğinize emin misiniz?", en: "Delete user {u} and all their data?" },
  "adm.confirmReset": { tr: "{u} kullanıcısının şifresi sıfırlansın mı? Geçici bir şifre üretilecek.", en: "Reset {u}'s password? A temporary password will be generated." },
  "adm.tempPrompt": { tr: "{u} için geçici şifre (kopyala ve kullanıcıya ilet, bir daha gösterilmez):", en: "Temporary password for {u} (copy and share it, it's shown only once):" },
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
  "ev.delete_feedback": { tr: "geri bildirim silme", en: "delete feedback" },
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

// Yüzde — DİLE göre, Intl.NumberFormat ile (EN "+58%", TR "+%58"). value yüzde puanıdır
// (58 → %58). signed: işaret her zaman (sıfır hariç). Tüm uygulama bunu kullanır.
export function fmtPct(value, { digits = 0, signed = true } = {}) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(LOCALE(), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value / 100);
}
// Tam sayı — dile göre binlik ayırıcı (EN 1,158 · TR 1.158).
export function fmtInt(value) {
  return value == null ? "—" : new Intl.NumberFormat(LOCALE()).format(value);
}
// Büyük sayıyı kısalt (EN 77K+ · TR 77 B+). Aşağı yuvarlanır, "+" bu yüzden doğru;
// 10.000 altı tam yazılır (binlik ayırıcıyla zaten okunur).
export function fmtCompact(value) {
  if (value == null) return "—";
  if (value < 1e4) return fmtInt(value);
  const step = value < 1e6 ? 1000 : value < 1e7 ? 1e5 : 1e6;
  const digits = step === 1e5 ? 1 : 0;
  const n = Math.floor(value / step) * step;
  return new Intl.NumberFormat(LOCALE(), { notation: "compact", maximumFractionDigits: digits }).format(n) + "+";
}

// Dil-farkında tarih/zaman yardımcıları (locale'e göre biçim).
const LOCALE = () => (_lang === "tr" ? "tr-TR" : "en-US");
export function fmtDate(iso) {
  if (!iso) return "—";
  return parseUtc(iso).toLocaleDateString(LOCALE(), { day: "2-digit", month: "short" });
}
export function fmtTime(d) {
  return parseUtc(d).toLocaleTimeString(LOCALE(), { hour: "2-digit", minute: "2-digit" });
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
