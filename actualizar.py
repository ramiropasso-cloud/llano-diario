#!/usr/bin/env python3
"""LLANO - Actualizacion automatica del diario 3x por dia"""

import os
import re
import json
import sys
import html as html_module
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

# Fix encoding en Windows para que print no rompa con tildes/caracteres
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── TIMEZONE ARGENTINA (UTC-3) ──
ARG_TZ = timezone(timedelta(hours=-3))
ahora = datetime.now(ARG_TZ)

MESES = {1:'ene',2:'feb',3:'mar',4:'abr',5:'may',6:'jun',
         7:'jul',8:'ago',9:'sep',10:'oct',11:'nov',12:'dic'}
MESES_L = {1:'enero',2:'febrero',3:'marzo',4:'abril',5:'mayo',6:'junio',
           7:'julio',8:'agosto',9:'septiembre',10:'octubre',11:'noviembre',12:'diciembre'}

fecha_display = f"{ahora.day} {MESES_L[ahora.month]} {ahora.year}"
fecha_corta   = f"{ahora.day} {MESES[ahora.month]} {ahora.year}"

hora = ahora.hour
if hora < 10:
    turno = "manana"
    turno_label = "Edición Mañana · 7:00"
elif hora < 14:
    turno = "mediodia"
    turno_label = "Edición Mediodía · 11:00"
else:
    turno = "tarde"
    turno_label = "Edición Tarde · 17:00"


def fetch(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LLANObot/1.0)',
            'Accept': 'text/html,application/xhtml+xml',
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  [fetch error] {url}: {e}")
        return ""


def apn_noticias(max_items=8):
    """Extrae titulos, URLs e imagenes de la homepage de APN La Pampa"""
    raw = fetch("https://apn.lapampa.gob.ar")
    if not raw:
        return []
    items = []
    seen_urls = set()
    # Las URLs son absolutas: https://apn.lapampa.gob.ar/nota/detalle/id/XXXXX/slug
    pattern = r'href="(https://apn\.lapampa\.gob\.ar/nota/detalle/id/\d+/[^"]+)"'
    for m in re.finditer(pattern, raw):
        url = m.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # Contexto siguiente para extraer alt (titulo) e img src
        ctx = raw[m.start():m.start() + 800]
        foto = ""
        titulo = ""
        # Imagen cercana
        img_m = re.search(r'<img[^>]+src="(https://apn\.lapampa\.gob\.ar/images/[^"]+)"[^>]+alt="([^"]{10,})"', ctx)
        if not img_m:
            img_m = re.search(r'<img[^>]+alt="([^"]{10,})"[^>]+src="(https://apn\.lapampa\.gob\.ar/images/[^"]+)"', ctx)
            if img_m:
                titulo = img_m.group(1).strip()
                foto = img_m.group(2)
        else:
            foto = img_m.group(1)
            titulo = img_m.group(2).strip()
        # Si no hay titulo por imagen, buscar en h2
        if not titulo:
            h2_m = re.search(r'<h2[^>]*class="[^"]*title-dest[^"]*"[^>]*>\s*([^<]{10,120})', ctx)
            if h2_m:
                titulo = re.sub(r'\s+', ' ', h2_m.group(1)).strip()
        # Titulo del slug como fallback
        if not titulo:
            slug = url.split('/')[-1]
            titulo = slug.replace('-', ' ')
        titulo = re.sub(r'\s+', ' ', titulo).strip()
        if len(titulo) > 10:
            items.append({'url': url, 'titulo': titulo, 'foto': foto})
        if len(items) >= max_items:
            break
    return items


def apn_cuerpo(url):
    """Obtiene el texto e imagen principal de un articulo APN"""
    raw = fetch(url)
    if not raw:
        return "", ""
    foto = ""
    # Imagen principal del articulo
    img_m = re.search(r'src="(https://apn\.lapampa\.gob\.ar/images/multimedia/[^"]+)"', raw)
    if img_m:
        foto = img_m.group(1)
    # Parrafos del cuerpo - buscar dentro del div de contenido
    parrafos = re.findall(r'<p[^>]*>\s*([^<]{40,})\s*</p>', raw)
    cuerpo = ' '.join(p.strip() for p in parrafos[:6] if len(p.strip()) > 40)
    return cuerpo[:900], foto


def diputados_noticias(max_items=4):
    """Extrae noticias de la pagina de prensa de Diputados"""
    raw = fetch("https://www.diputados.gob.ar/prensa/")
    if not raw:
        return []
    items = []
    for m in re.finditer(r'href="(/prensa/noticia/([^"]+))"[^>]*>([^<]{15,120})</a>', raw):
        titulo = re.sub(r'\s+', ' ', m.group(3)).strip()
        if len(titulo) > 15:
            items.append({
                'url': "https://www.diputados.gob.ar" + m.group(1),
                'titulo': titulo,
                'foto': ''
            })
        if len(items) >= max_items:
            break
    return items


# ── RECOLECTAR NOTICIAS ──
print(f"LLANO· Actualizacion automatica — {fecha_display} — Turno: {turno_label}")
print("Obteniendo noticias de APN La Pampa...")

apn_items = apn_noticias(8)
print(f"  {len(apn_items)} noticias encontradas en APN")

# Obtener cuerpos de las primeras 5 noticias APN
for item in apn_items[:5]:
    cuerpo, foto = apn_cuerpo(item['url'])
    item['cuerpo'] = cuerpo
    if foto:
        item['foto'] = foto

print("Obteniendo noticias de Diputados...")
dip_items = diputados_noticias(4)
print(f"  {len(dip_items)} noticias encontradas en Diputados")

# Si no hay noticias suficientes, mantener el contenido actual sin tocar
if len(apn_items) + len(dip_items) < 3:
    print("Menos de 3 noticias disponibles — manteniendo contenido actual sin modificar.")
    sys.exit(0)

# ── CONSTRUIR CONTEXTO PARA CLAUDE ──
apn_texto = ""
for it in apn_items:
    apn_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n  FOTO: {it.get('foto','')}\n  TEXTO: {it.get('cuerpo','')[:300]}\n"

dip_texto = ""
for it in dip_items:
    dip_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n"

PROMPT = f"""Sos el redactor jefe de LLANO, el primer diario digital 100% IA de La Pampa, Argentina.
Fecha: {fecha_display} — {turno_label}

NOTICIAS DISPONIBLES HOY:

APN La Pampa (fuente oficial del gobierno provincial):
{apn_texto if apn_texto.strip() else "No disponible hoy."}

Diputados.gob.ar:
{dip_texto if dip_texto.strip() else "No disponible hoy."}

PRINCIPIOS EDITORIALES:
1. OBJETIVIDAD ABSOLUTA — cobertura igual para PJ, UCR, LLA y todos los partidos. Sin sesgo.
2. SEGUIMIENTO PRIORITARIO: Di Napoli (Santa Rosa municipal y concejo), Alonso (General Pico), Ravier (diputado LLA), Berhongaray (UCR), Kronemberger.
3. FUENTE: Siempre "LLANO" — NUNCA mencionar La Arena, El Diario de La Pampa, ni Diarionoticias.
4. FOCO: 60% politica pampeana, 25% nacional con angulo pampeano, 15% economia/internacional.
5. VOZ: Clara, directa, rioplatense, sin sesgo partidario.
6. Fotos: usar SOLO las URLs de APN que estan en el contexto anterior. Si no hay foto, dejar vacio.

Usa la herramienta actualizar_diario con las noticias del dia.
Para cada articulo del array arts, escribe el cuerpo completo de 4 parrafos en HTML con etiquetas p y strong."""

# ── SCHEMA PARA TOOL USE (JSON GARANTIZADO) ──
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "id":      {"type": "string", "description": "id snake_case unico"},
        "cat":     {"type": "string", "description": "Seccion y subseccion"},
        "titulo":  {"type": "string"},
        "resumen": {"type": "string", "description": "Una oracion de resumen"},
        "foto":    {"type": "string", "description": "URL APN o vacio"},
        "ts":      {"type": "string", "description": f"{fecha_corta} · LLANO"}
    },
    "required": ["id", "cat", "titulo", "resumen", "foto", "ts"]
}

ART_SCHEMA = {
    "type": "object",
    "properties": {
        "id":     {"type": "string"},
        "cat":    {"type": "string"},
        "fecha":  {"type": "string"},
        "titulo": {"type": "string"},
        "bajada": {"type": "string", "description": "Dos oraciones de presentacion"},
        "cuerpo": {"type": "string", "description": "HTML con 4 parrafos usando etiquetas p y strong"},
        "foto":   {"type": "string"}
    },
    "required": ["id", "cat", "fecha", "titulo", "bajada", "cuerpo", "foto"]
}

TOOL = {
    "name": "actualizar_diario",
    "description": "Actualizar el contenido del diario LLANO con las noticias del dia",
    "input_schema": {
        "type": "object",
        "properties": {
            "hero": {
                "type": "object",
                "description": "La nota mas importante del dia para el hero principal",
                "properties": {
                    "art_id":  {"type": "string", "description": "Debe coincidir con un id en sec01"},
                    "cat":     {"type": "string"},
                    "titulo":  {"type": "string", "description": "Maximo 85 caracteres"},
                    "summary": {"type": "string", "description": "2 oraciones impactantes"},
                    "foto":    {"type": "string", "description": "URL foto APN o vacio"}
                },
                "required": ["art_id", "cat", "titulo", "summary", "foto"]
            },
            "sec01": {
                "type": "array",
                "description": "3 noticias de politica pampeana",
                "items": CARD_SCHEMA,
                "minItems": 3,
                "maxItems": 3
            },
            "sec03": {
                "type": "array",
                "description": "3 noticias de politica nacional con angulo pampeano",
                "items": CARD_SCHEMA,
                "minItems": 3,
                "maxItems": 3
            },
            "arts": {
                "type": "array",
                "description": "Todos los articulos completos (hero + sec01 + sec03 = min 7)",
                "items": ART_SCHEMA,
                "minItems": 6
            }
        },
        "required": ["hero", "sec01", "sec03", "arts"]
    }
}

# ── LLAMADA A CLAUDE API ──
print("Llamando a Claude API (claude-haiku-4-5)...")

try:
    import anthropic
except ImportError:
    print("ERROR: Instalar anthropic — pip install anthropic")
    sys.exit(1)

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("ERROR: Variable ANTHROPIC_API_KEY no configurada")
    sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)

try:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "actualizar_diario"},
        messages=[{"role": "user", "content": PROMPT}]
    )
    # tool_use garantiza que input es un dict Python valido
    data = message.content[0].input
    print(f"  Tool use OK — {len(data.get('arts', []))} articulos, hero: {data.get('hero', {}).get('art_id','?')}")
except Exception as e:
    print(f"ERROR API Claude: {e}")
    sys.exit(1)

# Detectar contenido relleno — si Claude genero titulos vagos, no actualizar
TITULOS_RELLENO = ['sin novedades', 'guardia redaccional', 'sin informacion', 'no hay noticias',
                   'sin novedad', 'mantiene guardia', 'sin actualizaciones', 'espera de actualizaciones']
for art in data.get('arts', []):
    titulo_lower = art.get('titulo', '').lower()
    if any(r in titulo_lower for r in TITULOS_RELLENO):
        print(f"Contenido relleno detectado: '{art['titulo']}' — manteniendo contenido actual.")
        sys.exit(0)


# ── GENERADORES HTML ──

def e(s):
    return html_module.escape(str(s)) if s else ""

def card_html(item):
    foto = item.get("foto", "")
    if foto and foto.startswith("http"):
        img_block = f'<div class="card-img" style="background:#111;"><img src="{foto}" alt="{e(item["titulo"])}" loading="lazy" /></div>'
    else:
        img_block = '<div class="card-img" style="background:linear-gradient(150deg,#0e1520,#182030);"><div class="illus-glow" style="background:radial-gradient(ellipse at 40% 60%, rgba(200,120,10,.18) 0%,transparent 55%);"></div></div>'
    return f"""    <div class="card">
      {img_block}
      <div class="card-meta"><span class="cat">{e(item.get("cat",""))}</span><span class="ia-badge">&#10022; IA</span></div>
      <h3>{e(item["titulo"])}</h3>
      <p>{e(item.get("resumen",""))}</p>
      <div class="card-meta"><span class="ts">{e(item.get("ts",""))}</span></div>
    </div>"""

def arts_entry(item):
    # Limpiar cuerpo de posibles problemas con backticks
    cuerpo = item.get("cuerpo", "<p>Contenido en elaboracion.</p>")
    cuerpo = cuerpo.replace("`", "'").replace("\\", "\\\\")
    titulo = item.get("titulo", "").replace("`", "'")
    bajada = item.get("bajada", "").replace("`", "'")
    return f"""    {item['id']}: {{
      cat:'{e(item.get("cat",""))}', fecha:'{e(item.get("fecha",""))}', fuente:'LLANO\\u00b7',
      fuenteUrl:'', foto:'{item.get("foto","")}',
      titulo:`{titulo}`,
      bajada:`{bajada}`,
      cuerpo:`{cuerpo}`
    }}"""


# ── LEER llano.html ──
html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llano.html")
with open(html_path, "r", encoding="utf-8") as f:
    llano = f.read()

original_size = len(llano)

# ── REEMPLAZAR HERO ──
hero = data.get("hero", {})
foto_hero = hero.get("foto", "")
img_hero = f'<img class="hero-photo" src="{foto_hero}" alt="{e(hero.get("titulo",""))}" />' if foto_hero and foto_hero.startswith("http") else ""
hero_nuevo = f"""{img_hero}
      <div class="hero-bg" style="background:linear-gradient(to top,rgba(10,9,9,.98) 0%,rgba(10,9,9,.88) 28%,rgba(10,9,9,.72) 58%,rgba(10,9,9,.35) 100%),radial-gradient(ellipse at 30% 80%, rgba(200,120,10,.25) 0%, transparent 55%);"></div>
      <div class="hero-grid-lines"></div>
      <div class="hero-main-content">
        <div class="hero-kicker">
          <span class="live-dot">SEGUIMIENTO</span>
          <span style="width:1px;height:12px;background:rgba(255,255,255,.15);display:inline-block;"></span>
          <span style="font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.4);font-weight:600;">{e(hero.get("cat",""))}</span>
        </div>
        <h1 class="hero-title">{e(hero.get("titulo",""))}</h1>
        <p class="hero-summary">{e(hero.get("summary",""))}</p>
        <div class="hero-footer">
          <span class="hero-ts">{fecha_display} · LLANO&#183;</span>
          <span class="ia-badge">&#10022; Analisis IA</span>
        </div>
      </div>"""

def safe_sub(pattern, replacement, text):
    """re.sub seguro — usa lambda para evitar que backslashes en el reemplazo rompan regex"""
    return re.sub(pattern, lambda _: replacement, text)

hero_bloque = f'<!-- AUTO:HERO:START -->\n      {hero_nuevo}\n<!-- AUTO:HERO:END -->'
llano = safe_sub(r'<!-- AUTO:HERO:START -->[\s\S]*?<!-- AUTO:HERO:END -->', hero_bloque, llano)

# ── REEMPLAZAR SEC01 ──
sec01 = data.get("sec01", [])[:3]
sec01_cards = "\n".join(card_html(c) for c in sec01)
sec01_bloque = f'<!-- AUTO:SEC01:START -->\n  <div class="g3 fade-in">\n{sec01_cards}\n  </div>\n  <!-- AUTO:SEC01:END -->'
llano = safe_sub(r'<!-- AUTO:SEC01:START -->[\s\S]*?<!-- AUTO:SEC01:END -->', sec01_bloque, llano)

# ── REEMPLAZAR SEC03 ──
sec03 = data.get("sec03", [])[:3]
sec03_cards = "\n".join(card_html(c) for c in sec03)
sec03_bloque = f'<!-- AUTO:SEC03:START -->\n  <div class="g3 fade-in">\n{sec03_cards}\n  </div>\n  <!-- AUTO:SEC03:END -->'
llano = safe_sub(r'<!-- AUTO:SEC03:START -->[\s\S]*?<!-- AUTO:SEC03:END -->', sec03_bloque, llano)

# ── REEMPLAZAR ARTS ──
arts_items = data.get("arts", [])
arts_entries_str = ",\n".join(arts_entry(a) for a in arts_items)
arts_block = f"  // AUTO:ARTS:START\n  const ARTS = {{\n{arts_entries_str}\n  }};\n  // AUTO:ARTS:END"
llano = safe_sub(r'// AUTO:ARTS:START[\s\S]*?// AUTO:ARTS:END', arts_block, llano)

# ── GUARDAR ──
with open(html_path, "w", encoding="utf-8") as f:
    f.write(llano)

new_size = len(llano)
print(f"llano.html actualizado: {original_size//1024}KB -> {new_size//1024}KB")
print(f"LLANO· {turno_label} — {fecha_display} — OK")
