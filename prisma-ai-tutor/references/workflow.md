# Flujo de trabajo

## Fase 1. Diagnóstico del tema

Objetivo:

- Identificar si el tema es viable como mini revisión sistemática.

Evalúa si el tema es:

- Viable.
- Demasiado amplio.
- Mejor para revisión narrativa.
- Mejor para investigación empírica.
- Necesitado de delimitación.

Salida esperada:

- Diagnóstico.
- Tema delimitado.
- Pregunta de revisión sugerida.
- Objetivo.
- Palabras clave.
- Advertencias.
- Siguiente paso.

## Fase 2. Formulación de la pregunta

Objetivo:

- Proponer una pregunta clara, investigable y coherente con el alcance del curso.

Acción:

- Proponer máximo tres preguntas.
- Recomendar una opción principal.
- Justificar la elección con PICOC adaptado cuando ayude.

## Fase 3. Protocolo reducido

Objetivo:

- Convertir el tema en un plan de trabajo trazable.

Debe incluir:

- Tema.
- Pregunta.
- Objetivo.
- Fuentes.
- Periodo de publicación.
- Idiomas.
- Tipos de documentos incluidos.
- Criterios de inclusión.
- Criterios de exclusión.
- Variables a extraer.
- Declaración de uso de IA.

Además debe dejar explícito:

- El conjunto mínimo de fuentes exigidas por la asignatura.
- Los tipos documentales elegibles y no elegibles.
- La meta de búsqueda inicial.
- La meta de estudios incluidos en la síntesis final.
- La extensión esperada del informe.
- El rango sugerido de referencias totales.

## Fase 4. Búsqueda

Objetivo:

- Proponer una estrategia reproducible.

Debe incluir:

- Palabras clave.
- Sinónimos.
- Términos en inglés.
- Cadenas simples.
- Cadenas avanzadas.
- Fuentes académicas pertinentes.

También debe recordar que:

- La estrategia debe cubrir las fuentes mínimas definidas en `references/constraints.md`.
- Deben priorizarse artículos académicos o científicos arbitrados.
- No deben contarse tesis ni trabajos de titulación como evidencia elegible.
- Si la búsqueda inicial queda por debajo del mínimo definido en `references/constraints.md`, debe sugerir ajustes antes de pasar al cribado (selección de estudios), salvo justificación explícita.

Regla:

- No afirmes que encontraste resultados si no se hizo la búsqueda o si el usuario no comparte la evidencia.

## Fase 5. Cribado (selección de estudios)

Entrada:

- Títulos y resúmenes.

Clasificación:

- Incluir.
- Excluir.
- Dudoso.

Cada decisión debe indicar:

- Justificación.
- Criterio de cribado.
- Qué revisar en texto completo.

Además, vigila que:

- No entren documentos no elegibles según `references/constraints.md`.
- La cantidad final de estudios incluidos siga siendo viable para una mini revisión sistemática del curso.

Niveles sugeridos de cribado:

- `initial`: primer filtro por título, resumen y metadatos básicos.
- `focused`: segundo filtro sobre los casos `Incluir` y `Dudoso`, todavía basado sobre todo en resumen, pero con mayor exigencia de alineación temática y metodológica.
- después de `focused`: validación operativa de accesibilidad y recuperación local del texto completo para el subconjunto priorizado.
- `final`: selección final antes de la extracción, idealmente verificando texto completo cuando sea posible.

Regla práctica:

- `initial` y `focused` pueden resolverse principalmente con título y abstract;
- en la redacción de artefactos, `initial` debe describirse como fase basada en `título + resumen + metadatos básicos`, no como una fase de `título + metadatos` solamente;
- `final` debería apoyarse ya en texto completo recuperado localmente o en evidencia ampliada suficiente para confirmar elegibilidad.
- si el texto completo no está disponible, la decisión final puede apoyarse en resumen y metadatos, pero debe quedar explícita esa limitación.

En la matriz de cribado conviene registrar además:

- `Texto completo accesible`
- `Base de seleccion final`
- `Observacion de seleccion final`

## Fase 6. Extracción de evidencia

Entrada:

- Texto completo, resumen ampliado o fragmento verificable.

Extrae solo:

- Autor/año.
- Título.
- Objetivo.
- Método.
- Contexto.
- Muestra o corpus.
- Tecnología o herramienta.
- Hallazgos principales.
- Limitaciones.
- Relevancia.

Si falta información:

- Escribe `No reportado`.

## Fase 7. Evaluación simple de calidad

Usa esta escala:

| Criterio | Sí | Parcial | No |
|---|---:|---:|---:|
| Objetivo claro | 2 | 1 | 0 |
| Método claro | 2 | 1 | 0 |
| Datos suficientes | 2 | 1 | 0 |
| Contexto o muestra descrita | 2 | 1 | 0 |
| Limitaciones reconocidas | 2 | 1 | 0 |

Interpretación:

| Puntaje | Calidad |
|---:|---|
| 8-10 | Alta |
| 5-7 | Media |
| 0-4 | Baja |

## Fase 8. Síntesis narrativa

Organiza la síntesis en:

1. Hallazgos principales.
2. Coincidencias.
3. Diferencias o contradicciones.
4. Vacíos de investigación.
5. Implicaciones para desarrollo de software.
6. Limitaciones.
7. Conclusión prudente.

## Fase 9. Auditoría final

Antes de cerrar, revisa:

1. Pregunta clara.
2. Fuentes identificadas.
3. Criterios estables.
4. Matrices con datos verificables.
5. Evaluación de calidad aplicada.
6. Declaración de uso de IA incluida.
7. Conclusiones proporcionales a la evidencia.
8. Cumplimiento de las fuentes mínimas exigidas por la asignatura.
9. Inclusión exclusiva de estudios elegibles.
10. Cumplimiento del mínimo de búsqueda inicial o justificación de excepción.
11. Cumplimiento del mínimo de estudios incluidos o justificación de excepción.
12. Coherencia entre estudios incluidos y referencias totales.
13. Extensión final dentro del rango esperado.
