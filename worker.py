#!/usr/bin/env python3
"""SEO Radar Local worker — runs trackers, polls the dashboard queue, deploys.

Commands:
  python worker.py run <tool>        run one tool now (rankings | research-page |
                                     competitors | ai-visibility | site-health |
                                     link-gap | map-grid | all)
  python worker.py render            re-render every page from stored data (free)
  python worker.py serve [port]      local mode — serve the dashboard at localhost:8000
  python worker.py deploy            deploy the site to Cloudflare Pages (hosted mode)
  python worker.py deploy-config     push ACCESS_KEY + DataForSEO secrets + KV binding
                                     to the Pages project (one-time, after setup.py)
  python worker.py loop              hosted mode — poll the refresh/manage queue every
                                     2 min and auto-run the daily refresh (put this in
                                     cron / launchd / a systemd timer, or just leave a
                                     terminal running)

Local mode needs nothing but DataForSEO credentials. Hosted mode (self-serve
refresh buttons, keyword management and live research from the browser) needs a
free Cloudflare account — see README.
"""
import datetime
import hashlib
import hmac
import http.server
import html
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "tracker"))
import config  # noqa: E402

TOOLS = {
    "rankings": [("rank_tracker.py", ["both", "--skip-geo"]), ("alerts.py", [])],
    "rankings-full": [("rank_tracker.py", ["both"]), ("alerts.py", [])],
    "research-page": [("research_page.py", [])],
    "explorer-page": [("explorer_page.py", [])],
    "competitors": [("competitor_gap.py", [])],
    "ai-visibility": [("ai_visibility.py", [])],
    "site-health": [("site_audit.py", [])],
    "link-gap": [("link_gap.py", [])],
    "map-grid": [("geogrid.py", ["both"])],
}
PAGES = {  # rendered file -> site path
    "dashboard.html": "index.html",
    "research.html": "research.html",
    "explorer.html": "explorer.html",
    "competitors.html": "competitors.html",
    "ai-visibility.html": "ai-visibility.html",
    "site-health.html": "site-health.html",
    "link-gap.html": "link-gap.html",
    "map-grid.html": "map-grid.html",
}

PAGE_ROUTES = {
    "/": "/index.html",
    "/research": "/research.html",
    "/explorer": "/explorer.html",
    "/competitors": "/competitors.html",
    "/ai-visibility": "/ai-visibility.html",
    "/site-health": "/site-health.html",
    "/link-gap": "/link-gap.html",
    "/map-grid": "/map-grid.html",
}

_job_lock = threading.Lock()
_running_jobs = set()


def run_tool(name):
    steps = TOOLS.get(name)
    if not steps:
        raise SystemExit(f"unknown tool '{name}' — one of: {', '.join(TOOLS)}, all")
    for script, args in steps:
        print(f"→ {script} {' '.join(args)}", flush=True)
        r = subprocess.run([sys.executable, str(REPO / "tracker" / script), *args])
        if r.returncode != 0:
            raise SystemExit(r.returncode)  # the tool already printed why


def render_all():
    for script, args in [("rank_tracker.py", ["render"]), ("research_page.py", []),
                         ("explorer_page.py", []),
                         ("competitor_gap.py", ["render"]), ("ai_visibility.py", ["render"]),
                         ("site_audit.py", ["render"]), ("link_gap.py", ["render"]),
                         ("geogrid.py", ["render"])]:
        try:
            subprocess.run([sys.executable, str(REPO / "tracker" / script), *args], check=True)
        except subprocess.CalledProcessError:
            print(f"  ({script} skipped — no data yet)", flush=True)
    copy_pages()


def copy_pages():
    for src, dst in PAGES.items():
        f = config.DATA / src
        if f.exists():
            shutil.copy(f, config.SITE / dst)


def _auth_token(password, salt):
    return hashlib.sha256(f"{password}|{salt}".encode()).hexdigest()


def _login_page(brand, error=False):
    brand = html.escape(brand)
    error_html = '<p class="error">Clave incorrecta.</p>' if error else ""
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acceso · {brand}</title><style>
*{{box-sizing:border-box}}body{{background:#08080b;color:#f5f5f5;font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0}}
.card{{width:min(420px,calc(100% - 32px));padding:34px;border:1px solid #303038;border-radius:16px;background:#101014}}
h1{{margin:0 0 8px;color:#ff7a2e}}p{{color:#aaa}}label{{display:block;margin:24px 0 8px}}
input,button{{width:100%;padding:12px;border-radius:8px;font:inherit}}input{{background:#08080b;color:#fff;border:1px solid #444}}
button{{margin-top:14px;background:#ff7a2e;color:#16100c;border:0;font-weight:800;cursor:pointer}}.error{{color:#ff6b6b}}
</style></head><body><main class="card"><h1>{brand}</h1><p>Acceso solo autorizado</p>
<form method="post" action="/login"><label for="password">Clave de acceso</label>
<input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
{error_html}<button type="submit">Entrar</button></form></main></body></html>'''.encode()


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve exclusivamente el directorio publico, con autenticacion local."""
    access_key = ""
    auth_salt = "seo-radar-local"
    brand_name = "SEO Radar Local"

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404, "No encontrado")
        return None

    def _authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return False
        value = cookie.get("rt_auth")
        if not value:
            return False
        expected = _auth_token(self.access_key, self.auth_salt)
        return hmac.compare_digest(value.value, expected)

    def _send_login(self, error=False):
        body = _login_page(self.brand_name, error)
        self.send_response(401 if error else 200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _run_background(tool):
        try:
            if tool == "all":
                for name in TOOLS:
                    if name not in {"rankings-full"}:
                        run_tool(name)
            else:
                run_tool(tool)
            render_all()
        except BaseException as error:
            print(f"Actualización {tool} fallida: {error}", flush=True)
        finally:
            with _job_lock:
                _running_jobs.discard(tool)

    def _queue_refresh(self, tool):
        allowed = {"rankings", "competitors", "ai-visibility", "site-health", "link-gap", "map-grid", "all"}
        if tool not in allowed:
            self._json({"ok": False, "error": "herramienta desconocida"}, 400)
            return
        with _job_lock:
            if tool in _running_jobs or "all" in _running_jobs:
                self._json({"ok": True, "queued": tool, "running": True})
                return
            _running_jobs.add(tool)
        threading.Thread(target=self._run_background, args=(tool,), daemon=True).start()
        self._json({"ok": True, "queued": tool, "running": True, "used": 1, "limit": 2})

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            body = json.dumps({"status": "ok", "service": "seo-radar-local"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/logout":
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "rt_auth=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/login":
            if self._authenticated():
                self._redirect("/")
            else:
                self._send_login()
            return
        if not self._authenticated():
            self._redirect("/login")
            return
        if path in PAGE_ROUTES:
            self.path = PAGE_ROUTES[path]
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/refresh":
            if not self._authenticated():
                self._json({"ok": False, "error": "no autorizado"}, 401)
                return
            tool = (urllib.parse.parse_qs(parsed.query).get("tool") or [""])[0]
            self._queue_refresh(tool)
            return
        if parsed.path != "/login":
            self.send_error(404, "No encontrado")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            self.send_error(400, "Solicitud no valida")
            return
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        supplied = (form.get("password") or [""])[0]
        if not hmac.compare_digest(supplied, self.access_key):
            self._send_login(error=True)
            return
        token = _auth_token(self.access_key, self.auth_salt)
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", f"rt_auth={token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000")
        self.send_header("Content-Length", "0")
        self.end_headers()


def _empty_page():
    target = config.SITE / "index.html"
    if not target.exists() or target.stat().st_size == 0:
        target.write_text('''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SEO Radar Local</title><style>body{background:#08080b;color:#fff;font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0}.box{max-width:620px;padding:36px;border:1px solid #333;border-radius:16px}h1{color:#ff7a2e}</style></head><body><main class="box"><h1>SEO Radar Local</h1><p>Todavia no hay ninguna web configurada.</p><p>Ejecuta <code>python setup.py</code> y despues <code>python worker.py run all</code>.</p></main></body></html>''', encoding="utf-8")

def serve(port=None):
    port = int(port if port is not None else os.environ.get("PORT", "8000"))
    DashboardHandler.access_key = config.require("ACCESS_KEY", "Configuralo como secreto en Easypanel.")
    DashboardHandler.auth_salt = config.env("AUTH_SALT", "seo-radar-local")
    DashboardHandler.brand_name = config.brand_name()
    render_all()
    _empty_page()
    import functools
    handler = functools.partial(DashboardHandler, directory=str(config.SITE))
    print(f"SEO Radar Local disponible en 0.0.0.0:{port} (Ctrl-C para detener)")
    print("Panel protegido con ACCESS_KEY. Algunas acciones aun requieren la consola.")
    http.server.ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()


def _cf():
    cf = config.cloudflare()
    if not cf:
        raise SystemExit("El modo alojado no está configurado — set CF_ACCOUNT_ID and CF_API_TOKEN in .env "
                         "(or use `python worker.py serve` for local mode).")
    return cf


def deploy():
    cf = _cf()
    copy_pages()
    env = dict(**__import__("os").environ,
               CLOUDFLARE_ACCOUNT_ID=cf["account_id"], CLOUDFLARE_API_TOKEN=cf["api_token"])
    subprocess.run(["npx", "wrangler", "pages", "deploy", str(config.SITE),
                    f"--project-name={cf['project']}", "--branch=main", "--commit-dirty=true"],
                   check=True, env=env)


def _cf_api(cf, path, method="GET", body=None):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {cf['api_token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def deploy_config():
    """One-time: create the Pages project + KV namespace if needed, push secrets."""
    cf = _cf()
    acct = cf["account_id"]
    # ensure project exists
    try:
        _cf_api(cf, f"/accounts/{acct}/pages/projects/{cf['project']}")
    except urllib.error.HTTPError:
        print(f"Creating Pages project '{cf['project']}'…")
        _cf_api(cf, f"/accounts/{acct}/pages/projects", "POST",
                {"name": cf["project"], "production_branch": "main"})
    # ensure KV namespace
    ns = cf.get("kv_namespace")
    if not ns:
        r = _cf_api(cf, f"/accounts/{acct}/storage/kv/namespaces", "POST",
                    {"title": f"{cf['project']}-queue"})
        ns = r["result"]["id"]
        with open(REPO / ".env", "a") as f:
            f.write(f"\nCF_KV_NAMESPACE={ns}\n")
        print(f"Created KV namespace {ns} (saved to .env)")
    # push env vars + KV binding
    payload = {"deployment_configs": {"production": {
        "env_vars": {
            "ACCESS_KEY": {"type": "secret_text", "value": config.require("ACCESS_KEY")},
            "AUTH_SALT": {"type": "secret_text", "value": config.env("AUTH_SALT", "seo-command-center")},
            "BRAND_NAME": {"type": "plain_text", "value": config.brand_name()},
            "DFS_LOGIN": {"type": "secret_text", "value": config.require("DATAFORSEO_LOGIN")},
            "DFS_PASSWORD": {"type": "secret_text", "value": config.require("DATAFORSEO_PASSWORD")},
        },
        "kv_namespaces": {"REFRESH_KV": {"namespace_id": ns}},
    }}}
    _cf_api(cf, f"/accounts/{acct}/pages/projects/{cf['project']}", "PATCH", payload)
    print("✓ Pages project configured (access key, DataForSEO secrets, queue binding).")
    print("Now run: python worker.py run all && python worker.py deploy")


def _kv(cf, path, method="GET", data=None):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{cf['account_id']}/storage/kv/namespaces/{cf['kv_namespace']}{path}",
        data=data, method=method, headers={"Authorization": f"Bearer {cf['api_token']}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def loop():
    cf = _cf()
    if not cf.get("kv_namespace"):
        raise SystemExit("Falta CF_KV_NAMESPACE en .env — ejecuta primero `python worker.py deploy-config`.")
    run_hour = int(config.env("DAILY_REFRESH_HOUR", "6"))
    last_daily = None
    print(f"Consultando la cola cada 120 s; actualización diaria a las {run_hour:02d}:00. Ctrl-C to stop.")
    while True:
        try:
            # 1. apply keyword/domain management ops queued from the dashboard
            r = subprocess.run([sys.executable, str(REPO / "tracker" / "manage_apply.py")])
            pending = []
            if r.returncode == 10:
                pending.append("rankings")
            # 2. requested refreshes — single "queue" key, not /keys?prefix=
            # (KV free tier caps list ops at 1,000/day; reads at 100,000/day)
            try:
                queued = _kv(cf, "/values/queue")
            except urllib.error.HTTPError:
                queued = {}
            pending += list(queued)
            # 3. daily refresh
            now = datetime.datetime.now()
            if now.hour == run_hour and last_daily != now.date():
                pending.append("rankings-full" if now.weekday() == 0 else "rankings")
                last_daily = now.date()
            if pending:
                print(f"[{now:%F %T}] running: {', '.join(dict.fromkeys(pending))}", flush=True)
                for tool in dict.fromkeys(pending):
                    try:
                        run_tool(tool if tool in TOOLS else "rankings")
                    except SystemExit as e:
                        print(f"  {tool} failed (exit {e.code})", flush=True)
                    _kv(cf, f"/values/last:{tool}", "PUT", f"{now:%F %T}".encode())
                # clear processed tools from the queue, keeping any queued mid-run
                try:
                    q = _kv(cf, "/values/queue")
                except urllib.error.HTTPError:
                    q = {}
                for tool in pending:
                    q.pop(tool, None)
                _kv(cf, "/values/queue", "PUT", json.dumps(q).encode())
                render_all()
                deploy()
        except Exception as e:
            print(f"error del bucle (nuevo intento en 120 s): {e}", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "run":
        target = sys.argv[2] if len(sys.argv) > 2 else "all"
        for t in (list(TOOLS) if target == "all" else [target]):
            if t == "rankings-full":
                continue
            run_tool(t)
        copy_pages()
    elif cmd == "render":
        render_all()
    elif cmd == "serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "deploy":
        render_all()
        deploy()
    elif cmd == "deploy-config":
        deploy_config()
    elif cmd == "loop":
        loop()
    else:
        print(__doc__)
