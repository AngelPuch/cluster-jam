package com.clusterjam.catalog.interfaces.http.health.dto;

public record HealthResponse(String status) {

    public static final HealthResponse OK = new HealthResponse("ok");
    public static final HealthResponse UNAVAILABLE = new HealthResponse("unavailable");
}
