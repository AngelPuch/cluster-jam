package com.clusterjam.catalog.interfaces.http;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

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
}
