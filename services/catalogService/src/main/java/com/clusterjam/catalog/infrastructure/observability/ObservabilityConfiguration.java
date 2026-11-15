package com.clusterjam.catalog.infrastructure.observability;

import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean(destroyMethod = "close")
    SdkTracerProvider tracerProvider() {
        return SdkTracerProvider.builder().build();
    }

    @Bean
    Tracer catalogTracer(SdkTracerProvider provider) {
        return provider.get("catalog-service");
    }
}
