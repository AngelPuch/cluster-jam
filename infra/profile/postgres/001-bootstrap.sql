\set ON_ERROR_STOP on
-- Infrastructure identities only; all domain tables come from versioned TypeORM migrations.
DO $$
DECLARE runtime_password text; migration_password text;
BEGIN
    runtime_password := rtrim(pg_read_file('/run/secrets/profile_db_password'), E'\r\n');
    migration_password := rtrim(pg_read_file('/run/secrets/profile_db_migration_password'), E'\r\n');
    IF btrim(runtime_password) = '' OR btrim(migration_password) = '' THEN
        RAISE EXCEPTION 'Profile database secret is empty';
    END IF;
    EXECUTE format('CREATE ROLE app_profile LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', runtime_password);
    EXECUTE format('CREATE ROLE migrator_profile LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', migration_password);
END $$;
ALTER DATABASE profile_db OWNER TO migrator_profile;
REVOKE ALL ON DATABASE profile_db FROM PUBLIC;
GRANT CONNECT ON DATABASE profile_db TO app_profile;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_profile;
