# Automatización de búsquedas con DOAJ

Fecha de referencia: 2026-05-19.

## Propósito

Esta guía describe cómo usar `DOAJ` como fuente automatizada dentro de `PRISMA-AI Tutor`, aprovechando la API oficial de artículos para poblar artefactos de búsqueda y una matriz de cribado inicial basada en `título + resumen`.

## Cuándo conviene usar DOAJ

Usa `DOAJ` cuando:

- te interese literatura abierta y revisada por pares;
- necesites una fuente programática con `abstract`, `DOI` y `fulltext link`;
- quieras complementar `OpenAlex` con una fuente OA de alta calidad editorial.

No lo trates como sustituto automático de infraestructuras regionales como `SciELO` cuando el objeto de análisis sea la plataforma regional misma.

## Qué recupera el script

El script:

- consulta la API oficial de artículos de DOAJ;
- pagina resultados;
- filtra localmente por `abstract` y por año si el caso lo exige;
- normaliza los resultados al esquema común del skill;
- genera artefactos de búsqueda en `search/doaj/`;
- y actualiza la matriz común en `screening/`.

Script principal:

- [scripts/doaj_search.py](../scripts/doaj_search.py)

## Artefactos de salida

Dentro de `outputs/<corrida>/` se generan:

- `search/doaj/query.txt`
- `search/doaj/raw_results.json`
- `search/doaj/normalized_results.json`
- `search/doaj/normalized_results.csv`
- `search/doaj/search_log.md`
- `search/doaj/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

Además, el índice de corrida:

- `run_overview.md`

se actualiza automáticamente.

## Campos especialmente útiles de DOAJ

La API de DOAJ ya devuelve de forma bastante directa:

- `title`
- `abstract`
- `author`
- `affiliation`
- `doi`
- `journal.title`
- `journal.country`
- `journal.language`
- `link` a full text

Eso hace que DOAJ encaje bien con el cribado por `título + resumen`.

## Configuración mínima en `case.env`

Variables esperadas:

- `DOAJ_QUERY_FILE`
- `DOAJ_FROM_YEAR`
- `DOAJ_TO_YEAR`
- `DOAJ_REQUIRE_ABSTRACT`
- `DOAJ_PAGE_SIZE`
- `DOAJ_MAX_RESULTS`
- `DOAJ_OUT_DIR`
- `DOAJ_QUERY_OUTPUT_NAME`
- `DOAJ_METADATA_CONFIG`

Ejemplo:

```env
DOAJ_QUERY_FILE=outputs/mi-corrida/search/doaj/query.txt
DOAJ_REQUIRE_ABSTRACT=true
DOAJ_PAGE_SIZE=20
DOAJ_MAX_RESULTS=100
DOAJ_OUT_DIR=outputs/mi-corrida
```

## Ejemplos de uso

Consulta directa:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/doaj_search.py \
  --max-results 30 \
  --page-size 10 \
  "OpenAlex"
```

Consulta desde archivo:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/doaj_search.py \
  --config-file cases/mi-caso/case.env
```

Con filtro local por años:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/doaj_search.py \
  --query-file outputs/mi-corrida/search/doaj/query.txt \
  --from-year 2020 \
  --to-year 2025 \
  --max-results 50 \
  --out-dir outputs/mi-corrida
```

## Regla metodológica de volumen

La misma lógica acordada para otras fuentes sigue aplicando:

- `max_results` es muestra objetivo, no selección metodológica final;
- si la fuente reporta más resultados que `max_results`, el recorte debe tratarse como muestra operativa;
- si el volumen es demasiado alto, conviene refinar la query antes del cribado inicial.

## Integración multi-fuente

Si el caso usa más de una fuente, la recomendación es:

1. ejecutar cada búsqueda en su subcarpeta:
   - `search/openalex/`
   - `search/doaj/`
   - `search/redalyc/` si el caso la activa;
2. fusionar antes del cribado común;
3. usar la matriz fusionada como única base para `initial`.

Si el caso ya tiene declaradas varias fuentes en `case.env`, el punto de entrada preferido para Fase 3 es:

- [scripts/phase3_multisource_search.py](../scripts/phase3_multisource_search.py)

Script de fusión:

- [scripts/merge_search_results.py](../scripts/merge_search_results.py)

Ejemplo:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/merge_search_results.py \
  --run-dir outputs/mi-corrida \
  --source openalex \
  --source doaj
```

Artefactos de fusión:

- `search/merged_normalized_results.json`
- `search/merged_normalized_results.csv`
- `search/merged_summary.json`
- `search/source_merge_log.md`
- `search/source_merge_log.csv`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

## Limitaciones actuales

- por ahora los filtros de año se aplican localmente, no como sintaxis avanzada de query a la API;
- la fusión multi-fuente deduplica primero por DOI y luego por combinación normalizada de `titulo + año`;
- si dos registros equivalentes no comparten DOI y el título varía mucho entre fuentes, pueden requerir revisión humana.
