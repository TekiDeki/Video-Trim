# -*- coding: utf-8 -*-
"""test_csp_live.py - regula casei de securitate, aplicata paginii publicate.

Ce verifica: CSP-ul exista si e cel care trebuie, service workerul se inregistreaza, fluxul
intreg (incarcare, export, descarcare, cadru PNG) trece fara nicio violare de CSP, fara erori
de consola si fara cereri in afara paginii, iar pagina se redeschide si fara retea.

    python3 tests/test_csp_live.py
"""
import base64, pathlib, tempfile
from playwright.sync_api import sync_playwright

LIVE = "https://tekideki.github.io/Video-Trim/"
src = open('/home/user/studio/audit-texte/repos/Video-Trim/tests/test_video.py', encoding='utf-8').read()
a = src.index('MAKE_VIDEO = """') + len('MAKE_VIDEO = """'); b = src.index('"""', a)
JS = src[a:b]
ok = bad = 0
def check(c, msg, extra=""):
    global ok, bad
    if c: ok += 1; print("  ok   " + msg)
    else: bad += 1; print("  RAU  " + msg + ((" (" + str(extra) + ")") if extra else ""))

tmp = pathlib.Path(tempfile.mkdtemp()) / "clip.webm"
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    pg = ctx.new_page()
    viol, errs, foreign = [], [], []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    def _req(r):
        u = r.url
        if u.startswith(('blob:', 'data:')) or u.startswith(LIVE.rstrip('/')):
            return
        foreign.append(u)
    pg.on("request", _req)
    pg.add_init_script("""
      window.__v = [];
      document.addEventListener('securitypolicyviolation', e => {
        window.__v.push(e.violatedDirective + ' <- ' + e.blockedURI);
      });
    """)
    pg.goto(LIVE, wait_until="load")
    pg.wait_for_timeout(800)

    csp = pg.evaluate("() => document.querySelector('meta[http-equiv=\"Content-Security-Policy\"]')?.content || ''")
    check("default-src 'self'" in csp, "pagina publicata are CSP prin meta", csp[:60])
    check("object-src 'none'" in csp and "base-uri 'self'" in csp, "CSP are object-src none si base-uri self")
    check("worker-src 'self' blob:" in csp, "CSP lasa workerul sa se inregistreze (are service worker)")

    sw = pg.evaluate("""async () => {
      if (!('serviceWorker' in navigator)) return 'fara suport';
      const r = await navigator.serviceWorker.getRegistration();
      if (!r) return 'neinregistrat';
      await navigator.serviceWorker.ready;
      return (r.active ? 'activ' : 'in curs') + ' / ' + (r.scope || '');
    }""")
    check(sw.startswith("activ"), "service workerul s-a inregistrat si e activ", sw)

    tmp.write_bytes(base64.b64decode(pg.evaluate(JS, 3.0)))
    pg.set_input_files("#file", str(tmp))
    pg.wait_for_selector("#editCard:not([hidden])", timeout=15000)
    pg.wait_for_function("() => document.getElementById('exportBtn').disabled === false", timeout=15000)
    pg.evaluate("([i,v]) => { const e=document.getElementById(i); e.value=String(v); e.dispatchEvent(new Event('input',{bubbles:true})); }", ["start", 0.4])
    pg.evaluate("([i,v]) => { const e=document.getElementById(i); e.value=String(v); e.dispatchEvent(new Event('input',{bubbles:true})); }", ["end", 1.4])
    pg.click("#exportBtn")
    pg.wait_for_selector("#result.on", timeout=90000)
    check(pg.evaluate("() => document.getElementById('download').href.slice(0,5)") == "blob:", "exportul a produs un blob local")
    with pg.expect_download(timeout=20000) as dl:
        pg.click("#download")
    f = tmp.parent / "out.webm"; dl.value.save_as(str(f))
    check(f.stat().st_size > 20000, "descarcarea trece de CSP (blob:)", str(f.stat().st_size) + " B")
    with pg.expect_download(timeout=15000) as dl2:
        pg.click("#snapBtn")
    check(True, "cadrul PNG se descarca")

    v = pg.evaluate("() => window.__v")
    check(len(v) == 0, "nici o violare de CSP pe tot fluxul", v[:4])
    check(len(errs) == 0, "nici o eroare de consola", errs[:3])
    check(len(foreign) == 0, "nici o cerere in afara paginii", foreign[:3])

    # offline dupa prima vizita (service workerul serveste din cache)
    pg.context.set_offline(True)
    pg.reload(wait_until="load")
    pg.wait_for_timeout(600)
    h1 = pg.inner_text("h1")
    check("Cut a video" in h1 or "Taie un video" in h1, "pagina se deschide si fara retea", h1[:40])
    pg.context.set_offline(False)
    br.close()
print("\n%d verificari trecute, %d esuate" % (ok, bad))
