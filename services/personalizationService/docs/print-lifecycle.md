# Edición, activación y retiro de estampados

Rama: `feat/personalization/print-lifecycle`.
Alcance: completar las operaciones administrativas sobre datos y estado
del estampado, conservando versiones e integridad, como parte de RF30.
El catálogo para clientes y las miniaturas conservan sus incrementos
propios. La activación actual prepara el estado para ese catálogo.

## Contrato

La nueva operación es PATCH `/api/v1/admin/prints/{printId}`. Exige un JWT
localmente verificado con rol administrador, JSON con al menos un campo
editable y el header If-Match. El éxito devuelve 200, la representación
actual y su nuevo ETag. No se adjuntan imágenes en esta operación.

| Campo | Regla |
| --- | --- |
| name | String recortado de 1–120 caracteres; no acepta null |
| description | String de hasta 2000 caracteres o null para limpiarlo |
| active | Booleano JSON true/false; no acepta cadenas, números ni null |

Los campos omitidos permanecen iguales. No se aceptan cambios de id,
actor, propietario, archivo, precio ni número de versión. Para cambiar
imagen o recargo se conserva POST `/{printId}/versions` y su
`expectedVersion`, implementado en la rama anterior.

Ejemplos de body:

```json
{"name": "Logo actualizado", "description": "Nueva descripción"}
```

```json
{"description": null}
```

```json
{"active": false}
```

```json
{"active": true}
```

Un estampado retirado continúa visible para el administrador y conserva
su historial y referencias. Puede editarse o recibir una nueva versión
mientras está inactivo. Reactivarlo verifica que la última versión
referencie un original disponible del bucket del servicio. Retirar no
borra archivos ni versiones; el permiso de descarga privada no cambia.
No se implementa borrado físico ni cambia un diseño histórico.

## ETag e integridad concurrente

GET `/{printId}` y POST de creación ahora entregan un ETag fuerte. Se
deriva de todos los valores de la representación: identificador, nombre,
descripción, estado y versión actual con su archivo y recargo. No añade
columnas al modelo ni reemplaza la numeración de estampado_version.

La edición envía ese valor completo, conservando las comillas:

```http
If-Match: "HASH_DEVUELTO_EN_ETAG"
```

El servidor bloquea la fila del estampado y vuelve a calcular la revisión
con los datos vigentes dentro de la transacción. Si otra edición o una
nueva versión la cambió, devuelve 412 sin escribir. El cliente consulta
de nuevo, revisa los cambios y decide si reenvía. No hay reintento ciego.
La consulta individual obtiene datos y última versión en una sola
sentencia SQL para evitar representaciones mezcladas entre dos lecturas.

Se admite la sintaxis HTTP de listas de etiquetas y se comparan solo las
fuertes; una etiqueta débil por sí sola no satisface la condición. La
longitud total se limita a 2048 caracteres y a 32 etiquetas como política
de recursos de este servicio. Las comas dentro de etiquetas opacas no se
confunden con separadores. If-Match `*` comprueba solo existencia, según
HTTP; no detecta ediciones intermedias. La colección usa un ETag concreto.

Una petición con valores idénticos y condición vigente devuelve 200 con
el mismo ETag sin crear auditoría ni versión adicional. Una etiqueta
previa puede volver a coincidir si la representación completa vuelve al
mismo estado; el ETag representa contenido, no un contador de eventos.

Se usan las columnas existentes de `app.estampado` y `app.auditoria_local`
y referencias existentes a estampado_version/archivo. No hay cambio de
esquema ni migración nueva. `0001_personalization` permanece intacta y no
se crean tablas al arrancar.

## Auditoría y permisos

El caso de uso vuelve a comprobar el rol, y deriva el actor del sub
verificado. El cambio y su auditoría se confirman en una transacción.
Si la auditoría falla después del UPDATE, ambos cambios se revierten.

- PRINT_UPDATED identifica cambios de datos o cambios combinados.
- PRINT_ACTIVATED y PRINT_RETIRED identifican cambios exclusivos de estado.
- El detalle contiene campos modificados, revisión anterior/nueva,
  estado anterior/nuevo e ID de versión; no copia textos libres, JWT,
  contraseñas, claves ni URLs firmadas.

Las versiones históricas y sus recargos no se actualizan. Los cambios
de nombre/estado pertenecen a estampado; imagen/precio pertenecen a
estampado_version, respetando el modelo oficial. No se toca Auth Service,
sus roles, otras bases de datos ni interfaces de escritorio o móvil.

## Errores

Se conserva application/problem+json con los siete campos del proyecto.

| HTTP | Caso |
| --- | --- |
| 400 | JSON mal formado o INVALID_PRINT_PRECONDITION |
| 401 | JWT ausente, inválido o vencido |
| 403 | Cliente o rol insuficiente |
| 404 | PRINT_NOT_FOUND |
| 409 | INVALID_PRINT_FILE al reactivar un original no disponible |
| 412 | PRINT_PRECONDITION_FAILED; volver a consultar el recurso |
| 422 | Body vacío, null no permitido, tipo inválido o campo no editable |
| 428 | PRINT_PRECONDITION_REQUIRED; enviar el ETag en If-Match |
| 503 | PostgreSQL o llaves JWKS no disponibles |

Las respuestas, incluidos 428 y el resto de errores, usan no-store.
El error no incorpora SQL ni datos de la entrada rechazada.

## Postman paso a paso

Importar solo `print-lifecycle.postman_collection.json`. Seleccionar el
entorno local existente; no hace falta reemplazarlo ni perder sus valores.

| Variable manual | Valor |
| --- | --- |
| baseUrl | http://127.0.0.1:8082 |
| adminAccessToken | JWT nuevo del administrador, sin Bearer |
| accessToken | JWT nuevo del cliente, para la prueba de 403 |
| printId | UUID de un estampado ya creado en el incremento anterior |

Si no existe alguna variable, agregarla manualmente en Environments al
entorno seleccionado. No confundir printId con printFileId o fileId.
Esta colección no necesita printFileId ni subir archivos. Para obtener
otro printId, usar Listar estampados o Crear estampado de la colección
anterior. El archivo versionado del entorno conserva vacíos los tokens.

Obtener ambas sesiones por separado mediante POST
`http://127.0.0.1:8080/api/v1/sessions`, Authorization No Auth y JSON
email/password. La Secret key de Storage no es un access token de usuario.

Consultar para editar guarda automáticamente printEtag,
previousPrintEtag, lifecycleVersionId y lifecycleVersionSnapshot. No hay
que pegarlas manualmente: los PATCH usan el ETag vigente de la petición
anterior. Los scripts también comprueban que la versión no cambie.

| Orden | Petición | Esperado |
| --- | --- | --- |
| 1 | Consultar para editar | 200; guarda el ETag y la versión original |
| 2 | Editar nombre y descripción | 200; mismo archivo y recargo |
| 3 | ETag anterior | 412; no sobrescribe |
| 4 | Limpiar descripción | 200; description=null |
| 5 | Retirar estampado | 200; active=false |
| 6 | Consultar retirado | 200; sigue disponible para administrador |
| 7 | Consultar versión preservada | 200; versión sin modificaciones |
| 8 | Reactivar estampado | 200; active=true |
| 9 | Sin If-Match | 428 |
| 10 | Cliente sin permiso | 403 |
| 11 | Sin JWT | 401 |
| 12 | Campo no editable | 422 |
| 13 | If-Match mal formado | 400 |
| 14 | Estado inválido | 422 |
| 15 | Activar sin cambios | 200; mismo ETag |

Ejecutar todas en orden y detenerse ante el primer resultado inesperado.
El nombre de prueba usa un GUID dinámico para asegurar un cambio real
incluso al repetir la secuencia. La prueba 3 conserva la etiqueta previa
y no reemplaza la vigente. No guardar JWT en el repositorio ni compartirlos
en capturas. No cambiar Authorization ni Headers preparados por la colección.

## Docker y GitHub Flow

Iniciar con la imagen construida, desde la raíz:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml up -d --no-build --wait personalization
```

La rama se abrió desde main limpio:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/print-lifecycle
```

Después de validar Postman y revisar los cambios:

```powershell
git add services/personalizationService contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): manage print lifecycle"
git push -u origin feat/personalization/print-lifecycle
```

Crear el PR hacia main con el mismo título. Revisar permisos, precondición
bajo bloqueo, rollback de auditoría, conservación de versiones, contrato
y CI en verde. Fusionar con Squash and merge antes del siguiente incremento.

```powershell
git switch main
git pull --ff-only origin main
git status
```

## Matriz de evidencia y fuentes

| Requisito | Implementación | Prueba |
| --- | --- | --- |
| RF30 | Edición, retiro y reactivación con historial | TestClient y PostgreSQL |
| RF30/RNF03 | Auditoría atómica y actor del JWT | Fallo de PK de auditoría después del UPDATE |
| RNF03 | Solo administrador; campos permitidos | Firmas JWT reales y rechazo de cliente/anonimato |
| RNF06 | Revisión bajo bloqueo de fila | Dos escritores: una edición y un 412 |
| RNF07/RNF09 | Contrato y flujos HTTP | OpenAPI y colección Postman |

Las pruebas automatizadas usan PostgreSQL real y claves JWT efímeras;
sustituyen únicamente el transporte JWKS. Las pruebas manuales con las
cuentas reales se registran por separado tras confirmación del usuario.
La cobertura de líneas/ramas no sustituye la matriz funcional de RNF09.

- [RFC 9110, If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match).
- [RFC 6585, 428](https://www.rfc-editor.org/rfc/rfc6585).
- [Variables dinámicas de Postman](https://learning.postman.com/docs/tests-and-scripts/write-scripts/variables-list).

## Resultado automatizado

Validación realizada el 2026-10-27:

- 374 pruebas generales aprobadas en Windows y Linux, con 81.86 % de
  cobertura de líneas/ramas y mínimo configurado de 70 %.
- 53 pruebas aprobadas contra PostgreSQL real, incluidas ocho nuevas de
  ciclo de vida, concurrencia, rollback y flujo HTTP completo.
- Ruff, formato, mypy estricto, contrato OpenAPI y paquete comprobados.
- Docker verificó migración explícita, aislamiento, usuario sin
  privilegios, recuperación de readiness y persistencia. Se retiraron
  solo los recursos de su proyecto temporal.

El usuario confirmó el 2026-10-27 que las 15 comprobaciones manuales
de Postman devolvieron las respuestas esperadas. Esto incluye edición,
limpieza de descripción, retiro, reactivación, conservación de versión,
ETag anterior, precondición ausente, permisos, campos/tipos rechazados
y actualización sin cambios. La evidencia manual se distingue de las
pruebas automatizadas anteriores.

No se modificaron roles ni se almacenaron tokens en el repositorio.
Al terminar se detuvieron Auth, Personalization y PostgreSQL,
conservando los datos y archivos.
