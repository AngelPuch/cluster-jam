package com.clusterjam.catalog.infrastructure.database;

import com.clusterjam.catalog.application.ports.ReadinessProbe;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcOperations;

public final class PostgresReadinessProbe implements ReadinessProbe {

    private static final String CHECK_SCHEMA = """
        SELECT current_database() = 'catalogo_db'
            AND bool_and(success AND type = 'SQL')
            AND array_agg(version::text ORDER BY installed_rank) = ARRAY['1', '2', '3', '4', '5']
            AND array_agg(script::text ORDER BY installed_rank) = ARRAY[
                'V1__create_catalog_schema.sql', 'V2__seed_catalog_reference_data.sql',
                'V3__add_catalog_admin_audit.sql', 'V4__grant_catalog_orm_inserts.sql',
                'V5__add_photo_cleanup.sql'
            ]
        FROM app.flyway_schema_history
        """;

    private final JdbcOperations jdbc;

    public PostgresReadinessProbe(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean isAvailable() {
        try {
            return Boolean.TRUE.equals(jdbc.queryForObject(CHECK_SCHEMA, Boolean.class));
        } catch (DataAccessException unavailable) {
            return false;
        }
    }
}
