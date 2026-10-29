# Previews privadas de diseños administrativos

Rama: `feat/personalization/design-previews`, desde main tras PR #40.

## Alcance

El worker genera PNG de frente y espalda a partir de las dimensiones físicas
de la plantilla y las aplicaciones guardadas. Sin contrato ni imágenes base
de Catalog, son lienzos esquemáticos blancos con contornos grises de zonas:
`representation=SCHEMATIC_TEMPLATE`, `approximate=true`,
`catalogCompatibilityVerified=false`, `checkoutReady=false`.
No se presentan como fotografías de prenda ni instrucciones de fabricación.
Siguen restringidos a borradores administrativos propios. Catalog, API de
cliente comercial, publicación de plantillas y checkout continúan pendientes.

Se reutilizan `archivo`, `diseno` y `auditoria_local` creadas mediante Alembic
en `0001_personalization`. No hay cambios de esquema, tablas de trabajos ni
DDL al arrancar. Las referencias faltantes del diseño forman la cola durable;
no se introduce una cola solo en memoria ni una dependencia nueva de Auth.

## Geometría, imágenes y límites

Ambas caras usan una escala común: 1024 / mayor dimensión de ambas caras,
en px/mm. Cada lienzo tiene al menos un píxel por eje y un máximo de 1024.
El núcleo de Fraction/Decimal anterior centra y ajusta las imágenes dentro
del tamaño permitido, conserva proporción y no superposición; al rasterizar
se redondean los bordes al píxel más cercano. Las posiciones resultantes
son aproximadas: un elemento menor de un píxel puede desaparecer. No hay
recorte manual ni estiramiento solicitado desde la API.

El worker revalida geometría, original PNG/JPEG, dimensiones, bytes y hash;
aplica orientación EXIF antes de ajustar. Compone alpha sobre blanco y no
conserva EXIF, comentarios ni otros metadatos en el PNG final. Agrupa las
aplicaciones por archivo original: cada fuente se descarga/decodifica una
vez por render, incluso usada en ambas caras. Procesa una fuente a la vez,
manteniendo dos lienzos acotados. No altera originales ni sus versiones.

El umbral mínimo DPI sigue pendiente de decisión del equipo. Este incremento
no inventa uno ni afirma calidad suficiente. El endpoint de análisis previo
continúa calculando resolución efectiva y avisos, con minimumDpi=null y
THRESHOLD_NOT_CONFIGURED hasta configurar MIN_PRINT_DPI. La consulta de
previews devuelve metadatos locales y no repite ese análisis ni decodifica
imágenes en HTTP; la colección consulta el diagnóstico por separado.

## Intenciones, recuperación y concurrencia

Las claves UUIDv5 dependen de diseño, revisión de entrada, cara y namespace
del renderer V1. `archivo.uso=PREVIA_V1:<designId>:<inputRevision>:<side>`
identifica la relación sin columnas nuevas. El propietario del derivado es
el del diseño, incluso si la fuente pertenece a otra cuenta y fue elegida
bajo el permiso administrativo existente.

Antes de cargar se confirma una intención PENDIENTE_CARGA con hash, tamaño,
MIME y dimensiones exactas. Storage usa claves UUID y create-only; nunca
sobrescribe un objeto. Si se pierde la respuesta de una carga, el siguiente
intento verifica los bytes existentes y confirma DISPONIBLE. Si el objeto
falta, vuelve a renderizar y exige metadatos idénticos antes de cargar.
Las imágenes disponibles se reutilizan sin nuevas cargas. El adaptador de
intenciones derivadas se comparte con miniaturas, conservando sus contratos.

Un advisory lock de sesión excluye workers competidores para el mismo
diseño. Se confirma antes del I/O; no mantiene una transacción SQL abierta
durante Storage/Pillow. La conexión física se cierra al terminar o fallar,
liberando el lock. Los lotes y el recorrido UUID están acotados y avanzan
ante fallas para no bloquear otros diseños. Los errores se registran como
códigos en JSON con traza, sin bytes, credenciales o enlaces firmados.

Solo después de tener ambos archivos DISPONIBLE se bloquea brevemente la
raíz y se compara la revisión. Si cambió o se congeló el diseño, las previews
viejas no se asocian. Los dos FK y DESIGN_PREVIEWS_GENERATED se confirman
juntos; una falla de auditoría revierte ambos FK. Repetir la asociación no
duplica la auditoría. Los archivos ya subidos quedan privados y recuperables.

Publicar previews no incrementa la versión del contenido, pero sí cambia el
ETag de la representación del diseño. Obtener un GET actualizado antes de
editar con If-Match. La revisión de entrada excluye los FK de preview para
que el worker no invalide su propio resultado. PUT significativo conserva
la regla anterior: versión nueva y ambos FK vacíos; el worker procesa esa
revisión con otras claves. Las copias obtienen sus propios archivos y UUID.

Los derivados de revisiones anteriores o renders obsoletos no se borran ni
se sobrescriben. Permanecen privados; su limpieza/reconciliación de retención
no se implementa aquí. Los enlaces emitidos antes de editar pueden servir
la imagen histórica hasta su expiración; nunca representan una autorización
de checkout. Cambiar el algoritmo/entorno que afecte bytes exige otro
namespace/versión de renderer; no reutilizar V1 con metadatos incompatibles.

## REST y acceso

| Método y ruta | Resultado |
| --- | --- |
| GET /api/v1/admin/design-drafts/{designId}/previews | 200, PENDING o READY |
| POST /api/v1/admin/design-drafts/{designId}/previews/{side}/download-urls | 201, enlace temporal |

side acepta FRONT o BACK. La consulta devuelve designId/designVersion,
representación aproximada y metadatos front/back. PENDING puede devolver
null, añade Retry-After: 10 como sugerencia, y exige esperar al worker.
READY contiene ambos PNG. No descarga imágenes, contacta Storage ni genera
archivos para responder al GET. Ambos endpoints llevan no-store y la
consulta devuelve el ETag vigente del diseño.

Sin JWT: 401; cliente u otro administrador no propietario: 403; inexistencia:
404; cara inválida: 422. Intentar firmar una preview faltante devuelve 409
FILE_NOT_READY. El enlace se genera solo tras verificar propiedad, relación
y estado de archivo, y que el bucket siga privado. Usa el TTL ya configurado
(60 s por defecto, 1–300). El GET del enlace firmado no lleva JWT: el enlace
es la capacidad temporal. No compartirlo ni guardarlo en Git.

La API /files sigue limitada a originales: no consulta ni firma derivados.
El paso 15 comprueba que un ID de preview recibe 404 FILE_NOT_FOUND por esa
ruta. Las previews solo se exponen mediante su ruta propia y la identidad
administradora propietaria. El permiso administrativo existente para los
originales de otras cuentas no cambia.

## Operación

Compose ahora ejecuta `personalization.interfaces.workers.images`, que procesa
miniaturas y previews en colas independientes. Una falla de miniaturas no
impide intentar el lote de previews. El comando anterior thumbnails sigue
disponible para compatibilidad. HTTP y worker son procesos separados.

Desde la raíz, con los secretos locales ya preparados:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml --profile images up -d --build --wait personalization personalization-worker
```

Un recorrido acotado, útil para diagnóstico:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile images run --rm --no-deps personalization-worker python -m personalization.interfaces.workers.images --once
```

--once procesa un lote por cola; ejecutar nuevamente si hay más candidatos.
Para inspeccionar fallas sin ver secretos:

```powershell
docker compose -f infra/personalization/compose.yaml --profile images logs --tail 50 personalization-worker
```

La primera ejecución también procesa borradores anteriores con FK vacíos.
No inicia migraciones automáticamente; readiness sigue exigiendo el esquema
versionado. PostgreSQL permanece sin puerto publicado.

## Postman

1. Importar `contracts/postman/personalization/design-previews.postman_collection.json`.
2. Conservar tu entorno actual: baseUrl=http://127.0.0.1:8082, printId existente,
   adminAccessToken y accessToken cliente vigentes. Las variables preview*
   las crean los scripts. No importar la plantilla vacía sobre tus valores.
3. Con Auth, Personalization, PostgreSQL y el worker encendidos, abrir
   Collection Runner: una iteración y Add a delay of = 1000 ms. Mantener el
   orden 01–26. No subir archivos ni modificar cuerpos.
4. 04, 14 y 19 se repiten hasta READY, con máximo de 60 consultas por paso.
   El número de envíos puede superar 26. Si no termina, falla la comprobación
   y el flujo se detiene: revisar el worker y volver a ejecutar desde 01.
5. Si usas Send manualmente, repetir esos tres pasos hasta ver READY antes
   de continuar. setNextRequest solo controla Collection Runner/CLI/Newman,
   no encadena solicitudes pulsando Send.
6. 07 y 09 muestran frente/espalda; 17 muestra la espalda con zona vacía tras
   retirar su aplicación. Son esquemas, sin fotografía de prenda. Los GET
   firmados ya tienen No Auth: no cambiarlo a Bearer.
7. Con Send, un 200 con PENDING no permite avanzar. Repetir 04 hasta READY
   y ejecutar 05; 11 renueva el ETag listo antes de 12. Los pasos 06/08
   también guardan los ID de archivo. 12 y 15 verifican sus variables antes
   de enviar, con un mensaje que indica qué preparación falta. La colección
   rev. 2 limpia valores de recorridos anteriores al crear el diseño.
8. Verificar códigos y Tests/Post-response, archivos nuevos tras edición,
   copia independiente y conservación de originales/históricos.

| Solicitudes | HTTP esperado |
| --- | --- |
| 01, 04–05, 07, 09–12, 14, 17, 19, 26 | 200 |
| 02–03, 06, 08, 16, 18 | 201 |
| 13 | 412 |
| 20, 24 | 403 |
| 21, 25 | 401 |
| 15, 22 | 404 |
| 23 | 422 |

Cada recorrido completo crea una plantilla QA inactiva, dos diseños propios
y seis archivos derivados (dos para cada revisión y dos para la copia),
además de los borradores anteriores que todavía necesitaran procesamiento.
No hay un 409 manual fijo porque el worker puede terminar antes de solicitar
el enlace; esa condición y el estado PENDING se prueban automáticamente.

Referencias de Postman para el sondeo y la pausa entre solicitudes:
[control del flujo](https://learning.postman.com/docs/tests-and-scripts/running-collections/building-workflows/),
[Collection Runner](https://learning.postman.com/docs/tests-and-scripts/running-collections/intro-to-collection-runs/).

## GitHub Flow

La rama ya se creó desde main actualizado:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/personalization/design-previews
```

Después de confirmar Postman y detener los servicios:

```powershell
git status
git diff --check
git add services/personalizationService infra/personalization contracts/openapi/personalization contracts/postman/personalization
git diff --cached --stat
git commit -m "feat(personalization): generate private design previews"
git push -u origin feat/personalization/design-previews
```

PR hacia main con el mismo título. Revisar privacidad/propiedad, esquemas
aproximados, orientación/proporciones, procesamiento fuera de HTTP, fencing,
recuperación, auditoría atómica, preservación de originales y CI en verde.
Fusionar con Squash and merge y después:

```powershell
git switch main
git pull --ff-only origin main
git status
```

No se realiza staging, commit, push ni PR automáticamente. Siguen pendientes
Catalog, API comercial de cliente, contrato gRPC y checkout. El umbral DPI
lo definirá el equipo.

## Evidencia

Validación automatizada del 2026-10-28, hora local:

- 629 pruebas generales aprobadas en Windows y Linux, con 80.29 % de
  cobertura de líneas/ramas y mínimo configurado de 70 %. Incluyen PNG/JPEG,
  EXIF 1–8, metadata, escala común, alpha, fuentes repetidas, lienzos sin
  aplicaciones, recuperación, carreras, permisos y funcionamiento de las
  dos colas aunque falle una. Ruff y formato aprobados; mypy estricto en
  228 archivos y construcción de paquete aprobados.
- 117 pruebas aprobadas con PostgreSQL real. Las nueve nuevas verifican
  recuperación antes/después de carga y publicación, rollback de auditoría,
  asociación atómica e idempotente, edición concurrente, locks, CONGELADO,
  parejas incompletas y HTTP con JWT firmado. La refactorización de
  intenciones conserva las pruebas previas de archivos y miniaturas.
- Docker verificó migraciones explícitas, reversión/reaplicación, usuario
  sin privilegios, red privada y puerto de BD sin publicar, persistencia y
  recuperación de readiness. Se retiró solo el proyecto temporal
  personalization-verify-280dbdf79293 con sus recursos desechables.
- Se revisaron las variables, cuerpos JSON, scripts y placeholders vacíos
  de la colección. Un recorrido con adaptadores aislados y ejecución de
  scripts completó sus 26 pasos, 29 envíos al repetir cada sondeo y 62
  aserciones. Ejercitó PENDING→READY con el renderer real y confirmó que
  los GET de PNG firmados no llevan JWT. No sustituye cuentas reales ni
  la ejecución manual de Postman.
- El worker local procesó los dos borradores de la rama anterior sin
  errores: cuatro PNG DISPONIBLE, vinculados a las revisiones correctas,
  con dos auditorías de generación. Una comprobación de operador verificó
  contra Supabase los cuatro hashes/longitudes, PNG, dimensiones esperadas,
  ausencia de metadatos y bucket privado. La consulta de comprobación fue
  READ ONLY y cerró su transacción antes de leer Storage; no creó diseños.
- Auth y Personalization respondieron 200 en live/ready. Los contratos
  nuevos aparecen en OpenAPI y ambas rutas rechazan el acceso anónimo con
  401 RFC 9457. Personalization escucha en 127.0.0.1:8082 y Auth en 8080.
  El worker images y PostgreSQL se encendieron para la prueba manual.
- La revisión de Git no detectó problemas de whitespace. El .env de Auth
  y la clave de Storage siguen ignorados; los JWT y enlaces de la plantilla
  Postman siguen vacíos. No hay staging, commit, push ni PR automáticos.

El usuario confirmó que los 26 pasos de la colección corregida devolvieron
los resultados esperados. Después se detuvieron Auth, Personalization,
worker y PostgreSQL, conservando volumen, originales y derivados privados. Catalog, API
comercial de cliente, gRPC y checkout siguen pendientes; no se establece
un umbral DPI ni se habilita publicación/congelación comercial.


### Revisión del primer recorrido manual

El usuario informó que envió las solicitudes con Send y obtuvo 412 en 12
y 422 en 15. Se reprodujo ese patrón al conservar el ETag de PENDING y al
consultar /files con un identificador inválido. Publicar previews cambia el
ETag; 200 PENDING no completa la preparación ni guarda los ID de READY.
La API conserva ambos rechazos: no se elimina If-Match ni se usa wildcard.

La colección rev. 2 captura/renueva explícitamente los valores listos y
comprueba los requisitos de 12/15. La prueba HTTP con JWT firmado cubre
ahora el 412 tras publicar y la diferencia entre UUID inválido (422) y UUID
válido de un derivado fuera de /files (404). El primer recorrido no se
registra como aprobado; la confirmación posterior corresponde a la
colección corregida.

La colección rev. 2 completó nuevamente los 26 pasos, 29 envíos y 64
aserciones con adaptadores aislados. Se comprobaron también los avisos de
preparación de 12/15; las dos pruebas HTTP con JWT firmado pasaron. Ruff y
mypy estricto siguen aprobados. La repetición manual fue confirmada.


### Cierre de la validación manual

El 2026-10-28 (hora local), el usuario confirmó que todos los pasos de la
colección rev. 2 dieron los resultados esperados, cerrando las observaciones
de 12 y 15. Esta confirmación se registra separadamente de las 64 aserciones
automatizadas y de las pruebas HTTP con JWT firmado.

Se detuvieron primero el worker y después Personalization, PostgreSQL y
Auth. Se comprobó que no quedaran contenedores activos del proyecto ni
escuchas en 8080/8082. El volumen PostgreSQL permanece presente. No se
eliminaron originales ni derivados privados de Supabase. Docker Desktop
puede permanecer abierto con su motor Linux.

La rama feat/personalization/design-previews queda lista para revisión y
commit manual. No se realizó staging, commit, push ni PR automáticamente.
Catalog, API comercial de cliente, gRPC y checkout siguen pendientes;
el umbral DPI continúa a cargo del equipo.
