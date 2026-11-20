package com.clusterjam.catalog.infrastructure.database.models;

import com.clusterjam.catalog.application.reads.CatalogReadModels;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

public final class CatalogReferenceEntities {

    private CatalogReferenceEntities() {
    }

    @Entity(name = "CatalogType")
    @Immutable
    @Table(schema = "app", name = "tipo_prenda")
    public static class Type {

        @Id
        private short id;
        @Column(name = "nombre", length = 40, nullable = false)
        private String name;

        protected Type() {
        }

        public CatalogReadModels.Type view() {
            return new CatalogReadModels.Type(id, name);
        }
    }

    @Entity(name = "CatalogSize")
    @Immutable
    @Table(schema = "app", name = "talla")
    public static class Size {

        @Id
        private short id;
        @Column(name = "codigo", length = 12, nullable = false)
        private String code;
        @Column(name = "orden", nullable = false)
        private short displayOrder;

        protected Size() {
        }

        public CatalogReadModels.Size view() {
            return new CatalogReadModels.Size(id, code, displayOrder);
        }
    }

    @Entity(name = "CatalogColor")
    @Immutable
    @Table(schema = "app", name = "color")
    public static class Color {

        @Id
        private short id;
        @Column(name = "nombre", length = 40, nullable = false)
        private String name;
        @Column(name = "codigo_hex", length = 7, nullable = false, columnDefinition = "char(7)")
        @JdbcTypeCode(SqlTypes.CHAR)
        private String hex;

        protected Color() {
        }

        public CatalogReadModels.Color view() {
            return new CatalogReadModels.Color(id, name, hex);
        }
    }
}
