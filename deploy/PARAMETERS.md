# SSM Parameter Store parametreleri

Üretim ayarları **SSM Parameter Store**'da tutulur. Yol `/newsradar/prod/<AD>`, bölge `eu-central-1`.
EC2'de [`load-secrets.sh`](load-secrets.sh) bu parametreleri okur ve `deploy/.env` dosyasını yazar (izin 600, repoya girmez).
`<AD>`, uygulamanın okuduğu ortam değişkeninin adıyla aynıdır.

- **SecureString**: sırlar. KMS ile şifreli saklanır, `--with-decryption` ile çözülür.
- **String**: sır olmayan ayarlar.
- Bir parametre SSM'de yoksa uygulama aşağıdaki **varsayılanı** kullanır. Zorunlu parametreler bunun dışındadır: eksiklerse `load-secrets.sh` `.env` dosyasını hiç yazmaz.
- Örnek değerler biçimi göstermek içindir. Bu dosyaya **gerçek değer yazılmaz**.

Parametre ekleme örneği:

```bash
aws ssm put-parameter --region eu-central-1 --name /newsradar/prod/APP_SECRET \
  --type SecureString --value "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

EC2 instance rolünün ihtiyaç duyduğu izinlerin tam ve en dar hali `deploy/iam/ec2-instance-policy.json` dosyasında.

## 1. Zorunlu

Bunlardan biri eksik ya da boşsa `load-secrets.sh` durur ve mevcut `.env`'ye dokunmaz.

| Ad | Açıklama | Tür | Örnek |
|---|---|---|---|
| `DOMAIN` | Caddy'nin sunduğu alan adı. API adresi `api.$DOMAIN` olur ve TLS sertifikası Let's Encrypt'ten otomatik alınır. | String | `newsradarapp.com` |
| `APP_SECRET` | Oturum token'larının HMAC imza sırrı. Değişirse tüm oturumlar düşer. | SecureString | `<48+ karakter rastgele>` |
| `ANTHROPIC_API_KEY` | Claude API anahtarı. Analiz ve sohbet bununla çalışır. | SecureString | `sk-ant-api03-…` |
| `NEWSRADAR_CORS_ORIGINS` | İzinli frontend origin'leri (virgülle ayrılmış, tam origin). | String | `https://newsradarapp.com,https://www.newsradarapp.com` |
| `BACKUP_BUCKET` | Gece yedeğinin S3 bucket'ı (`backup.sh`, `restore.sh`). Uygulama bunu okumaz. | String | `newsradar-backups-<hesap>` |
| `BACKEND_IMAGE` | Backend image'ı. `docker-compose.yml` bunu okur; yoksa image EC2'de yerel olarak build edilir. | String | `<hesap>.dkr.ecr.eu-central-1.amazonaws.com/newsradar-api:prod` |

## 2. Sırlar (isteğe bağlı)

Boş bırakılırsa ilgili özellik kapanır ama uygulama çalışmaya devam eder.

| Ad | Açıklama | Tür | Varsayılan | Örnek |
|---|---|---|---|---|
| `FINNHUB_API_KEY` | Ticker haberleri ve analist tavsiyesi. Yoksa ticker sağlayıcısı atlanır. | SecureString | boş | `c1ab…` |
| `NEWSAPI_KEY` | NewsAPI anahtarı; yalnızca `NEWSRADAR_NEWSAPI_ENABLED=on` iken kullanılır (varsayılan: keyword haberleri GDELT'ten, anahtarsız). | SecureString | boş | `0f9e…` |
| `FMP_API_KEY` | Analist hedef fiyatı. Yoksa hedef fiyat gösterilmez. | SecureString | boş | `Xy7…` |
| `APP_PASSWORD` | Eski genel giriş şifresi (`/auth/login`). Site herkese açık olduğu için artık zorunlu değil. | SecureString | boş | `<parola>` |
| `NEWSRADAR_LLM_API_KEY` | OpenAI uyumlu yedek LLM anahtarı. Yalnızca `NEWSRADAR_LLM_PROVIDER≠anthropic` iken kullanılır. | SecureString | boş | `sk-or-v1-…` |

## 3. AWS profili (önerilen değerler)

Varsayılanlar Render'a göre ayarlıdır. AWS'de bu değerleri vermek gerekir.

| Ad | Açıklama | Tür | Varsayılan | AWS değeri |
|---|---|---|---|---|
| `NEWSRADAR_COOKIE_SAMESITE` | Cihaz cookie'sinin SameSite değeri (`lax`, `strict` veya `none`). `none` için Secure açık olmalı. | String | `none` | `lax` |
| `NEWSRADAR_COOKIE_SECURE` | Cookie yalnızca HTTPS üzerinden gönderilir (`on`/`off`). | String | `on` | `on` |
| `NEWSRADAR_COOKIE_DOMAIN` | Cookie domain'i. Boşsa cookie yalnızca API host'unda geçerlidir. | String | boş | `.newsradarapp.com` |
| `NEWSRADAR_HOSTING_PROVIDER` | Gizlilik metninde gösterilen barındırma sağlayıcısı. | String | `Render` | `AWS (eu-central-1)` |
| `NEWSRADAR_CONTACT_EMAIL` | Gizlilik metnindeki iletişim adresi (veri silme talepleri). | String | boş | `privacy@example.com` |
| `NEWSRADAR_SEED_ON_START` | Açılışta varsayılan izleme listesini ekler (idempotent). | String | `off` | `on` |
| `ADMIN_USERNAME` | Bu kullanıcı adıyla kayıt olan hesap admin olur. Boşsa ilk kayıt olan admin olur. | String | boş | `<kullanıcı adı>` |

## 4. Ayar (isteğe bağlı, varsayılan çoğu durumda yeterli)

| Ad | Açıklama | Tür | Varsayılan | Örnek |
|---|---|---|---|---|
| `NEWSRADAR_LLM_PROVIDER` | `anthropic` ise Claude kullanılır. Başka her değer OpenAI uyumlu endpoint'e yönlendirir (geri dönüş). | String | `anthropic` | `anthropic` |
| `NEWSRADAR_ARTICLE_MODEL` | Makale toplu analizi için model; değerlendirme metinlerinin TR çevirisi de bu modelle yapılır (hüküm/risk çeviriye gitmez). | String | `claude-haiku-5-5` | `claude-haiku-5-5` |
| `NEWSRADAR_ASSESSMENT_MODEL` | Entity değerlendirmesi için model (şirket başına tek çağrı, İngilizce kaynak; TR ve EN aynı hükmü paylaşır). | String | `claude-haiku-5-5` | `claude-haiku-5-5` |
| `NEWSRADAR_CHAT_MODEL` | Sohbet için model. | String | `claude-haiku-5-5` | `claude-haiku-5-5` |
| `NEWSRADAR_LLM_BASE_URL` | OpenAI uyumlu endpoint'in adresi (geri dönüş). | String | `https://openrouter.ai/api/v1` | `https://openrouter.ai/api/v1` |
| `NEWSRADAR_LLM_MODEL` | OpenAI uyumlu endpoint'in modeli (geri dönüş). | String | `meta-llama/llama-3.3-70b-instruct` | aynı |
| `NEWSRADAR_DAILY_BUDGET_USD` | Günlük toplam LLM harcama tavanı (UTC günü, USD; 0 = sınırsız). | String | `1.50` | `1.50` |
| `NEWSRADAR_DAILY_ENTITY_ADD_CAP` | Sistem genelinde günlük yeni entity sınırı (0 = sınırsız). | String | `300` | `300` |
| `NEWSRADAR_MAX_USERS` | En fazla hesap sayısı, anonim hesaplar dahil (0 = sınırsız). | String | `500` | `500` |
| `NEWSRADAR_MAX_ENTITIES_ANON` | Anonim kullanıcının izleme listesi sınırı. | String | `3` | `3` |
| `NEWSRADAR_MAX_ENTITIES_REGISTERED` | Kayıtlı kullanıcının izleme listesi sınırı. | String | `10` | `10` |
| `NEWSRADAR_MAX_REFRESH_ANON` | Anonim kullanıcının 24 saatteki elle yenileme hakkı. | String | `1` | `1` |
| `NEWSRADAR_MAX_REFRESH_REGISTERED` | Kayıtlı kullanıcının 24 saatteki elle yenileme hakkı. | String | `3` | `3` |
| `NEWSRADAR_REFRESH_QUEUE_MAX` | Yenileme kuyruğunda aynı anda bekleyebilecek en fazla kullanıcı isteği (çalışan hariç; zamanlayıcı sayılmaz). Doluysa kullanıcıya "sıra dolu" denir. Kullanıcı başına zaten en fazla 1 istek. İsteğe bağlı. | String | `20` | `20` |
| `NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR` | IP başına saatlik yeni anonim oturum sınırı. | String | `10` | `10` |
| `NEWSRADAR_FEEDBACK_PER_IP_HOUR` | IP başına saatlik geri bildirim sınırı (0 = sınırsız). | String | `5` | `5` |
| `NEWSRADAR_IP_RETENTION_DAYS` | Kötüye kullanım kayıtlarındaki IP'lerin silinme süresi (gün). | String | `7` | `7` |
| `NEWSRADAR_TOKEN_TTL_DAYS` | Oturum token'ının geçerlilik süresi (gün). | String | `30` | `30` |
| `NEWSRADAR_SESSION_COOKIE` | Cihaz cookie'sinin adı. | String | `nr_device` | `nr_device` |
| `NEWSRADAR_SESSION_COOKIE_DAYS` | Cihaz cookie'sinin ömrü (gün). | String | `365` | `365` |
| `NEWSRADAR_SCHEDULER` | Otomatik yenileme (`on`/`off`). | String | `on` | `on` |
| `NEWSRADAR_SCHEDULER_HOURS` | Otomatik yenileme aralığı (saat). | String | `6` | `6` |
| `EMAIL_BACKEND` | Hesap e-postaları (doğrulama, şifre sıfırlama): `console` (gönderilmez, yalnızca log; production'da "Şifremi unuttum" ve doğrulama uyarısı gizlenir) ya da `ses` (Amazon SES v2, boto3; kimlik AWS varsayılan zincirinden). Bkz. DEPLOY_AWS.md Ek C. İsteğe bağlı. | String | `console` | `console` |
| `EMAIL_FROM` | Gönderen adres (`ses`). SES'te doğrulanmış alan adından olmalı. İsteğe bağlı. | String | `NewsRadar <no-reply@localhost>` | `NewsRadar <no-reply@${DOMAIN}>` |
| `EMAIL_SES_REGION` | SES bölgesi (`ses`). İsteğe bağlı. | String | `eu-central-1` | `$REGION` |
| `NEWSRADAR_PUBLIC_URL` | E-postadaki bağlantıların kökü (`https://alanadi`). Boşsa ilk CORS kökeni; isteğin Host başlığı asla kullanılmaz. İsteğe bağlı. | String | — | `https://${DOMAIN}` |
| `NEWSRADAR_LOOKBACK_HOURS` | Her yenilemede geriye dönük haber penceresi (saat). Bu süreden eski haber kaydedilmez; analiz edilmeden süresi geçen bekleyen haber `expired` olur (LLM'e gitmez). | String | `48` | `48` |
| `NEWSRADAR_BACKFILL_DAYS` | Yeni eklenen şirkette (hiç değerlendirmesi yoksa) bir kerelik geriye dönük doldurma penceresi (gün). Lookback'ten eski haberlerden en yeni `NEWSRADAR_BACKFILL_MAX_ARTICLES` tanesi kaydedilir; ikinci yenilemede çalışmaz. `0` = kapalı. İsteğe bağlı. | String | `7` | `7` |
| `NEWSRADAR_BACKFILL_MAX_ARTICLES` | Geriye dönük doldurmada kaydedilecek en fazla eski haber (yeni şirket başına en fazla bu kadar ek makale analizi). İsteğe bağlı. | String | `20` | `20` |
| `NEWSRADAR_NEWSAPI_ENABLED` | NewsAPI'yi kullan (`on`/`off`). NewsAPI'nin ücretsiz Developer planı production kullanımını yasaklar; varsayılan `off`: anahtar kelimeli ve ABD dışı şirketler GDELT'ten haber alır. `on` yalnızca ücretli planla ya da yerel denemede. İsteğe bağlı. | String | `off` | `off` |
| `NEWSAPI_DAILY_LIMIT` | NewsAPI'nin günlük istek sınırı (ücretsiz katmanda yaklaşık 100). | String | `100` | `100` |
| `NEWSRADAR_BATCH_SIZE` | Tek LLM çağrısında analiz edilen makale sayısı. | String | `10` | `10` |
| `NEWSRADAR_MAX_ARTICLES_PER_ENTITY` | Bir yenilemede entity başına makale tavanı (0 = sınırsız). | String | `200` | `200` |
| `NEWSRADAR_ANALYSIS_CONCURRENCY` | Aynı anda yapılabilecek LLM çağrısı sayısı. | String | `5` | `5` |
| `NEWSRADAR_MAX_OUTPUT_TOKENS` | Makale toplu çağrısında çıktı token tavanı. | String | `16384` | `16384` |

## 5. SSM'e konmaz

Bunlar ya `docker-compose.yml` / Dockerfile tarafından sabitlenir, ya yalnızca Render'da ya da host'ta kullanılır, ya da frontend build'ine aittir. SSM'de bulunsalar bile Docker'da kullanılmazlar. `load-secrets.sh`, compose'un sabitlediği değişkenler için uyarı verir.

| Ad | Nerede | Açıklama | Değer |
|---|---|---|---|
| `NEWSRADAR_DB` | docker-compose.yml | SQLite yolu (`data` volume'ü). | `/data/newsradar.db` |
| `NEWSRADAR_TRUSTED_PROXY` | docker-compose.yml | İstemci IP'sinin kaynağı (`render` veya `caddy`). | `caddy` (Render: `render`) |
| `NEWSRADAR_CADDY_IP` | docker-compose.yml + Dockerfile | uvicorn'un `--forwarded-allow-ips` değeri (Caddy'nin sabit iç IP'si). | `172.28.0.10` |
| `NEWSRADAR_FAKE_REFRESH_SECONDS` | yalnızca testler (e2e, birim) | **Sadece test. Production'da ASLA tanımlama.** >0 ise yenilemeler sahte çalışır (ağ/LLM yok, veri güncellenmez). Tanımlıysa açılışta uyarı loglanır (Caddy arkasında ERROR). | tanımsız (`0`) |
| `FRONTEND_URL` | Render | CORS origin'lerinin eski adı. `NEWSRADAR_CORS_ORIGINS` ile birleştirilir. AWS'de gerekmez. | `https://newsradar-web.onrender.com` |
| `VITE_API_URL` | frontend build (CloudFront) | Build sırasında frontend'e gömülen API adresi. Sır değildir. | `https://api.newsradarapp.com` |
| `VITE_API_BASE` | frontend build | `VITE_API_URL`'in eski adı (geriye uyum). | — |
| `AWS_REGION` | backup/restore/load-secrets (host) | AWS bölgesi. | `eu-central-1` |
| `LOG_FILE` | backup/restore (host) | Log'un ayrıca yazıldığı dosya. systemd birimi bunu ayarlar. | `/var/log/newsradar/backup.log` |
| `SAFETY_DIR` | restore.sh (host) | Restore öncesi DB kopyalarının klasörü. | `deploy/local-backups/pre-restore` |
| `HEALTH_TIMEOUT` | restore.sh (host) | Restore sonrası healthy bekleme süresi (sn). | `120` |
| `DEPLOY_SKIP_SECRETS` | deploy.sh (host) | `1` ise `load-secrets.sh` atlanır. Yalnızca yerel test için: yerel `deploy/.env`'yi ezmemek. | boş |
| `DB_IN_CONTAINER` | backup/restore (host) | Container içindeki DB yolu. Testler dışında değiştirilmez. | `/data/newsradar.db` |

Yerel `backend/.env` dosyasında bulunabilecek `NVIDIA_API_KEY` kodda okunmaz, bu yüzden gerekmez.
`deploy/tests/check-parameters.py` bu listeyi kodla karşılaştırır: koddaki her değişkenin burada geçtiğini ve burada kodda olmayan bir ad kalmadığını doğrular.
