# Automatización de búsquedas con OpenAlex

Fecha de referencia: 2026-05-09.

## Propósito

Este documento describe el MVP de automatización de búsquedas abiertas para `PRISMA-AI Tutor`, empezando por `OpenAlex` como primera fuente programática.

## Modelo recomendado de configuracion

Usa dos niveles de configuracion:

- `base.env` para credenciales y parametros compartidos;
- `case.env` para query, salidas, filtros y artefactos del caso activo.

Regla de portabilidad:

- las rutas internas del skill no dependen del workspace;
- las rutas operativas del caso (`cases/`, `outputs/`) se resuelven contra `PRISMA_AI_TUTOR_WORKSPACE_ROOT` si está definido;
- si no está definido, se usan relativas al directorio actual desde el que se ejecuta el comando.
- los scripts puramente CLI también aceptan `--workspace-root` para resolver rutas relativas sin depender del directorio desde el que se los lance.

La herencia se activa con:

- `PRISMA_AI_TUTOR_BASE_CONFIG=../../config/prisma-ai-tutor/base.env`
- `PRISMA_AI_TUTOR_WORKSPACE_ROOT=../..`

## Objetivo del MVP

Automatizar la recuperación inicial de literatura para que el estudiante o docente pueda:

- ejecutar una búsqueda trazable;
- exportar resultados normalizados;
- poblar una matriz inicial de cribado (selección de estudios);
- documentar la búsqueda sin depender de copias manuales.

## Arquitectura mínima

### 1. Query builder

Transforma la necesidad de búsqueda en parámetros reproducibles:

- consulta principal;
- modo de búsqueda;
- rango de fechas;
- idioma;
- tipo documental;
- inclusión o exclusión explícita de tipos documentales;
- filtros de acceso abierto o DOAJ.
- autenticación por `api_key` cuando esté disponible.
- carga de configuración desde archivo `.env` cuando esté disponible.
- reintentos ante errores transitorios o límites temporales de la API.
- filtro posterior por disponibilidad de `abstract` cuando el caso lo exige.

### 2. Source connector

El primer conector implementado es `OpenAlex`, porque:

- tiene API abierta;
- permite filtros útiles para revisiones de literatura;
- facilita automatización sin depender de licencias institucionales.

### 3. Normalizer

Los resultados se transforman a un esquema común:

- `code`
- `source`
- `source_id`
- `title`
- `authors`
- `year`
- `publication_date`
- `doi`
- `abstract`
- `journal`
- `journal_type`
- `language`
- `document_type`
- `is_oa`
- `oa_status`
- `source_is_in_doaj`
- `cited_by_count`
- `primary_url`
- `openalex_url`

### 3.1. Configuración de columnas en v2

Desde la v2, la matriz de cribado ya no depende de una cabecera fija escrita en el código. Las columnas visibles se toman de:

- [metadata-columns.yaml](../assets/metadata-columns.yaml)

Esto permite:

- agregar o quitar metadata sin tocar el generador principal;
- mantener consistencia entre la plantilla de cribado y la corrida real;
- preparar perfiles distintos para futuras fuentes o cursos.

Scripts relacionados:

- [scripts/openalex_search.py](../scripts/openalex_search.py)
- [scripts/render_matrix_templates.py](../scripts/render_matrix_templates.py)
- [scripts/metadata_config.py](../scripts/metadata_config.py)

### 4. Export layer

El script exporta:

- `search/openalex/query.txt`
- `search/openalex/query_history.md` cuando la estrategia del caso haya sido refinada entre corridas
- `search/openalex/raw_results.json`
- `search/openalex/normalized_results.json`
- `search/openalex/normalized_results.csv`
- `search/openalex/search_log.md`
- `search/openalex/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

Además, `search_log.md` y `summary.json` registran:

- la ruta del archivo `metadata-columns.yaml` usado;
- la lista de columnas de cribado activas en esa corrida.
- alertas de volumen y muestreo cuando `max_results` o el total estimado requieren revisión metodológica.

Regla de trazabilidad del query:

- `search/openalex/query.txt` conserva la version vigente ejecutada en la corrida actual;
- cuando el caso refine la estrategia de busqueda de forma sustantiva, corresponde crear o actualizar `query_history.md` en el mismo directorio de salida;
- `query_history.md` debe conservar al menos:
  - la version inicial;
  - cada version refinada;
  - el motivo del refinamiento;
  - el cambio operativo observado, por ejemplo en volumen estimado o pertinencia del conjunto.

Después de aplicar decisiones de cribado, el flujo debe generar además:

- `screening/screening_decisions_<fase>.csv`
- `screening/screening_summary_<fase>.md`

Ejemplos típicos:

- `screening/screening_decisions_initial.csv`
- `screening/screening_summary_initial.md`
- `screening/screening_decisions_focused.csv`
- `screening/screening_summary_focused.md`
- `screening/screening_decisions_final.csv`
- `screening/screening_summary_final.md`

La actualización de decisiones mantiene sincronizados:

- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

La matriz de cribado generada desde OpenAlex incluye ahora, desde la primera corrida:

- `Primera afiliación`
- `País`
- `DOI`
- `Acceso abierto`
- `Texto completo accesible`
- `URL DOI`
- `URL de acceso`
- `URL OpenAlex`

Esto ayuda a:

- ubicar de forma operativa el origen institucional y geográfico del estudio;
- facilitar la lectura posterior del texto completo;
- documentar si el estudio parece accesible o no;
- apoyar deduplicación futura cuando se integren otras fuentes;
- dejar trazabilidad de cómo se localizó cada documento.

Nota metodológica:

- `Primera afiliación` y `País` se derivan de la primera afiliación institucional disponible en OpenAlex;
- por tanto, son metadata operativa útil para cribado y extracción, pero no deben interpretarse automáticamente como representación completa de todas las afiliaciones del estudio.

Regla para `Texto completo accesible`:

- `Sí` solo cuando una validación posterior confirmó acceso efectivo a una ruta de texto completo o acceso abierto.
- `Por verificar` cuando existe una ruta potencial, pero el acceso completo no se ha confirmado todavía.
- `No confirmado` cuando ya se intentó validar la ruta, pero no se pudo confirmar acceso efectivo a un full text útil.
- `No` cuando no hay una ruta útil o no se identificó una vía razonable de acceso.

La recomendación operativa es no validar esta columna sobre toda la búsqueda amplia. Conviene hacerlo después del cribado `focused`, cuando ya existe un subconjunto pequeño y priorizado.

Script para esa validación posterior:

- [scripts/validate_fulltext_access.py](../scripts/validate_fulltext_access.py)

Ejemplo:

```bash
python3 skills/prisma-ai-tutor/scripts/validate_fulltext_access.py \
  --matrix outputs/<corrida>/screening/screening_matrix.md \
  --decisions outputs/<corrida>/screening/screening_decisions_focused.csv
```

## Recuperación local de texto completo

Después del cribado `focused`, conviene intentar una recuperación local del texto completo solo para el subconjunto priorizado.

Script disponible:

- [scripts/download_fulltext.py](../scripts/download_fulltext.py)

Este script:

- usa la matriz y un CSV de decisiones;
- por defecto intenta recuperar registros `Incluir` y `Dudoso` del subconjunto priorizado;
- puede mostrar progreso periódico cada `n` registros con `PRISMA_PROGRESS_DOWNLOAD_EVERY` o `--progress-every`;
- permite filtrar decisiones concretas con `--decision` cuando se necesita un subconjunto mas estricto;
- omite por defecto estudios que no figuran como `Acceso abierto = Si`;
- intenta descargar el recurso localmente;
- puede reutilizar una sesión del navegador con `--cookies-file`;
- diferencia entre:
  - `downloaded_pdf`
  - `downloaded_fulltext_html`
  - `downloaded_landing_page`
  - `downloaded_blocked_page`
  - omisiones como `skipped_non_oa`
- guarda un log detallado y un resumen de la subfase.

Ejemplo:

```bash
python3 skills/prisma-ai-tutor/scripts/download_fulltext.py \
  --matrix outputs/<corrida>/screening/screening_matrix.md \
  --decisions outputs/<corrida>/screening/screening_decisions_focused.csv \
  --output-dir cases/ia-generativa-programacion/fulltext \
  --log outputs/<corrida>/fulltext/fulltext_download_log.csv \
  --summary outputs/<corrida>/fulltext/fulltext_recovery_summary.md \
  --config-file cases/ia-generativa-programacion/case.env
```

Ejemplo con cookies exportadas del navegador:

```bash
python3 skills/prisma-ai-tutor/scripts/download_fulltext.py \
  --matrix outputs/<corrida>/screening/screening_matrix.md \
  --decisions outputs/<corrida>/screening/screening_decisions_focused.csv \
  --output-dir cases/ia-generativa-programacion/fulltext \
  --log outputs/<corrida>/fulltext/fulltext_download_log.csv \
  --summary outputs/<corrida>/fulltext/fulltext_recovery_summary.md \
  --config-file cases/ia-generativa-programacion/case.env \
  --cookies-file ruta/a/browser-cookies.txt
```

Artefactos esperados:

- carpeta local de documentos fuente, por ejemplo `cases/<slug>/fulltext/`
- `outputs/<corrida>/fulltext/fulltext_download_log.csv`
- `outputs/<corrida>/fulltext/fulltext_recovery_summary.md`

Clasificación operativa recomendada:

- `pdf_fulltext`: PDF útil para revisión
- `html_fulltext`: HTML que contiene el artículo legible
- `landing_metadata_only`: landing con metadata o navegación, pero sin artículo útil para lectura final
- `blocked_or_error`: página de bloqueo, login, challenge o error

Nota importante:

- descargar un PDF o un HTML no significa que el agente ya esté leyendo el texto;
- para el cribado `final`, conviene preparar texto legible a partir de esos artefactos recuperados.

## Preparación de texto para revisión asistida

Después de recuperar PDFs o HTML útiles, conviene extraer texto plano a un directorio derivado dentro de `outputs/<corrida>/`.

Script disponible:

- [scripts/prepare_fulltext_review_text.py](../scripts/prepare_fulltext_review_text.py)

Ejemplo:

```bash
python3 skills/prisma-ai-tutor/scripts/prepare_fulltext_review_text.py \
  --input-dir cases/ia-generativa-programacion/fulltext \
  --output-dir outputs/<corrida>/fulltext/review_text \
  --download-log outputs/<corrida>/fulltext/fulltext_download_log.csv
```

Artefactos esperados:

- `outputs/<corrida>/fulltext/review_text/`
- `outputs/<corrida>/fulltext/fulltext_review_text_log.csv`
- `outputs/<corrida>/fulltext/fulltext_review_text_summary.md`

Recomendación metodológica:

- no confundir una `landing_metadata_only` con un `full text` útil;
- el `final` del apoyo automatizado debería usar primero los textos preparados desde `pdf_fulltext` o `html_fulltext`;
- cuando no se pueda recuperar el documento, el estudio no debe entrar al corpus final.
- para sitios con challenge como Cloudflare, la recuperación automática puede requerir cookies exportadas de una sesión del navegador que ya haya pasado el desafío.

Además genera un resumen rápido de calidad del conjunto con datos como:

- cantidad de registros con `DOI`;
- cantidad con `abstract`;
- cantidad tipo `article`;
- cantidad `open access`;
- distribución de idiomas;
- distribución de tipos documentales.

La query efectiva queda persistida en `search/openalex/query.txt` dentro del directorio de salida, para que pueda revisarse, corregirse y reutilizarse en la siguiente fase.

Nota de uso:

- el script permite recibir la query directamente o desde `--query-file`;
- sin embargo, dentro del flujo formal de `PRISMA-AI Tutor` se recomienda tratar `search/openalex/query.txt` como artefacto obligatorio de la fase de búsqueda.
- el script puede funcionar sin archivo de configuración, pero dentro del flujo formal de `PRISMA-AI Tutor` se fuerza el uso de un archivo `.env` en la Fase 3.

## Script disponible

Archivo:

- [scripts/openalex_search.py](../scripts/openalex_search.py)
- [scripts/apply_screening_decisions.py](../scripts/apply_screening_decisions.py)
- [scripts/render_matrix_templates.py](../scripts/render_matrix_templates.py)

## Ejemplos de uso

### Búsqueda simple

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  "software testing education" \
  --config-file skills/prisma-ai-tutor/assets/case.env.template
```

### Búsqueda usando configuración explícita de columnas

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  "software testing education" \
  --config-file cases/mi-caso/case.env \
  --metadata-config mi-columnas.yaml
```

### Búsqueda booleana simple

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py '"software engineering" AND education'
```

### Búsqueda booleana con operadores y paréntesis

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '("machine learning" OR "artificial intelligence") AND programming AND NOT thesis'
```

### Búsqueda acotada por fechas e idioma

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  "artificial intelligence programming education" \
  --from-date 2021-01-01 \
  --to-date 2025-12-31 \
  --language en \
  --max-results 100 \
  --config-file ruta/a/openalex.env
```

### Búsqueda con reintentos más conservadores

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '"software engineering" AND maintainability' \
  --max-results 150 \
  --config-file ruta/a/openalex.env \
  --max-retries 6 \
  --retry-delay 3 \
  --max-retry-wait 30
```

### Usar configuración desde archivo `.env`

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '"software engineering" AND maintainability' \
  --config-file ruta/a/openalex.env
```

### Ejemplo de contenido del archivo `.env` de caso

```env
PRISMA_AI_TUTOR_BASE_CONFIG=../../config/prisma-ai-tutor/base.env
PRISMA_AI_TUTOR_WORKSPACE_ROOT=../..
OPENALEX_QUERY_FILE=outputs/mi-corrida/search/openalex/query.txt
OPENALEX_OUT_DIR=outputs/mi-corrida
ZOTERO_ATTACHMENTS_DIR=cases/mi-caso/fulltext
ZOTERO_SCREENING_DECISIONS=outputs/mi-corrida/screening/screening_decisions_final.csv
ZOTERO_SCREENING_MATRIX=outputs/mi-corrida/screening/screening_matrix.csv
```

En el flujo formal del skill, esta es la opción preferida porque permite:

- separar la credencial compartida de los artefactos del caso;
- mantener trazabilidad de que existe una configuración validada;
- evitar escribir la API key directamente en la ficha o en documentos del protocolo.

### Búsqueda enfocada en artículos OA

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  "software engineering learning analytics" \
  --type article \
  --is-oa true \
  --source-in-doaj true \
  --max-results 80
```

### Incluir varios tipos documentales

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '"software engineering" AND maintainability' \
  --include-type article \
  --include-type review \
  --max-results 100
```

### Excluir tipos documentales no deseados

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '"software engineering" AND maintainability' \
  --exclude-type dissertation \
  --exclude-type preprint \
  --max-results 100
```

### Búsqueda sin stemming

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  '"software testing"' \
  --no-stem
```

### Búsqueda desde archivo

Archivo `query.txt`:

```text
("software engineering" OR "computer programming") AND education AND NOT thesis
```

Ejecutar:

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py --query-file query.txt --max-results 120
```

### Recuperar todos los resultados disponibles

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py "long covid" --fetch-all --allow-large-fetch
```

Usa esta opción con cuidado: puede tardar bastante y generar archivos grandes.

### Recuperar una cantidad grande pero acotada

```bash
python3 skills/prisma-ai-tutor/scripts/openalex_search.py \
  "long covid" \
  --max-results 2000
```

### Qué ocurre si el volumen es muy grande

Si `OpenAlex` reporta más de `2000` resultados y usas `--fetch-all` sin protección adicional, el script se detendrá y te pedirá una decisión explícita:

- usar `--allow-large-fetch` para continuar;
- o usar `--max-results N` para limitar la descarga.

### Política metodológica simplificada para `max_results`

- `max_results` es la muestra objetivo, no una selección metodológica final.
- debe existir un umbral operativo configurable, recomendado en `500`.
- si `max_results` supera ese umbral, el flujo debe advertir posible latencia.
- si OpenAlex reporta más resultados que `max_results`, el usuario decide si autoriza trabajar con muestra acotada o si prefiere refinar la query.
- si OpenAlex reporta más de `1000` resultados estimados, corresponde refinar la query antes del cribado inicial.
- el orden `relevance_score:desc` de OpenAlex solo debe usarse como última instancia operativa si el refinamiento no reduce suficientemente el volumen.

## Actualización de la misma matriz de cribado

La intención del flujo es que el cribado inicial actualice la misma `screening/screening_matrix.md` generada por la búsqueda.

Aplicar decisiones a la matriz:

```bash
python3 skills/prisma-ai-tutor/scripts/apply_screening_decisions.py \
  --matrix outputs/<corrida>/screening/screening_matrix.md \
  --decisions outputs/<corrida>/screening/screening_decisions_initial.csv
```

Comportamiento actual:

- actualiza `screening/screening_matrix.md`
- genera automaticamente un resumen en la misma carpeta del CSV de decisiones
- si el CSV se llama `screening_decisions_initial.csv`, `screening_decisions_focused.csv` o `screening_decisions_final.csv`, el resumen se nombra automaticamente por fase
- `--summary` sigue disponible cuando se necesita una ruta personalizada

Si quieres escribir el resumen en otra ruta, puedes usar `--summary`.

## Qué hace hoy y qué no hace todavía

### Ya resuelve

- búsqueda automatizada en OpenAlex;
- paginación por cursor;
- normalización básica;
- exportación a formatos útiles para cribado;
- persistencia de la cadena usada en `query.txt`;
- bitácora inicial de trazabilidad.
- resumen de la búsqueda mostrado en pantalla al finalizar la ejecución.
- mensajes de progreso por página durante descargas largas.
- snapshot rápido de calidad del conjunto recuperado.
- reintentos automáticos ante errores transitorios como `429 Too Many Requests`.
- corte rápido cuando `Retry-After` es excesivo.
- soporte para autenticación y configuración base desde archivo `.env`.
- filtrado explícito por inclusión o exclusión de tipos documentales.
- generación automática de un resumen de cribado al aplicar decisiones, con posibilidad de nombrarlo por fase usando `--summary`.

### Pendiente para la siguiente iteración

- deduplicación entre múltiples fuentes;
- madurar la vía semiasistida de `SciELO`;
- exportación directa al formato final del protocolo;
- clasificación preliminar automática por elegibilidad;
- integración con fuentes adicionales condicionadas, como `Scopus` con CSV/API o `PubMed` cuando el tema sea biomédico o de salud.

## Relación con el skill

Este MVP encaja entre la `Fase 4. Búsqueda` y la `Fase 5. Cribado (selección de estudios)` del skill:

1. El estudiante define pregunta, criterios y cadena.
2. El script recupera una muestra inicial desde OpenAlex.
3. Se genera una matriz de cribado inicial.
4. El análisis humano decide inclusión, exclusión o duda.

## Decisiones técnicas

- Se usa `urllib` de la librería estándar para evitar dependencias externas.
- Se exporta una copia cruda del resultado para auditoría.
- El script puede cargar configuración básica desde un archivo `.env`.
- Se prioriza `title_and_abstract.search` como modo por defecto, porque es más estable para revisiones sistemáticas que una búsqueda amplia de full text.
- El script acepta consultas booleanas de OpenAlex con `AND`, `OR`, `NOT`, paréntesis y comillas dobles.
- Puede desactivar stemming con `--no-stem` cuando convenga una búsqueda más literal.
- Puede incluir o excluir tipos documentales con `--include-type` y `--exclude-type`.
- Puede recuperar todos los resultados disponibles con `--fetch-all`.
- Si el volumen es grande, exige confirmación explícita con `--allow-large-fetch` o una descarga acotada con `--max-results`.
- Muestra progreso por página para que no parezca una ejecución bloqueada.
- Imprime en consola el mismo resumen metodológico que guarda en `search_log.md`.
- Reintenta automáticamente cuando OpenAlex responde con errores transitorios o límites temporales.
- Si OpenAlex pide una espera demasiado larga, falla rápido y sugiere reintentar después o usar un correo real en `--mailto`.
- Se conserva el abstract reconstruido desde `abstract_inverted_index` cuando está disponible.

## Referencias oficiales

- OpenAlex works: https://docs.openalex.org/api-entities/works
- OpenAlex filter works: https://docs.openalex.org/api-entities/works/filter-works
- OpenAlex search works: https://docs.openalex.org/api-entities/works/search-works
- OpenAlex paging: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/paging
- OpenAlex rate limits and authentication: https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
