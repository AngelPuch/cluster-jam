# Catálogo de estampados para clientes

Rama: feat/personalization/print-catalog, desde main tras el PR #36.

## Alcance y decisiones

RF08: consultar imágenes de estampados precargadas por el administrador,
con miniatura y recargo. Catalog & Inventory sigue siendo responsable de
prendas base, fotos, tallas, colores, SKU, precio base e inventario.
Esta rama no añade interfaces WPF/Android ni prendas prediseñadas.

Un estampado es visible si está activo y su versión de mayor número tiene
un original DISPONIBLE del bucket del servicio y su miniatura v1 DISPONIBLE,
con propietario coincidente, PNG válido en metadata y máximo 320 × 320.
La consulta calcula la última versión antes de comprobar disponibilidad.
No vuelve a una versión anterior si la nueva imagen aún espera al worker:
así no mezcla una imagen anterior con el recargo vigente. El worker vuelve
visible el recurso automáticamente al completar la miniatura; no hay un
nuevo estado SQL de publicación ni migraciones adicionales.

Estas son decisiones de publicación de este incremento. RF08 exige mostrar
miniatura y recargo, pero no define un contrato para miniaturas pendientes.
Se eligió omitir temporalmente los recursos que aún no pueden mostrarla.

## Contratos REST

JWT local de rol cliente o administrador en las tres operaciones:

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | /api/v1/prints | 200, items y nextCursor |
| GET | /api/v1/prints/{printId} | 200, detalle visible |
| POST | /api/v1/prints/{printId}/versions/{versionId}/thumbnail/download-urls | 201, fileId, expiresAt y downloadUrl |

La representación del estampado tiene id, name, description, version y
thumbnail. version contiene id, number, surchargeCents y currency=MXN.
thumbnail contiene id, mimeType=image/png, widthPx, heightPx, sizeBytes y
downloadUrlEndpoint relativo. No contiene propietario, archivo original,
bucket, clave de objeto ni URL firmada. Los importes son enteros seguros
en JSON; no se usa float ni se calcula aún el total del diseño o prenda.

El listado usa limit=20, rango 1–100, orden UUID ascendente y cursor opaco
propio de print-catalog. Lee limit+1 para determinar si hay otra página.
El cursor de administración no es válido aquí. Una página posterior a la
última devuelve items=[] y nextCursor=null. No se usa OFFSET ni count.
Cada página es una lectura actual: publicaciones, retiros o nuevas
versiones entre páginas pueden cambiar el conjunto; no se promete una
instantánea global para toda la navegación.

La lista y el detalle ejecutan una sola consulta SQL con sus joins,
filtrando disponibilidad antes del límite. Evitan N+1 y no consultan
Storage, Auth, Profile, Catalog ni ningún otro servicio durante la lectura.
La verificación de JWT conserva JWKS en caché y no consulta al usuario
en Auth. Solo el POST de descarga verifica el bucket y firma un enlace.
Se reutilizan los índices de ID/versiones del modelo actual. La meta p95
de RNF05 queda pendiente del ensayo de carga del cierre del backend; contar
consultas no sustituye medir 30 usuarios durante 5 minutos.

Todas las respuestas de la API llevan Cache-Control: no-store. Los
errores son RFC 9457: 401 sin JWT/vencido; 403 rol no válido; 400 cursor
inválido; 422 limit/UUID inválido; 404 inexistente, retirado, no preparado
o versión de descarga que ya no es la vigente; 503 dependencia no disponible.
La descripción o SQL internos no se exponen. Las rutas administrativas
siguen exigiendo administrador y permiten inspeccionar versiones históricas.

## Permisos de archivos y concurrencia

El enlace cliente se genera solo para la miniatura calculada por el servidor,
nunca a partir de un fileId o URL proporcionados por el usuario. Revalida
que el estampado esté visible y que versionId sea su versión vigente.
Retirarlo impide nuevas consultas y nuevas firmas. Los enlaces firmados
emitidos antes del retiro conservan su vigencia hasta caducar: por defecto
60 segundos (configurable de 1 a 300). Un retiro no revoca una URL ya emitida.
La comprobación de visibilidad se realiza al autorizar la operación; una
transición posterior a esa lectura puede coincidir con la firma en curso.

Conocer el ID de un estampado no concede permiso para descargar su original.
Las rutas /files conservan propiedad o administrador, y las rutas /admin
conservan guards de administrador. Las miniaturas no se vuelven públicas.
Una nueva versión de precio puede reutilizar la miniatura si conserva la
imagen; nuevos enlaces del catálogo deben usar su nuevo versionId. Las
versiones y archivos anteriores se conservan para diseños e historial.

## QA automatizado y trazabilidad

| Requisito | Operación y prueba |
| --- | --- |
| RF08 | Listado/detalle con miniatura y MXN; HTTP y PostgreSQL |
| RF30 | Retiros, reactivación e historial; PostgreSQL y Postman |
| RNF01/RNF03 | Solo miniatura autorizada; original ajeno 403; JWT real |
| RNF05 | Paginación y una consulta SQL por lectura; carga final pendiente |
| RNF06 | Versión más reciente en una sentencia, sin fallback obsoleto |
| RNF07/RNF09 | OpenAPI, pruebas unitarias/HTTP/PG, colección manual |
| RNF10/RNF11 | Docker, Alembic vigente sin DDL automático, GitHub Flow |

La suite PostgreSQL usa un volumen temporal vacío. Comprueba miniatura
pendiente, nueva imagen, cambios de recargo, retiros, paginación antes del
límite, una consulta por listado/detalle, guardas de originales e integridad
de identidad/cantidades JSON. No ejecutar integración sobre la base local
con datos del usuario. La cobertura de líneas/ramas se registra aparte y
no sustituye la cobertura funcional de RNF09.

No hay cambios de esquema: se consultan estampado, estampado_version y
archivo. La revisión Alembic sigue siendo la previa y se aplica de manera
explícita; no se crean tablas a mano ni al arrancar. No se agregan librerías,
eventos AMQP ni llamadas a servicios aún inexistentes.

## Postman: ejecutar las 21 solicitudes en orden

Importar print-catalog.postman_collection.json sin reemplazar el entorno
local ya configurado. Requiere baseUrl=http://127.0.0.1:8082, accessToken
vigente del cliente, adminAccessToken vigente del administrador y printId
del estampado utilizado en la rama anterior. Auth sigue en el puerto 8080.
El login de cada cuenta es POST /api/v1/sessions; usar credenciales solo
en Postman y guardar accessToken en la variable correspondiente al rol.

La colección toma el fileId desde la consulta administrativa inicial;
no tienes que llenar printFileId ni subir otra imagen. Crea un estampado
QA nuevo que reutiliza esa imagen y miniatura. Lo retira al terminar y
conserva su auditoría e historial. No modifica el estampado de origen.
Las variables catalog* se guardan automáticamente y no deben editarse.
Los requests PATCH de QA ya incluyen If-Match y los cuerpos necesarios.

| Paso | Prueba | HTTP |
| --- | --- | --- |
| 01 | Consultar imagen de referencia como administrador | 200 |
| 02 | Crear estampado exclusivo QA | 201 |
| 03 | Catálogo como cliente | 200 |
| 04 | Detalle y recargo de 1250 centavos MXN | 200 |
| 05 | Crear enlace cliente de miniatura | 201 |
| 06 | Descargar PNG antes de 60 segundos | 200 |
| 07 | Detalle del catálogo como administrador | 200 |
| 08 | Página de un elemento | 200 |
| 09 | Cursor al final del catálogo | 200 |
| 10 | Cursor inválido | 400 |
| 11 | Límite 101 | 422 |
| 12 | Sin JWT | 401 |
| 13 | Estampado inexistente | 404 |
| 14 | Versión incorrecta para firmar enlace | 404 |
| 15 | Cliente intenta administrar | 403 |
| 16 | Retirar el estampado QA como administrador | 200 |
| 17 | Cliente ya no ve el retirado | 404 |
| 18 | Retirado no genera nuevo enlace | 404 |
| 19 | Reactivar como administrador | 200 |
| 20 | Cliente ve nuevamente versión y recargo conservados | 200 |
| 21 | Dejar QA retirado al terminar | 200 |

Si caduca el enlace antes de 06, repetir 05 y enseguida 06, mientras QA
siga activo. Para repetir toda la colección empezar en 01: crea otro
recurso QA independiente. No exportar valores locales de JWT/URL a Git.
Si 04 devuelve 404 revisar que la miniatura del original esté lista;
arrancar el worker según print-thumbnails.md. Las pruebas con PostgreSQL
ya verifican el caso de nueva imagen aún pendiente del worker.

## GitHub Flow

Crear desde main (ya realizado para esta rama):

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/print-catalog
```

Después de confirmar Postman y revisar cambios:

```powershell
git add services/personalizationService contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): expose the print catalog"
git push -u origin feat/personalization/print-catalog
```

PR hacia main con ese título. Revisar visibilidad activa/vigente, ausencia
de originales en DTOs, paginación, permisos, historial, contratos y CI en
verde. Fusionar con Squash and merge antes de avanzar a otra rama:

```powershell
git switch main
git pull --ff-only origin main
git status
```

## Resultados

Validación automatizada del 2026-10-28:

- 448 pruebas generales aprobadas en Windows y Linux, con 81.88 % de
  cobertura de líneas/ramas y mínimo configurado de 70 %.
- 75 pruebas aprobadas con PostgreSQL real, incluidas 14 nuevas del
  catálogo y un flujo HTTP completo con JWT firmado, precios e historial.
- Ruff, formato (177 archivos), mypy estricto (165 archivos), tipos de
  infraestructura, OpenAPI y construcción del paquete aprobados.
- Docker verificó usuario sin privilegios, red privada, base sin puerto
  público, migración explícita/reversión/reaplicación, recuperación de
  readiness y persistencia. Se eliminaron solo sus recursos temporales.
- La colección Postman contiene 21 solicitudes; scripts, cuerpos JSON,
  variables referenciadas y plantilla sin secretos fueron comprobados.
- En la base local, el estampado existente está retirado: la consulta del
  catálogo devolvió cero elementos y el detalle no lo mostró, conforme a
  la política. No se reactivó ni modificó. La verificación interna de
  operador descargó su miniatura real de 213 × 320 desde Storage con 200
  y hash coincidente. Esa comprobación no sustituye la prueba manual del
  POST cliente con un JWT real de la cuenta del usuario.

El usuario confirmó el 2026-10-28 que las 21 comprobaciones manuales
de Postman devolvieron las respuestas esperadas. Se validaron catálogo y
detalle con JWT de cliente/administrador, recargo y miniatura real,
paginación, entradas inválidas, ausencia de JWT, restricciones de
administración, retiro, reactivación y conservación de versión/recargo.
La colección dejó su estampado QA retirado y conservó el historial.
Esta evidencia manual se distingue de las pruebas automatizadas anteriores.

Tras confirmar las pruebas se detuvieron Auth, Personalization, PostgreSQL
y el worker. Se verificó que no quedaran contenedores del proyecto en
ejecución ni escuchas en 8080 y 8082. El volumen de PostgreSQL y los
archivos de Storage se conservaron. No se ha realizado commit, push
ni PR de este incremento.
