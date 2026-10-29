# Worker y miniaturas privadas de estampados

Rama: `feat/personalization/print-thumbnails`, desde main tras el PR #35.

## Alcance y contratos

Este incremento prepara las miniaturas de RF08. El catálogo de clientes
se implementará en la rama siguiente. No representa prendas ni modifica
el catálogo de productos, precios base o inventario de Catalog Service.

Pillow se ejecuta en un proceso y contenedor separados de FastAPI. Cada
original DISPONIBLE utilizado por alguna versión de estampado tiene una
miniatura PNG v1: cabe en 320 × 320 píxeles, conserva proporción y alpha,
aplica orientación EXIF y elimina EXIF, perfiles y textos del derivado.
No amplía imágenes pequeñas. El tamaño es una decisión técnica local;
los documentos exigen miniaturas, pero no fijan una resolución concreta.

Se validan nuevamente firma, formato, dimensiones y decodificación. Los
bytes descargados deben coincidir con tamaño y SHA-256 de archivo antes
de procesarse. Los originales permanecen intactos; una versión de precio
que reutiliza la misma imagen reutiliza también su miniatura. Se procesan
versiones históricas y estampados retirados para conservar sus recursos.

Solo un JWT administrador verificado localmente puede usar estas rutas:

| Método y ruta relativa a /api/v1/admin/prints | Resultado |
| --- | --- |
| GET /{printId}/versions/{versionId}/thumbnail | 200, metadata camelCase |
| POST /{printId}/versions/{versionId}/thumbnail/download-urls | 201, fileId, expiresAt y downloadUrl |

Los enlaces duran 60 segundos por defecto, dentro del límite previo de
1–300 segundos. Las respuestas llevan Cache-Control: no-store. El acceso
por enlace firmado es temporal y no requiere enviar JWT al proveedor.
El bucket sigue privado; conocer la clave de objeto no autoriza acceso.

Errores: 401 sin JWT, 403 cliente, 404 versión inexistente o ajena al
estampado, 409 FILE_NOT_READY si falta la miniatura o sigue pendiente,
422 UUID inválido y 503 por dependencia no disponible. Todos los errores
de la API siguen RFC 9457. GET nunca inicia procesamiento. Las rutas de
originales /files rechazan las miniaturas con 404; su acceso se controla
mediante el recurso de estampado, no reutilizando permisos de originales.

## Persistencia, concurrencia y recuperación

Se conserva exactamente el modelo SQL de la sección 7. No se requiere
nueva tabla, columna ni migración: las referencias de estampado_version
son trabajos durables redescubribles; las miniaturas son filas de archivo.
No se ejecuta DDL al arrancar y no se crea nada manualmente en PostgreSQL.

La convención de uso es MINIATURA_V1:<UUID del original>. El identificador
del derivado es UUIDv5 con namespace fijo y UUID del original; la clave de
objeto es <UUID del derivado>.png. Es una relación técnica calculable,
sin una FK nueva que el modelo oficial no contempla. propietario_ref y
bucket se conservan. Un cambio incompatible del algoritmo debe introducir
otra versión de uso/namespace y mantener las miniaturas ya referenciadas.

El worker consulta lotes ordenados por UUID con cursor y un máximo de
100 imágenes. Avanza después de errores para no bloquear a las demás;
al completar la vuelta vuelve a intentar los trabajos pendientes. Cada
trabajo reclama un advisory lock de sesión de PostgreSQL sin esperar.
Dos procesos no procesan simultáneamente un mismo origen mientras su
conexión está viva. No mantiene transacciones ni bloqueos de fila durante
la descarga, transformación o subida. La conexión física del reclamo se
cierra al salir, incluso por excepción; nunca devuelve locks al pool.
Perder la conexión puede liberar el reclamo antes de terminar el proceso:
el UUID estable, la intención persistida y la subida create-only siguen
protegiendo el objeto de sobrescrituras.

Antes de subir se confirma PENDIENTE_CARGA con hash, dimensiones y bytes
exactos. Solo después de una respuesta de éxito pasa a DISPONIBLE. Si
la subida tuvo resultado incierto o falló la publicación local, el ciclo
siguiente descarga el objeto esperado y verifica hash y tamaño. Si ya
existe y coincide, publica sin volver a subirlo. Si hay ausencia explícita
NoSuchKey/not_found, puede reconstruir y subir al mismo UUID. Fallos de
red, permisos, bucket, respuesta desconocida o corrupción se conservan
como pendientes: no se interpretan como ausencia y no se sobrescribe ni
elimina nada. Cada intento queda limitado por timeouts y tamaños; no hay
reintentos ciegos de una escritura con resultado incierto.

No se añade RabbitMQ para una tarea derivada que ya puede reconstruirse
desde referencias confirmadas. Esto evita cambiar los contratos de otros
servicios. La búsqueda por uso es suficiente para el alcance actual;
revisar índices o una cola técnica mediante migraciones si el volumen
y las mediciones futuras lo justifican.

## Ejecución y límites

Requisitos: Docker Linux, base migrada por Alembic, bucket privado y clave
de servidor ya preparados según private-files.md. No volver a crear claves
ni compartirlas. El worker monta los mismos secretos de backend y no
publica puertos. Reutiliza la imagen del servicio como usuario 10001, con
raíz de solo lectura, 1 CPU y 512 MiB. Procesa una imagen a la vez.

Desde la raíz del repositorio, arrancar la base y API para pruebas:

```powershell
docker compose --env-file infra/personalization/.env -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml up -d --wait db-personalizacion personalization
```

Si aún faltan migraciones, aplicar explícitamente `personalization-migrate`
antes de exigir readiness. No usar create_all ni editar tablas a mano.

Worker continuo (perfil images, sin alterar el arranque por defecto):

```powershell
docker compose --env-file infra/personalization/.env -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile images up -d personalization-worker
docker compose --env-file infra/personalization/.env -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml logs --tail 20 personalization-worker
```

Un único lote acotado, útil para diagnóstico; no vacía toda la cola:

```powershell
docker compose --env-file infra/personalization/.env -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml run --rm --no-deps personalization-worker python -m personalization.interfaces.workers.thumbnails --once
```

WORKER_BATCH_SIZE=10 (1–100) y WORKER_POLL_SECONDS=10 (1–300) se validan
al arrancar. El worker comprueba revisión Alembic y acceso a la base antes
de cada lote. Sin Storage configurado termina con código 1; configuración
inválida devuelve 2; --once devuelve 1 si falla algún trabajo o dependencia.
El modo continuo difiere errores y vuelve a sondear. SIGTERM/SIGINT termina
el trabajo actual y evita iniciar el siguiente. La gracia de cierre es
120 segundos; una interrupción forzada conserva la intención recuperable.

Los logs JSON resumen conteos/códigos por lote con trace_id y span_id.
No incluyen imágenes, JWT, nombres, claves de servidor ni enlaces firmados.
No se registra cada sondeo vacío exitoso del modo continuo.

## Pruebas automáticas

La suite verifica renderizado PNG/JPEG/CMYK/paleta, orientación, alpha,
proporción, no ampliación, stripping de metadata e integridad del origen.
También comprueba errores de Storage, dos reclamos concurrentes, cortes
antes/después de subir y fallo de publicación, recuperación sin duplicados,
descubrimiento histórico, paginación y permisos con JWT firmado real.

Ejecutar pytest desde services/personalizationService con dependencias
del lockfile. Para PostgreSQL usar `infra/personalization/verify_stack.py`:
crea un proyecto y volumen temporales, rechaza esquemas poblados y retira
solo sus recursos. Nunca ejecutar la suite de integración contra la base
de desarrollo con archivos y estampados del usuario.

## Postman: 12 comprobaciones en orden

Importar únicamente print-thumbnails.postman_collection.json. Conservar
el entorno local actual para no perder las variables ya guardadas. Usar:

- baseUrl=http://127.0.0.1:8082.
- adminAccessToken: access token vigente de la cuenta administrador.
- accessToken: access token vigente de la cuenta cliente.
- printId: un estampado existente con original DISPONIBLE.

Los primeros pasos crean automáticamente thumbnailVersionId,
thumbnailSourceSnapshot, thumbnailFileId y thumbnailDownloadUrl. No hay
cuerpos multipart, archivos adjuntos ni datos que editar manualmente en
los requests. Si caduca el enlace, repetir 03 y enseguida 04. El JWT se
obtiene en Auth, POST http://127.0.0.1:8080/api/v1/sessions, con correo y
contraseña solo en Postman; copiar accessToken al campo del rol correcto.

| Paso | Comprobación | HTTP |
| --- | --- | --- |
| 01 | Seleccionar la versión actual | 200 |
| 02 | Metadata de miniatura disponible, PNG y <=320 px | 200 |
| 03 | Crear enlace privado | 201 |
| 04 | Descargar y visualizar PNG antes de 60 segundos | 200 |
| 05 | Repetir metadata conserva el mismo ID | 200 |
| 06 | Versión, archivo original y recargo conservados | 200 |
| 07 | Cliente no consulta metadata administrativa | 403 |
| 08 | Cliente no crea enlace administrativo | 403 |
| 09 | Sin JWT | 401 |
| 10 | Versión inexistente | 404 |
| 11 | UUID inválido | 422 |
| 12 | El ID derivado no se ofrece como original | 404 |

Si 02 devuelve 409, esperar al siguiente lote y revisar el log del worker.
Un error de permisos/JWT no se corrige subiendo otro archivo. No exportar
valores locales de tokens ni URL firmadas a Git. La plantilla versionada
mantiene esos campos vacíos. Registrar la confirmación manual del usuario
separadamente de los resultados de pytest y Docker.

Para detener después de las pruebas, conservando todos los datos:

```powershell
docker compose --env-file infra/personalization/.env -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml --profile images stop personalization-worker personalization db-personalizacion
```

Detener también el proceso local de Auth iniciado para estas pruebas.
No ejecutar down --volumes sobre el proyecto local.

## GitHub Flow y revisión

Crear desde main (ya realizado para este incremento):

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/print-thumbnails
```

Después de confirmar Postman y revisar los cambios:

```powershell
git add services/personalizationService infra/personalization contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): generate private print thumbnails"
git push -u origin feat/personalization/print-thumbnails
```

Crear PR con ese título hacia main. Revisar procesamiento separado de la
API, permisos y Storage privado, conservación de originales/versiones,
recuperación de intenciones, ausencia de secretos, contratos, límites y
CI en verde. Fusionar mediante Squash and merge y después sincronizar:

```powershell
git switch main
git pull --ff-only origin main
git status
```

## Trazabilidad y fuentes

| Requisito | Evidencia |
| --- | --- |
| RF08 | Miniaturas preparadas; catálogo cliente reservado al siguiente incremento |
| RF30 | Inspección administrativa por versión sin alterar historial |
| RNF01/RNF03 | Decodificación, límites, hash, bucket privado y guards JWT locales |
| RNF06 | Reclamo entre procesos, intención durable y publicación recuperable |
| RNF07/RNF09 | OpenAPI, pruebas HTTP/PG y colección manual |
| Estándar secciones 6/7 | Logs con trazas, contenedor separado y secretos montados |
| BD sección 7 | archivo y estampado_version, sin cambios al esquema oficial |

La cobertura de líneas y ramas no sustituye la matriz funcional de RNF09.

- [Pillow 13.0, Image.thumbnail](https://pillow.readthedocs.io/en/stable/reference/Image.html).
- [Pillow, orientación EXIF](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).
- [PostgreSQL 17, advisory locks](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).
- [Supabase Storage, errores de objetos](https://supabase.com/docs/guides/storage/debugging/error-codes).

## Resultados

Validación realizada el 2026-10-28:

- 420 pruebas generales aprobadas en Windows y en la imagen Linux.
  Windows registró 81.74 % de cobertura de líneas/ramas, sobre el mínimo
  configurado de 70 %. Las 61 pruebas PostgreSQL se ejecutaron aparte.
- 61 pruebas aprobadas contra PostgreSQL real, incluidas ocho nuevas de
  descubrimiento, exclusión entre conexiones, recuperación y persistencia.
- Ruff, formato, mypy estricto (152 archivos), tipos de infraestructura,
  exportación OpenAPI, paquete y scripts de las 12 pruebas Postman válidos.
- Docker verificó migración explícita, aislamiento, usuario 10001,
  recuperación de readiness, reversión/reaplicación y persistencia del
  volumen. El proyecto temporal y su volumen fueron eliminados.
- Storage real: una miniatura PNG de 213 × 320 píxeles y 131748 bytes
  quedó DISPONIBLE. El original de 2658613 bytes conserva su SHA-256 y
  la versión 2 del estampado permanece intacta. La descarga firmada
  devolvió 200 con los mismos bytes; la ruta pública anónima devolvió 400.
- Un segundo lote real completó cero trabajos y no duplicó el derivado.
  No se almacenaron tokens, claves de servidor ni enlaces en Git.

El usuario confirmó el 2026-10-28 que las 12 comprobaciones manuales
de Postman devolvieron las respuestas esperadas: metadata y descarga PNG,
reutilización del ID, conservación de la versión original, permisos de
administrador/cliente, ausencia de JWT, versión inexistente, UUID inválido
y rechazo del derivado como original. Esta evidencia manual se distingue
de las pruebas automatizadas anteriores.

Tras la confirmación se detuvieron Auth, Personalization, PostgreSQL y
el worker. Se verificó que no quedaban contenedores del proyecto en
ejecución ni escuchas en los puertos 8080 y 8082. El volumen de la base
y los objetos de Storage se conservaron. No se ha realizado commit,
push ni PR de este incremento.
