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
import io.swagger.v3.oas.models.servers.Server;
import io.swagger.v3.oas.models.tags.Tag;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpenApiConfiguration {

    @Bean
    OpenAPI catalogOpenApi() {
        Components components = new Components();
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
        return api -> api.getPaths().values().forEach(path -> path.readOperations().forEach(operation -> {
            ApiResponse response = new ApiResponse().description("RFC 9457 Problem Details.")
                .content(new Content().addMediaType(
                    org.springframework.http.MediaType.APPLICATION_PROBLEM_JSON_VALUE,
                    new MediaType().schema(new Schema<>().$ref("#/components/schemas/ProblemDetails"))));
            operation.getResponses().putIfAbsent("default", response);
        }));
    }
}
