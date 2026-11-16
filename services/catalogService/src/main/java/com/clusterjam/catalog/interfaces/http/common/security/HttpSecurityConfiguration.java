package com.clusterjam.catalog.interfaces.http.common.security;

import com.clusterjam.catalog.application.security.CatalogAuthority;
import com.clusterjam.catalog.infrastructure.config.CatalogSecurityProperties;
import com.clusterjam.catalog.infrastructure.security.CatalogJwtAuthorities;
import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.ObjectPostProcessor;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class HttpSecurityConfiguration {

    private static final String INTERNAL = "/api/v1/internal";
    private static final String RESERVATIONS = INTERNAL + "/stock-reservations";

    private final SecurityProblemHandlers problems;
    private final WriteQuotaFilter writeQuota;

    public HttpSecurityConfiguration(
        SecurityProblemHandlers problems,
        CatalogSecurityProperties settings
    ) {
        this.problems = problems;
        this.writeQuota = new WriteQuotaFilter(settings.writesPerMinute(), settings.maxJsonBytes(), problems);
    }

    @Bean
    @Order(1)
    SecurityFilterChain serviceApi(
        HttpSecurity http,
        @Qualifier("serviceJwtDecoder") JwtDecoder decoder
    ) throws Exception {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(CatalogJwtAuthorities::service);

        base(http);
        return http.securityMatcher(INTERNAL, INTERNAL + "/**")
            .authorizeHttpRequests(access -> access
                .requestMatchers(HttpMethod.GET,
                    INTERNAL + "/variants/{variantId}",
                    INTERNAL + "/products/{productId}/sizes/{sizeId}")
                .hasAnyAuthority(CatalogAuthority.READ, CatalogAuthority.COMPATIBILITY)
                .requestMatchers(HttpMethod.GET, RESERVATIONS + "/{id}")
                .hasAuthority(CatalogAuthority.RESERVE)
                .requestMatchers(HttpMethod.POST, RESERVATIONS,
                    RESERVATIONS + "/{id}/confirmations", RESERVATIONS + "/{id}/releases",
                    RESERVATIONS + "/{id}/consumptions")
                .hasAuthority(CatalogAuthority.RESERVE)
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.authenticationEntryPoint(problems)
                .withObjectPostProcessor(bearerFailures())
                .jwt(jwt -> jwt.decoder(decoder).jwtAuthenticationConverter(converter)))
            .addFilterAfter(writeQuota, AuthorizationFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain humanApi(
        HttpSecurity http,
        @Qualifier("humanJwtDecoder") JwtDecoder decoder
    ) throws Exception {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(CatalogJwtAuthorities::human);

        base(http);
        return http.securityMatcher("/api/v1", "/api/v1/**")
            .authorizeHttpRequests(access -> access
                .requestMatchers(HttpMethod.GET, "/api/v1/products", "/api/v1/products/**")
                .hasAnyAuthority(CatalogAuthority.CLIENT, CatalogAuthority.ADMIN)
                .requestMatchers(HttpMethod.HEAD, "/api/v1/products", "/api/v1/products/**")
                .hasAnyAuthority(CatalogAuthority.CLIENT, CatalogAuthority.ADMIN)
                .requestMatchers("/api/v1/admin", "/api/v1/admin/**").hasAuthority(CatalogAuthority.ADMIN)
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.authenticationEntryPoint(problems)
                .withObjectPostProcessor(bearerFailures())
                .jwt(jwt -> jwt.decoder(decoder).jwtAuthenticationConverter(converter)))
            .addFilterAfter(writeQuota, AuthorizationFilter.class)
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain technicalEndpoints(HttpSecurity http) throws Exception {
        base(http);
        return http.authorizeHttpRequests(access -> access
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/health/live", "/health/ready", "/docs", "/docs/**", "/swagger-ui/**",
                    "/openapi.json", "/openapi.json/swagger-config", "/openapi.json.yaml")
                .permitAll()
                .anyRequest().denyAll())
            .build();
    }

    private ObjectPostProcessor<BearerTokenAuthenticationFilter> bearerFailures() {
        return new ObjectPostProcessor<>() {
            @Override
            public <T extends BearerTokenAuthenticationFilter> T postProcess(T filter) {
                filter.setAuthenticationFailureHandler(problems::commence);
                return filter;
            }
        };
    }

    private void base(HttpSecurity http) {
        http.csrf(AbstractHttpConfigurer::disable)
            .cors(AbstractHttpConfigurer::disable)
            .requestCache(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(errors -> errors.authenticationEntryPoint(problems).accessDeniedHandler(problems));
    }
}
