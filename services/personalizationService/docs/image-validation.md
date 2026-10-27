# Validación de imágenes originales

Este incremento prepara RF10 y RNF01: originales PNG/JPEG de hasta
10 000 000 bytes, formato real, decodificación y límites de dimensiones.
No añade operaciones REST de negocio todavía. La integración con Supabase
Storage y la persistencia del archivo se implementarán en otro incremento.

## Capas y resultado

`ValidateImageService` pertenece a aplicación. Recibe un `ImageSourcePort`
de lectura binaria y un MIME declarado opcional; delega la inspección al
puerto `ImageInspectorPort`. El adaptador `PillowImageInspector` vive en
infraestructura. El servicio se compone una vez por aplicación y se puede
resolver desde HTTP mediante `get_image_validator`. La validación es
sincrónica; la futura ruta usará el pool de hilos de FastAPI y límites
de concurrencia para no bloquear el loop ni acumular decodificaciones.

El resultado inmutable `ValidatedImage` contiene UUID v4, clave de objeto,
MIME real, bytes, ancho, alto, SHA-256 y los bytes originales. El UUID se
genera después de validar; la clave es `<uuid>.png` o `<uuid>.jpg`, sin
aceptar nombres ni rutas del cliente. El hash hexadecimal se calcula sobre
el original completo, sin recodificarlo. El cuerpo binario se excluye de
`repr` y no forma parte de un contrato JSON ni de logs.

La clave y el ID aún no corresponden a un objeto guardado ni a una fila de
`archivo`. No se devuelve una URL ni se promete persistencia. El siguiente
caso de uso asignará el propietario desde la identidad verificada y
coordinará Storage y la base de datos.

## Secuencia de validación

1. Leer por bloques de hasta 65 536 bytes, desde la posición actual del
   stream. Se consumen como máximo 10 000 001 bytes para detectar exceso.
   El límite de 10 000 000 es inclusivo y no se puede ampliar por entorno.
   Las lecturas cortas no equivalen a EOF; el servicio no hace seek ni
   cierra el stream, que pertenece al llamador.
2. Rechazar contenido vacío y exigir la firma binaria PNG o JPEG. No se
   infiere el formato a partir del nombre, extensión o MIME enviado.
3. Validar el MIME declarado si es específico. Se permiten `image/png` y
   `image/jpeg`, sin distinguir mayúsculas y admitiendo parámetros MIME.
   Una declaración ausente o `application/octet-stream` obliga igualmente
   a detectar el formato real; cualquier otro tipo o discrepancia se rechaza.
4. Abrir con Pillow restringiendo el decodificador al formato esperado.
   Comprobar ancho, alto y píxeles antes de cargar el buffer de imagen.
   Rechazar originales con más de un frame, incluido APNG animado.
5. Ejecutar `verify()` para la estructura y CRC cuando el formato lo
   permite. Reabrir los mismos bytes inmutables y ejecutar `load()` para
   exigir una decodificación completa; `verify()` solo no basta para JPEG
   ni para un PNG con CRC correcto y datos comprimidos inválidos.
6. Volver a comprobar los metadatos en aplicación, calcular SHA-256 y
   generar el identificador y la clave con sufijo canónico.

Se cierran las imágenes y buffers internos incluso ante rechazo. Los
warnings de descompresión y los UserWarning originados en Pillow se
convierten en errores durante la composición del adaptador y se traducen
a códigos saneados. No se cambian filtros durante cada validación, no se
desactiva `Image.MAX_IMAGE_PIXELS` y no se habilita la lectura de imágenes
truncadas. Las instancias de imagen no se comparten entre peticiones.

## Límites iniciales de recursos

Los documentos no fijan una dimensión máxima numérica. Se adoptan estos
límites iniciales de implementación para acotar la decodificación:

| Variable | Predeterminado | Valores permitidos |
| --- | --- | --- |
| `IMAGE_MAX_WIDTH_PX` | 8192 | 1–8192 |
| `IMAGE_MAX_HEIGHT_PX` | 8192 | 1–8192 |
| `IMAGE_MAX_PIXELS` | 16000000 | 1–16000000 |

Las variables permiten restringir los límites. Aumentar los techos requiere
revisar recursos y carga con mediciones; estos valores no son una garantía
de rendimiento o memoria total bajo concurrencia. Settings rechaza valores
fuera de rango antes de arrancar. Compose transmite las variables con sus
valores predeterminados y los ejemplos `.env.example` las documentan.

Se aceptan imágenes pequeñas válidas. La resolución insuficiente se
advertirá cuando se conozca el tamaño físico de impresión, según RF14;
no se inventa un mínimo de píxeles ni DPI para esta etapa.

Se conservan los originales y sus metadatos; las dimensiones reportadas
son las codificadas. La orientación EXIF, conversión de color, composición
y generación de previews corresponderán al worker. No se recodifica ni
elimina metadata del original al calcular su hash.

## Errores HTTP preparados

Los mappers usan RFC 9457 con los siete campos del proyecto, incluido
`detail` y `traceId`, y `application/problem+json`. No incluyen nombres de
archivo, contenido, rutas internas ni mensajes de Pillow.

| Motivo | Estado | Código |
| --- | --- | --- |
| Cuerpo vacío | 400 | `EMPTY_IMAGE` |
| Exceso de bytes | 413 | `IMAGE_TOO_LARGE` |
| Tipo no admitido | 415 | `UNSUPPORTED_IMAGE_TYPE` |
| MIME en conflicto | 415 | `IMAGE_MIME_MISMATCH` |
| Archivo dañado o no decodificable | 422 | `INVALID_IMAGE` |
| Dimensiones o píxeles excesivos | 422 | `IMAGE_DIMENSIONS_EXCEEDED` |
| Más de un frame | 422 | `ANIMATED_IMAGE_NOT_SUPPORTED` |
| Fallo de lectura del stream | 503 | `IMAGE_READ_FAILED` |

El fallo de lectura representa indisponibilidad del recurso temporal del
servidor, no una firma de imagen inválida. Todos los rechazos usan mensajes
constantes. No se registran binarios, filenames, MIME recibido ni metadata
arbitraria. El contexto HTTP conserva la correlación de trazas existente.

## Pruebas y límites del incremento

La suite genera imágenes pequeñas con Pillow, sin datos de usuarios ni
servicios externos. Incluye PNG RGB/RGBA, paleta, gris y 16 bits; JPEG RGB,
gris, CMYK y progresivo; corrupción CRC y zlib, truncamiento, APNG, firma
falsa, MIME contradictorio, límites inclusivos y lectura acotada. Los
headers de imágenes enormes se construyen sin reservar sus píxeles para
comprobar que se rechazan antes de `load()`.

También se prueba validación concurrente, claves distintas para originales
iguales, SHA-256 estable y ausencia de cambios de los globals del decoder
por petición. Las rutas multipart y de errores usadas por QA se registran
exclusivamente en `test/`; no se publican en el servicio ni en su OpenAPI.
Las pruebas de autenticación existentes siguen comprobando los JWT y roles.

No se han añadido aún subida a Storage, una fila de `archivo`, limpieza de
objetos, URLs firmadas, límites de concurrencia ni el endpoint definitivo.
El límite de este caso de uso se aplica al archivo leído: el proxy, el
cuerpo multipart completo y el spool temporal necesitan límites propios
cuando se incorpore el transporte de carga. Las transformaciones costosas
permanecerán en un worker separado. Postman probará la operación persistente
y su autorización al completar esa integración.

Desde la carpeta del servicio:

```powershell
py -3.14 -m uv run --locked pytest test/images test/e2e/test_image_validation_contract.py
py -3.14 -m uv run --locked pytest --cov --cov-fail-under=70
```

El Dockerfile ejecuta la misma suite antes de construir la imagen final.
`verify_stack.py` comprueba adicionalmente las migraciones y PostgreSQL
reales en un proyecto temporal, conservando la base de desarrollo.


## Matriz de trazabilidad de este incremento

| Requisito | Comprobación implementada | Prueba | Alcance pendiente |
| --- | --- | --- | --- |
| RF10 | Firma real, MIME y decodificación | `test/images/` | Endpoint y almacenamiento |
| RNF01 | Máximo inclusivo de bytes y lectura acotada | `test_byte_limit_is_inclusive`, `test_oversized_stream_stops_before_decoder` | Límite del cuerpo HTTP y proxy |
| RNF01 | Dimensiones y píxeles antes de cargar | `test_large_headers_are_rejected_before_pixel_allocation` | Mediciones bajo carga |
| RNF01 | Claves UUID y hash del original | `test_real_originals_are_decoded_without_modification`, `test_concurrent_validation_does_not_change_decoder_globals` | Storage privado y acceso por propietario |
| RNF03 | Errores saneados y correlación | `test_multipart_rejections_keep_safe_problem_details` | Autorización de la operación persistente |
| RNF09 | Pruebas de reglas y contrato multipart | `test/images/`, `test/e2e/test_image_validation_contract.py` | Flujos completos con Storage |
| RF14 | Original preservado para futuras vistas | `test_real_originals_are_decoded_without_modification` | Worker, proporciones, EXIF y aviso de resolución |

Esta matriz registra partes de requisitos; la cobertura de líneas no
equivale a haber completado RF10, RNF01 o el microservicio completo.
