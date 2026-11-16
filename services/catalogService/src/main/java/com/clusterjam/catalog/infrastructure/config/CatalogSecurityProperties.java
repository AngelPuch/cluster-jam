package com.clusterjam.catalog.infrastructure.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("catalog.security")
public record CatalogSecurityProperties(
    String supabaseUrl,
    String serviceJwtIssuer,
    @Min(1) @Max(10000) int writesPerMinute,
    @Min(1024) @Max(1048576) long maxJsonBytes
) {
}
