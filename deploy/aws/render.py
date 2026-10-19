"""Şablondaki __AD__ yer tutucularını ortam değişkenleriyle doldurur (stdout'a yazar).

Kullanım: python3 deploy/aws/render.py deploy/iam/ec2-instance-policy.json > /tmp/policy.json
Eksik ya da boş değişken varsa hiçbir şey yazmadan hata verir; .json şablonlarının çıktısı
ayrıca JSON olarak doğrulanır.
"""
import json
import os
import re
import sys

TOKEN = re.compile(r"__([A-Z][A-Z0-9_]*)__")

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
missing = sorted({n for n in TOKEN.findall(text) if not os.environ.get(n)})
if missing:
    sys.exit(f"render.py: {path} için eksik/boş değişken: {', '.join(missing)}")
out = TOKEN.sub(lambda m: os.environ[m.group(1)], text)
if path.endswith(".json"):
    json.loads(out)
sys.stdout.write(out)
