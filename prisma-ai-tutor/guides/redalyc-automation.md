# Automatización de búsquedas con Redalyc

Fecha de referencia: 2026-05-22.

## Propósito

Esta guía describe cómo usar `Redalyc` como fuente regional programática dentro de `PRISMA-AI Tutor`, aprovechando su API documentada con `API key` para poblar artefactos de búsqueda. En el estado actual, la recuperación se aproxima mejor a `título + filtros metadata`; cuando la respuesta trae `dc_description`, ese campo se usa después como equivalente operativo de resumen para el cribado local.

## Cuándo conviene usar Redalyc

Usa `Redalyc` cuando:

- necesites una fuente regional iberoamericana con fuerte presencia latinoamericana;
- quieras complementar `OpenAlex` o `DOAJ` con cobertura regional más contextual;
- dispongas de una `API key` válida de Redalyc.

No lo trates como sustituto automático de `DOAJ` si tu interés principal es literatura OA global y homogénea. Su valor principal aquí es regional.

## Qué recupera el script

El script:

- consulta la API documentada de Redalyc con `token(apikey)`;
- recupera por un único `search_field` documentado de la API, normalmente `title`;
- puede combinar filtros metadata solo a nivel de la sintaxis de la API, pero no expone una búsqueda directa por resumen;
- recorre resultados por lotes usando el comportamiento observado de `page(...)`;
- filtra localmente por `dc_description` y por año si el caso lo exige;
- si la query contiene operadores booleanos, aplica un filtro local adicional para conservar solo registros cuyo `dc_title` o `dc_description` contengan al menos un término sustantivo de la query;
- normaliza los resultados al esquema común del skill;
- genera artefactos de búsqueda en `search/redalyc/`;
- y actualiza la matriz común en `screening/`.

Script principal:

- [scripts/redalyc_search.py](../scripts/redalyc_search.py)

## Artefactos de salida

Dentro de `outputs/<corrida>/` se generan:

- `search/redalyc/query.txt`
- `search/redalyc/raw_results.json`
- `search/redalyc/normalized_results.json`
- `search/redalyc/normalized_results.csv`
- `search/redalyc/search_log.md`
- `search/redalyc/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

Además, el índice de corrida:

- `run_overview.md`

se actualiza automáticamente.

## Campos especialmente útiles de Redalyc

En las pruebas reales con `API key`, Redalyc devolvió de forma útil:

- `dc_title`
- `dc_creator`
- `dc_description`
- `dc_date`
- `dc_type`
- `dc_language`
- `dc_source`
- `dc_rights`
- `recordIdentifier`

Eso permite construir un conjunto suficiente para cribado con `título + dc_description` cuando ese campo viene informado, aunque por ahora no siempre aparezca `DOI` ni `PDF URL` directa.

## Qué significa realmente `dc_description`

En las pruebas reales, `dc_description` se comporta como el `resumen` o `abstract` del artículo cuando el registro lo trae.

Importante:

- `dc_description` aparece en la **respuesta**;
- pero no existe un filtro documentado tipo `description(...)`, `abstract(...)` o `summary(...)` para consultarlo directamente en la API.

Por eso, en el flujo del skill:

- `Redalyc` recupera por `title` o por otro campo metadata documentado;
- y luego el agente criba localmente usando `title + dc_description` cuando ese campo está disponible.

## Qué hace y qué no hace `Multiple`

La sección `Multiple` de la documentación de Redalyc no agrega un campo textual nuevo.

Solo permite combinar filtros documentados separados por comas, por ejemplo:

- `title(...)`
- `language(...)`
- `country(...)`
- `subject(...)`
- `type(...)`

Eso sirve para refinar por metadata, pero no equivale a un `OR` entre `title` y `abstract`.

Además:

- `subject` filtra disciplina o descriptores temáticos;
- no reemplaza una búsqueda por resumen.

## Advertencia sobre operadores booleanos

No asumas que `OR`, `AND`, paréntesis o comillas se interpretan igual que en OpenAlex o DOAJ.

En Redalyc, una cadena como:

```text
"mala conducta cientifica" OR plagio OR retractacion
```

puede devolver ruido si se envía completa dentro de `title(...)`.

Por eso el script:

- conserva la query aprobada en `search/redalyc/query.txt`;
- ejecuta la consulta con la sintaxis disponible de Redalyc;
- y, si detecta operadores booleanos, filtra localmente los resultados para exigir presencia de términos sustantivos en `dc_title` o `dc_description`.

Si después de ese filtro Redalyc devuelve cero o muy pocos resultados, no debe forzarse su inclusión. Lo metodológicamente correcto es documentar baja cobertura de la fuente para esa query o crear una versión Redalyc más simple y trazada en `query_history.md`.

## Configuración mínima en `case.env`

Variables esperadas:

- `REDALYC_API_KEY`
- `REDALYC_QUERY_FILE`
- `REDALYC_SEARCH_FIELD`
- `REDALYC_FROM_YEAR`
- `REDALYC_TO_YEAR`
- `REDALYC_REQUIRE_ABSTRACT`
- `REDALYC_BATCH_SIZE`
- `REDALYC_MAX_RESULTS`
- `REDALYC_OUT_DIR`
- `REDALYC_QUERY_OUTPUT_NAME`
- `REDALYC_METADATA_CONFIG`

Ejemplo:

```env
REDALYC_API_KEY=TU_API_KEY_AQUI
REDALYC_QUERY_FILE=outputs/mi-corrida/search/redalyc/query.txt
REDALYC_SEARCH_FIELD=title
REDALYC_REQUIRE_ABSTRACT=true
REDALYC_BATCH_SIZE=10
REDALYC_MAX_RESULTS=100
REDALYC_OUT_DIR=outputs/mi-corrida
```

## Ejemplos de uso

Consulta directa:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/redalyc_search.py \
  --api-key TU_API_KEY_AQUI \
  --max-results 30 \
  "ciencia"
```

Consulta desde archivo:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/redalyc_search.py \
  --config-file cases/mi-caso/case.env
```

Con cambio de campo de búsqueda:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/redalyc_search.py \
  --api-key TU_API_KEY_AQUI \
  --search-field language \
  --max-results 50 \
  "plagio"
```

## Regla metodológica de volumen

La misma lógica acordada para otras fuentes sigue aplicando:

- `max_results` es muestra objetivo, no selección metodológica final;
- si la fuente sigue devolviendo lotes completos y se alcanza `max_results`, debe asumirse que puede haber más resultados;
- si el volumen es demasiado alto, conviene refinar la query antes del cribado inicial.

## Integración multi-fuente

Si el caso usa más de una fuente, la recomendación es:

1. ejecutar cada búsqueda en su subcarpeta:
   - `search/openalex/`
   - `search/doaj/`
   - `search/redalyc/`
2. fusionar antes del cribado común.

Si el caso declara una Fase 3 multi-fuente en `case.env`, el punto de entrada preferido es:

- [scripts/phase3_multisource_search.py](../scripts/phase3_multisource_search.py)

Script de fusión:

- [scripts/merge_search_results.py](../scripts/merge_search_results.py)

Ejemplo:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/merge_search_results.py \
  --run-dir outputs/mi-corrida \
  --source openalex \
  --source redalyc
```

## Limitaciones actuales

- la API de Redalyc usa una sintaxis propia y no expone, en las pruebas actuales, un total global tan claro como `OpenAlex` o `DOAJ`;
- la API documentada no expone un filtro directo por `abstract` o `dc_description`, así que no reproduce de forma simétrica la búsqueda `título + resumen` de otras fuentes;
- `Multiple` solo combina filtros metadata existentes; no crea una búsqueda libre por varios campos textuales;
- `sizePage(...)` no parece respetarse de forma completamente estable, así que el script recorre lotes de forma conservadora;
- no siempre aparece `DOI` ni enlace PDF directo en la respuesta;
- por ahora el script deja `primary_url` apuntando al artículo en Redalyc y marca el acceso como `Por verificar`.
