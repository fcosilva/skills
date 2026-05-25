# Protocolo reducido PRISMA-AI

Nota de navegación:

- el protocolo metodológico vive en `cases/<tema-slug>/protocol.md`;
- la corrida debería complementarse con `outputs/<corrida>/run_overview.md` como índice navegable para el estudiante.

## Tema

[...]

## Tema delimitado

[...]

## Pregunta de revisión

[...]

## Objetivo

[...]

## Fuentes de información

- OpenAlex, DOAJ, Redalyc
- Scopus si existe acceso institucional o CSV exportado
- PubMed si el tema tiene pertinencia biomédica o de salud
- SciELO, Redalyc 

## Configuración técnica de búsqueda

- Query aprobada y persistida en `search/<fuente>/query.txt`
- Archivo de configuración de OpenAlex disponible y validado por el estudiante
- `OPENALEX_REQUIRE_ABSTRACT=true` cuando el caso exige trabajar solo con estudios con resumen disponible
- Si se llega al cribado `focused`, la validación de `Texto completo accesible` debe hacerse sobre ese subconjunto antes de la selección final
- Si el caso exige artículos revisados por pares, esto debe expresarse metodológicamente y no asumirse como campo automático de OpenAlex
- `max_results` debe definirse junto con un umbral operativo de muestra

Si el caso usa varias fuentes programáticas:

- la Fase 2 debe dejar una `query` aprobada por fuente;
- la estrategia conceptual puede ser común, pero la sintaxis no tiene por qué ser idéntica;
- si hay adaptación por cobertura, campo de búsqueda o limitación técnica de la fuente, debe quedar justificada.

## Periodo de publicación

[...]

## Idiomas

[...]

## Tipos de documentos incluidos

- Artículos académicos o científicos revisados por pares.

## Criterios de inclusión

[...]

## Criterios de exclusión

- Tesis
- Trabajos de titulación
- Literatura no académica como evidencia principal
- preprint

## Cadenas de búsqueda

[...]

Sugerencia de redacción cuando hay varias fuentes:

- OpenAlex: `[...]`
- DOAJ: `[...]`
- Redalyc: `[...]`

## Historial de refinamiento de query

Registrar cuando corresponda:

- versión inicial de la query
- versión o versiones refinadas
- motivo del refinamiento
- efecto observado en volumen o pertinencia
- ruta al artefacto `query_history.md` si ya existe

Nota metodológica:

- si en `Idiomas` se declara más de un idioma, la estrategia de búsqueda debe reflejarlo explícitamente o justificar por qué se usó solo uno;
- si `preprint` está excluido metodológicamente, la configuración técnica debe trasladar esa exclusión a los filtros reales de búsqueda.
- si el volumen estimado supera `max_results`, primero corresponde decidir si se refina la query o si se autoriza una muestra acotada;
- si el volumen estimado supera `1000`, corresponde refinar la query antes del cribado inicial;
- el orden de relevancia de OpenAlex solo debe usarse como última instancia operativa cuando el refinamiento no logra reducir suficientemente el volumen.
- si el caso usa varias fuentes, las diferencias entre queries por fuente no son una inconsistencia por sí mismas; solo deben quedar justificadas y trazadas.

## Meta de recuperación inicial

Al menos 30 registros antes de eliminar duplicados, o justificación de excepción.

## Meta de selección final

Idealmente entre 8 y 12 estudios. Mínimo aceptable: 6 con justificación.

## Artefactos esperados para la selección final / evaluación de elegibilidad

- `screening_decisions_final.csv`
- `screening/screening_summary_final.md`
- actualización de la matriz de cribado con:
  - `Texto completo accesible`
  - `Base de seleccion final`
  - `Observacion de seleccion final`

## Trazabilidad del paso `focused` -> selección final

Registrar de forma breve:

- cantidad de estudios priorizados tras `focused`;
- cantidad de estudios con `Texto completo` confirmado;
- cantidad de estudios excluidos por falta de `Texto completo`;
- justificacion metodologica si el subconjunto priorizado no logró recuperar suficiente texto completo;
- constancia de confirmacion humana del corpus final.

Esta seccion no reemplaza la matriz ni la ficha del caso. Su objetivo es dejar visible, dentro del protocolo, con que base real se cerró la selección final.

## Variables o categorías a extraer

[...]

## Extensión objetivo del informe

5000 a 6000 palabras incluyendo título, resumen y referencias.

## Rango sugerido de referencias

12 a 20 verificables.

## Declaración de uso de IA

[...]
