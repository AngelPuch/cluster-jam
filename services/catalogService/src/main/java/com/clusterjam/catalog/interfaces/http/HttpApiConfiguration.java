package com.clusterjam.catalog.interfaces.http;

import com.clusterjam.catalog.infrastructure.config.CatalogSecurityProperties;
import org.springframework.boot.jackson.autoconfigure.JsonFactoryBuilderCustomizer;
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import tools.jackson.core.StreamReadConstraints;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.MapperFeature;
import tools.jackson.databind.cfg.CoercionAction;
import tools.jackson.databind.cfg.CoercionInputShape;
import tools.jackson.databind.type.LogicalType;

@Configuration(proxyBeanMethods = false)
public class HttpApiConfiguration implements WebMvcConfigurer {

    private static final String HTTP_PACKAGE = HttpApiConfiguration.class.getPackageName();
    private static final String HEALTH_PACKAGE = HTTP_PACKAGE + ".health";

    @Override
    public void configurePathMatch(PathMatchConfigurer configurer) {
        configurer.addPathPrefix("/api/v1", type -> {
            String packageName = type.getPackageName();
            return AnnotatedElementUtils.hasAnnotation(type, RestController.class)
                && packageName.startsWith(HTTP_PACKAGE + ".")
                && !packageName.equals(HEALTH_PACKAGE)
                && !packageName.startsWith(HEALTH_PACKAGE + ".");
        });
    }

    @Bean
    JsonFactoryBuilderCustomizer catalogJsonLimits(CatalogSecurityProperties settings) {
        return builder -> builder.enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .streamReadConstraints(StreamReadConstraints.builder()
                .maxDocumentLength(settings.maxJsonBytes())
                .build());
    }

    @Bean
    JsonMapperBuilderCustomizer catalogJsonTypes() {
        return builder -> builder.disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
            .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .withCoercionConfig(LogicalType.Enum, config -> config
                .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail))
            .withCoercionConfig(LogicalType.Textual, config -> config
                .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
                .setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
                .setCoercion(CoercionInputShape.Boolean, CoercionAction.Fail));
    }
}
