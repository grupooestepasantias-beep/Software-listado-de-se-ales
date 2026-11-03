# Informe de auditoría y cierre - Generador de protocolos FAT/SAT

Fecha: 02/11/2026. Alcance: aplicación completa (generador, plantillas, lectura de PDF, interfaz, archivos).

## 1. Documentación de referencia usada
- **Estándar documental: Nueva California** (`la paz\SAT\Protocolo de ensayo SAT - Nueva California.docx/.pdf`), que trae
  los Anexos 1 y 2 dentro del SAT. No existe un FAT de Nueva California en la red: por indicación del usuario, los
  FAT (y sus anexos) se tomaron de los anexos del SAT, con el formato de los FAT de La Paz (`la paz\FAT`).
- **Documentos generados por la versión de prueba: Neuquén** (`la paz\Primeros words generados`).
- También se leyeron SAT de La Paz, Santa Rosa y San Martín Este, y los planos EF/TP de La Paz rC.
- Decisiones del usuario aplicadas: SAT con apartados 3.1 a 3.3; en los FAT se deja "en sitio" tal como está.

## 2. Problemas encontrados (Neuquén y versión anterior) y qué se hizo

### Críticos
| # | Problema | Corrección |
|---|---|---|
| 1 | **FAT: el índice listaba "Contenido" como capítulo 1**: toda la numeración corría (capítulo 4 "Pruebas por realizar" con apartados 3.1 a 3.5) y los anexos quedaban numerados 2, 3, 4… | "Contenido" fuera de la numeración y del índice. Ahora OBJETO es el capítulo 1 y los apartados 3.x cuelgan del capítulo 3. |
| 2 | **Índices con números de página fijos** (SAT escrito a mano, FAT con entradas viejas). Con otra cantidad de componentes o señales, el índice mentía. El propio SAT de Nueva California tiene un índice que lista 3.2 Propiedades dieléctricas y 3.3 Punto a punto que su cuerpo no tiene. | Índice real (campo TOC de Word) con hipervínculos, actualizado al generar. El validador compara el índice con los títulos y con las páginas reales del PDF. |
| 3 | **FAT y anexos: total de páginas escrito a mano** ("Página 13 de 10"). | Campo NUMPAGES en los pies de las 4 plantillas. |
| 4 | **Documentos regenerados pisaban a los anteriores** (sin versiones ni registro). | Archivo anterior a `versiones\` con fecha y hora, guardado atómico, restauración y registro de operaciones con huella SHA-256. |
| 5 | **Documentos con datos obligatorios vacíos** (tabla de documentos de referencia vacía en el FAT y en ambos anexos de Neuquén). | La generación se bloquea con un mensaje claro; no se crean archivos con tablas vacías. |
| 6 | **El .exe no leía PDF**: `pymupdf.layout` fallaba al cargar y el botón parecía no hacer nada (error silencioso). | Módulo excluido; los errores de la ventana ahora se muestran en un cartel. Probado dentro de un .exe. |

### Importantes
| # | Problema | Corrección |
|---|---|---|
| 7 | Relleno con 26 y 11 párrafos vacíos para "empujar" apartados a la hoja siguiente (deja hojas en blanco si crece una tabla). | Salto de página real antes de 3.2/Anexo 1/Registro de componentes. |
| 8 | Tablas largas partidas a mitad de fila y sin encabezado repetido (componentes, verificaciones). | Filas que no se parten; encabezado repetido. Firma siempre completa. |
| 9 | "Observaciones" no empezaba en hoja nueva en los anexos (y el último folio quedaba en blanco). Firma en una columna en el SAT. | Observaciones en hoja nueva en los 4 documentos; firma "Por Grupo Oeste \| Por <cliente>" más abajo en la hoja. |
| 10 | El SAT omitía el párrafo de lectura de protecciones que sí tienen Nueva California, La Paz y el FAT. | Restaurado (opción "Incluir lectura de protecciones", activada por defecto). |
| 11 | Índice con tipografía distinta a la de Nueva California; entradas "Descripción" y títulos de energización dentro del índice. | Estilos de índice Arial; solo entran los apartados. |
| 12 | Sin forma de elegir qué generar, ni proyectos, ni control de calidad. | Ver sección 3. |

### Redacción (sin cambiar procedimientos)
`bandejas rebatibles. Etc.)` → `bandejas rebatibles, etc.)`; `correspondiente(48VCC/110VCC)` → `correspondiente (48VCC/110VCC)`;
`VETILACIÓN` → `VENTILACIÓN`; punto final en el párrafo de protecciones. Se comparó toda la prosa fija del SAT con la
de Nueva California: coincide salvo los datos del proyecto y una diferencia pendiente (sección 6).

## 3. Funcionalidades terminadas
- Generación de SAT, FAT, Anexo 1 y Anexo 2, solos o en paquete, con PDF opcional.
- Lectura de térmicas, señales y comandos desde los PDF subidos para cada anexo.
- Control de calidad (docs. y entre docs.): 12 familias de controles pedidas, con archivo, apartado, descripción, gravedad,
  tipo y solución; bloqueantes separados de advertencias; aviso de que no valida criterios técnicos.
- Coherencia entre SAT, FAT y anexos: obra, tablero, cliente, fecha, revisión, planos, componentes, referencias a anexos.
- Interfaz: proyectos (nuevo/abrir/guardar), selección de documentos, progreso, control de calidad, versiones, registro.
- Seguridad e integridad: validación de entradas y de PDF, nombres de archivo seguros, guardado atómico, sin pisar, registro.

## 4. Archivos
Modificados: `app.py`, `generador_sat.py`, `crear_plantilla.py`, `docx_util.py`, `README.md`, las 4 `plantilla_*.docx`.
Nuevos: `validador.py`, `gestion.py`, `word_tools.py`, `ejecutar_pruebas.py`, `tests\` (5 archivos), `INFORME.md`.
Sin cambios: `extraer_pdf.py`. No se modificó ningún documento original de la red.

## 5. Pruebas
`python ejecutar_pruebas.py` - **113 pruebas, 0 fallas, 0 errores, 1 omitida** (la omitida es la variante "sin Word", que
solo corre en una PC sin Word; su equivalente con Word simulado como ausente sí pasa).

| Grupo | Qué cubre |
|---|---|
| Generación | Paquete de 4 documentos; sin marcadores sin reemplazar ni datos de otros proyectos; portada y encabezados; estructura SAT 3.1-3.3 / FAT 3.1-3.5.1; numeración; Observaciones en hoja nueva; firma en dos columnas; opción de protecciones |
| Índice y páginas | Índice actualizado; hipervínculos con marcador válido; números de página del índice = páginas reales del PDF; total de páginas del pie; sin hojas en blanco; NUMPAGES en las 4 plantillas |
| Tablas | Contenido y orden de referencias, componentes, térmicas, señales y comandos; filas sin partir; encabezado repetido |
| Casos límite | Caracteres XML y unicode, 1 señal, 1.500 señales, 1 documento, nombre con caracteres prohibidos, anexo con un solo grupo |
| Validador (detección) | Cada control se prueba **rompiendo a propósito** un documento bueno: marcadores, portada, fecha, tipo, apartado faltante, estructura FAT en SAT, títulos duplicados, saltos de numeración, índice con entrada inexistente, tablas vacías o sin descripción, DI/DO con el mismo modelo, firma, señales sin descripción/borne/duplicadas, anexo inexistente o equivocado, ortografía, encabezado de otro proyecto, objeto sin tablero, nombre en minúsculas, y 5 de coherencia entre documentos |
| Gestión | Versiones, restauración, fallo de guardado a mitad (el original queda intacto), registro (incluido registro dañado), proyectos (versión nueva, JSON corrupto), validación de entradas y PDF, datos incompletos, sin Word, ventana |
| Referencias (red) | Contra el FAT de La Paz: los 213 bornes/28 comandos/8 térmicas leídos coinciden con el FAT hecho a mano (las únicas diferencias están enumeradas y verificadas contra el plano rC); contra Nueva California: misma prosa fija, mismos apartados, mismo orden de tablas |

Pruebas manuales/visuales: se exportaron a PDF con Word los 4 documentos y se revisaron las hojas (índice, saltos, tablas,
firma); comparación lado a lado con Nueva California; generación completa dentro de un .exe congelado (lectura de PDF,
generación, actualización con Word, PDF, control = APTO); la ventana del .exe abre.
Los datos de prueba son ficticios (`tests\datos_prueba.py`); los PDF reales de La Paz se usan solo como entrada de lectura.

## 6. Pendientes que requieren una decisión de ingeniería (no se resolvieron por no inventar contenido)
1. **"en fábrica" vs "en sitio"**: el SAT de Nueva California dice "protocolo de ensayos en fábrica"; el generado dice "en sitio";
   los FAT de La Paz dicen "en sitio". Se dejaron como estaban. Hay que definir el texto correcto para SAT y para FAT.
2. **Módulos DI/DO**: el FAT de La Paz lista "MÓDULO DI SEL 2244-3" (los demás documentos usan 2244-2 para DI). El control
   advierte si un mismo modelo figura como DI y como DO; qué modelo es correcto lo decide el responsable técnico.
3. **Nombres de las señales**: el FAT de La Paz usa nombres como "TR01 Int en Local" y los planos dicen "Interruptor 35201 en Local".
   El generador usa los del plano. Si debe usarse otra nomenclatura, hay que definir la regla.
4. **Térmicas Q224 (ventilación y calefacción) y Q4 (UPS)** estaban en el FAT viejo y no figuran en el plano rC: no se cargan.
5. **"Falla Alimentación General"** no tiene borne de bornera en el plano: queda como "(ver H3/C01)" y se advierte; hay que
   poner el elemento (en el FAT viejo era -Q1).
6. **Variantes de Nueva California no reproducidas** (no están en los FAT de La Paz): columnas INSERTADO/EXTRAIDO y el texto
   "Para comandos, se verificará…" del Anexo 2 (celdas extraíbles). Si un proyecto las necesita, hace falta una plantilla variante.
7. Los recuadros "Verificación anexo 1/2" del SAT vienen de Santa Rosa; Nueva California no los tiene.

## 7. Riesgos y limitaciones
- **Word es necesario** para índice, números de página y PDF; sin Word el control marca NO APTO (por diseño).
- La **lectura de PDF** solo se probó con los planos de La Paz rC; otro diseño de plano puede leerse mal. Avisa cuando las
  cantidades no cierran, pero **no valida el contenido técnico**: las listas leídas deben revisarse siempre.
- La tabla de **comandos** del Anexo 2 está anidada y Word no repite su encabezado al cambiar de hoja.
- Sin control de acceso ni sesiones (aplicación de escritorio): el registro guarda el usuario de Windows. `config.json` junto al
  .exe se comparte si el .exe se usa desde la carpeta de red. Dos personas generando en la misma carpeta a la vez no se bloquean entre sí
  (el guardado atómico evita archivos corruptos, pero la última gana y la otra queda en `versiones`).
- El .exe (67 MB) no está firmado: puede aparecer el aviso de SmartScreen; desde la red tarda en abrir la primera vez.
- Las pruebas contra referencias se omiten sin acceso a la red.
- La ventana del .exe se probó abriéndola; los clics se probaron sobre el mismo código ejecutado con Python.

## 8. Evaluación de preparación para producción
**Apto para uso real con revisión humana del contenido técnico.** El generador produce documentos con estructura, numeración,
índice, tablas y formato coherentes con el estándar y detecta defectos documentales y de coherencia; no pierde versiones
anteriores y deja registro. **No sustituye** la revisión de un responsable técnico: señales, bornes, térmicas, modelos y los puntos
de la sección 6 siguen siendo decisión de ingeniería. Recomendado: cerrar los puntos 1 a 3 de la sección 6 antes de emitir
documentos a clientes, y probar con otro tablero real (distinto plano) para ampliar la cobertura de la lectura de PDF.
