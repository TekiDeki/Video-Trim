#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_video.py - suita Video Trimmer.

Ce verifica, in ordinea in care se intimpla un utilizator:
  1. pagina se incarca fara erori de consola si fara cereri in exterior;
  2. un videoclip real (facut in pagina: canvas + MediaRecorder) se incarca in unealta;
  3. durata, marimea si formatul apar dupa incarcare;
  4. intervalul se poate muta (silderul de start si cel de end), iar butoanele
     "Start here" / "End here" iau pozitia de redare;
  5. exportul chiar produce un fisier: non-gol, cu durata ceruta, in containerul anuntat;
  6. exportul cu sunetul scos merge pina la capat;
  7. "Save this frame" descarca un PNG;
  8. la 320px nu exista derulare pe orizontala, iar pe pointer gros fiecare tinta
     de atingere are cel putin 44x44px (regula casei, WCAG 2.5.5);
  9. cele patru limbi (en, ro, sr latina, sr chirilica): titlu, h1, descriere, JSON-LD,
     <html lang>, linia de sprijin, memorarea alegerii si faptul ca nici o limba nu
     rupe asezarea la 320px.

Folosire:
    python3 tests/test_video.py             # pagina locala, servita pe 127.0.0.1
    python3 tests/test_video.py --live      # pagina publicata
    python3 tests/test_video.py --keep      # nu sterge videoclipul de proba

Iese cu cod 1 la prima problema.
"""
import base64
import functools
import http.server
import pathlib
import socketserver
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = "https://tekideki.github.io/Video-Trim/"
USE_LIVE = "--live" in sys.argv
KEEP = "--keep" in sys.argv

PASS = 0
FAIL = 0
PROBLEMS = []


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   " + msg)
    else:
        FAIL += 1
        PROBLEMS.append(msg + (" (" + str(extra) + ")" if extra else ""))
        print("  RĂU  " + msg + (" (" + str(extra) + ")" if extra else ""))


# ---------------------------------------------------------------- server local
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = functools.partial(Quiet, directory=str(ROOT))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d/index.html" % httpd.server_address[1]


# ---------------------------------------------------------------- videoclip de proba
MAKE_VIDEO = """
async (secs) => {
  const c = document.createElement('canvas'); c.width = 320; c.height = 180;
  const ctx = c.getContext('2d');
  const stream = c.captureStream(25);
  const rec = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8' });
  const chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  const stopped = new Promise(r => rec.onstop = r);
  rec.start();
  const t0 = performance.now();
  await new Promise(res => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      ctx.fillStyle = 'hsl(' + (t * 120) + ',70%,50%)';
      ctx.fillRect(0, 0, 320, 180);
      ctx.fillStyle = '#08121c'; ctx.font = 'bold 40px sans-serif';
      ctx.fillText(t.toFixed(2) + 's', 100, 110);
      if (t < secs) requestAnimationFrame(tick); else res();
    };
    tick();
  });
  rec.stop(); await stopped;
  const blob = new Blob(chunks, { type: 'video/webm' });
  const buf = await blob.arrayBuffer();
  let bin = '';
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
"""

# muta un slider ca un utilizator (valoare + eveniment input)
SET_RANGE = """
([id, value]) => {
  const el = document.getElementById(id);
  el.value = String(value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return el.value;
}
"""


def main():
    httpd = None
    url = LIVE
    if not USE_LIVE:
        httpd, url = serve()
    print("pagina: " + url)
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="vtrim-"))
    clip = workdir / "probe.webm"

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------------- 1. incarcarea paginii, fara erori si fara cereri externe
        print("\n1. Pagina")
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        page = ctx.new_page()
        console_errors, foreign = [], []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("request", lambda r: foreign.append(r.url)
                if not r.url.startswith(url.rsplit("/", 1)[0]) and not r.url.startswith("blob:")
                and not r.url.startswith("data:") else None)
        resp = page.goto(url, wait_until="load")
        check(resp is not None and resp.ok, "pagina raspunde 200", resp.status if resp else "fara raspuns")
        page.wait_for_timeout(400)
        check(page.title().lower().find("video") >= 0, "titlul paginii e despre video", page.title()[:60])
        check(len(foreign) == 0, "nici o cerere in afara paginii", foreign[:3])

        # ---------------- 2. videoclip de proba + incarcare
        print("\n2. Incarcarea unui videoclip")
        b64 = page.evaluate(MAKE_VIDEO, 2.0)
        clip.write_bytes(base64.b64decode(b64))
        check(clip.stat().st_size > 5000, "videoclipul de proba s-a generat", str(clip.stat().st_size) + " B")
        page.set_input_files("#file", str(clip))
        page.wait_for_selector("#editCard:not([hidden])", timeout=10000)
        page.wait_for_function("() => document.getElementById('exportBtn').disabled === false", timeout=10000)
        metas = page.inner_text("#meta")
        check("long" in metas, "durata apare dupa incarcare", metas[:80].replace("\n", " "))
        check(page.inner_text("#fileline").find("probe.webm") >= 0, "numele fisierului apare")
        check("320×180" in metas, "rezolutia apare", metas[:80].replace("\n", " "))
        dur = page.evaluate("() => document.querySelector('video').duration")
        check(1.5 <= dur <= 3.0, "durata citita corect", round(dur, 2))

        # ---------------- 3. intervalul
        print("\n3. Alegerea intervalului")
        page.evaluate(SET_RANGE, ["start", 0.4])
        page.evaluate(SET_RANGE, ["end", 1.6])
        page.wait_for_timeout(120)
        start_out = page.inner_text("#startOut")
        end_out = page.inner_text("#endOut")
        check(start_out.startswith("0:00.4"), "startul afiseaza 0:00.4", start_out)
        check(end_out.startswith("0:01.6"), "sfirsitul afiseaza 0:01.6", end_out)
        label = page.inner_text("#exportLabel")
        check("1.2" in label, "butonul arata lungimea pastrata", label)
        # butoanele care iau pozitia de redare
        page.evaluate("() => { const v = document.querySelector('video'); v.currentTime = 0.9; }")
        page.wait_for_timeout(300)
        page.click("#setStart")
        page.wait_for_timeout(100)
        check(page.inner_text("#startOut").startswith("0:00.9"), "„Start here” ia pozitia de redare",
              page.inner_text("#startOut"))
        page.click("#resetRange")
        page.wait_for_timeout(100)
        check(page.inner_text("#startOut").startswith("0:00.0"), "„Whole video” readuce intervalul intreg")
        # inapoi la intervalul de testat
        page.evaluate(SET_RANGE, ["start", 0.4])
        page.evaluate(SET_RANGE, ["end", 1.6])
        page.wait_for_timeout(100)

        # ---------------- 4. export
        print("\n4. Exportul")
        t0 = time.time()
        page.click("#exportBtn")
        page.wait_for_selector("#result.on", timeout=90000)
        took = time.time() - t0
        check(took < 45, "exportul s-a terminat in timp rezonabil", str(round(took, 1)) + " s")
        meta_out = page.inner_text("#rMeta")
        check("long" in meta_out, "rezultatul arata durata", meta_out.replace("\n", " ")[:80])
        info = page.evaluate("""async () => {
          const a = document.getElementById('download');
          const v = document.getElementById('rPreview');
          await new Promise(r => { if (v.readyState >= 1) r(); else v.onloadedmetadata = r; });
          const shown = document.getElementById('rMeta').innerText;
          return { name: a.getAttribute('download'), dur: v.duration, shown: shown, href: a.href.slice(0, 5) };
        }""")
        check(info["href"] == "blob:", "rezultatul e un blob local, nu un link catre retea", info["href"])
        check(info["name"].endswith(".webm") or info["name"].endswith(".mp4"), "are extensia potrivita", info["name"])
        check("0:01.2" in info["shown"] or "0:01.1" in info["shown"] or "0:01.3" in info["shown"],
              "durata afisata e cea ceruta (1.2 s)", info["shown"].replace("\n", " ")[:60])
        check(isinstance(info["dur"], float) and (info["dur"] == info["dur"]) and
              (info["dur"] == float("inf") or 0.7 <= info["dur"] <= 2.4),
              "elementul video nu raporteaza o durata imposibila", str(info["dur"]))
        # descarcarea, adica exact ce face utilizatorul
        out_path = workdir / "export1.webm"
        with page.expect_download(timeout=20000) as dl1:
            page.click("#download")
        dl1.value.save_as(str(out_path))
        check(out_path.stat().st_size > 20000, "fisierul descarcat are continut",
              str(out_path.stat().st_size) + " B")
        check(out_path.read_bytes()[:4] == b"\x1a\x45\xdf\xa3", "fisierul descarcat e un container valid (WebM)",
              out_path.read_bytes()[:8].hex())
        # sunetul se vede in antetul containerului: pista Opus e anuntata prin CodecID
        check(b"A_OPUS" in out_path.read_bytes(), "exportul cu sunet are pista audio (Opus)")
        check(page.evaluate("() => document.querySelector('video').paused"), "redarea s-a oprit la sfirsit")

        # ---------------- 5. sunetul scos
        print("\n5. Export fara sunet")
        page.click("#againBtn")
        page.check("#mute")
        page.click("#exportBtn")
        page.wait_for_selector("#result.on", timeout=90000)
        out2 = workdir / "export2.webm"
        with page.expect_download(timeout=20000) as dl2:
            page.click("#download")
        dl2.value.save_as(str(out2))
        check(out2.stat().st_size > 15000, "exportul fara sunet are continut", str(out2.stat().st_size) + " B")
        check(b"A_OPUS" not in out2.read_bytes(), "exportul fara sunet nu are pista audio",
              str(out2.stat().st_size) + " B")
        info2 = page.evaluate("() => document.getElementById('download').getAttribute('download')")
        check(info2.endswith(".webm") or info2.endswith(".mp4"), "si exportul mut are extensie", info2)
        check(len(console_errors) == 0, "nici o eroare de consola dupa doua exporturi", console_errors[:2])
        page.uncheck("#mute")

        # ---------------- 6. cadru ca PNG
        print("\n6. Cadru ca PNG")
        with page.expect_download(timeout=15000) as dl:
            page.click("#snapBtn")
        d = dl.value
        frame_path = workdir / "frame.png"
        d.save_as(str(frame_path))
        check(frame_path.stat().st_size > 1000, "cadrul s-a descarcat ca PNG", str(frame_path.stat().st_size) + " B")
        check(frame_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "fisierul e chiar PNG")
        ctx.close()

        # ---------------- 7. ecran mic si tinte de atingere
        print("\n7. Telefon: 320px fara derulare, tinte de 44px")
        for width in (320, 360, 390):
            ctx2 = browser.new_context(viewport={"width": width, "height": 780}, has_touch=True,
                                       device_scale_factor=2, is_mobile=True,
                                       user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                                                  "(KHTML, like Gecko) Chrome/126 Mobile Safari/537.36")
            pg = ctx2.new_page()
            errs = []
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(url, wait_until="load")
            pg.set_input_files("#file", str(clip))
            pg.wait_for_selector("#editCard:not([hidden])", timeout=10000)
            pg.wait_for_timeout(500)
            over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            check(over <= 1, "%dpx: fara derulare pe orizontala" % width, str(over) + "px")
            small = pg.evaluate("""() => {
              const out = [];
              const sel = 'button, a[href], select, input:not([type=file]), label.check';
              for (const el of document.querySelectorAll(sel)) {
                // regula casei (ca in pwa_44.py): pentru un bifator se masoara eticheta, nu patratelul
                const box = (el.type === 'checkbox' || el.type === 'radio') && el.labels && el.labels[0] ? el.labels[0] : el;
                const r = box.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) continue;
                if (el.closest('[hidden]')) continue;
                const inText = el.closest('p, li, footer, .notes');
                if (inText && el.tagName === 'A') continue;   // exceptia WCAG 2.5.5 pentru legaturi din propozitie
                if (r.height < 43.5 || (el.tagName !== 'OUTPUT' && r.width < 43.5)) {
                  out.push((el.id || el.className || el.tagName) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
                }
              }
              return out;
            }""")
            check(len(small) == 0, "%dpx: toate tintele au cel putin 44px" % width, small[:4])
            check(len(errs) == 0, "%dpx: fara erori de consola" % width, errs[:2])
            ctx2.close()

        # ---------------- 8. limbile
        print("\n8. Cele patru limbi")
        ctx3 = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                                   device_scale_factor=2, is_mobile=True)
        pg = ctx3.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url, wait_until="load")

        valori = pg.eval_on_selector_all("#langSel option", "els => els.map(e => e.value)")
        check(valori == ["en", "ro", "sr", "src"], "comutatorul are exact cele patru limbi", valori)
        check(pg.evaluate("() => document.documentElement.lang") == "en",
              "prima vizita e in engleza, nu dupa limba browserului")
        check(pg.eval_on_selector("#langSel", "e => e.value") == "en", "comutatorul arata engleza")

        # linia de sprijin, regula casei
        sprijin = pg.eval_on_selector_all('footer a[href*="paypal.me" i]', "els => els.map(e => e.href)")
        check(len(sprijin) == 1 and "paypal.me/tekideki" in sprijin[0].lower(),
              "subsolul are linia de sprijin catre PayPal.me/TekiDeki", sprijin)

        INTERZISE = "\u0451\u044a\u044b\u044d\u044e\u044f"   # litere rusesti, interzise in sarba
        LIMBI = [("ro", "ro"), ("sr", "sr"), ("src", "sr-Cyrl"), ("en", "en")]
        texte = {}
        for cod, html_lang in LIMBI:
            pg.select_option("#langSel", cod)
            pg.wait_for_timeout(200)
            h1 = pg.inner_text("h1")
            lede = pg.inner_text(".lede")
            titlu = pg.title()
            desc = pg.eval_on_selector('meta[name="description"]', "e => e.content")
            og = pg.eval_on_selector('meta[property="og:description"]', "e => e.content")
            ld = pg.evaluate("() => JSON.parse(document.getElementById('ldjson').textContent)")
            hl = pg.evaluate("() => document.documentElement.lang")
            butoane = pg.inner_text("#setStart")
            check(hl == html_lang, "%s: <html lang> e %s" % (cod, html_lang), hl)
            check(ld["inLanguage"] == [html_lang], "%s: JSON-LD declara limba" % cod, ld["inLanguage"])
            check(ld["description"] and ld["description"] !=
                  pg.evaluate("() => JSON.parse(document.getElementById('ldjson').textContent).name"),
                  "%s: JSON-LD are descrierea tradusa" % cod, (ld["description"] or "")[:40])
            check(desc and og and titlu.lower().find("video") >= 0,
                  "%s: titlu, descriere si og:description sunt scrise" % cod, titlu[:50])
            check(butoane.strip() != "", "%s: butoanele au text" % cod, butoane)
            if cod in ("sr", "src"):
                gasite = sorted({c for c in (h1 + lede + desc + butoane) if c in INTERZISE})
                check(not gasite, "%s: fara litere rusesti" % cod, gasite)
            texte[cod] = (h1, titlu, desc)
            check(pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth") <= 1,
                  "%s: 390px fara derulare pe orizontala" % cod)

        check(len({v[0] for v in texte.values()}) == 4, "cele patru titluri mari sunt diferite",
              [v[0] for v in texte.values()])
        check(texte["en"][0] != texte["ro"][0] and "video" in texte["en"][0].lower(),
              "intoarcerea pe engleza readuce textul englez", texte["en"][0])

        # alegerea se pastreaza dupa reincarcare (regula casei)
        pg.select_option("#langSel", "ro")
        pg.wait_for_timeout(150)
        pg.reload(wait_until="load")
        pg.wait_for_timeout(200)
        check(pg.eval_on_selector("#langSel", "e => e.value") == "ro",
              "limba aleasa se pastreaza dupa reincarcare", pg.eval_on_selector("#langSel", "e => e.value"))
        check(pg.evaluate("() => document.documentElement.lang") == "ro",
              "dupa reincarcare, <html lang> e tot ro")

        # cea mai lunga limba nu rupe asezarea la 320px
        for cod in ("ro", "sr", "src"):
            pg.select_option("#langSel", cod)
            pg.set_viewport_size({"width": 320, "height": 780})
            pg.wait_for_timeout(200)
            over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            check(over <= 1, "%s: 320px fara derulare pe orizontala" % cod, str(over) + "px")

        check(len(errs) == 0, "schimbarea limbii nu produce erori de consola", errs[:2])
        ctx3.close()

        browser.close()

    if not KEEP:
        for f in workdir.iterdir():
            f.unlink(missing_ok=True)
        workdir.rmdir()
    if httpd:
        httpd.shutdown()

    print("\n%d verificari trecute, %d esuate" % (PASS, FAIL))
    if FAIL:
        print("Probleme:")
        for p in PROBLEMS:
            print("  - " + p)
        return 1
    print("TOATE TESTELE AU TRECUT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
