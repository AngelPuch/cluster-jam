package com.clusterjam.catalog.infrastructure.config;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
    @NotNull Environment environment
) {

    public enum Environment {
        DEVELOPMENT,
        TEST,
        STAGING,
        PRODUCTION
    }
}
