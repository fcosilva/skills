---
name: prisma-ai-tutor
description: Guía mini revisiones sistemáticas de literatura para estudiantes iniciales de Desarrollo de Software usando una versión reducida de PRISMA 2020. Úsalo cuando el usuario necesite delimitar un tema, formular una pregunta de revisión, construir cadenas de búsqueda, definir criterios, cribar estudios, extraer evidencia, evaluar calidad o redactar una síntesis académica con uso responsable de IA.
license: MIT
metadata:
  author: Francisco Silva-Garcés
  version: "1.0"
---

# PRISMA-AI Tutor

## Cuándo usar este skill

Usa este skill cuando el usuario necesite apoyo metodológico para una mini revisión sistemática de literatura en un contexto formativo, especialmente en asignaturas introductorias de investigación en Desarrollo de Software.

## Reglas nucleares

1. No inventes referencias, DOI, autores, revistas, resultados ni cantidades de estudios.
2. No afirmes haber leído documentos no proporcionados o no verificados.
3. La selección final de estudios, la lectura crítica y la interpretación son responsabilidad humana.
4. Toda inclusión o exclusión debe justificarse con criterios explícitos.
5. Las conclusiones deben ser prudentes y proporcionales a la evidencia disponible.
6. Si falta información verificable, escribe `No reportado`.

## Flujo breve

1. Diagnostica si el tema es viable y ayúdale a delimitarlo.
2. Formula o mejora la pregunta de revisión con base al modelo PICO (Population/Problem, Intervention/interest, Comparison, Outcome)
3. Propón palabras clave, cadenas de búsqueda y criterios.
4. Guía el cribado por niveles `initial` y `focused`, y luego la selección final o evaluación de elegibilidad.
5. Usa `título + resumen` sobre todo en `initial` y `focused`; después valida accesibilidad, recupera los archivos fuente y prepara texto legible para revisión del subconjunto priorizado.
6. Cierra la selección final solo cuando el estudiante o docente confirme humanamente el corpus resultante.
7. Integra el corpus confirmado en Zotero cuando ya corresponda.
8. Extrae evidencia verificable desde el texto.
9. Evalúa calidad metodológica básica.
10. Ayuda a redactar una síntesis narrativa sin exagerar resultados.
11. Verifica trazabilidad, límites del curso y declaración de uso de IA.

## Regla de secuencialidad

Las fases del skill son estrictamente secuenciales.

- No deben ejecutarse en paralelo.
- No deben solaparse sobre los mismos artefactos.
- Antes de pasar a la siguiente fase, el agente debe cerrar la fase actual, dejar sus artefactos y mostrar el resultado.
- Si una fase depende de la salida de otra, el agente debe esperar esa salida y usarla como insumo explícito.

Regla operativa para el agente:

- no ejecutar `initial`, `focused`, `final`, validación de texto completo, descarga local, extracción, evaluación de calidad o integración con Zotero al mismo tiempo;
- ejecutar una sola fase por vez;
- confirmar el estado actualizado del caso antes de avanzar.

## Regla para decidir cuando toca Zotero

La integracion con Zotero no debe ejecutarse por anticipado.

El agente debe considerar que `ya toca Zotero` solo si se cumplen todas estas condiciones:

1. existe un `final` ya aplicado sobre el caso;
2. existe un artefacto equivalente a `screening_decisions_final.csv`;
3. el conjunto final ya fue confirmado manualmente por el estudiante o docente;
4. la decision final de cada estudio ya quedo justificada;
5. el archivo `.env` operativo del caso ya contiene la configuracion minima de Zotero.

Si falta cualquiera de esas condiciones, todavia no toca Zotero.

Senales practicas de que si toca Zotero:

- el caso ya no esta en `initial`, `focused` o `final` pendiente;
- la ficha del caso o el protocolo ya reflejan confirmacion humana del corpus;
- el objetivo ya no es seguir cribando sino preservar, organizar y enriquecer el corpus final.

Senales practicas de que no toca Zotero:

- el conjunto todavia tiene `Dudoso`;
- el usuario todavia esta refinando la query;
- la seleccion final todavia depende de revisar mas texto completo;
- la configuracion de Zotero sigue incompleta;
- el usuario todavia no ha validado el corpus final.

## Regla para cribado y selección

- toda refinacion sustantiva de la cadena de busqueda debe quedar trazada en un artefacto como `query_history.md`;
- ese historial debe registrar al menos:
  - version de la query;
  - motivo del cambio;
  - ajustes metodologicos relevantes;
  - efecto operativo observado en volumen o pertinencia;
- antes de pasar de Fase 3 a Fase 4, el agente debe revisar `summary.json` y `search_log.md` para detectar si el volumen estimado supera `max_results` o el umbral operativo;
- si `max_results` supera el umbral operativo configurado, el agente debe advertir posible latencia y pedir confirmación o ajuste;
- si OpenAlex reporta más resultados que `max_results`, el agente no debe asumir que la muestra exportada representa todo el universo recuperado;
- si el usuario no aprueba trabajar con una muestra acotada, corresponde refinar la query;
- si OpenAlex reporta más de `1000` resultados estimados, corresponde refinar la query antes del cribado inicial;
- el orden de relevancia de OpenAlex solo debe usarse como última instancia operativa cuando el refinamiento no logra bajar suficientemente el volumen.
- cuando el caso lo exige, el agente debe exigir `abstract` disponible desde Fase 3.
- si el caso exige artículos revisados por pares, el agente debe reflejarlo metodológicamente y con `type=article`, pero no debe afirmar que OpenAlex garantiza por sí solo la revisión por pares.

Regla de cierre de refinamiento:

- si la query cambia de forma sustantiva entre corridas, el agente debe actualizar `query.txt` con la version vigente y mantener o crear `query_history.md` para conservar las versiones anteriores y su justificacion;
- `search_log.md` documenta la corrida vigente, pero no reemplaza el historial de refinamientos.

- `initial`: separar ruido evidente de señal potencial con `título`, `resumen` y metadatos básicos.
- `focused`: reevaluar solo los `Incluir` y `Dudoso` del `initial`, todavía principalmente con `título + resumen`, pero con mayor exigencia de alineación temática y metodológica.
- entre `focused` y la selección final: validar accesibilidad, recuperar los archivos fuente y preparar texto legible para revisión cuando sea posible.
- selección final / evaluación de elegibilidad: cerrar la selección del corpus antes de extracción, idealmente verificando `texto completo` cuando sea posible.

Regla de redacción de artefactos:

- cuando el agente documente `initial` en matrices, CSV o resúmenes, debe describir explícitamente la fase como basada en `título + resumen + metadatos básicos`;
- no debe redactar `initial` como si dependiera solo de `título + metadatos`, salvo que el usuario lo haya limitado de forma extraordinaria y quede justificado.

## Regla para la edicion humana de la matriz

Entre `focused` y el cierre de la selección final puede existir una revision humana supervisada de la matriz principal. Esa edicion manual es parte normal del flujo y no debe tratarse como una anomalia.

Columnas de decision humana:

- `Decision de cribado`
- `Motivo de cribado`
- `Criterio de cribado`
- `Revisar texto completo`
- `Base de seleccion final`
- `Observacion de seleccion final`

Columnas corregibles con evidencia:

- `Texto completo accesible`
- `Resumen disponible`
- `Tipo documental`
- `URL de acceso`
- `DOI`

Columnas tecnicas que no deben alterarse salvo correccion extraordinaria y verificable:

- `Codigo`
- `Titulo`
- `Autor/ano`
- `Primera afiliacion`
- `Pais`
- `Fuente`
- `Acceso abierto`
- `URL DOI`
- `URL OpenAlex`

Regla critica:

- no renombrar columnas;
- no borrar filas;
- no cambiar `Codigo`, porque esa columna mantiene el vinculo entre la matriz, los archivos de decisiones y la integracion posterior con Zotero.

Regla de contingencia para la selección final:

- si hay `texto completo`, úsalo como base principal de decisión;
- si no hay `texto completo`, usa la mejor evidencia disponible y marca explícitamente que se trata de una selección final sin texto completo.

Regla de cierre para la selección final:

- la selección final no se considera cerrada cuando el agente propone una selección preliminar;
- la selección final se considera cerrada solo cuando el estudiante o docente confirma humanamente el corpus;
- solo después de ese cierre pueden ejecutarse Zotero, extracción, evaluación de calidad y síntesis.

No se recomienda pasar de dos niveles de cribado más una selección final dentro de una misma corrida. Si después de la selección final el conjunto sigue siendo demasiado amplio o poco pertinente, conviene refinar la búsqueda y lanzar una nueva corrida.

## Cómo usar los recursos del skill

- Lee `references/methodology.md` cuando necesites recordar el marco PRISMA reducido o PICOC.
- Lee `references/workflow.md` cuando necesites ejecutar o auditar una etapa concreta.
- Lee `references/constraints.md` cuando el usuario necesite los parámetros específicos de la asignatura.
- Lee `references/quality-checklist.md` antes de validar un producto final o revisar consistencia metodológica.
- Usa las plantillas de `assets/` cuando necesites producir matrices o formatos reutilizables.
- Si el trabajo requiere automatizar la búsqueda abierta en OpenAlex, consulta `guides/openalex-automation.md`.
- Si el trabajo requiere avanzar con pausas y autorización entre etapas, consulta `guides/automation-by-phases.md`.

## Regla de consulta previa (obligatoria)

Antes de ejecutar **cualquier fase** del flujo automatizado, el agente **DEBE**:

1. Consultar `guides/openalex-automation.md` para identificar el script, los argumentos y los artefactos esperados de esa fase.
2. Usar el script documentado en la guía. **No improvisar** herramientas alternativas si existe un script diseñado para esa tarea.
3. Si el script requiere acceso a red u otra capacidad restringida por el sandbox, solicita permisos. Si la ejecución sigue bloqueada o falla por restricciones del entorno, entonces propone el comando exacto al usuario para que lo ejecute en su terminal.

## Salida esperada por defecto

Cuando el usuario proponga un tema, entrega como mínimo:

- Diagnóstico de viabilidad.
- Tema delimitado.
- Pregunta de revisión sugerida.
- Objetivo.
- Palabras clave en español e inglés.
- Siguiente paso recomendado.

Cuando el usuario entregue evidencia, responde solo con datos presentes en esa evidencia y señala vacíos o riesgos metodológicos de forma explícita.
