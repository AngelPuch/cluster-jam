package com.clusterjam.catalog.interfaces.http.openapi;

import java.util.List;

import com.clusterjam.catalog.interfaces.http.common.errors.dto.ProblemDetailsDto;
import io.swagger.v3.core.converter.ModelConverters;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import io.swagger.v3.oas.models.tags.Tag;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpenApiConfiguration {

    private static final String USER_BEARER = "supabaseBearer";
    private static final String SERVICE_BEARER = "serviceBearer";

    @Bean
    OpenAPI catalogOpenApi() {
        Components components = new Components()
            .addSecuritySchemes(USER_BEARER, bearer("Supabase access token."))
            .addSecuritySchemes(SERVICE_BEARER, bearer("Service token with catalog-service audience."))
            .addResponses("CatalogConflict", problem("Duplicate SKU or combination, or invalid state transition."))
            .addResponses("CatalogStaleRevision", problem("The validator does not match the current revision."))
            .addResponses("CatalogMissingRevision", problem("A current strong ETag is required in If-Match."));
        ModelConverters.getInstance(true).read(ProblemDetailsDto.class).forEach(components::addSchemas);
        return new OpenAPI()
            .info(new Info()
                .title("Cluster JAM Catalog Service")
                .version("1.0.0")
                .description("HTTP API for the Cluster JAM catalog and inventory service."))
            .servers(List.of(new Server().url("/")))
            .tags(List.of(new Tag().name("Health").description("Technical health checks.")))
            .components(components);
    }

    @Bean
    OpenApiCustomizer commonProblemResponse() {
        return api -> api.getPaths().forEach((route, path) -> path.readOperations().forEach(operation -> {
            if (route.startsWith("/api/v1/")) {
                String scheme = route.startsWith("/api/v1/internal/") ? SERVICE_BEARER : USER_BEARER;
                operation.addSecurityItem(new SecurityRequirement().addList(scheme));
            }
            operation.getResponses().putIfAbsent("default", problem("RFC 9457 Problem Details."));
        }));
    }

    private ApiResponse problem(String description) {
        return new ApiResponse().description(description)
            .content(new Content().addMediaType(
                org.springframework.http.MediaType.APPLICATION_PROBLEM_JSON_VALUE,
                new MediaType().schema(new Schema<>().$ref("#/components/schemas/ProblemDetails"))));
    }

    private SecurityScheme bearer(String description) {
        return new SecurityScheme().type(SecurityScheme.Type.HTTP)
            .scheme("bearer")
            .bearerFormat("JWT")
            .description(description);
    }
}
