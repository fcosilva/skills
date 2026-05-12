# Ficha inicial del caso

## Regla de validación

Si algún campo se completa de forma asistida por el skill o mediante un borrador propuesto por IA, el estudiante debe revisarlo y validarlo explícitamente antes de avanzar a la siguiente fase.

## Mínimo para iniciar automatización

Para iniciar la automatización, la ficha debe contener al menos:

- tema propuesto;
- una pregunta inicial o una formulación clara del problema;
- ambos datos mínimos deben haber sido proporcionados por el estudiante.

Si falta alguno de estos elementos, el flujo no debe avanzar. Primero el estudiante debe completar la información mínima.

Una vez que el estudiante haya llenado esos datos, el skill sí puede:

- revisar viabilidad;
- delimitar el tema;
- proponer mejoras a la pregunta;
- sugerir borradores para los campos recomendados.

Cualquier propuesta o ajuste del skill debe ser validado por el estudiante antes de pasar a la siguiente fase.

## Uso de esta plantilla

- Esta plantilla debe mantenerse limpia en `assets/`.
- Para un caso real, crea una copia en `cases/<tema-slug>/case.md`.
- La ficha real del caso es el documento que debe evolucionar durante las fases.

## Estado del caso

- Estado actual: [...]
- Responsable: [...]
- Fecha: [...]

## Tema propuesto

Obligatorio.

[[...]]

## Tema delimitado

Recomendado al cierre de la Fase 1.

[[...]]

## Pregunta de revisión

Obligatoria para pasar a la construcción formal de la query.

[[...]]

Versión refinada validada:

[[...]]

## Hipótesis de trabajo

Recomendada. Si es propuesta por el skill, requiere validación del estudiante.

[[...]]

Versión refinada validada:

[[...]]

## Objetivo de la revisión

Recomendado. Puede proponerse de forma asistida, pero requiere validación antes de pasar a búsqueda.

[[...]]

## Palabras clave iniciales

### Español

Recomendadas. Pueden proponerse de forma asistida, pero deben validarse antes de ejecutar la búsqueda.

- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]

### Inglés

Recomendadas. Pueden proponerse de forma asistida, pero deben validarse antes de ejecutar la búsqueda.

- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]

## Alcance preliminar

Recomendado. Si falta, el skill puede proponer un borrador inicial, pero no debe avanzar a búsqueda formal sin validación del estudiante.

- Periodo de publicación: [[...]]
- Idiomas: [[...]]
- Tipos documentales elegibles: [[...]]
- Tipos documentales excluidos: [[...]]

Nota:

- si aquí se declara búsqueda en más de un idioma, la `query.txt` de la Fase 2 debe reflejarlo explícitamente o justificar la reducción;
- si aquí se excluye `preprint` u otro tipo documental, la configuración técnica de la búsqueda debe trasladar esa exclusión a `OPENALEX_EXCLUDE_TYPES` o a los flags equivalentes.

## Configuración técnica para automatización

Obligatoria para pasar a la Fase 3 en el flujo formal.

- Archivo de configuración de OpenAlex disponible: [[sí / no]]
- Ruta del archivo de configuración: [[...]]
- Validación del estudiante para usar esa configuración en la búsqueda: [[sí / no]]

Nota:

- el script permite búsqueda sin configuración como capacidad técnica general;
- sin embargo, en el flujo formal del skill la Fase 3 debe ejecutarse con archivo de configuración para reducir fricción con límites de uso y mejorar la continuidad del protocolo;
- el archivo de configuración puede incluir `OPENALEX_API_KEY`, `OPENALEX_MAILTO` y otros ajustes básicos;
- la API key real no debe escribirse en la ficha; solo debe indicarse la disponibilidad y la ruta del archivo.

## Criterios preliminares

Recomendados. Si el skill los propone, el estudiante debe validarlos antes del cribado formal.

### Inclusión

- [[...]]
- [[...]]
- [[...]]
- [[...]]

### Exclusión

- [[...]]
- [[...]]
- [[...]]
- [[...]]

## Variables o categorías a observar

Recomendadas. Pueden ajustarse más adelante, pero conviene validarlas antes de la extracción de evidencia.

- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]
- [[...]]

## Observaciones del estudiante o docente

Opcional.

[[...]]

## Estado del corpus para cierre de `final`

Completar cuando el caso ya haya pasado por `focused` y por la validacion de accesibilidad o recuperacion local.

- Fecha de cierre propuesta de `final`: [[...]]
- Confirmacion humana del corpus final: [[pendiente / confirmada]]
- Total de estudios incluidos en `final`: [[...]]
- Estudios con base principal `Texto completo`: [[...]]
- Estudios con base principal `Resumen y metadatos`: [[...]]
- Observacion breve sobre la proporcion del corpus: [[...]]

Nota:

- este bloque ayuda a dejar trazabilidad de como paso el caso desde `focused` hasta el cierre real de `final`;
- `final` solo se considera cerrado cuando la confirmacion humana ya consta aqui o en un artefacto equivalente del caso.

## Autorización por fases

Obligatoria como control del flujo.

- Fase 1. Delimitación del tema: [[pendiente / aprobada]]
- Fase 2. Construcción de query: [[pendiente / aprobada]]
- Fase 3. Búsqueda automatizada: [[pendiente / aprobada]]
- Fase 4. Cribado inicial: [[pendiente / aprobada]]
- Fase 5. Cribado focused: [[pendiente / aprobada]]
- Fase 6. Validación de accesibilidad y recuperación de full text: [[pendiente / aprobada]]
- Fase 7. Cribado final: [[pendiente / aprobada]]
- Fase 8. Integración en Zotero: [[pendiente / aprobada]]
- Fase 9. Extracción de evidencia: [[pendiente / aprobada]]
- Fase 10. Evaluación de calidad: [[pendiente / aprobada]]
- Fase 11. Síntesis narrativa y auditoría final: [[pendiente / aprobada]]
