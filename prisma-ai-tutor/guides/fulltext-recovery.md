# Recuperación verificable de texto completo

## Objetivo

Recuperar PDF o HTML por vías legítimas y demostrar que el archivo contiene texto
académico legible antes de marcarlo como accesible.

## Secuencia obligatoria

1. Validar de forma preliminar la URL registrada. Este paso solo produce una
   pista remota (`Por verificar`), nunca el valor final `Si`.
2. Ejecutar la recuperación multivía con download_fulltext.py.
3. Auditar los archivos locales con audit_fulltext_recovery.py --apply.
4. Preparar texto con prepare_fulltext_review_text.py y pasar `--matrix` y
   `--decisions` para sincronizar todo el subconjunto focused/final.
5. Confirmar la identidad bibliográfica con al menos dos señales entre título,
   DOI, primer autor y año. Poner los `identity_mismatch` en cuarentena.
6. Usar como evidencia final el estado `prepared` con identidad `confirmed`, no
   la extensión, el host, el Content-Type ni una validación remota.

## Rutas de recuperación

El descargador prueba y registra, sin eludir controles de acceso:

- URL de acceso de la matriz;
- ubicaciones explícitamente abiertas descubiertas por DOI en OpenAlex,
  priorizando `pdf_url` y descartando ubicaciones primarias no OA;
- ubicaciones abiertas de Unpaywall cuando existe un correo de contacto;
- copias de Europe PMC cuando el DOI está indexado;
- URL DOI o editorial para registros OA, o cuando se activa
  --try-non-oa-direct;
- enlaces PDF declarados mediante citation_pdf_url y enlaces de descarga
  presentes en una landing.

Cada URL probada se registra en fulltext_attempt_log.csv. La ruta que produjo el
archivo final queda en fulltext_download_log.csv.

Los valores por defecto pueden centralizarse en base.env o sobrescribirse por
caso mediante PRISMA_FULLTEXT_DISCOVERY_SOURCES,
PRISMA_FULLTEXT_REQUEST_DELAY, PRISMA_FULLTEXT_MAX_LINKED_CANDIDATES y
PRISMA_FULLTEXT_TRY_NON_OA_DIRECT. Los argumentos de línea de comandos tienen
prioridad.

## Evidencia de contenido

- Aceptar PDF solo si el contenido comienza con la firma %PDF-.
- Aceptar HTML solo cuando contenga cuerpo académico sustantivo y varias
  secciones reconocibles.
- Clasificar como landing una página con resumen, metadatos o navegación sin
  cuerpo completo.
- Tratar PubMed y rutas `article-abstract`, `abstract` o `abs` como landing,
  salvo que una ruta no PubMed demuestre un cuerpo académico completo.
- Clasificar como blocked_or_error un challenge humano, una respuesta vacía
  dependiente de scripts o una página de bloqueo.
- Confirmar legibilidad únicamente después de extraer texto por encima del
  umbral configurado.

## Comandos

Validación remota preliminar:

    python3 .codex/skills/prisma-ai-tutor/scripts/validate_fulltext_access.py \
      --matrix outputs/<corrida>/screening/screening_matrix.csv \
      --decisions outputs/<corrida>/screening/screening_decisions_focused.csv \
      --resume

Recuperación:

    python3 .codex/skills/prisma-ai-tutor/scripts/download_fulltext.py \
      --matrix outputs/<corrida>/screening/screening_matrix.csv \
      --decisions outputs/<corrida>/screening/screening_decisions_focused.csv \
      --output-dir outputs/<corrida>/fulltext \
      --config-file cases/<caso>/case.env \
      --resume

Auditoría:

    python3 .codex/skills/prisma-ai-tutor/scripts/audit_fulltext_recovery.py \
      --download-log outputs/<corrida>/fulltext/fulltext_download_log.csv \
      --apply

Preparación y sincronización:

    python3 .codex/skills/prisma-ai-tutor/scripts/prepare_fulltext_review_text.py \
      --input-dir outputs/<corrida>/fulltext \
      --output-dir outputs/<corrida>/fulltext/review_text \
      --download-log outputs/<corrida>/fulltext/fulltext_download_log.csv \
      --matrix outputs/<corrida>/screening/screening_matrix.csv \
      --decisions outputs/<corrida>/screening/screening_decisions_focused.csv \
      --resume

El preparador usa el CSV como representación canónica, valida esquema, filas
malformadas, códigos duplicados y códigos ausentes antes de reemplazar de forma
coordinada el CSV y el Markdown. Un documento legible pero incompatible se
mueve por defecto a `fulltext/quarantine_bibliographic_mismatch/` y no genera texto
de revisión.

## Controles humanos y acceso

No intentar resolver, simular ni evadir CAPTCHA, Cloudflare u otros verificadores
humanos. Usar una sesión autorizada solo cuando la persona haya completado el
desafío y los términos del sitio permitan reutilizar sus cookies. Como
alternativas, buscar repositorios abiertos, acceso institucional, entrega manual
del PDF o solicitud al autor.

No interpretar No confirmado como inexistencia del documento. Significa que las
vías intentadas no produjeron texto completo legible en esa corrida.

## Reanudación y trazabilidad

Usar `--resume` para conservar archivos previamente verificados. Tanto la
validación como la descarga y la preparación escriben logs incrementales y
reportan progreso; una interrupción no obliga a reiniciar los positivos.
Conservar juntos:

- fulltext_attempt_log.csv;
- fulltext_download_log.csv;
- fulltext_content_audit.csv y su resumen;
- fulltext_review_text_log.csv y su resumen;
- quarantine_bibliographic_mismatch cuando exista;
- carpeta review_text.
