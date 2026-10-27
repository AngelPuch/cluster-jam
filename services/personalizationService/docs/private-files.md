# Archivos originales privados

Rama: `feat/personalization/private-file-storage`.
Alcance: RF10 y RNF01/RNF03, sobre el validador y la migración existentes.
Se implementan la subida persistente, la lectura autorizada de metadata y
la emisión de enlaces de descarga breves. El bucket real y su clave deben
ser preparados por alguien con acceso al proyecto Supabase.

## Contratos REST

Todas las operaciones exigen un JWT Supabase validado localmente por JWKS,
con rol protegido `cliente` o `administrador`. El propietario se obtiene
exclusivamente de `sub`. El body o las cabeceras de usuario no otorgan roles
ni pueden asignar propietario.

| Método y recurso | Entrada | Éxito |
| --- | --- | --- |
| `POST /api/v1/files` | Multipart con un solo campo archivo `file` | 201, metadata y `Location` |
| `GET /api/v1/files/{fileId}` | UUID del recurso | 200, metadata autorizada |
| `POST /api/v1/files/{fileId}/download-urls` | Sin body | 200, URL firmada y expiración |

La metadata usa camelCase: `id`, `ownerId`, `mimeType`, `sizeBytes`,
`widthPx`, `heightPx`, `sha256` y `state`. No se publican bucket, ruta de
objeto, nombre original, binarios ni claves de servidor. La descarga incluye
`fileId`, `downloadUrl` y `expiresAt`, y usa `Cache-Control: no-store`.

El dueño puede leer su metadata y solicitar un enlace. La excepción para
administrador está explícita en el caso de uso. Otro cliente recibe 403
antes de cualquier petición de firma a Storage; un ID desconocido produce
404. Un original pendiente no permite descarga y devuelve 409.

Los errores conservan los siete campos RFC 9457 del proyecto y su traza.
JWT ausente o inválido produce 401; rol o propiedad insuficientes, 403;
formato/MIME, 415; imagen dañada o dimensiones, 422; tamaño, 413; capacidad,
429; recepción lenta, 408; proveedor/configuración/BD no disponible, 503.
No se copian mensajes remotos, URLs firmadas o secretos en los errores.

## Carga duradera y recuperación

No existe una transacción distribuida entre PostgreSQL y Storage. El flujo
aplica esta secuencia, sin mantener una transacción SQL abierta en la red:

1. Validar el original y calcular metadata, UUID y SHA-256.
2. Comprobar que el bucket configurado sea privado y tenga los límites
   esperados: 10 000 000 bytes y PNG/JPEG.
3. Confirmar `archivo` con estado `PENDIENTE_CARGA` y uso `ORIGINAL`.
4. Crear el objeto con clave UUID, MIME real y `x-upsert=false`.
5. Tras recibir confirmación, cambiar la fila a `DISPONIBLE` bajo bloqueo
   de fila. Publicar de nuevo es idempotente.

No hay reintentos automáticos de la escritura externa ni borrados ante
timeouts: una respuesta perdida puede corresponder a una carga exitosa.
La intención ya confirmada permite localizar cualquier objeto creado.
Si la carga o su publicación falla, el error incluye `Location` de la
metadata conocida sin añadir campos al Problem Details. El cliente puede
consultarla para distinguir `PENDIENTE_CARGA` de `DISPONIBLE`.

El comando de reconciliación descarga el original con lectura acotada y
compara tamaño y SHA-256 antes de publicarlo. No sobreescribe ni elimina
objetos, ni publica un archivo ausente o diferente. Si el fallo ocurrió
antes de transferir el original, hace falta una carga nueva; la intención
anterior permanece sin publicar. `POST /files` no promete idempotencia de
reintentos del cliente ni reanudación de una transferencia perdida.

Se usan las columnas ya versionadas de `app.archivo`; no hace falta una
migración nueva para estas operaciones. La API no crea tablas al arrancar.
Los estados son valores de aplicación sobre el `text` del modelo oficial.
No se agregan columnas ni tablas ajenas al modelo. No hay borrado de archivos
referenciados ni limpieza automática basada en una antigüedad inexistente.

## Límites de recepción y recursos

El handler recibe `Request`, no un `File()` que FastAPI pueda analizar
antes de ejecutar sus dependencias. El JWT y rol se comprueban antes de
leer el multipart. Se permiten un archivo y cero campos de texto; se
rechazan parámetros como `ownerId`, `userId`, `state` o `bucket`.

El archivo conserva el máximo inclusivo de 10 000 000 bytes. El cuerpo
multipart completo tiene un máximo adicional de 131 072 bytes de overhead,
comprobado tanto en Content-Length como en los chunks reales, incluso sin
ese header. La recepción tiene un plazo de 30 segundos y se acepta una
subida en curso por proceso; las demás reciben 429 con `Retry-After: 1`.
Pillow, SQLAlchemy y HTTPX síncronos se ejecutan en el pool de hilos.

El spool puede pasar a disco después de 1 MiB. Compose mantiene la raíz
de ejecución de solo lectura y añade `/tmp` como tmpfs de 32 MiB. Starlette
cierra los archivos parciales ante fallos o cancelación; el handler cierra
el formulario en cualquier resultado. Los originales no quedan en un
directorio persistente local. El proxy de producción debe mantener sus
propios límites de cuerpo y tiempo de recepción.

## Preparar Supabase sin exponer la clave

Una persona con acceso al proyecto debe crear una **Secret key** de servidor
llamada `personalization` en Settings → API Keys. Debe comenzar con
`sb_secret_`; esta integración no utiliza la clave publicable ni el JWT de
un usuario como credencial de servidor. Crear una clave nueva no exige
reemplazar las que utiliza Auth Service.

Desde la raíz del repositorio, en una terminal interactiva:

```powershell
py -3.14 infra/personalization/provision_local.py
py -3.14 infra/personalization/set_storage_key.py
```

El segundo comando solicita la clave sin mostrarla y escribe únicamente
`infra/personalization/.secrets/supabase_storage_key`, ignorado por Git.
No pasar la clave como argumento, pegarla en el chat, agregarla a `.env`
ni colocarla en Postman. El contenedor la recibe como secreto montado. Al rotar esa clave,
recrear la API con `--force-recreate` para renovar el montaje y cliente.
En Linux el directorio está protegido y el secreto permite lectura al
usuario de ejecución; en Windows se usan los permisos del usuario local.

La configuración pública permanece en `infra/personalization/.env`:

```dotenv
SUPABASE_ISSUER=https://your-project.supabase.co/auth/v1
SUPABASE_JWKS_URL=https://your-project.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_STORAGE_BUCKET=personalization-originals
DOWNLOAD_URL_TTL_SECONDS=60
```

Para crear y verificar el bucket mediante la API, sin SQL manual:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile tools build personalization-storage
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml run --rm personalization-storage create
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml run --rm personalization-storage check
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml up -d --wait personalization
```

`create` solo crea un bucket ausente; no cambia uno existente. `check`
rechaza buckets públicos o con límites distintos. El propietario del
proyecto debe mantener este bucket sin políticas de acceso directo de
clientes, incluidas políticas generales que pudieran abarcarlo.

La clave nueva viaja exclusivamente en `apikey`, según el contrato actual
de Supabase. No se envía como bearer ni se sustituye por el JWT del cliente.
El adaptador solo permite el origen configurado, bucket esperado y claves
UUID canónicas. No sigue redirecciones ni utiliza proxies del entorno.
HTTPX utiliza límites explícitos: 5 s de conexión/pool y 30 s de lectura y
escritura. La emisión de enlaces acepta 1–300 s, con 60 s predeterminados.
Una URL firmada permite acceso hasta expirar a quien la posea.

Sin el overlay, Storage queda desactivado y no se monta la clave. Las
operaciones de almacenamiento fallan con 503, sin usar un almacenamiento
local alternativo. Liveness y el contrato siguen disponibles; readiness
comprueba PostgreSQL y su revisión. La consulta de metadata puede continuar
durante una caída de Storage. El arranque no crea buckets ni llama a Auth.

## Reconciliación de intenciones

Desde la raíz, solo para operadores del servidor:

```powershell
docker compose -f infra/personalization/compose.yaml run --rm personalization-storage pending --limit 20
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml run --rm personalization-storage reconcile --file-id UUID_DEL_ARCHIVO
```

`pending` devuelve IDs en un evento JSON, con límite máximo de 100. No lee
credenciales de Storage si está desactivado. La reconciliación requiere el
secreto y no tiene endpoint público. Los comandos devuelven 0 en éxito,
1 ante fallo de la operación y 2 ante configuración inválida.

## Prueba con Postman de este incremento

Importar `contracts/postman/personalization/files.postman_collection.json`
y `local.postman_environment.json`. Seleccionar ese entorno y configurar
`baseUrl=http://127.0.0.1:8082` y `accessToken` con un JWT de cliente emitido
por el Auth Service del equipo. La clave `sb_secret_` no es un JWT de usuario.
No guardar valores reales en los archivos versionados de entorno.

1. En **Subir original**, Body → form-data contiene la clave `file` de tipo
   File. Seleccionar un PNG o JPEG válido. No fijar Content-Type del body
   manualmente: Postman debe generar el boundary. Enviar y comprobar 201,
   `Location`, `ownerId`, SHA-256 y estado DISPONIBLE. El script guarda `fileId`.
2. Ejecutar **Consultar metadata**. Debe devolver 200 con el mismo ID.
3. Ejecutar **Crear enlace de descarga**. Debe devolver 200, `downloadUrl`
   y `expiresAt`. El script guarda el enlace solo en el entorno local.
   Ejecutar **Descargar original** y comprobar bytes/formato. La petición
   de descarga usa el enlace firmado y no envía Authorization.
4. Ejecutar **Sin JWT** con Authorization → No Auth y Body → none: debe
   devolver 401 con `WWW-Authenticate: Bearer`. No requiere archivo.
5. En **Formato inválido**, seleccionar un archivo de texto no vacío:
   debe devolver 415 `UNSUPPORTED_IMAGE_TYPE`. Un PNG truncado debe producir
   422 `INVALID_IMAGE`; un archivo que supere 10 000 000 bytes, 413.
6. Añadir un campo de texto `ownerId` al multipart: debe producir 400,
   sin crear una fila ni objeto. Quitar el campo para las demás pruebas.
7. Con otro JWT de cliente, consultar el ID anterior o pedir su descarga:
   debe producir 403. Un JWT con rol protegido administrador puede hacerlo.
8. Con un ID inexistente válido, comprobar 404. Ante una caída o falta de
   configuración de Storage, comprobar 503 y ausencia de enlaces públicos.

Cada error debe ser `application/problem+json`, tener siete campos y un
`traceId` coincidente con `traceparent`. Los demás recursos del microservicio
y gRPC se probarán con Postman en sus incrementos correspondientes.

## Evidencia automatizada y validación externa

Las pruebas usan firmas JWT reales y validación local, imágenes reales de
Pillow, el protocolo HTTP del adaptador y PostgreSQL real en Docker.
El transporte de Supabase se sustituye por respuestas aisladas para probar
timeout antes/después de guardar, error de commit, propiedad, privilegios,
no sobrescritura, SHA-256 y rechazo de URLs o buckets incorrectos.

La prueba real contra el proyecto del equipo requiere acceso y clave de
servidor. Los tests aislados no se presentan como una carga real en la nube.
Tampoco equivalen a haber completado plantillas, estampados, diseños,
previews, checkout o el microservicio entero.

Fuentes técnicas primarias consultadas:

- [Claves de Supabase](https://supabase.com/docs/guides/getting-started/api-keys).
- [Acceso a Storage](https://supabase.com/docs/guides/storage/security/access-control).
- [Contrato HTTP de Storage](https://supabase.com/docs/reference/self-hosting-storage/v1/upload-a-new-object).
- [Carga estándar](https://supabase.com/docs/guides/storage/uploads/standard-uploads): permite este máximo; Supabase recomienda TUS por encima de 6 MB para mejorar fiabilidad. Este incremento no implementa reanudación.


## Trazabilidad del incremento

| Requisito | Implementación | Prueba | Validación pendiente |
| --- | --- | --- | --- |
| RF10 | Validación, intención local y carga del original | `test/files/`, `test/integration/test_private_files.py` | Proyecto real de Supabase |
| RNF01 | Bucket privado, UUID, SHA-256 y descargas breves | `test/files/test_supabase_storage.py` | Configuración de bucket y políticas del proyecto |
| RNF03 | JWT local, rol, propietario y excepción administrativa | `test/security/test_file_http.py` | Sesiones reales de usuarios del equipo |
| RNF09 | Casos de errores, recuperación y contrato | Suite de pytest y colección Postman | Ejecución de Postman contra el proveedor real |
| RNF10 | Imagen, secreto montado y tmpfs acotado | Docker y `verify_stack.py` | Despliegue y respaldos de producción |

La ausencia de acceso al proyecto no se sustituye por una validación
ficticia de la nube. Los dobles HTTP se limitan a los tests y no pueden
habilitar cargas de producción sin credenciales.

## Verificación real de Storage: 2026-10-27

Tras preparar la clave local, se creó y verificó el bucket privado desde
el comando operativo y desde la API en ejecución. Se activó el overlay
de Storage y ambos endpoints de salud respondieron correctamente.

El usuario confirmó una carga real desde Postman con HTTP 201. Una lectura
de PostgreSQL confirmó el original como `DISPONIBLE`. La verificación
contra Supabase confirmó el tamaño y SHA-256, la descarga mediante un
enlace firmado respondió HTTP 200 con bytes idénticos y el acceso anónimo
por la ruta pública fue rechazado. No se guardaron claves, JWT, enlaces
firmados ni datos de la cuenta en esta evidencia.

Esta comprobación usa el adaptador real y las credenciales del servidor.
Las consultas REST, los permisos y los casos negativos deben completarse
también en Postman con las identidades de los usuarios, según la guía
anterior. No implica que los demás incrementos del servicio estén listos.

## Archivos y autorización en Postman

| Petición | Archivo en el body | Autorización |
| --- | --- | --- |
| Subir original | PNG/JPEG real | JWT del cliente |
| Consultar metadata | Ninguno | JWT del dueño o administrador |
| Crear enlace de descarga | Ninguno | JWT del dueño o administrador |
| Descargar original | Ninguno | No Auth; usar el enlace firmado |
| Sin JWT | Ninguno; Body → none | No Auth |
| Formato inválido | Archivo .txt real, no vacío | JWT del cliente |

`EISDIR` indica que Postman intenta leer un directorio como archivo. En
las peticiones con multipart, eliminar la fila heredada y crear una fila
`file` de tipo File, seleccionando el archivo real. No escribir una ruta
de carpeta en Value ni dejar otro adjunto vacío. En Settings la carpeta
de trabajo debe contener el archivo elegido; en Body se selecciona el
archivo, no esa carpeta. No establecer Content-Type manualmente.
