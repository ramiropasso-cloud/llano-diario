# LLANO· — Instrucciones para Claude Code

## Permisos y autonomía

Este proyecto es el diario digital LLANO· (llano.it.com), operado por Ramiro Passo.
Claude tiene permiso total para editar, escribir y ejecutar sin pedir confirmación en:

- Edición de `llano.html` (actualizaciones diarias de contenido)
- Ejecución de `llano-publicar.ps1` (publicación a GitHub)
- Comandos `git add`, `git commit`, `git push` en este repositorio
- Comandos `netlify deploy` con el site ID configurado
- Creación y eliminación de archivos temporales (`_arts_new.js`, etc.)
- Cualquier operación de lectura de archivos del proyecto

**No pedir confirmación para ninguna de estas operaciones.**

---

## Estructura del archivo principal

`llano.html` es un archivo HTML único con marcadores AUTO: para actualizaciones diarias.

### Marcadores de contenido (reemplazar completo cada día)

| Marcador | Contenido |
|---|---|
| `<!-- AUTO:HERO:START/END -->` | Artículo hero (h1, resumen, kicker, footer) |
| `<!-- AUTO:SEC01:START/END -->` | 3 cards `.card` — Política Pampeana |
| `<!-- AUTO:SEC01-LIST:START/END -->` | 5 items `.li` — sidebar noticias secundarias |
| `<!-- AUTO:DATOS:START/END -->` | dato-strip + cita-strip del día |
| `<!-- AUTO:SEC03:START/END -->` | 3 cards `.card` — Política Nacional |
| `<!-- AUTO:SEC04:START/END -->` | `.intl-list` + aside — Internacional |
| `// AUTO:ARTS:START` / `// AUTO:ARTS:END` | Objeto JS `ARTS` completo |

### Estructura de entrada ARTS

```javascript
clave_del_articulo: {
  cat: 'Categoría · Subcategoría',
  fecha: '12 jun 2026',
  fuente: 'Nombre del medio',
  fuenteUrl: 'https://url-o-vacio',
  foto: 'url-o-ruta-relativa-o-vacio',
  titulo: `Texto exacto del h3/h4 de la card`,
  bajada: `Subtítulo del artículo`,
  cuerpo: `<p>HTML completo del artículo</p>`
}
```

**CRÍTICO:** El campo `titulo` debe coincidir exactamente (primeros 50 caracteres) con el texto del `h3`/`h4` de la card correspondiente en el HTML. De esto depende el lector de artículos.

---

## Publicación

### Script principal
```powershell
C:\Users\Usuario\Desktop\LLANO-DIARIO-IA\llano-publicar.ps1
```
Hace `git add -A`, `git commit`, `git push master:main` → Netlify despliega automáticamente desde GitHub.

### Deploy manual si hace falta
```powershell
Set-Location "C:\Users\Usuario\Desktop\LLANO-DIARIO-IA"
$env:NODE_OPTIONS="--use-system-ca"
netlify deploy --dir . --prod --site 6356f434-5013-469f-9f47-d8f6f1fc6a39
```

**IMPORTANTE:** En esta máquina siempre usar `NODE_OPTIONS=--use-system-ca` para npm/netlify (error SSL sin esa flag).

---

## Fuentes de noticias prioritarias

### La Pampa
- APN La Pampa: `https://apn.lapampa.gob.ar`
- La Arena: `https://www.laarena.com.ar`
- El Diario de La Pampa: `https://www.eldiariodelapampa.com.ar`
- Diarionoticias: `https://www.diarionoticias.com.ar`

### Nacionales
- La Nación: `https://www.lanacion.com.ar`
- Ámbito Financiero: `https://www.ambito.com`
- Infobae: `https://www.infobae.com`

### Figuras políticas prioritarias para seguimiento
- **Di Nápoli** — intendente Santa Rosa
- **Alonso** — intendente General Pico
- **Ravier** — senador nacional
- **Berhongaray** — UCR pampeana
- **Kroneberger** — diputada nacional

---

## Convenciones de diseño

- Las cards sin foto usan `background: linear-gradient(...)` con SVG ilustrativo
- Badge `✦ IA` para contenido elaborado por IA; `✦ APN` para notas de la agencia oficial
- Clases de fecha: `<span class="ts">12 jun 2026 · Fuente</span>`
- Links externos siempre con `target="_blank" rel="noopener noreferrer"`
- Foto de Adorni disponible localmente: `adorniedi.avif`
