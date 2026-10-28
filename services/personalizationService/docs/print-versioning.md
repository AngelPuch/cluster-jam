# Estampados y versiones administrativas

Rama: `feat/personalization/print-versioning`.
Alcance: creación y consulta administrativa de estampados y nuevas
versiones de imagen/recargo, como parte de RF30 y RNF03/RNF07/RNF09.
RF08 completo requiere las miniaturas y la consulta para clientes de un
incremento posterior. No se incorpora aún edición de nombre, retirada,
plantillas, zonas, tamaños, diseños ni procesamiento de previews.

## Contratos y permisos

Todas estas operaciones requieren JWT validado localmente por JWKS y el
rol protegido `administrador`. El caso de uso vuelve a exigir ese rol.
No se aceptan `actorId`, `userId`, `active`, número asignado por el cliente
ni nombres snake_case como alternativas del contrato JSON.

| Método y recurso bajo `/api/v1/admin/prints` | Éxito |
| --- | --- |
| POST `/` | 201, estampado y primera versión, Location del recurso |
| GET `/` | 200, items y nextCursor |
| GET `/{printId}` | 200, datos y latestVersion |
| POST `/{printId}/versions` | 201, versión nueva y Location individual |
| GET `/{printId}/versions` | 200, historial paginado |
| GET `/{printId}/versions/{versionId}` | 200, versión histórica exacta |

Las rutas de colección no llevan barra final. Las lecturas no requieren
archivo ni body. Los POST usan JSON, nunca multipart. Para subir un nuevo
original se utiliza el endpoint `/api/v1/files` del incremento anterior.

Crear estampado:

```json
{
  "name": "Logo de prueba",
  "description": "Estampado del catálogo",
  "fileId": "UUID_DEL_ORIGINAL_VALIDADO",
  "surchargeCents": 1250
}
```

Agregar versión, conservando intacta la anterior:

```json
{
  "expectedVersion": 1,
  "fileId": "UUID_DEL_ORIGINAL_VALIDADO",
  "surchargeCents": 2000
}
```

La versión permite cambiar imagen, recargo o ambos. Reutilizar el mismo
original con otro precio es válido. La creación comienza en número 1 y
estado activo. Los importes son enteros exactos de centavos en MXN, con
intervalo inclusivo 0–9007199254740991: el esquema usa bigint y la API
respeta el máximo entero seguro de JSON exigido por el estándar. No se
aceptan booleanos, flotantes ni cadenas para representar centavos.

El nombre se recorta y tiene 1–120 caracteres. La descripción opcional
admite como máximo 2000 caracteres; este límite de recursos es una
decisión del contrato, no una cifra prescrita por el modelo relacional.

## Integridad y transacciones

Se usan exclusivamente `app.estampado`, `app.estampado_version`,
`app.archivo` y `app.auditoria_local`, ya instaladas por Alembic en
`0001_personalization`. No se modifica esa migración ni el esquema y la
API sigue sin crear tablas al arrancar. No hay accesos a las bases de
Auth, Catalog o Profile ni llamadas a Auth por cada petición.

La referencia debe existir, pertenecer al bucket configurado, tener uso
`ORIGINAL` y estado `DISPONIBLE`. Un administrador autorizado puede
seleccionar un original existente; conocer un UUID no otorga acceso al
cliente. Esta operación no cambia su propietario ni lo vuelve público.
Las descargas siguen pasando por la política de archivos privados.

Crear el estampado, su versión 1 y `PRINT_CREATED` es una sola transacción.
Crear una versión y `PRINT_VERSION_CREATED` es otra transacción local.
La auditoría identifica al actor mediante `sub` ya verificado y solo
guarda IDs técnicos, número, recargo y moneda. No registra JWT, claves,
correos, nombre original ni URL de descarga. Si falla la auditoría, se
revierte también el cambio de negocio; no se responde 201 sin commit.

La escritura de versiones bloquea la fila del estampado con
`SELECT FOR UPDATE`, lee la última versión y compara `expectedVersion`.
Dos peticiones con la misma expectativa producen una nueva versión y un
409, conservando la restricción única `(estampado_id, numero)`.
Una repetición de una escritura ya confirmada también obtiene 409: el
cliente debe recargar antes de decidir otro cambio. No hay reintentos
automáticos ni actualización de versiones antiguas. Al alcanzar el máximo
integer del modelo, se devuelve un conflicto y no se desborda el contador.

Las lecturas paginan por cursor opaco con limit 20, máximo 100, y devuelven
`nextCursor=null` al terminar. Los estampados se ordenan por UUID; sus
versiones por número e ID. El cursor se limita a su colección y, para el
historial, al estampado concreto. Las páginas representan el estado actual,
sin prometer una fotografía transaccional entre peticiones independientes.
La lista de estampados obtiene la última versión en una consulta SQL.

## Errores

Todos usan application/problem+json y los siete campos RFC 9457, con
`traceId`, códigos estables y detalles seguros. No se filtra SQL.

| Estado | Casos |
| --- | --- |
| 400 | JSON mal formado; INVALID_CURSOR |
| 401 | JWT ausente, inválido o vencido |
| 403 | Cliente o rol insuficiente |
| 404 | PRINT_NOT_FOUND, PRINT_VERSION_NOT_FOUND, PRINT_FILE_NOT_FOUND |
| 409 | INVALID_PRINT_FILE, PRINT_VERSION_CONFLICT, PRINT_VERSION_LIMIT |
| 422 | Datos rechazados por DTO; INVALID_PRINT_DATA |
| 503 | Llaves JWKS o PostgreSQL no disponibles |

## Docker y prueba manual con Postman

Desde la raíz, iniciar la base y la API con la imagen ya construida:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml up -d --no-build --wait personalization
```

No se necesita una migración nueva. Para construir la imagen en otro
equipo, ejecutar antes `docker compose -f infra/personalization/compose.yaml build personalization`.

Auth Service local se inicia desde su propia carpeta con `npm run start`.
El JWT se obtiene mediante POST `http://127.0.0.1:8080/api/v1/sessions`,
Authorization No Auth y JSON email/password. Usar la cuenta que ya tenga
el rol administrador; no modificar roles para superar una prueba.

Importar la colección `prints.postman_collection.json`. El entorno
`local.postman_environment.json` incluye las variables nuevas. Si ya hay
un entorno importado con valores locales, agregar las variables a ese
entorno para conservar sus valores, siguiendo esta tabla:

| Variable | Valor local |
| --- | --- |
| baseUrl | http://127.0.0.1:8082 |
| adminAccessToken | accessToken de la sesión del administrador, sin Bearer |
| accessToken | accessToken de la sesión del cliente, para comprobar 403 |
| printFileId | id de un original validado y DISPONIBLE |
| printId | vacío; lo guarda Crear estampado |
| originalPrintVersionId | vacío; lo guarda Crear estampado |
| printVersionId | vacío; lo guarda Crear versión 2 |

El original del incremento anterior se puede elegir por su id conocido.
Para usar otra imagen, subirla antes con `/api/v1/files`; esa es la única
operación multipart. No hace falta volver a subirla en las peticiones de
esta colección. No guardar credenciales reales en los archivos del repo.

Ejecutar en orden:

1. **Crear estampado**: 201; latestVersion.number=1 y surchargeCents=1250.
2. **Listar estampados** y **Consultar estampado**: 200.
3. **Crear versión 2**: 201; number=2 y surchargeCents=2000. Para repetir
   toda la secuencia se crea primero un nuevo estampado.
4. **Consultar versión original**, **Consultar versión nueva** y
   **Listar versiones**: 200. La primera conserva 1250 y la segunda 2000.
5. **Versión desactualizada**: 409 PRINT_VERSION_CONFLICT; no crea versión 3.
6. **Sin JWT**: 401. **Cliente sin permiso**: 403 usando el token del cliente.
7. **Importe inválido**: 422 por un importe fraccionario.
8. **Cursor inválido**: 400 INVALID_CURSOR.

Todas las peticiones de esta colección tienen JSON o Body none, sin
adjuntos locales. El token administrativo se hereda de la colección salvo
las pruebas explícitas No Auth y cliente. Ante 401 por expiración, hacer
login otra vez y cambiar solo la variable del token correspondiente.

## Matriz requisito, operación y prueba

| Requisito | Operación o regla | Evidencia automatizada |
| --- | --- | --- |
| RF30 | Alta y versiones de imagen/recargo | test/prints y test/integration/test_print_versioning.py |
| RF30 | Historial y auditoría atómica | Prueba de fallo real de PK de auditoría y rollback |
| RNF01/RNF03 | Original disponible y rol administrador | Pruebas de estado, bucket, JWT y actor derivado de sub |
| RNF06 | Dos escritores con expectedVersion=1 | PostgreSQL real: un sucesor y un conflicto |
| RNF07 | JSON camelCase, centavos MXN y paginación | Contrato OpenAPI y test/security/test_print_http.py |
| RNF09 | Flujos HTTP completos y errores | TestClient con JWT real y PostgreSQL; casos unitarios |

La cobertura de líneas de pytest se informa aparte: no equivale por sí
sola al porcentaje de funcionalidad exigido por RNF09. Las pruebas de JWT
usan firmas reales con claves efímeras y sustituyen solo el transporte
JWKS. La prueba SQL usa el esquema oficial en un proyecto Docker temporal,
sin SQLite, usuarios de producción ni borrado de la base de desarrollo.
La ejecución manual de esta colección con la cuenta real debe registrarse
por separado; no se deduce de las pruebas automatizadas.

## Verificación del incremento

Validación automatizada realizada el 2026-10-27:

- 330 pruebas generales aprobadas en Windows y Linux, con 82.55 % de
  cobertura de líneas/ramas; el mínimo configurado es 70 %.
- 45 pruebas aprobadas con PostgreSQL real en Docker, incluidas las 12
  nuevas de versiones administrativas y su flujo HTTP con JWT firmado.
- Ruff, formato, mypy estricto, exportación de OpenAPI y paquete Python
  comprobados. El contrato expone nueve rutas y seis operaciones de
  administración de estampados.
- Docker comprobó aislamiento, usuario sin privilegios, migración
  explícita, recuperación de readiness y persistencia al recrear la base.
  Se retiraron exclusivamente los recursos de su proyecto temporal.

El usuario confirmó el 2026-10-27 la ejecución manual de las 12
peticiones con las respuestas esperadas: creación e historial,
conservación de recargos, conflicto de versión, JWT ausente, cliente
sin permiso, importe inválido y cursor inválido. Se configuró
printFileId con el id de un original disponible y se usaron tokens
vigentes separados para cliente y administrador, solo en Postman.
Esta evidencia manual se distingue de las pruebas automatizadas.
No se emitieron tokens de prueba desde el servicio ni se modificaron roles.

## GitHub Flow de este incremento

La rama se creó desde main limpio con estos comandos:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/print-versioning
```

Después de revisar los cambios y validar Postman, desde la raíz:

```powershell
git add services/personalizationService contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): version administrative prints"
git push -u origin feat/personalization/print-versioning
```

Crear el PR hacia main con ese mismo título. Revisar permisos de
administrador, actor derivado de sub, conservación del historial,
transacción de auditoría, concurrencia y controles de CI en verde.
Fusionar con Squash and merge antes de comenzar otro incremento.

Tras fusionar:

```powershell
git switch main
git pull --ff-only origin main
git status
```

Los cambios no se confirman ni se suben automáticamente.
