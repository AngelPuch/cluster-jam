\set ON_ERROR_STOP on
\getenv migration_password CATALOG_MIGRATION_PASSWORD
\getenv application_password CATALOG_DB_PASSWORD

BEGIN;

CREATE ROLE migrator_catalogo LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE app_catalogo LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'application_password';

REVOKE ALL ON DATABASE catalogo_db FROM PUBLIC;
GRANT CONNECT ON DATABASE catalogo_db TO migrator_catalogo, app_catalogo;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA app AUTHORIZATION migrator_catalogo;
GRANT USAGE ON SCHEMA app TO app_catalogo;

ALTER ROLE migrator_catalogo IN DATABASE catalogo_db SET search_path = pg_catalog, app;
ALTER ROLE app_catalogo IN DATABASE catalogo_db SET search_path = pg_catalog, app;
ALTER ROLE app_catalogo IN DATABASE catalogo_db SET lock_timeout = '500ms';
ALTER ROLE app_catalogo IN DATABASE catalogo_db SET statement_timeout = '1500ms';

COMMIT;
