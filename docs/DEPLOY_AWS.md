# NewsRadar AWS kurulum runbook'u

Hedef mimari:

```
                         ┌──────────── CloudFront (OAC, HTTP/2+3) ── S3: newsradar-frontend-<hesap>
 newsradarapp.com  ──────┤   www.newsradarapp.com → 301 → newsradarapp.com (CloudFront Function)
 www.newsradarapp.com ───┘
 api.newsradarapp.com ──── Elastic IP ── EC2 t4g.small (AL2023) ── Caddy :80/:443 ── backend (Docker)
                                             │  SQLite: Docker volume  → gece yedeği → S3: newsradar-backups-<hesap>
                                             │  image: ECR newsradar-api · sırlar: SSM /newsradar/prod/*
                                             └─ log'lar: CloudWatch Logs /newsradar/prod (7 gün)
```

Bölge **eu-central-1**. Tek istisna ACM sertifikası: CloudFront zorunlu kıldığı için **us-east-1**'de alınır. Health check alarmı da Route 53 metrikleri yalnızca orada yayımlandığı için **us-east-1**'de kurulur. API'nin TLS sertifikasını Caddy kendisi alır (Let's Encrypt); ACM gerekmez.

## Nasıl kullanılır

- Adımlar **sırayla** çalıştırılır. Her adım dört bölümden oluşur: ne yapıyoruz → komutlar → doğrulama (beklenen çıktıyla) → hata alırsam.
- Komutlar **bash** içindir. macOS'ta varsayılan kabuk zsh olduğu için her yeni terminalde önce `bash` yazın.
- Komutlar **repo kökünden** çalıştırılır (`cd ~/Desktop/newsradar`). Instance üzerinde çalışanlar ayrıca **[instance]** diye işaretlidir.
- [Adım 1](#adım-1--değişkenler-ve-durum-dosyası)'deki blok, her yeni terminalde **ilk iş olarak** yeniden çalıştırılır. Oluşan kaynak kimlikleri (instance ID, dağıtım ID…) `~/.newsradar-aws-state.env` dosyasına kaydedilir ve bu blokla geri yüklenir. Bu dosyada sır yoktur, yalnızca kimlikler vardır.
- Hiçbir komutta hesap ID'si, sır ya da e-posta yazılı değildir; hepsi değişkenlerden gelir. Sırlar `read -s` ile girilir: ekranda görünmez, shell geçmişine ve process listesine düşmez.
- Bir adım yarıda kalırsa önce o adımın **Doğrulama** komutunu çalıştırın. Kaynak zaten oluşmuşsa "already exists" hatası zararsızdır ve bir sonraki komuttan devam edebilirsiniz.

İçindekiler:

| # | Adım | # | Adım |
|---|---|---|---|
| 0 | [Ön koşullar (Mac, SSO)](#adım-0--ön-koşullar-mac-sso) | 13 | [EC2 instance'ı](#adım-13--ec2-instanceı-user-data) |
| 1 | [Değişkenler](#adım-1--değişkenler-ve-durum-dosyası) | 14 | [İlk başlatma](#adım-14--servisi-ilk-kez-başlat-session-manager) |
| 2 | [Ön kontroller](#adım-2--ön-kontroller-dns-vpc) | 15 | [Yedeklemeyi dene](#adım-15--yedeklemeyi-dene) |
| 3 | [ECR deposu](#adım-3--ecr-deposu) | 16 | [Frontend bucket'ı](#adım-16--frontend-bucketı) |
| 4 | [Image'ı ECR'a gönder](#adım-4--backend-imageını-derle-ve-ecra-gönder) | 17 | [ACM sertifikası](#adım-17--acm-sertifikası-us-east-1) |
| 5 | [Yedek bucket'ı](#adım-5--yedek-bucketı) | 18 | [CloudFront](#adım-18--cloudfront-function-oac-ve-dağıtım) |
| 6 | [Log grubu](#adım-6--cloudwatch-log-grubu) | 19 | [Frontend'i yükle](#adım-19--frontendi-derle-ve-yükle) |
| 7 | [SSM parametreleri](#adım-7--ssm-parametreleri) | 20 | [DNS geçişi](#adım-20--dns-apex--www--cloudfront-geçiş) |
| 8 | [KMS anahtarı](#adım-8--ssm-kms-anahtarının-arni) | 21 | [İzleme](#adım-21--health-izleme-ve-e-posta-uyarısı) |
| 9 | [IAM rolü](#adım-9--iam-rolü-ve-instance-profile) | 22 | [Rutin: yeni sürüm](#adım-22--rutin-yeni-sürüm-yayınlama) |
| 10 | [Security group](#adım-10--security-group) | 23 | [Teardown](#adım-23--geri-alma-ve-temizlik-teardown) |
| 11 | [Elastic IP](#adım-11--elastic-ip) | 24 | [Maliyet](#adım-24--aylık-maliyet-tahmini) |
| 12 | [DNS: api](#adım-12--dns-api--elastic-ip) | Ek | [Kaynak adları](#ek-a--kaynak-adları) · [Gereksinimden sapmalar](#ek-b--gereksinimden-bilinçli-sapmalar) |

---

## Adım 0 — Ön koşullar (Mac, SSO)

**Ne yapıyoruz:** Mac'e AWS CLI v2 ve Session Manager eklentisini kuruyor, uzun ömürlü access key oluşturmadan IAM Identity Center (SSO) ile kısa ömürlü kimlik alıyoruz.

**Komutlar:**

```bash
# 1) AWS CLI v2 (resmi paket)
curl -fsSL https://awscli.amazonaws.com/AWSCLIV2.pkg -o /tmp/AWSCLIV2.pkg
sudo installer -pkg /tmp/AWSCLIV2.pkg -target /

# 2) Session Manager eklentisi (SSH yerine; 22 numaralı port kapalı kalacak)
curl -fsSL https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/session-manager-plugin.pkg \
  -o /tmp/session-manager-plugin.pkg
sudo installer -pkg /tmp/session-manager-plugin.pkg -target /
sudo ln -sf /usr/local/sessionmanagerplugin/bin/session-manager-plugin /usr/local/bin/session-manager-plugin

# 3) Diğer araçlar: jq (macOS 15+ ile gelir), Docker Desktop (buildx), Node 20+ (frontend build), git
jq --version && docker buildx version && node --version && git --version
```

IAM Identity Center **bir kez, konsoldan** açılır (CLI ile de yapılabilir ama bu kısım konsolda daha az hatalı):

1. Konsol → **IAM Identity Center** → bölge **eu-central-1** → *Enable*. Hesap bir AWS Organization'a bağlı değilse burada ücretsiz bir organizasyon oluşturulur.
2. *Users* → kendinize bir kullanıcı açın ve MFA'yı zorunlu tutun.
3. *Permission sets* → `AdministratorAccess` (session süresi 4 saat). Bu yetki yalnızca **sizin kurulum oturumunuz** için. Uygulamanın kullanacağı rol [Adım 9](#adım-9--iam-rolü-ve-instance-profile)'da en az yetkiyle ayrıca kurulur.
4. *AWS accounts* → hesabı seçin → kullanıcınızı bu permission set'le atayın.
5. *Settings* sayfasındaki **AWS access portal URL**'ini (`https://d-….awsapps.com/start`) not alın.

```bash
aws configure sso --profile newsradar
#   SSO session name: newsradar
#   SSO start URL:    <access portal URL>
#   SSO region:       eu-central-1
#   SSO registration scopes: (Enter — varsayılan)
#   → tarayıcıda onaylayın → hesabı ve AdministratorAccess rolünü seçin
#   CLI default client Region: eu-central-1
#   CLI default output format: json
aws sso login --profile newsradar
```

**Doğrulama:**

```bash
aws --version
aws sts get-caller-identity --profile newsradar --query Arn --output text
session-manager-plugin --version
```

Beklenen çıktı:
- `aws-cli/2.…`
- `arn:aws:sts::…:assumed-role/AWSReservedSSO_AdministratorAccess_…/<kullanıcı>`. Rol adı `AWSReservedSSO_` ile başlamalı; bu, kimliğin kısa ömürlü olduğunu gösterir.
- Eklentinin sürüm numarası.

**Hata alırsam:**
- `The SSO session associated with this profile has expired` → `aws sso login --profile newsradar`. Bu beklenen bir durum: oturum 4 saatte bir yenilenir.
- **Identity Center açılamıyorsa** (hesap, yönetim hesabına erişiminiz olmayan bir Organization'ın üyesiyse ya da organizasyon politikası buna izin vermiyorsa) **burada durun ve bana yazın.** Uzun ömürlü access key oluşturmayın; alternatifini birlikte konuşalım.
- Kök (root) kullanıcıyla bu adımlardan hiçbirini yapmayın. Kök yalnızca Identity Center'ı açmak için gerekiyorsa sonra MFA'lı bırakın.
- `installer: Error` → paketi Finder'dan çift tıklayarak kurun ve komutun geri kalanından devam edin.

---

## Adım 1 — Değişkenler ve durum dosyası

**Ne yapıyoruz:** Tüm adımların kullandığı sabitleri ve yardımcı fonksiyonları tek yerde tanımlıyoruz. **Her yeni terminalde bu bloğu ilk iş olarak yeniden çalıştırın.**

**Komutlar:**

```bash
bash                                   # zsh'den bash'e geçin (komutlar bash içindir)
cd "$(git -C ~/Desktop/newsradar rev-parse --show-toplevel)"

export AWS_PROFILE=newsradar
export REGION=eu-central-1
export AWS_REGION="$REGION"
export DOMAIN=newsradarapp.com
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export BACKUP_BUCKET="newsradar-backups-${ACCOUNT_ID}"
export FRONTEND_BUCKET="newsradar-frontend-${ACCOUNT_ID}"
export ECR_REPO=newsradar-api
export ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
export LOG_GROUP=/newsradar/prod
export SSM_PREFIX=/newsradar/prod
export ROLE_NAME=newsradar-ec2-role
export PROFILE_NAME=newsradar-ec2-profile
export SG_NAME=newsradar-api-sg
export INSTANCE_NAME=newsradar-api
export CF_FUNCTION_NAME=newsradar-www-redirect
export OAC_NAME=newsradar-frontend-oac
export ALARM_NAME=newsradar-api-health
export SNS_TOPIC_NAME=newsradar-alerts
export REPO_URL="https://github.com/$(git remote get-url origin | sed -E 's#^(https://github\.com/|git@github\.com:)##')"
export REPO_BRANCH=main
export STATE_FILE="$HOME/.newsradar-aws-state.env"

# Durum dosyası: adımların ürettiği kimlikler (sır yok). Yeni terminalde geri yüklenir.
touch "$STATE_FILE" && chmod 600 "$STATE_FILE" && . "$STATE_FILE"
save() { # save AD DEĞER → bu oturuma export + durum dosyasına yaz
  export "$1=$2"
  { grep -v "^export $1=" "$STATE_FILE" || true; printf 'export %s=%q\n' "$1" "$2"; } >"$STATE_FILE.tmp"
  mv "$STATE_FILE.tmp" "$STATE_FILE" && chmod 600 "$STATE_FILE"
}
render() { python3 deploy/aws/render.py "$@"; }   # __AD__ yer tutucularını değişkenlerle doldurur
put_param() { # put_param AD TÜR [DEĞER] — değer verilmezse sorulur (SecureString gizli); boş = atla
  local name="$1" type="$2" value="${3-}"
  if [ $# -lt 3 ]; then
    if [ "$type" = SecureString ]; then read -rsp "  $name (gizli; boş = atla): " value; echo
    else read -rp "  $name (boş = atla): " value; fi
  fi
  if [ -z "$value" ]; then echo "  - $name atlandı (uygulama varsayılanı kullanılır)"; return 0; fi
  # Değer stdin'den gider: argv'de (ps) ve shell geçmişinde görünmez.
  printf '%s' "$value" | aws ssm put-parameter --region "$REGION" --name "$SSM_PREFIX/$name" --type "$type" \
    --value file:///dev/stdin --overwrite --query Version --output text >/dev/null && echo "  ✓ $name ($type)"
}
```

**Doğrulama:**

```bash
printf '%s\n' "$ACCOUNT_ID" "$BACKUP_BUCKET" "$FRONTEND_BUCKET" "$ECR_URI" "$REPO_URL" | sed 's/[0-9]\{12\}/<hesap>/'
```

Beklenen çıktı: beş dolu satır. Hesap ID'si `<hesap>` olarak maskelenir, `REPO_URL` `https://github.com/<kullanıcı>/newsradar.git` biçimindedir.

**Hata alırsam:**
- `ACCOUNT_ID` boşsa SSO oturumunun süresi dolmuştur: `aws sso login`, sonra bloğu tekrar çalıştırın.
- `REPO_URL` yanlışsa `git remote -v` çıktısına bakın ve değişkeni elle `export REPO_URL=https://github.com/<kullanıcı>/<repo>.git` diye verin.

---

## Adım 2 — Ön kontroller (DNS, VPC)

**Ne yapıyoruz:** Hosted zone'un gerçekten bu alan adına bağlı olduğunu doğruluyor, mevcut DNS kayıtlarının yedeğini alıyor ve varsayılan VPC'yi buluyoruz.

**Komutlar:**

```bash
save HOSTED_ZONE_ID "$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
  --query "HostedZones[?Name=='${DOMAIN}.'].Id | [0]" --output text | sed 's|/hostedzone/||')"

# Geri dönüş için mevcut tüm kayıtların yedeği (Adım 20 ve 23 bu dosyayı kullanır).
save DNS_BACKUP "$HOME/newsradar-dns-backup-$(date +%Y%m%d-%H%M).json"
aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" >"$DNS_BACKUP"

save VPC_ID "$(aws ec2 describe-vpcs --region "$REGION" --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text)"
save SUBNET_ID "$(aws ec2 describe-subnets --region "$REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" Name=default-for-az,Values=true Name=availability-zone,Values="${REGION}a" \
  --query 'Subnets[0].SubnetId' --output text)"
```

**Doğrulama:**

```bash
# 1) Kayıt şirketindeki NS kayıtları bu zone'u göstermeli
diff <(dig +short NS "$DOMAIN" | sort) \
     <(aws route53 get-hosted-zone --id "$HOSTED_ZONE_ID" --query 'DelegationSet.NameServers' --output text | tr '\t' '\n' | sed 's/$/./' | sort) \
  && echo "NS eşleşiyor"
# 2) Etkilenecek mevcut kayıtlar ve CAA
jq -r --arg d "$DOMAIN." '.ResourceRecordSets[] | select(.Name==$d or .Name=="www."+$d or .Name=="api."+$d or .Type=="CAA")
  | "\(.Name) \(.Type) \(.AliasTarget.DNSName // ([.ResourceRecords[]?.Value] | join(",")))"' "$DNS_BACKUP"
echo "$HOSTED_ZONE_ID $VPC_ID $SUBNET_ID"
```

Beklenen çıktı:
- `NS eşleşiyor`.
- Apex/www/api kayıtlarının bugünkü hali. Bunlar Adım 12 ve 20'de değişecek; yedeği `$DNS_BACKUP`'ta duruyor.
- Üç kimlik: `Z…`, `vpc-…`, `subnet-…`.

**Hata alırsam:**
- `HOSTED_ZONE_ID` `None` ise zone başka bir hesapta ya da adı farklıdır. `aws route53 list-hosted-zones` ile bakın.
- NS eşleşmiyorsa alan adı bu zone'a delege edilmemiştir; Adım 12'den sonraki hiçbir şey çalışmaz. Kayıt şirketinde NS kayıtlarını zone'unkilerle değiştirin.
- **CAA kaydı varsa** hem `amazon.com` (ACM, Adım 17) hem `letsencrypt.org` (Caddy, Adım 14) izinli olmalı. Değilse bu iki değeri CAA kaydına ekleyin.
- `VPC_ID` `None` ise bölgede varsayılan VPC yoktur: `aws ec2 create-default-vpc --region "$REGION"`, sonra komutları tekrarlayın.
- `SUBNET_ID` `None` ise `${REGION}a` yerine `${REGION}b` deneyin.

---

## Adım 3 — ECR deposu

**Ne yapıyoruz:** Backend image'ı için push sırasında taranan ve yalnızca son 10 image'ı tutan bir ECR deposu oluşturuyoruz.

**Komutlar:**

```bash
aws ecr create-repository --region "$REGION" --repository-name "$ECR_REPO" \
  --image-scanning-configuration scanOnPush=true --image-tag-mutability MUTABLE \
  --encryption-configuration encryptionType=AES256 --tags Key=Project,Value=newsradar
aws ecr put-lifecycle-policy --region "$REGION" --repository-name "$ECR_REPO" \
  --lifecycle-policy-text file://deploy/aws/ecr-lifecycle.json
```

**Doğrulama:**

```bash
aws ecr describe-repositories --region "$REGION" --repository-names "$ECR_REPO" \
  --query 'repositories[0].[repositoryUri,imageScanningConfiguration.scanOnPush]' --output text
aws ecr get-lifecycle-policy --region "$REGION" --repository-name "$ECR_REPO" \
  --query lifecyclePolicyText --output text | jq -c '.rules[0].selection'
```

Beklenen çıktı:
- `<ECR_URI>	True`
- `{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10}`

**Hata alırsam:**
- `RepositoryAlreadyExistsException` → depo zaten var. Tarama ayarını garantiye almak için `aws ecr put-image-scanning-configuration --region "$REGION" --repository-name "$ECR_REPO" --image-scanning-configuration scanOnPush=true` çalıştırıp lifecycle komutundan devam edin.

---

## Adım 4 — Backend image'ını derle ve ECR'a gönder

**Ne yapıyoruz:** arm64 (t4g) image'ı Mac'te derleyip commit kısaltmasıyla ve `prod` etiketiyle ECR'a gönderiyoruz.

**Komutlar:**

```bash
git status --short                      # boş olmalı: etiket = commit
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR_URI%%/*}"
save IMAGE_TAG "$(git rev-parse --short HEAD)"
docker buildx build --platform linux/arm64 -t "$ECR_URI:$IMAGE_TAG" -t "$ECR_URI:prod" --push backend
save BACKEND_IMAGE "$ECR_URI:prod"
aws ecr wait image-scan-complete --region "$REGION" --repository-name "$ECR_REPO" --image-id imageTag=prod
```

**Doğrulama:**

```bash
aws ecr describe-images --region "$REGION" --repository-name "$ECR_REPO" --image-ids imageTag=prod \
  --query 'imageDetails[0].[imageTags,imageScanStatus.status]' --output json | jq -c
aws ecr describe-image-scan-findings --region "$REGION" --repository-name "$ECR_REPO" --image-id imageTag=prod \
  --query 'imageScanFindings.findingSeverityCounts' --output json
```

Beklenen çıktı:
- `[["<commit>","prod"],"COMPLETE"]` (etiketlerin sırası değişebilir)
- `{}` ya da önem derecesine göre sayılar. `CRITICAL` varsa ayrıntısını `describe-image-scan-findings` ile görün; yayına almadan önce temel image'ı güncelleyin (`docker buildx build --pull …`).

**Hata alırsam:**
- `no basic auth credentials` / `denied` → giriş token'ı 12 saatte bir yenilenir; `docker login` satırını tekrarlayın.
- `docker exporter does not currently support exporting manifest lists` → `docker buildx create --name newsradar --use`, sonra build satırını tekrarlayın.
- `git status` boş değilse önce commit'leyin. Etiket commit'i göstermeli ki geri dönüş (Adım 22) anlamlı olsun.

---

## Adım 5 — Yedek bucket'ı

**Ne yapıyoruz:** Versioning'li, SSE-S3 ile şifreli, herkese tamamen kapalı ve yedekleri 30 gün sonra silen yedek bucket'ını oluşturuyoruz.

**Komutlar:**

```bash
aws s3api create-bucket --region "$REGION" --bucket "$BACKUP_BUCKET" \
  --create-bucket-configuration LocationConstraint="$REGION"
aws s3api put-public-access-block --bucket "$BACKUP_BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket "$BACKUP_BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BACKUP_BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-lifecycle-configuration --bucket "$BACKUP_BUCKET" \
  --lifecycle-configuration file://deploy/aws/backup-lifecycle.json
aws s3api put-bucket-tagging --bucket "$BACKUP_BUCKET" --tagging 'TagSet=[{Key=Project,Value=newsradar}]'
```

Lifecycle kuralı ([deploy/aws/backup-lifecycle.json](../deploy/aws/backup-lifecycle.json)) şöyle çalışır:
- Her yedek 30. günde güncel olmaktan çıkar.
- Eski sürümler, güncel olmaktan çıktıktan 30 gün sonra kalıcı olarak silinir.

Böylece kazara silinen ya da üzerine yazılan bir yedek 30 gün boyunca kurtarılabilir. Süresi doğal yolla dolan bir yedek ise en geç 60. günde tamamen kaybolur. Kesin 30 gün istiyorsanız `NoncurrentDays` değerini `1` yapın; bu durumda kazara silmeye karşı koruma 1 güne düşer.

**Doğrulama:**

```bash
aws s3api get-public-access-block --bucket "$BACKUP_BUCKET" --query PublicAccessBlockConfiguration --output json | jq -c
aws s3api get-bucket-versioning --bucket "$BACKUP_BUCKET" --query Status --output text
aws s3api get-bucket-encryption --bucket "$BACKUP_BUCKET" \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text
aws s3api get-bucket-lifecycle-configuration --bucket "$BACKUP_BUCKET" --query 'Rules[].ID' --output text
```

Beklenen çıktı:
- dört alanın tamamı `true`
- `Enabled`
- `AES256`
- `expire-backups-30d	remove-expired-delete-markers`

**Hata alırsam:**
- `BucketAlreadyOwnedByYou` → bucket zaten sizin; sonraki satırlardan devam edin.
- `BucketAlreadyExists` → ad başka bir hesapta alınmış (bucket adları küreseldir). Adım 1'deki adı değiştirin, örneğin `newsradar-backups-${ACCOUNT_ID}-2`. Bu ad değişirse [Ek A](#ek-a--kaynak-adları)'daki tüm geçişler de değişir.
- `IllegalLocationConstraintException` → `--region` ile `LocationConstraint` aynı olmalı.

---

## Adım 6 — CloudWatch log grubu

**Ne yapıyoruz:** Container log'larının gideceği log grubunu 7 gün saklama süresiyle önceden oluşturuyoruz; Docker'ın awslogs sürücüsü grup yoksa container'ı başlatmaz.

**Komutlar:**

```bash
aws logs create-log-group --region "$REGION" --log-group-name "$LOG_GROUP" --tags Project=newsradar
aws logs put-retention-policy --region "$REGION" --log-group-name "$LOG_GROUP" --retention-in-days 7
```

**Doğrulama:**

```bash
aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$LOG_GROUP" \
  --query 'logGroups[0].[logGroupName,retentionInDays]' --output text
```

Beklenen çıktı: `/newsradar/prod	7`

**Hata alırsam:**
- `ResourceAlreadyExistsException` → grup zaten var. Yalnızca `put-retention-policy` satırını çalıştırın.

Not: 7 günlük saklama, gizlilik metnindeki "IP'ler 7 gün sonra silinir" taahhüdüyle uyumlu. Caddy'nin erişim log'larında istemci IP'si bulunur.

---

## Adım 7 — SSM parametreleri

**Ne yapıyoruz:** [deploy/PARAMETERS.md](../deploy/PARAMETERS.md)'deki her parametreyi `/newsradar/prod/` altına yazıyoruz; değerler `read -s` ile girilir, komut satırına ve geçmişe düşmez.

**Komutlar:**

```bash
# put_param: Adım 1'de tanımlı (değer stdin'den gider; argv'de ve geçmişte görünmez).
# --- 1. Zorunlu ---
put_param DOMAIN String "$DOMAIN"
# APP_SECRET üretilir, hiç ekrana basılmaz. Zaten varsa DOKUNULMAZ (değişirse tüm oturumlar düşer).
aws ssm get-parameter --region "$REGION" --name "$SSM_PREFIX/APP_SECRET" >/dev/null 2>&1 \
  || put_param APP_SECRET SecureString "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
put_param ANTHROPIC_API_KEY SecureString
put_param NEWSRADAR_CORS_ORIGINS String "https://${DOMAIN},https://www.${DOMAIN}"
put_param BACKUP_BUCKET String "$BACKUP_BUCKET"
put_param BACKEND_IMAGE String "$BACKEND_IMAGE"

# --- 2. Sırlar (isteğe bağlı; boş bırakılan özellik kapanır) ---
for n in FINNHUB_API_KEY NEWSAPI_KEY FMP_API_KEY APP_PASSWORD NEWSRADAR_LLM_API_KEY; do put_param "$n" SecureString; done

# --- 3. AWS profili ---
put_param NEWSRADAR_COOKIE_SAMESITE String lax
put_param NEWSRADAR_COOKIE_SECURE String on
put_param NEWSRADAR_COOKIE_DOMAIN String ".${DOMAIN}"
put_param NEWSRADAR_HOSTING_PROVIDER String "AWS (${REGION})"
put_param NEWSRADAR_SEED_ON_START String on
put_param NEWSRADAR_CONTACT_EMAIL String          # sorulur (gizlilik metnindeki adres)
put_param ADMIN_USERNAME String                   # sorulur

# --- 4. İnce ayar: boş bırakırsanız koddaki varsayılan geçerli (değerler PARAMETERS.md'de) ---
for n in NEWSRADAR_LLM_PROVIDER NEWSRADAR_ARTICLE_MODEL NEWSRADAR_ASSESSMENT_MODEL NEWSRADAR_CHAT_MODEL \
  NEWSRADAR_LLM_BASE_URL NEWSRADAR_LLM_MODEL NEWSRADAR_DAILY_BUDGET_USD NEWSRADAR_DAILY_ENTITY_ADD_CAP \
  NEWSRADAR_MAX_USERS NEWSRADAR_MAX_ENTITIES_ANON NEWSRADAR_MAX_ENTITIES_REGISTERED NEWSRADAR_MAX_REFRESH_ANON \
  NEWSRADAR_MAX_REFRESH_REGISTERED NEWSRADAR_ANON_SESSIONS_PER_IP_HOUR NEWSRADAR_FEEDBACK_PER_IP_HOUR \
  NEWSRADAR_IP_RETENTION_DAYS NEWSRADAR_TOKEN_TTL_DAYS NEWSRADAR_SESSION_COOKIE NEWSRADAR_SESSION_COOKIE_DAYS \
  NEWSRADAR_SCHEDULER NEWSRADAR_SCHEDULER_HOURS NEWSRADAR_LOOKBACK_HOURS NEWSAPI_DAILY_LIMIT NEWSRADAR_BATCH_SIZE \
  NEWSRADAR_MAX_ARTICLES_PER_ENTITY NEWSRADAR_ANALYSIS_CONCURRENCY NEWSRADAR_MAX_OUTPUT_TOKENS; do
  put_param "$n" String
done
```

[PARAMETERS.md](../deploy/PARAMETERS.md) §5'teki değişkenler (`NEWSRADAR_DB`, `NEWSRADAR_TRUSTED_PROXY`, `NEWSRADAR_CADDY_IP`, `FRONTEND_URL`, `VITE_*`, host değişkenleri) bilerek SSM'e **yazılmaz**: compose bunları sabitler ya da yalnızca Render'da veya build sırasında kullanılırlar.

**Doğrulama:**

```bash
aws ssm get-parameters-by-path --region "$REGION" --path "$SSM_PREFIX/" \
  --query 'Parameters[].[Name,Type]' --output text | sort
aws ssm get-parameters-by-path --region "$REGION" --path "$SSM_PREFIX/" --query 'Parameters[].Name' --output text \
  | tr '\t' '\n' | sed "s|$SSM_PREFIX/||" | sort >/tmp/newsradar-params.txt
for r in DOMAIN APP_SECRET ANTHROPIC_API_KEY NEWSRADAR_CORS_ORIGINS BACKUP_BUCKET BACKEND_IMAGE; do
  grep -qx "$r" /tmp/newsradar-params.txt && echo "✓ $r" || echo "✗ EKSİK: $r"; done
```

Beklenen çıktı:
- Ad ve tür listesi. Değerler **gösterilmez**, çünkü `--with-decryption` kullanılmadı.
- Zorunlu altı parametrenin hepsi `✓`.

**Hata alırsam:**
- `ParameterAlreadyExists` → `--overwrite` zaten var. Bu hata yalnızca türü değiştirmeye çalışınca çıkar (ör. String → SecureString): önce `aws ssm delete-parameter --name …`, sonra tekrar yazın.
- Bir değeri yanlış girdiyseniz aynı `put_param` satırını tekrar çalıştırın.
- `AccessDeniedException` → SSO oturumu düşmüştür: `aws sso login`.
- `ValidationException … value` → SSM boş değer kabul etmez. `put_param` zaten boş değeri atlıyor; elle girerken boş bırakmayın.

---

## Adım 8 — SSM KMS anahtarının ARN'i

**Ne yapıyoruz:** SecureString'leri şifreleyen AWS-managed `aws/ssm` anahtarının ARN'ini alıyoruz; IAM politikası `kms:Decrypt` iznini yalnızca bu anahtara veriyor.

**Komutlar:**

```bash
save SSM_KMS_KEY_ARN "$(aws kms describe-key --region "$REGION" --key-id alias/aws/ssm --query KeyMetadata.Arn --output text)"
```

**Doğrulama:**

```bash
echo "$SSM_KMS_KEY_ARN" | sed 's/[0-9]\{12\}/<hesap>/'
```

Beklenen çıktı: `arn:aws:kms:eu-central-1:<hesap>:key/<uuid>`

**Hata alırsam:**
- `NotFoundException` → bu anahtar ilk SecureString yazılınca oluşur. Adım 7'yi tamamlayın.

---

## Adım 9 — IAM rolü ve instance profile

**Ne yapıyoruz:** EC2'nin üstleneceği rolü yalnızca gereken izinlerle oluşturuyoruz ([deploy/iam/](../deploy/iam/)); uzun ömürlü anahtar yok, instance kimliği IMDSv2'den gelir.

İzinlerin tamamı: `/newsradar/prod/*` parametrelerini okuma, yalnızca bu parametreler için `kms:Decrypt`, yedek bucket'ında yalnızca `backups/` öneki, yalnızca `newsradar-api` reposundan image çekme, yalnızca `/newsradar/prod` log grubuna yazma, ve AWS-managed `AmazonSSMManagedInstanceCore` (Session Manager). Gereksinimden sapan iki nokta (`ecr:GetAuthorizationToken` ve log izinleri) [Ek B](#ek-b--gereksinimden-bilinçli-sapmalar)'de açıklanıyor.

**Komutlar:**

```bash
render deploy/iam/ec2-instance-policy.json >/tmp/newsradar-ec2-policy.json
aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://deploy/iam/ec2-trust-policy.json \
  --description "NewsRadar EC2 instance role" --tags Key=Project,Value=newsradar
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name newsradar-ec2-inline \
  --policy-document file:///tmp/newsradar-ec2-policy.json
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" --tags Key=Project,Value=newsradar
aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
aws iam wait instance-profile-exists --instance-profile-name "$PROFILE_NAME"
sleep 15                                # IAM yayılımı: run-instances'ın profili görmesi birkaç saniye sürer
```

**Doğrulama:**

```bash
aws accessanalyzer validate-policy --region "$REGION" --policy-type IDENTITY_POLICY \
  --policy-document file:///tmp/newsradar-ec2-policy.json --query 'findings[].[findingType,issueCode]' --output text
aws iam list-attached-role-policies --role-name "$ROLE_NAME" --query 'AttachedPolicies[].PolicyName' --output text
aws iam list-role-policies --role-name "$ROLE_NAME" --query PolicyNames --output text
aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" --query 'InstanceProfile.Roles[0].RoleName' --output text
```

Beklenen çıktı:
- Access Analyzer: boş, ya da yalnızca `ecr:GetAuthorizationToken`'ın `*` kaynağıyla ilgili bir `SUGGESTION`/`WARNING`. `ERROR` olmamalı.
- `AmazonSSMManagedInstanceCore`
- `newsradar-ec2-inline`
- `newsradar-ec2-role`

**Hata alırsam:**
- `render.py: … eksik/boş değişken: SSM_KMS_KEY_ARN` → Adım 8'i çalıştırın. Değişken boşsa ilgili adım eksik kalmıştır.
- `EntityAlreadyExists` → rol ya da profil zaten var. `put-role-policy` idempotenttir; kalan satırlardan devam edin.
- `MalformedPolicyDocument` → `/tmp/newsradar-ec2-policy.json`'u `jq . /tmp/newsradar-ec2-policy.json` ile açıp yer tutucuların dolu olduğunu kontrol edin.

---

## Adım 10 — Security group

**Ne yapıyoruz:** Dışarıdan yalnızca 80 ve 443'e izin veren bir security group oluşturuyoruz; 22 kapalı, bağlantı Session Manager ile.

**Komutlar:**

```bash
save SG_ID "$(aws ec2 create-security-group --region "$REGION" --vpc-id "$VPC_ID" --group-name "$SG_NAME" \
  --description "NewsRadar API - only 80/443, no SSH" \
  --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=newsradar-api-sg},{Key=Project,Value=newsradar}]' \
  --query GroupId --output text)"
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" --ip-permissions \
  'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' \
  'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' \
  'IpProtocol=udp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]'
```

UDP 443, Caddy'nin HTTP/3'ü (QUIC) içindir. Aynı porttur; istemezseniz son satırı çıkarabilirsiniz, HTTP/2 yine çalışır.

**Doğrulama:**

```bash
aws ec2 describe-security-groups --region "$REGION" --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[].[IpProtocol,FromPort,ToPort]' --output text
```

Beklenen çıktı: yalnızca `tcp 80 80`, `tcp 443 443`, `udp 443 443`. **22 olmamalı.**

**Hata alırsam:**
- `InvalidGroup.Duplicate` → grup zaten var: `save SG_ID "$(aws ec2 describe-security-groups --region "$REGION" --filters Name=group-name,Values="$SG_NAME" --query 'SecurityGroups[0].GroupId' --output text)"`, sonra ingress komutunu çalıştırın.
- `InvalidPermission.Duplicate` → kurallar zaten var, sorun değil.
- `InvalidParameterValue … description` → açıklamada Türkçe karakter kullanmayın (yalnızca ASCII).

---

## Adım 11 — Elastic IP

**Ne yapıyoruz:** API'nin sabit genel IP'sini ayırıyoruz; DNS `api` kaydı bu adrese işaret edecek.

**Komutlar:**

```bash
read -r alloc ip < <(aws ec2 allocate-address --region "$REGION" --domain vpc \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=newsradar-api-eip},{Key=Project,Value=newsradar}]' \
  --query '[AllocationId,PublicIp]' --output text)
save EIP_ALLOC "$alloc"; save EIP_IP "$ip"
```

**Doğrulama:**

```bash
aws ec2 describe-addresses --region "$REGION" --allocation-ids "$EIP_ALLOC" --query 'Addresses[0].[PublicIp,AssociationId]' --output text
```

Beklenen çıktı: `<IP>	None`. Instance'a Adım 13'te bağlanacak.

**Hata alırsam:**
- `AddressLimitExceeded` → bölgede 5 EIP sınırı dolmuş. Kullanılmayanı bırakın (`release-address`) ya da kota artışı isteyin.
- Not: Ayrılmış her genel IPv4 adresi, bağlı olsun olmasın, saatlik ücretlidir ([Adım 24](#adım-24--aylık-maliyet-tahmini)).

---

## Adım 12 — DNS: api → Elastic IP

**Ne yapıyoruz:** `api.newsradarapp.com` için A kaydını EIP'ye yönlendiriyoruz; Caddy Adım 14'te sertifikayı bu kayıt sayesinde alacak.

**Komutlar:**

```bash
cat >/tmp/newsradar-dns-api.json <<EOF
{"Comment": "api -> Elastic IP",
 "Changes": [{"Action": "UPSERT", "ResourceRecordSet": {"Name": "api.${DOMAIN}", "Type": "A", "TTL": 300,
              "ResourceRecords": [{"Value": "${EIP_IP}"}]}}]}
EOF
change="$(aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/newsradar-dns-api.json --query ChangeInfo.Id --output text)"
aws route53 wait resource-record-sets-changed --id "$change"
```

**Doğrulama:**

```bash
dig +short "api.$DOMAIN" @1.1.1.1; echo "beklenen: $EIP_IP"
```

Beklenen çıktı: iki satır aynı IP.

**Hata alırsam:**
- Eski bir değer ya da boş çıktı: önceki kaydın TTL'i ya da negatif önbellek dolmamıştır. Birkaç dakika sonra `dig +short "api.$DOMAIN" @$(dig +short NS "$DOMAIN" | head -1)` ile doğrudan zone'a sorun.
- `InvalidChangeBatch … CNAME` → `api` için bir CNAME kaydı var. Önce o kaydı silin (değerini `$DNS_BACKUP`'tan alın).

---

## Adım 13 — EC2 instance'ı (user-data)

**Ne yapıyoruz:** Amazon Linux 2023, t4g.small, şifreli 20 GB gp3 diskli ve IMDSv2 zorunlu instance'ı açıyoruz. İlk açılışta [user-data](../deploy/aws/user-data.sh) gerekenleri kuruyor.

User-data şunları yapar:
- Docker ≥25 kurar ve `docker version` ile doğrular. AL2023 deposundaki sürüm 25'ten küçükse resmi statik paketi kurar.
- compose ve buildx eklentilerini sabit sha256 doğrulamasıyla kurar.
- aws CLI, sqlite3, gzip, curl ve python3'ü kurar.
- Docker log'larını CloudWatch'a yönlendirir.
- Public repoyu https ile `/opt/newsradar`'a klonlar; kimlik bilgisi gerekmez.
- systemd birimlerini kurar ve yedek timer'ını etkinleştirir.

**Ön koşul:** Repo **public** olmalı ve bu runbook'un ve `deploy/` klasörünün son hali **GitHub'a push edilmiş** olmalı (`$REPO_BRANCH`), çünkü instance repoyu oradan, kimlik bilgisi olmadan https ile klonlar.

**Komutlar:**

```bash
git fetch -q origin && git status -sb | head -1        # "ahead" görünmemeli
curl -s -o /dev/null -w 'repo herkese açık mı: %{http_code}\n' "${REPO_URL%.git}"   # 200 olmalı (404 = private)
render deploy/aws/user-data.sh >/tmp/newsradar-user-data.sh
save INSTANCE_ID "$(aws ec2 run-instances --region "$REGION" \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --instance-type t4g.small --credit-specification CpuCredits=standard \
  --iam-instance-profile Name="$PROFILE_NAME" \
  --network-interfaces "DeviceIndex=0,SubnetId=${SUBNET_ID},Groups=${SG_ID},AssociatePublicIpAddress=false" \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled \
  --user-data file:///tmp/newsradar-user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=newsradar-api},{Key=Project,Value=newsradar}]' \
                       'ResourceType=volume,Tags=[{Key=Name,Value=newsradar-api-root},{Key=Project,Value=newsradar}]' \
  --query 'Instances[0].InstanceId' --output text)"
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
aws ec2 associate-address --region "$REGION" --instance-id "$INSTANCE_ID" --allocation-id "$EIP_ALLOC"
aws ec2 wait instance-status-ok --region "$REGION" --instance-ids "$INSTANCE_ID"   # ~3-5 dk
```

Bu ayarların nedenleri:
- **Genel IP'siz açılış.** Instance bilerek genel IP'siz açılır (`AssociatePublicIpAddress=false`), çünkü EIP birkaç saniye sonra bağlanıyor. Böylece ikinci, ücretli bir genel IP oluşmuyor; user-data da internet gelene kadar bekliyor.
- **`HttpPutResponseHopLimit=1`.** Container'lar instance rolünün kimlik bilgilerine IMDS'ten ulaşamaz. Bu ayar yalnızca host'taki Docker daemon'ının, aws CLI'ın ve SSM agent'ın kimlik almasına izin veriyor.
- **`CpuCredits=standard`.** t4g'nin varsayılanı olan "unlimited" moddaki sürpriz CPU ücretini kapatır.

**Doğrulama:**

```bash
aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" --query \
  'Reservations[0].Instances[0].[InstanceType,PublicIpAddress,MetadataOptions.HttpTokens,PlatformDetails]' --output text
aws ec2 describe-volumes --region "$REGION" --filters Name=attachment.instance-id,Values="$INSTANCE_ID" \
  --query 'Volumes[0].[Size,VolumeType,Encrypted]' --output text
aws ssm describe-instance-information --region "$REGION" --filters Key=InstanceIds,Values="$INSTANCE_ID" \
  --query 'InstanceInformationList[0].PingStatus' --output text
aws ssm start-session --region "$REGION" --target "$INSTANCE_ID"
```

**[instance]** Session Manager oturumunda:

```bash
sudo tail -n 4 /var/log/newsradar-user-data.log
sudo docker version --format 'docker {{.Server.Version}}'; sudo docker compose version; sudo docker buildx version
aws --version; sqlite3 --version | cut -d' ' -f1; python3 --version
systemctl list-timers newsradar-backup.timer --no-pager | head -2
exit
```

Beklenen çıktı:
- `t4g.small	<EIP_IP>	required	Linux/UNIX`
- `20	gp3	True`
- `Online`. Agent'ın kaydı birkaç dakika sürebilir.
- user-data log'unun son satırı `[user-data] … tamam`. Docker `25.` ya da üstü, compose ve buildx sürümleri, aws/sqlite3/python3 sürümleri, ve `newsradar-backup.timer` için bir sonraki 03:15 UTC çalışma zamanı.

**Hata alırsam:**
- `Invalid IAM Instance Profile name` → IAM yayılımı tamamlanmamış. 30 sn bekleyip `run-instances`'ı tekrarlayın.
- `Unsupported … t4g.small … availability zone` → Adım 2'de başka bir AZ'nin subnet'ini seçin (`${REGION}b`).
- `PingStatus` 10 dakikadan uzun süre boşsa:
  - EIP bağlandı mı (`describe-addresses`)?
  - Profil instance'ta mı (`describe-instances --query '…IamInstanceProfile'`)?
  - Konsol çıktısı: `aws ec2 get-console-output --region "$REGION" --instance-id "$INSTANCE_ID" --latest --output text | tail -40`.
- user-data log'unda `HATA: satır N` görünüyorsa:
  - `sha256 tutmadı` → indirme bozulmuştur; aşağıdaki gibi yeniden çalıştırın.
  - `Authentication failed` / `Repository not found` → repo hâlâ private ya da `REPO_URL` yanlış. Public yapın; user-data kimlik bilgisi kullanmaz.
  - `REPO_URL https:// ile başlamalı` → Adım 1'deki `REPO_URL` https biçiminde olmalı.

  Düzelttikten sonra **[instance]** `sudo bash /var/lib/cloud/instance/scripts/part-001` ile tekrar çalıştırın (yoksa `/var/lib/cloud/instance/user-data.txt`). Betik tekrar çalıştırılabilir: repo zaten varsa yeniden klonlamaz.
- Instance'ı baştan kurmak en temiz yol olabilir: [Teardown T7](#t7--ec2-instanceı-adım-13) ile kapatıp bu adımı tekrarlayın. EIP, SG ve rol yerinde kalır.

---

## Adım 14 — Servisi ilk kez başlat (Session Manager)

**Ne yapıyoruz:** Instance'a Session Manager ile bağlanıp sırları SSM'den `.env`'ye yazıyor, image'ı ECR'dan çekiyor ve servisi başlatıyoruz.

**Komutlar:**

```bash
aws ssm start-session --region "$REGION" --target "$INSTANCE_ID"
```

**[instance]** (root olarak, `/opt/newsradar/deploy` içinde):

```bash
sudo -i
export AWS_REGION=eu-central-1               # Adım 1'deki REGION ile aynı
cd /opt/newsradar/deploy
./load-secrets.sh                            # → deploy/.env (600); değerler log'a yazılmaz
set -a; . <(grep -E '^(DOMAIN|BACKEND_IMAGE)=' .env); set +a
aws ecr get-login-password | docker login --username AWS --password-stdin "${BACKEND_IMAGE%%/*}"
docker compose pull backend
docker compose up -d --no-build
docker compose ps
./smoke-test.sh "api.${DOMAIN}"
```

**Doğrulama** (Mac'te, Adım 1'in değişkenleriyle):

```bash
curl -sS "https://api.${DOMAIN}/health"; echo
curl -sv "https://api.${DOMAIN}/health" -o /dev/null 2>&1 | grep -E 'issuer|HTTP/'
deploy/smoke-test.sh "api.${DOMAIN}"
```

Beklenen çıktı:
- `load-secrets.sh` için `yazıldı: /opt/newsradar/deploy/.env (izin 600, N parametre): …` ve `docker compose config: geçerli`. Yalnızca adlar görünür.
- `docker compose ps` çıktısında `backend … (healthy)` ve `caddy … Up`.
- `smoke-test.sh` için `== TAMAM`.
- Mac'te `{"status":"ok"}`, `issuer: … Let's Encrypt` ve `HTTP/2 200`.

**Hata alırsam:**
- `load-secrets.sh` hataları:
  - `zorunlu parametre eksik/boş: X` → Adım 7'de X'i yazın ve tekrar çalıştırın.
  - `AccessDenied … ssm:GetParametersByPath` / `kms:Decrypt` → Adım 9'daki politika doğru render edilmemiştir. Adım 8 ile 9'u tekrar çalıştırın.
- `docker login` / `pull` sırasında `denied` → ECR izinleri (`PullBackendImage`) ya da image etiketi yanlıştır. `BACKEND_IMAGE` değerine bakın; değer sır değildir.
- `failed to initialize logging driver … ResourceNotFoundException` → Adım 6 atlanmıştır. `… AccessDenied` → `ContainerLogsToCloudWatch` izni eksiktir.
- Caddy sertifika alamıyorsa (`docker compose logs caddy | grep -iE 'error|obtain'`):
  - `api` DNS kaydı EIP'yi göstermiyor olabilir (Adım 12).
  - 80/443 kapalı olabilir (Adım 10).
  - CAA kaydı engelliyor olabilir (Adım 2).

  **Sürekli yeniden başlatmayın:** Let's Encrypt'in başarısız deneme sınırı vardır (saatte 5). Sorunu düzeltip bir kez `docker compose restart caddy` deyin.
- `smoke-test.sh` `/health` için 502 dönüyorsa backend henüz healthy değildir: `docker compose logs backend --tail 50`.

İsteğe bağlı: eski verinizi taşımak isterseniz yerel bir yedeği S3'e koyup geri yükleyebilirsiniz:
- Mac: `aws s3 cp <yedek>.db.gz "s3://$BACKUP_BUCKET/backups/newsradar-YYYYMMDD-HHMM.db.gz"`
- **[instance]**: `./restore.sh newsradar-YYYYMMDD-HHMM.db.gz`

Render'ın ücretsiz katmanındaki DB kalıcı olmadığı için varsayılan olarak boş bir DB ile başlanır (seed açık).

---

## Adım 15 — Yedeklemeyi dene

**Ne yapıyoruz:** Gece timer'ını beklemeden yedek servisini bir kez çalıştırıp S3 izinlerini ve uçtan uca yedeklemeyi doğruluyoruz.

**Komutlar** **[instance]**:

```bash
sudo systemctl start newsradar-backup.service
sudo journalctl -u newsradar-backup.service -n 5 --no-pager
```

**Doğrulama** (Mac):

```bash
aws s3 ls "s3://$BACKUP_BUCKET/backups/"
```

Beklenen çıktı:
- journal'da `… [backup] tamam: s3://newsradar-backups-…/backups/newsradar-YYYYMMDD-HHMM.db.gz (N bayt)`.
- S3 listesinde aynı dosya.

**Hata alırsam:**
- `AccessDenied … PutObject` → `BackupObjectsReadWrite` ifadesindeki bucket adını kontrol edin.
- `head-object … 403` → `s3:GetObject` eksiktir (HeadObject bu izni kullanır).
- `BACKUP_BUCKET tanımlı değil` → `.env` yoktur; Adım 14'teki `load-secrets.sh`'i çalıştırın.

---

## Adım 16 — Frontend bucket'ı

**Ne yapıyoruz:** Statik frontend için herkese tamamen kapalı bir bucket oluşturuyoruz; okuma izni Adım 18'de yalnızca CloudFront'a (OAC) verilecek.

**Komutlar:**

```bash
aws s3api create-bucket --region "$REGION" --bucket "$FRONTEND_BUCKET" \
  --create-bucket-configuration LocationConstraint="$REGION"
aws s3api put-public-access-block --bucket "$FRONTEND_BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$FRONTEND_BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-tagging --bucket "$FRONTEND_BUCKET" --tagging 'TagSet=[{Key=Project,Value=newsradar}]'
```

**Doğrulama:**

```bash
aws s3api get-public-access-block --bucket "$FRONTEND_BUCKET" --query PublicAccessBlockConfiguration --output json | jq -c
aws s3api get-bucket-ownership-controls --bucket "$FRONTEND_BUCKET" --query 'OwnershipControls.Rules[0].ObjectOwnership' --output text
```

Beklenen çıktı:
- dört alanın tamamı `true`
- `BucketOwnerEnforced` (ACL'ler kapalı)

**Hata alırsam:** [Adım 5](#adım-5--yedek-bucketı)'teki bucket hatalarıyla aynı.

---

## Adım 17 — ACM sertifikası (us-east-1)

**Ne yapıyoruz:** CloudFront için `newsradarapp.com` ve `www.newsradarapp.com` sertifikasını us-east-1'de istiyor ve Route 53 DNS kaydıyla doğruluyoruz.

**Komutlar:**

```bash
save CERT_ARN "$(aws acm request-certificate --region us-east-1 --domain-name "$DOMAIN" \
  --subject-alternative-names "www.$DOMAIN" --validation-method DNS --key-algorithm RSA_2048 \
  --tags Key=Project,Value=newsradar --query CertificateArn --output text)"
sleep 15                                     # doğrulama kayıtlarının üretilmesi
aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord' --output json \
| jq '{Comment: "ACM DNS validation", Changes: (unique_by(.Name) | map({Action: "UPSERT",
      ResourceRecordSet: {Name: .Name, Type: .Type, TTL: 300, ResourceRecords: [{Value: .Value}]}}))}' \
  >/tmp/newsradar-acm-validation.json
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/newsradar-acm-validation.json --query ChangeInfo.Status --output text
aws acm wait certificate-validated --region us-east-1 --certificate-arn "$CERT_ARN"   # genelde 2-10 dk
```

**Doğrulama:**

```bash
aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" \
  --query 'Certificate.[Status,join(`,`,SubjectAlternativeNames)]' --output text
```

Beklenen çıktı: `ISSUED	newsradarapp.com,www.newsradarapp.com`

**Hata alırsam:**
- `jq` çıktısında `Changes: []` ya da `null` → doğrulama kayıtları henüz üretilmemiştir. 15 sn bekleyip `describe-certificate` satırından itibaren tekrarlayın.
- Waiter zaman aşımına uğradı ya da durum `FAILED` → CAA kaydı `amazon.com`'a izin vermiyor olabilir (Adım 2). Sertifikayı silip (`aws acm delete-certificate --region us-east-1 --certificate-arn "$CERT_ARN"`) adımı tekrarlayın.
- Doğrulama CNAME'leri Teardown'da silinmek üzere `/tmp/newsradar-acm-validation.json`'da durur. Dosya kaybolursa `describe-certificate` ile yeniden üretilebilir.

---

## Adım 18 — CloudFront: Function, OAC ve dağıtım

**Ne yapıyoruz:** Bu adımda üç şey kuruluyor:
- `www → apex` yönlendiren bir CloudFront Function.
- Bucket'ı yalnızca CloudFront'un okuyabilmesini sağlayan bir OAC.
- Bunları birleştiren dağıtım.

Dağıtımın ayarları:
- Yalnızca HTTPS; HTTP istekleri HTTPS'e yönlenir.
- HTTP/2 ve HTTP/3 açık.
- SPA için 403/404 → `/index.html`.
- Cache: `index.html` için no-cache, hash'li asset'ler için 1 yıl.

**Komutlar:**

```bash
# 1) www → apex yönlendirmesi (deploy/aws/www-redirect.js; alan adı koda gömülü değil)
etag="$(aws cloudfront create-function --name "$CF_FUNCTION_NAME" \
  --function-config 'Comment=www to apex 301,Runtime=cloudfront-js-2.0' \
  --function-code fileb://deploy/aws/www-redirect.js --query ETag --output text)"
cat >/tmp/newsradar-cf-test.json <<EOF
{"version": "1.0", "context": {"eventType": "viewer-request"}, "viewer": {"ip": "192.0.2.10"},
 "request": {"method": "GET", "uri": "/test", "querystring": {"a": {"value": "1"}},
             "headers": {"host": {"value": "www.${DOMAIN}"}}, "cookies": {}}}
EOF
aws cloudfront test-function --name "$CF_FUNCTION_NAME" --if-match "$etag" --stage DEVELOPMENT \
  --event-object fileb:///tmp/newsradar-cf-test.json --query 'TestResult.FunctionOutput' --output text | jq -c '.response | {statusCode, location: .headers.location.value}'
aws cloudfront publish-function --name "$CF_FUNCTION_NAME" --if-match "$etag" --query 'FunctionSummary.Status' --output text
save CF_FUNCTION_ARN "$(aws cloudfront describe-function --name "$CF_FUNCTION_NAME" --stage LIVE \
  --query 'FunctionSummary.FunctionMetadata.FunctionARN' --output text)"

# 2) Origin Access Control
save OAC_ID "$(aws cloudfront create-origin-access-control --origin-access-control-config \
  "Name=${OAC_NAME},Description=newsradar frontend bucket,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
  --query OriginAccessControl.Id --output text)"

# 3) Dağıtım (deploy/aws/cloudfront-distribution.json)
save CF_CALLER_REF "newsradar-frontend-$(date +%s)"
render deploy/aws/cloudfront-distribution.json >/tmp/newsradar-cf-dist.json
read -r dist cfdomain < <(aws cloudfront create-distribution --distribution-config file:///tmp/newsradar-cf-dist.json \
  --query 'Distribution.[Id,DomainName]' --output text)
save DISTRIBUTION_ID "$dist"; save CF_DOMAIN "$cfdomain"
aws cloudfront tag-resource --resource "arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DISTRIBUTION_ID}" \
  --tags 'Items=[{Key=Project,Value=newsradar}]'

# 4) Bucket'ı yalnızca bu dağıtım okuyabilir
render deploy/iam/frontend-bucket-policy.json >/tmp/newsradar-frontend-policy.json
aws s3api put-bucket-policy --bucket "$FRONTEND_BUCKET" --policy file:///tmp/newsradar-frontend-policy.json
aws cloudfront wait distribution-deployed --id "$DISTRIBUTION_ID"                   # ~5-15 dk
```

Cache politikaları AWS-managed kimliklerle tanımlı:
- Varsayılan davranış `CachingOptimized` (`658327ea-…`). Origin'in `Cache-Control` başlığına uyar, bu yüzden asset'lere yüklemede 1 yıl, `index.html`'e `no-cache` verilir ([Adım 19](#adım-19--frontendi-derle-ve-yükle)).
- `/index.html` için ayrı bir davranış `CachingDisabled` (`4135ea2d-…`).
- Yanıtlara `SecurityHeadersPolicy` (`67f7725c-…`) eklenir: HSTS, nosniff, X-Frame-Options, Referrer-Policy.

**Doğrulama:**

```bash
aws cloudfront get-distribution --id "$DISTRIBUTION_ID" --query 'Distribution.[Status,DomainName,
  DistributionConfig.HttpVersion,DistributionConfig.DefaultCacheBehavior.ViewerProtocolPolicy,
  join(`,`,DistributionConfig.Aliases.Items)]' --output text
aws cloudfront list-cache-policies --type managed \
  --query "CachePolicyList.Items[?CachePolicy.Id=='658327ea-f89d-4fab-a63d-7e88639e58f6' || CachePolicy.Id=='4135ea2d-6df8-44a3-9df3-4b5a84be39ad'].CachePolicy.CachePolicyConfig.Name" --output text
```

Beklenen çıktı:
- `test-function`: `{"statusCode":301,"location":"https://newsradarapp.com/test?a=1"}`
- `publish-function`: `UNASSOCIATED` ya da `DEPLOYED`
- `Deployed	d….cloudfront.net	http2and3	redirect-to-https	newsradarapp.com,www.newsradarapp.com`
- `Managed-CachingOptimized	Managed-CachingDisabled`

**Hata alırsam:**
- `CNAMEAlreadyExists` → `newsradarapp.com` ya da `www` başka bir dağıtıma (başka bir hesapta olabilir) bağlı. O dağıtımdan alias'ı kaldırın, sonra 3. bloğu tekrarlayın.
- `InvalidViewerCertificate` → sertifika henüz `ISSUED` değil ya da us-east-1'de değil (Adım 17).
- `InvalidIfMatchVersion` → `etag` eskimiştir: `etag="$(aws cloudfront describe-function --name "$CF_FUNCTION_NAME" --query ETag --output text)"`.
- `FunctionAlreadyExists` / `OriginAccessControlAlreadyExists` → var olanın kimliğini alın:
  - `aws cloudfront list-origin-access-controls --query "OriginAccessControlList.Items[?Name=='${OAC_NAME}'].Id" --output text`
  - Function için `describe-function`.

---

## Adım 19 — Frontend'i derle ve yükle

**Ne yapıyoruz:** Frontend'i API adresiyle derleyip S3'e doğru `Cache-Control` başlıklarıyla yüklüyoruz:
- hash'li asset'ler 1 yıl, değişmez
- diğer statik dosyalar 1 saat
- `index.html` no-cache

**Komutlar:**

```bash
(cd frontend && npm ci && VITE_API_URL="https://api.${DOMAIN}" npm run build)
# Önce asset'ler (yeni index.html'in istediği dosyalar hazır olsun). Eski asset'ler bilerek SİLİNMEZ:
# önbellekte eski index.html'i olan kullanıcılar onları hâlâ isteyebilir.
aws s3 sync frontend/dist/assets "s3://${FRONTEND_BUCKET}/assets" --cache-control "public, max-age=31536000, immutable"
aws s3 sync frontend/dist "s3://${FRONTEND_BUCKET}" --exclude "assets/*" --exclude "index.html" \
  --cache-control "public, max-age=3600" --delete
aws s3 cp frontend/dist/index.html "s3://${FRONTEND_BUCKET}/index.html" \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/index.html" "/" \
  --query 'Invalidation.Status' --output text
```

**Doğrulama** (DNS henüz değişmedi; CloudFront'un kendi alan adıyla):

```bash
curl -sI "https://${CF_DOMAIN}/" | grep -iE '^(HTTP|cache-control|strict-transport)'
asset="$(cd frontend/dist && ls assets/*.js | head -1)"
curl -sI "https://${CF_DOMAIN}/${asset}" | grep -iE '^(HTTP|cache-control)'
curl -s -o /dev/null -w 'SPA derin bağlantı: %{http_code}\n' "https://${CF_DOMAIN}/olmayan/yol"
curl -s -o /dev/null -w 'S3 doğrudan: %{http_code}\n' "https://${FRONTEND_BUCKET}.s3.${REGION}.amazonaws.com/index.html"
curl -s -o /dev/null -w 'HTTP: %{http_code} → %{redirect_url}\n' "http://${CF_DOMAIN}/"
grep -o "https://api\.${DOMAIN}" frontend/dist/assets/*.js | head -1
```

Beklenen çıktı:
- `HTTP/2 200`, `cache-control: no-cache` ve `strict-transport-security: …`
- `HTTP/2 200` ve `cache-control: public, max-age=31536000, immutable`
- `SPA derin bağlantı: 200`
- `S3 doğrudan: 403`. Bucket herkese kapalı.
- `HTTP: 301 → https://d….cloudfront.net/`
- Build'e gömülü API adresi.

**Hata alırsam:**
- Her istek 403 dönüyorsa bucket policy'deki `DISTRIBUTION_ID` yanlıştır ya da policy uygulanmamıştır: `aws s3api get-bucket-policy --bucket "$FRONTEND_BUCKET"`.
- 403 yalnızca bazı yollarda çıkıyorsa dosya yoktur; bu durumda 200 + index.html dönmesi doğru davranış.
- Eski içerik geliyorsa invalidation'ın tamamlanmasını bekleyin: `aws cloudfront list-invalidations --distribution-id "$DISTRIBUTION_ID"`.
- `npm ci` hatası → Node 20+ gerekir (`node --version`).

---

## Adım 20 — DNS: apex + www → CloudFront (geçiş)

**Ne yapıyoruz:** `newsradarapp.com` ve `www.newsradarapp.com` için ALIAS (A + AAAA) kayıtlarını CloudFront'a yönlendiriyoruz; site bu anda yeni altyapıya geçer.

**Komutlar:**

```bash
# www'de mevcut bir CNAME varsa (ör. Render) aynı adda ALIAS yazılamaz → aynı değişiklikte silinir.
jq --arg d "$DOMAIN." '[.ResourceRecordSets[] | select(.Name=="www."+$d and .Type=="CNAME") | {Action:"DELETE", ResourceRecordSet:.}]' \
  "$DNS_BACKUP" >/tmp/newsradar-dns-delete.json
jq -n --arg d "$DOMAIN" --arg cf "$CF_DOMAIN" --slurpfile del /tmp/newsradar-dns-delete.json '
  {Comment: "apex + www -> CloudFront",
   Changes: ($del[0] + [ ($d, "www." + $d) as $n | ("A", "AAAA") as $t
     | {Action: "UPSERT", ResourceRecordSet: {Name: $n, Type: $t,
        AliasTarget: {HostedZoneId: "Z2FDTNDATAQYW2", DNSName: $cf, EvaluateTargetHealth: false}}} ])}' \
  >/tmp/newsradar-dns-frontend.json
jq -c '.Changes[] | [.Action, .ResourceRecordSet.Name, .ResourceRecordSet.Type]' /tmp/newsradar-dns-frontend.json
change="$(aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/newsradar-dns-frontend.json --query ChangeInfo.Id --output text)"
aws route53 wait resource-record-sets-changed --id "$change"
```

`Z2FDTNDATAQYW2` bir hesap kimliği değildir: CloudFront alias hedeflerinin, AWS'nin tüm hesaplar için kullandığı sabit hosted zone kimliğidir.

**Doğrulama:**

```bash
dig +short "$DOMAIN" A @1.1.1.1 | head -2
curl -sI "https://${DOMAIN}/" | grep -iE '^(HTTP|cache-control)'
curl -s -o /dev/null -w 'www: %{http_code} → %{redirect_url}\n' "https://www.${DOMAIN}/abc?x=1"
curl -s -o /dev/null -w 'http: %{http_code} → %{redirect_url}\n' "http://${DOMAIN}/"
curl -sI -X OPTIONS -H "Origin: https://${DOMAIN}" -H "Access-Control-Request-Method: POST" \
  "https://api.${DOMAIN}/session/bootstrap" | grep -i '^access-control-allow-'
```

Beklenen çıktı:
- CloudFront IP'leri
- `HTTP/2 200` ve `cache-control: no-cache`
- `www: 301 → https://newsradarapp.com/abc?x=1`
- `http: 301 → https://newsradarapp.com/`
- `access-control-allow-origin: https://newsradarapp.com` ve `access-control-allow-credentials: true`

Son olarak tarayıcıda siteyi açın ve bir şirket ekleyip yenileyin. DevTools → Application → Cookies'te `nr_device` çerezi `Domain=.newsradarapp.com`, `Secure`, `SameSite=Lax` görünmeli.

**Hata alırsam:**
- `InvalidChangeBatch … conflicting RRSet` → apex ya da www'de başka türde bir kayıt var. `jq` çıktısına bakın ve o kaydı `DELETE` olarak ekleyin.
- **Geri dönüş (site çalışmıyorsa):** CloudFront ALIAS'larını silip yedekteki eski apex/www kayıtlarını aynı değişiklikte geri yazın:

```bash
aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --output json >/tmp/newsradar-dns-now.json
jq -n --arg d "$DOMAIN." --arg cf "$CF_DOMAIN." --slurpfile now /tmp/newsradar-dns-now.json --slurpfile old "$DNS_BACKUP" '
  def site: select((.Name==$d or .Name=="www."+$d) and (.Type=="A" or .Type=="AAAA" or .Type=="CNAME"));
  {Comment: "rollback apex/www",
   Changes: ([$now[0].ResourceRecordSets[] | site | select(.AliasTarget.DNSName==$cf) | {Action: "DELETE", ResourceRecordSet: .}]
           + [$old[0].ResourceRecordSets[] | site | {Action: "CREATE", ResourceRecordSet: .}])}' >/tmp/newsradar-dns-rollback.json
jq -c '.Changes[] | [.Action, .ResourceRecordSet.Name, .ResourceRecordSet.Type]' /tmp/newsradar-dns-rollback.json
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --change-batch file:///tmp/newsradar-dns-rollback.json
```

---

## Adım 21 — Health izleme ve e-posta uyarısı

**Ne yapıyoruz:** `https://api.newsradarapp.com/health`'i dışarıdan kontrol eden bir Route 53 health check ve düşünce e-posta gönderen bir CloudWatch alarmı kuruyoruz. Log'ların CloudWatch'a geldiğini de doğruluyoruz.

**Maliyet uyarısı:** HTTPS health check **ücretsiz katmanda değildir**. Ayda yaklaşık 1,50–2,75 USD tutar ([Adım 24](#adım-24--aylık-maliyet-tahmini)). Alarm (ilk 10 alarm ücretsiz) ve e-posta bildirimi (ayda ilk 1000 ücretsiz) ek ücret getirmez.

**Komutlar:**

```bash
read -rp "Uyarı e-posta adresi: " ALERT_EMAIL         # komut satırına/geçmişe yazılmaz
cat >/tmp/newsradar-hc.json <<EOF
{"Type": "HTTPS", "FullyQualifiedDomainName": "api.${DOMAIN}", "Port": 443, "ResourcePath": "/health",
 "RequestInterval": 30, "FailureThreshold": 3, "EnableSNI": true,
 "Regions": ["eu-west-1", "us-east-1", "ap-southeast-1"]}
EOF
save HEALTH_CHECK_ID "$(aws route53 create-health-check --caller-reference "newsradar-api-$(date +%s)" \
  --health-check-config file:///tmp/newsradar-hc.json --query HealthCheck.Id --output text)"
aws route53 change-tags-for-resource --resource-type healthcheck --resource-id "$HEALTH_CHECK_ID" \
  --add-tags Key=Name,Value=newsradar-api-health Key=Project,Value=newsradar

# Route 53 health check metrikleri yalnızca us-east-1'de → konu ve alarm da orada.
save TOPIC_ARN "$(aws sns create-topic --region us-east-1 --name "$SNS_TOPIC_NAME" --query TopicArn --output text)"
aws sns subscribe --region us-east-1 --topic-arn "$TOPIC_ARN" --protocol email \
  --notification-endpoint "$ALERT_EMAIL" --query SubscriptionArn --output text
unset ALERT_EMAIL
aws cloudwatch put-metric-alarm --region us-east-1 --alarm-name "$ALARM_NAME" \
  --alarm-description "api /health 3 dakika boyunca basarisiz" \
  --namespace AWS/Route53 --metric-name HealthCheckStatus --dimensions Name=HealthCheckId,Value="$HEALTH_CHECK_ID" \
  --statistic Minimum --period 60 --evaluation-periods 3 --threshold 1 --comparison-operator LessThanThreshold \
  --treat-missing-data breaching --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"
```

Gelen kutunuzdaki **"AWS Notification - Subscription Confirmation"** e-postasındaki bağlantıya tıklayın.

**Doğrulama:**

```bash
aws route53 get-health-check-status --health-check-id "$HEALTH_CHECK_ID" \
  --query 'HealthCheckObservations[].StatusReport.Status' --output text | tr '\t' '\n' | sort | uniq -c
aws sns list-subscriptions-by-topic --region us-east-1 --topic-arn "$TOPIC_ARN" --query 'Subscriptions[0].SubscriptionArn' --output text | cut -c1-24
aws cloudwatch describe-alarms --region us-east-1 --alarm-names "$ALARM_NAME" --query 'MetricAlarms[0].StateValue' --output text
# Uyarı zinciri testi (e-posta gelmeli; bir sonraki ölçümde alarm kendiliğinden OK'a döner):
aws cloudwatch set-alarm-state --region us-east-1 --alarm-name "$ALARM_NAME" --state-value ALARM --state-reason "runbook testi"
# Log'lar:
aws logs tail "$LOG_GROUP" --region "$REGION" --since 10m | tail -5
```

Beklenen çıktı:
- Birkaç dakika içinde tüm gözlemciler `Success: HTTP Status Code 200, OK`.
- Abonelik onaylandıysa `arn:aws:sns:us-east-1:` ile başlayan bir değer. `PendingConfirmation` görünüyorsa e-postayı onaylamamışsınız demektir.
- Alarm durumu ilk dakikalarda `INSUFFICIENT_DATA`, sonra `OK`.
- Test komutundan sonra bir ALARM e-postası, ardından OK e-postası.
- `newsradar-backend-1` / `newsradar-caddy-1` kaynaklı log satırları.

**Hata alırsam:**
- Health check `Failure: … SSL` → `EnableSNI` açık olmalı; sertifikanın Let's Encrypt'ten alındığını Adım 14'te doğrulayın.
- Health check `Failure: … timed out` → Route 53 denetleyicileri 443'e ulaşamıyor. SG'de `0.0.0.0/0` 443 kuralı olmalı (Adım 10).
- `aws logs tail` boş dönüyorsa:
  - **[instance]** `cat /etc/docker/daemon.json` → `awslogs` görünmeli.
  - Container'lar daemon.json'dan **önce** oluşturulduysa log'lar CloudWatch'a gitmez. `docker compose up -d --force-recreate` ile yeniden yaratın.

Not: Route 53 denetleyicileri 3 bölgeden yaklaşık her 30 saniyede bir istek atar. Bu istekler Caddy ve uvicorn'un erişim log'larına girer; ayda yüzlerce MB eder, CloudWatch'ın 5 GB'lık ücretsiz kotasının içinde kalır.

---

## Adım 22 — Rutin: yeni sürüm yayınlama

**Ne yapıyoruz:** Kuruluma dokunmadan backend'in ya da frontend'in yeni sürümünü yayınlıyor, gerekirse önceki image'a dönüyoruz.

**Komutlar:**

```bash
# Backend — Mac:
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR_URI%%/*}"
save IMAGE_TAG "$(git rev-parse --short HEAD)"
docker buildx build --platform linux/arm64 -t "$ECR_URI:$IMAGE_TAG" -t "$ECR_URI:prod" --push backend
```

**[instance]** (`sudo -i; export AWS_REGION=eu-central-1; cd /opt/newsradar/deploy`):

```bash
git -C /opt/newsradar pull --ff-only                 # deploy/ dosyaları değiştiyse
./load-secrets.sh                                    # SSM'de değer değiştiyse
set -a; . <(grep -E '^(DOMAIN|BACKEND_IMAGE)=' .env); set +a
aws ecr get-login-password | docker login --username AWS --password-stdin "${BACKEND_IMAGE%%/*}"
docker compose pull backend && docker compose up -d --no-build
./smoke-test.sh "api.${DOMAIN}"
```

Frontend için [Adım 19](#adım-19--frontendi-derle-ve-yükle)'daki komutları tekrarlayın.

**Önceki image'a dönüş:** ECR son 10 image'ı tutar.
- Mac'te `aws ecr describe-images --region "$REGION" --repository-name "$ECR_REPO" --query 'sort_by(imageDetails,&imagePushedAt)[].imageTags' --output text` ile etiketleri listeleyin.
- `put_param BACKEND_IMAGE String "$ECR_URI:<eski-etiket>"` (`put_param` [Adım 1](#adım-1--değişkenler-ve-durum-dosyası)'deki blokta tanımlı).
- Instance'ta yukarıdaki bloğu çalıştırın.

**Doğrulama:** `smoke-test.sh` → `== TAMAM`. Mac'te `curl -sS "https://api.${DOMAIN}/health"` → `{"status":"ok"}`.

**Hata alırsam:**
- `smoke-test` başarısızsa önceki image'a dönün (yukarıda).
- Veri bozulduysa **[instance]** `./restore.sh` en son gece yedeğini geri yükler. Onay sorar; işlemden önce mevcut DB'nin kopyasını alır.

---

## Adım 23 — Geri alma ve temizlik (teardown)

**Ne yapıyoruz:** Kurulumu ters sırayla siliyoruz. Kısmi bir arızada neyin bırakılıp neyin silineceği aşağıdaki tabloda.

| Kaynak | Bir şey ters giderse | Tamamen vazgeçersem |
|---|---|---|
| Route 53 hosted zone | **Asla silinmez.** Kurulumdan önce vardı. | Bırakılır, yalnızca kayıtlar geri alınır (T2, T8). |
| `$DNS_BACKUP` dosyası (Mac) | Saklayın; geri dönüşün kaynağı bu. | Saklayın. |
| Yedek bucket'ı | **Bırakın:** tek veri kopyası burada. | **En son** silinir, ancak yerel bir kopya indirildikten sonra (T6, T15). |
| SSM parametreleri | Bırakın: ücretsizdir, tekrar denemede kullanılır. | Silinir (T13). |
| ECR image'ları | Bırakın: kuruşlar tutar. | Silinir (T16). |
| EC2 | Arızalıysa kapatıp Adım 13'ü tekrarlayın; veri S3'te. | Silinir (T7). Durdurulmuş instance da disk ve IP ücreti öder. |
| Elastic IP | Instance yoksa **hemen bırakın**: bağlı değilken de ücretlidir. | Silinir (T9). |
| CloudFront, ACM, OAC, Function | Devre dışı dağıtım ücretsizdir; acele etmeyin. | Silinir (T3, T4). |
| Health check | Ücretlidir; uzun süre arızalıysa silin. | Silinir (T1). |
| IAM rol/profil, SG, log grubu | Ücretsiz (log saklama ihmal edilebilir). | Silinir (T10, T11, T14). |

Komutlar `NotFound` hatası verirse kaynak zaten silinmiştir; sonraki adıma geçin. Önce Adım 1'deki bloğu çalıştırın: kimlikler `$STATE_FILE`'dan gelir.

### T1 — Health izleme (Adım 21)

```bash
aws cloudwatch delete-alarms --region us-east-1 --alarm-names "$ALARM_NAME"
aws sns delete-topic --region us-east-1 --topic-arn "$TOPIC_ARN"
aws route53 delete-health-check --health-check-id "$HEALTH_CHECK_ID"
```

Doğrulama: `aws route53 list-health-checks --query "HealthChecks[?Id=='$HEALTH_CHECK_ID']" --output text` → boş.

### T2 — DNS: apex + www (Adım 20)

Kurulumdan önceki kayıtlara (ör. Render) dönmek için [Adım 20](#adım-20--dns-apex--www--cloudfront-geçiş)'deki **geri dönüş** bloğunu çalıştırın. Önceden apex/www kaydı yoksa yalnızca CloudFront ALIAS'larını silin:

```bash
aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --output json \
| jq --arg d "$DOMAIN." --arg cf "$CF_DOMAIN." '{Changes: [.ResourceRecordSets[]
    | select((.Name==$d or .Name=="www."+$d) and .AliasTarget.DNSName==$cf) | {Action: "DELETE", ResourceRecordSet: .}]}' \
  >/tmp/newsradar-dns-del-frontend.json
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --change-batch file:///tmp/newsradar-dns-del-frontend.json
```

Doğrulama: `dig +short "$DOMAIN" @1.1.1.1` → eski değer ya da boş.

### T3 — CloudFront (Adım 18)

```bash
aws cloudfront get-distribution-config --id "$DISTRIBUTION_ID" >/tmp/newsradar-cf-current.json
jq '.DistributionConfig | .Enabled = false' /tmp/newsradar-cf-current.json >/tmp/newsradar-cf-disabled.json
aws cloudfront update-distribution --id "$DISTRIBUTION_ID" --if-match "$(jq -r .ETag /tmp/newsradar-cf-current.json)" \
  --distribution-config file:///tmp/newsradar-cf-disabled.json --query Distribution.Status --output text
aws cloudfront wait distribution-deployed --id "$DISTRIBUTION_ID"                    # ~5-15 dk
aws cloudfront delete-distribution --id "$DISTRIBUTION_ID" \
  --if-match "$(aws cloudfront get-distribution --id "$DISTRIBUTION_ID" --query ETag --output text)"
aws cloudfront delete-function --name "$CF_FUNCTION_NAME" \
  --if-match "$(aws cloudfront describe-function --name "$CF_FUNCTION_NAME" --query ETag --output text)"
aws cloudfront delete-origin-access-control --id "$OAC_ID" \
  --if-match "$(aws cloudfront get-origin-access-control --id "$OAC_ID" --query ETag --output text)"
```

Doğrulama: `aws cloudfront list-distributions --query "DistributionList.Items[?Id=='$DISTRIBUTION_ID']" --output text` → boş.

Hata: `DistributionNotDisabled` → `wait` tamamlanmamıştır; birkaç dakika sonra silme satırını tekrarlayın.

### T4 — ACM (Adım 17)

```bash
aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord' --output json \
| jq '{Changes: (unique_by(.Name) | map({Action: "DELETE", ResourceRecordSet: {Name: .Name, Type: .Type, TTL: 300,
      ResourceRecords: [{Value: .Value}]}}))}' >/tmp/newsradar-acm-del.json
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --change-batch file:///tmp/newsradar-acm-del.json
aws acm delete-certificate --region us-east-1 --certificate-arn "$CERT_ARN"
```

Hata: `ResourceInUseException` → dağıtım henüz tamamen silinmemiştir (T3).

### T5 — Frontend bucket'ı (Adım 16, 19)

```bash
aws s3 rm "s3://${FRONTEND_BUCKET}" --recursive --quiet
aws s3api delete-bucket --bucket "$FRONTEND_BUCKET"
```

### T6 — Son yedeği yerel olarak al (Adım 15)

Önce **[instance]** üzerinde taze bir yedek alın (`aws ssm start-session --region "$REGION" --target "$INSTANCE_ID"`):

```bash
sudo systemctl start newsradar-backup.service && sudo journalctl -u newsradar-backup.service -n 1 --no-pager
exit
```

Sonra Mac'te indirin:

```bash
last="$(aws s3 ls "s3://${BACKUP_BUCKET}/backups/" | awk '{print $4}' | sort | tail -1)"
aws s3 cp "s3://${BACKUP_BUCKET}/backups/${last}" "$HOME/${last}" && gzip -t "$HOME/${last}" && echo "yerel kopya: $HOME/${last}"
```

### T7 — EC2 instance'ı (Adım 13)

```bash
aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID" --query 'TerminatingInstances[0].CurrentState.Name' --output text
aws ec2 wait instance-terminated --region "$REGION" --instance-ids "$INSTANCE_ID"
```

Disk `DeleteOnTermination=true` olduğu için instance'la birlikte silinir. Veri T6'daki yedekte durur.

### T8 — DNS: api (Adım 12)

```bash
printf '{"Changes":[{"Action":"DELETE","ResourceRecordSet":{"Name":"api.%s","Type":"A","TTL":300,"ResourceRecords":[{"Value":"%s"}]}}]}' \
  "$DOMAIN" "$EIP_IP" >/tmp/newsradar-dns-api-del.json
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --change-batch file:///tmp/newsradar-dns-api-del.json
```

Hata: `InvalidChangeBatch … not found` → kayıt zaten yok ya da TTL ve değer farklı. Güncel halini `aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" --query "ResourceRecordSets[?Name=='api.${DOMAIN}.']"` ile görün.

### T9 — Elastic IP (Adım 11)

```bash
aws ec2 release-address --region "$REGION" --allocation-id "$EIP_ALLOC"
```

Hata: `InvalidIPAddress.InUse` → instance henüz kapanmamıştır (T7).

### T10 — Security group (Adım 10)

```bash
aws ec2 delete-security-group --region "$REGION" --group-id "$SG_ID"
```

Hata: `DependencyViolation` → instance'ın ağ arayüzü hâlâ siliniyordur; 1 dakika sonra tekrarlayın.

### T11 — IAM (Adım 9)

```bash
aws iam remove-role-from-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
aws iam delete-instance-profile --instance-profile-name "$PROFILE_NAME"
aws iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name newsradar-ec2-inline
aws iam delete-role --role-name "$ROLE_NAME"
```

### T12 — KMS (Adım 8)

Yapılacak bir şey yok: `aws/ssm` AWS-managed bir anahtar ve ücretsiz.

### T13 — SSM parametreleri (Adım 7)

```bash
aws ssm get-parameters-by-path --region "$REGION" --path "$SSM_PREFIX/" --query 'Parameters[].Name' --output text \
  | tr '\t' '\n' | xargs -n 10 aws ssm delete-parameters --region "$REGION" --query 'DeletedParameters' --output text --names
```

### T14 — Log grubu (Adım 6)

```bash
aws logs delete-log-group --region "$REGION" --log-group-name "$LOG_GROUP"
```

### T15 — Yedek bucket'ı (Adım 5) — yalnızca T6'daki yerel kopya doğrulandıysa

```bash
while :; do
  aws s3api list-object-versions --bucket "$BACKUP_BUCKET" --max-items 1000 --output json \
    --query '{Objects: [Versions, DeleteMarkers][][].{Key: Key, VersionId: VersionId}}' >/tmp/newsradar-versions.json
  [ "$(jq '.Objects | length' /tmp/newsradar-versions.json)" -gt 0 ] || break
  aws s3api delete-objects --bucket "$BACKUP_BUCKET" --delete file:///tmp/newsradar-versions.json --query 'length(Deleted)'
done
aws s3api delete-bucket --bucket "$BACKUP_BUCKET"
```

### T16 — ECR (Adım 3, 4)

```bash
aws ecr delete-repository --region "$REGION" --repository-name "$ECR_REPO" --force --query 'repository.repositoryName' --output text
```

### Son kontrol

```bash
aws resourcegroupstaggingapi get-resources --region "$REGION" --tag-filters Key=Project,Values=newsradar --query 'ResourceTagMappingList[].ResourceARN'
aws resourcegroupstaggingapi get-resources --region us-east-1 --tag-filters Key=Project,Values=newsradar --query 'ResourceTagMappingList[].ResourceARN'
mv "$STATE_FILE" "$STATE_FILE.removed-$(date +%Y%m%d)"
```

Beklenen çıktı: `[]` ve `[]`. Etiket indeksi birkaç dakika gecikebilir. IAM kaynakları bu sorguda görünmez; T11'de silindiler.

---

## Adım 24 — Aylık maliyet tahmini

eu-central-1, ayda yaklaşık 730 saat, bu uygulamanın ölçeği (günde birkaç yüz ziyaret). Fiyatlar bu yazımdaki liste fiyatlarına dayanan **tahminlerdir**. Kurulumdan önce ve sonra **[AWS Pricing Calculator](https://calculator.aws/) ile doğrulayın**. Gerçekleşen tutarı Billing → Cost Explorer'da `Project=newsradar` etiketiyle izleyin.

| Kalem | Varsayım | Aylık (USD) |
|---|---|---|
| EC2 t4g.small | ~0,0192 $/saat, On-Demand, `CpuCredits=standard` | ~14,00 |
| EBS gp3 20 GB | ~0,0952 $/GB-ay; 3000 IOPS/125 MB/s temel dahil | ~1,90 |
| Elastic IP (genel IPv4) | 0,005 $/saat; bağlı olsun olmasın ücretli | ~3,65 |
| S3 | yedekler <100 MB, frontend birkaç MB, az istek | <0,10 |
| CloudFront | Her zaman ücretsiz katman: 1 TB çıkış ve 10 M istek/ay; Function'lar 2 M/ay ücretsiz | 0,00 |
| Route 53 | hosted zone 0,50 (zaten ödüyorsunuz); CloudFront ALIAS sorguları ücretsiz | 0,50 (mevcut) |
| Route 53 health check | HTTPS (temel + HTTPS seçeneği); AWS dışı uç sayılırsa üst sınır | ~1,50–2,75 |
| ECR | ~0,10 $/GB-ay; 10 image, ortak katmanlar → <1 GB; aynı bölgede çekme ücretsiz | ~0,05–0,10 |
| CloudWatch | Logs: ~0,5–1 GB/ay alım, 5 GB ücretsiz kotada; 7 gün saklama; 1 alarm (10 ücretsiz) | ~0,00 |
| Diğer | ACM, SSM Parameter Store (standart), Session Manager, `aws/ssm` KMS: ücretsiz; 100 GB'a kadar internet çıkışı ücretsiz | 0,00 |
| **Toplam** | | **~21–23 / ay** (mevcut hosted zone hariç ~20,5–22,5) |

Notlar:
- **Ücretsiz katmana güvenmeyin.** EC2, EBS, genel IPv4 ve health check bu kurulumda ücretli kabul edildi. Hesabınız yeni ve kredili "Free plan"daysa bu tutar kredilerden düşer. Kredi bitince fatura başlar.
- Tasarruf seçenekleri:
  - 1 yıllık Compute Savings Plan EC2 kalemini ~%30–35 düşürür.
  - Health check yerine yalnızca ücretsiz EC2 `StatusCheckFailed` alarmı kullanılabilir. Bu alarm instance'ın düştüğünü yakalar ama uygulamanın düştüğünü yakalamaz.
  - UDP 443'ü (HTTP/3) kapatmanın maliyete etkisi yoktur.
- Beklenmedik maliyet riski: t4g'nin "unlimited" CPU kredisi (bu kurulumda kapalı), bağlı olmayan EIP'ler, silinmeyen health check, ve CloudWatch Logs'ta beklenmedik log hacmi (ör. bir hata döngüsü). Billing → **Budgets**'ta aylık 30 USD'lik bir bütçe uyarısı önerilir (ilk 2 bütçe ücretsiz).

---

## Ek A — Kaynak adları

| Kaynak | Ad / kimlik | Tanım | Kullanıldığı adımlar |
|---|---|---|---|
| SSO profili | `newsradar` | Adım 0 | hepsi |
| Durum dosyası | `~/.newsradar-aws-state.env` | Adım 1 | hepsi |
| DNS yedeği | `~/newsradar-dns-backup-*.json` (`$DNS_BACKUP`) | Adım 2 | 20, 23 |
| ECR deposu | `newsradar-api` (`$ECR_REPO`) | Adım 3 | 4, 7, 9, 22, T16 |
| Image | `$ECR_URI:prod` + `$ECR_URI:<commit>` (`$BACKEND_IMAGE`) | Adım 4 | 7, 14, 22 |
| Yedek bucket'ı | `newsradar-backups-<hesap>` (`$BACKUP_BUCKET`) | Adım 5 | 7, 9, 15, T6, T15 |
| Log grubu | `/newsradar/prod` (`$LOG_GROUP`) | Adım 6 | 9, 13, 21, T14 |
| SSM yolu | `/newsradar/prod/*` (`$SSM_PREFIX`) | Adım 7 | 9, 14, 22, T13 |
| KMS anahtarı | `alias/aws/ssm` (`$SSM_KMS_KEY_ARN`) | Adım 8 | 9 |
| IAM rolü | `newsradar-ec2-role` (`$ROLE_NAME`), inline policy `newsradar-ec2-inline` | Adım 9 | 13, T11 |
| Instance profile | `newsradar-ec2-profile` (`$PROFILE_NAME`) | Adım 9 | 13, T11 |
| Security group | `newsradar-api-sg` (`$SG_NAME`, `$SG_ID`) | Adım 10 | 13, T10 |
| Elastic IP | etiket `newsradar-api-eip` (`$EIP_ALLOC`, `$EIP_IP`) | Adım 11 | 12, 13, T8, T9 |
| DNS api | `api.newsradarapp.com A → $EIP_IP` | Adım 12 | 14, 21, T8 |
| EC2 | etiket `newsradar-api` (`$INSTANCE_ID`), disk `newsradar-api-root` | Adım 13 | 14, 15, T6, T7 |
| Frontend bucket'ı | `newsradar-frontend-<hesap>` (`$FRONTEND_BUCKET`) | Adım 16 | 18, 19, T5 |
| ACM sertifikası | us-east-1, `$CERT_ARN` | Adım 17 | 18, T4 |
| CloudFront Function | `newsradar-www-redirect` (`$CF_FUNCTION_NAME`, `$CF_FUNCTION_ARN`) | Adım 18 | T3 |
| OAC | `newsradar-frontend-oac` (`$OAC_NAME`, `$OAC_ID`) | Adım 18 | T3 |
| CloudFront dağıtımı | `$DISTRIBUTION_ID`, `$CF_DOMAIN` | Adım 18 | 19, 20, T2, T3 |
| Health check | etiket `newsradar-api-health` (`$HEALTH_CHECK_ID`) | Adım 21 | T1 |
| SNS konusu | `newsradar-alerts` (us-east-1, `$TOPIC_ARN`) | Adım 21 | T1 |
| Alarm | `newsradar-api-health` (us-east-1, `$ALARM_NAME`) | Adım 21 | T1 |

Repo dosyaları:
- [deploy/iam/](../deploy/iam/): trust policy, instance policy, frontend bucket policy
- [deploy/aws/](../deploy/aws/): user-data, CloudFront dağıtımı ve Function'ı, S3 ve ECR lifecycle kuralları, `render.py`
- [deploy/tests/test-aws-templates.sh](../deploy/tests/test-aws-templates.sh): şablonların yerel testi

## Ek B — Gereksinimden bilinçli sapmalar

| Konu | İstenen | Yapılan ve neden |
|---|---|---|
| `ecr:GetAuthorizationToken` | IAM'de `*` olmasın | Bu eylem kaynak bazlı kısıtlamayı **desteklemiyor**; AWS yalnızca `"Resource": "*"` kabul ediyor. Token tek başına bir image'a erişim vermez; çekme izinleri yalnızca `newsradar-api` reposuyla sınırlı. Politikadaki tek `*` bu. |
| `AmazonSSMManagedInstanceCore` | İstendi | AWS-managed bir policy ve içinde `*` kaynaklar var (Session Manager'ın çalışma biçimi). Değiştirilemez; istendiği gibi eklendi. |
| CloudWatch Logs izinleri | İzin listesinde yoktu | Gözlem gereksinimi (container log'ları CloudWatch'a) bunu zorunlu kılıyor. Yalnızca `logs:CreateLogStream` ve `logs:PutLogEvents`, yalnızca `/newsradar/prod` grubuna. |
| Port 443 | "Yalnızca 80 ve 443" | 443 TCP'nin yanında 443 **UDP** de açık (HTTP/3). Kapatılabilir ([Adım 10](#adım-10--security-group)). |
| "Yalnızca HTTPS" (CloudFront) | | `redirect-to-https`: HTTP üzerinden hiçbir içerik sunulmaz, yalnızca HTTPS'e 301 döner. `https-only` seçilirse `http://newsradarapp.com` yazan kullanıcı 403 alır. |
| Yedek saklama | 30 gün, eski sürümler dahil | Güncel sürüm 30 gün, eski sürüm güncel olmaktan çıktıktan sonra 30 gün → en fazla 60 gün. Kesin 30 gün için `NoncurrentDays: 1` ([Adım 5](#adım-5--yedek-bucketı)). |
| ACM | | Yalnızca CloudFront için (us-east-1). API sertifikasını Caddy alıyor. |
