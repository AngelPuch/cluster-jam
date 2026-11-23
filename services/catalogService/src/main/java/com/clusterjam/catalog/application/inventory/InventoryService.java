package com.clusterjam.catalog.application.inventory;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

import com.clusterjam.catalog.application.inventory.InventoryModels.Adjustment;
import com.clusterjam.catalog.application.inventory.InventoryModels.Balance;
import com.clusterjam.catalog.application.inventory.InventoryModels.History;
import com.clusterjam.catalog.application.inventory.InventoryModels.Movement;
import com.clusterjam.catalog.application.inventory.InventoryModels.Result;
import com.clusterjam.catalog.application.ports.InventoryStore;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryStore store;

    public InventoryService(InventoryStore store) {
        this.store = store;
    }

    @Transactional(readOnly = true)
    public Balance balance(UUID variantId) {
        return store.balance(variantId);
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Result adjust(UUID actor, UUID key, UUID variantId, int delta, String reason) {
        if (reason == null || reason.length() > 200 || reason.strip().isEmpty()
            || reason.matches("(?s).*[\\p{Cc}\\p{Cf}].*")
            || delta == 0 || delta < -1_000_000 || delta > 1_000_000) {
            throw new InventoryFailure(InventoryFailure.Reason.INVALID);
        }
        String normalized = reason.strip();
        String canonical = variantId + "\n" + delta + "\n" + normalized;
        return store.adjust(actor, key, hash(canonical), new Adjustment(variantId, delta, normalized));
    }

    @Transactional(readOnly = true)
    public History history(UUID variantId, int afterVersion, int limit) {
        return store.history(variantId, afterVersion, limit);
    }

    @Transactional(readOnly = true)
    public Movement movement(UUID variantId, UUID movementId) {
        return store.movement(variantId, movementId);
    }

    private String hash(String canonical) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException unavailable) {
            throw new IllegalStateException("SHA-256 unavailable", unavailable);
        }
    }
}
