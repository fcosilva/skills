# Automatización e importación de búsquedas con Scopus

Fecha de referencia: 2026-05-24.

## Propósito

Esta guía define cómo usar `Scopus` como fuente adicional dentro de `PRISMA-AI Tutor`.

Scopus puede operar en dos modos:

- `api`: consulta automática mediante Scopus Search API.
- `manual_csv`: búsqueda manual en la interfaz de Scopus, exportación CSV e importación del CSV al flujo.

## Recomendación metodológica

Para el flujo formal del skill, la vía recomendada es `manual_csv` cuando el cribado requiere `título + resumen`.

Motivo:

- Scopus Search API permite buscar con `TITLE-ABS-KEY(...)`;
- pero con una API key básica, la vista `STANDARD` devuelve metadata y no devuelve el abstract;
- las vistas `COMPLETE`, `META_ABS` o `FULL` pueden requerir permisos adicionales;
- por tanto, la API puede servir para descubrimiento automático, pero no siempre entrega el resumen necesario para cribado.

## Opción 1. Scopus automático vía API

Usa esta opción cuando:

- tienes una API key Elsevier válida;
- aceptas que la respuesta puede no traer abstract;
- o tu institución tiene permisos suficientes para vistas con abstract.

Configuración:

```env
SCOPUS_MODE=api
SCOPUS_API_KEY=
SCOPUS_QUERY_FILE=outputs/mi-corrida/search/scopus/query.txt
SCOPUS_VIEW=STANDARD
SCOPUS_REQUIRE_ABSTRACT=false
SCOPUS_OUT_DIR=outputs/mi-corrida
```

Script:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/scopus_search.py \
  --config-file cases/mi-caso/case.env
```

Artefactos:

- `search/scopus/query.txt`
- `search/scopus/raw_results.json`
- `search/scopus/normalized_results.json`
- `search/scopus/normalized_results.csv`
- `search/scopus/search_log.md`
- `search/scopus/summary.json`

## Opción 2. Scopus semiasistido con CSV

Usa esta opción cuando:

- necesitas abstracts para el cribado;
- el API no entrega abstracts por permisos;
- el estudiante puede entrar a Scopus desde la biblioteca institucional;
- quieres mantener trazabilidad sin depender de scraping.

Secuencia:

1. El skill genera y guarda la query en `search/scopus/query.txt`.
2. El estudiante copia esa query en Scopus.
3. El estudiante exporta los resultados en CSV.
4. El archivo CSV se guarda en el workspace.
5. El skill importa el CSV con `scopus_import_csv.py`.

Pausa obligatoria:

- esta vía se prepara en Fase 2, no durante Fase 3;
- si `SCOPUS_MODE=manual_csv`, el agente debe detenerse al cierre de Fase 2 hasta que exista el CSV;
- no debe iniciar Fase 3 si `SCOPUS_CSV_FILE` está vacío o apunta a un archivo inexistente;
- cuando el CSV ya existe y `SCOPUS_CSV_FILE` está configurado, recién entonces puede pedir autorización para Fase 3.

Configuración:

```env
SCOPUS_MODE=manual_csv
SCOPUS_QUERY_FILE=outputs/mi-corrida/search/scopus/query.txt
SCOPUS_CSV_FILE=inputs/scopus/export.csv
SCOPUS_REQUIRE_ABSTRACT=true
SCOPUS_OUT_DIR=outputs/mi-corrida
```

Script:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/scopus_import_csv.py \
  --config-file cases/mi-caso/case.env
```

Campos recomendados en el CSV:

- `Title`
- `Abstract`
- `Year`
- `DOI`
- `Source title`
- `Authors`
- `Document Type`
- `Link`
- `EID`
- `Cited by`

## Uso en Fase 3 multi-fuente

Para agregar Scopus al orquestador:

```env
PRISMA_PHASE3_SOURCES=openalex,doaj,semanticscholar,lens,scopus,redalyc
PRISMA_PHASE3_AUTO_MERGE=true
```

El orquestador usa:

- `scopus_search.py` si `SCOPUS_MODE=api`;
- `scopus_import_csv.py` si `SCOPUS_MODE=manual_csv`.

## Regla de trazabilidad

Si se usa `manual_csv`, el agente debe registrar:

- query exacta usada en Scopus;
- fecha de búsqueda manual;
- nombre y ruta del CSV importado;
- filtros usados en la interfaz de Scopus;
- cantidad de resultados exportados;
- cantidad de resultados importados.

## Limitaciones

- La API Search con `STANDARD` no garantiza abstract en la respuesta.
- La API puede reportar muchos más resultados que los exportados por `SCOPUS_MAX_RESULTS`.
- El CSV depende de las columnas seleccionadas por el usuario al exportar.
- Si el CSV no incluye `Abstract`, el flujo debe advertirlo y, si `SCOPUS_REQUIRE_ABSTRACT=true`, excluir esas filas.
