package com.clusterjam.catalog.infrastructure.database.repositories;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.infrastructure.database.models.CatalogPhotoTaskEntity;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

public interface CatalogPhotoTaskJpaRepository extends JpaRepository<CatalogPhotoTaskEntity, UUID> {

    List<CatalogPhotoTaskEntity> findByCleanupAfterLessThanEqualOrderByCleanupAfterAsc(Instant now, Limit limit);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<CatalogPhotoTaskEntity> findLockedById(UUID id);
}
