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
import jakarta.validation.constraints.Size;

public final class ReservationMessages {

    public static final String RESERVE = "cmd.catalog.reserve-stock.v1";
    public static final String CONFIRM = "cmd.catalog.confirm-reservation.v1";
    public static final String RELEASE = "cmd.catalog.release-reservation.v1";
    public static final String CONSUME = "cmd.catalog.consume-stock.v1";
    public static final String CREATED = "catalog.inventory.reservation-created.v1";
    public static final String REJECTED = "catalog.inventory.reservation-rejected.v1";
    public static final String CONFIRMED = "catalog.inventory.reservation-confirmed.v1";
    public static final String RELEASED = "catalog.inventory.reservation-released.v1";
    public static final String EXPIRED = "catalog.inventory.reservation-expired.v1";
    public static final String CONSUMED = "catalog.inventory.stock-consumed.v1";

    private ReservationMessages() {
    }

    public sealed interface Command permits ReserveCommand, ConfirmCommand, ReleaseCommand, ConsumeCommand {
        UUID messageId();

        String type();

        UUID orderId();

        Instant occurredAt();
    }

    public record ReserveCommand(
        @NotNull UUID messageId,
        @NotBlank String type,
        @NotNull UUID orderId,
        @NotNull Instant occurredAt,
        @NotNull @Valid ReserveData data
    ) implements Command {
    }

    public record ConfirmCommand(
        @NotNull UUID messageId,
        @NotBlank String type,
        @NotNull UUID orderId,
        @NotNull Instant occurredAt,
        @NotNull @Valid ConfirmData data
    ) implements Command {
    }

    public record ReleaseCommand(
        @NotNull UUID messageId,
        @NotBlank String type,
        @NotNull UUID orderId,
        @NotNull Instant occurredAt,
        @NotNull @Valid ReleaseData data
    ) implements Command {
    }

    public record ConsumeCommand(
        @NotNull UUID messageId,
        @NotBlank String type,
        @NotNull UUID orderId,
        @NotNull Instant occurredAt,
        @NotNull @Valid ConsumeData data
    ) implements Command {
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

    public record ConfirmData(@NotNull UUID reservationId, @NotNull UUID paymentId) {
    }

    public record ReleaseData(@NotNull UUID reservationId, @NotBlank @Size(max = 200) String reason) {
    }

    public record ConsumeData(@NotNull UUID reservationId) {
    }

    public record ResultMessage(UUID messageId, String type, UUID orderId, Instant occurredAt, Object data) {
    }

    public record CreatedData(UUID reservationId, Instant expiresAt) {
    }

    public record RejectedData(String reason) {
    }

    public record ConfirmedData(UUID reservationId, UUID paymentId) {
    }

    public record ReleasedData(UUID reservationId, String reason) {
    }

    public record ExpiredData(UUID reservationId, Instant expiresAt) {
    }

    public record ConsumedData(UUID reservationId) {
    }
}
