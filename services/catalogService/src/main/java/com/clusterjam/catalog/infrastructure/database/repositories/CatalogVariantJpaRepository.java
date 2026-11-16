package com.clusterjam.catalog.infrastructure.database.repositories;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.infrastructure.database.models.CatalogVariantEntity;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogVariantJpaRepository extends JpaRepository<CatalogVariantEntity, UUID> {

    List<CatalogVariantEntity> findByProductIdOrderByIdAsc(UUID productId, Limit limit);

    List<CatalogVariantEntity> findByProductIdAndIdGreaterThanOrderByIdAsc(UUID productId, UUID after, Limit limit);

    Optional<CatalogVariantEntity> findByProductIdAndId(UUID productId, UUID id);
}
