"""Şablondaki __AD__ yer tutucularını ortam değişkenleriyle doldurur (stdout'a yazar).

Kullanım: python3 deploy/aws/render.py deploy/iam/ec2-instance-policy.json > /tmp/policy.json
Eksik ya da boş değişken varsa hiçbir şey yazmadan hata verir; .json şablonlarının çıktısı
ayrıca JSON olarak doğrulanır. Biçimi bilinen değişkenler (FORMATS) şablonda geçiyorsa
doğrulanır: ör. GitHub OIDC sub'ı `repo:<sahip>@<sahip-id>/<repo>@<repo-id>:ref:…` olduğundan
yanlış bir ID sessizce bozuk bir trust policy üretmez, render burada durur.
"""
import json
import os
import re
import sys

TOKEN = re.compile(r"__([A-Z][A-Z0-9_]*)__")
FORMATS = {
    "ACCOUNT_ID": (r"[0-9]{12}", "12 haneli AWS hesap ID'si"),
    "GITHUB_OWNER": (r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", "GitHub kullanıcı/kuruluş adı"),
    "GITHUB_OWNER_ID": (r"[1-9][0-9]*", "GitHub sahip ID'si (yalnızca rakam)"),
    "GITHUB_REPO_NAME": (r"[A-Za-z0-9._-]{1,100}", "GitHub repo adı"),
    "GITHUB_REPO_ID": (r"[1-9][0-9]*", "GitHub repo ID'si (yalnızca rakam)"),
}

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
missing = sorted({n for n in TOKEN.findall(text) if not os.environ.get(n)})
if missing:
    sys.exit(f"render.py: {path} için eksik/boş değişken: {', '.join(missing)}")
bad = [f"{n}={os.environ[n]!r} ({FORMATS[n][1]} bekleniyor)" for n in sorted(set(TOKEN.findall(text)))
       if n in FORMATS and not re.fullmatch(FORMATS[n][0], os.environ[n])]
if bad:
    sys.exit(f"render.py: {path} için geçersiz değer: {'; '.join(bad)}")
out = TOKEN.sub(lambda m: os.environ[m.group(1)], text)
if path.endswith(".json"):
    json.loads(out)
sys.stdout.write(out)
