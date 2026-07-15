# Flujo posterior a la selección final

## Alcance

Usar esta guía para Zotero, extracción, calidad, síntesis e informe final. Estas fases solo comienzan después de la confirmación humana del corpus.

## Zotero

1. Preparar el manifiesto desde `search/merged_normalized_results.json` en corridas multifuente o `normalized_results.json` en corridas simples.
2. Detenerse si falta la fuente normalizada, está vacía, toda la metadata enriquecida está vacía o existen códigos/identidades duplicados.
3. Ejecutar primero `sync_zotero_mcp.py --dry-run` y revisar el manifiesto.
4. Ejecutar una sola sincronización de escritura. El bloqueo por biblioteca/colección impide dos procesos concurrentes.
5. Actualizar solo campos vacíos de ítems existentes. No retirar, mover, fusionar ni borrar duplicados sin auditoría y autorización explícita.
6. Cerrar la fase únicamente después de comprobar ítems canónicos y notas hijas de `screening`.

## Extracción como propuesta específica del caso

1. Leer pregunta, objetivo, criterios y tipos de estudio del corpus.
2. Proponer `extraction_protocol.md` y una plantilla adaptada. Definir unidad de fila, campos, vocabularios, tratamiento de revisiones y localizadores.
3. Mostrar la plantilla al humano y esperar aprobación antes de extraer. Archivar pilotos no aprobados y no tratarlos como evidencia válida.
4. Generar una propuesta asistida desde textos completos confirmados. Escribir `No reportado` cuando falte evidencia y separar texto explícito de categorización inferida.
5. Marcar cada fila como `Pendiente` hasta su revisión humana. Permitir múltiples filas por estudio cuando la unidad aprobada sea mecanismo, intervención o resultado.
6. Tras correcciones y validación, ejecutar:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/validate_human_review_gate.py \
  --matrix outputs/<corrida>/extraction/extraction_matrix.csv \
  --phase extraction
```

7. Solo un gate positivo permite cerrar Fase 9, escribir notas Zotero o usar la extracción en calidad y síntesis.

## Calidad como propuesta específica del diseño

1. Inventariar los diseños presentes y proponer criterios o instrumentos pertinentes para cada grupo.
2. Acordar con el humano el propósito: adecuación de reporte, riesgo de sesgo, propiedades de medición u otro. No tratarlos como equivalentes.
3. Usar `Sí`, `Parcial`, `No` y `No aplica` con evidencia y justificación. No penalizar protocolos por no tener resultados ni aplicar criterios de primarios a revisiones.
4. No mezclar puntuaciones de instrumentos distintos en una escala común salvo justificación metodológica aprobada.
5. Mantener todas las valoraciones como propuestas pendientes hasta la revisión humana y ejecutar:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/validate_human_review_gate.py \
  --matrix outputs/<corrida>/quality/quality_matrix.csv \
  --phase quality
```

6. La calidad informa el peso interpretativo; no excluye automáticamente estudios.

## Notas Zotero posteriores

`write_zotero_notes.py` acepta CSV o Markdown, reconoce `Codigo`, `Código`, `Codigo estudio` y `Código estudio`, y consolida todas las filas de un estudio sin descartarlas. Para `extraction` o `quality`, rechaza matrices sin validación humana completa.

## Síntesis narrativa

- Usar únicamente extracción y calidad validadas.
- Distinguir estudios únicos, instancias estudio–mecanismo y mecanismos canónicos; declarar denominadores de porcentajes.
- No convertir frecuencia de reporte, frecuencia de uso y eficacia en equivalentes.
- Conservar `No reportado` como ausencia de información, no como ausencia de la práctica.
- Escribir un párrafo por línea física, sin cortes manuales dentro del párrafo.
- En artefactos de auditoría, usar ``[`Mxxx`](../fulltext/fuente.pdf) [`Lxxx`](../fulltext/review_text/fuente.txt)`` sin paréntesis añadidos. `M` enlaza al PDF/HTML y `L` al texto derivado; el número de línea es un localizador separado y no implica salto automático.
- Validar rutas relativas desde el archivo narrativo, existencia de destinos, identidad bibliográfica y rango de localizadores.

Ejecutar la auditoría reproducible antes de validar la síntesis:

```bash
python3 .codex/skills/prisma-ai-tutor/scripts/audit_synthesis_links.py \
  --synthesis outputs/<corrida>/synthesis/narrative_synthesis.md
```

## Informe final y APA 7

Antes del informe final, crear y revisar una matriz `ID interno ↔ elemento Zotero ↔ cita APA ↔ referencia`. Comprobar unicidad, autoría colectiva, preprints, capitalización, volumen, número, páginas y DOI. Los códigos internos sirven para trazabilidad, pero el informe usa citas APA autor–fecha. La ausencia de alertas automáticas no sustituye validación humana.

## Auditoría opcional de disponibilidad

Al cierre puede analizarse el sesgo por acceso solo entre registros que superaron `focused` y llegaron a recuperación. Separar no OA según metadata de fallos técnicos en publicaciones declaradas abiertas; `No confirmado` no equivale automáticamente a paywall. Desagregar, cuando sea posible, revista, fuente, país y periodo.
