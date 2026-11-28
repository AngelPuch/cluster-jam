\set ON_ERROR_STOP on
\getenv application_password DB_PASSWORD
\getenv migration_password PAYMENTS_MIGRATION_PASSWORD

BEGIN;
SELECT current_database() AS payments_database \gset
CREATE ROLE migrator_pagos LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE app_pagos LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS PASSWORD :'application_password';
REVOKE ALL ON DATABASE :"payments_database" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"payments_database" TO migrator_pagos, app_pagos;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA app AUTHORIZATION migrator_pagos;
GRANT USAGE ON SCHEMA app TO app_pagos;
ALTER ROLE app_pagos IN DATABASE :"payments_database" SET statement_timeout = '3s';
COMMIT;
