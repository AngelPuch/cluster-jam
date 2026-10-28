# Reglas de diseño y análisis administrativo

Rama: feat/personalization/design-rules, desde main tras PR #38.

## Alcance y decisiones confirmadas

Este incremento prepara el núcleo de cálculo de RF12–RF15 y el recargo
de personalización. Catalog Service y su contrato siguen ausentes; las
plantillas se conservan inactivas. No crea diseños, aplicaciones, carrito,
pedidos ni cotizaciones; no publica plantillas ni verifica compatibilidad
real de producto/talla/variante. Es un diagnóstico administrativo de solo
lectura. La futura API de diseños y checkout debe validar esas condiciones.

El usuario eligió que su equipo definirá el umbral DPI. Por ello no se
impone 150 ni 300 como valor por defecto. MIN_PRINT_DPI omitido o vacío
significa pendiente: minimumDpi=null y resolutionStatus=
THRESHOLD_NOT_CONFIGURED. Cuando el equipo lo decida, configurar un entero
de 1 a 2400 en infra/personalization/.env y recrear Personalization. Ese
rango es un límite técnico, no una recomendación de calidad. INSUFFICIENT
es un aviso y no provoca rechazo de la imagen. El umbral solo lo establece
el servidor; un cuerpo que intente cambiarlo recibe 422.

## Contrato y seguridad

POST /api/v1/admin/template-versions/{templateId}/design-analyses
devuelve 200 con el cálculo, sin Location ni recurso persistido. Requiere
JWT local de administrador; sin JWT 401 y cliente 403 antes de leer fuentes.
Cache-Control: no-store. No se consulta Auth por petición ni se acepta
usuario/rol en el cuerpo. No se añade una ruta cliente de borradores.

El cuerpo tiene applications (1–20). Cada entrada especifica zoneId,
zoneSizeId y exactamente uno de printVersionId o fileId. No admite precios,
dimensiones de píxeles, posición, lado, cantidad, moneda ni umbral DPI
aportados por el cliente. Los datos se resuelven en la base del servicio.

zoneId debe pertenecer a la plantilla y zoneSizeId a esa zona. Solo se
admite una aplicación por zona. Se revalida toda la geometría de plantilla
y se usan originales DISPONIBLE, uso ORIGINAL y bucket configurado.
No se aceptan IDs de miniaturas o previews como originales. El administrador
puede analizar originales de otros propietarios por su permiso explícito;
esto no modifica los permisos de /files para clientes.

Este diagnóstico puede inspeccionar versiones históricas de estampados,
incluso retirados, con su recargo inmutable. Eso no habilita elegirlos
para un diseño nuevo de cliente. La futura API debe comprobar elegibilidad
de catálogo y propiedad de archivos, y checkout debe volver a validar
vigencia y compatibilidad antes de congelar y cotizar.

## Geometría exacta y presentación aproximada

Con W/H píxeles orientados y un tamaño permitido w/h milímetros:

scale = min(w/W, h/H)
printedWidth = W × scale; printedHeight = H × scale
x = zoneX + (zoneWidth − printedWidth)/2
y = zoneY + (zoneHeight − printedHeight)/2
effectiveDpi = 25.4 / scale

Esto centra la imagen y conserva su proporción dentro del tamaño elegido,
que a su vez cabe en la zona. No hay recorte, deformación, rotación manual
ni posición libre. Las zonas de una misma cara ya deben ser disjuntas;
la selección impide más de una aplicación en cada una.

El núcleo usa Fraction sobre Decimal del modelo: no usa float. El factor
25.4 mm/pulgada es exacto (127/5). La comparación contra el umbral se hace
con la fracción exacta antes de redondear; igualdad al mínimo es SUFFICIENT.
No se usan los DPI declarados en EXIF como calidad: se calcula la resolución
efectiva según píxeles reales y tamaño físico solicitado.

La respuesta muestra placement en cadenas mm con seis decimales y
effectiveDpi con tres, redondeo half-even. Son valores de presentación
aproximados, marcados approximate=true. Las fracciones internas conservan
proporción y límites exactos; el redondeo decimal puede introducir una
diferencia microscópica al sumar valores mostrados. El futuro renderer y
checkout deben reutilizar el núcleo, no reconstruir geometría desde estos
decimales ni tratar el diagnóstico como instrucción de fabricación.

La respuesta también incluye diagnosticOnly=true,
catalogCompatibilityVerified=false, templateActive, minimumDpi,
applications y personalizationSurchargeCents. Cada aplicación indica lado,
IDs seleccionados, píxeles orientados, posición, effectiveDpi, estado de
resolución y desglose de recargos en centavos. Estos indicadores explicitan
que no hay validación comercial de Catalog ni cotización vigente.

## Precios y fuentes

Recargo por aplicación = recargo de tamano_zona + recargo de la versión
de estampado cuando corresponda. Una imagen propia no suma recargo de
estampado. El total suma todas las aplicaciones de una unidad, en MXN.
No incluye precio base de prenda, cantidad, descuentos, impuestos ni pagos;
esos cálculos completos pertenecen a Orders/Catalog según sus contratos.

Cada importe y suma debe estar entre 0 y 9007199254740991 centavos, seguro
para JSON y dentro de bigint. Un desbordamiento se rechaza con 422 antes
de leer imágenes. No se trunca, redondea ni convierte dinero a float.

Las fuentes propias y de catálogo se obtienen con un máximo de dos
consultas SQL por lote de IDs. Las versiones de precio son inmutables.
Las sesiones SQL se cierran antes del acceso a Storage. Una imagen usada
en dos caras solo se inspecciona una vez por petición; no se guarda una
caché persistente con datos privados.

## Inspección de imágenes

Storage mantiene los originales privados. Se verifican bucket, hash y
longitud al descargar el original, con los límites/timeouts del adaptador
existente. Se comparan MIME y dimensiones de cabecera con archivo. Pillow
lee orientación EXIF/XMP, incluyendo PNG con metadatos después de IDAT,
y cambia W/H para orientaciones 5–8. El archivo y los píxeles no se alteran.

Para PNG se recorre el contenido ya verificado y se construye en memoria
una vista de metadatos sin IDAT comprimidos, conservando chunks auxiliares
y un límite vacío para que Pillow abra la cabecera. Se llama al lector EXIF
base, evitando el override PNG que decodificaría píxeles. Esta vista nunca
se guarda ni se entrega; no es un PNG de salida. Las pruebas prohíben
Image.load durante la inspección y verifican orientación PNG/JPEG 1–8.
Metadatos de orientación inválidos se rechazan como inconsistencia.

No se generan previews ni miniaturas en HTTP. Las transformaciones pesadas
siguen reservadas al worker. La lectura de originales implica latencia de
Storage; este diagnóstico no demuestra la meta RNF05 de lecturas sin
proveedores. Un fallo de Storage devuelve error saneado, sin URLs ni claves.

## Persistencia y pruebas

No se modifica el esquema ni se necesita migración adicional. Se reutilizan
plantilla_version, zona, tamano_zona, estampado_version y archivo para leer.
El análisis no inserta diseno, aplicacion, auditoria_local ni trabajos.
La creación previa de una plantilla QA sí conserva su auditoría habitual.
El log HTTP registra solo metadatos permitidos y correlación, no cuerpos,
imágenes, JWT, claves de Storage ni enlaces firmados.

Las pruebas cubren proporción/centrado, fronteras DPI exactas, umbral
ausente, avisos no bloqueantes, recargos, sobreflujo, IDs cruzados, fuentes
exclusivas, permisos, orientación antes/después de IDAT, lectura única y
ausencia de escrituras. PostgreSQL prueba también precios históricos,
fuentes no disponibles, lotes acotados y HTTP con JWT firmado real.
Usar verify_stack.py con volumen temporal; nunca integración contra la base
poblada de desarrollo. La cobertura funcional de RNF09 se registra aparte
de cobertura de líneas/ramas.

Errores RFC 9457: 422 por zona/tamaño ajenos, zona duplicada, cuerpo o dinero
inválido; 404 por plantilla/origen inexistentes; 409 por original no listo
o metadatos inconsistentes; 503 por base/Storage no disponibles. El cliente
no elige proveedor, bucket, URL remota ni costos. No hay escrituras parciales
porque la operación de análisis no escribe estado.

## Postman: 21 solicitudes en orden

Importar design-rules.postman_collection.json y conservar el entorno actual:
baseUrl=http://127.0.0.1:8082, adminAccessToken vigente del administrador,
accessToken vigente del cliente y printId del estampado anterior. El login
de Auth sigue en 8080. El estampado puede estar retirado: el diagnóstico
administrativo permite revisar su versión, sin volver a publicarlo.

01 guarda automáticamente la versión, imagen y recargo de referencia.
02 crea una plantilla QA nueva e inactiva con dos caras y un tamaño por
zona, y guarda todos los IDs. Los demás requests ya contienen los cuerpos.
No subir archivos nuevos ni rellenar dimensiones/precios manualmente.
MIN_PRINT_DPI debe seguir omitido/vacío mientras el equipo decide.

| Paso | Caso | HTTP |
| --- | --- | --- |
| 01 | Consultar versión de estampado como administrador | 200 |
| 02 | Crear plantilla de análisis inactiva | 201 |
| 03 | Frente de catálogo + espalda con archivo propio | 200 |
| 04 | Repetir conserva cálculo | 200 |
| 05 | Imagen propia suma solo recargo del tamaño | 200 |
| 06 | Catálogo suma su recargo versionado | 200 |
| 07 | Plantilla sin cambios | 200 |
| 08 | Original sigue disponible para administrador | 200 |
| 09 | Zona de otra plantilla | 422 |
| 10 | Tamaño de otra zona | 422 |
| 11 | Dos aplicaciones por zona | 422 |
| 12 | Dos fuentes a la vez | 422 |
| 13 | Sin fuente | 422 |
| 14 | Precio manipulado en cuerpo | 422 |
| 15 | Posición arbitraria | 422 |
| 16 | Umbral DPI en cuerpo | 422 |
| 17 | Versión de estampado inexistente | 404 |
| 18 | Plantilla inexistente | 404 |
| 19 | Sin JWT | 401 |
| 20 | Cliente intenta analizar borrador | 403 |
| 21 | Aplicaciones vacías | 422 |

Los requests 03–06 verifican minimumDpi=null y aviso pendiente; no fallan
por pocos DPI. No cambiarles el umbral para hacer pasar la prueba. Los
casos con umbral definido están automatizados y se ajustarán al valor real
cuando el equipo lo decida. Repetir desde 01 crea otra plantilla QA; los
análisis repetidos no generan diseños ni auditorías nuevas.

## GitHub Flow

Creación desde main (ya realizada):

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/design-rules
```

Después de validar Postman y revisar cambios:

```powershell
git add services/personalizationService infra/personalization contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): analyze design geometry and surcharges"
git push -u origin feat/personalization/design-rules
```

Crear PR hacia main con el mismo título. Revisar operaciones de solo lectura,
guard administrador, datos de servidor, Fraction/centavos enteros, orientación,
umbral pendiente, conservación de archivos, contratos y CI en verde. Usar
Squash and merge antes del siguiente incremento:

```powershell
git switch main
git pull --ff-only origin main
git status
```

## Matriz y dependencias pendientes

| Requisito | Alcance |
| --- | --- |
| RF12/RF13 | Selección de una fuente y zona/tamaño válidos; Catalog real pendiente |
| RF14 | Ajuste proporcional y resolución efectiva; umbral del equipo pendiente |
| RF15 | Aplicación única por zona y respeto a geometría de plantilla |
| RF17/BD §7 | Recargo de personalización por unidad; cotización completa pendiente |
| RNF01/RNF03 | Original privado verificado y análisis solo administrador |
| RNF07/RNF09 | Contrato OpenAPI, pruebas unitarias/HTTP/PG y colección |
| RNF10/RNF11 | Docker y GitHub Flow; sin DDL manual ni automático |

Siguen pendientes: contrato/validación de Catalog y activación de plantillas;
valor DPI decidido por el equipo; persistencia REST de diseños, previews,
congelación y coordinación de checkout. No se presenta el diagnóstico como
un diseño listo para comprar o fabricar.

## Resultados

Validación automatizada del 2026-10-28:

- 564 pruebas generales aprobadas en Windows y Linux; 81.84 % de cobertura
  de líneas/ramas, con mínimo configurado de 70 %.
- 92 pruebas aprobadas con PostgreSQL real, incluidas ocho nuevas de
  fuentes, precios históricos, lotes, sobreflujo y análisis HTTP/JWT.
- Ruff, formato (212 archivos), mypy estricto (198 archivos), tipos de
  infraestructura, OpenAPI y construcción del paquete aprobados.
- Docker verificó usuario sin privilegios, migración explícita,
  aislamiento, reversión/reaplicación, recuperación de readiness y
  persistencia; se retiraron sus recursos temporales.
- Se comprobaron los 21 scripts Postman, sus cuerpos JSON y variables;
  la plantilla de entorno conserva JWT y enlaces firmados vacíos.
- El diagnóstico interno de operador con el original real de Supabase
  calculó dos aplicaciones, 4550 centavos de personalización y 260.096 DPI
  efectivos en ambas. minimumDpi siguió null; la evaluación no se calificó
  como suficiente o insuficiente. Se leyó el original una sola vez y los
  conteos de diseno, aplicacion y auditoria_local permanecieron iguales.
  La plantilla, el estampado y el archivo se conservaron. Esta prueba
  interna no sustituye la validación manual HTTP con cuentas reales.

El usuario confirmó el 2026-10-28 que las 21 solicitudes de la colección
Postman devolvieron los códigos HTTP esperados. Incluyen análisis de dos
caras, repetición, recargos de catálogo/archivo propio, consulta de recursos,
selecciones inválidas, precios/posiciones/umbral en el cuerpo, inexistencia
y permisos. La confirmación manual de códigos se registra separadamente
de las pruebas automatizadas de cuerpos, cálculo y ausencia de escrituras.

Tras confirmar los resultados se detuvieron Auth, Personalization y
PostgreSQL; el worker permanece detenido. Se verificó que no quedaran
contenedores del proyecto ejecutándose ni escuchas en 8080 y 8082. El
volumen de PostgreSQL y los archivos de Storage se conservaron.

Siguen pendientes el valor DPI que definirá el equipo y el contrato de
Catalog para validación/activación. El análisis conserva su alcance de
diagnóstico administrativo; no crea diseños ni cotizaciones. No se ha
realizado commit, push ni PR de este incremento.
