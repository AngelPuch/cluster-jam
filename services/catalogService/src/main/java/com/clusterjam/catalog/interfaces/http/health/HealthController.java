package com.clusterjam.catalog.interfaces.http.health;

import com.clusterjam.catalog.application.health.ReadinessService;
import com.clusterjam.catalog.interfaces.http.common.errors.dto.ProblemDetailsDto;
import com.clusterjam.catalog.interfaces.http.health.dto.HealthResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/health")
@Tag(name = "Health")
public class HealthController {

    private final ReadinessService readiness;

    public HealthController(ReadinessService readiness) {
        this.readiness = readiness;
    }

    @GetMapping("/live")
    @Operation(summary = "Check if the service process can respond.")
    @ApiResponse(responseCode = "200", description = "The process is alive.", content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = HealthResponse.class)))
    public ResponseEntity<HealthResponse> live() {
        return ok();
    }

    @GetMapping("/ready")
    @Operation(summary = "Check if the service is ready to accept traffic.")
    @ApiResponse(responseCode = "200", description = "The service is ready.", content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = HealthResponse.class)))
    @ApiResponse(responseCode = "503", description = "The service is temporarily unavailable.", content = @Content(
        mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
        schema = @Schema(implementation = ProblemDetailsDto.class)))
    public ResponseEntity<HealthResponse> ready() {
        if (!readiness.isReady()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
        }
        return ok();
    }

    private ResponseEntity<HealthResponse> ok() {
        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(HealthResponse.OK);
    }
}
