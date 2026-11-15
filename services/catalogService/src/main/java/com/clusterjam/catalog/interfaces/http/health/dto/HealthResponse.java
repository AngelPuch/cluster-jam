package com.clusterjam.catalog.interfaces.http.health.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(requiredProperties = "status")
public record HealthResponse(@Schema(example = "ok", allowableValues = "ok") String status) {

    public static final HealthResponse OK = new HealthResponse("ok");
}
