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
2. `DOAJ` como fuente abierta curada y reproducible.
3. `Semantic Scholar` como fuente semántica complementaria por defecto.
4. `Redalyc` como fuente regional programática cuando exista API key.

Opcionales:

- `Scopus` como fuente comercial si existe acceso institucional, CSV exportado o API key suficiente.
- `Web of Science` solo como alternativa institucional si ya existe acceso; no forma parte del flujo operativo recomendado del skill.
- `Dimensions` como fuente complementaria avanzada.

## Tabla comparativa general

| Base | Tipo | Acceso | Cobertura reportada oficialmente | Qué cubre | Valor principal para el curso |
|---|---|---|---|---|---|
| OpenAlex | Abierta | API abierta | `240M+` works en la documentación técnica; `474M+` a `477M+` scholarly works en la ayuda institucional | Artículos, libros, datasets, tesis y otros trabajos académicos | Reproducibilidad, automatización y acceso abierto |
| Semantic Scholar | Abierta | API abierta con key recomendada | Cobertura amplia de literatura académica indexada por Semantic Scholar | Artículos, conferencias y otros trabajos académicos con búsqueda por relevancia semántica | Sensibilidad temática y recuperación complementaria |
| Scopus | Comercial | Suscripción y APIs oficiales | `100M+` records | Revistas, preprints, libros y actas de conferencias | Curación fuerte y prestigio académico |
| Web of Science Core Collection | Comercial | Suscripción y APIs oficiales | `97M+` records conectados; la plataforma completa reporta `271M+` records | Revistas arbitradas, proceedings y libros académicos | Alta confianza editorial, pero acceso operativo restringido |
| Dimensions | Comercial / institucional | Plataforma y API bajo licencia; versión gratuita limitada | `140M+` publications en la versión gratuita; otras páginas del proveedor reportan `160M+` global publications | Publicaciones, datasets, grants, patents, policy y más | Vista conectada del ecosistema de investigación |
| SciELO | Regional | Acceso web abierto | La cobertura varía por colección y no se presenta como un solo conteo global estable en una página oficial equivalente | Revistas científicas iberoamericanas y regionales | Visibilidad regional, español y portugués |
| Redalyc | Regional | Acceso web abierto | La cobertura varía por portal y colección; no encontré un conteo global oficial único comparable | Revistas científicas iberoamericanas y regionales | Cobertura latinoamericana y pertinencia contextual |

## Tabla comparativa para decisión docente

| Base | Fortalezas | Riesgos o límites | Recomendación de uso en el curso |
|---|---|---|---|
| OpenAlex | Abierta, automatizable, transparente y reproducible | Metadatos heterogéneos según la fuente de origen | Obligatoria como base abierta |
| Semantic Scholar | Búsqueda semántica, abstracts y PDFs OA cuando están disponibles | No ofrece sintaxis booleana estricta ni búsqueda formal por title/abstract/keywords | Fuente complementaria por defecto para aumentar sensibilidad |
| Scopus | Curación fuerte, prestigio, buena cobertura interdisciplinaria | Acceso restringido por licencia | Condicionada a acceso institucional, CSV o API suficiente |
| Web of Science | Selección editorial muy exigente, buena trazabilidad | Acceso restringido incluso para búsqueda web; menor viabilidad en aula sin suscripción | No recomendado para el flujo por defecto; usar solo si la institución ya ofrece acceso |
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

### 1b. Fuente semántica complementaria: Semantic Scholar

Se incluye por defecto porque aporta:

- búsqueda por relevancia semántica;
- recuperación de `abstract` cuando está disponible;
- enlaces a `openAccessPdf` cuando la fuente los reporta;
- cobertura especialmente útil en temas de IA, computación, software, educación y ciencia de datos.

Limitación metodológica:

- no debe tratarse como búsqueda booleana estricta;
- no reemplaza las queries por campo de fuentes como PubMed o Scopus;
- su función es aumentar sensibilidad y descubrir literatura potencialmente relevante, sabiendo que la deduplicación posterior controlará el solapamiento.

## 2. Fuente comercial: Scopus

Se recomienda porque aporta:

- selección y curación reconocidas;
- cobertura amplia de revistas, libros y conferencias;
- una referencia estándar en muchos trabajos académicos.

`Web of Science` puede cumplir una función equivalente solo si ya existe acceso institucional claro. Si no hay acceso, no conviene incluirlo en el flujo operativo.

## 3. Fuente regional: SciELO o Redalyc

Se recomienda porque reduce el sesgo anglocéntrico y mejora:

- pertinencia latinoamericana;
- acceso a literatura en español y portugués;
- visibilidad de contextos regionales que no siempre aparecen bien representados en bases comerciales.

### Estado operativo actual de las fuentes regionales

Para el uso real del skill conviene distinguir entre valor metodológico y madurez operativa:

- `SciELO` sigue siendo valioso como fuente regional, pero su automatización programática todavía no forma parte del flujo normal del skill;
- `SciELO Search` puede bloquear clientes HTTP simples, así que hoy se considera una vía experimental o semiasistida;
- `Redalyc` sí expone una API documentada y requiere `API key` para las búsquedas;
- en pruebas reales con clave válida, `Redalyc` ya devolvió registros JSON con `título`, `autores`, `dc_description` como resumen cuando está disponible, `año`, `tipo documental`, `idioma`, `fuente` y referencia al `PDF`;
- la API documentada no expone un filtro directo por resumen, así que su recuperación se parece más a `title + filtros metadata` que a una búsqueda simétrica por `título + abstract`;
- por eso, en el estado actual del skill, `OpenAlex`, `DOAJ` y `Semantic Scholar` son fuentes abiertas activas, `Redalyc` es la fuente regional programática activa cuando hay API key, y `SciELO` permanece como fuente regional semiasistida o experimental.

Implicación pedagógica:

- si el objetivo principal del trabajo es comparar cobertura regional como fenómeno metodológico, `SciELO` y `Redalyc` siguen siendo relevantes aunque su automatización sea parcial;
- si el objetivo principal es ejecutar una corrida reproducible y automatizable con baja fricción, hoy conviene apoyarse primero en `OpenAlex`, `DOAJ`, `Semantic Scholar` y `Redalyc` cuando haya API key.

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
- Semantic Scholar API product page: https://www.semanticscholar.org/product/api
- Semantic Scholar Graph API docs: https://api.semanticscholar.org/api-docs/graph
- Scopus product page: https://www.elsevier.com/products/scopus
- Scopus content page: https://www.elsevier.com/en-gb/products/scopus/content
- Dimensions free version: https://www.dimensions.ai/products/all-products/dimensions-free-version/
- Dimensions analytics: https://www.dimensions.ai/products/all-products/dimensions-analytics/
- Dimensions homepage: https://www.dimensions.ai/
