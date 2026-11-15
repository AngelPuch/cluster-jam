package com.clusterjam.catalog.interfaces.http.common.errors.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "ProblemDetails",
    requiredProperties = {"type", "title", "status", "detail", "instance", "code", "traceId"}
)
public record ProblemDetailsDto(
    @Schema(example = "about:blank") String type,
    @Schema(example = "Service Unavailable") String title,
    @Schema(example = "503") int status,
    @Schema(example = "The service is temporarily unavailable.") String detail,
    @Schema(example = "/health/ready") String instance,
    @Schema(example = "SERVICE_UNAVAILABLE") String code,
    @Schema(example = "4bf92f3577b34da6a3ce929d0e0e4736", pattern = "^[0-9a-f]{32}$") String traceId,
    @Schema(description = "Controlled validation messages when applicable.") List<String> errors
) {
}
