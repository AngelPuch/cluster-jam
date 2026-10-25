# Configuración de Supabase para Auth Service

## Política de autenticación

| Parámetro                     | Valor acordado           | Configuración local                |
| ----------------------------- | ------------------------ | ---------------------------------- |
| Longitud mínima de contraseña | 8 caracteres             | `auth.minimum_password_length = 8` |
| Longitud del OTP de correo    | 6 dígitos                | `auth.email.otp_length = 6`        |
| Vigencia del OTP de correo    | 600 segundos: 10 minutos | `auth.email.otp_expiry = 600`      |
| Vigencia del access token     | 900 segundos: 15 minutos | `auth.jwt_expiry = 900`            |

## Configuración local y Cloud

- `config.toml` configura la instancia local de Supabase. Los puertos, el correo de pruebas y los límites locales de envío son ajustes de desarrollo.
- Las plantillas de confirmación y recuperación están en `templates/`; usan `{{ .Token }}`. En Cloud se configuran en las plantillas de correo del Dashboard.
- Las migraciones versionan la outbox y la protección de roles. No establecen la política de contraseña, OTP o duración del JWT.
- SMTP, claves y contraseñas de conexiones se administran fuera del repositorio. Los límites y el proveedor de correo de Cloud se conservan según su configuración efectiva; no se deducen de los valores locales.

## Renovación y cierre de sesión

Auth devuelve `expiresIn` a partir de la respuesta del proveedor. El cliente renueva mediante `POST /api/v1/session-renewals`, enviando el refresh token vigente y conservando el nuevo par de tokens.

El vencimiento de un access token no obliga a iniciar sesión de nuevo si la renovación sigue siendo válida. El cliente debe ejecutar esa renovación; Auth no la realiza automáticamente en segundo plano.

El logout usa `scope=local`. Los JWT ya emitidos pueden seguir siendo aceptados hasta su `exp` por las APIs que verifican únicamente el token. Cambiar la duración no modifica el `exp` de los tokens anteriores.

Tras cambiar un rol, se obtiene un token nuevo mediante renovación o nuevo login para actualizar sus claims. La consulta de identidad actual no sustituye ese token en otras APIs.

## Asignación administrativa

`operations/assign-single-admin.sql` es una plantilla operativa. Antes de ejecutarla, se reemplaza el `null` de `target_id uuid := null;` por el UUID de una cuenta confirmada. Con `null`, la operación se detiene sin asignar un administrador.

La operación conserva la restricción de administrador único. No es necesario volver a ejecutarla cuando el administrador ya está asignado.

## Publicador de outbox

El proceso utiliza una cuenta SQL dedicada con el rol `auth_outbox_publisher`, limitado a lectura y actualización de las columnas técnicas autorizadas. No necesita permisos administrativos ni acceso a los datos de Profile. En entornos alojados se usa TLS con verificación del certificado.

### Fallos y reproceso

Un evento se considera publicado cuando `publicado_en` tiene valor. Si sigue sin publicar y `bloqueado_en` tiene valor, está apartado por `REGISTRATION_EVENT_INVALID` y no se selecciona automáticamente. Si ambas columnas están vacías, permanece pendiente y puede tener un próximo intento programado.

Los fallos temporales del broker conservan el reintento progresivo. Un mensaje no enrutable también permanece pendiente; debe revisarse el binding de la cola. `ultimo_error_codigo` guarda únicamente un código técnico permitido, sin mensajes crudos ni datos del evento.

El bloqueo genera `auth.outbox.event.blocked` con el `event_id`. El evento y sus intentos se conservan; no se marca como publicado ni se elimina. La cuarentena técnica pertenece a la outbox; no sustituye la DLQ del consumidor de Profile.

Tras corregir la causa, se usa `operations/requeue-auth-outbox.sql` con el UUID concreto del evento. La operación solo reabre eventos bloqueados y no publicados, conservando su ID, datos e intentos. El publicador vuelve a validar el contenido; si sigue siendo inválido, lo bloquea de nuevo. El script no repara el contenido automáticamente.

Aplicar la migración `20261025190000_quarantine_invalid_auth_outbox.sql` antes de ejecutar esta versión del publicador. Conserva las filas anteriores y añade las dos columnas técnicas, sus permisos y el índice de pendientes elegibles.
