# Persistencia y migraciones de Personalization

Fuente: `BD-Cluster-JAM.pdf`, versión 1.1, secciones 7, 11 y 12;
`Proyecto-Cluster-JAM.docx` y `Estandar-codificacion.docx`. Estos documentos
definen el alcance; este archivo registra decisiones de implementación.

La base es `personalizacion_db`, host `db-personalizacion`, usuario
`app_personalizacion`, esquema `app`. Docker inicializa la base, el rol y
el esquema vacío. Alembic crea y evoluciona todas las tablas del dominio.
No se requiere instalar PostgreSQL ni crear tablas manualmente en Windows.

## Correspondencia ORM

Los atributos Python están en inglés; todos los nombres SQL se declaran
explícitamente con `mapped_column`, incluso cuando coinciden con Python.
Los modelos pertenecen exclusivamente a infraestructura. Las conexiones
SQLAlchemy usan `search_path=pg_catalog`: todas las tablas se acceden con
su esquema `app` explícito y la reflexión de Alembic conserva los nombres
completos de tablas y FK. No se cambia el search_path del rol PostgreSQL
ni se conceden permisos sobre `public`.

| Modelo | Tabla SQL |
| --- | --- |
| `FileModel` | `archivo` |
| `PrintModel` | `estampado` |
| `PrintVersionModel` | `estampado_version` |
| `TemplateVersionModel` | `plantilla_version` |
| `ZoneModel` | `zona` |
| `ZoneSizeModel` | `tamano_zona` |
| `DesignModel` | `diseno` |
| `ApplicationModel` | `aplicacion` |
| `AuditEntryModel` | `auditoria_local` |

La única tabla adicional es `app.alembic_version`, el historial técnico
de Alembic. No se incorporan tablas de usuarios, catálogo, pedidos, inbox
ni outbox sin un contrato que las requiera. Las referencias externas son
UUID, salvo `talla_ref` que es `smallint`; no tienen FK hacia otros servicios.

## Tipos e integridad

Los identificadores son UUID. Los genera Python mediante `uuid4`, sin
extensiones PostgreSQL adicionales. Versiones, números y píxeles son
`integer`; recargos y bytes son `bigint`. Los importes representan centavos
de MXN. No se agrega una columna de moneda que el modelo no contiene.

El documento no fija el tipo ni la precisión de las medidas `_mm`.
Se usa PostgreSQL `NUMERIC` sin escala impuesta y Python `Decimal`, para
evitar redondeo binario y no inventar un límite de precisión del negocio.
Se rechazan medidas no positivas, coordenadas negativas y los valores
especiales NaN e infinito. Las conversiones a centímetros pertenecen al
contrato de presentación futuro.

Se conservan las columnas, nulabilidad, claves únicas y relaciones de la
sección 7. La FK compuesta `(tamano_id, zona_id)` referencia
`tamano_zona(id, zona_id)`; la clave única auxiliar de ese par permite
aplicarla. Una restricción exige exactamente uno de
`estampado_version_id` y `archivo_usuario_id`. No hay borrados en cascada.

También se comprueban números/versiones positivos, recargos no negativos,
píxeles y bytes positivos, MIME PNG/JPEG, SHA-256 hexadecimal y textos
obligatorios no vacíos. Las caras admitidas son FRENTE y ESPALDA. Los
estados y usos permanecen como texto, sin inventar enumeraciones que los
documentos no especifican. Los límites de carga, decodificación, cantidad
de píxeles, propiedad y compatibilidad se aplicarán en los casos de uso.

La geometría entre filas, ausencia de superposición, pertenencia de zona
y diseño a una plantilla, costos y edición de un diseño CONGELADO se
implementarán en negocio. Esta migración prepara su persistencia, pero
no afirma haber implementado todavía esos flujos ni los endpoints.

`auditoria_local` conserva actor opcional, acción, recurso, UUID del recurso,
detalle JSONB opcional y fecha `timestamptz` generada en PostgreSQL. Los
casos administrativos guardarán auditoría y cambio en la misma transacción,
sin credenciales ni información sensible en `detalle`.

## Aplicación explícita

Desde la raíz del repositorio, después de preparar secretos y las dos URLs
públicas de Supabase descritas en el README:

```powershell
docker compose -f infra/personalization/compose.yaml --profile tools build personalization-migrate
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm personalization-migrate
docker compose -f infra/personalization/compose.yaml run --rm personalization-migrate python -m personalization.infrastructure.database.migrate check
docker compose -f infra/personalization/compose.yaml run --rm personalization-migrate python -m personalization.infrastructure.database.migrate current
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml up -d --wait personalization
```

El comando `upgrade` aplica hasta `head`; repetirlo conserva datos y no
recrea tablas. `check` detecta diferencias entre el esquema y los modelos.
`current` exige que la revisión instalada alcance todas las cabezas.
Cada comando usa una transacción y un bloqueo asesor de PostgreSQL para
serializar ejecuciones; las esperas y consultas tienen límites de tiempo.
Se valida la identidad y propiedad del esquema antes de ejecutar DDL.

Los resultados son logs JSON saneados: salida 0 para éxito, 1 para fallo
de migración o acceso y 2 para configuración inválida. La URL de conexión
se construye en memoria a partir del secreto montado y no se guarda en
`alembic.ini` ni en revisiones. La imagen instala las revisiones dentro
del paquete; el comando funciona independientemente de su directorio.

Ejecutar migraciones una vez antes de desplegar réplicas. La API no llama
a `create_all`, no ejecuta Alembic ni modifica el esquema al arrancar.
Sin la revisión esperada, `/health/live` devuelve 200 y `/health/ready`
devuelve 503; la aplicación de la migración permite recuperar readiness
sin reiniciar el proceso. La revisión esperada se actualiza junto con
cada migración y se verifica contra la única cabeza de Alembic.

## Cambios futuros y reversión

No editar una revisión ya fusionada/aplicada. Crear otra revisión, revisar
el SQL y conservar compatibilidad con la versión anterior durante el
despliegue. `alembic.ini` permite usar las herramientas de Alembic desde
la carpeta del servicio; la ejecución de despliegue usa el comando del
paquete con bloqueo y logs saneados.

La revisión inicial implementa `downgrade()` en orden inverso a las FK.
Al volver a `base` se eliminan las nueve tablas y se conserva vacía la
tabla de versión. Esa reversión pierde datos y se prueba únicamente en
el proyecto desechable. En una instalación con datos, conservar respaldo,
detener escrituras y preparar una migración correctiva o restauración
verificada; cambiar solamente la imagen no revierte el esquema.

## Verificación real

```powershell
py -3.14 infra/personalization/verify_stack.py
```

El verificador crea su propio proyecto y volumen temporales. Arranca la
API antes de migrar, exige readiness 503 y ejecuta las pruebas contra
PostgreSQL real con el usuario de aplicación. Se prueban instalación,
reversión a base y reaplicación; ausencia de diferencias con los modelos;
restricciones, FK compuesta, unicidad, Decimal/bigint, auditoría, conservación
de datos al repetir upgrade y detección de una revisión desactualizada.

La suite de integración rechaza cualquier esquema `app` que ya contenga
tablas antes de comenzar. No ejecutar `personalization-db-test` contra la
base de desarrollo: usar siempre `verify_stack.py`, que proporciona el
entorno desechable. Las pruebas normales omiten estos casos cuando no se
activa el entorno de integración; la CI los ejecuta con Docker.

Las imágenes de producción contienen las revisiones y Alembic, pero no
pytest ni las pruebas. La etapa `integration` conserva las herramientas
solo para QA. La imagen de ejecución continúa como UID/GID 10001 y con
raíz de solo lectura. Los recursos temporales se retiran al terminar.
