package com.clusterjam.catalog.application.reservations;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public final class ReservationMessages {

    public static final String RESERVE = "cmd.catalog.reserve-stock.v1";
    public static final String CREATED = "catalog.inventory.reservation-created.v1";
    public static final String REJECTED = "catalog.inventory.reservation-rejected.v1";

    private ReservationMessages() {
    }

    public record ReserveCommand(
        @NotNull UUID messageId,
        @NotBlank String type,
        @NotNull UUID orderId,
        @NotNull Instant occurredAt,
        @NotNull @Valid ReserveData data
    ) {
    }

    public record ReserveData(
        @NotNull Instant quoteValidUntil,
        @NotEmpty List<@NotNull @Valid ReserveLine> lines
    ) {
    }

    public record ReserveLine(
        @NotNull UUID variantId,
        @NotNull @Positive Integer quantity,
        @NotNull @Positive @Max(10000000) Long expectedBasePriceCents
    ) {
    }

    public record ResultMessage(UUID messageId, String type, UUID orderId, Instant occurredAt, Object data) {
    }

    public record CreatedData(UUID reservationId, Instant expiresAt) {
    }

    public record RejectedData(String reason) {
    }
}
