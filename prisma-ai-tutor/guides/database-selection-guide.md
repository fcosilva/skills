# Guía de selección de bases de datos

Fecha de referencia de esta guía: 2026-05-09.

## Propósito

Esta guía explica por qué el curso pide combinar una fuente abierta, una fuente comercial y una fuente regional. La intención no es abrumar al estudiante con demasiadas bases, sino equilibrar:

- trazabilidad y reproducibilidad;
- calidad de curación bibliográfica;
- cobertura regional y en español.

## Regla curricular recomendada

Para esta asignatura se recomienda exigir:

1. `OpenAlex` como fuente abierta obligatoria.
2. `Scopus` como fuente comercial obligatoria.
3. `SciELO` o `Redalyc` como fuente regional obligatoria.

Opcionales:

- `Web of Science` como sustituto o validación de la fuente comercial.
- `Dimensions` como fuente complementaria avanzada.

## Tabla comparativa general

| Base | Tipo | Acceso | Cobertura reportada oficialmente | Qué cubre | Valor principal para el curso |
|---|---|---|---|---|---|
| OpenAlex | Abierta | API abierta | `240M+` works en la documentación técnica; `474M+` a `477M+` scholarly works en la ayuda institucional | Artículos, libros, datasets, tesis y otros trabajos académicos | Reproducibilidad, automatización y acceso abierto |
| Scopus | Comercial | Suscripción y APIs oficiales | `100M+` records | Revistas, preprints, libros y actas de conferencias | Curación fuerte y prestigio académico |
| Web of Science Core Collection | Comercial | Suscripción y APIs oficiales | `97M+` records conectados; la plataforma completa reporta `271M+` records | Revistas arbitradas, proceedings y libros académicos | Alta confianza editorial y validación de calidad |
| Dimensions | Comercial / institucional | Plataforma y API bajo licencia; versión gratuita limitada | `140M+` publications en la versión gratuita; otras páginas del proveedor reportan `160M+` global publications | Publicaciones, datasets, grants, patents, policy y más | Vista conectada del ecosistema de investigación |
| SciELO | Regional | Acceso web abierto | La cobertura varía por colección y no se presenta como un solo conteo global estable en una página oficial equivalente | Revistas científicas iberoamericanas y regionales | Visibilidad regional, español y portugués |
| Redalyc | Regional | Acceso web abierto | La cobertura varía por portal y colección; no encontré un conteo global oficial único comparable | Revistas científicas iberoamericanas y regionales | Cobertura latinoamericana y pertinencia contextual |

## Tabla comparativa para decisión docente

| Base | Fortalezas | Riesgos o límites | Recomendación de uso en el curso |
|---|---|---|---|
| OpenAlex | Abierta, automatizable, transparente y reproducible | Metadatos heterogéneos según la fuente de origen | Obligatoria como base abierta |
| Scopus | Curación fuerte, prestigio, buena cobertura interdisciplinaria | Acceso restringido por licencia | Obligatoria como base comercial si hay acceso |
| Web of Science | Selección editorial muy exigente, buena trazabilidad | Acceso restringido; puede ser menos accesible operativamente | Sustituto o validación de Scopus |
| Dimensions | Gran riqueza contextual, enlaces con grants y patents, full-text indexing en gran parte de la base | Menor replicabilidad en aula si no todos tienen acceso | Complementaria, no obligatoria |
| SciELO | Acceso abierto, fuerte presencia regional, útil para literatura en español y portugués | Menor homogeneidad global que las bases comerciales | Obligatoria como opción regional |
| Redalyc | Acceso abierto, foco iberoamericano, valor regional alto | Menor claridad en automatización y métricas globales | Obligatoria como opción regional |

## Por qué no exigir demasiadas bases a la vez

Pedir muchas fuentes puede parecer metodológicamente fuerte, pero en cursos iniciales suele producir:

- más carga operativa que aprendizaje real;
- errores en la documentación de cadenas;
- duplicados mal controlados;
- falsa sensación de exhaustividad.

Por eso, para este curso, una combinación de tres categorías es más pedagógica:

- una abierta;
- una comercial;
- una regional.

## Justificación breve de cada categoría

### 1. Fuente abierta: OpenAlex

Se recomienda porque permite enseñar:

- búsqueda reproducible;
- acceso por API;
- documentación clara de resultados;
- autonomía del estudiante fuera de plataformas cerradas.

## 2. Fuente comercial: Scopus

Se recomienda porque aporta:

- selección y curación reconocidas;
- cobertura amplia de revistas, libros y conferencias;
- una referencia estándar en muchos trabajos académicos.

`Web of Science` puede cumplir una función equivalente si es la base más disponible en la institución.

## 3. Fuente regional: SciELO o Redalyc

Se recomienda porque reduce el sesgo anglocéntrico y mejora:

- pertinencia latinoamericana;
- acceso a literatura en español y portugués;
- visibilidad de contextos regionales que no siempre aparecen bien representados en bases comerciales.

## Nota sobre cifras de cobertura

Las cifras de cobertura cambian con el tiempo y no siempre son directamente comparables, porque cada proveedor cuenta cosas distintas:

- `works`
- `records`
- `publications`
- documentos de varias clases en una misma plataforma

Por eso, estas cifras deben leerse como una referencia comparativa general, no como un criterio único para decidir calidad metodológica.

## Fuentes oficiales

- OpenAlex works: https://docs.openalex.org/api-entities/works
- OpenAlex about the data: https://help.openalex.org/hc/en-us/articles/24397285563671-About-the-data
- OpenAlex about us: https://help.openalex.org/hc/en-us/articles/24396686889751-About-us
- Scopus product page: https://www.elsevier.com/products/scopus
- Scopus content page: https://www.elsevier.com/en-gb/products/scopus/content
- Web of Science Core Collection: https://clarivate.com/products/scientific-and-academic-research/research-discovery-and-workflow-solutions/webofscience-platform/web-of-science-core-collection/
- Dimensions free version: https://www.dimensions.ai/products/all-products/dimensions-free-version/
- Dimensions analytics: https://www.dimensions.ai/products/all-products/dimensions-analytics/
- Dimensions homepage: https://www.dimensions.ai/
