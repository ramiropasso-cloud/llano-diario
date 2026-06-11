#!/usr/bin/env python3
"""LLANO· — Actualizacion automatica del diario 3x por dia"""

import os
import re
import json
import sys
import html as html_module
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

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
    # Links a notas internas APN
    for m in re.finditer(r'href="(/nota/detalle/[^"]+)"', raw):
        url = "https://apn.lapampa.gob.ar" + m.group(1)
        # Extraer titulo del contexto cercano
        start = m.start()
        ctx = raw[start:start+400]
        titulo_m = re.search(r'<(?:h[123]|strong|a)[^>]*>([^<]{15,120})</(?:h[123]|strong|a)>', ctx)
        if titulo_m:
            titulo = re.sub(r'\s+', ' ', titulo_m.group(1)).strip()
            if len(titulo) > 15 and url not in [i['url'] for i in items]:
                items.append({'url': url, 'titulo': titulo, 'foto': ''})
        if len(items) >= max_items:
            break
    return items


def apn_cuerpo(url):
    """Obtiene el texto e imagen principal de un articulo APN"""
    raw = fetch(url)
    if not raw:
        return "", ""
    # Imagen principal
    foto = ""
    img_m = re.search(r'<img[^>]+class="[^"]*noticia[^"]*"[^>]+src="([^"]+)"', raw)
    if not img_m:
        img_m = re.search(r'src="(https://apn\.lapampa\.gob\.ar/images/[^"]+)"', raw)
    if img_m:
        foto = img_m.group(1)
    # Parrafos del cuerpo
    parrafos = re.findall(r'<p[^>]*>([^<]{40,})</p>', raw)
    cuerpo = ' '.join(p.strip() for p in parrafos[:6])
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

# ── CONSTRUIR CONTEXTO PARA CLAUDE ──
apn_texto = ""
for it in apn_items:
    apn_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n  FOTO: {it.get('foto','')}\n  TEXTO: {it.get('cuerpo','')[:300]}\n"

dip_texto = ""
for it in dip_items:
    dip_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n"

PROMPT = f"""Sos el redactor jefe de LLANO·, el primer diario digital 100% IA de La Pampa, Argentina.
Fecha: {fecha_display} — {turno_label}

═══ NOTICIAS DISPONIBLES ═══

── APN La Pampa (fuente oficial del gobierno provincial) ──
{apn_texto if apn_texto.strip() else "No disponible hoy."}

── Diputados.gob.ar ──
{dip_texto if dip_texto.strip() else "No disponible hoy."}

═══ PRINCIPIOS EDITORIALES DE LLANO· ═══
1. OBJETIVIDAD ABSOLUTA — cobertura igual para PJ, UCR, LLA y todos los partidos. Sin sesgo.
2. SEGUIMIENTO PRIORITARIO: Di Napoli (Santa Rosa municipal y concejo), Alonso (General Pico municipal y concejo), Ravier (diputado LLA), Berhongaray (UCR), Kronemberger (legislador).
3. FUENTE: Siempre "LLANO·" — NUNCA mencionar La Arena, El Diario de La Pampa, ni Diarionoticias.
4. FOCO: 60% politica pampeana, 25% nacional con angulo pampeano, 15% economia/internacional.
5. VOZ: Clara, directa, rioplatense, sin sesgo partidario.
6. Las fotos son URLs de APN — usar SOLO las que existen en el contexto anterior.

GENERA EL SIGUIENTE JSON (sin texto adicional, solo el JSON valido):

{{
  "hero": {{
    "art_id": "id_snake_case",
    "cat": "Seccion · Subseccion",
    "titulo": "Titulo impactante maximo 85 caracteres",
    "summary": "Dos oraciones resumiendo la nota principal.",
    "foto": "URL foto APN o vacio"
  }},
  "sec01": [
    {{"id":"id1","cat":"Cat · Sub","titulo":"Titulo nota 1","resumen":"Una oracion de resumen.","foto":"URL o vacio","ts":"{fecha_corta} · LLANO·"}},
    {{"id":"id2","cat":"Cat · Sub","titulo":"Titulo nota 2","resumen":"Una oracion.","foto":"","ts":"{fecha_corta} · LLANO·"}},
    {{"id":"id3","cat":"Cat · Sub","titulo":"Titulo nota 3","resumen":"Una oracion.","foto":"","ts":"{fecha_corta} · LLANO·"}}
  ],
  "sec03": [
    {{"id":"id4","cat":"Nacional · Sub","titulo":"Titulo nacional 1","resumen":"Una oracion.","foto":"","ts":"{fecha_corta} · LLANO·"}},
    {{"id":"id5","cat":"Nacional · Sub","titulo":"Titulo nacional 2","resumen":"Una oracion.","foto":"","ts":"{fecha_corta} · LLANO·"}},
    {{"id":"id6","cat":"Nacional · Sub","titulo":"Titulo nacional 3","resumen":"Una oracion.","foto":"","ts":"{fecha_corta} · LLANO·"}}
  ],
  "arts": [
    {{
      "id":"id1",
      "cat":"Seccion · Subseccion",
      "fecha":"{fecha_corta}",
      "titulo":"Titulo completo del articulo",
      "bajada":"Dos oraciones que presentan el articulo.",
      "cuerpo":"<p>Parrafo 1 completo con <strong>negritas</strong> en nombres.</p><p>Parrafo 2.</p><p>Parrafo 3.</p><p>Parrafo 4 con conclusion.</p>",
      "foto":"URL o vacio"
    }}
  ]
}}

INSTRUCCIONES:
- sec01 = politica pampeana (3 noticias locales)
- sec03 = politica nacional (3 noticias nacionales con angulo pampeano cuando sea posible)
- arts = array con TODOS los articulos: el hero + los 3 de sec01 + los 3 de sec03 = minimo 7 articulos
- El id del hero debe coincidir con uno de los ids en sec01
- Escribi cuerpos completos de 4 parrafos en espanol rioplatense
- Backticks y comillas simples dentro del JSON deben estar escapados
- Devuelve SOLO el JSON, sin ningun texto antes ni despues"""

# ── LLAMADA A CLAUDE API ──
print("Llamando a Claude API (claude-haiku-4-5)...")

try:
    import anthropic
except ImportError:
    print("ERROR: Instalar anthropic → pip install anthropic")
    sys.exit(1)

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("ERROR: Variable de entorno ANTHROPIC_API_KEY no configurada")
    sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)

try:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": PROMPT}]
    )
    response_text = message.content[0].text.strip()
    print(f"  Respuesta recibida ({len(response_text)} chars)")
except Exception as e:
    print(f"ERROR API Claude: {e}")
    sys.exit(1)

# ── PARSEAR JSON ──
json_m = re.search(r'\{[\s\S]*\}', response_text)
if not json_m:
    print("ERROR: No se encontro JSON en la respuesta de Claude")
    print("Respuesta:", response_text[:500])
    sys.exit(1)

try:
    data = json.loads(json_m.group())
except json.JSONDecodeError as e:
    # Intentar limpiar el JSON
    raw_json = json_m.group()
    # Eliminar backticks no escapados dentro de strings JS
    print(f"ERROR JSON ({e}) — intentando limpiar...")
    sys.exit(1)

print(f"  JSON valido — {len(data.get('arts', []))} articulos, hero: {data.get('hero', {}).get('art_id','?')}")


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

llano = re.sub(
    r'<!-- AUTO:HERO:START -->[\s\S]*?<!-- AUTO:HERO:END -->',
    f'<!-- AUTO:HERO:START -->\n      {hero_nuevo}\n<!-- AUTO:HERO:END -->',
    llano
)

# ── REEMPLAZAR SEC01 ──
sec01 = data.get("sec01", [])[:3]
sec01_cards = "\n".join(card_html(c) for c in sec01)
llano = re.sub(
    r'<!-- AUTO:SEC01:START -->[\s\S]*?<!-- AUTO:SEC01:END -->',
    f'<!-- AUTO:SEC01:START -->\n  <div class="g3 fade-in">\n{sec01_cards}\n  </div>\n  <!-- AUTO:SEC01:END -->',
    llano
)

# ── REEMPLAZAR SEC03 ──
sec03 = data.get("sec03", [])[:3]
sec03_cards = "\n".join(card_html(c) for c in sec03)
llano = re.sub(
    r'<!-- AUTO:SEC03:START -->[\s\S]*?<!-- AUTO:SEC03:END -->',
    f'<!-- AUTO:SEC03:START -->\n  <div class="g3 fade-in">\n{sec03_cards}\n  </div>\n  <!-- AUTO:SEC03:END -->',
    llano
)

# ── REEMPLAZAR ARTS ──
arts_items = data.get("arts", [])
arts_entries_str = ",\n".join(arts_entry(a) for a in arts_items)
arts_block = f"""  // AUTO:ARTS:START
  const ARTS = {{
{arts_entries_str}
  }};
  // AUTO:ARTS:END"""

llano = re.sub(
    r'// AUTO:ARTS:START[\s\S]*?// AUTO:ARTS:END',
    arts_block,
    llano
)

# ── GUARDAR ──
with open(html_path, "w", encoding="utf-8") as f:
    f.write(llano)

new_size = len(llano)
print(f"llano.html actualizado: {original_size//1024}KB -> {new_size//1024}KB")
print(f"LLANO· {turno_label} — {fecha_display} — OK")
