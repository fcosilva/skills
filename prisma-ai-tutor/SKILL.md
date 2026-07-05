---
name: prisma-ai-tutor
description: Guía mini revisiones sistemáticas de literatura para estudiantes iniciales de Desarrollo de Software usando una versión reducida de PRISMA 2020. Úsalo cuando el usuario necesite delimitar un tema, formular una pregunta de revisión, construir cadenas de búsqueda, definir criterios, cribar estudios, extraer evidencia, evaluar calidad o redactar una síntesis académica con uso responsable de IA.
license: MIT
metadata:
  author: Francisco Silva-Garcés
  version: "1.1"
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
5. Usa `título + resumen` sobre todo en `initial` y `focused`; después valida accesibilidad (open access), recupera los archivos fuente y prepara texto legible para revisión del subconjunto priorizado.
6. Pide autorización humana explícita al cerrar Fase 2 antes de ejecutar Fase 3.
7. Cierra la selección final solo cuando el estudiante o docente confirme humanamente el corpus resultante.
8. Integra el corpus confirmado en Zotero cuando ya corresponda.
9. Dentro de la fase Zotero, crea explícitamente las notas hijas mínimas de `screening` antes de dar por cerrada esa fase.
10. Extrae evidencia verificable desde el texto.
11. Evalúa calidad metodológica básica.
12. Ayuda a redactar una síntesis narrativa sin exagerar resultados.
13. Verifica trazabilidad, límites del curso y declaración de uso de IA.
14. Genera `synthesis/informe_final.md` solo si el estudiante o docente lo confirma explícitamente después de la síntesis y auditoría.

## Regla sobre scripts auxiliares

Antes de crear scripts nuevos o usar `scratch/`, el agente debe revisar `guides/script-inventory.md`.

- No debe crear scripts ad hoc para tareas ya cubiertas por los scripts oficiales.
- Si necesita una utilidad temporal, debe explicar por qué no alcanza con los scripts existentes y no debe convertirla en artefacto oficial del flujo.
- El cribado `initial` y `focused` lo propone el agente; el usuario revisa, corrige o aprueba, pero no debe recibir como tarea inicial hacer el filtrado que corresponde al agente.

## Regla sobre mantenimiento del skill durante una corrida

Durante la ejecución de un caso, el agente no debe modificar archivos del skill ni scripts del core metodológico.

- Si detecta un bug, una brecha de flujo o una necesidad de cambio parametrizable, debe crear un reporte en `cases/<slug>/agent_reports/`.
- El reporte debe distinguir entre bug, solicitud de mejora, workaround aplicado y riesgo metodológico.
- El agente puede continuar solo si existe un workaround seguro que no modifique el core del skill ni altere la trazabilidad.
- Las correcciones del skill deben revisarse en un flujo de mantenimiento separado.

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
- todos los artefactos operativos de una corrida deben escribirse dentro de `outputs/<corrida>/`;
- las queries aprobadas por fuente son artefactos operativos y deben vivir en `outputs/<corrida>/search/<fuente>/query.txt`, no en `cases/<slug>/search/<fuente>/query.txt`;
- el agente no debe crear archivos del caso directamente en `outputs/` raíz;
- el agente no debe crear carpetas `search/`, `screening/`, `fulltext/`, `extraction/`, `quality/` o `synthesis/` dentro de `cases/<slug>/`;
- si detecta artefactos del caso en `outputs/` raíz, debe tratarlos como desviación del flujo, corregir la ruta antes de seguir y dejar constancia de la corrección.

Regla adicional para Fase 3 multi-fuente:

- si el caso declara varias fuentes activas para Fase 3, deben ejecutarse en secuencia dentro de la misma fase;
- el orden recomendado por defecto es `openalex -> doaj -> semanticscholar -> lens -> redalyc`;
- si el caso incorpora Scopus, ubícalo preferentemente como `openalex -> doaj -> semanticscholar -> lens -> scopus -> redalyc`;
- salvo indicación explícita del usuario, la Fase 3 multi-fuente debe activar `openalex`, `doaj`, `semanticscholar`, `lens` y `redalyc`;
- `semanticscholar` debe usarse como fuente semántica complementaria: su query no es booleana estricta y debe redactarse como frase o concepto natural alineado con el tema;
- `lens` debe usarse como fuente programática opcional activada cuando exista `LENS_API_KEY`; su query puede usar booleanos simples sobre `title` y `abstract`;
- si Scopus está activo con `SCOPUS_MODE=manual_csv`, la Fase 3 no debe iniciar hasta que `SCOPUS_CSV_FILE` apunte a un CSV existente exportado desde Scopus;
- si el tema está relacionado con salud, medicina, biomedicina, bioética, educación médica, publicación científica biomédica o IA en salud, el agente debe proponer agregar `pubmed` como fuente especializada;
- la fusión debe ocurrir al cierre de Fase 3, antes de cualquier `initial`;
- no se debe esperar a `focused` ni a selección final para deduplicar entre fuentes.

## Regla para decidir cuando toca Zotero

La integracion con Zotero no debe ejecutarse por anticipado.

El agente debe considerar que `ya toca Zotero` solo si se cumplen todas estas condiciones:

1. existe un `final` ya aplicado sobre el caso;
2. existe un artefacto equivalente a `screening_decisions_final.csv`;
3. el conjunto final ya fue confirmado manualmente por el estudiante o docente;
4. la decisión final de cada estudio ya quedó justificada;
5. el archivo `.env` operativo del caso ya contiene la configuración mínima de Zotero.

Si falta cualquiera de esas condiciones, todavia no toca Zotero.

Señales prácticas de que sí toca Zotero:

- el caso ya no está en `initial`, `focused` o `final` pendiente;
- la ficha del caso o el protocolo ya reflejan confirmación humana del corpus;
- el objetivo ya no es seguir cribando sino preservar, organizar y enriquecer el corpus final.
- el agente puede completar tanto la sincronización bibliográfica como la nota hija minima de `screening` por cada item.

Señales prácticas de que no toca Zotero:

- el conjunto todavía tiene `Dudoso`;
- el usuario todavía está refinando la query;
- la selección final todavía depende de revisar más texto completo;
- la configuración de Zotero sigue incompleta;
- el usuario todavía no ha validado el corpus final.
- la sincronización bibliográfica terminó pero las notas hijas obligatorias de `screening` todavía no fueron creadas.

Regla de cierre de Fase 8:

- la Fase 8 no se considera cerrada solo porque los items ya existan en la librería o en la colección;
- la Fase 8 se considera cerrada solo cuando se completan ambos pasos, en este orden:
  - sincronización bibliográfica del corpus final con Zotero;
  - creación o actualización de la nota hija minima de `screening` por cada item sincronizado;
- antes de iniciar Fase 8, el agente debe actualizar en `case.env` las rutas vigentes de `ZOTERO_SCREENING_DECISIONS` y `ZOTERO_SCREENING_MATRIX` si todavia están vacías, desactualizadas o apuntan a otra corrida;
- si el agente ejecuta `prepare_zotero_import.py` o `sync_zotero_mcp.py`, debe verificar después si corresponde ejecutar también `write_zotero_notes.py --phase screening`;
- el agente no debe asumir que la escritura de notas ocurre implícitamente dentro de `sync_zotero_mcp.py`.

## Regla para cribado y selección

- toda refinación sustantiva de la cadena de búsqueda debe quedar trazada en un artefacto como `query_history.md`;
- ese historial debe registrar al menos:
  - versión de la query;
  - motivo del cambio;
  - ajustes metodológicos relevantes;
  - efecto operativo observado en volumen o pertinencia;
- antes de pasar de Fase 3 a Fase 4, el agente debe revisar `summary.json` y `search_log.md` para detectar si el volumen estimado supera `max_results` o el umbral operativo;
- si Fase 3 usa varias fuentes, el agente debe revisar además `merged_summary.json` y `source_merge_log.md` antes de pasar a Fase 4;
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
- si el caso usa varias fuentes, la Fase 2 debe admitir una `query` por fuente;
- el agente no debe asumir que una misma sintaxis sirve de forma identica para `OpenAlex`, `DOAJ`, `Semantic Scholar`, `Lens`, `Scopus` y `Redalyc`;
- si el caso usa Semantic Scholar, debe traducir la estrategia conceptual a una query semantica natural, no a operadores booleanos ni busqueda por campos especificos;
- si el caso usa Lens, debe traducir la estrategia a una query `query_string` sencilla para buscar en `title` y `abstract`;
- si el caso usa PubMed, debe traducir la estrategia a sintaxis PubMed, preferentemente con campos `[Title/Abstract]`;
- si el caso usa Scopus en modo `manual_csv`, el cierre de Fase 2 debe detenerse para que el usuario ejecute la búsqueda web en Scopus, exporte el CSV, guarde el archivo en el workspace y complete `SCOPUS_CSV_FILE`;
- puede existir una estrategia conceptual comun, pero debe traducirse y guardarse por separado en cada `outputs/<corrida>/search/<fuente>/query.txt`;
- si las queries por fuente divergen de forma sustantiva, la justificacion debe quedar trazada por fuente en `query_history.md`.
- al cerrar Fase 2, el agente debe pedir aprobación breve del usuario antes de ejecutar Fase 3.

- `initial`: separar ruido evidente de señal potencial con `título`, `resumen` y metadatos básicos.
- `focused`: reevaluar solo los `Incluir` y `Dudoso` del `initial`, todavía principalmente con `título + resumen`, pero con mayor exigencia de alineación temática y metodológica.
- entre `focused` y la selección final: validar accesibilidad, recuperar los archivos fuente y preparar texto legible para revisión cuando sea posible.
- selección final / evaluación de elegibilidad: cerrar la selección del corpus antes de extracción, trabajando solo con estudios que sí tengan `texto completo` accesible y legible, ya sea en PDF, HTML o algún otro formato.

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

Regla de elegibilidad para la selección final:

- si hay `texto completo`, úsalo como base principal de decisión;
- si no hay `texto completo`, el estudio no debe entrar al corpus final;
- la falta de `texto completo` puede justificar exclusión o una nueva búsqueda/refinamiento, pero no una inclusión final basada solo en resumen y metadatos.

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
- Si el trabajo requiere automatizar búsqueda abierta en DOAJ, consulta `guides/doaj-automation.md`.
- Si el trabajo requiere automatizar búsqueda semántica complementaria en Semantic Scholar, consulta `guides/semanticscholar-automation.md`.
- Si el trabajo requiere automatizar búsqueda en Lens Scholarly API, consulta `guides/lens-automation.md`.
- Si el tema tiene pertinencia biomédica o de salud y requiere PubMed, consulta `guides/pubmed-automation.md`.
- Si el trabajo requiere incorporar Scopus, consulta `guides/scopus-automation.md`.
- Si el trabajo requiere automatizar búsqueda regional en Redalyc con API key, consulta `guides/redalyc-automation.md`.
- Si el trabajo requiere avanzar con pausas y autorización entre etapas, consulta `guides/automation-by-phases.md`.
- Si necesitas decidir qué script usar, consulta `guides/script-inventory.md`.

## Regla de consulta previa (obligatoria)

Antes de ejecutar **cualquier fase** del flujo automatizado, el agente **DEBE**:

1. Consultar la guía de automatización correspondiente a la fuente activa para identificar el script, los argumentos y los artefactos esperados de esa fase.
   - `guides/openalex-automation.md` para OpenAlex
   - `guides/doaj-automation.md` para DOAJ
   - `guides/semanticscholar-automation.md` para Semantic Scholar
   - `guides/lens-automation.md` para Lens
   - `guides/pubmed-automation.md` para PubMed
   - `guides/scopus-automation.md` para Scopus
   - `guides/redalyc-automation.md` para Redalyc
   - si el caso declara una Fase 3 multi-fuente, consultar también `guides/automation-by-phases.md`
   - `guides/script-inventory.md` para no duplicar scripts existentes
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
