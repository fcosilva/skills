# Automatización de búsquedas con PubMed

Fecha de referencia: 2026-05-25.

## Propósito

Esta guía define cómo usar `PubMed` como fuente programática abierta dentro de `PRISMA-AI Tutor`.

PubMed es especialmente útil para temas de:

- salud;
- medicina;
- biomedicina;
- bioética;
- educación médica;
- integridad científica en ciencias de la salud;
- publicación científica biomédica;
- IA aplicada a salud, medicina o investigación biomédica.

## Regla de activación por tema

Si el agente detecta que el tema del estudiante está claramente relacionado con salud, medicina, biomedicina, bioética, educación médica o investigación biomédica, debe proponer PubMed como fuente activa.

PubMed no reemplaza automáticamente a OpenAlex o DOAJ. Se añade como fuente especializada cuando el tema lo justifica.

Ejemplo de configuración:

```env
PRISMA_PHASE3_SOURCES=openalex,doaj,semanticscholar,pubmed,redalyc
```

Si además el caso usa Scopus:

```env
PRISMA_PHASE3_SOURCES=openalex,doaj,semanticscholar,pubmed,scopus,redalyc
```

## API usada

El script usa NCBI E-utilities:

- `ESearch` para recuperar PMIDs.
- `EFetch` para recuperar registros PubMed en XML.

La API key es opcional, pero recomendada.

## Configuración mínima

```env
PUBMED_QUERY_FILE=outputs/mi-corrida/search/pubmed/query.txt
PUBMED_REQUIRE_ABSTRACT=true
PUBMED_MAX_RESULTS=100
PUBMED_OUT_DIR=outputs/mi-corrida
```

Opcionalmente en `base.env`:

```env
PUBMED_API_KEY=
PUBMED_EMAIL=tu_correo@institucion.edu
```

## Query PubMed

Usa sintaxis PubMed. Para cribado con título y resumen, recomienda campos explícitos:

```text
("research misconduct"[Title/Abstract] OR plagiarism[Title/Abstract] OR retraction[Title/Abstract])
```

Con rango de años, el script puede agregar automáticamente:

```text
AND (2015:2025[pdat])
```

## Script

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/pubmed_search.py \
  --config-file cases/mi-caso/case.env
```

## Artefactos

Dentro de `outputs/<corrida>/`:

- `search/pubmed/query.txt`
- `search/pubmed/raw_results.json`
- `search/pubmed/normalized_results.json`
- `search/pubmed/normalized_results.csv`
- `search/pubmed/search_log.md`
- `search/pubmed/summary.json`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`

## Limitaciones

- PubMed no es una fuente generalista; úsala sólo cuando el tema tenga pertinencia biomédica o de salud.
- No todos los registros PubMed tienen DOI.
- No todos los registros PubMed tienen abstract; por eso `PUBMED_REQUIRE_ABSTRACT=true` puede reducir el conjunto exportado.
- PubMed no garantiza texto completo; la recuperación de full text sigue ocurriendo después, en Fase 6.
