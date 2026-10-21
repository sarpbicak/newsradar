"""deploy/PARAMETERS.md ↔ kod: okunan her ortam değişkeni dokümanda var mı, dokümanda
kodda olmayan ad kaldı mı?

Taranır: backend/app (os.getenv / _env / os.environ), backend/Dockerfile (ENV),
deploy/docker-compose.yml (${VAR} ve environment anahtarları), deploy/*.sh (${VAR:-…}
biçimindeki dış girdiler), deploy/systemd (Environment=), frontend/src (import.meta.env.VITE_*).
Çalıştır: python3 deploy/tests/check-parameters.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Betik içi yardımcılar: dışarıdan verilmez, dokümana girmez.
INTERNAL = {"LOG_TAG", "PREV_ID"}  # PREV_ID: deploy.sh log'unda ${PREV_ID:-yok}
# Dokümanda "kullanılmaz" diye anılan adlar (kodda bilerek yok).
DOCUMENTED_UNUSED = {"NVIDIA_API_KEY"}
# Docker image'ının Python çalışma ortamı (uygulama ayarı değil).
RUNTIME = {"PATH", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE", "PIP_DISABLE_PIP_VERSION_CHECK"}


def found() -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}

    def add(name, where):
        names.setdefault(name, set()).add(where)

    for f in (ROOT / "backend/app").rglob("*.py"):
        for m in re.finditer(r'(?:os\.getenv|_env|os\.environ\.get)\(\s*"([A-Z][A-Z0-9_]+)"'
                             r'|os\.environ\[\s*"([A-Z][A-Z0-9_]+)"', f.read_text()):
            add(m.group(1) or m.group(2), "backend")
    for line in (ROOT / "backend/Dockerfile").read_text().splitlines():
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]+)=", line if re.match(r"\s*(ENV|\w+=)", line) else ""):
            add(m.group(1), "Dockerfile")
    compose = (ROOT / "deploy/docker-compose.yml").read_text()
    for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]+)", compose):
        add(m.group(1), "compose")
    env_block = re.findall(r"environment:\n((?:\s{6,}[A-Z0-9_]+:.*\n)+)", compose)
    for block in env_block:
        for m in re.finditer(r"^\s+([A-Z][A-Z0-9_]+):", block, re.M):
            add(m.group(1), "compose")
    for f in (ROOT / "deploy").glob("*.sh"):
        for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]+):-", f.read_text()):
            add(m.group(1), f.name)
    for f in (ROOT / "deploy/systemd").glob("*"):
        for m in re.finditer(r"^Environment=([A-Z][A-Z0-9_]+)=", f.read_text(), re.M):
            add(m.group(1), f.name)
    for f in (ROOT / "frontend/src").rglob("*.js*"):
        for m in re.finditer(r"import\.meta\.env\.(VITE_[A-Z0-9_]+)", f.read_text()):
            add(m.group(1), "frontend")
    for k in INTERNAL | RUNTIME:
        names.pop(k, None)
    return names


def documented() -> set[str]:
    doc = (ROOT / "deploy/PARAMETERS.md").read_text()
    return set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", doc, re.M)) | (
        set(re.findall(r"`([A-Z][A-Z0-9_]+)`", doc)) & DOCUMENTED_UNUSED)


code, doc = found(), documented()
missing = sorted(set(code) - doc)
stale = sorted(doc - set(code) - DOCUMENTED_UNUSED)
print(f"kodda {len(code)} değişken, PARAMETERS.md tablolarında {len(doc - DOCUMENTED_UNUSED)}")
for n in missing:
    print(f"  ✗ dokümanda yok: {n} ({', '.join(sorted(code[n]))})")
for n in stale:
    print(f"  ✗ kodda yok (eski satır?): {n}")
if not missing and not stale:
    print("  ✓ birebir eşleşiyor")
sys.exit(1 if missing or stale else 0)
