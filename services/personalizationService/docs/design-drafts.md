# Borradores administrativos de diseño

Rama: `feat/personalization/design-drafts`, desde main tras PR #39.

## Alcance

Este incremento guarda selecciones de diseño en `diseno` y `aplicacion`,
con acciones administrativas en `auditoria_local`. Reutiliza el esquema
creado por la migración `0001_personalization`: no cambia tablas ni crea
DDL al arrancar. No requiere una migración nueva sin cambios de esquema.

Catalog Service y su contrato siguen ausentes. La API queda restringida a
borradores administrativos propios, con referencias QA de variante sin
verificar; todas las respuestas indican `catalogCompatibilityVerified=false`
y `checkoutReady=false`. Las plantillas siguen inactivas. Esto no habilita
diseños comerciales de clientes, publicación, carrito ni congelación real.
El valor mínimo DPI sigue pendiente de decisión del equipo; no cambia aquí.

No se generan previews ni se descargan imágenes al guardar: se validan las
referencias locales de archivos originales y versiones de estampado. El
análisis anterior sigue siendo una operación distinta, de solo lectura.

## Contrato y permisos

Todas estas operaciones exigen JWT local de administrador y propiedad del
diseño. El propietario siempre procede de `sub`; otro administrador recibe
403 al consultar, editar o copiar. El listado solo devuelve diseños propios.
Sin JWT: 401; rol cliente: 403 antes de consultar borradores o fuentes.

| Método y ruta | Resultado |
| --- | --- |
| POST /api/v1/admin/design-drafts | 201, nuevo BORRADOR versión 1 |
| GET /api/v1/admin/design-drafts | 200, resúmenes paginados propios |
| GET /api/v1/admin/design-drafts/{designId} | 200, snapshot con aplicaciones |
| PUT /api/v1/admin/design-drafts/{designId} | 200, reemplazo con If-Match |
| POST /api/v1/admin/design-drafts/{designId}/copies | 201, copia independiente |

POST/PUT reciben solo `variantId`, `templateId`, `applications` (0–20).
Cada aplicación recibe `zoneId`, `zoneSizeId` y exactamente una fuente:
`printVersionId` o `fileId`. Vaciar `applications` permite retirar todas las
aplicaciones del borrador. No hay PATCH ni DELETE en esta fase.

La zona pertenece a la plantilla; el tamaño pertenece a esa zona; no se
repite zona. Se reutiliza la validación completa de geometría y tamaños de
plantilla: límites, proporciones y no superposición. El ajuste proporcional y la
resolución efectiva se consultan mediante el análisis separado; el guardado
no vuelve a descargar la imagen ni acepta posiciones o transformaciones.

La transacción comprueba de nuevo relaciones zona/tamaño/plantilla y fuentes
originales DISPONIBLE en el bucket configurado. Versiones históricas de
estampados, incluso retirados, y originales de otros propietarios pueden
usarse aquí bajo el permiso administrativo explícito ya existente. Esto no
define la futura política de selección de cliente ni valida Catalog.

No se aceptan propietario, estado, versión, precios o previews en el cuerpo.
Se rechazan con 422. Las respuestas conservan JSON camelCase y errores RFC
9457 con siete campos, `application/problem+json` y traceId, sin tokens.
Todas las respuestas correctas llevan `Cache-Control: no-store`.

## Edición, concurrencia y copias

Las respuestas individuales incluyen ETag fuerte. POST devuelve además
Location. PUT exige el ETag vigente en If-Match, incluidas sus comillas.
Falta de header: 428; sintaxis inválida: 400; revisión obsoleta o solo tags
débiles: 412. El parser limita longitud y número de tags y admite listas;
`*` verifica existencia, sin proteger de otra revisión concurrente. Para
editar con control de revisión debe usarse el ETag concreto de GET.

El hash abarca raíz, propietario, versión, previews y selecciones/IDs de
aplicación en orden canónico de zona. Un reemplazo significativo incrementa
la versión, crea nuevos IDs de aplicación, invalida referencias de previews
y registra auditoría. Repetir el mismo contenido, incluso reordenado,
conserva versión, ETag, IDs, previews y auditoría. La versión evita aceptar
un ETag antiguo cuando el contenido cambia y luego vuelve al valor inicial.

Una escritura bloquea la raíz antes de comprobar estado y ETag. Un GET usa
bloqueo compartido breve para leer raíz y aplicaciones de la misma revisión.
Los cambios y la auditoría se confirman juntos: una falla revierte todo.
No se mantienen bloqueos mientras se accede a Storage. El listado usa UUID
ascendente y cursor vinculado a la identidad; no es un snapshot global.

Un diseño CONGELADO no admite PUT (409). POST de copies crea otro UUID en
BORRADOR versión 1, con nuevos IDs de aplicación y sin previews. El original
no cambia. No se expone una operación de congelación en esta rama: ese
estado se prueba solo en fixtures de la base desechable, sin SQL manual en
la base local. Un borrador también puede copiarse. Las copias revalidan las
referencias actuales y guardan sourceDesignId/sourceVersion en auditoría.

## Postman, paso a paso

1. Importar `contracts/postman/personalization/design-drafts.postman_collection.json`.
2. Seleccionar el entorno local que ya tiene tus variables. No reemplazarlo
   por la plantilla vacía si ya conserva tus valores locales.
3. Revisar `baseUrl=http://127.0.0.1:8082`, `printId` del estampado existente,
   `adminAccessToken` con JWT administrador vigente y `accessToken` cliente
   vigente. Renovar ambos mediante Auth si expiraron; no compartirlos.
4. Ejecutar las 31 solicitudes, de 01 a 31. Usar Collection Runner con una
   iteración o enviarlas en orden. No adjuntar imágenes ni editar cuerpos.
5. Los scripts crean automáticamente las variables draft*. No tienes que
   copiar ETag, IDs de zonas o IDs de aplicación manualmente. Una ejecución
   completa crea una plantilla QA inactiva y dos borradores propios.
6. Revisar códigos **y** Tests/Post-response: snapshots persistidos, revisión,
   copias independientes, paginación y errores problem+json. No basta con
   observar solo 200/201. Si una preparación falla, corregir JWT/printId y
   comenzar desde 01 para obtener referencias coherentes.

| Solicitudes | Código esperado |
| --- | --- |
| 01, 04–05, 07, 09–14, 31 | 200 |
| 02–03, 08 | 201 |
| 06, 17 | 412 |
| 15 | 428 |
| 16, 26 | 400 |
| 18–23, 29 | 422 |
| 24–25 | 404 |
| 27 | 403 |
| 28 | 401 |
| 30 | 405 |

Los errores comprueban ausencia de If-Match, sintaxis/tag débil, campos
controlados por servidor, tamaño de otra zona, duplicación y XOR de fuentes,
inexistencia, cursor y permisos. 31 vuelve a consultar para verificar que
las peticiones rechazadas no alteraron el diseño. Las pruebas automáticas
cubren además otra identidad administradora, CONGELADO, carreras y rollback;
no necesitas otra cuenta administradora ni modificar SQL para Postman.

## GitHub Flow

La rama de este incremento ya fue creada desde main actualizado:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/design-drafts
```

Después de confirmar las pruebas manuales y detener los servicios:

```powershell
git status
git diff --check
git add services/personalizationService contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): persist owned design drafts"
git push -u origin feat/personalization/design-drafts
```

PR hacia main con ese mismo título. Revisar propiedad/roles, borrador
administrativo sin Catalog, If-Match, transacciones/auditoría, copias de
CONGELADO, invalidación de previews y ausencia de credenciales. CI en verde;
usar Squash and merge. Después:

```powershell
git switch main
git pull --ff-only origin main
git status
```

No se realiza commit, push ni PR automáticamente. Antes de fusionar debe
quedar registrada la validación manual; previews, contrato gRPC, checkout,
Catalog y API comercial de cliente siguen pendientes.

## Validación

Validación automatizada del 2026-10-28 (hora local):

- 597 pruebas generales aprobadas en Windows y Linux, con 80.05 % de
  cobertura de líneas/ramas y mínimo configurado de 70 %.
- 108 pruebas aprobadas con PostgreSQL real en una base desechable. Las
  16 nuevas verifican snapshots, no-op, invalidación de previews, copias,
  carrera de dos ediciones, rollback de creación/edición/copia por falla
  de auditoría, propiedad, CONGELADO, límite de versión, relaciones locales,
  fuentes listas y flujo HTTP con JWT firmado.
- Ruff, formato, mypy estricto (211 archivos), paquete y OpenAPI aprobados.
  La refactorización de resolución de fuentes conserva las pruebas previas.
- Docker comprobó migración explícita, reversión/reaplicación, usuario sin
  privilegios, red/puerto privados de BD, recuperación y persistencia. Se
  retiró únicamente el proyecto temporal personalization-verify-5b596f40dfd5.
- Los 31 cuerpos/scripts de Postman y sus variables fueron revisados. Un
  recorrido HTTP separado con puertos en memoria y un ejecutor de scripts
  comprobó 61 aserciones en orden. Este recorrido no usa JWT reales ni
  sustituye las pruebas PostgreSQL/JWT o la ejecución manual de Postman.
- Auth y Personalization respondieron 200 en live/ready. La API real
  expone las cinco operaciones declaradas y rechaza el acceso anónimo con
  401 problem+json. Se inició Auth para renovación de JWT en el puerto 8080;
  Personalization escucha en 127.0.0.1:8082 con PostgreSQL privado.
- Una consulta local READ ONLY confirmó los recursos de referencia listos,
  cero diseños, cero aplicaciones y 16 auditorías antes de Postman. No se
  crearon datos ficticios mediante SQL en la base local. El worker quedó
  detenido; los recursos temporales de pruebas ya fueron retirados.
- La clave de Storage y el .env de Auth siguen excluidos de Git; JWT y
  enlaces firmados permanecen vacíos en la plantilla versionada. Sin
  cambios preparados en staging, commit, push ni PR automáticos.

El usuario confirmó el 2026-10-28 que las 31 solicitudes de la colección
Postman devolvieron los códigos esperados. Esta confirmación manual se
registra separadamente de las 61 aserciones verificadas automáticamente.
Incluye creación, consulta, edición, no-op, copias, vaciado, paginación y
rechazos por precondiciones, referencias, campos del servidor y permisos.

Después de la confirmación se detuvieron Auth, Personalization y PostgreSQL;
el worker quedó detenido. Se verificó que no quedaran contenedores activos
del proyecto ni escuchas en 8080 o 8082. El volumen PostgreSQL sigue
presente y no se eliminaron datos ni archivos de Storage. Docker Desktop
puede permanecer abierto con su motor Linux.

La revisión final no detectó errores de whitespace en Git. La rama sigue
siendo feat/personalization/design-drafts, sin staging, commit, push ni PR
automáticos. Está lista para revisión y commit manual. Siguen pendientes
Catalog, API comercial de cliente, previews, gRPC y checkout; no se habilita
congelación real ni se establece un mínimo DPI sin decisión del equipo.
No registrar aquí tokens, contraseñas ni respuestas con enlaces firmados.
