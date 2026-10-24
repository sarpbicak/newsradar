"""Yenileme kuyruğu — sıra, birleştirme, hak, iptal, sınır, bütçe, zamanlayıcı (izole temp DB).

Gerçek tarama YOK: NEWSRADAR_FAKE_REFRESH_SECONDS ile sahte tarama (ağ/LLM yok). Sahte
tarama ayrıca bir "kapı" ile sarılır: HOLD açıkken her iş başladığı an (hak düşüldükten
sonra) STEP semaforunu bekler → testler işleri tek tek ilerletir (sabit uyku yok).

Doğrular:
  (A) FIFO + konumlar (3 kullanıcı), kullanıcı başı en fazla 1 iş (running / queued yanıtı),
      POST'tan hemen sonra /status tutarlı, sıradan çalışmaya geçişte boşluk yok
  (B) birleştirme: aynı entity → "merged" (hak düşülmez); kısmi örtüşme → yalnızca kalanlar
  (C) hak sıraya girerken değil iş başlarken düşülür
  (D) tarama hatası → "failed" + hak iadesi; işçi ayakta kalır
  (E) DELETE /refresh: sıradaki iş iptal (204), çalışan 409, yok 404
  (F) sıra sınırı (NEWSRADAR_REFRESH_QUEUE_MAX) → queue_full
  (G) bütçe doldu → sıradaki işler "budget"; yeni istek reason="budget"
  (H) zamanlayıcı işi en düşük öncelik, sırada en fazla bir tane, konum sayılmaz
  (I) sahte tarama ilerleme bildirir ("Yenileniyor i/N")
Çalıştır: python test_refresh_queue.py
"""
import os
import tempfile
import threading
import time

_db = os.path.join(tempfile.gettempdir(), "nr_test_refresh_queue.db")
for sfx in ("", "-wal", "-shm"):
    try:
        os.remove(_db + sfx)
    except FileNotFoundError:
        pass
os.environ.update(
    NEWSRADAR_DB=_db, APP_PASSWORD="genelsifre", APP_SECRET="rq-secret-1234567890",
    ADMIN_USERNAME="rootadmin", NEWSRADAR_SCHEDULER="off", NEWSRADAR_SEED_ON_START="off",
    NEWSRADAR_MAX_USERS="0", NEWSRADAR_TRUSTED_PROXY="render", NEWSRADAR_COOKIE_SECURE="off",
    NEWSRADAR_COOKIE_SAMESITE="lax", NEWSRADAR_MAX_REFRESH_ANON="50",
    NEWSRADAR_MAX_ENTITIES_ANON="10", NEWSRADAR_DAILY_BUDGET_USD="0",
    # YALNIZCA TEST: sahte tarama (ağ/LLM yok), iş başına toplam 0.3 sn.
    NEWSRADAR_FAKE_REFRESH_SECONDS="0.3", NEWSRADAR_REFRESH_QUEUE_MAX="20",
)

from fastapi.testclient import TestClient  # noqa: E402

import app.budget as budget_mod  # noqa: E402
import app.refresh as R  # noqa: E402
import app.refresh_queue as Q  # noqa: E402
from app import scheduler  # noqa: E402
from app.api.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import UsageEvent  # noqa: E402

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {msg}")
    else:
        FAIL += 1; print(f"  ✗ FAIL: {msg}")


def wait_until(cond, timeout=10.0, step=0.01):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return False


# ---- Sahte taramayı kapıyla sar (işçi modül özniteliğinden çağırır) ----
RUNS: list = []            # (user_id, işlenen entity id'leri) — iş gerçekten başladığında
HOLD = {"on": False}
STEP = threading.Semaphore(0)
FAIL_FOR: set = set()      # bu kullanıcıların taraması hata atar
_orig_fake = R.run_fake_refresh


def gated_fake(ids, uid, secs):
    RUNS.append((uid, sorted(ids) if ids is not None else None))
    if HOLD["on"]:
        STEP.acquire(timeout=15)
    if uid in FAIL_FOR:
        raise RuntimeError("test: tarama çöktü")
    return _orig_fake(ids, uid, secs)


R.run_fake_refresh = gated_fake


def release(n=1):
    for _ in range(n):
        STEP.release()


def idle():
    return Q._running is None and not Q._waiting


def finish_all():
    """Kapıyı kapat, bekleyenleri bırak, kuyruk boşalsın, artan izinleri boşalt."""
    HOLD["on"] = False
    release(30)
    ok = wait_until(idle)
    while STEP.acquire(blocking=False):
        pass
    return ok


def run_of(uid):
    return [ids for u, ids in RUNS if u == uid]


with TestClient(app) as c:
    _ip = [10]

    def new_user(*names):
        """Yeni misafir (benzersiz IP) + izleme listesine keyword entity'ler."""
        _ip[0] += 1
        c.cookies.clear()
        tok = c.post("/session/bootstrap", headers={"X-Forwarded-For": f"203.0.113.{_ip[0]}"}).json()["token"]
        c.cookies.clear()
        h = {"Authorization": f"Bearer {tok}"}
        uid = c.get("/users/me", headers=h).json()["id"]
        for n in names:
            r = c.post("/entities", headers=h, json={"name": n, "type": "keyword", "query": n, "language": "en"})
            assert r.status_code in (200, 201), (n, r.status_code, r.text)
        ids = {e["id"]: e["name"] for e in c.get("/entities", headers=h).json()}
        return h, uid, ids

    def st(h):
        return c.get("/status", headers=h).json()

    def post(h):
        return c.post("/refresh", headers=h).json()

    def events(uid):
        with session_scope() as s:
            return s.query(UsageEvent).filter(UsageEvent.user_id == uid,
                                              UsageEvent.event_type == "refresh").count()

    check(Q._worker is not None and Q._worker.is_alive() and Q._worker.daemon,
          "kuyruk işçisi açılışta başladı (daemon)")

    # ------------------------------------------------------------------ #
    print("== A: FIFO, konumlar, kullanıcı başı 1 iş, durum tutarlılığı")
    H1, u1, _ = new_user("Alpha")
    H2, u2, _ = new_user("Bravo")
    H3, u3, _ = new_user("Charlie")
    RUNS.clear(); HOLD["on"] = True
    a1 = post(H1)
    check(a1["accepted"] and a1["started"] and a1["is_running"] and not a1["queued"]
          and a1["reason"] is None and a1["queue_position"] is None, f"1. kullanıcı hemen başladı ({a1})")
    s1 = st(H1)
    check(s1["is_running"] and not s1["queued"] and s1["progress_total"] == 1,
          "POST'tan hemen sonra /status is_running=true (boşluk yok)")
    a2 = post(H2)
    check(a2["accepted"] and a2["queued"] and a2["queue_position"] == 1 and not a2["started"]
          and not a2["is_running"] and a2["reason"] is None, f"2. kullanıcı sırada 1 ({a2})")
    check("sıra" in a2["message"] and "—" not in a2["message"], f"Türkçe mesaj, uzun tire yok ({a2['message']})")
    a3 = post(H3)
    check(a3["queued"] and a3["queue_position"] == 2, f"3. kullanıcı sırada 2 ({a3['queue_position']})")
    s3 = st(H3)
    check(s3["queued"] and s3["queue_position"] == 2 and s3["queue_length"] == 2 and not s3["is_running"],
          f"/status: sıra 2/2 ({s3['queue_position']}/{s3['queue_length']})")
    check(st(H1)["queue_length"] == 2 and st(H1)["queue_position"] is None, "çalışan kullanıcı sırada değil, uzunluk 2")
    again = post(H1)
    check(again["accepted"] and again["reason"] == "running" and again["is_running"] and not again["started"],
          f"çalışan kullanıcı tekrar → running ({again['reason']})")
    again = post(H2)
    check(again["accepted"] and again["reason"] == "queued" and again["queue_position"] == 1 and not again["started"],
          f"sıradaki kullanıcı tekrar → queued, yeni iş yok ({again['reason']})")
    check(len(Q._waiting) == 2, f"ikinci istekler yeni iş eklemedi (bekleyen {len(Q._waiting)})")
    # 1. biter → 2. çalışmaya geçer; arada 2. kullanıcı hiçbir an "ne sırada ne çalışıyor" olmaz.
    release(1)
    gap = []

    def u2_running():
        s = st(H2)
        if not (s["is_running"] or s["queued"]):
            gap.append(s)
        return s["is_running"]
    check(wait_until(u2_running), "1. bitti → 2. kullanıcı çalışıyor")
    check(not gap, f"sıradan çalışmaya geçişte boşluk yok ({len(gap)} boş yoklama)")
    s3 = st(H3)
    check(s3["queue_position"] == 1 and s3["queue_length"] == 1, f"3. kullanıcı öne geçti: sıra 1/1 ({s3['queue_position']})")
    check(finish_all(), "kuyruk boşaldı")
    check([u for u, _ in RUNS] == [u1, u2, u3], f"FIFO sırası ({[u for u, _ in RUNS]} == {[u1, u2, u3]})")
    check(all(st(h)["last_result_status"] == "done" and st(h)["last_completed_at"] and st(h)["last_summary"]
              for h in (H1, H2, H3)), "üçü de done, özet + bitiş zamanı görünür")

    # ------------------------------------------------------------------ #
    print("== B: birleştirme")
    HA, ua, ida = new_user("Xray")
    HB, ub, idb = new_user("Xray")
    x_id = next(iter(ida))
    check(set(ida) == set(idb), "aynı şirket ortak havuzda tek entity")
    RUNS.clear(); HOLD["on"] = True
    check(post(HA)["started"], "A başladı (Xray)")
    check(post(HB)["queued"], "B sırada (aynı Xray)")
    release(1)
    check(wait_until(lambda: st(HB)["last_result_status"] is not None), "B'nin işi bitti")
    sb = st(HB)
    check(sb["last_result_status"] == "merged" and sb["last_completed_at"] and sb["last_summary"] is None,
          f"B → merged ({sb['last_result_status']})")
    check(sb["refresh_used"] == 0 and events(ub) == 0, f"merged: hak düşülmedi (used={sb['refresh_used']})")
    check("düşülmedi" in (sb["last_result_message"] or ""), f"merged mesajı ({sb['last_result_message']})")
    check(run_of(ub) == [], "B için tarama hiç çalışmadı")
    check(finish_all(), "kuyruk boşaldı")
    # Kısmi örtüşme: C {Yankee}, D {Yankee, Zulu} → D yalnızca Zulu'yu işler.
    HC, uc, idc = new_user("Yankee")
    HD, ud, idd = new_user("Yankee", "Zulu")
    zulu = [i for i, n in idd.items() if n == "Zulu"]
    RUNS.clear(); HOLD["on"] = True
    post(HC)
    check(post(HD)["queued"], "D sırada (Yankee + Zulu)")
    release(1)
    check(wait_until(lambda: run_of(ud) != []), "D başladı")
    check(run_of(ud) == [zulu], f"kısmi örtüşme: D yalnızca kalanı işler ({run_of(ud)} == {[zulu]})")
    check(st(HD)["progress_total"] == 1, f"ilerleme toplamı kalan entity sayısı ({st(HD)['progress_total']})")
    check(finish_all(), "kuyruk boşaldı")
    check(st(HD)["last_result_status"] == "done" and st(HD)["refresh_used"] == 1, "D done, hak 1")

    # ------------------------------------------------------------------ #
    print("== C: hak iş başlarken düşülür")
    HE, ue, _ = new_user("Echo")
    HF, uf, _ = new_user("Foxtrot")
    RUNS.clear(); HOLD["on"] = True
    post(HE)
    check(wait_until(lambda: events(ue) == 1), "E başladı → hakkı düşüldü")
    check(post(HF)["queued"], "F sırada")
    sf = st(HF)
    check(sf["refresh_used"] == 0 and events(uf) == 0, f"sıradayken hak düşülmez (used={sf['refresh_used']})")
    release(1)
    check(wait_until(lambda: st(HF)["is_running"]), "F çalışmaya geçti")
    check(st(HF)["refresh_used"] == 1, f"F başlayınca hak düşüldü ({st(HF)['refresh_used']})")
    check(finish_all(), "kuyruk boşaldı")

    # ------------------------------------------------------------------ #
    print("== D: tarama hatası → failed + iade")
    HG, ug, _ = new_user("Golf")
    FAIL_FOR.add(ug)
    a = post(HG)
    check(a["started"], "G başladı")
    check(wait_until(lambda: st(HG)["last_result_status"] == "failed"), "G → failed")
    sg = st(HG)
    check(not sg["is_running"] and sg["last_summary"] is None and sg["last_completed_at"] is None,
          "failed: çalışmıyor, özet/bitiş (taze veri) yok")
    check(wait_until(lambda: events(ug) == 0) and st(HG)["refresh_used"] == 0, "hak iade edildi (UsageEvent silindi)")
    check("iade" in (sg["last_result_message"] or ""), f"failed mesajı ({sg['last_result_message']})")
    FAIL_FOR.discard(ug)
    HH, uh, _ = new_user("Hotel")
    post(HH)
    check(wait_until(lambda: st(HH)["last_result_status"] == "done"), "hatadan sonra işçi ayakta: sonraki iş done")
    check(finish_all(), "kuyruk boşaldı")

    # ------------------------------------------------------------------ #
    print("== E: DELETE /refresh (iptal)")
    HI, ui, _ = new_user("India")
    HJ, uj, _ = new_user("Juliet")
    HK0, _, _ = new_user("Kilo")
    RUNS.clear(); HOLD["on"] = True
    post(HI)
    check(post(HJ)["queued"], "J sırada")
    r = c.delete("/refresh", headers=HJ)
    check(r.status_code == 204, f"sıradaki iş iptal → 204 ({r.status_code})")
    sj = st(HJ)
    check(not sj["queued"] and sj["last_result_status"] == "canceled" and sj["refresh_used"] == 0
          and sj["last_completed_at"] is None, f"iptal: sırada değil, canceled, hak düşülmedi ({sj['last_result_status']})")
    check(c.delete("/refresh", headers=HJ).status_code == 404, "tekrar iptal → 404")
    check(c.delete("/refresh", headers=HI).status_code == 409, "çalışan iş → 409")
    check(c.delete("/refresh", headers=HK0).status_code == 404, "etkin işi yok → 404")
    check(finish_all(), "kuyruk boşaldı")
    check(run_of(uj) == [] and events(uj) == 0, "iptal edilen iş hiç çalışmadı")

    # ------------------------------------------------------------------ #
    print("== F: sıra sınırı")
    get_settings().refresh_queue_max = 2
    hs = [new_user(f"Lima{i}")[0] for i in range(4)]
    RUNS.clear(); HOLD["on"] = True
    acks = [post(h) for h in hs]
    check(acks[0]["started"] and acks[1]["queued"] and acks[2]["queued"], "1 çalışıyor + 2 sırada")
    full = acks[3]
    check(full["accepted"] is False and full["reason"] == "queue_full" and not full["queued"],
          f"sınır 2 → 4. istek queue_full ({full['reason']})")
    check("dolu" in full["message"] and "—" not in full["message"], f"açık mesaj ({full['message']})")
    r = c.post("/refresh", headers=hs[3])
    check(r.status_code == 200, f"queue_full HTTP 200 ({r.status_code})")
    check(finish_all(), "kuyruk boşaldı")
    get_settings().refresh_queue_max = 20

    # ------------------------------------------------------------------ #
    print("== G: bütçe doldu")
    HL, ul, _ = new_user("Mike")
    HM, um, _ = new_user("November")
    HN, un, _ = new_user("Oscar")
    RUNS.clear(); HOLD["on"] = True
    post(HL)
    check(post(HM)["queued"] and post(HN)["queued"], "M, N sırada")
    check(Q.enqueue_scheduler(), "zamanlayıcı işi de sırada")
    orig_budget = budget_mod.is_budget_exceeded
    budget_mod.is_budget_exceeded = lambda: True
    try:
        release(1)
        check(wait_until(idle), "kuyruk boşaldı")
        sm, sn = st(HM), st(HN)
        check(sm["last_result_status"] == "budget" and sn["last_result_status"] == "budget",
              f"sıradakiler → budget ({sm['last_result_status']}, {sn['last_result_status']})")
        check(sm["refresh_used"] == 0 and sn["refresh_used"] == 0, "budget: hak düşülmedi")
        check("bütçe" in (sm["last_result_message"] or "").lower(), f"bütçe mesajı ({sm['last_result_message']})")
        check(st(HL)["last_result_status"] == "done", "çalışan iş kendi akışında bitti (done)")
        check(run_of(um) == [] and run_of(un) == [] and run_of(None) == [], "bütçe sonrası tarama çalışmadı (zamanlayıcı dahil)")
        a = post(HM)
        check(a["accepted"] is False and a["reason"] == "budget" and "—" not in a["message"],
              f"bütçe doluyken POST → budget ({a['reason']})")
        check(idle(), "bütçe doluyken iş sıraya girmedi")
    finally:
        budget_mod.is_budget_exceeded = orig_budget
    finish_all()

    # ------------------------------------------------------------------ #
    print("== H: zamanlayıcı işi en düşük öncelik")
    HP, up, idp = new_user("Papa")
    HQ, uq, idq = new_user("Quebec")
    RUNS.clear(); HOLD["on"] = True
    post(HP)
    scheduler.set_enabled(True)
    try:
        scheduler._job()  # zamanlayıcı doğrudan çalıştırmaz, kuyruğa bırakır
        check(sum(1 for j in Q._waiting if j.user_id is None) == 1, "scheduler._job kuyruğa iş bıraktı")
        scheduler._job()
        check(sum(1 for j in Q._waiting if j.user_id is None) == 1, "sırada en fazla bir zamanlayıcı işi")
        check(Q.enqueue_scheduler() is False, "enqueue_scheduler ikinciyi reddetti")
    finally:
        scheduler.set_enabled(False)
    aq = post(HQ)
    check(aq["queued"] and aq["queue_position"] == 1, f"kullanıcı zamanlayıcının önüne geçer (sıra {aq['queue_position']})")
    sq = st(HQ)
    check(sq["queue_length"] == 1, f"queue_length zamanlayıcıyı saymaz ({sq['queue_length']})")
    check(finish_all(), "kuyruk boşaldı")
    order = [u for u, _ in RUNS]
    check(order == [up, uq, None], f"sıra: P, Q, zamanlayıcı ({order})")
    sched_ids = run_of(None)[0] if run_of(None) else None
    check(sched_ids is not None and not (set(idp) | set(idq)) & set(sched_ids) and len(sched_ids) > 0,
          "zamanlayıcı işi beklerken tazelenen entity'leri atladı (birleştirme)")

    # ------------------------------------------------------------------ #
    print("== I: sahte tarama ilerlemesi")
    HR, ur, idr = new_user("Romeo", "Sierra")
    RUNS.clear()
    seen = []

    def progressed():
        s = st(HR)
        if s["is_running"] and s["step_entity"]:
            seen.append((s["step"], s["step_entity"], s["progress_done"], s["progress_total"]))
        return s["last_result_status"] == "done"
    check(post(HR)["started"], "R başladı")
    check(wait_until(progressed), "R bitti")
    check(any(t == 2 for *_, t in seen) and {e for _, e, _, _ in seen} <= set(idr.values()) and seen,
          f"ilerleme bildirildi: adım/entity/i/N ({seen[:2]})")
    summ = st(HR)["last_summary"]
    check(summ and summ["fetched_new"] == 0 and summ["analyzed"] == 0, "sahte özet sıfırlı")

print("=" * 50)
print(f"SONUÇ: {PASS} geçti, {FAIL} başarısız")
raise SystemExit(1 if FAIL else 0)
