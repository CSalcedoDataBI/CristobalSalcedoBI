#!/usr/bin/env python3
"""Genera el README del perfil CSalcedoDataBI/CSalcedoDataBI.

Rellena los bloques marcados del README y dibuja la tarjeta de estadisticas.
Sin dependencias: solo biblioteca estandar. Sin servicios de terceros: todo
sale de la API de GitHub y del RSS del sitio.

Uso:  GITHUB_TOKEN=... python3 update_profile.py [--readme README.md]

Si una fuente falla, su bloque se deja INTACTO y el script termina en 1.
Nunca se publica una seccion vacia por un fallo de red.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

OWNER = "CSalcedoDataBI"
SITE = "https://csalcedodatabi.com"
RSS_URL = f"{SITE}/rss.xml"
GALLERY_REPO = "PowerBI-Deneb"

MAX_POSTS = 5
MAX_TEMPLATES = 5
MAX_RELEASES = 5
MAX_RELEASES_POR_REPO = 2  # que la columna no sea el changelog de un solo repo

# Agrupacion editorial de los repos publicos. El orden manda.
REPO_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Visualización avanzada — Deneb / Vega",
        [
            ("PowerBI-Deneb", "Plantillas Deneb listas para copiar en tus informes de Power BI."),
        ],
    ),
    (
        "Microsoft Fabric y agentes de datos",
        [
            ("fabric-data-agents",
             "Cómo construir e instruir un Fabric Data Agent, medido y reproducible."),
            ("fabric-app-gallery",
             "Plantillas de Microsoft Fabric Apps listas para ejecutar y adaptar."),
        ],
    ),
    (
        "Herramientas y automatización",
        [
            ("agentic-board",
             "Coordinador de agentes de código sobre un board real de GitHub Projects."),
            ("powerbi-pbip-tools", "Automatización de proyectos Power BI en formato PBIP."),
        ],
    ),
    (
        "Datos y retos",
        [
            ("SampleDataSets", "Conjuntos de datos de muestra para pruebas, aprendizaje y demos."),
            ("BI_Challenges", "Soluciones a retos de la comunidad BI en PySpark, Python y M."),
            ("ubl-star", "De factura electrónica UBL 2.1 a un modelo dimensional analizable."),
        ],
    ),
]

# Paleta Fabric flow — identica a src/styles/global.css del sitio.
THEMES = {
    "light": {
        "bg0": "#FFFFFF", "bg1": "#E8F2EF", "text": "#0B1A17",
        "muted": "#44544F", "accent": "#116B62", "border": "#CFE3DD",
        "g0": "#0d9488", "g1": "#0ea5e9",
    },
    "dark": {
        "bg0": "#08110F", "bg1": "#17241F", "text": "#E4F0EC",
        "muted": "#93A8A2", "accent": "#72EBC4", "border": "#263B35",
        "g0": "#72EBC4", "g1": "#38BDF8",
    },
}

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
UA = "csalcedodatabi-profile-updater"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("falta GITHUB_TOKEN en el entorno")
    return tok


def http_get(url: str, *, auth: bool = True, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    if auth:
        req.add_header("Authorization", f"Bearer {_token()}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def rest(path: str) -> object:
    return json.loads(http_get(f"{API}{path}"))


def rest_paged(path: str) -> tuple[object, str]:
    """Devuelve (json, cabecera Link) para poder saltar a la ultima pagina."""
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "User-Agent": UA,
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_token()}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()), resp.headers.get("Link", "")


def graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPHQL, data=body,
        headers={
            "User-Agent": UA,
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(f"GraphQL: {payload['errors']}")
    return payload["data"]


def es_date(iso: str) -> str:
    """2026-08-12T… -> 12 ago 2026"""
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d.day} {meses[d.month - 1]} {d.year}"


# --------------------------------------------------------------------------
# Fuentes
# --------------------------------------------------------------------------

def collect_posts() -> list[str]:
    """Ultimos articulos del blog, desde el RSS del sitio."""
    raw = http_get(RSS_URL, auth=False, accept="application/xml")
    root = ET.fromstring(raw)
    items = root.findall("./channel/item")
    if not items:
        raise RuntimeError("el RSS no trajo items")

    lines = []
    for item in items[:MAX_POSTS]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        try:
            fecha = es_date(parsedate_to_datetime(pub).isoformat())
        except (TypeError, ValueError):
            fecha = ""
        if not link.startswith("http"):
            link = f"{SITE}{link}"
        sufijo = f" — {fecha}" if fecha else ""
        lines.append(f"[{title}]({link}){sufijo}")
    return lines


def fecha_de_alta(repo: str, carpeta: str) -> str | None:
    """Fecha del PRIMER commit de una carpeta, no del ultimo.

    Sin esto, un commit masivo (una licencia, un README) reordena la galeria
    entera y todas las plantillas parecen nuevas el mismo dia.
    """
    ruta = urllib.parse.quote(carpeta)
    base = f"/repos/{OWNER}/{repo}/commits?path={ruta}&per_page=1"
    commits, link = rest_paged(base)
    if not commits:
        return None
    ultima = re.search(r'[?&]page=(\d+)>; rel="last"', link)
    if ultima:
        commits, _ = rest_paged(f"{base}&page={ultima.group(1)}")
        if not commits:
            return None
    return commits[0]["commit"]["committer"]["date"]


def collect_templates() -> list[str]:
    """Plantillas de la galeria, de la mas reciente a la mas antigua."""
    tree = rest(f"/repos/{OWNER}/{GALLERY_REPO}/contents")
    dirs = [e["name"] for e in tree if e["type"] == "dir"]
    if not dirs:
        raise RuntimeError("la galeria no tiene carpetas")

    fechas: list[tuple[str, str]] = []
    for name in dirs:
        alta = fecha_de_alta(GALLERY_REPO, name)
        if alta:
            fechas.append((alta, name))

    fechas.sort(reverse=True)
    lines = []
    for iso, name in fechas[:MAX_TEMPLATES]:
        titulo = name.replace("_", " ").strip()
        url = f"https://github.com/{OWNER}/{GALLERY_REPO}/tree/main/{urllib.parse.quote(name)}"
        lines.append(f"[{titulo}]({url}) — {es_date(iso)}")
    return lines


def collect_releases(repos: list[dict]) -> list[str]:
    """Ultimas versiones publicadas en cualquier repo publico."""
    todas: list[tuple[str, str]] = []
    for repo in repos:
        try:
            rels = rest(f"/repos/{OWNER}/{repo['name']}/releases?per_page=10")
        except urllib.error.HTTPError:
            continue
        publicadas = [
            r for r in rels if not r.get("draft") and r.get("published_at")
        ][:MAX_RELEASES_POR_REPO]
        for rel in publicadas:
            etiqueta = rel.get("tag_name") or rel.get("name") or ""
            todas.append((
                rel["published_at"],
                f"[{repo['name']} {etiqueta}]({rel['html_url']}) — {es_date(rel['published_at'])}",
            ))
    if not todas:
        raise RuntimeError("ningun repo publico tiene releases")
    todas.sort(reverse=True)
    return [linea for _, linea in todas[:MAX_RELEASES]]


def collect_account() -> tuple[dict, list[dict]]:
    """Datos del perfil y de sus repos publicos, en una sola consulta.

    OJO con el token: `contributionsCollection` devuelve lo que el token puede
    ver. Con el GITHUB_TOKEN del workflow salen las contribuciones PUBLICAS,
    que es justo lo que debe anunciar un perfil publico. Si ejecutas esto en
    local con un PAT personal amplio, los commits y PRs saldran MUY inflados
    porque incluyen los repos privados: no compares ambas cifras.
    """
    query = """
    query($login: String!) {
      user(login: $login) {
        followers { totalCount }
        repositories(first: 100, privacy: PUBLIC, isFork: false,
                     ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
          totalCount
          nodes { name stargazerCount description }
        }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
        }
      }
    }"""
    user = graphql(query, {"login": OWNER})["user"]
    repos = user["repositories"]["nodes"]
    cuenta = {
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "prs": user["contributionsCollection"]["totalPullRequestContributions"],
    }
    return cuenta, repos


def render_repos(repos: list[dict]) -> list[str]:
    """Tabla de repos agrupada por linea de trabajo, con estrellas reales."""
    estrellas = {r["name"]: r["stargazerCount"] for r in repos}
    out: list[str] = []
    for titulo, entradas in REPO_GROUPS:
        out.append(f"**{titulo}**")
        out.append("")
        for nombre, desc in entradas:
            if nombre not in estrellas:
                continue  # repo privado o renombrado: no lo anunciamos
            marca = f" · ★ {estrellas[nombre]}" if estrellas[nombre] else ""
            out.append(f"- [{nombre}](https://github.com/{OWNER}/{nombre}) — {desc}{marca}")
        out.append("")
    return out


# --------------------------------------------------------------------------
# Tarjeta de estadisticas
# --------------------------------------------------------------------------

def render_stats_svg(cuenta: dict, theme: str) -> str:
    c = THEMES[theme]
    celdas = [
        ("Repos públicos", cuenta["repos"]),
        ("Estrellas", cuenta["stars"]),
        ("Commits (12 meses)", cuenta["commits"]),
        ("Pull requests", cuenta["prs"]),
        ("Seguidores", cuenta["followers"]),
    ]
    ahora = es_date(datetime.now(timezone.utc).isoformat())
    ancho, alto = 860, 190
    paso = (ancho - 96) / len(celdas)

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" '
        f'width="{ancho}" height="{alto}" role="img" '
        f'aria-label="Estadisticas publicas de {OWNER}">',
        "<defs>",
        f'<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{c["bg0"]}"/>'
        f'<stop offset="100%" stop-color="{c["bg1"]}"/></linearGradient>',
        f'<linearGradient id="rule" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{c["g0"]}"/>'
        f'<stop offset="100%" stop-color="{c["g1"]}" stop-opacity="0.15"/></linearGradient>',
        "</defs>",
        f'<rect x="0.5" y="0.5" width="{ancho - 1}" height="{alto - 1}" rx="14" '
        f'fill="url(#bg)" stroke="{c["border"]}"/>',
        f'<rect x="14" y="1" width="{ancho - 28}" height="3" fill="url(#rule)"/>',
        '<g font-family="ui-sans-serif,-apple-system,BlinkMacSystemFont,Segoe UI,'
        'Roboto,Helvetica,Arial,sans-serif">',
        f'<text x="48" y="56" font-size="19" font-weight="700" fill="{c["text"]}">'
        f"Actividad pública</text>",
        f'<text x="48" y="80" font-size="14" fill="{c["muted"]}">'
        f"Generado desde la API de GitHub · actualizado {ahora}</text>",
    ]
    for i, (etiqueta, valor) in enumerate(celdas):
        x = 48 + paso * i
        partes.append(
            f'<text x="{x:.0f}" y="140" font-size="38" font-weight="700" '
            f'fill="{c["accent"]}">{valor}</text>'
        )
        partes.append(
            f'<text x="{x:.0f}" y="164" font-size="13" fill="{c["muted"]}">{etiqueta}</text>'
        )
    partes.append("</g></svg>")
    return "\n".join(partes) + "\n"


# --------------------------------------------------------------------------
# Sustitucion de bloques
# --------------------------------------------------------------------------

def replace_block(texto: str, nombre: str, lineas: list[str]) -> str:
    inicio, fin = f"<!-- {nombre}:start -->", f"<!-- {nombre}:end -->"
    patron = re.compile(
        re.escape(inicio) + r".*?" + re.escape(fin), re.DOTALL
    )
    if not patron.search(texto):
        raise RuntimeError(f"no encuentro los marcadores de '{nombre}' en el README")
    cuerpo = "\n".join(lineas)
    return patron.sub(f"{inicio}\n{cuerpo}\n{fin}", texto)


def as_list(lineas: list[str]) -> list[str]:
    return [f"- {linea}" for linea in lineas]


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--assets", default="profile")
    args = ap.parse_args()

    with open(args.readme, encoding="utf-8") as fh:
        readme = fh.read()

    fallos: list[str] = []

    try:
        cuenta, repos = collect_account()
    # A proposito: da igual por que fallo (red, token, esquema). Sin esta
    # consulta no hay ni repos ni tarjeta, asi que se aborta sin tocar nada.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        print(f"ERROR: no pude leer la cuenta: {exc}", file=sys.stderr)
        return 1

    bloques = {
        "blog": lambda: as_list(collect_posts()),
        "plantillas": lambda: as_list(collect_templates()),
        "releases": lambda: as_list(collect_releases(repos)),
        "repos": lambda: render_repos(repos),
    }

    for nombre, recolectar in bloques.items():
        try:
            readme = replace_block(readme, nombre, recolectar())
            print(f"ok    {nombre}")
        # A proposito: cualquier fallo de UN bloque deja ese bloque intacto y
        # el resto sigue. Es lo que evita publicar una seccion vacia.
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            fallos.append(f"{nombre}: {exc}")
            print(f"AVISO {nombre} sin tocar — {exc}", file=sys.stderr)

    os.makedirs(args.assets, exist_ok=True)
    for tema in THEMES:
        destino = os.path.join(args.assets, f"stats-{tema}.svg")
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(render_stats_svg(cuenta, tema))
        print(f"ok    {destino}")

    with open(args.readme, "w", encoding="utf-8") as fh:
        fh.write(readme)

    if fallos:
        print("\nBloques no actualizados:\n  " + "\n  ".join(fallos), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
