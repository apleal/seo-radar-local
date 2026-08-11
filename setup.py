#!/usr/bin/env python3
"""SEO Radar Local â€” configuración guiada. Run: python setup.py

Walks you through everything, validates your DataForSEO credentials with a
free API call, and writes .env + data/keywords.json. Re-run any time; it
won't clobber existing sites unless you tell it to.
"""
import base64
import getpass
import json
import pathlib
import re
import secrets
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent
ENV = REPO / ".env"
KEYWORDS = REPO / "data" / "keywords.json"

COUNTRIES = {
    "us": (2840, "en", "United States"), "uk": (2826, "en", "United Kingdom"),
    "gb": (2826, "en", "United Kingdom"), "ca": (2124, "en", "Canada"),
    "au": (2036, "en", "Australia"), "de": (2276, "de", "Germany"),
    "fr": (2250, "fr", "France"), "es": (2724, "es", "España"),
    "it": (2380, "it", "Italy"), "nl": (2528, "nl", "Netherlands"),
    "br": (2076, "pt", "Brazil"), "mx": (2484, "es", "Mexico"),
    "co": (2170, "es", "Colombia"), "ar": (2032, "es", "Argentina"),
    "in": (2356, "en", "India"), "jp": (2392, "ja", "Japan"),
}


def ask(prompt, default=None, required=True, secret=False):
    sfx = f" [{default}]" if default else ""
    while True:
        try:
            v = (getpass.getpass(f"{prompt}{sfx}: ") if secret else input(f"{prompt}{sfx}: ")).strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nConfiguración cancelada â€” nothing was written. Run `python setup.py` again any time.")
        if not v and default is not None:
            return default
        if v or not required:
            return v
        print("  (obligatorio)")


def yes(prompt, default=False):
    d = "Y/n" if default else "y/N"
    v = input(f"{prompt} ({d}): ").strip().lower()
    return v.startswith("y") if v else default


def validate_dfs(login, password):
    """Free call â€” confirms the credentials work and shows remaining balance."""
    auth = "Basic " + base64.b64encode(f"{login}:{password}".encode()).decode()
    req = urllib.request.Request("https://api.dataforseo.com/v3/appendix/user_data",
                                 headers={"Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        money = ((d["tasks"][0]["result"] or [{}])[0].get("money") or {})
        bal = money.get("balance")
        print(f"  âœ“ credenciales válidas" + (f" â€” balance ${bal:,.2f}" if bal is not None else ""))
        return True
    except urllib.error.HTTPError as e:
        print(f"  âœ— DataForSEO rejected those credentials (HTTP {e.code}). "
              "Use the API login + API password from https://app.dataforseo.com/api-access")
        return False
    except Exception as e:
        print(f"  âœ— no se pudo conectar con DataForSEO: {e}")
        return False


def main():
    print("\nâ”â”â” SEO Radar Local Â· setup â”â”â”\n")
    env = {}

    # 1. branding + access key
    brand = ask("Nombre mostrado en la cabecera (Intro = conservar SEO Radar Local)", "SEO Radar Local")
    if brand != "SEO Radar Local":
        env["BRAND_NAME"] = brand
    print("\nLa clave de acceso protege la pantalla de inicio de sesión.")
    env["ACCESS_KEY"] = ask("Clave de acceso", secrets.token_urlsafe(12))
    env["AUTH_SALT"] = secrets.token_hex(8)

    # 2. DataForSEO (the only hard requirement)
    print("\nDataForSEO proporciona posiciones, palabras clave, competidores y mapas.")
    print("Crea una cuenta de pago por uso (el coste depende de las consultas): https://dataforseo.com/")
    while True:
        login = ask("Usuario API de DataForSEO (normalmente tu correo)")
        password = ask("Contraseña API de DataForSEO", secret=True)
        if validate_dfs(login, password):
            break
        print("  Vamos a intentarlo de nuevo.\n")
    env["DATAFORSEO_LOGIN"] = login
    env["DATAFORSEO_PASSWORD"] = password

    # 3. sites
    sites = {}
    if KEYWORDS.exists() and not yes("\ndata/keywords.json ya existe. ¿Quieres sustituirlo?", False):
        sites = None
    if sites is not None:
        print("\nAñade las webs que quieras monitorizar. Podrás añadir más después.")
        while True:
            name = ask("\nNombre de la web (p. ej., Cafetería Acme)")
            domain = ask("Dominio (p. ej., ejemplo.es)").lower()
            domain = re.sub(r"^https?://", "", domain).strip("/").replace("www.", "")
            cc = ask("Código de país (es, us, uk, ca, de, fr, etc.)", "es").lower()
            loc, lang, label = COUNTRIES.get(cc, COUNTRIES["es"])
            print(f"  â†’ Google {label}, language '{lang}'")
            seeds = ask("Palabras clave semilla, separadas por comas (p. ej., posicionamiento local)", required=False)
            entry = {
                "domain": domain,
                "gsc_site": f"https://{domain}/",
                "geo": None,
                "location_code": loc,
                "language_code": lang,
                "seed_keywords": [s.strip() for s in seeds.split(",") if s.strip()],
                "brand_keywords": [name.lower()],
            }
            sites[name] = entry
            if not yes("¿Añadir otra web?", False):
                break

    # 4. optional: hosted mode
    print("\nEl modo alojado publica el panel en Cloudflare Pages y activa")
    print("los botones de actualización, gestión, investigación y mapas.")
    if yes("¿Configurar Cloudflare ahora?", False):
        print("Necesitas el ID de la cuenta (dash.cloudflare.com â†’ any site â†’ barra lateral derecha)")
        print("y un token API con permisos de edición para Pages y Workers KV")
        print("(dash.cloudflare.com/profile/api-tokens â†’ Crear token).")
        env["CF_ACCOUNT_ID"] = ask("ID de cuenta de Cloudflare")
        env["CF_API_TOKEN"] = ask("Token API de Cloudflare", secret=True)
        env["CF_PAGES_PROJECT"] = ask("Nombre del proyecto Pages", "seo-radar-local")

    # 5. optional: Telegram alerts
    if yes("\n¿Configurar alertas de cambios por Telegram?", False):
        print("Crea un bot con @BotFather, envíale un mensaje y obtén el ID del chat")
        print("from https://api.telegram.org/bot<TOKEN>/getUpdates")
        env["TELEGRAM_BOT_TOKEN"] = ask("Token del bot", secret=True)
        env["TELEGRAM_CHAT_ID"] = ask("ID del chat")

    # write
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV.write_text("# SEO Radar Local â€” generated by setup.py (never commit this file)\n"
                   + "\n".join(lines) + "\n")
    print(f"\nâœ“ creado .env")
    if sites is not None:
        KEYWORDS.parent.mkdir(exist_ok=True)
        KEYWORDS.write_text(json.dumps({"track_cap": 100, "brands": sites}, indent=2))
        print(f"âœ“ creado data/keywords.json ({len(sites)} site{'s' if len(sites) != 1 else ''})")

    print("\nâ”â”â” siguientes pasos â”â”â”")
    print("1. python worker.py run all      # primera obtención de datos (~$0.10-0.50 depending on sites)")
    print("2. python worker.py serve        # open http://localhost:8000")
    if env.get("CF_ACCOUNT_ID"):
        print("3. python worker.py deploy-config && python worker.py deploy   # publicar")
        print("4. python worker.py loop       # mantén los datos al día y atiende los botones")
    else:
        print("   (más adelante, vuelve a ejecutar setup para configurar Cloudflare)")
    print()


if __name__ == "__main__":
    main()
