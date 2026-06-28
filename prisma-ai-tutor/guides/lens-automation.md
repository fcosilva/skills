# Automatización con Lens

Esta guía define cómo usar `Lens` como fuente programática opcional dentro de `PRISMA-AI Tutor`.

Lens Scholarly API requiere una `API key` aprobada. Cuando está disponible, puede aportar una búsqueda estructurada en literatura académica con buenos identificadores externos para deduplicación.

## Rol metodológico

- Se usa en Fase 3 como fuente programática opcional activada cuando existe `LENS_API_KEY`.
- En esta configuración del skill, la query se envía como `query_string` sobre `title` y `abstract`.
- Puede devolver `abstract`, DOI, autores, año, tipo de publicación, fuente, Lens ID, PubMed ID y OpenAlex ID cuando están disponibles.
- El solapamiento con OpenAlex, DOAJ, Semantic Scholar, PubMed, Scopus o Redalyc es esperado y se resuelve en la fusión/deduplicación de Fase 3.

## Recomendación de query

Lens admite booleanos simples dentro de `query_string`. Una query razonable sería:

```text
("research misconduct" OR plagiarism OR retraction) AND ("scientific communication" OR publishing)
```

La estrategia conceptual puede ser común con otras fuentes, pero conviene guardar una versión propia en `search/lens/query.txt`.

## Configuración base

Define la key y parámetros de robustez en `base.env`:

```env
LENS_API_KEY=
LENS_MAX_RETRIES=3
LENS_RETRY_DELAY=2
LENS_MAX_RETRY_WAIT=60
```

No guardes claves reales dentro del repositorio.

## Configuración por caso

```env
PRISMA_PHASE3_SOURCES=openalex,doaj,semanticscholar,lens,redalyc

LENS_QUERY_FILE=outputs/mi-corrida/search/lens/query.txt
LENS_FROM_YEAR=
LENS_TO_YEAR=
LENS_PUBLICATION_TYPE=journal article
LENS_REQUIRE_ABSTRACT=true
LENS_REQUIRE_OPEN_ACCESS=false
LENS_PAGE_SIZE=50
LENS_MAX_RESULTS=100
LENS_OUT_DIR=outputs/mi-corrida
LENS_QUERY_OUTPUT_NAME=query.txt
```

Si el caso usa Fase 3 multi-fuente, `LENS_OUT_DIR` debe apuntar al mismo directorio de corrida que las demás fuentes activas.

## Ejecución individual

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/lens_search.py \
  --config-file cases/mi-caso/case.env
```

También puede ejecutarse con una query directa para prueba:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/lens_search.py \
  '"long covid" AND neuromuscular' \
  --from-year 2020 \
  --to-year 2026 \
  --max-results 10 \
  --out-dir outputs/lens-smoketest
```

## Artefactos esperados

- `search/lens/query.txt`
- `search/lens/raw_results.json`
- `search/lens/normalized_results.json`
- `search/lens/normalized_results.csv`
- `search/lens/search_log.md`
- `search/lens/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

En modo multi-fuente, la matriz común final debe ser la generada después de `merge_search_results.py`.

## Limitaciones

- Requiere `LENS_API_KEY`; sin key la fuente no debe activarse.
- La disponibilidad de `abstract`, DOI, OpenAlex ID o PubMed ID depende del registro.
- `LENS_PUBLICATION_TYPE=journal article` aproxima el filtro de artículos, pero no sustituye la verificación humana de pertinencia y revisión por pares.
- `LENS_REQUIRE_OPEN_ACCESS=true` puede reducir sensibilidad en Fase 3; normalmente se deja `false` y se valida texto completo en Fase 6.
- Si Lens reporta un volumen muy alto, corresponde refinar la query antes de Fase 4.

## Fuentes oficiales

- Lens API docs: https://docs.api.lens.org/
- Lens API getting started: https://docs.api.lens.org/getting-started.html
- Lens API terms: https://about.lens.org/lens-api-terms-of-use/
