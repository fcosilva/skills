# PRISMA-AI Tutor

**Versión del repositorio / primera publicación:** `Versión 1`

`PRISMA-AI Tutor` es un agente/skill para acompañar mini revisiones sistemáticas de literatura en contextos formativos, especialmente en asignaturas iniciales de investigación en Desarrollo de Software.

Su foco no es sustituir el juicio académico del estudiante o del docente, sino:

- ayudar a delimitar temas y preguntas;
- construir estrategias de búsqueda;
- dejar trazabilidad por fases;
- apoyar el cribado y la extracción;
- mantener una separación clara entre automatización y decisión humana final.

## Propósito

Este agente está pensado para trabajos como:

- revisiones exploratorias o mini revisiones sistemáticas;
- temas de programación, IA en educación, ingeniería de software y áreas afines;
- cursos donde importa más aprender el proceso metodológico que producir una revisión exhaustiva a escala profesional.

## Alcance metodológico

El agente usa una versión reducida y pedagógica de `PRISMA 2020`.

Reglas básicas:

- no inventa referencias, DOI ni resultados;
- no afirma haber leído documentos no verificados;
- toda inclusión o exclusión debe justificarse;
- la lectura crítica final y la interpretación sustantiva siguen siendo responsabilidad humana.

## Estructura

```text
skills/
└── prisma-ai-tutor/
    ├── README.md
    ├── SKILL.md
    ├── assets/
    │   ├── extraction-matrix.md
    │   ├── extraction-summary.md
    │   ├── metadata-columns.yaml
    │   ├── base.env.template
    │   ├── case.env.template
    │   ├── protocol-template.md
    │   ├── quality-matrix.md
    │   ├── quality-summary.md
    │   ├── run-overview.md
    │   ├── screening-matrix.md
    │   ├── screening-trace.md
    │   └── student-case-template.md
    ├── guides/
    │   ├── automation-by-phases.md
    │   ├── database-selection-guide.md
    │   ├── doaj-automation.md
    │   ├── openalex-automation.md
    │   ├── script-inventory.md
    │   └── semanticscholar-automation.md
    ├── scripts/
    │   ├── openalex_search.py
    │   ├── scielo_search.py
    │   ├── doaj_search.py
    │   ├── redalyc_search.py
    │   ├── semanticscholar_search.py
    │   ├── apply_screening_decisions.py
    │   ├── validate_fulltext_access.py
    │   └── ...
    └── references/
        ├── constraints.md
        ├── methodology.md
        ├── quality-checklist.md
        └── workflow.md
```

Documentos de apoyo dentro del propio skill:

- [guides/automation-by-phases.md](guides/automation-by-phases.md)
- [guides/openalex-automation.md](guides/openalex-automation.md)
- [guides/doaj-automation.md](guides/doaj-automation.md)
- [guides/semanticscholar-automation.md](guides/semanticscholar-automation.md)
- [guides/redalyc-automation.md](guides/redalyc-automation.md)
- [guides/script-inventory.md](guides/script-inventory.md)
- [guides/database-selection-guide.md](guides/database-selection-guide.md)
- carpeta de casos reales: [cases](../../../cases)
- scripts de automatización: [scripts](scripts)

## Configuracion recomendada

Para evitar mezclar casos, el skill usa este modelo:

- un archivo base reutilizable con valores compartidos, ubicado fuera del skill;
- un archivo `case.env` dentro de cada carpeta de caso con rutas, query y artefactos de ese caso.

Variable de herencia usada por los scripts:

- `PRISMA_AI_TUTOR_BASE_CONFIG`
- `PRISMA_AI_TUTOR_WORKSPACE_ROOT`

Archivos esperados:

- `config/prisma-ai-tutor/base.env` o `~/.codex/prisma-ai-tutor/base.env`
- `cases/<slug-del-caso>/case.env`

Recomendación de uso:

- si normalmente trabajarás varios casos dentro del mismo repositorio, conviene `config/prisma-ai-tutor/base.env` en el workspace;
- si quieres reutilizar la misma configuración entre múltiples workspaces, conviene `~/.codex/prisma-ai-tutor/base.env`.

Diferencia de alcance:

- `base.env` contiene defaults compartidos, credenciales, retries y parámetros de entorno que rara vez cambian entre casos;
- `case.env` contiene las rutas, fuentes activas, filtros metodológicos, queries y artefactos específicos de un caso;
- `case.env` puede sobrescribir valores de `base.env` cuando un caso necesita una excepción puntual, pero no debería duplicar por defecto toda la configuración global.

Regla de resolución de rutas:

- las rutas internas del skill se resuelven desde el propio skill;
- las rutas operativas del caso, como `cases/` y `outputs/`, se resuelven contra `PRISMA_AI_TUTOR_WORKSPACE_ROOT` si está definido;
- si `PRISMA_AI_TUTOR_WORKSPACE_ROOT` no está definido, se usa el directorio actual desde el que se ejecuta el comando.

## Flujo recomendado

El flujo formal del agente se organiza por fases:

1. delimitación del tema;
2. construcción y validación de `query.txt`;
3. búsqueda automatizada;
4. cribado `initial`;
5. cribado `focused`;
6. validación de accesibilidad y recuperación local de full text;
7. selección final o evaluación de elegibilidad;
8. integración bibliográfica en Zotero;
9. extracción de evidencia;
10. evaluación de calidad;
11. síntesis narrativa y auditoría final.

Regla de ejecución:

- estas fases son secuenciales;
- no deben ejecutarse en paralelo sobre el mismo caso;
- cada fase debe cerrar sus artefactos antes de pasar a la siguiente.

Regla para Zotero:

- Zotero entra solo despues del `final` confirmado por el estudiante;
- no entra durante `initial`, `focused` ni `final` pendiente;
- su disparador correcto es `corpus final confirmado + configuracion minima disponible`.

Regla importante:

- `initial` y `focused` trabajan principalmente con `título + resumen + metadatos`;
- la selección final idealmente ya incorpora texto preparado para revision desde `pdf_fulltext` o `html_fulltext`;
- si no existe full text, el estudio no debe entrar a la selección final del corpus.
- la selección final solo se considera cerrada cuando el estudiante o docente confirma humanamente el corpus.
- Zotero debe recibir solo el conjunto ya confirmado en la selección final del estudiante.

## Punto de entrada para el estudiante

Cada corrida debería ofrecer un índice claro para no obligar al estudiante a abrir muchos archivos sin contexto.

Orden recomendado de lectura:

1. `case.md`
2. `outputs/<corrida>/run_overview.md`
3. resumen de la fase actual
4. matriz o CSV solo si hace falta revisar detalle

Plantilla sugerida para ese índice:

- [assets/run-overview.md](assets/run-overview.md)

Regla operativa:

- cuando una fase cierra mediante los scripts del skill, el índice `run_overview.md` y los resúmenes derivados disponibles deben actualizarse automáticamente.
- además, una corrida nueva puede sembrar automáticamente archivos base en `extraction/`, `quality/` y `synthesis/` como placeholders de trabajo.
- esos placeholders no significan que la fase ya esté cerrada; solo preparan la estructura y el punto de entrada.
- esos placeholders deben vivir dentro de `outputs/<corrida>/extraction/`, `outputs/<corrida>/quality/` y `outputs/<corrida>/synthesis/`.
- no se deben crear placeholders ni artefactos del caso en `outputs/` raíz.
- si aparecen archivos como `outputs/extraction/...` o `outputs/synthesis/...` fuera de `outputs/<corrida>/`, se consideran artefactos mal ubicados y deben corregirse antes de continuar el flujo.

## Regla de busqueda y muestreo

Para la transicion entre `Fase 3` y `Fase 4`, el skill sigue estas reglas:

- `max_results` es la muestra objetivo para exportacion y cribado, no una seleccion metodologica final;
- debe existir un umbral operativo configurable, recomendado en `500`, usando `PRISMA_MAX_RESULTS_THRESHOLD`;
- si `max_results` supera ese umbral, el flujo debe advertir posible latencia y pedir confirmacion o ajuste;
- si OpenAlex reporta mas resultados que `max_results`, el usuario decide si autoriza trabajar con muestra acotada o si prefiere refinar la query;
- si OpenAlex reporta mas de `1000` resultados estimados, corresponde refinar la query antes del cribado inicial;
- el orden de relevancia de OpenAlex solo debe usarse como ultima instancia operativa cuando el refinamiento no logra reducir suficientemente el volumen.

Reglas complementarias:

- cuando el caso lo exige, la Fase 3 debe trabajar solo con registros con `abstract` disponible, usando `OPENALEX_REQUIRE_ABSTRACT=true`;
- si el caso exige articulos revisados por pares, esto debe declararse metodologicamente y reflejarse al menos con `OPENALEX_TYPE=article`;
- OpenAlex no expone una bandera exacta de peer review, asi que la verificacion fina sigue siendo parte del cribado humano.

Regla para la matriz de cribado:

- entre `focused` y el cierre de la selección final puede existir edicion humana supervisada de la matriz;
- las columnas de decision pueden ajustarse manualmente;
- `Codigo` no debe cambiar, porque actua como clave de trazabilidad entre cribado, scripts y Zotero.

## Integración con Zotero

Cuando el estudiante ya confirmó manualmente la selección final, el siguiente paso recomendado es integrar el corpus seleccionado en Zotero.

Reglas acordadas para esta integración:

- deben entrar todos los estudios de la selección final, no solo los que tienen PDF accesible;
- si existe PDF local, el flujo actual lo copia primero a la carpeta configurada de Zotero;
- no es necesario adjuntar el `.txt` extraído;
- el ítem debe conservar también la URL de origen;
- si el ítem ya existe en Zotero, se debe complementar la metadata faltante;
- si el ítem ya existe pero está en otra colección, también debe añadirse a la colección destino indicada.
- además, el flujo puede crear varias notas hijas por ítem:
  - una nota mínima de selección final en Fase 8;
  - una nota nueva de extracción en Fase 9;
  - una nota nueva de calidad en Fase 10.

Regla operativa obligatoria:

- antes de lanzar Fase 8, el agente debe completar o corregir en `case.env` las variables `ZOTERO_SCREENING_DECISIONS` y `ZOTERO_SCREENING_MATRIX` con los artefactos reales de la corrida final vigente;
- la integración en Zotero no queda cerrada solo con `prepare_zotero_import.py` o `sync_zotero_mcp.py`;
- la Fase 8 se considera completa únicamente cuando también se ejecuta explícitamente `write_zotero_notes.py --phase screening` o un paso equivalente que cree la nota hija mínima de selección final;
- el agente debe tratar la creación de notas como un subpaso obligatorio y verificable, no como un efecto implícito de la sincronización bibliográfica.

Configuración esperada para esta futura integración:

- la configuración operativa debe vivir en el archivo `.env` del proyecto;
- el script de integración con Zotero leerá desde ahí, como mínimo:
  - nombre de la librería;
  - nombre de la colección;
  - ruta de la carpeta local fuente con PDFs;
  - ruta de la carpeta que Zotero usa para enlazar o almacenar PDFs;
  - ruta de los artefactos de la selección final que se usarán como fuente de verdad.

Parámetros ya reservados en la plantilla `.env`:

- `ZOTERO_LIBRARY`
- `ZOTERO_MCP_URL`
- `ZOTERO_COLLECTION`
- `ZOTERO_ATTACHMENTS_DIR`
- `ZOTERO_LIBRARY_FILES_DIR`
- `ZOTERO_SCREENING_DECISIONS`
- `ZOTERO_SCREENING_MATRIX`

Scripts ya disponibles para esta integración:

- [scripts/prepare_zotero_import.py](scripts/prepare_zotero_import.py)
- [scripts/sync_zotero_mcp.py](scripts/sync_zotero_mcp.py)
- [scripts/write_zotero_notes.py](scripts/write_zotero_notes.py)
- [scripts/zotero_mcp_client.py](scripts/zotero_mcp_client.py)

Secuencia recomendada para Fase 8:

1. `prepare_zotero_import.py`
2. `sync_zotero_mcp.py`
3. `write_zotero_notes.py --phase screening`

Checklist de cierre de Fase 8:

- `case.env` actualizado con `ZOTERO_SCREENING_DECISIONS` y `ZOTERO_SCREENING_MATRIX` de la corrida vigente;
- items del corpus final sincronizados con la colección destino;
- log de sincronización persistido;
- notas hijas mínimas de `screening` creadas o actualizadas para cada ítem sincronizado.

Artefactos esperados de esta fase:

- `zotero/zotero_import_manifest.json`
- `zotero/zotero_import_manifest.csv`
- `zotero/zotero_attachment_copy_log.csv`
- `zotero/zotero_import_summary.json`
- `zotero/zotero_sync_summary.json`
- `zotero/zotero_sync_actions.csv`
- `zotero/zotero_notes_summary.json`
- `zotero/zotero_notes_actions.csv`

Limitación actual:

- el `zotero-mcp` disponible permite crear colecciones, buscar ítems, crear ítems, actualizar metadata y añadir ítems a colecciones;
- también permite crear notas hijas estructuradas por ítem;
- por ahora no expone una herramienta directa para importar un PDF local como attachment nuevo;
- por eso el flujo actual puede copiar PDFs a la carpeta configurada de Zotero y sincronizar metadata, pero el enlace automático del PDF como attachment depende de una capacidad futura del MCP o de un paso auxiliar.

## Automatización de fuentes programáticas

La automatización abierta actual del agente se apoya sobre todo en `OpenAlex`, `DOAJ`, `Semantic Scholar` y, cuando existe `API key`, `Redalyc`.

Scripts principales:

- [scripts/openalex_search.py](scripts/openalex_search.py)
- [scripts/scielo_search.py](scripts/scielo_search.py)
- [scripts/doaj_search.py](scripts/doaj_search.py)
- [scripts/semanticscholar_search.py](scripts/semanticscholar_search.py)
- [scripts/redalyc_search.py](scripts/redalyc_search.py)
- [scripts/merge_search_results.py](scripts/merge_search_results.py)
- [scripts/apply_screening_decisions.py](scripts/apply_screening_decisions.py)
- [scripts/validate_fulltext_access.py](scripts/validate_fulltext_access.py)
- [scripts/download_fulltext.py](scripts/download_fulltext.py)
- [scripts/prepare_fulltext_review_text.py](scripts/prepare_fulltext_review_text.py)

Estado actual de SciELO:

- `scielo_search.py` es una primera automatización experimental para búsquedas por query en `SciELO Search`;
- escribe sus artefactos en `search/scielo/` dentro de la corrida;
- reutiliza la matriz común de `screening/` para permitir una futura integración multi-base;
- su parser depende de la estructura HTML visible de SciELO Search, así que conviene validar una muestra cuando la interfaz cambie.

Estado actual de DOAJ:

- `doaj_search.py` consulta directamente la API oficial de artículos de DOAJ;
- escribe sus artefactos en `search/doaj/` dentro de la corrida;
- devuelve metadata especialmente útil para el cribado por `titulo + resumen`, incluyendo abstract, DOI, revista, idioma y enlace a full text;
- por ahora aplica filtros de año de forma local sobre los resultados recuperados.

Estado actual de Semantic Scholar:

- `semanticscholar_search.py` consulta la Semantic Scholar Graph API;
- escribe sus artefactos en `search/semanticscholar/` dentro de la corrida;
- se usa como fuente semántica complementaria por defecto;
- devuelve metadata útil para cribado por `titulo + resumen`, incluyendo abstract, DOI, autores, año, tipo de publicación, conteo de citas, URL de Semantic Scholar y `openAccessPdf` cuando está disponible;
- no debe tratarse como búsqueda booleana estricta ni como búsqueda formal por campo `title/abstract/keywords`.

Estado actual de Redalyc:

- `redalyc_search.py` consulta la API documentada de Redalyc con `API key`;
- escribe sus artefactos en `search/redalyc/` dentro de la corrida;
- devuelve metadata suficiente para cribado local con `titulo + dc_description` cuando ese campo aparece, incluyendo titulo, autores, descripcion, idioma, tipo documental y fuente;
- la API documentada no expone un filtro directo por `abstract` o `dc_description`, asi que la recuperacion se aproxima mejor a `title + filtros metadata` que a una busqueda simetrica por `titulo + resumen`;
- en las pruebas actuales, la API no expone un total global tan claro como OpenAlex o DOAJ, asi que el control de volumen depende sobre todo de `max_results` y del refinamiento de query.

Integración multi-fuente:

- cuando un caso use dos o más fuentes programáticas, la recomendación es recuperar cada una en su subcarpeta (`search/openalex/`, `search/doaj/`, `search/semanticscholar/`, `search/redalyc/`, etc.) y luego fusionarlas antes del cribado común;
- el script inicial para esa fusión es [scripts/merge_search_results.py](scripts/merge_search_results.py);
- la política actual de deduplicación es:
  - primero por DOI exacto normalizado;
  - luego por combinación normalizada de `titulo + año`.

Artefactos típicos por corrida:

- `run_overview.md`
- `search/openalex/query.txt`
- `search/<fuente>/normalized_results.json`
- `search/<fuente>/normalized_results.csv`
- `search/<fuente>/search_log.md`
- `screening/screening_matrix.md`
- `screening/screening_matrix.csv`
- `screening/screening_decisions_*.csv`
- `screening/screening_summary_*.md`
- `screening/screening_trace.md`
- `fulltext/fulltext_download_log.csv`
- `fulltext/fulltext_recovery_summary.md`
- `fulltext/fulltext_review_text_log.csv`
- `fulltext/fulltext_review_text_summary.md`
- `extraction/extraction_matrix.md`
- `extraction/extraction_summary.md`
- `quality/quality_matrix.md`
- `quality/quality_summary.md`
- `zotero/zotero_summary.md`
- `synthesis/narrative_synthesis.md`
- `synthesis/final_audit.md`

## Metadata generada

La normalización actual de OpenAlex incluye, entre otros:

- `DOI`
- `Acceso abierto`
- `Texto completo accesible`
- `Primera afiliación`
- `País`
- `URL DOI`
- `URL de acceso`
- `URL OpenAlex`

## Configuracion de columnas en v2

Desde la v2, las columnas operativas de metadata para matrices se configuran en:

- [metadata-columns.yaml](assets/metadata-columns.yaml)

Esto permite ajustar columnas de cribado y extracción sin editar el código del conector cada vez que se agregue metadata nueva.

Regla práctica:

- `openalex_search.py` usa ese `YAML` para la matriz de cribado generada en cada corrida;
- las plantillas de `screening-matrix.md` y `extraction-matrix.md` se regeneran desde el mismo archivo;
- los artefactos `json/csv` normalizados siguen conservando el conjunto completo de metadata disponible, aunque la matriz muestre solo el subconjunto configurado.

### Regla para `Primera afiliación` y `País`

Estos dos campos se derivan de la **primera afiliación institucional disponible en OpenAlex**.

Eso significa que:

- no necesariamente representan a todos los autores;
- no sustituyen una lectura bibliométrica más fina;
- funcionan como metadata operativa útil para cribado, extracción y análisis descriptivo básico.

## Límite entre agente y estudiante

Este agente puede:

- proponer delimitaciones;
- sugerir criterios;
- automatizar partes de la búsqueda;
- apoyar el cribado;
- preparar matrices;
- resumir hallazgos con prudencia.

Este agente no debe:

- cerrar la interpretación académica por sí solo;
- presentar como “leído” un documento no recuperado;
- inventar resultados;
- reemplazar la revisión humana final.

## Estado esperado de una primera versión operativa

Una primera versión madura del flujo debería permitir:

- arrancar desde una ficha de caso;
- ejecutar una búsqueda abierta trazable;
- iterar el cribado por niveles;
- recuperar localmente parte del corpus;
- separar estudios con full text claro de estudios solo accesibles por resumen;
- pasar a extracción con un subconjunto defendible.

## Próximo uso recomendado

Para abrir un caso nuevo:

1. crear una carpeta del caso, por ejemplo `cases/<slug-del-caso>/`;
2. copiar [student-case-template.md](assets/student-case-template.md) como `cases/<slug-del-caso>/case.md`;
3. crear `cases/<slug-del-caso>/case.env` a partir de [case.env.template](assets/case.env.template);
4. completar tema, pregunta inicial y configuración del caso;
5. avanzar por fases con autorización;
6. conservar una carpeta `outputs/<corrida>` por cada iteración importante.
