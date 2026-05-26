# Automatización con Semantic Scholar

Esta guía define cómo usar `Semantic Scholar` como fuente por defecto y complementaria dentro de `PRISMA-AI Tutor`.

Semantic Scholar no reemplaza las búsquedas booleanas controladas de otras fuentes. Su aporte principal es ampliar sensibilidad mediante búsqueda semántica por relevancia, especialmente cuando el tema puede expresarse como concepto natural.

## Rol metodológico

- Se usa en Fase 3 como fuente programática por defecto junto con `OpenAlex`, `DOAJ` y `Redalyc`.
- Su query debe redactarse como frase o concepto natural, no como sintaxis booleana estricta.
- No debe documentarse como búsqueda por campo `title`, `abstract` o `keywords`.
- Puede devolver `abstract`, DOI, autores, año, tipo de publicación, conteo de citas, URL de Semantic Scholar y PDF OA cuando está disponible.
- El solapamiento con otras fuentes es esperado y se resuelve en la fusión/deduplicación de Fase 3.

## Recomendación de query

En vez de traducir literalmente una cadena como:

```text
("large language models" OR ChatGPT) AND ("programming education" OR "software development education")
```

usa una versión semántica:

```text
large language models in programming education and software development learning outcomes
```

La estrategia conceptual puede ser la misma que en otras fuentes, pero la sintaxis no.

## Configuración base

La API funciona sin key en algunos contextos, pero puede responder `429 Too Many Requests`. Por eso se recomienda definir la key en `base.env`:

```env
SEMANTIC_SCHOLAR_API_KEY=
SEMANTIC_SCHOLAR_MAX_RETRIES=3
SEMANTIC_SCHOLAR_RETRY_DELAY=2
SEMANTIC_SCHOLAR_MAX_RETRY_WAIT=60
```

No guardes claves reales dentro del repositorio.

## Configuración por caso

```env
PRISMA_PHASE3_SOURCES=openalex,doaj,semanticscholar,redalyc

SEMANTIC_SCHOLAR_QUERY_FILE=outputs/mi-corrida/search/semanticscholar/query.txt
SEMANTIC_SCHOLAR_FROM_YEAR=
SEMANTIC_SCHOLAR_TO_YEAR=
SEMANTIC_SCHOLAR_REQUIRE_ABSTRACT=true
SEMANTIC_SCHOLAR_REQUIRE_OPEN_ACCESS=false
SEMANTIC_SCHOLAR_LIMIT=50
SEMANTIC_SCHOLAR_MAX_RESULTS=100
SEMANTIC_SCHOLAR_OUT_DIR=outputs/mi-corrida
SEMANTIC_SCHOLAR_QUERY_OUTPUT_NAME=query.txt
```

Si el caso usa Fase 3 multi-fuente, `SEMANTIC_SCHOLAR_OUT_DIR` debe apuntar al mismo directorio de corrida que las demás fuentes activas.

## Ejecución individual

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/semanticscholar_search.py \
  --config-file cases/mi-caso/case.env
```

También puede ejecutarse con una query directa para prueba:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/semanticscholar_search.py \
  "large language models in programming education" \
  --max-results 10 \
  --out-dir outputs/semanticscholar-smoketest
```

## Artefactos esperados

- `search/semanticscholar/query.txt`
- `search/semanticscholar/raw_results.json`
- `search/semanticscholar/normalized_results.json`
- `search/semanticscholar/normalized_results.csv`
- `search/semanticscholar/search_log.md`
- `search/semanticscholar/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

En modo multi-fuente, la matriz común final debe ser la generada después de `merge_search_results.py`.

## Limitaciones

- No soporta sintaxis booleana estricta en `query`.
- No permite restringir formalmente la búsqueda a `title`, `abstract` o `keywords`.
- Los filtros por año sí se envían a la API mediante `year`.
- `openAccessPdf` es una señal útil para Fase 6, pero no reemplaza la validación de texto completo.
- Si la API reporta un volumen muy alto, corresponde refinar la query semántica antes de Fase 4.

## Fuentes oficiales

- Semantic Scholar API product page: https://www.semanticscholar.org/product/api
- Semantic Scholar Graph API docs: https://api.semanticscholar.org/api-docs/graph
