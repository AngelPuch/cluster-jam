package com.clusterjam.catalog.infrastructure.database.models;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProducts.Change;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Immutable
@Table(schema = "app", name = "auditoria_local")
public class CatalogAuditEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "actor_ref", nullable = false)
    private UUID actor;

    @Column(name = "accion", nullable = false, length = 40)
    private String action;

    @Column(name = "recurso", nullable = false, length = 40)
    private String resource;

    @Column(name = "recurso_id", nullable = false)
    private UUID resourceId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "detalle", nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> details;

    protected CatalogAuditEntity() {
    }

    public CatalogAuditEntity(UUID actor, UUID photoId, String action, int version, boolean active) {
        this.actor = actor;
        this.action = action;
        resource = "PHOTO";
        resourceId = photoId;
        details = Map.of("version", version, "active", active);
    }

    public CatalogAuditEntity(Change change) {
        actor = change.actor();
        action = change.previousStatus() == null ? "CREATE" : "UPDATE";
        resource = change.resource().name();
        resourceId = change.resourceId();

        details = new LinkedHashMap<>();
        details.put("status", change.status().name());
        details.put("version", change.version());
        if (change.previousStatus() != null) {
            details.put("previousStatus", change.previousStatus().name());
        }
        if (change.previousPrice() != null) {
            details.put("previousBasePriceCents", change.previousPrice());
        }
        if (change.price() != null) {
            details.put("basePriceCents", change.price());
        }
    }
}
