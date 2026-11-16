package com.clusterjam.catalog.infrastructure.database.models;

import java.time.Instant;
import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;

@MappedSuperclass
abstract class CatalogVersionedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    protected UUID id;

    @Version
    @Column(nullable = false)
    protected Integer version;

    @Convert(converter = CatalogStatusConverter.class)
    @Column(name = "estado", nullable = false, columnDefinition = "text")
    protected Status status = Status.DRAFT;

    @Column(name = "actualizado_en", nullable = false, insertable = false)
    private Instant updatedAt;

    protected void markEdited(Status nextStatus) {
        status = nextStatus;
        Instant now = Instant.now();
        updatedAt = updatedAt == null || now.isAfter(updatedAt) ? now : updatedAt.plusNanos(1_000);
    }
}
