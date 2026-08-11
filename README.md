# SEO Radar Local

SEO Radar Local es una plataforma SEO autohospedada para consultar posiciones, investigar palabras clave, analizar competidores, revisar visibilidad en IA, salud técnica, oportunidades de enlaces y mapas de visibilidad local. Esta adaptación está orientada a Google España y al castellano.

Es un fork de [SEO Command Center](https://github.com/testedmedia/seo-command-center). Conserva su arquitectura ligera basada en la biblioteca estándar de Python, SQLite y páginas HTML estáticas. No es un producto oficial de Google y los rankings son observaciones de resultados, no una garantía de exactitud absoluta.

## Funciones principales

- Posiciones orgánicas, históricos y exportación CSV.
- Palabras clave y análisis de competidores.
- Explorador de sitios, visibilidad en IA y salud SEO.
- Oportunidades de enlaces y mapa de visibilidad local.
- Datos bajo tu control en `data/ranks.db` y ficheros auxiliares de `data/`.

## Requisitos

- Python 3.12 recomendado, o Docker.
- Cuenta de DataForSEO para obtener datos reales. El coste depende del número y la frecuencia de consultas; consulta siempre sus precios actuales.
- Google Search Console es opcional y se puede conectar más adelante.
- Cloudflare es opcional y solo se necesita actualmente para las acciones interactivas descritas más abajo.

## Demostración sin API

No hace llamadas de pago:

```bash
python3 demo.py
python3 worker.py serve
```

Abre `http://localhost:8000`. `demo.py` no sobrescribe una base existente salvo que se indique `--force`.

## Instalación local

```bash
git clone https://github.com/apleal/seo-radar-local.git
cd seo-radar-local
python3 setup.py
python3 worker.py run all
python3 worker.py serve
```

`setup.py` crea `.env` y `data/keywords.json`. España (`es`, location code `2724`, idioma `es`) es la opción predeterminada, aunque se conservan otros países. La primera actualización usa DataForSEO y puede generar costes.

## Docker

```bash
docker build -t seo-radar-local .
docker run --rm -p 8000:8000 -v seo-radar-data:/app/data seo-radar-local
```

Para una prueba local también puedes usar `docker compose up --build`. El contenedor usa Python 3.12, un usuario sin privilegios, escucha en `0.0.0.0` y expone `/health` sin consultar APIs externas.

## Despliegue en Easypanel

Configura el servicio con estos valores:

- Tipo de servicio: App.
- Fuente: GitHub.
- Repositorio: `apleal/seo-radar-local`.
- Rama: `main` después de fusionar el PR.
- Build path: `/`.
- Builder: Dockerfile.
- Dockerfile path: `Dockerfile`.
- Puerto interno: `8000`.
- Volumen persistente: `/app/data`.
- Dominio: configurado desde Easypanel.
- HTTPS: gestionado por Easypanel.

En el primer arranque el volumen puede estar vacío: el servidor mostrará una explicación en vez de bloquearse. Abre la terminal del servicio en Easypanel y ejecuta:

```bash
python setup.py
python worker.py run all
```

Después reinicia el servicio o ejecuta `python worker.py render`. Protege el dominio con autenticación en Easypanel o en otro proxy de confianza: el servidor Python está pensado para un panel interno detrás del proxy, no para exposición pública sin autenticación.

## Variables de entorno

| Variable | Uso |
|---|---|
| `DATAFORSEO_LOGIN` | Usuario API de DataForSEO para datos reales |
| `DATAFORSEO_PASSWORD` | Contraseña API de DataForSEO |
| `ACCESS_KEY` | Clave del login en Cloudflare Pages |
| `AUTH_SALT` | Sal aleatoria del login de Cloudflare |
| `BRAND_NAME` | Marca visible; por defecto SEO Radar Local |
| `LOGO_FILE` | Ruta opcional a un SVG propio |
| `PORT` | Puerto interno; por defecto 8000 |
| `DAILY_REFRESH_HOUR` | Hora local de actualización; por defecto 6 |
| `GSC_CLIENT_SECRET` | Ruta al secreto OAuth opcional |
| `GSC_TOKENS` | Ruta a los tokens OAuth opcionales |
| `TELEGRAM_BOT_TOKEN` | Token opcional para alertas |
| `TELEGRAM_CHAT_ID` | Chat opcional para alertas |

Añade los secretos como variables protegidas de Easypanel. No los escribas en la imagen, el repositorio ni el HTML.

## Persistencia y copias de seguridad

Crea siempre un volumen en `/app/data`; contiene SQLite, configuración, cachés, cuadrículas, resultados e informes persistentes. Crea `/app/credentials` solamente al conectar Search Console o montar un logotipo privado. Haz copias periódicas del volumen con el servicio detenido o mediante una copia coherente de SQLite, y prueba la restauración.

## Cloudflare y modo de lectura

El despliegue directo en Easypanel sirve correctamente todas las páginas en modo lectura. Los botones de actualizar, añadir/eliminar webs o palabras clave, investigación en vivo y configuración de mapas dependen actualmente de `site/functions`, Cloudflare Pages, KV y el proceso `worker.py loop`. Esas funciones se conservan, pero no se han reconstruido como backend Python. No configures tokens de Cloudflare si solo necesitas lectura.

## Search Console

Cuando quieras activarlo, monta `/app/credentials` y define:

```dotenv
GSC_CLIENT_SECRET=/app/credentials/gsc-client-secret.json
GSC_TOKENS=/app/credentials/gsc-tokens.json
```

No publiques esos ficheros.

## Actualizaciones y proyecto original

Para incorporar cambios del proyecto original, añade un remoto `upstream`, revisa los cambios en una rama separada y resuelve con cuidado las diferencias de idioma, Docker y rutas persistentes antes de fusionar. Conserva la licencia y prueba `demo.py`, el render y el servidor después de cada actualización.

## Licencia

MIT. Consulta [LICENSE](LICENSE). Esta adaptación mantiene los avisos del proyecto original.

## Aviso de costes

Las consultas reales de posiciones, investigación, competidores y mapas consumen saldo de DataForSEO. El coste varía con el volumen, profundidad y frecuencia. La demo y `/health` no realizan llamadas a DataForSEO.
