package com.clusterjam.catalog.infrastructure.database.models;

import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Objects;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
@Table(schema = "app", name = "foto_producto")
public class CatalogPhotoEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "producto_id", nullable = false, updatable = false)
    private UUID productId;

    @Column(name = "color_id", nullable = false, updatable = false)
    private short colorId;

    @Column(name = "cara", nullable = false, updatable = false, columnDefinition = "text")
    private String side;

    @Column(nullable = false, columnDefinition = "text")
    private String bucket;

    @Column(name = "objeto_clave", nullable = false, columnDefinition = "text")
    private String original;

    @Column(name = "miniatura_objeto_clave", nullable = false, columnDefinition = "text")
    private String thumbnail;

    @Column(name = "activo", nullable = false)
    private boolean active;

    @Version
    @Column(nullable = false)
    private Integer version;

    @Column(name = "actualizado_en", insertable = false)
    private java.time.Instant updatedAt;

    protected CatalogPhotoEntity() {
    }

    public CatalogPhotoEntity(Slot slot, Objects objects) {
        productId = slot.productId();
        colorId = (short) slot.colorId();
        side = slot.side() == Side.FRONT ? "FRENTE" : "ESPALDA";
        replace(objects);
    }

    public void replace(Objects objects) {
        bucket = objects.bucket();
        original = objects.original();
        thumbnail = objects.thumbnail();
        active = true;
        updatedAt = java.time.Instant.now();
    }

    public void retire() {
        active = false;
        updatedAt = java.time.Instant.now();
    }

    public Photo toPhoto() {
        Side face = side.equals("FRENTE") ? Side.FRONT : Side.BACK;
        return new Photo(id, new Slot(productId, colorId, face), bucket, original, thumbnail, active, version);
    }
}
