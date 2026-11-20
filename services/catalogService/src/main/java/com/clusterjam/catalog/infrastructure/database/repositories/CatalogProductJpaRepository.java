package com.clusterjam.catalog.infrastructure.database.repositories;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.infrastructure.database.models.CatalogProductEntity;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;

public interface CatalogProductJpaRepository extends JpaRepository<CatalogProductEntity, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<CatalogProductEntity> findLockedById(UUID id);

    List<CatalogProductEntity> findAllByOrderByIdAsc(Limit limit);

    List<CatalogProductEntity> findByIdGreaterThanOrderByIdAsc(UUID after, Limit limit);
}
