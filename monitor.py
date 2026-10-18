#!/usr/bin/env python3
"""
Wafid auto-assign monitor -> Telegram.
Read-only: loads the public book-appointment page, reads COUNTRY_MEDICAL_CENTER
(the center the server auto-assigns next per destination) and reports changes.
"""
import json, os, re, sys, time, random, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta

URL = os.environ.get("WAFID_URL", "https://wafid.com/en/book-appointment/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
STATE = os.environ.get("STATE_FILE", "state/state.json")
TG_TOKEN = os.environ.get("TG_TOKEN", "").strip()
TG_CHAT = os.environ.get("TG_CHAT_ID", "").strip()
COUNTRY = os.environ.get("COUNTRY", "BD").strip() or "BD"
INTERVAL = max(int(os.environ.get("MIN_INTERVAL","30")), int(os.environ.get("INTERVAL_SEC", "30") or 30))
RUN_MIN = float(os.environ.get("RUN_MINUTES", "340") or 340)
SUMMARY_MIN = float(os.environ.get("SUMMARY_MINUTES", "60") or 60)
TZ = timezone(timedelta(hours=6))  # Bangladesh time
DEST_NAME = {"SA": "Saudi Arabia", "KW": "Kuwait", "OM": "Oman", "QA": "Qatar", "BH": "Bahrain", "UAE": "UAE", "AE": "AE", "YE": "Yemen"}

def parse_targets(s):
    # "SA=10600|10734, KW=6136"  or  "10600,10734" (= any destination)
    out = {}
    for part in re.split(r"[,;\n]+", s or ""):
        part = part.strip()
        if not part: continue
        if "=" in part:
            d, ids = part.split("=", 1)
            out.setdefault(d.strip().upper(), set()).update(x.strip() for x in re.split(r"[|/ ]+", ids) if x.strip())
        else:
            out.setdefault("*", set()).add(part)
    return out
TARGETS = parse_targets(os.environ.get("TARGETS", ""))

def now(): return time.time()
def bdt(ts): return datetime.fromtimestamp(ts, TZ).strftime("%d/%m %H:%M:%S")
def dur(sec):
    sec = int(sec)
    if sec < 60: return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60: return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 24: return f"{h}h {m}m"
    d, h = divmod(h, 24); return f"{d}d {h}h"
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def log(*a): print(datetime.now(TZ).strftime("%H:%M:%S"), *a, flush=True)

def tg(text):
    if not (TG_TOKEN and TG_CHAT):
        log("[telegram disabled]", text.replace("\n", " | ")[:300]); return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    for attempt in range(3):
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data, timeout=20).read(); return
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            log("telegram error", e.code, body[:200])
            if e.code == 429:
                try: time.sleep(json.loads(body)["parameters"]["retry_after"] + 1); continue
                except Exception: pass
            if e.code in (400, 401, 403, 404): return
        except Exception as e:
            log("telegram error", e)
        time.sleep(3)

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "ignore"); code = r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    m = re.search(r'COUNTRY_MEDICAL_CENTER\s*=\s*JSON\.parse\("((?:[^"\\]|\\.)*)"\)', html)
    if not m: return None, code
    data = json.loads(json.loads('"' + m.group(1) + '"'))
    live = {}
    for row in data.get(COUNTRY, []):
        cid, name, _, dest = row[0], row[1], row[2], row[3]
        live[str(dest)] = {"id": str(cid), "name": name}
    return live, code

def load():
    try:
        with open(STATE) as f: return json.load(f)
    except Exception:
        return {"current": {}, "history": [], "stats": {}}
def save(st):
    os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True)
    st["history"] = st["history"][-2000:]
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f: json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)

def is_target(dest, cid):
    return cid in TARGETS.get(dest, set()) or cid in TARGETS.get("*", set())

def avg_gap(st, dest):
    ts = [h["at"] for h in st["history"] if h["dest"] == dest and h.get("from")]
    if len(ts) < 2: return None
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    return sum(gaps) / len(gaps), len(gaps)

def target_text():
    if not TARGETS: return "none"
    return ", ".join(f"{d if d != '*' else 'any'}: " + "/".join("#" + x for x in sorted(v)) for d, v in TARGETS.items())

def board(st):
    lines = []
    for dest, c in sorted(st["current"].items()):
        held = dur(now() - c["since"]) if c.get("since") else "?"
        mark = "  <b>[TARGET]</b>" if is_target(dest, c["id"]) else ""
        lines.append(f"<b>{esc(dest)}</b>  #{esc(c['id'])} {esc(c['name'])}  <i>({held})</i>{mark}")
    return "\n".join(lines) or "-"

def main():
    st = load()
    started = now(); end = started + RUN_MIN * 60
    last_summary = now(); fails = 0; checks = 0; err_notified = False; backoff = 0
    first = not st["current"]
    log(f"start: country={COUNTRY} interval={INTERVAL}s run={RUN_MIN}min targets={target_text()}")
    while now() < end:
        live, code = fetch()
        checks += 1
        if live is None:
            fails += 1
            backoff = min(backoff + 1, 5)
            log(f"fetch failed HTTP {code} (#{fails})")
            if fails == 5 and not err_notified:
                tg(f"<b>Wafid monitor: site not responding</b>\nLast status: HTTP {code}. The monitor keeps trying with longer pauses.")
                err_notified = True
        else:
            if err_notified: tg("<b>Wafid monitor: site is back</b>, checks resumed.")
            fails = 0; err_notified = False; backoff = 0
            t = now(); changes = []
            for dest, c in live.items():
                old = st["current"].get(dest)
                if old and old["id"] == c["id"]:
                    old["name"] = c["name"]; continue
                ev = {"at": t, "dest": dest, "id": c["id"], "name": c["name"],
                      "from": old["id"] if old else None, "from_name": old["name"] if old else None,
                      "held": (t - old["since"]) if old and old.get("since") else None}
                st["history"].append(ev)
                st["current"][dest] = {"id": c["id"], "name": c["name"], "since": t}
                if old: changes.append(ev)
            save(st)
            if first:
                first = False
                tg(f"<b>Wafid monitor started</b> ({COUNTRY})\n\n{board(st)}\n\nTargets: {esc(target_text())}\nCheck every {INTERVAL}s")
            for ev in changes:
                g = avg_gap(st, ev["dest"])
                gtxt = f"\nAverage change gap for {ev['dest']}: <b>{dur(g[0])}</b> ({g[1]} changes)" if g else ""
                held = f" (held for {dur(ev['held'])})" if ev["held"] else ""
                if is_target(ev["dest"], ev["id"]):
                    tg(f"<b>GOOD TIME TO BOOK - {esc(ev['dest'])}</b>\n\n"
                       f"Auto assign now gives: <b>#{esc(ev['id'])} {esc(ev['name'])}</b>\n"
                       f"Book now with Standard Appointment and leave Medical Center empty (auto assign).\n"
                       f"Previous: #{esc(ev['from'])} {esc(ev['from_name'])}{held}\n"
                       f"Detected {bdt(ev['at'])} (BD time){gtxt}\n\n{URL}")
                else:
                    tg(f"<b>Center changed - {esc(ev['dest'])}</b> ({esc(DEST_NAME.get(ev['dest'], ev['dest']))})\n"
                       f"#{esc(ev['from'])} {esc(ev['from_name'])}{held}\n-> <b>#{esc(ev['id'])} {esc(ev['name'])}</b>\n"
                       f"{bdt(ev['at'])}{gtxt}")
            if changes: log("changes:", ", ".join(f"{e['dest']} {e['from']}->{e['id']}" for e in changes))
            if SUMMARY_MIN > 0 and now() - last_summary >= SUMMARY_MIN * 60:
                last_summary = now()
                tg(f"<b>Wafid status</b> {bdt(now())}\n\n{board(st)}\n\n{checks} checks in this run · targets {esc(target_text())}")
        sleep = INTERVAL * (2 ** backoff) + random.uniform(0, 5)
        sleep = min(sleep, 900, max(0, end - now()))
        if sleep <= 0: break
        time.sleep(sleep)
    save(st)
    log(f"run finished: {checks} checks")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
