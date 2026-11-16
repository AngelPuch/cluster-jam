package com.clusterjam.catalog.infrastructure.database.repositories;

import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.infrastructure.database.models.CatalogProductEntity;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogProductJpaRepository extends JpaRepository<CatalogProductEntity, UUID> {

    List<CatalogProductEntity> findAllByOrderByIdAsc(Limit limit);

    List<CatalogProductEntity> findByIdGreaterThanOrderByIdAsc(UUID after, Limit limit);
}
