package com.clusterjam.catalog.interfaces.http.admin;

import java.net.URI;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.inventory.InventoryFailure;
import com.clusterjam.catalog.application.inventory.InventoryModels.Balance;
import com.clusterjam.catalog.application.inventory.InventoryModels.History;
import com.clusterjam.catalog.application.inventory.InventoryModels.Movement;
import com.clusterjam.catalog.application.inventory.InventoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/admin/variants/{variantId}/inventory", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Admin inventory")
public class InventoryAdminController {

    public record AdjustmentInput(
        @NotNull @Min(-1_000_000) @Max(1_000_000) Integer quantityDelta,
        @NotBlank @Size(max = 200) @Pattern(regexp = "[^\\p{Cc}\\p{Cf}]+") String reason
    ) {
    }

    private final InventoryService service;

    public InventoryAdminController(InventoryService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "Read the current physical, reserved and available inventory as an administrator.")
    public ResponseEntity<Balance> balance(@PathVariable UUID variantId) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.balance(variantId));
    }

    @PostMapping(path = "/adjustments", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Record an audited physical stock delta without changing reserved stock.",
        description = "Administrator only. A UUID Idempotency-Key is required. Identical retries return the original "
            + "201 and historical movement; changed content with the same actor and key returns 409. "
            + "A zero delta is invalid. Physical stock cannot fall below reserved stock.")
    @ApiResponse(
        responseCode = "201",
        description = "Adjustment created or original result replayed.",
        useReturnTypeSchema = true,
        headers = {
            @Header(name = "Location", description = "Administrative movement URL.", schema = @Schema(type = "string")),
            @Header(name = "Idempotency-Replayed", schema = @Schema(type = "boolean"))
        }
    )
    @ApiResponse(responseCode = "409", description = "Insufficient unreserved stock, key conflict or numeric limit.",
        content = @Content(mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(ref = "#/components/schemas/ProblemDetails")))
    @ApiResponse(responseCode = "422", description = "Invalid input or missing/invalid idempotency key.",
        content = @Content(mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(ref = "#/components/schemas/ProblemDetails")))
    public ResponseEntity<Movement> adjust(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID variantId,
        @Parameter(required = true, description = "One canonical UUID per administrator action.",
            schema = @Schema(type = "string", format = "uuid"))
        @RequestHeader(name = "Idempotency-Key", required = false) List<String> keys,
        @Valid @RequestBody AdjustmentInput input
    ) {
        var result = service.adjust(UUID.fromString(jwt.getSubject()), requireKey(keys), variantId,
            input.quantityDelta(), input.reason());
        URI location = URI.create("/api/v1/admin/variants/" + variantId + "/inventory/movements/"
            + result.movement().id());
        return ResponseEntity.created(location).cacheControl(CacheControl.noStore())
            .header("Idempotency-Replayed", Boolean.toString(result.replayed())).body(result.movement());
    }

    @GetMapping("/movements")
    @Operation(summary = "Read inventory movements in ascending inventory version order.")
    public ResponseEntity<History> history(
        @PathVariable UUID variantId,
        @RequestParam(defaultValue = "0") @Min(0) int afterVersion,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit
    ) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(service.history(variantId, afterVersion, limit));
    }

    @GetMapping("/movements/{movementId}")
    @Operation(summary = "Read a historical movement belonging to this variant as an administrator.")
    public ResponseEntity<Movement> movement(@PathVariable UUID variantId, @PathVariable UUID movementId) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.movement(variantId, movementId));
    }

    private UUID requireKey(List<String> keys) {
        if (keys == null || keys.size() != 1 || !keys.get(0).matches(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")) {
            throw new InventoryFailure(InventoryFailure.Reason.INVALID);
        }
        return UUID.fromString(keys.get(0));
    }
}
