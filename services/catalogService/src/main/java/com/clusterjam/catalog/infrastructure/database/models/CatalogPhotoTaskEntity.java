package com.clusterjam.catalog.infrastructure.database.models;

import java.time.Instant;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(schema = "app", name = "foto_limpieza")
public class CatalogPhotoTaskEntity {

    @Id
    private UUID id;

    @Column(nullable = false, columnDefinition = "text")
    private String bucket;

    @Column(name = "objeto_clave", nullable = false, columnDefinition = "text")
    private String original;

    @Column(name = "miniatura_objeto_clave", nullable = false, columnDefinition = "text")
    private String thumbnail;

    @Column(name = "limpiar_despues", nullable = false)
    private Instant cleanupAfter;

    protected CatalogPhotoTaskEntity() {
    }

    public CatalogPhotoTaskEntity(Objects objects, Instant after) {
        id = objects.id();
        bucket = objects.bucket();
        original = objects.original();
        thumbnail = objects.thumbnail();
        cleanupAfter = after;
    }

    public Objects objects() {
        return new Objects(id, bucket, original, thumbnail);
    }

    public boolean due(Instant now) {
        return !cleanupAfter.isAfter(now);
    }
}
