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
import urllib.parse

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
DIAS_SEMANA = {0:'Lunes',1:'Martes',2:'Miércoles',3:'Jueves',4:'Viernes',5:'Sábado',6:'Domingo'}

fecha_display = f"{ahora.day} {MESES_L[ahora.month]} {ahora.year}"
fecha_corta   = f"{ahora.day} {MESES[ahora.month]} {ahora.year}"
dia_semana    = DIAS_SEMANA[ahora.weekday()]

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

# ── EVITAR CORRIDAS DUPLICADAS DEL MISMO TURNO ──
# Permite que un "watchdog" dispare este script seguido (ej. al desbloquear la PC)
# sin gastar tokens de mas si el turno de hoy ya se publico.
_archivo_path_check = os.path.join(os.path.dirname(os.path.abspath(__file__)), "noticias.json")
_clave_hoy = f"{ahora.strftime('%Y-%m-%d')}_{turno}"
try:
    with open(_archivo_path_check, "r", encoding="utf-8") as _f:
        _archivo_check = json.load(_f)
    if any(c.get("clave") == _clave_hoy for c in _archivo_check.get("corridas", [])):
        print(f"Turno '{turno}' de hoy ya esta publicado (clave={_clave_hoy}) — nada que hacer.")
        sys.exit(0)
except (FileNotFoundError, json.JSONDecodeError):
    pass


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
    pattern = r'href="(https://apn\.lapampa\.gob\.ar/nota/detalle/id/\d+/[^"]+)"'
    for m in re.finditer(pattern, raw):
        url = m.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # Contexto amplio: 600 chars antes + 1200 despues del href
        start = max(0, m.start() - 600)
        ctx = raw[start:m.start() + 1200]
        foto = ""
        titulo = ""
        # Buscar imagen de nota (noticias/ o multimedia/) — excluye logos e iconos
        img_m = re.search(r'src="(https://apn\.lapampa\.gob\.ar/images/(?:noticias|multimedia)/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', ctx, re.IGNORECASE)
        if img_m:
            foto = img_m.group(1)
        # Fallback: URL relativa /images/noticias/ o /images/multimedia/
        if not foto:
            img_m = re.search(r'src="(/images/(?:noticias|multimedia)/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', ctx, re.IGNORECASE)
            if img_m:
                foto = "https://apn.lapampa.gob.ar" + img_m.group(1)
        # Titulo desde alt de imagen
        if not titulo:
            alt_m = re.search(r'<img[^>]+alt="([^"]{10,})"', ctx)
            if alt_m:
                titulo = alt_m.group(1).strip()
        # Titulo desde h2
        if not titulo:
            h2_m = re.search(r'<h2[^>]*>\s*(?:<[^>]+>)?\s*([^<]{10,120})', ctx)
            if h2_m:
                titulo = re.sub(r'\s+', ' ', h2_m.group(1)).strip()
        # Fallback: slug
        if not titulo:
            titulo = url.split('/')[-1].replace('-', ' ')
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
    # Imagen del articulo — prioriza noticias/multimedia, excluye logos
    img_m = re.search(r'src="(https://apn\.lapampa\.gob\.ar/images/(?:noticias|multimedia)/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', raw, re.IGNORECASE)
    if img_m:
        foto = img_m.group(1)
    if not foto:
        img_m = re.search(r'src="(/images/(?:noticias|multimedia)/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', raw, re.IGNORECASE)
        if img_m:
            foto = "https://apn.lapampa.gob.ar" + img_m.group(1)
    # Parrafos del cuerpo
    parrafos = re.findall(r'<p[^>]*>\s*([^<]{40,})\s*</p>', raw)
    cuerpo = ' '.join(p.strip() for p in parrafos[:6] if len(p.strip()) > 40)
    return cuerpo[:900], foto


# Mapeo keyword → foto local (img/politicos/)
FOTO_LOCAL = [
    (['adorni'],                          'img/politicos/ardo.webp'),
    (['berhongaray'],                     'img/politicos/berhongaray.webp'),
    (['huala'],                           'img/politicos/huala.webp'),
    (['kroneberger'],                     'img/politicos/krone.webp'),
    (['mac allister', 'macallister'],     'img/politicos/mac allister.webp'),
    (['ravier'],                          'img/politicos/ravier.jpg'),
    (['torroba'],                         'img/politicos/torroba.webp'),
    (['altolaguirre'],                    'img/politicos/leandro altolaguirre.jpg'),
    (['ardohain'],                        'img/politicos/ardo.webp'),
    (['di napoli', 'dinapoli'],           'img/politicos/lucianodinapoli.webp'),
    (['ziliotto'],                        'img/politicos/Dinapolizilioto.webp'),
    (['gisela cuadrado', 'cuadrado'],     'img/politicos/gisela cuadrado.webp'),
]

def buscar_foto_local(titulo, resumen=''):
    texto = (titulo + ' ' + resumen).lower()
    for keywords, path in FOTO_LOCAL:
        if any(kw in texto for kw in keywords):
            return path
    return ''

WIKI_EXCLUIR = ['flag', 'icon', 'logo', 'blank', 'svg', 'stub', 'escudo',
                'bandera', 'coat_of_arms', 'seal_of', 'cropped', 'portrait']

def _es_headshot(url):
    """Detecta retratos de personas por patron del nombre de archivo"""
    fn = re.sub(r'^\d+px-', '', url.split('/')[-1].lower().rsplit('.', 1)[0])
    if 'cropped' in fn:
        return True
    partes = [p for p in re.split(r'[_\-]', fn) if p and p[0].isupper()]
    # Patron Nombre_Apellido_Año → retrato de persona
    return 2 <= len(partes) <= 4 and len(fn) < 40

def buscar_foto_wikipedia(titulo, lang='es'):
    """Busca foto libre en Wikipedia para un titulo dado (2 requests)"""
    try:
        termino = urllib.parse.quote(titulo[:80])
        raw = fetch(f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={termino}&format=json&srlimit=1&srnamespace=0", timeout=7)
        if not raw:
            return ""
        results = json.loads(raw).get('query', {}).get('search', [])
        if not results:
            return ""
        page = urllib.parse.quote(results[0]['title'].replace(' ', '_'))
        raw2 = fetch(f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={page}&format=json&pithumbsize=600&redirects=1", timeout=7)
        if not raw2:
            return ""
        pages = json.loads(raw2).get('query', {}).get('pages', {})
        for p in pages.values():
            src = p.get('thumbnail', {}).get('source', '')
            if not src:
                continue
            if any(x in src.lower() for x in WIKI_EXCLUIR):
                continue
            if _es_headshot(src):
                continue
            return src
    except Exception as e:
        print(f"  [wiki] {e}")
    return ""


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


# ── CARGAR REFERENTES PROVINCIALES ──
referentes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "referentes.txt")
try:
    with open(referentes_path, "r", encoding="utf-8") as f:
        REFERENTES = f.read()
except FileNotFoundError:
    REFERENTES = ""
    print("ADVERTENCIA: referentes.txt no encontrado — los cargos pueden tener errores.")

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

NOTICIAS DISPONIBLES HOY (FUENTES OFICIALES PROVINCIALES):
{apn_texto if apn_texto.strip() else "No disponible hoy."}

PRINCIPIOS EDITORIALES:
1. OBJETIVIDAD ABSOLUTA — cobertura igual para PJ, UCR, LLA y todos los partidos. Sin sesgo.
2. SEGUIMIENTO: Di Napoli (intendente Santa Rosa), Alonso (intendenta General Pico), Ravier (DIPUTADO NACIONAL LLA — no senador), Kroneberger (SENADOR UCR), Berhongaray (presidente Comité UCR provincial — no legislador), Altolaguirre (EX INTENDENTE Santa Rosa UCR — sin cargo actual).
3. FUENTE EN CAMPO TS: el campo ts SIEMPRE debe ser exactamente "{fecha_corta} · LLANO·". NUNCA poner La Arena, El Diario de La Pampa, Diarionoticias, Ambito, ni ningún otro medio en ningún campo.
4. VOZ: Clara, directa, rioplatense, sin sesgo partidario.
5. Fotos: usar SOLO las URLs de APN del contexto. Si no hay foto real, dejar vacio.

DEFINICION ESTRICTA DE SECCIONES:
- sec01 (cards) = 3 noticias de LA PAMPA (gobierno provincial, municipios, politica pampeana)
- sec01_list = 4 noticias de LA PAMPA en formato lista (economia, salud, cultura, obra publica)
- sec03 (cards) = 3 noticias de ARGENTINA NACIONAL (Casa Rosada, Congreso, economia nacional, partidos nacionales) — NADA de La Pampa
- sec04 (lista) = 5 noticias INTERNACIONALES (otros paises, organismos mundiales) — NADA de Argentina
- dato_dia = el dato estadistico/cifra mas importante del dia en La Pampa
- cita_dia = la frase textual mas relevante del dia en la politica pampeana

Para sec03 y sec04 usa tu conocimiento del contexto mundial y nacional de hoy {fecha_display}.
Para cada articulo del array arts, escribe 4 parrafos completos en HTML con etiquetas p y strong.

CARGOS VERIFICADOS — CONSULTAR SIEMPRE ESTE MAPA ANTES DE ESCRIBIR:
{REFERENTES if REFERENTES else "Ver referentes.txt — archivo no disponible en esta corrida."}

HECHOS VERIFICADOS — NO INVENTAR NI CONTRADECIR:
- El Mundial FIFA 2026 se juega en ESTADOS UNIDOS, Canada y Mexico. Argentina NO es sede. Argentina es el campeon defensor (gano Qatar 2022).
- No atribuir declaraciones que no puedan verificarse en las fuentes disponibles.
- No inventar cifras, fechas, cargos ni ubicaciones geograficas. Si no estas seguro de un dato, omitilo.
- NUNCA mezclar el nombre de una persona con la biografia de otra persona distinta, aunque sean del mismo ambito (ej: derechos humanos, politica). Si el titulo de una nota menciona a "Persona A", TODO el cuerpo debe hablar de "Persona A" — revisar que el nombre no cambie a mitad del texto.
- Si una noticia ya fue cubierta en una edicion anterior (ej. un fallecimiento), no la reescribas como si fuera nueva ni le cambies los datos.
- NUNCA inventar resultados de partidos, marcadores, ganadores de elecciones o cualquier evento con desenlace incierto que todavia no ocurrio. Si un partido o evento esta programado pero no tenes confirmacion de que ya se jugo, hablar en futuro/presente ("se prepara para", "debuta hoy") y JAMAS inventar un marcador o resultado final."""

# ── SCHEMA PARA TOOL USE (JSON GARANTIZADO) ──
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "id":      {"type": "string", "description": "id snake_case unico"},
        "cat":     {"type": "string", "description": "Seccion y subseccion"},
        "titulo":  {"type": "string"},
        "resumen": {"type": "string", "description": "Una oracion de resumen"},
        "foto":    {"type": "string", "description": "URL APN o vacio"},
        "ts":      {"type": "string", "description": f"EXACTAMENTE '{fecha_corta} · LLANO·' — NUNCA otro medio"}
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

LI_SCHEMA = {
    "type": "object",
    "properties": {
        "id":      {"type": "string"},
        "cat":     {"type": "string"},
        "titulo":  {"type": "string"},
        "resumen": {"type": "string"},
        "foto":    {"type": "string", "description": "URL APN o vacio"},
        "ts":      {"type": "string", "description": f"EXACTAMENTE '{fecha_corta} · LLANO·' — NUNCA otro medio"}
    },
    "required": ["id", "cat", "titulo", "resumen", "foto", "ts"]
}

INTL_SCHEMA = {
    "type": "object",
    "properties": {
        "id":     {"type": "string"},
        "titulo": {"type": "string"},
        "ts":     {"type": "string"}
    },
    "required": ["id", "titulo", "ts"]
}

TOOL = {
    "name": "actualizar_diario",
    "description": "Actualizar el contenido del diario LLANO con las noticias del dia",
    "input_schema": {
        "type": "object",
        "properties": {
            "hero": {
                "type": "object",
                "description": "La nota mas importante del dia de La Pampa para el hero",
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
                "description": "3 noticias de LA PAMPA en cards (solo provincia)",
                "items": CARD_SCHEMA,
                "minItems": 3,
                "maxItems": 3
            },
            "sec01_list": {
                "type": "array",
                "description": "4 noticias de LA PAMPA en lista (economia, salud, obra publica, cultura pampeana)",
                "items": LI_SCHEMA,
                "minItems": 4,
                "maxItems": 5
            },
            "sec03": {
                "type": "array",
                "description": "3 noticias NACIONALES de Argentina (fuera de La Pampa) — Casa Rosada, Congreso, economia nacional",
                "items": CARD_SCHEMA,
                "minItems": 3,
                "maxItems": 3
            },
            "sec04": {
                "type": "array",
                "description": "5 noticias INTERNACIONALES (fuera de Argentina)",
                "items": INTL_SCHEMA,
                "minItems": 4,
                "maxItems": 5
            },
            "dato_dia": {
                "type": "object",
                "description": "Cifra o dato estadistico clave del dia en La Pampa",
                "properties": {
                    "num":   {"type": "string", "description": "Cifra destacada (ej: 2027, USD 500k, 48%)"},
                    "texto": {"type": "string", "description": "Contexto en 2 oraciones"},
                    "fuente":{"type": "string", "description": "LLANO· · fecha"}
                },
                "required": ["num", "texto", "fuente"]
            },
            "cita_dia": {
                "type": "object",
                "description": "Frase textual mas relevante del dia",
                "properties": {
                    "frase": {"type": "string"},
                    "autor": {"type": "string", "description": "Nombre, cargo y fecha"}
                },
                "required": ["frase", "autor"]
            },
            "arts": {
                "type": "array",
                "description": "Articulos con cuerpo — al menos hero + 3 de sec01 = minimo 4. Escribi 2 parrafos por articulo.",
                "items": ART_SCHEMA,
                "minItems": 4
            },
            "ticker": {
                "type": "array",
                "description": "6 titulares cortos para el ticker de noticias al tope. keyword: palabra clave MAYUSCULAS (ej: ADORNI, LA PAMPA, RAVIER). texto: resto del titular, max 70 chars.",
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "Palabra clave MAYUSCULAS, max 15 chars"},
                        "texto":   {"type": "string", "description": "Resto del titular, max 70 chars"}
                    },
                    "required": ["keyword", "texto"]
                },
                "minItems": 5,
                "maxItems": 7
            },
            "hero_side": {
                "type": "array",
                "description": "3 noticias para la barra lateral También hoy (mix La Pampa + nacional). chip_cls: chip-a (Hoy), chip-b (Info), chip-r (Escandalo).",
                "items": {
                    "type": "object",
                    "properties": {
                        "cat":      {"type": "string", "description": "Seccion · lugar"},
                        "titulo":   {"type": "string", "description": "Max 90 chars"},
                        "resumen":  {"type": "string", "description": "Una oracion"},
                        "chip_cls": {"type": "string", "description": "chip-a, chip-b o chip-r"},
                        "chip_txt": {"type": "string", "description": "Texto del chip (Hoy, Info, Escandalo, etc.)"},
                        "foto":     {"type": "string", "description": "URL foto o vacio"},
                        "ts":       {"type": "string", "description": f"EXACTAMENTE '{fecha_corta} · LLANO·' — NUNCA otro medio"}
                    },
                    "required": ["cat", "titulo", "resumen", "chip_cls", "chip_txt", "ts"]
                },
                "minItems": 3,
                "maxItems": 3
            }
        },
        "required": ["hero", "sec01", "sec01_list", "sec03", "sec04", "dato_dia", "cita_dia", "arts", "ticker", "hero_side"]
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

# ── VALIDAR RESPUESTA — descartar items malformados o respuestas degeneradas ──
for clave in ['sec01', 'sec01_list', 'sec03', 'arts', 'ticker', 'hero_side']:
    items = data.get(clave, [])
    if not isinstance(items, list):
        data[clave] = []
        continue
    limpios = [it for it in items if isinstance(it, dict)]
    if len(limpios) != len(items):
        print(f"  ADVERTENCIA: {clave} tenia {len(items) - len(limpios)} items malformados — descartados")
    data[clave] = limpios

if len(data.get('arts', [])) > 12 or len(data.get('sec01', [])) > 10:
    print(f"ERROR: respuesta degenerada de la API (arts={len(data.get('arts',[]))}, sec01={len(data.get('sec01',[]))}) — abortando sin modificar llano.html")
    sys.exit(1)

if not isinstance(data.get('hero'), dict):
    print("ERROR: hero malformado en la respuesta — abortando sin modificar llano.html")
    sys.exit(1)

# ── BÚSQUEDA DE FOTOS WIKIPEDIA (para artículos sin foto de APN) ──
print("Buscando fotos en Wikipedia para artículos sin imagen...")

# SEC01 provincial: foto local → Wikipedia
for item in data.get('sec01', []):
    if not item.get('foto'):
        foto = buscar_foto_local(item['titulo'], item.get('resumen', ''))
        if not foto:
            foto = buscar_foto_wikipedia(item['titulo'], lang='es')
        if foto:
            item['foto'] = foto
            print(f"  [foto] sec01: {item['titulo'][:50]}")

# SEC03 nacional: SOLO foto local (Wikipedia devuelve politicos equivocados para noticias genericas)
for item in data.get('sec03', []):
    if not item.get('foto'):
        foto = buscar_foto_local(item['titulo'], item.get('resumen', ''))
        if foto:
            item['foto'] = foto
            print(f"  [foto-local] sec03: {item['titulo'][:50]}")

# Arts: foto local → Wikipedia
for art in data.get('arts', []):
    if not art.get('foto'):
        foto = buscar_foto_local(art['titulo'], art.get('bajada', ''))
        if not foto:
            lang = 'en' if any(x in art.get('cat','').lower() for x in ['intern', 'mundial', 'global']) else 'es'
            foto = buscar_foto_wikipedia(art['titulo'], lang=lang)
        if foto:
            art['foto'] = foto
            print(f"  [foto] art: {art['titulo'][:50]}")

# Hero-side: foto local si Claude no asigno ninguna
for item in data.get('hero_side', []):
    if not item.get('foto'):
        foto = buscar_foto_local(item['titulo'], item.get('resumen', ''))
        if foto:
            item['foto'] = foto
            print(f"  [foto] hero-side: {item['titulo'][:50]}")

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
    if foto and (foto.startswith("http") or foto.startswith("img/")):
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

def li_html(item):
    foto = item.get("foto", "")
    if foto and (foto.startswith("http") or foto.startswith("img/")):
        img_block = f'<div class="li-img" style="width:88px;height:58px;background:#111;position:relative;overflow:hidden;border-radius:var(--r);"><img src="{foto}" alt="{e(item["titulo"])}" loading="lazy" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;" /></div>'
    else:
        img_block = '<div class="li-img" style="width:88px;height:58px;background:linear-gradient(135deg,#0e1520,#182030);border-radius:var(--r);"></div>'
    return f"""        <div class="li">
          {img_block}
          <div>
            <div class="card-meta" style="margin-bottom:.3rem;"><span class="cat">{e(item.get("cat",""))}</span></div>
            <h4>{e(item["titulo"])}</h4>
            <p>{e(item.get("resumen",""))}</p>
            <div class="li-meta"><span class="ts">{e(item.get("ts",""))}</span><span class="ia-badge">&#10022; IA</span></div>
          </div>
        </div>"""

def intl_html(items):
    rows = ""
    for i, it in enumerate(items, 1):
        rows += f"""      <div class="intl-item">
        <span class="intl-num">0{i}</span>
        <h4>{e(it["titulo"])}</h4>
        <span class="ts ia-badge" style="flex-shrink:0;">&#10022; IA</span>
      </div>\n"""
    return rows

def safe_sub(pattern, replacement, text):
    """re.sub seguro — usa lambda para evitar que backslashes en el reemplazo rompan regex"""
    return re.sub(pattern, lambda _: replacement, text)

def ticker_html(items):
    single = ""
    for it in items:
        kw = e(it.get("keyword", "").upper())
        txt = e(it.get("texto", ""))
        single += f'    <span class="ti"><span class="ti-sep">●</span> <strong>{kw}</strong> {txt}</span>\n'
    return single + single  # duplicado para scroll CSS infinito

def hero_side_item(item):
    chip_cls = e(item.get("chip_cls", "chip-a"))
    chip_txt = e(item.get("chip_txt", "Hoy"))
    cat      = e(item.get("cat", ""))
    titulo   = e(item.get("titulo", ""))
    resumen  = e(item.get("resumen", ""))
    ts       = e(item.get("ts", ""))
    foto     = item.get("foto", "")
    if foto and (foto.startswith("http") or foto.startswith("img/")):
        inner = (
            f'<div style="display:flex;gap:.75rem;align-items:flex-start;">'
            f'<div style="width:52px;height:52px;border-radius:50%;flex-shrink:0;overflow:hidden;border:1px solid rgba(255,255,255,.12);">'
            f'<img src="{foto}" alt="{titulo}" style="width:100%;height:100%;object-fit:cover;object-position:center top;" /></div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div class="card-meta" style="margin-bottom:.3rem;"><span class="cat">{cat}</span><span class="ia-badge">&#10022; IA</span></div>'
            f'<h3>{titulo}</h3><p>{resumen}</p>'
            f'<div class="hero-item-meta"><span class="ts">{ts}</span><span class="chip {chip_cls}">{chip_txt}</span></div>'
            f'</div></div>'
        )
    else:
        inner = (
            f'<div class="card-meta"><span class="cat">{cat}</span><span class="ia-badge">&#10022; IA</span></div>'
            f'<h3>{titulo}</h3><p>{resumen}</p>'
            f'<div class="hero-item-meta"><span class="ts">{ts}</span><span class="chip {chip_cls}">{chip_txt}</span></div>'
        )
    return f'      <div class="hero-item">\n        {inner}\n      </div>'

hero_bloque = f'<!-- AUTO:HERO:START -->\n      {hero_nuevo}\n<!-- AUTO:HERO:END -->'
llano = safe_sub(r'<!-- AUTO:HERO:START -->[\s\S]*?<!-- AUTO:HERO:END -->', hero_bloque, llano)

# ── ACTUALIZAR META TAGS OG/TWITTER CON LA NOTA PRINCIPAL ──
og_titulo = hero.get("titulo", "LLANO· — Política y Poder en La Pampa")
og_desc   = hero.get("summary", "")[:200] or "El primer diario digital 100% IA de La Pampa."
og_foto   = foto_hero if foto_hero and foto_hero.startswith("http") else "https://llano.it.com/og-image.jpg"

llano = re.sub(r'<meta property="og:title" content="[^"]*"', f'<meta property="og:title" content="{e(og_titulo)}"', llano)
llano = re.sub(r'<meta property="og:description" content="[^"]*"', f'<meta property="og:description" content="{e(og_desc)}"', llano)
llano = re.sub(r'<meta property="og:image" content="[^"]*"', f'<meta property="og:image" content="{og_foto}"', llano)
llano = re.sub(r'<meta name="twitter:title" content="[^"]*"', f'<meta name="twitter:title" content="{e(og_titulo)}"', llano)
llano = re.sub(r'<meta name="twitter:description" content="[^"]*"', f'<meta name="twitter:description" content="{e(og_desc)}"', llano)
llano = re.sub(r'<meta name="twitter:image" content="[^"]*"', f'<meta name="twitter:image" content="{og_foto}"', llano)
print(f"  Meta tags OG actualizados — foto: {'hero' if og_foto != 'https://llano.it.com/og-image.jpg' else 'fallback'}")

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

# ── REEMPLAZAR SEC01-LIST ──
sec01_list = data.get("sec01_list", [])
sec01_list_html = "\n".join(li_html(it) for it in sec01_list)
llano = safe_sub(
    r'<!-- AUTO:SEC01-LIST:START -->[\s\S]*?<!-- AUTO:SEC01-LIST:END -->',
    f'<!-- AUTO:SEC01-LIST:START -->\n{sec01_list_html}\n        <!-- AUTO:SEC01-LIST:END -->',
    llano
)

# ── REEMPLAZAR DATO DEL DÍA ──
dato = data.get("dato_dia", {})
cita = data.get("cita_dia", {})
datos_bloque = f"""<!-- AUTO:DATOS:START -->
  <div class="dato-strip fade-in">
    <span class="dato-strip-badge">Dato del día</span>
    <div class="dato-strip-num">{e(dato.get("num",""))}</div>
    <div class="dato-strip-txt">
      <p>{e(dato.get("texto",""))}</p>
      <cite>{e(dato.get("fuente",""))}</cite>
    </div>
  </div>
  <div class="cita-strip fade-in">
    <blockquote>"{e(cita.get("frase",""))}"</blockquote>
    <cite>— {e(cita.get("autor",""))}</cite>
  </div>
  <!-- AUTO:DATOS:END -->"""
llano = safe_sub(r'<!-- AUTO:DATOS:START -->[\s\S]*?<!-- AUTO:DATOS:END -->', datos_bloque, llano)

# ── REEMPLAZAR SEC04 INTERNACIONAL ──
sec04 = data.get("sec04", [])[:5]
sec04_rows = intl_html(sec04)
sec04_bloque = f"""<!-- AUTO:SEC04:START -->
  <div class="lay fade-in" style="margin-bottom:3rem;">
    <div class="intl-list">
{sec04_rows}    </div>
    <aside>
      <div class="ab">
        <h6 class="ab-hd">Contexto global hoy</h6>
        <div class="dato-box">
          <div class="num">{e(dato.get("num",""))}</div>
          <div class="label">{e(dato.get("texto",""))}</div>
          <div class="src">{e(dato.get("fuente",""))}</div>
        </div>
      </div>
    </aside>
  </div>
  <!-- AUTO:SEC04:END -->"""
llano = safe_sub(r'<!-- AUTO:SEC04:START -->[\s\S]*?<!-- AUTO:SEC04:END -->', sec04_bloque, llano)

# ── REEMPLAZAR ARTS ──
arts_items = data.get("arts", [])
print(f"  arts recibidos: {len(arts_items)}")
for a in arts_items:
    print(f"    - [{a.get('id','?')}] {a.get('titulo','?')[:60]}")

if len(arts_items) >= 4:
    arts_entries_str = ",\n".join(arts_entry(a) for a in arts_items)
    arts_block = f"  // AUTO:ARTS:START\n  const ARTS = {{\n{arts_entries_str}\n  }};\n  // AUTO:ARTS:END"
    llano = safe_sub(r'// AUTO:ARTS:START[\s\S]*?// AUTO:ARTS:END', arts_block, llano)
else:
    print(f"  ARTS insuficientes ({len(arts_items)}) — manteniendo articulos previos sin modificar")

# ── REEMPLAZAR TICKER ──
ticker_items = data.get("ticker", [])
if ticker_items:
    t_html = ticker_html(ticker_items)
    llano = safe_sub(
        r'<!-- AUTO:TICKER:START -->[\s\S]*?<!-- AUTO:TICKER:END -->',
        f'<!-- AUTO:TICKER:START -->\n{t_html}    <!-- AUTO:TICKER:END -->',
        llano
    )
    print(f"  Ticker actualizado — {len(ticker_items)} items")

# ── REEMPLAZAR HERO-SIDE (También hoy) ──
hero_side_items = data.get("hero_side", [])
if hero_side_items:
    hs_html = "\n".join(hero_side_item(it) for it in hero_side_items)
    llano = safe_sub(
        r'<!-- AUTO:HERO-SIDE:START -->[\s\S]*?<!-- AUTO:HERO-SIDE:END -->',
        f'<!-- AUTO:HERO-SIDE:START -->\n{hs_html}\n      <!-- AUTO:HERO-SIDE:END -->',
        llano
    )
    print(f"  Hero-side actualizado — {len(hero_side_items)} items")

# ── ACTUALIZAR FECHA DEL HEADER ──
llano = safe_sub(
    r'<span class="mb-date">[^<]+</span>',
    f'<span class="mb-date">{dia_semana}, {ahora.day} de {MESES_L[ahora.month]} de {ahora.year} · La Pampa</span>',
    llano
)

# ── ARCHIVAR EN NOTICIAS.JSON ──
archivo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "noticias.json")
try:
    with open(archivo_path, "r", encoding="utf-8") as f:
        noticias_archivo = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    noticias_archivo = {"version": 1, "corridas": []}

fecha_iso = ahora.strftime("%Y-%m-%d")
clave_corrida = f"{fecha_iso}_{turno}"

# Reemplazar corrida del mismo turno si ya existía (re-run del mismo turno)
noticias_archivo["corridas"] = [c for c in noticias_archivo.get("corridas", [])
                                 if c.get("clave") != clave_corrida]

corrida = {
    "clave":     clave_corrida,
    "fecha_iso": fecha_iso,
    "fecha":     fecha_display,
    "turno":     turno_label,
    "hero": {
        "titulo":  hero.get("titulo", ""),
        "summary": hero.get("summary", ""),
        "cat":     hero.get("cat", ""),
        "foto":    hero.get("foto", "")
    },
    "sec01":      [{"titulo": c["titulo"], "resumen": c.get("resumen",""), "cat": c.get("cat",""), "foto": c.get("foto",""), "ts": c.get("ts","")} for c in data.get("sec01",[])],
    "sec03":      [{"titulo": c["titulo"], "resumen": c.get("resumen",""), "cat": c.get("cat",""), "ts": c.get("ts","")} for c in data.get("sec03",[])],
    "hero_side":  [{"titulo": it.get("titulo",""), "resumen": it.get("resumen",""), "cat": it.get("cat",""), "ts": it.get("ts","")} for it in data.get("hero_side",[])],
    "arts":       [{"id": a["id"], "cat": a.get("cat",""), "titulo": a.get("titulo",""), "bajada": a.get("bajada",""), "cuerpo": a.get("cuerpo",""), "foto": a.get("foto","")} for a in data.get("arts",[])]
}

noticias_archivo["corridas"].insert(0, corrida)
noticias_archivo["corridas"] = noticias_archivo["corridas"][:180]  # ~60 dias

with open(archivo_path, "w", encoding="utf-8") as f:
    json.dump(noticias_archivo, f, ensure_ascii=False, indent=2)
print(f"  Archivo JSON: corrida '{clave_corrida}' guardada — total {len(noticias_archivo['corridas'])} corridas")

# ── ACTUALIZAR SITEMAP ──
sitemap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sitemap.xml")
fecha_iso_hoy = ahora.strftime("%Y-%m-%d")
sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://llano.it.com/</loc>
    <lastmod>{fecha_iso_hoy}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://llano.it.com/archivo.html</loc>
    <lastmod>{fecha_iso_hoy}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>
"""
with open(sitemap_path, "w", encoding="utf-8") as f:
    f.write(sitemap_xml)

# ── GUARDAR ──
with open(html_path, "w", encoding="utf-8") as f:
    f.write(llano)

new_size = len(llano)
print(f"llano.html actualizado: {original_size//1024}KB -> {new_size//1024}KB")
print(f"LLANO· {turno_label} — {fecha_display} — OK")
