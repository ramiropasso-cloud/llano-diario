#!/usr/bin/env python3
"""LLANO - Actualizacion automatica del diario 3x por dia"""

import os
import re
import json
import sys
import time
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


def fetch(url, timeout=12, intentos=3):
    for intento in range(1, intentos + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; LLANObot/1.0)',
                'Accept': 'text/html,application/xhtml+xml',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if intento < intentos:
                print(f"  [fetch reintento {intento}/{intentos}] {url}: {e}")
                time.sleep(3)
            else:
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
    (['adorni'],                          'img/politicos/adorni.avif'),
    (['berhongaray'],                     'img/politicos/berhongaray.webp'),
    (['huala'],                           'img/politicos/huala.webp'),
    (['kroneberger'],                     'img/politicos/krone.webp'),
    (['mac allister', 'macallister'],     'img/politicos/mac allister.webp'),
    (['ravier'],                          'img/politicos/ravier2.webp'),
    (['matzkin'],                         'img/politicos/matzkin.jpg'),
    (['torroba'],                         'img/politicos/torroba.webp'),
    (['altolaguirre'],                    'img/politicos/leandro altolaguirre.jpg'),
    (['ardohain'],                        'img/politicos/ardo.webp'),
    (['di napoli', 'dinapoli'],           'img/politicos/lucianodinapoli.webp'),
    (['ziliotto'],                        'img/politicos/zillioto.webp'),
    (['gisela cuadrado', 'cuadrado'],     'img/politicos/gisela cuadrado.webp'),
    (['mayoral'],                         'img/politicos/mayoral.jpg'),
    (['verna'],                           'img/politicos/verna.jpg'),
    (['rauschenberger'],                  'img/politicos/rauschenberger.png'),
    (['insaurralde'],                     'https://upload.wikimedia.org/wikipedia/commons/a/aa/Manzur_e_Insaurralde_%28cropped%29.jpg'),
    (['tosso'],                           'img/politicos/tosso.jpg'),
]

def buscar_foto_local(titulo, resumen=''):
    """Elige la foto de la persona que aparece mas temprano en el titulo (el sujeto principal
    de la noticia), no la primera coincidencia de FOTO_LOCAL — evita que una nota sobre Ravier
    que menciona de pasada a Adorni (su antecesor) termine usando la foto de Adorni."""
    titulo_l = titulo.lower()
    mejor_pos, mejor_path = None, None
    for keywords, path in FOTO_LOCAL:
        for kw in keywords:
            pos = titulo_l.find(kw)
            if pos != -1 and (mejor_pos is None or pos < mejor_pos):
                mejor_pos, mejor_path = pos, path
    if mejor_path:
        return mejor_path
    texto = (titulo + ' ' + resumen).lower()
    for keywords, path in FOTO_LOCAL:
        if any(kw in texto for kw in keywords):
            return path
    return ''


def foto_es_valida(foto):
    """Una foto valida es una URL real (http/https) provista por el contexto de APN.
    Cualquier otro valor (nombre de archivo inventado por el modelo, ej. 'adorniedi.avif')
    se descarta y se reemplaza por busqueda real en el pipeline de fotos."""
    return bool(foto) and foto.startswith('http')

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

def buscar_foto_wikipedia(titulo, lang='es', contexto=''):
    """Busca foto libre en Wikipedia para un titulo dado (2 requests). El parametro
    'contexto' (ej. 'La Pampa Argentina') se suma a la busqueda para evitar que un
    nombre de lugar ambiguo (ej. 'Santa Rosa', 'San Miguel') traiga la foto de una
    ciudad homonima en otro pais o provincia."""
    try:
        time.sleep(0.4)  # evitar HTTP 429 por demasiadas busquedas seguidas
        termino_base = titulo[:80] + (' ' + contexto if contexto else '')
        termino = urllib.parse.quote(termino_base)
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


_STOPWORDS_INICIALES = {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'este', 'esta', 'estos', 'estas'}

def extraer_nombre_propio(texto):
    """Extrae la secuencia de palabras capitalizadas mas larga (candidato a nombre de persona).
    Descarta candidatos como 'El Gobierno' o 'El Congreso', que son mayuscula de inicio de oracion
    seguida de un sustantivo comun, no un nombre propio real."""
    candidatos = re.findall(
        r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|y)?\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}\b',
        texto or ''
    )
    limpios = []
    for c in candidatos:
        palabras = c.split()
        while palabras and palabras[0].lower() in _STOPWORDS_INICIALES:
            palabras = palabras[1:]
        if len(palabras) >= 2:
            limpios.append(' '.join(palabras))
    return max(limpios, key=len) if limpios else ''


def _nombre_coincide(nombre, titulo_wiki):
    conectores = {'de', 'del', 'la', 'y'}
    palabras_nombre = {w.lower() for w in nombre.split() if len(w) > 2 and w.lower() not in conectores}
    palabras_wiki = {w.lower() for w in re.split(r'[\s,]+', titulo_wiki) if len(w) > 2}
    return bool(palabras_nombre & palabras_wiki)


def buscar_foto_persona(titulo, resumen=''):
    """Busca foto de una persona nombrada en titulo/resumen, validando que la pagina de Wikipedia
    encontrada corresponda a ese nombre antes de usar la foto — evita el problema de fotos
    erroneas que motivo deshabilitar Wikipedia para noticias nacionales genericas."""
    nombre = extraer_nombre_propio(titulo) or extraer_nombre_propio(resumen)
    if not nombre:
        return ""
    try:
        time.sleep(0.4)  # evitar HTTP 429 por demasiadas busquedas seguidas
        termino = urllib.parse.quote(nombre[:80])
        raw = fetch(f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={termino}&format=json&srlimit=1&srnamespace=0", timeout=7)
        if not raw:
            return ""
        results = json.loads(raw).get('query', {}).get('search', [])
        if not results:
            return ""
        titulo_wiki = results[0]['title']
        if not _nombre_coincide(nombre, titulo_wiki):
            return ""
        page = urllib.parse.quote(titulo_wiki.replace(' ', '_'))
        raw2 = fetch(f"https://es.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={page}&format=json&pithumbsize=600&redirects=1", timeout=7)
        if not raw2:
            return ""
        pages = json.loads(raw2).get('query', {}).get('pages', {})
        for p in pages.values():
            src = p.get('thumbnail', {}).get('source', '')
            if not src:
                continue
            if any(x in src.lower() for x in WIKI_EXCLUIR):
                continue
            return src
    except Exception as e:
        print(f"  [wiki-persona] {e}")
    return ""


_W = 'https://upload.wikimedia.org/wikipedia/commons'

# Cada tema mapea a una LISTA de fotos candidatas (no una sola), para poder
# rotar y evitar que dos noticias distintas terminen mostrando la misma imagen.
_ECONOMIA_BUILDING = f'{_W}/thumb/1/16/Edificio_del_Ministerio_de_Econom%C3%ADa_de_la_Naci%C3%B3n_Argentina%2C_ubicado_sobre_la_calle_Hip%C3%B3lito_Yrigoyen%2C_frente_al_entorno_de_Plaza_de_Mayo%2C_en_la_Ciudad_de_Buenos_Aires.jpg/960px-thumbnail.jpg'

# IMPORTANTE: todas las URLs de este mapa deben ser fotos reales y recientes
# (verificadas, no de archivo/stock viejo) — si no se encuentra una foto actual
# confiable para un tema, se omite el tema (el pipeline cae al placeholder con
# gradiente) en vez de usar una foto vieja o de un lugar/persona distinto.
TOPIC_LOCAL = [
    (['congreso', 'diputados', 'camara baja', 'camara de diputados'],
     [f'{_W}/thumb/d/d2/144_PER%C3%8DODO_DE_SESIONES_ORDINARIAS_EN_EL_CONGRESO_DE_LA_NACI%C3%93N.jpg/960px-144_PER%C3%8DODO_DE_SESIONES_ORDINARIAS_EN_EL_CONGRESO_DE_LA_NACI%C3%93N.jpg']),
    (['senado', 'senadores nacionales', 'camara alta'],
     [f'{_W}/6/61/Fin_PASO_01.jpg']),
    (['casa rosada', 'gobierno nacional', 'presidencia', 'poder ejecutivo', 'vocero presidencial', 'voceria'],
     [f'{_W}/thumb/2/26/Casa_Rosada_frente_a_Plaza_de_Mayo%2C_en_el_centro_de_Buenos_Aires%2C_Argentina.jpg/960px-Casa_Rosada_frente_a_Plaza_de_Mayo%2C_en_el_centro_de_Buenos_Aires%2C_Argentina.jpg']),
    (['banco central', 'bcra'],
     [_ECONOMIA_BUILDING]),
    (['inflación', 'inflacion', 'economía nacional', 'economia nacional', 'dólar', 'dolar',
      'ministerio de economía', 'ministerio de economia', 'tasas de interés', 'tasas de interes',
      'mercados', 'bonos argentinos'],
     [f'{_W}/thumb/9/91/Sello_Ministerio_de_Econom%C3%ADa_-_Argentina.png/960px-Sello_Ministerio_de_Econom%C3%ADa_-_Argentina.png',
      _ECONOMIA_BUILDING]),
    (['pyme', 'pymes', 'crédito', 'creditos', 'créditos', 'financiamiento'],
     [_ECONOMIA_BUILDING]),
    (['empleo', 'desempleo', 'trabajo', 'ministerio de trabajo', 'mercado laboral'],
     [f'{_W}/thumb/c/ce/Cartel_ministerio_de_trabajo_y_empleo_argentina.jpg/960px-Cartel_ministerio_de_trabajo_y_empleo_argentina.jpg']),
    # cosecha/agro y deuda/bolsa: sin foto reciente confiable disponible — se omiten
    # a proposito para no caer en fotos viejas (ver comentario arriba).
]

# Fallback para noticias genericas de La Pampa (sin persona ni foto APN) que el
# resto del pipeline (foto local / persona / wikipedia) no logra resolver.
PAMPA_LOCAL = [
    (['cultura', 'patrimonio', 'museo'],
     [f'{_W}/thumb/6/6f/Entrada_al_Museo_Provincial_de_Historia_Natural_de_La_Pampa_1.jpg/960px-Entrada_al_Museo_Provincial_de_Historia_Natural_de_La_Pampa_1.jpg']),
    (['educación', 'educacion', 'escuela', 'digital', 'tecnologia', 'tecnología', 'universidad'],
     [f'{_W}/thumb/4/4b/Universidad_Nacional_de_La_Pampa_2.jpg/960px-Universidad_Nacional_de_La_Pampa_2.jpg']),
    (['pj', 'peronis', 'justicialista', 'legislatura', 'diputados de la pampa', 'electoral'],
     [f'{_W}/thumb/f/f3/Camara_de_diputados_de_La_Pampa_05.jpg/960px-Camara_de_diputados_de_La_Pampa_05.jpg']),
    (['santa rosa', 'municipal', 'intendencia'],
     [f'{_W}/thumb/9/9d/Municipalidad_de_Santa_Rosa%2C_La_Pampa.jpg/960px-Municipalidad_de_Santa_Rosa%2C_La_Pampa.jpg']),
    # salud/hospital y general pico: sin foto reciente confiable disponible — se omiten
    # (la unica de Hospital Regional encontrada es de 1930-1950; la de Gral. Pico es de 2009).
]

TOPIC_LOCAL_ALL = TOPIC_LOCAL + PAMPA_LOCAL


def buscar_foto_tema(cat, titulo, resumen='', usadas=None):
    """Foto institucional fija para temas genericos sin persona nombrada (Congreso,
    Casa Rosada, hospitales, museos, etc.) — URLs estables de Wikimedia Commons. Si se
    pasa 'usadas', prefiere una candidata todavia no usada en esta corrida para no repetir."""
    texto = f"{cat} {titulo} {resumen}".lower()
    for keywords, urls in TOPIC_LOCAL_ALL:
        if any(kw in texto for kw in keywords):
            if usadas:
                for u in urls:
                    if u not in usadas:
                        return u
            return urls[0]
    return ""


def resolver_foto(candidatos, usadas):
    """Prueba cada funcion candidata en orden y devuelve la primera foto que no
    este ya usada en esta corrida. Si todas las candidatas encontradas ya estan
    usadas, devuelve la primera que se encontro (mejor repetir que dejar vacio)."""
    primera_encontrada = ''
    for fn in candidatos:
        foto = fn()
        if not foto:
            continue
        if not primera_encontrada:
            primera_encontrada = foto
        if foto not in usadas:
            return foto
    return primera_encontrada


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


def rss_items(url, max_items=10):
    """Parsea un feed RSS/Atom y devuelve lista de {titulo, url, descripcion}"""
    import xml.etree.ElementTree as ET
    raw = fetch(url, timeout=15)
    if not raw:
        return []
    items = []
    try:
        # Quitar namespace para simplificar XPath
        raw_clean = re.sub(r' xmlns[^"]*"[^"]*"', '', raw)
        root = ET.fromstring(raw_clean)
        # RSS 2.0
        for it in root.findall('.//item')[:max_items]:
            titulo = (it.findtext('title') or '').strip()
            link   = (it.findtext('link') or it.findtext('guid') or '').strip()
            desc   = re.sub(r'<[^>]+>', '', it.findtext('description') or '')[:250].strip()
            if titulo and len(titulo) > 10:
                items.append({'titulo': titulo, 'url': link, 'desc': desc})
        # Atom
        if not items:
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            for it in root.findall('.//a:entry', ns)[:max_items]:
                titulo = (it.findtext('a:title', namespaces=ns) or '').strip()
                link_el = it.find('a:link', ns)
                link = (link_el.get('href', '') if link_el is not None else '').strip()
                desc = re.sub(r'<[^>]+>', '', it.findtext('a:summary', namespaces=ns) or '')[:250].strip()
                if titulo and len(titulo) > 10:
                    items.append({'titulo': titulo, 'url': link, 'desc': desc})
    except Exception as e:
        print(f"  [rss parse error] {url}: {e}")
    return items


def noticias_nacionales_rss(max_items=10):
    """Intenta varios feeds RSS nacionales y devuelve las noticias mas frescas"""
    FUENTES = [
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
        "https://www.ambito.com/rss/home.xml",
        "https://www.infobae.com/feeds/rss/",
        "https://www.pagina12.com.ar/rss/portada",
    ]
    for url in FUENTES:
        items = rss_items(url, max_items)
        if len(items) >= 3:
            print(f"  Nacionales RSS: {len(items)} items de {url}")
            return items
        elif items:
            print(f"  Nacionales RSS parcial: {len(items)} items de {url}")
        else:
            print(f"  [nac rss fallo] {url}")
    return []


def noticias_internacionales_rss(max_items=8):
    """Intenta varios feeds RSS internacionales en espanol"""
    FUENTES = [
        "https://feeds.bbci.co.uk/mundo/rss.xml",
        "https://rss.dw.com/xml/rss-es-all",
        "https://www.swissinfo.ch/spa/temas-del-d%C3%ADa/rss.xml",
    ]
    for url in FUENTES:
        items = rss_items(url, max_items)
        if len(items) >= 3:
            print(f"  Internacionales RSS: {len(items)} items de {url}")
            return items
        elif items:
            print(f"  Internacionales RSS parcial: {len(items)} items de {url}")
        else:
            print(f"  [intl rss fallo] {url}")
    return []


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

print("Obteniendo noticias nacionales (RSS)...")
nac_items = noticias_nacionales_rss(10)
print(f"  {len(nac_items)} noticias nacionales via RSS")

print("Obteniendo noticias internacionales (RSS)...")
intl_items = noticias_internacionales_rss(8)
print(f"  {len(intl_items)} noticias internacionales via RSS")

pampa_sin_fuentes = (len(apn_items) + len(dip_items) < 3)
if pampa_sin_fuentes:
    print("Pocas/ninguna noticia provincial disponible (APN/Diputados) — se prioriza nacional/internacional este turno.")

# ── CONSTRUIR CONTEXTO PARA CLAUDE ──
apn_texto = ""
for it in apn_items:
    apn_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n  FOTO: {it.get('foto','')}\n  TEXTO: {it.get('cuerpo','')[:300]}\n"

dip_texto = ""
for it in dip_items:
    dip_texto += f"\n• TITULO: {it['titulo']}\n  URL: {it['url']}\n"

nac_texto = ""
for it in nac_items:
    nac_texto += f"\n• {it['titulo']}\n  {it.get('desc','')[:200]}\n  URL: {it.get('url','')}\n"

intl_texto = ""
for it in intl_items:
    intl_texto += f"\n• {it['titulo']}\n  {it.get('desc','')[:200]}\n  URL: {it.get('url','')}\n"

aviso_sin_fuentes_pampa = ""
if pampa_sin_fuentes:
    aviso_sin_fuentes_pampa = "ATENCION — HOY NO HAY FUENTES PROVINCIALES FRESCAS (APN y Diputados no respondieron): NO inventes noticias puntuales, anuncios, declaraciones ni hechos nuevos de La Pampa. En este turno: el hero principal y hero_side deben centrarse en la noticia nacional o internacional mas importante del dia (no en La Pampa). sec01_list puede tener menos de 6 items si no hay nada seguro que contar — preferi 1-3 items de seguimiento institucional ya conocido y verificable (continuidad de gestion, sin hechos puntuales inventados) antes que rellenar con noticias falsas. dato_dia y cita_dia tambien pueden referirse a nacional/internacional si no hay nada confiable de La Pampa hoy."

PROMPT = f"""Sos el redactor jefe de LLANO, el primer diario digital 100% IA de La Pampa, Argentina.
Fecha: {fecha_display} — {turno_label}

NOTICIAS DISPONIBLES HOY (FUENTES OFICIALES PROVINCIALES):
{apn_texto if apn_texto.strip() else "No disponible hoy."}

NOTICIAS NACIONALES — RSS REAL DE HOY:
{nac_texto if nac_texto.strip() else "RSS nacional no disponible en este turno."}

NOTICIAS INTERNACIONALES — RSS REAL DE HOY:
{intl_texto if intl_texto.strip() else "RSS internacional no disponible en este turno."}

REGLA FUNDAMENTAL — NUNCA INVENTAR:
- sec03 (nacional) SOLO puede cubrir noticias que aparecen en la seccion "NOTICIAS NACIONALES" de arriba. Si hay pocas, pone menos items — preferi 2-3 items reales a 6 inventados.
- sec04 (internacional) SOLO puede cubrir noticias que aparecen en la seccion "NOTICIAS INTERNACIONALES" de arriba. Si hay pocas, pone menos items — preferi 2-3 items reales a 5 inventados.
- NUNCA uses tu entrenamiento para inventar noticias de hoy en sec03 ni sec04. Las noticias de hoy solo pueden venir de las fuentes RSS de arriba.
{aviso_sin_fuentes_pampa}

PRINCIPIOS EDITORIALES:
1. OBJETIVIDAD ABSOLUTA — cobertura igual para PJ, UCR, LLA y todos los partidos. Sin sesgo.
2. SEGUIMIENTO EQUILIBRADO DE TODA LA OPOSICION Y EL OFICIALISMO — no concentrar la cobertura en un solo referente opositor. Cubrir segun peso institucional real:
   OFICIALISMO: Ziliotto (GOBERNADOR PJ), Di Napoli (intendente Santa Rosa, PJ/La Campora), Alonso (intendenta Gral. Pico, vernismo/PJ).
   OPOSICION (cubrir el conjunto, sin sobre-representar a uno solo): Kroneberger (SENADOR NACIONAL UCR), Huala (SENADORA NACIONAL PRO), Ardohain (DIPUTADO NACIONAL PRO), Ravier (DIPUTADO NACIONAL LLA — viene ganando protagonismo politico, cubrir con la misma intensidad que a los demas referentes opositores, no menos), Berhongaray (presidente Comite UCR provincial, conduccion partidaria sin banca), Altolaguirre (EX INTENDENTE Santa Rosa UCR, sin cargo actual).
3. FUENTE EN CAMPO TS: el campo ts SIEMPRE debe ser exactamente "{fecha_corta} · LLANO·". NUNCA poner La Arena, El Diario de La Pampa, Diarionoticias, Ambito, ni ningún otro medio en ningún campo.
4. VOZ: Clara, directa, rioplatense, sin sesgo partidario.
5. FOTOS: APN es fuente de texto/notas oficiales, NO la fuente de fotos. Si el contexto trae una URL de foto de APN, usala; si no, deja el campo vacio y NO inventes ni busques fotos por tu cuenta — el sistema completa automaticamente con foto local del archivo o foto verificada de Wikipedia.
6. PROFUNDIDAD Y TRASFONDO: ademas del anuncio o hecho del dia, buscar el "entre telones" — alianzas, tensiones internas, operadores y conectores que explican por que pasa lo que pasa en la politica pampeana. Priorizar notas que muestren el juego de poder y los vinculos entre actores, no solo la gacetilla oficial.

DEFINICION ESTRICTA DE SECCIONES:
- sec01_list = 6 noticias de LA PAMPA en formato lista (gobierno provincial, municipios, politica pampeana, economia, salud, cultura, obra publica) — NO repetir los temas/protagonistas ya cubiertos en hero o hero_side, deben ser noticias distintas
- sec03 (cards) = noticias de ARGENTINA NACIONAL basadas en RSS de arriba (Casa Rosada, Congreso, economia nacional, partidos nacionales) — NADA de La Pampa — puede tener menos de 6 si el RSS tiene pocos items hoy
- sec04 (lista) = noticias INTERNACIONALES basadas en RSS de arriba (otros paises, organismos mundiales) — NADA de Argentina — puede tener menos de 5 si el RSS tiene pocos items hoy
- dato_dia = el dato estadistico/cifra mas importante del dia en La Pampa
- cita_dia = la frase textual mas relevante del dia en la politica pampeana

ARTICULO COMPLETO OBLIGATORIO PARA TODAS LAS NOTAS — NO SOLO LAS PRINCIPALES:
El array "arts" debe incluir UN articulo completo por CADA noticia que aparece en sec01_list, sec03 y hero_side (NO es necesario para sec04, que es solo lista internacional sin clic). Es decir: 6 (sec01_list) + 6 (sec03) + 2 (hero_side) = 14 articulos en total. El campo "titulo" de cada entrada en "arts" debe coincidir EXACTAMENTE con el "titulo" de la noticia correspondiente en su seccion de origen, porque el sitio usa ese texto para abrir el articulo al hacer clic. Ninguna noticia debe quedar sin articulo completo: ningun lector debe hacer clic y que no pase nada. Para cada articulo escribe 4 parrafos completos en HTML con etiquetas p y strong.

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
                    "cat":     {"type": "string"},
                    "titulo":  {"type": "string", "description": "Maximo 85 caracteres"},
                    "summary": {"type": "string", "description": "2 oraciones impactantes"},
                    "foto":    {"type": "string", "description": "URL foto APN o vacio"}
                },
                "required": ["cat", "titulo", "summary", "foto"]
            },
            "sec01_list": {
                "type": "array",
                "description": "6 noticias de LA PAMPA en lista (gobierno provincial, municipios, economia, salud, obra publica, cultura) — distintas de las cubiertas en hero/hero_side",
                "items": LI_SCHEMA,
                "minItems": 6,
                "maxItems": 6
            },
            "sec03": {
                "type": "array",
                "description": "6 noticias NACIONALES de Argentina (fuera de La Pampa) — Casa Rosada, Congreso, economia nacional",
                "items": CARD_SCHEMA,
                "minItems": 6,
                "maxItems": 6
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
                "description": "Articulo completo para CADA noticia de sec01_list + sec03 + hero_side (no para sec04). El 'titulo' de cada art debe coincidir exactamente con el de su noticia de origen. Minimo 14 articulos. Escribi 4 parrafos por articulo.",
                "items": ART_SCHEMA,
                "minItems": 14
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
                "description": "2 noticias para los paneles secundarios del hero (estilo Apple: foto + titulo + resumen), mix La Pampa + nacional. La SEGUNDA noticia es la menos relevante de las dos y ocupa el panel ancho de abajo. chip_cls: chip-a (Hoy), chip-b (Info), chip-r (Escandalo).",
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
                "minItems": 2,
                "maxItems": 2
            }
        },
        "required": ["hero", "sec01_list", "sec03", "sec04", "dato_dia", "cita_dia", "arts", "ticker", "hero_side"]
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
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=24000,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "actualizar_diario"},
        messages=[{"role": "user", "content": PROMPT}]
    ) as stream:
        message = stream.get_final_message()
    # tool_use garantiza que input es un dict Python valido
    data = message.content[0].input
    print(f"  Tool use OK — {len(data.get('arts', []))} articulos, hero: {data.get('hero', {}).get('titulo','?')[:50]}")
except Exception as e:
    print(f"ERROR API Claude: {e}")
    sys.exit(1)

# ── VALIDAR RESPUESTA — descartar items malformados o respuestas degeneradas ──
for clave in ['sec01_list', 'sec03', 'arts', 'ticker', 'hero_side']:
    items = data.get(clave, [])
    if not isinstance(items, list):
        data[clave] = []
        continue
    limpios = [it for it in items if isinstance(it, dict)]
    if len(limpios) != len(items):
        print(f"  ADVERTENCIA: {clave} tenia {len(items) - len(limpios)} items malformados — descartados")
    data[clave] = limpios

if len(data.get('arts', [])) > 20:
    print(f"ERROR: respuesta degenerada de la API (arts={len(data.get('arts',[]))}) — abortando sin modificar llano.html")
    sys.exit(1)

if not isinstance(data.get('hero'), dict):
    print("ERROR: hero malformado en la respuesta — abortando sin modificar llano.html")
    sys.exit(1)

if not data.get('sec01_list') or len(data.get('sec03', [])) < 2 or not data.get('sec04'):
    print(f"ERROR: respuesta insuficiente (sec01_list={len(data.get('sec01_list',[]))}, sec03={len(data.get('sec03',[]))}, sec04={len(data.get('sec04',[]))}) — abortando sin modificar llano.html")
    sys.exit(1)

# ── BÚSQUEDA DE FOTOS WIKIPEDIA (para artículos sin foto de APN) ──
# 'fotos_usadas' rastrea todas las fotos ya asignadas en esta corrida para que
# dos noticias distintas nunca terminen mostrando la misma imagen.
print("Buscando fotos en Wikipedia para artículos sin imagen...")
fotos_usadas = set()

def _es_pampa(cat):
    c = (cat or '').lower()
    return 'pampa' in c or 'provincia' in c or any(m in c for m in ['santa rosa', 'general pico'])

# Hero principal: foto local → persona nombrada en Wikipedia → tema institucional fijo
_hero = data.get('hero', {})
if not foto_es_valida(_hero.get('foto')):
    _hero['foto'] = ''
    foto = resolver_foto([
        lambda: buscar_foto_local(_hero.get('titulo', ''), _hero.get('summary', '')),
        lambda: buscar_foto_persona(_hero.get('titulo', ''), _hero.get('summary', '')),
        lambda: buscar_foto_tema(_hero.get('cat', ''), _hero.get('titulo', ''), _hero.get('summary', ''), usadas=fotos_usadas),
    ], fotos_usadas)
    if foto:
        _hero['foto'] = foto
        fotos_usadas.add(foto)
        print(f"  [foto] hero: {_hero.get('titulo','')[:50]}")

# SEC01-LIST provincial (economia/salud/cultura/obra publica): foto local → persona nombrada → Wikipedia (con contexto La Pampa) → tema fijo
for item in data.get('sec01_list', []):
    if not foto_es_valida(item.get('foto')):
        item['foto'] = ''
        foto = resolver_foto([
            lambda: buscar_foto_local(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_persona(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_wikipedia(item['titulo'], lang='es', contexto='La Pampa Argentina'),
            lambda: buscar_foto_tema(item.get('cat', ''), item['titulo'], item.get('resumen', ''), usadas=fotos_usadas),
        ], fotos_usadas)
        if foto:
            item['foto'] = foto
            fotos_usadas.add(foto)
            print(f"  [foto] sec01_list: {item['titulo'][:50]}")

# SEC03 nacional: foto local → persona nombrada en Wikipedia → tema institucional fijo
for item in data.get('sec03', []):
    if not foto_es_valida(item.get('foto')):
        item['foto'] = ''
        foto = resolver_foto([
            lambda: buscar_foto_local(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_persona(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_tema(item.get('cat', ''), item['titulo'], item.get('resumen', ''), usadas=fotos_usadas),
        ], fotos_usadas)
        if foto:
            item['foto'] = foto
            fotos_usadas.add(foto)
            print(f"  [foto] sec03: {item['titulo'][:50]}")

# Hero-side: foto local → persona nombrada en Wikipedia → tema institucional fijo
# (el ultimo item es el panel ancho de abajo y no usa foto — se omite la busqueda)
_hero_side_list = data.get('hero_side', [])
for _idx, item in enumerate(_hero_side_list):
    if _idx == len(_hero_side_list) - 1:
        continue
    if not foto_es_valida(item.get('foto')):
        item['foto'] = ''
        foto = resolver_foto([
            lambda: buscar_foto_local(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_persona(item['titulo'], item.get('resumen', '')),
            lambda: buscar_foto_tema(item.get('cat', ''), item['titulo'], item.get('resumen', ''), usadas=fotos_usadas),
        ], fotos_usadas)
        if foto:
            item['foto'] = foto
            fotos_usadas.add(foto)
            print(f"  [foto] hero-side: {item['titulo'][:50]}")

# Mapa titulo → foto ya resuelta para hero/sec01_list/sec03/hero_side, de modo
# que el articulo completo (arts) de una noticia muestre SIEMPRE la misma foto
# que su card/item de origen, en vez de hacer una busqueda independiente que
# puede dar un resultado distinto (o peor, equivocado).
_foto_por_titulo = {}
for _src in [_hero] + data.get('sec01_list', []) + data.get('sec03', []) + data.get('hero_side', []):
    if _src.get('titulo') and _src.get('foto'):
        _foto_por_titulo[_src['titulo']] = _src['foto']

# Arts: reusa la foto de su card/item de origen → si no hay match, foto local → Wikipedia → tema institucional fijo
for art in data.get('arts', []):
    if not foto_es_valida(art.get('foto')):
        reusada = _foto_por_titulo.get(art.get('titulo', ''), '')
        if reusada:
            art['foto'] = reusada
            continue
        art['foto'] = ''
        contexto = 'La Pampa Argentina' if _es_pampa(art.get('cat', '')) else 'Argentina'
        lang = 'en' if any(x in art.get('cat','').lower() for x in ['intern', 'mundial', 'global']) else 'es'
        foto = resolver_foto([
            lambda: buscar_foto_local(art['titulo'], art.get('bajada', '')),
            lambda: buscar_foto_wikipedia(art['titulo'], lang=lang, contexto=(contexto if lang == 'es' else '')),
            lambda: buscar_foto_tema(art.get('cat', ''), art['titulo'], art.get('bajada', ''), usadas=fotos_usadas),
        ], fotos_usadas)
        if foto:
            art['foto'] = foto
            fotos_usadas.add(foto)
            print(f"  [foto] art: {art['titulo'][:50]}")

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
        img_block = '<div class="card-img" style="background:linear-gradient(150deg,#0e1520,#182030);"><div class="illus-glow" style="background:radial-gradient(ellipse at 40% 60%, rgba(46,168,255,.16) 0%,transparent 55%);"></div></div>'
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
if foto_hero and (foto_hero.startswith("http") or foto_hero.startswith("img/")):
    foto_block_hero = f'<div class="hero-panel-photo" style="background-image:url(\'{foto_hero}\');"></div>'
else:
    foto_block_hero = '<div class="hero-panel-photo" style="background-image:linear-gradient(150deg,#0e1520,#182030);"></div>'
hero_nuevo = f"""<div class="hero-panel hero-panel--lead">
        <div class="hero-panel-top">
          <div class="hero-panel-kicker">
            <span class="live-dot">SEGUIMIENTO</span>
            <span class="hero-panel-cat">{e(hero.get("cat",""))}</span>
          </div>
          <h1 class="hero-panel-title">{e(hero.get("titulo",""))}</h1>
          <p class="hero-panel-sub">{e(hero.get("summary",""))}</p>
          <div class="hero-panel-foot">
            <span class="ts">{fecha_display} &#183; LLANO&#183;</span>
            <span class="ia-badge">&#10022; Analisis IA</span>
          </div>
        </div>
        {foto_block_hero}
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

def hero_panel_item(item, wide=False):
    chip_cls = e(item.get("chip_cls", "chip-a"))
    chip_txt = e(item.get("chip_txt", "Hoy"))
    cat      = e(item.get("cat", ""))
    titulo   = e(item.get("titulo", ""))
    resumen  = e(item.get("resumen", ""))
    ts       = e(item.get("ts", ""))
    foto     = item.get("foto", "")
    cls = "hero-panel hero-panel--wide" if wide else "hero-panel"
    if wide:
        # panel ancho de abajo (menos relevante) — sin foto, fondo claro de contraste
        foto_block = ""
    elif foto and (foto.startswith("http") or foto.startswith("img/")):
        foto_block = f'<div class="hero-panel-photo" style="background-image:url(\'{foto}\');"></div>'
    else:
        foto_block = '<div class="hero-panel-photo" style="background-image:linear-gradient(150deg,#0e1520,#182030);"></div>'
    return f"""      <div class="{cls}">
        <div class="hero-panel-top">
          <div class="hero-panel-kicker">
            <span class="hero-panel-cat">{cat}</span>
          </div>
          <h2 class="hero-panel-title">{titulo}</h2>
          <p class="hero-panel-sub">{resumen}</p>
          <div class="hero-panel-foot">
            <span class="ts">{ts}</span>
            <span class="chip {chip_cls}">{chip_txt}</span>
          </div>
        </div>
        {foto_block}
      </div>"""

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

# ── REEMPLAZAR SEC03 ──
sec03 = data.get("sec03", [])[:6]
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
    n_hs = len(hero_side_items)
    hs_html = "\n".join(hero_panel_item(it, wide=(i == n_hs - 1)) for i, it in enumerate(hero_side_items))
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
    "sec01_list": [{"titulo": c["titulo"], "resumen": c.get("resumen",""), "cat": c.get("cat",""), "foto": c.get("foto",""), "ts": c.get("ts","")} for c in data.get("sec01_list",[])],
    "sec03":      [{"titulo": c["titulo"], "resumen": c.get("resumen",""), "cat": c.get("cat",""), "foto": c.get("foto",""), "ts": c.get("ts","")} for c in data.get("sec03",[])],
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
  <url>
    <loc>https://llano.it.com/nosotros.html</loc>
    <lastmod>{fecha_iso_hoy}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
  <url>
    <loc>https://llano.it.com/como-funciona-la-ia.html</loc>
    <lastmod>{fecha_iso_hoy}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
  <url>
    <loc>https://llano.it.com/politica-editorial.html</loc>
    <lastmod>{fecha_iso_hoy}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
</urlset>
"""
with open(sitemap_path, "w", encoding="utf-8") as f:
    f.write(sitemap_xml)

# ── GUARDAR ──
# Se escribe tanto en llano.html como en index.html (la raiz del sitio) para que
# "/" sirva el contenido real en lugar de depender de un redirect meta-refresh,
# que generaba un canonical apuntando a una pagina practicamente vacia.
with open(html_path, "w", encoding="utf-8") as f:
    f.write(llano)
index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
with open(index_path, "w", encoding="utf-8") as f:
    f.write(llano)

new_size = len(llano)
print(f"llano.html actualizado: {original_size//1024}KB -> {new_size//1024}KB")
print(f"LLANO· {turno_label} — {fecha_display} — OK")
