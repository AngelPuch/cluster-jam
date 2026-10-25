\set ON_ERROR_STOP on

-- Bootstrap identities and the schema; domain tables use Alembic.
DO $$
DECLARE
    application_password text;
BEGIN
    application_password := rtrim(
        pg_read_file('/run/secrets/personalization_db_password'),
        E'\r\n'
    );
    IF application_password IS NULL
        OR btrim(application_password) = '' THEN
        RAISE EXCEPTION 'The application database secret is empty';
    END IF;
    EXECUTE format(
        'CREATE ROLE app_personalizacion LOGIN PASSWORD %L '
        'NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION '
        'NOBYPASSRLS',
        application_password
    );
END;
$$;

REVOKE ALL ON DATABASE personalizacion_db FROM PUBLIC;
GRANT CONNECT ON DATABASE personalizacion_db TO app_personalizacion;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA app AUTHORIZATION app_personalizacion;
ALTER ROLE app_personalizacion IN DATABASE personalizacion_db
    SET search_path TO app, pg_catalog;
