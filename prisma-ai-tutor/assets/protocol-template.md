# Protocolo reducido PRISMA-AI

## Tema

[...]

## Tema delimitado

[...]

## Pregunta de revisión

[...]

## Objetivo

[...]

## Fuentes de información

- OpenAlex, DOAJ
- Scopus, WoS, Dimensions
- SciELO, Redalyc 

## Configuración técnica de búsqueda

- Query aprobada y persistida en `query.txt`
- Archivo de configuración de OpenAlex disponible y validado por el estudiante
- `OPENALEX_REQUIRE_ABSTRACT=true` cuando el caso exige trabajar solo con estudios con resumen disponible
- Si se llega al cribado `focused`, la validación de `Texto completo accesible` debe hacerse sobre ese subconjunto antes del `final`
- Si el caso exige artículos revisados por pares, esto debe expresarse metodológicamente y no asumirse como campo automático de OpenAlex
- `max_results` debe definirse junto con un umbral operativo de muestra

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

Nota metodológica:

- si en `Idiomas` se declara más de un idioma, la estrategia de búsqueda debe reflejarlo explícitamente o justificar por qué se usó solo uno;
- si `preprint` está excluido metodológicamente, la configuración técnica debe trasladar esa exclusión a los filtros reales de búsqueda.
- si el volumen estimado supera `max_results`, primero corresponde decidir si se refina la query o si se autoriza una muestra acotada;
- si el volumen estimado supera `1000`, corresponde refinar la query antes del cribado inicial;
- el orden de relevancia de OpenAlex solo debe usarse como última instancia operativa cuando el refinamiento no logra reducir suficientemente el volumen.

## Meta de recuperación inicial

Al menos 30 registros antes de eliminar duplicados, o justificación de excepción.

## Meta de selección final

Idealmente entre 8 y 12 estudios. Mínimo aceptable: 6 con justificación.

## Artefactos esperados para el cribado final

- `screening_decisions_final.csv`
- `screening_summary_final.md`
- actualización de la matriz de cribado con:
  - `Texto completo accesible`
  - `Base de decisión final`
  - `Observación final`

## Trazabilidad del paso `focused` -> `final`

Registrar de forma breve:

- cantidad de estudios priorizados tras `focused`;
- cantidad de estudios con `Texto completo` confirmado;
- cantidad de estudios que llegaron a `final` con base `Resumen y metadatos`;
- justificacion metodologica si una parte relevante del corpus no tuvo texto completo;
- constancia de confirmacion humana del corpus final.

Esta seccion no reemplaza la matriz ni la ficha del caso. Su objetivo es dejar visible, dentro del protocolo, con que base real se cerró `final`.

## Variables o categorías a extraer

[...]

## Extensión objetivo del informe

5000 a 6000 palabras incluyendo título, resumen y referencias.

## Rango sugerido de referencias

12 a 20 verificables.

## Declaración de uso de IA

[...]
