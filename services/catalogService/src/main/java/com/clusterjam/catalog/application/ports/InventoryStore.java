package com.clusterjam.catalog.application.ports;

import java.util.UUID;

import com.clusterjam.catalog.application.inventory.InventoryModels.Adjustment;
import com.clusterjam.catalog.application.inventory.InventoryModels.Balance;
import com.clusterjam.catalog.application.inventory.InventoryModels.History;
import com.clusterjam.catalog.application.inventory.InventoryModels.Movement;
import com.clusterjam.catalog.application.inventory.InventoryModels.Result;

public interface InventoryStore {

    Balance balance(UUID variantId);

    Result adjust(UUID actor, UUID key, String hash, Adjustment adjustment);

    History history(UUID variantId, int afterVersion, int limit);

    Movement movement(UUID variantId, UUID movementId);
}
