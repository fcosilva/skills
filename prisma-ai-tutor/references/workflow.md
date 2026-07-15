# Flujo de trabajo consolidado

Este documento resume el flujo conceptual vigente de `PRISMA-AI Tutor`.

Uso recomendado:

- usa este archivo para entender o auditar la lógica metodológica de cada fase;
- usa `guides/automation-by-phases.md` para comandos, scripts, artefactos detallados y pausas operativas;
- si hay conflicto entre ambos documentos, prevalece `guides/automation-by-phases.md` como guía operativa.

## Principios transversales

- Las fases son secuenciales: no se ejecutan en paralelo ni se saltan sin cierre explícito.
- Toda decisión de inclusión o exclusión debe tener criterio y justificación.
- El agente propone cribados y síntesis, pero el corpus final requiere confirmación humana.
- `initial` y `focused` se basan principalmente en título, resumen y metadatos.
- La selección final solo puede incluir estudios con texto completo accesible y legible.
- La extracción y calidad comienzan como propuestas adaptadas al caso, requieren validación humana por fila y solo después alimentan síntesis e informe.

## Fase 1. Delimitación del tema

Objetivo:

- evaluar si el tema es viable como mini revisión sistemática formativa;
- delimitar población/problema, intervención o fenómeno de interés, contexto y alcance.

Salida esperada:

- diagnóstico de viabilidad;
- tema delimitado;
- pregunta preliminar;
- objetivo preliminar;
- palabras clave iniciales;
- advertencias de alcance.

## Fase 2. Construcción y validación de la estrategia de búsqueda

Objetivo:

- formular la pregunta de revisión y traducirla en queries por fuente.

Debe incluir:

- pregunta de revisión recomendada;
- criterios de inclusión y exclusión;
- periodo, idiomas y tipos documentales;
- fuentes activas;
- query adaptada por fuente;
- aprobación humana antes de ejecutar búsquedas.

Regla clave:

- si hay varias fuentes, no se debe asumir que una misma sintaxis sirve para todas.
- cada fuente debe tener su propio `outputs/<corrida>/search/<fuente>/query.txt`.
- no se deben guardar queries operativas en `cases/<slug>/search/`.

## Fase 3. Búsqueda automatizada multi-fuente

Objetivo:

- ejecutar las fuentes activas, normalizar resultados y preparar la matriz común.

Fuentes programáticas habituales:

- `OpenAlex`;
- `DOAJ`;
- `Semantic Scholar`;
- `Lens`, si existe `LENS_API_KEY`;
- `Redalyc`, si existe API key;
- `PubMed`, cuando el tema es biomédico o de salud;
- `Scopus`, cuando hay API suficiente o CSV manual configurado.

Salida esperada:

- `outputs/<corrida>/search/<fuente>/raw_results.json`;
- `outputs/<corrida>/search/<fuente>/normalized_results.json`;
- `outputs/<corrida>/search/<fuente>/normalized_results.csv`;
- `outputs/<corrida>/search/<fuente>/search_log.md`;
- `outputs/<corrida>/search/<fuente>/summary.json`;
- `search/merged_normalized_results.*` cuando hay más de una fuente;
- `search/source_merge_log.*`;
- `screening/screening_matrix.*`.

Regla clave:

- si hay más de una fuente, se fusiona y deduplica al cierre de Fase 3 antes de cualquier cribado.

## Fase 4. Cribado inicial

Objetivo:

- separar ruido evidente de señal potencial.

Base de decisión:

- título;
- resumen;
- metadatos básicos.

Salida esperada:

- `screening/screening_decisions_initial.csv`;
- `screening/screening_summary_initial.md`;
- matriz actualizada.

Regla clave:

- el agente propone el cribado inicial; el usuario revisa, corrige o aprueba.

## Fase 5. Cribado focused

Objetivo:

- reevaluar solo los registros `Incluir` y `Dudoso` del cribado inicial.

Base de decisión:

- título;
- resumen;
- metadatos básicos;
- mayor exigencia de alineación temática y metodológica.

Salida esperada:

- `screening/screening_decisions_focused.csv`;
- `screening/screening_summary_focused.md`;
- matriz actualizada.

Regla clave:

- todavía no es selección final; no debe cerrarse el corpus sin revisar accesibilidad y texto completo.

## Fase 6. Validación de accesibilidad y recuperación local de texto completo

Objetivo:

- verificar accesibilidad a texto completo;
- descargar PDF/HTML solo después de autorización;
- preparar texto crudo legible para la selección final.

Secuencia recomendada:

- verificar accesibilidad sin descarga masiva;
- actualizar matriz;
- pedir autorización para descargar;
- recuperar por varias rutas legítimas y registrar cada URL intentada;
- validar la firma PDF o el cuerpo académico HTML;
- auditar falsos positivos y falsos negativos del descargador;
- extraer texto plano verificable y sincronizar la matriz desde los estados `prepared`.

Salida esperada:

- `fulltext/fulltext_access_validation.*`;
- `fulltext/fulltext_download_log.csv`;
- `fulltext/fulltext_attempt_log.csv`;
- `fulltext/fulltext_content_audit.csv`;
- `fulltext/fulltext_recovery_summary.md`;
- `fulltext/review_text/`;
- `fulltext/fulltext_review_text_log.csv`;
- `fulltext/fulltext_review_text_summary.md`.

Regla clave:

- descargar no equivale a leer; solo la extracción verificable confirma texto legible.
- no se deben evadir challenges, CAPTCHA ni verificadores humanos.

## Fase 7. Selección final o evaluación de elegibilidad

Objetivo:

- cerrar el corpus antes de extracción.

Base de decisión:

- texto completo accesible y legible;
- criterios de inclusión/exclusión;
- observaciones de elegibilidad.

Salida esperada:

- `screening/screening_decisions_final.csv`;
- `screening/screening_summary_final.md`;
- matriz actualizada con base de selección final.

Regla clave:

- un estudio sin texto completo accesible no entra al corpus final.
- el cierre real ocurre solo cuando el estudiante o docente confirma humanamente el corpus.

## Fase 8. Integración bibliográfica en Zotero

Objetivo:

- preservar el corpus final confirmado en Zotero y crear trazabilidad mínima por ítem.

Entrada:

- corpus final confirmado;
- configuración Zotero completa;
- rutas vigentes en `case.env`.

Salida esperada:

- paquete de importación;
- resumen de sincronización;
- acciones Zotero;
- nota hija mínima de `screening` por cada ítem.

Regla clave:

- la fase no cierra solo porque los ítems existan en Zotero; también debe existir la nota mínima de trazabilidad.
- usar la fuente normalizada fusionada cuando corresponda, rechazar manifiestos bibliográficamente vacíos o duplicados y ejecutar una sola sincronización de escritura por colección.

## Fase 9. Extracción de evidencia

Objetivo:

- extraer datos verificables desde el texto completo del corpus final.

Secuencia:

- proponer protocolo, unidad de análisis y campos según la pregunta y los diseños;
- obtener validación humana de la plantilla;
- generar extracción asistida con localizadores y estado pendiente;
- obtener correcciones o validación humana de todas las filas;
- ejecutar el gate antes del cierre y de las notas Zotero.

Debe registrar:

- autor/año;
- título;
- objetivo;
- método;
- contexto;
- muestra o corpus;
- tecnología o fenómeno estudiado;
- hallazgos principales;
- limitaciones;
- relevancia para la pregunta.

Salida esperada:

- `extraction/extraction_matrix.md`;
- `extraction/extraction_summary.md`;
- notas hijas de extracción en Zotero cuando corresponda.

Regla clave:

- si un dato no aparece en el texto revisado, se escribe `No reportado`.
- una matriz poblada no equivale a fase cerrada; puede tener varias filas por estudio y permanece como propuesta hasta validar cada fila.

## Fase 10. Evaluación de calidad

Objetivo:

- valorar calidad metodológica básica y riesgos de interpretación.

Secuencia:

- inventariar diseños y proponer criterios o instrumentos pertinentes;
- validar humanamente el protocolo antes de valorar;
- generar valoraciones asistidas con evidencia, localizadores y estado pendiente;
- revisar o corregir humanamente cada fila y ejecutar el gate de cierre.

Criterios mínimos:

- objetivo claro;
- método claro;
- datos suficientes;
- contexto o muestra descrita;
- limitaciones reconocidas.

Salida esperada:

- `quality/quality_matrix.md`;
- `quality/quality_summary.md`;
- notas hijas de calidad en Zotero cuando corresponda.

Regla clave:

- la calidad no elimina automáticamente estudios; ayuda a interpretar el peso de la evidencia.
- no confundir adecuación de reporte, riesgo de sesgo y propiedades de medición, ni sumar escalas incompatibles sin justificación aprobada.

## Fase 11. Síntesis narrativa, auditoría e informe final

Objetivo:

- integrar evidencia;
- declarar límites;
- revisar trazabilidad final;
- generar el informe final solo si el humano lo confirma.

Acción:

- redactar síntesis narrativa;
- contrastar hallazgos, coincidencias, diferencias y vacíos;
- declarar limitaciones del corpus y del proceso;
- ejecutar auditoría o checklist de cierre;
- pedir confirmación humana antes de generar `informe_final.md`.
- generar antes una matriz código interno–Zotero–cita APA–referencia y validar enlaces documentales/localizadores de la narrativa.

Salida esperada:

- `synthesis/narrative_synthesis.md`;
- `synthesis/final_audit.md`;
- `synthesis/informe_final.md`, solo con autorización humana explícita.

Contenido mínimo sugerido para `informe_final.md`:

- título;
- resumen;
- introducción;
- pregunta y objetivo;
- método resumido;
- fuentes y estrategia de búsqueda;
- criterios de inclusión/exclusión;
- flujo de búsqueda, cribado y selección;
- caracterización del corpus final;
- síntesis de hallazgos;
- evaluación de calidad y limitaciones;
- declaración de uso de IA;
- referencias.

Regla clave:

- el informe final no reemplaza los artefactos de trazabilidad; los integra en un documento legible para entrega académica.
- el informe usa APA 7 autor–fecha; los códigos internos quedan en auditorías y no sustituyen citas bibliográficas.
