package com.clusterjam.catalog.infrastructure.database.repositories;

import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.infrastructure.database.models.CatalogPhotoEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogPhotoJpaRepository extends JpaRepository<CatalogPhotoEntity, UUID> {

    Optional<CatalogPhotoEntity> findByProductIdAndColorIdAndSide(UUID productId, short colorId, String side);

    @Query("""
        select count(p) > 0 from CatalogPhotoEntity p where p.active = true and p.bucket = :bucket
        and (p.original in (:original, :thumbnail) or p.thumbnail in (:original, :thumbnail))
        """)
    boolean referenced(@Param("bucket") String bucket, @Param("original") String original,
                       @Param("thumbnail") String thumbnail);
}
