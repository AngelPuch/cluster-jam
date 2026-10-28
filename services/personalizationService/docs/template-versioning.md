# Plantillas versionadas en borrador

Rama: feat/personalization/template-versioning, desde main tras PR #37.

## Alcance y dependencia pendiente

El usuario confirmó que Catalog Service y su contrato aún no existen.
Este incremento permite al administrador definir plantillas, zonas y
tamaños como borradores estructuralmente válidos y versionados (RF30).
Todos se guardan con activa=false. No existe operación de publicación,
no se aceptan active/actorId en el cuerpo y los clientes no leen borradores.

producto_ref (UUID) y talla_ref (smallint) son referencias externas, no FK
entre bases. Guardarlas en un borrador no confirma existencia, publicación
ni compatibilidad de producto/talla. Antes de activar plantillas o permitir
diseños reales hay que integrar un contrato de Catalog para comprobar
producto, talla y variante; validar la activación y establecer una sola
versión vigente por serie. No se simula esa comprobación ni se consulta
directamente la base de Catalog. Esta dependencia queda registrada para
el cierre del backend y no se presenta como funcionalidad terminada.

No se generaron clientes WPF ni Android. La composición de imágenes,
proporciones, advertencia de resolución y costo total del diseño quedan
para sus incrementos. Aquí se valida la geometría mínima necesaria para
no guardar plantillas inválidas.

## Modelo y versionado

Se reutilizan plantilla_version, zona, tamano_zona y auditoria_local de
la migración existente 0001_personalization. No hay tablas nuevas ni DDL
al arrancar: no se necesita migración adicional en este incremento.
No crear tablas o registros a mano para probarlo.

Cada serie corresponde a (productId, sizeId). POST recibe expectedVersion:
0 para la primera y el último número confirmado para crear la siguiente.
Un advisory lock transaccional de PostgreSQL serializa la serie, incluida
su primera creación sin filas previas. Un hash de 64 bits identifica el
reclamo; una colisión solo serializa dos series sin mezclar sus datos.
La consulta está acotada por el timeout SQL del servicio. Un escritor
vence y el otro recibe 409 si ambos partían de la misma versión.

Se crea una copia completa de la geometría, con nuevo UUID de plantilla,
de cada zona y de cada tamaño. No hay PATCH/DELETE sobre versiones.
Cambiar medidas, zonas o recargos exige otra versión. Las referencias
de diseños previos permanecen apuntando a los IDs originales. La versión,
zonas, tamaños y auditoría se confirman en una sola transacción; un fallo
de auditoría revierte incluso las filas geométricas ya enviadas a SQL.

SQL conserva identificadores españoles. El contrato usa FRONT/BACK,
almacenados como FRENTE/ESPALDA, y SMALL/MEDIUM/LARGE, almacenados como
CHICO/MEDIANO/GRANDE. Estos labels de tamaño de impresión no son la talla
de la prenda: sizeId identifica una referencia de talla en Catalog.

## Contratos administrativos

| Método | Ruta | Resultado |
| --- | --- | --- |
| POST | /api/v1/admin/template-versions | 201, versión completa y Location |
| GET | /api/v1/admin/template-versions/{templateId} | 200, versión con zonas/tamaños |
| GET | /api/v1/admin/template-versions?productId=...&sizeId=... | 200, resúmenes paginados de la serie |

Las tres rutas exigen JWT local válido con app_role=administrador. No
consultan Auth por petición. Cliente recibe 403; sin JWT se responde 401.
Las respuestas JSON usan camelCase y Cache-Control: no-store.

POST contiene productId, sizeId, expectedVersion, front, back y zones.
front/back tienen widthMm y heightMm. Cada zona tiene code, side, xMm,
yMm, widthMm, heightMm y sizes. Cada tamaño tiene label, widthMm,
heightMm y surchargeCents. IDs y active los decide el servidor.

Las medidas JSON son cadenas decimales, por ejemplo "100.125", nunca
números float. Se usa Decimal en negocio y numeric en PostgreSQL. Máximo
10000 mm, hasta tres decimales, sin notación científica, NaN, Infinity,
comas, signo ni espacios. Las dimensiones son positivas; x/y permiten 0.
La respuesta normaliza mm a tres decimales. Cada tamaño incluye widthCm
y heightCm con cuatro decimales, por ejemplo 100.125 mm = 10.0125 cm.
Esto prepara las medidas de RF11 sin habilitar aún selección de cliente.

Límites técnicos iniciales (decisiones locales, no medidas del documento):
1–20 zonas por versión, 1–3 tamaños por zona, sizeId entero de 1 a 32767,
código ASCII minúsculo [a-z][a-z0-9-]{0,39}. Los recargos son enteros de
0 a 9007199254740991 centavos y moneda MXN. No se suman todavía con
estampados o prendas. Las opciones de tamaño pueden ser un subconjunto
de SMALL/MEDIUM/LARGE, sin etiquetas repetidas en una misma zona.

Cada zona debe caber en su cara. Dos zonas de la misma cara no pueden
superponerse; tocar bordes está permitido. Zonas en caras distintas pueden
tener las mismas coordenadas. (side, code) es único en la versión. Cada
tamaño debe caber en su zona. Estas validaciones ocurren antes de abrir la
transacción, y los constraints SQL existentes protegen sus invariantes.

El detalle lee plantilla/zonas/tamaños en una consulta con joins. La salida
ordena FRONT antes de BACK y luego por código; los tamaños se presentan
SMALL, MEDIUM, LARGE. La lista de la serie devuelve solo resúmenes, en
orden de número ascendente, limit=20, máximo 100, cursor opaco ligado al
producto y talla. Cursors de otra serie o endpoint se rechazan.

Errores RFC 9457: 409 TEMPLATE_VERSION_CONFLICT; 422 VALIDATION_ERROR
por estructura/formato, DUPLICATE_ZONE, DUPLICATE_ZONE_SIZE,
ZONE_OUTSIDE_TEMPLATE, ZONES_OVERLAP o SIZE_OUTSIDE_ZONE por geometría;
404 TEMPLATE_NOT_FOUND; 400 INVALID_CURSOR; 503
TEMPLATE_DATABASE_UNAVAILABLE sin detalles SQL. No se devuelven 200
para entradas inválidas. PATCH/DELETE responden 405 y no alteran historial.

## Auditoría y pruebas

TEMPLATE_VERSION_CREATED se guarda con actor del JWT verificado, recurso
plantilla_version e ID de la versión. El detalle guarda solo productId,
sizeId, versionNumber, zoneCount, sizeCount, active=false y
catalogValidation=PENDING. Esta última marca es evidencia técnica de
que el borrador no ha sido validado con Catalog; no es un nuevo campo SQL
de publicación. No se registran cuerpos, JWT ni credenciales en logs.

Las pruebas verifican geometría, decimales exactos, cm, roles, DTOs
estrictos, inmutabilidad, CAS inicial y sucesor, rollback de auditoría,
mapeos españoles y referencias históricas. La fixture con un diseño
CONGELADO comprueba conservación de su FK; no representa una creación de
diseño autorizada en producción con un borrador.

Usar verify_stack.py para PostgreSQL: crea un proyecto/volumen temporal,
rechaza una base poblada y limpia solo sus recursos. Nunca ejecutar
integración contra el volumen de desarrollo. RNF09 exige cobertura de
funcionalidad; la cobertura de líneas/ramas se reporta por separado.

## Postman: 25 solicitudes en orden

Importar template-versions.postman_collection.json. Conservar el entorno
actual con baseUrl=http://127.0.0.1:8082, adminAccessToken vigente del
administrador y accessToken vigente del cliente. Auth está en 8080.
No necesitas printId, imágenes, buckets nuevos, productId real ni Catalog.

01 genera un UUID de producto ficticio exclusivo para QA, con referencia
de talla 1 que no implica una talla real. Guarda templateProductId,
templateFirstId y el snapshot. 04 guarda templateSecondId y 07 el cursor.
Las demás variables y cuerpos están preparados. Las dos versiones quedan
inactivas y se conservan como datos de prueba. Repetir toda la colección
desde 01 crea otra serie de QA independiente.

| Paso | Caso | HTTP |
| --- | --- | --- |
| 01 | Crear v1, dos caras y tres tamaños | 201 |
| 02 | Consultar medidas exactas y centímetros | 200 |
| 03 | ExpectedVersion anterior | 409 |
| 04 | Crear v2 con nuevos IDs, geometría y recargo | 201 |
| 05 | v1 conserva todos sus datos | 200 |
| 06 | v2 tiene los nuevos datos | 200 |
| 07 | Primera página, limit=1 | 200 |
| 08 | Segunda página | 200 |
| 09 | Otra talla tiene otra serie | 200 |
| 10 | Cursor de otra talla | 400 |
| 11 | Cursor inválido | 400 |
| 12 | Intentar active=true | 422 |
| 13 | Medida enviada como número en vez de cadena | 422 |
| 14 | Zona fuera de la cara | 422 |
| 15 | Superposición en la misma cara | 422 |
| 16 | Etiqueta de tamaño duplicada | 422 |
| 17 | Tamaño fuera de la zona | 422 |
| 18 | Recargo negativo | 422 |
| 19 | Sin JWT | 401 |
| 20 | Cliente consulta borrador | 403 |
| 21 | Cliente crea versión | 403 |
| 22 | ID inexistente | 404 |
| 23 | PATCH de una versión | 405 |
| 24 | DELETE de historial | 405 |
| 25 | Borrador no expuesto en API de cliente | 404 |

No publicar estas referencias ficticias cuando se integre Catalog: crear
versiones vinculadas a productos/tallas reales y validar compatibilidad.
Si aparece 422 en una creación válida, revisar que las medidas sigan siendo
cadenas y los nombres camelCase. Los requests inválidos ya están preparados;
no hay que corregirlos, porque prueban rechazos esperados.

## GitHub Flow

Creación de rama (ya realizada):

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/template-versioning
```

Después de validar Postman y revisar cambios:

```powershell
git add services/personalizationService contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): version draft templates"
git push -u origin feat/personalization/template-versioning
```

Crear PR hacia main con el mismo título. Revisar límites, mapeos SQL,
inmutabilidad, ausencia de activación sin Catalog, auditoría atómica,
concurrencia, contratos y CI en verde. Usar Squash and merge:

```powershell
git switch main
git pull --ff-only origin main
git status
```

## Matriz de requisitos

| Requisito | Cobertura de este incremento |
| --- | --- |
| RF30 | Administración versionada de borradores, zonas y recargos |
| RF11 | Medidas exactas mm/cm; selección de cliente pendiente |
| RF13/RF15 | Geometría estructural; compatibilidad real con Catalog pendiente |
| RNF03 | JWT/rol y actor auditado; sin acceso cliente a borradores |
| RNF06 | Dos escritores, un sucesor; rollback completo |
| RNF07/RNF09 | OpenAPI y pruebas unitarias, HTTP, PG y Postman |
| RNF10/RNF11 | Migración vigente explícita, Docker y revisión GitHub Flow |

## Resultados

Validación automatizada del 2026-10-28:

- 490 pruebas generales aprobadas en Windows y Linux; 81.14 % de
  cobertura de líneas/ramas con mínimo configurado de 70 %.
- 84 pruebas aprobadas contra PostgreSQL real, incluidas nueve nuevas de
  versiones, concurrencia inicial/sucesora, rollback, historial y HTTP/JWT.
- Ruff, formato (193 archivos), mypy estricto (180 archivos), tipos de
  infraestructura, OpenAPI y construcción del paquete aprobados.
- Docker verificó usuario sin privilegios, red privada, migración explícita,
  reversión/reaplicación, recuperación de readiness y volumen persistente.
  El proyecto temporal y su volumen fueron retirados al terminar.
- Se comprobaron los 25 scripts de Postman, cuerpos JSON y variables;
  además se validó el ejemplo de dos caras/tres tamaños y su representación
  estable al invertir el orden de registros de entrada. La plantilla
  versionada de entorno conserva JWT y enlaces firmados vacíos.

El usuario confirmó el 2026-10-28 que las 25 solicitudes de la colección
Postman devolvieron los códigos HTTP esperados. Incluyen creación y consulta
de dos versiones, conflicto de versión, paginación, rechazos de geometría,
medidas y recargos inválidos, permisos, inexistencia e inmutabilidad.
La confirmación manual de códigos se registra separadamente de las pruebas
automatizadas de cuerpos, medidas, auditoría y concurrencia anteriores.

La activación y validación con Catalog siguen pendientes de su contrato,
conforme a lo confirmado por el usuario. No se ha simulado esa validación.
Las versiones de QA se conservan inactivas y no deben publicarse como
referencias reales de producto/talla cuando se integre Catalog.

Tras la validación se detuvieron Auth, Personalization y PostgreSQL;
el worker permanece detenido. Se verificó que no quedaran contenedores del
proyecto en ejecución ni escuchas en 8080 y 8082. El volumen de PostgreSQL
y los archivos de Storage se conservaron. No se ha realizado commit,
push ni PR de este incremento.
