package com.clusterjam.catalog.infrastructure.config;

import com.clusterjam.catalog.application.health.ReadinessService;
import com.clusterjam.catalog.application.ports.ReadinessProbe;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class HealthConfiguration {

    @Bean
    ReadinessProbe readinessProbe(CatalogProperties properties) {
        return properties::readinessAvailable;
    }

    @Bean
    ReadinessService readinessService(ReadinessProbe probe) {
        return new ReadinessService(probe);
    }
}
