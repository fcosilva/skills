# Automatización por fases

Fecha de referencia: 2026-05-09.

## Propósito

Esta guía define un flujo de automatización gradual para `PRISMA-AI Tutor`. La idea es evitar ejecuciones opacas o demasiado largas y mantener control docente o del estudiante en cada etapa importante.

## Principio general

La automatización no debe saltar directamente desde el tema hasta una lista final de estudios. Debe avanzar por fases, mostrando resultados intermedios y pidiendo autorización antes de continuar.

## Regla obligatoria de ejecución

Las fases de este flujo son secuenciales.

- No se ejecutan en paralelo.
- No se deben lanzar dos fases sobre el mismo caso al mismo tiempo.
- No se debe actualizar el mismo `screening/screening_matrix.md` desde dos iteraciones simultáneas.
- Cada fase debe terminar, persistir sus artefactos y quedar revisable antes de continuar.

Si el agente necesita hacer trabajo adicional:

- puede preparar insumos de la siguiente fase;
- pero no debe aplicar esa fase todavía sobre los artefactos del caso hasta cerrar formalmente la fase actual.

## Artefactos del flujo

- Plantilla de la ficha del caso: [student-case-template.md](../assets/student-case-template.md)
- Ficha real del caso: copia de la plantilla en `cases/<tema-slug>/case.md`
- Protocolo: [protocol-template.md](../assets/protocol-template.md)
- Matriz de cribado: [screening-matrix.md](../assets/screening-matrix.md)
- Índice principal de cada corrida: [run-overview.md](../assets/run-overview.md)
- Query persistida: `search/query.txt` en el directorio de salida de cada búsqueda
- Historial de refinamiento de query: `search/query_history.md` en el directorio de salida cuando exista al menos una refinación sustantiva
- Archivo de configuración del caso: [case.env.template](../assets/case.env.template) como plantilla de referencia
- Resumen por iteración de cribado: `screening/screening_summary_<fase>.md` en el directorio de salida de cada búsqueda
- Trazabilidad acumulada de cribado y selección final: [screening-trace.md](../assets/screening-trace.md)
- Resumen de extracción: [extraction-summary.md](../assets/extraction-summary.md)
- Resumen de calidad: [quality-summary.md](../assets/quality-summary.md)
- Resumen de Zotero: [zotero-summary.md](../assets/zotero-summary.md)

## Punto de entrada recomendado

Para el estudiante, cada corrida debe tener un solo punto de entrada visible:

- `outputs/<corrida>/run_overview.md`

Desde ese índice deben enlazarse:

- el `case.md` del caso;
- el resumen de la fase actual;
- la matriz principal si hace falta detalle;
- los artefactos derivados relevantes de búsqueda, full text, Zotero, extracción, calidad y síntesis.

Regla práctica:

- al cerrar una fase con los scripts del skill, `run_overview.md` debe actualizarse automáticamente;
- cuando haya artefactos suficientes, también deben actualizarse automáticamente `screening_trace.md`, `zotero_summary.md`, `extraction_summary.md` y `quality_summary.md`.
- para ayudar al estudiante, una corrida nueva puede crear automáticamente placeholders en `extraction/`, `quality/` y `synthesis/`;
- esos archivos placeholder no deben interpretarse como evidencia de fase cerrada.

## Fases recomendadas

### Fase 1. Delimitación

Entrada:

- tema
- pregunta inicial
- hipótesis

Acción:

- revisar viabilidad
- delimitar tema
- corregir o mejorar pregunta

Salida:

- ficha del caso completada
- pregunta de revisión refinada

Pausa:

- pedir autorización para pasar a Fase 2

### Fase 2. Construcción de query

Entrada:

- ficha del caso
- palabras clave
- criterios preliminares

Acción:

- construir cadena inicial
- ajustar tipo documental, idioma, fechas y demás filtros
- guardar la cadena en `search/query.txt`
- si la cadena cambia de forma sustantiva en una nueva iteración, crear o actualizar `query_history.md`

Reglas operativas:

- si el caso o el protocolo especifican más de un idioma de búsqueda, la query debe reflejarlo explícitamente o dejar justificación metodológica de por qué se reduce a uno;
- si el protocolo excluye tipos documentales como `preprint`, esa exclusión debe traducirse al filtro técnico correspondiente antes de ejecutar la búsqueda;
- el agente no debe inferir tipos documentales adicionales si el caso ya los delimitó explícitamente.

Nota:

- aunque el script permite recibir la query directamente por parámetro, en el flujo formal del skill esta fase debe producir y dejar aprobado `query.txt` antes de ejecutar la búsqueda.
- si el caso excluye `preprint`, conviene dejarlo también reflejado en `OPENALEX_EXCLUDE_TYPES` o con `--exclude-type preprint`.

Salida:

- `search/query.txt`
- `query_history.md` cuando ya hubo refinamientos sustantivos
- estrategia de búsqueda documentada

Pausa:

- pedir autorización para pasar a Fase 3

### Fase 3. Búsqueda automatizada

Entrada:

- `search/query.txt`
- archivo de configuración disponible y validado por el estudiante
- parámetros de OpenAlex

Acción:

- ejecutar la búsqueda
- generar resultados normalizados
- generar matriz inicial de cribado
- generar bitácora

Regla metodológica de volumen:

- `max_results` es la muestra objetivo para exportación y cribado, no una selección metodológica final;
- debe existir un umbral operativo configurable, recomendado en `500`;
- si `max_results` supera el umbral, el agente debe advertir posible latencia y pedir confirmación o ajuste;
- si OpenAlex reporta más resultados que `max_results`, el agente debe advertirlo;
- si el usuario no aprueba trabajar con muestra acotada, corresponde refinar la query;
- si OpenAlex reporta más de `1000` resultados estimados, corresponde refinar la query antes del cribado inicial;
- el orden de relevancia de OpenAlex solo puede usarse como última instancia operativa si el refinamiento no logra bajar suficientemente el volumen.

Regla de trazabilidad:

- si la corrida obliga a refinar la query, antes de reemplazar la versión vigente el agente debe registrar en `query_history.md` la versión previa, el motivo del cambio y el efecto observado;
- el historial debe permitir reconstruir la secuencia de refinamientos del caso sin depender del recuerdo conversacional.

Regla metodológica de elegibilidad mínima para entrar al conjunto exportado:

- el caso puede exigir `abstract` disponible como filtro obligatorio de Fase 3;
- si el caso exige artículos revisados por pares, esto debe declararse metodológicamente y reflejarse al menos con `type=article`;
- OpenAlex no expone una bandera exacta de peer review, así que la verificación fina sigue siendo parte del cribado humano.

Salida:

- `search/raw_results.json`
- `search/normalized_results.json`
- `search/normalized_results.csv`
- `screening/screening_matrix.md`
- `search/search_log.md`
- `search/summary.json`

Pausa:

- revisar volumen, ruido y calidad del conjunto
- pedir autorización para pasar a Fase 4

Nota:

- aunque el script puede operar sin configuración como capacidad técnica general, en el flujo formal del skill esta fase debe ejecutarse con archivo de configuración.
- cuando el volumen exportado ya es una muestra acotada, Fase 4 trabaja sobre esa muestra y no sobre la totalidad estimada por OpenAlex.

### Fase 4. Cribado inicial

Entrada:

- `screening/screening_matrix.md`
- pregunta y criterios de inclusión/exclusión

Acción:

- clasificar cada registro como `Incluir`, `Excluir` o `Dudoso`
- completar en la misma matriz:
  - `Decision de cribado`
  - `Motivo de cribado`
  - `Criterio de cribado`
  - `Revisar texto completo`

Salida:

- misma `screening/screening_matrix.md` actualizada
- `screening/screening_summary_initial.md`

Pausa:

- pedir autorización para:
  - refinar búsqueda
  - o pasar a Fase 5

### Fase 5. Cribado focused

Entrada:

- registros `Incluir` y `Dudoso` heredados de `initial`
- pregunta de revision y criterios afinados
- matriz de cribado ya actualizada por `initial`

Acción:

- reevaluar solo el subconjunto priorizado
- aumentar la exigencia de pertinencia tematica y metodologica
- mantener la decision en la misma matriz y preparar el subconjunto que amerita validacion de acceso o texto completo

Regla de progreso:

- si el subconjunto de `focused` es grande, por ejemplo superior a 100 estudios, el agente debe informar avance periodico durante la revision para no volver opaco el proceso

Salida:

- matriz de cribado refinada
- resumen de cribado `focused`
- subconjunto priorizado para revisar acceso y full text

Pausa:

- si el conjunto sigue pobre o ruidoso, volver a Fase 2 y ajustar la query
- si el conjunto es pertinente, pedir autorizacion para pasar a Fase 6

## Regla para la revision humana entre `focused` y la selección final

Entre `focused` y el cierre de la selección final puede haber una revision humana supervisada de `screening/screening_matrix.md` o de su equivalente en CSV. Esa revision forma parte esperada del proceso.

Columnas que el humano puede editar libremente:

- `Decision de cribado`
- `Motivo de cribado`
- `Criterio de cribado`
- `Revisar texto completo`
- `Base de seleccion final`
- `Observacion de seleccion final`

Columnas que el humano puede corregir solo si hay evidencia clara:

- `Texto completo accesible`
- `Resumen disponible`
- `Tipo documental`
- `URL de acceso`
- `DOI`

Columnas que deben preservarse:

- `Codigo`
- `Titulo`
- `Autor/ano`
- `Primera afiliacion`
- `Pais`
- `Fuente`
- `Acceso abierto`
- `URL DOI`
- `URL OpenAlex`

Antes de pasar a la selección final, el agente debe asumir que:

- la edicion humana puede haber mejorado el juicio metodologico del caso;
- pero la estructura del archivo debe seguir siendo valida;
- no deben haberse renombrado columnas;
- no debe haberse modificado `Codigo`.

### Fase 6. Validación de accesibilidad y recuperación de full text

Entrada:

- subconjunto priorizado desde `focused`
- matriz de cribado refinada
- configuracion operativa del caso

Acción:

- verificar accesibilidad de texto completo
- recuperar localmente los archivos fuente cuando sea posible
- distinguir entre `pdf_fulltext`, `html_fulltext`, `landing_metadata_only` y `blocked_or_error`
- preparar texto legible para revisión asistida a partir de los `pdf_fulltext` y `html_fulltext`
- registrar que estudios tienen `texto completo` realmente util para lectura y cuales dependen de `Resumen y metadatos`

Salida:

- matriz con estado de accesibilidad actualizado
- carpeta `cases/<slug>/fulltext/` con archivos fuente recuperados
- log de recuperacion y resumen de accesibilidad
- directorio derivado `outputs/<corrida>/fulltext/review_text/`
- log y resumen de preparacion de texto para revision

Pausa:

- pedir autorizacion para pasar a Fase 7

### Fase 7. Selección final / evaluación de elegibilidad

Entrada:

- matriz refinada
- resultados de validacion de acceso y recuperacion de full text
- textos preparados para revision cuando existan
- observaciones del estudiante o docente

Acción:

- cerrar la seleccion del corpus final
- usar como base principal los textos preparados desde `pdf_fulltext` o `html_fulltext` cuando existan
- si no existe `texto completo`, justificar explicitamente el uso de `Resumen y metadatos`
- incorporar la revision humana supervisada como parte del cierre
- dejar el conjunto final sin dependencias metodologicas pendientes

Salida:

- `screening_decisions_final.csv`
- matriz final del caso
- corpus final confirmado humanamente

Pausa:

- confirmar que la selección final ya quedo cerrada por validacion humana
- pedir autorizacion para pasar a Fase 8

### Fase 8. Integración en Zotero

Entrada:

- `screening_decisions_final.csv` confirmado por el estudiante
- `screening/screening_matrix.csv` o `screening/screening_matrix.md` final
- configuración de Zotero disponible en el `.env` operativo del caso

Acción:

- preparar el paquete de importación para Zotero
- sincronizar los ítems bibliográficos con la colección objetivo
- copiar PDFs locales cuando existan y el flujo lo permita
- crear una nota hija mínima de trazabilidad del cribado final por estudio

Salida:

- manifiesto o artefactos de preparación para Zotero
- log de sincronización
- notas hijas mínimas de cribado final generadas o planificadas

Pausa:

- revisar el resultado de sincronización
- pedir autorizacion para pasar a Fase 9

## Regla de activación de Zotero

El agente debe pasar a Zotero solo cuando el caso haya cruzado claramente el umbral de `corpus final confirmado`.

Checklist mínima para activar Zotero:

- existe `screening_decisions_final.csv`;
- la selección final ya fue aplicada a la matriz del caso;
- no quedan registros `Dudoso` que afecten el corpus objetivo;
- la base de decisión final ya está marcada como `Texto completo` o `Resumen y metadatos`;
- el estudiante o docente ya confirmó que ese conjunto es el corpus a conservar;
- la configuración mínima de Zotero ya está disponible.

Si una de esas condiciones no se cumple:

- el agente no debe entrar todavía a Zotero;
- debe seguir en cribado, recuperación, revisión o cierre metodológico.

Regla simple:

- `selección final confirmada` -> sí toca Zotero
- `selección final pendiente` -> no toca Zotero
- `focused` o `initial` -> no toca Zotero

### Fase 9. Extracción de evidencia

Entrada:

- corpus final ya confirmado
- textos completos y metadatos finales

Acción:

- extraer evidencia verificable
- completar la matriz de extraccion
- agregar una nota hija nueva por estudio para la fase de extraccion

Salida:

- `extraction/extraction_matrix.md`
- observaciones de extraccion por estudio

Pausa:

- pedir autorizacion para pasar a Fase 10

### Fase 10. Evaluación de calidad

Entrada:

- corpus final confirmado
- matriz de extraccion

Acción:

- evaluar la calidad metodologica basica de los estudios incluidos
- documentar limitaciones y riesgos de interpretacion
- agregar una nota hija nueva por estudio para la fase de calidad

Salida:

- matriz o resumen de calidad

Pausa:

- pedir autorizacion para pasar a Fase 11

### Fase 11. Síntesis narrativa y auditoría final

Entrada:

- corpus final confirmado
- extraccion y evaluacion de calidad

Acción:

- redactar la sintesis narrativa
- declarar limites del corpus y del proceso
- revisar trazabilidad final

Salida:

- sintesis narrativa
- auditoria o checklist de cierre

Pausa:

- confirmar cierre del caso o necesidad de nueva corrida

## Reglas de operación sugeridas para el skill

Cuando el estudiante o docente diga `iniciar automatizacion`, el skill debería:

1. identificar la fase actual del caso;
2. explicar qué va a hacer en esa fase;
3. ejecutar solo esa fase;
4. mostrar el resultado;
5. pedir autorización breve para continuar.

Regla adicional:

6. no ejecutar una segunda fase mientras la actual siga abierta o sin revisar.

## Regla de trazabilidad

Cada iteración de búsqueda y cribado debe dejar sus propios artefactos en un directorio de salida independiente.

Como mínimo, cada iteración debe conservar:

- `search/query.txt`
- `search_log.md`
- `screening/screening_matrix.md`
- `screening_decisions_<fase>.csv`
- `screening_summary_<fase>.md`

Esto evita mezclar corridas distintas y permite justificar cómo evolucionó la estrategia de búsqueda y selección.

## Iteraciones de cribado

Para que el proceso sea comprensible y no se vuelva infinito, el cribado debe organizarse en un máximo de tres niveles por cada corrida de búsqueda:

### 1. `initial`

Objetivo:

- separar ruido evidente de señal potencial.

Base principal de decisión:

- título;
- resumen;
- metadatos básicos.

Salida esperada:

- muchos `Excluir`;
- un conjunto inicial de `Incluir` y `Dudoso`.

Artefactos sugeridos:

- `screening_decisions_initial.csv`
- `screening_summary_initial.md`

### 2. `focused`

Objetivo:

- reevaluar solo los `Incluir` y `Dudoso` del paso anterior;
- reducir el conjunto a estudios realmente fuertes para la pregunta del caso.

Base principal de decisión:

- título;
- resumen;
- mayor atención a:
  - contexto educativo;
  - tipo de participantes;
  - variables centrales;
  - claridad del diseño;
  - cercanía con el tema del estudiante.

Salida esperada:

- un conjunto más pequeño de `Incluir`;
- algunos `Dudoso` de reserva;
- descarte de estudios demasiado generales o redundantes.

Artefactos sugeridos:

- `screening_decisions_focused.csv`
- `screening_summary_focused.md`

Paso recomendado después de `focused`:

- validar accesibilidad real del texto completo solo sobre los registros `Incluir` y `Dudoso`;
- actualizar la columna `Texto completo accesible` en la matriz;
- intentar recuperar localmente el texto completo antes de la selección `final`.

### Subfase de recuperación local de texto completo

Objetivo:

- descargar o localizar localmente los documentos del subconjunto priorizado;
- distinguir entre:
  - `pdf_fulltext`;
  - `html_fulltext`;
  - `landing_metadata_only`;
  - `blocked_or_error`.

Artefactos sugeridos:

- carpeta local del caso, por ejemplo `cases/<tema-slug>/fulltext/`
- `fulltext/fulltext_download_log.csv`
- `fulltext_recovery_summary.md`
- `outputs/<corrida>/fulltext/review_text/`
- `fulltext/fulltext_review_text_log.csv`
- `fulltext/fulltext_review_text_summary.md`

Regla operativa:

- esta subfase ocurre después de `focused` y antes de la selección final;
- la selección final del apoyo automatizado debe apoyarse primero en los textos preparados desde `pdf_fulltext` o `html_fulltext`;
- si un estudio no pudo recuperarse, la selección final todavía puede hacerse con `Resumen y metadatos`, pero esa limitación debe quedar explícita.
- cuando un publisher imponga un challenge, puede usarse una sesión de navegador ya validada mediante un archivo de cookies exportado para intentar la recuperación asistida.

### 3. selección final / evaluación de elegibilidad

Objetivo:

- cerrar la selección antes de extracción de evidencia.

Base principal de decisión:

- lectura asistida de texto preparado cuando sea posible;
- si el texto completo no está disponible todavía, usar el resumen ampliado y dejar la limitación explícita.

Regla:

- aquí ya no basta solo con el título.
- idealmente, esta etapa confirma elegibilidad definitiva para extracción.
- si no hay texto completo, la selección final puede hacerse con la mejor evidencia disponible, pero debe quedar marcada como selección final sin texto completo.

Salida esperada:

- conjunto final candidato para texto completo y extracción;
- justificación clara de por qué entran esos estudios y no otros.
- indicación explícita de la base de selección final:
  - `Texto completo`
  - `Resumen y metadatos`

Artefactos sugeridos:

- `screening_decisions_final.csv`
- `screening/screening_summary_final.md`
- actualización de `screening/screening_matrix.md` con:
  - `Base de seleccion final`
  - `Observacion de seleccion final`

Campos recomendados en la matriz para esta etapa:

- `Texto completo accesible`
- `Base de seleccion final`
- `Observacion de seleccion final`

### Paso posterior: confirmación humana e integración en Zotero

El cierre real de la selección final ocurre cuando el estudiante o docente confirma manualmente el conjunto.

Solo después de esa confirmación conviene integrar el corpus en Zotero.

Decisión operativa para el agente:

- si el usuario pide `continuar` y el corpus final ya está confirmado, la siguiente fase natural es Zotero;
- si el usuario pide `continuar` pero el corpus final todavía no está confirmado, el agente no debe saltar a Zotero aunque la configuración exista.

Reglas acordadas:

- se integran todos los estudios resultantes del cribado final confirmado;
- no se limita la integración solo a documentos con PDF;
- si existe PDF local, el flujo actual lo copia primero a la carpeta configurada de Zotero;
- no se adjunta el `.txt` extraído;
- el ítem debe conservar la URL de origen;
- si el ítem ya existe, se complementa su metadata;
- si ya existe en otra colección, también debe añadirse a la colección objetivo.
- en Fase 8 conviene crear una nota hija mínima de trazabilidad por ítem;
- en Fase 9 conviene agregar una nota hija nueva de extracción por ítem;
- en Fase 10 conviene agregar una nota hija nueva de calidad por ítem.

Parámetros mínimos esperados para la integración:

- esta configuración debe vivir en el archivo `.env` del proyecto;
- nombre de la librería Zotero;
- nombre de la colección destino;
- ruta de la carpeta local fuente con PDFs;
- ruta de la carpeta que Zotero usa para enlazar o almacenar PDFs;
- ruta a los artefactos del cribado final.

Parámetros reservados en la plantilla de configuración:

- `ZOTERO_LIBRARY`
- `ZOTERO_MCP_URL`
- `ZOTERO_COLLECTION`
- `ZOTERO_ATTACHMENTS_DIR`
- `ZOTERO_LIBRARY_FILES_DIR`
- `ZOTERO_SCREENING_DECISIONS`
- `ZOTERO_SCREENING_MATRIX`

Scripts ya disponibles para esta etapa:

- `scripts/prepare_zotero_import.py`
- `scripts/sync_zotero_mcp.py`
- `scripts/write_zotero_notes.py`
- `scripts/zotero_mcp_client.py`

Limitación práctica actual:

- el MCP de Zotero sí permite trabajar con colecciones e ítems bibliográficos;
- también permite crear notas hijas estructuradas;
- actualmente no expone una operación directa para importar un PDF local como attachment nuevo;
- por eso el flujo puede copiar PDFs a la carpeta configurada de Zotero y sincronizar metadata, pero el enlace automático del PDF como attachment requiere una capacidad futura del MCP o un paso auxiliar/manual.

## Límite recomendado

- No pasar de `initial`, `focused` y selección final dentro de la misma corrida.
- Si después de la selección final el conjunto sigue siendo demasiado amplio o poco pertinente, no conviene inventar una cuarta ronda.
- En ese caso, lo correcto es volver a refinar la búsqueda y lanzar una nueva corrida.

## Regla simple para estudiantes

Puede entenderse así:

- `initial`: filtro rápido con `título + resumen`.
- `focused`: filtro más fino, todavía principalmente con `título + resumen`.
- después de `focused`: validación operativa de accesibilidad y recuperación local del texto completo sobre el subconjunto priorizado.
- selección final / evaluación de elegibilidad: confirmación antes de extracción, preferiblemente con `texto completo`.

La idea es no leer textos completos demasiado pronto, pero tampoco cerrar la selección definitiva solo con resúmenes.

## Frases de transición sugeridas

- `Fase 1 completada. ¿Autorizas que pase a la construcción de la query inicial?`
- `La query ya quedó guardada en search/query.txt. ¿Autorizas ejecutar la búsqueda en OpenAlex?`
- `La búsqueda ya generó una matriz inicial. ¿Autorizas el cribado preliminar sobre esa misma matriz?`
- `El cribado sugiere refinar la estrategia. ¿Prefieres ajustar la query o pasar a extracción solo con los casos dudosos?`
