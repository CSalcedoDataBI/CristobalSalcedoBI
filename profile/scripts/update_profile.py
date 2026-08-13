#!/usr/bin/env python3
"""Genera el README del perfil CSalcedoDataBI/CSalcedoDataBI.

Rellena los bloques marcados del README. Sin dependencias: solo biblioteca
estandar. Sin servicios de terceros: todo sale de la API de GitHub y del RSS
del sitio.

Uso:  GITHUB_TOKEN=... python3 update_profile.py [--readme README.md]

Todo lo que escribe es texto markdown, nunca una imagen. Un SVG con texto
dentro se encoge con la columna: en un movil de 390 px el README ocupa 293 y
las etiquetas de una tarjeta de 860 px quedaban en 4 px, ilegibles, ademas de
invisibles para un lector de pantalla (WCAG 1.4.5, imagenes de texto).

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
from datetime import datetime
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
# Fuentes — cada una devuelve la lista COMPLETA; el recorte es cosa del render
# --------------------------------------------------------------------------

def fetch_posts() -> list[str]:
    """Articulos del blog, del mas reciente al mas antiguo, desde el RSS."""
    raw = http_get(RSS_URL, auth=False, accept="application/xml")
    items = ET.fromstring(raw).findall("./channel/item")
    if not items:
        raise RuntimeError("el RSS no trajo items")

    lineas = []
    for item in items:
        titulo = (item.findtext("title") or "").strip()
        enlace = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        try:
            fecha = es_date(parsedate_to_datetime(pub).isoformat())
        except (TypeError, ValueError):
            fecha = ""
        if not enlace.startswith("http"):
            enlace = f"{SITE}{enlace}"
        sufijo = f" — {fecha}" if fecha else ""
        lineas.append(f"[{titulo}]({enlace}){sufijo}")
    return lineas


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


def fetch_templates() -> list[str]:
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
    lineas = []
    for iso, name in fechas:
        titulo = name.replace("_", " ").strip()
        url = f"https://github.com/{OWNER}/{GALLERY_REPO}/tree/main/{urllib.parse.quote(name)}"
        lineas.append(f"[{titulo}]({url}) — {es_date(iso)}")
    return lineas


def fetch_releases(repos: list[dict]) -> list[str]:
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
    return [linea for _, linea in todas]


def collect_account() -> tuple[dict, list[dict]]:
    """Datos del perfil y de sus repos publicos, en una sola consulta.

    OJO con el token: `contributionsCollection` devuelve lo que el token puede
    ver. Con el GITHUB_TOKEN del workflow salen las contribuciones PUBLICAS,
    que es justo lo que debe anunciar un perfil publico. Si ejecutas esto en
    local con un PAT personal amplio, los commits saldran MUY inflados porque
    incluyen los repos privados: no compares ambas cifras.
    """
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, privacy: PUBLIC, isFork: false,
                     ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
          totalCount
          nodes { name stargazerCount }
        }
        contributionsCollection { totalCommitContributions }
      }
    }"""
    user = graphql(query, {"login": OWNER})["user"]
    cuenta = {
        "repos": user["repositories"]["totalCount"],
        "commits": user["contributionsCollection"]["totalCommitContributions"],
    }
    return cuenta, user["repositories"]["nodes"]


# --------------------------------------------------------------------------
# Render — solo markdown, nunca una imagen con texto dentro
# --------------------------------------------------------------------------

def render_actividad(cuenta: dict, posts: list[str], plantillas: list[str]) -> list[str]:
    """Linea de actividad, en texto corrido.

    NO es una tabla, y no por gusto: medido en la pagina publicada, una tabla
    de estas cuatro metricas pide 345 px y la columna del README en un movil
    mide 293, asi que la ultima quedaba tras una barra de scroll horizontal.
    El texto corrido refluye y no puede recortarse a ningun ancho.

    Se miden las cifras que sostienen el argumento. Fuera seguidores y
    estrellas: eran los dos numeros mas flojos y estaban en el tipo mas grande
    de la pagina, asi que el ojo aterrizaba justo en la peor evidencia.
    """
    partes = [
        f"**{len(posts)}** artículos publicados",
        f"**{len(plantillas)}** plantillas Deneb",
        f"**{cuenta['repos']}** repos públicos",
        f"**{cuenta['commits']}** commits en 12 meses",
    ]
    return [" · ".join(partes)]


def render_repos(repos: list[dict]) -> list[str]:
    """Repos agrupados por linea de trabajo, con estrellas reales."""
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


def replace_block(texto: str, nombre: str, lineas: list[str]) -> str:
    inicio, fin = f"<!-- {nombre}:start -->", f"<!-- {nombre}:end -->"
    patron = re.compile(re.escape(inicio) + r".*?" + re.escape(fin), re.DOTALL)
    if not patron.search(texto):
        raise RuntimeError(f"no encuentro los marcadores de '{nombre}' en el README")
    cuerpo = "\n".join(lineas)
    return patron.sub(f"{inicio}\n{cuerpo}\n{fin}", texto)


def as_list(lineas: list[str], tope: int) -> list[str]:
    return [f"- {linea}" for linea in lineas[:tope]]


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default="README.md")
    args = ap.parse_args()

    # newline="" al leer y LF explicito al escribir: sin esto los saltos
    # dependerian del sistema operativo (CRLF en Windows, LF en el runner) y
    # cada ejecucion reescribiria el archivo entero en el otro formato.
    with open(args.readme, encoding="utf-8", newline="") as fh:
        readme = fh.read()

    fallos: list[str] = []

    try:
        cuenta, repos = collect_account()
        posts = fetch_posts()
        plantillas = fetch_templates()
    # A proposito: da igual por que fallo (red, token, esquema). Sin estas tres
    # fuentes no hay ni bloques ni tabla, asi que se aborta sin tocar nada.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        print(f"ERROR: no pude leer las fuentes: {exc}", file=sys.stderr)
        return 1

    bloques = {
        "actividad": lambda: render_actividad(cuenta, posts, plantillas),
        "repos": lambda: render_repos(repos),
        "blog": lambda: as_list(posts, MAX_POSTS),
        "plantillas": lambda: as_list(plantillas, MAX_TEMPLATES),
        "releases": lambda: as_list(fetch_releases(repos), MAX_RELEASES),
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

    with open(args.readme, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(readme)

    if fallos:
        print("\nBloques no actualizados:\n  " + "\n  ".join(fallos), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
