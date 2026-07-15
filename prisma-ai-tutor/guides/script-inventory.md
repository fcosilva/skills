# Inventario de scripts

Esta tabla ayuda al agente a elegir herramientas existentes antes de crear scripts auxiliares en `scratch/`.

Regla práctica:

- no crear scripts nuevos para tareas ya cubiertas por esta tabla;
- si falta una capacidad del flujo, documentar la brecha antes de crear una utilidad temporal;
- cualquier script temporal debe quedar fuera del flujo oficial y no debe reemplazar los artefactos esperados del skill.
- durante una corrida de caso, no editar scripts del skill; reportar bugs o solicitudes de cambio en `cases/<slug>/agent_reports/`.

| Script | Fase principal | Para qué sirve | Entradas clave | Salidas esperadas |
|---|---|---|---|---|
| `openalex_search.py` | Fase 3 | Buscar en OpenAlex y normalizar resultados | `OPENALEX_QUERY_FILE`, filtros, `case.env` | `search/openalex/*`, `screening/screening_matrix.*` |
| `doaj_search.py` | Fase 3 | Buscar artículos en DOAJ | `DOAJ_QUERY_FILE`, años, `case.env` | `search/doaj/*`, `screening/screening_matrix.*` |
| `semanticscholar_search.py` | Fase 3 | Buscar en Semantic Scholar con query semántica | `SEMANTIC_SCHOLAR_QUERY_FILE`, API key recomendada | `search/semanticscholar/*`, `screening/screening_matrix.*` |
| `lens_search.py` | Fase 3 | Buscar en Lens Scholarly API con query sobre título/resumen | `LENS_QUERY_FILE`, `LENS_API_KEY` | `search/lens/*`, `screening/screening_matrix.*` |
| `redalyc_search.py` | Fase 3 | Buscar en Redalyc con API key | `REDALYC_QUERY_FILE`, `REDALYC_SEARCH_FIELD` | `search/redalyc/*`, `screening/screening_matrix.*` |
| `pubmed_search.py` | Fase 3 | Buscar en PubMed sin mutar la query conceptual; registra aparte la query efectiva | `PUBMED_QUERY_FILE`, años, API key opcional | `query.txt`, `effective_query.txt`, resultados y matriz |
| `scopus_search.py` | Fase 3 | Buscar en Scopus vía API cuando hay permisos suficientes | `SCOPUS_QUERY_FILE`, API key | `search/scopus/*`, `screening/screening_matrix.*` |
| `scopus_import_csv.py` | Fase 3 | Importar CSV exportado manualmente desde Scopus | `SCOPUS_CSV_FILE` | `search/scopus/*`, `screening/screening_matrix.*` |
| `scielo_search.py` | Fase 3 experimental | Búsqueda semiasistida/experimental en SciELO Search | `SCIELO_QUERY_FILE` | `search/scielo/*`, `screening/screening_matrix.*` |
| `phase3_multisource_search.py` | Fase 3 | Ejecutar fuentes activas en secuencia y fusionar | `PRISMA_PHASE3_SOURCES`, `case.env` | `search/<fuente>/*`, `search/merged_*`, matriz fusionada |
| `merge_search_results.py` | Fase 3 | Fusionar y deduplicar resultados normalizados | `search/<fuente>/normalized_results.json` | `search/merged_*`, `source_merge_log.*`, matriz fusionada |
| `apply_screening_decisions.py` | Fases 4, 5 y 7 | Aplicar decisiones de cribado o selección final a la matriz | `screening_decisions_<fase>.csv`, matriz | matriz actualizada, CSV actualizado, resumen de fase |
| `summarize_screening.py` | Fases 4, 5 y 7 | Resumir decisiones ya registradas | CSV de decisiones | resumen Markdown |
| `validate_fulltext_access.py` | Fase 6 | Verificar accesibilidad remota probable sin promoverla todavía a `Si`; admite progreso y reanudación | matriz CSV, decisiones focused | log incremental y matriz con estado provisional |
| `download_fulltext.py` | Fase 6 | Recuperar PDF/HTML por vías legítimas, solo desde ubicaciones OA de descubrimiento, con checkpoints y reanudación verificada | matriz, decisiones focused, DOI, configuración | `fulltext_attempt_log.csv`, `fulltext_download_log.csv`, resumen y archivos fuente |
| `audit_fulltext_recovery.py` | Fase 6 | Reauditar archivos locales y corregir falsos PDF, landing o bloqueos | `fulltext_download_log.csv`, archivos locales | `fulltext_content_audit.csv`, resumen y log corregido con `--apply` |
| `prepare_fulltext_review_text.py` | Fase 6 | Verificar legibilidad e identidad bibliográfica, poner incompatibles en cuarentena y sincronizar todo el subconjunto | log, carpeta fulltext, matriz y decisiones | `review_text/`, cuarentena, log, resumen y matriz sincronizada |
| `fulltext_utils.py` | Soporte Fase 6 | Detectar firma PDF, cuerpo HTML, challenges, landings conocidas, enlaces secundarios e identidad bibliográfica | payload local o descargado y metadata esperada | clasificación y evidencia reutilizable |
| `prepare_zotero_import.py` | Fase 8 | Preparar metadata del corpus, priorizar resultados fusionados y rechazar manifiestos vacíos o duplicados | selección final, matriz, resultados normalizados | paquete de importación Zotero validado |
| `sync_zotero_mcp.py` | Fase 8 | Sincronizar ítems con bloqueo por colección para evitar carreras | paquete de importación, configuración Zotero | acciones y resumen Zotero |
| `write_zotero_notes.py` | Fase 8 y notas posteriores | Crear notas hijas, consolidar matrices relacionales y exigir validación humana para extracción/calidad | decisiones, matrices, gate humano | notas por fase y logs |
| `validate_human_review_gate.py` | Fases 9 y 10 | Impedir el cierre mientras existan filas asistidas no validadas | matriz CSV/Markdown, columnas configurables | JSON de gate y código de salida 0/1 |
| `audit_synthesis_links.py` | Fase 11 | Validar pares M/L, destinos, tipos de archivo, rangos de línea y hard wraps | síntesis narrativa Markdown | `study_link_audit.json` y código de salida 0/1 |
| `run_outputs.py` | Todas | Regenerar índice y resúmenes de corrida | `outputs/<corrida>/` | `run_overview.md`, trazas y resúmenes derivados |
| `render_matrix_templates.py` | Soporte | Renderizar plantillas reutilizables | assets del skill | matrices/plantillas renderizadas |

## Nota sobre cribado

El skill no delega el cribado inicial al usuario. El agente debe producir una propuesta de decisiones en `screening_decisions_initial.csv` y aplicarla con `apply_screening_decisions.py`. Después de eso, el usuario revisa, corrige o aprueba.

Lo mismo aplica para `focused`: el agente propone el cribado focused, deja trazabilidad y luego pide revisión humana antes de avanzar.
