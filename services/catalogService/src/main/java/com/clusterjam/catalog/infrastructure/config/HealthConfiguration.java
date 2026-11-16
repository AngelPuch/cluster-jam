package com.clusterjam.catalog.infrastructure.config;

import com.clusterjam.catalog.application.health.ReadinessService;
import com.clusterjam.catalog.application.ports.ReadinessProbe;
import com.clusterjam.catalog.infrastructure.database.PostgresReadinessProbe;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class HealthConfiguration {

    @Bean
    ReadinessProbe readinessProbe(JdbcOperations jdbc) {
        return new PostgresReadinessProbe(jdbc);
    }

    @Bean
    ReadinessService readinessService(ReadinessProbe probe) {
        return new ReadinessService(probe);
    }
}
