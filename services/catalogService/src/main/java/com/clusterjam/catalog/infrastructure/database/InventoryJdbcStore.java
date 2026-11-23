package com.clusterjam.catalog.infrastructure.database;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

import com.clusterjam.catalog.application.inventory.InventoryFailure;
import com.clusterjam.catalog.application.inventory.InventoryModels.Adjustment;
import com.clusterjam.catalog.application.inventory.InventoryModels.Balance;
import com.clusterjam.catalog.application.inventory.InventoryModels.History;
import com.clusterjam.catalog.application.inventory.InventoryModels.Movement;
import com.clusterjam.catalog.application.inventory.InventoryModels.Result;
import com.clusterjam.catalog.application.ports.InventoryStore;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.stereotype.Repository;
import org.springframework.jdbc.core.RowMapper;

@Repository
public class InventoryJdbcStore implements InventoryStore {

    private static final String OPERATION = "ADJUST_INVENTORY_V1";
    private static final String BALANCE = """
        SELECT variante_id, stock_fisico, stock_reservado, version
        FROM app.inventario WHERE variante_id = ?
        """;
    private static final String MOVEMENTS = "SELECT * FROM app.movimiento_inventario ";

    private final JdbcOperations jdbc;

    public InventoryJdbcStore(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Balance balance(UUID variantId) {
        return requiredBalance(variantId, false);
    }

    @Override
    public Result adjust(UUID actor, UUID key, String hash, Adjustment input) {
        UUID movementId = UUID.randomUUID();
        int inserted = jdbc.update("""
            INSERT INTO app.idempotencia_ajuste(actor_ref, operacion, clave, solicitud_hash, movimiento_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (actor_ref, operacion, clave) DO NOTHING
            """, actor, OPERATION, key, hash, movementId);
        if (inserted == 0) {
            var stored = jdbc.queryForMap("""
                SELECT solicitud_hash, movimiento_id FROM app.idempotencia_ajuste
                WHERE actor_ref = ? AND operacion = ? AND clave = ?
                """, actor, OPERATION, key);
            if (!hash.equals(stored.get("solicitud_hash"))) {
                throw new InventoryFailure(InventoryFailure.Reason.CONFLICT);
            }
            return new Result(movement(input.variantId(), (UUID) stored.get("movimiento_id")), true);
        }

        Balance before = requiredBalance(input.variantId(), true);
        long after = (long) before.physicalQuantity() + input.quantityDelta();
        if (after < before.reservedQuantity() || after > Integer.MAX_VALUE
            || before.version() == Integer.MAX_VALUE) {
            throw new InventoryFailure(InventoryFailure.Reason.CONFLICT);
        }
        int version = before.version() + 1;
        int updated = jdbc.update("""
            UPDATE app.inventario SET stock_fisico = ?, version = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE variante_id = ? AND version = ?
            """, (int) after, version, input.variantId(), before.version());
        if (updated != 1) {
            throw new InventoryFailure(InventoryFailure.Reason.CONFLICT);
        }
        jdbc.update("""
            INSERT INTO app.movimiento_inventario(id, variante_id, tipo, cantidad_delta, motivo, actor_ref,
                fisico_antes, fisico_despues, reservado, version_despues)
            VALUES (?, ?, 'AJUSTE', ?, ?, ?, ?, ?, ?, ?)
            """, movementId, input.variantId(), input.quantityDelta(), input.reason(), actor,
            before.physicalQuantity(), (int) after, before.reservedQuantity(), version);
        return new Result(movement(input.variantId(), movementId), false);
    }

    @Override
    public History history(UUID variantId, int afterVersion, int limit) {
        balance(variantId);
        var rows = jdbc.query(MOVEMENTS + """
            WHERE variante_id = ? AND version_despues > ? ORDER BY version_despues LIMIT ?
            """, this::mapMovement, variantId, afterVersion, limit + 1);
        boolean more = rows.size() > limit;
        var items = rows.stream().limit(limit).toList();
        Integer next = more ? items.get(items.size() - 1).inventoryVersion() : null;
        return new History(items, next);
    }

    @Override
    public Movement movement(UUID variantId, UUID movementId) {
        return jdbc.query(MOVEMENTS + "WHERE variante_id = ? AND id = ?",
                this::mapMovement, variantId, movementId).stream().findFirst()
            .orElseThrow(() -> new InventoryFailure(InventoryFailure.Reason.MISSING));
    }

    private Balance requiredBalance(UUID variantId, boolean lock) {
        String sql = lock ? BALANCE + " FOR UPDATE" : BALANCE;
        RowMapper<Balance> mapper = (row, index) -> {
            int physical = row.getInt("stock_fisico");
            int reserved = row.getInt("stock_reservado");
            return new Balance(variantId, physical, reserved, physical - reserved, row.getInt("version"));
        };
        return jdbc.query(sql, mapper, variantId).stream().findFirst()
            .orElseThrow(() -> new InventoryFailure(InventoryFailure.Reason.MISSING));
    }

    private Movement mapMovement(ResultSet row, int index) throws SQLException {
        int physical = row.getInt("fisico_despues");
        int reserved = row.getInt("reservado");
        return new Movement(row.getObject("id", UUID.class), row.getObject("variante_id", UUID.class),
            row.getString("tipo"), row.getInt("cantidad_delta"), row.getString("motivo"),
            row.getObject("actor_ref", UUID.class), row.getInt("fisico_antes"), physical, reserved,
            physical - reserved, row.getInt("version_despues"), row.getTimestamp("creado_en").toInstant());
    }
}
