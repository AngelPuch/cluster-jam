package com.clusterjam.catalog.infrastructure.security;

import java.net.URI;
import java.net.http.HttpClient;
import java.text.ParseException;
import java.time.Duration;
import java.time.Instant;

import com.clusterjam.catalog.infrastructure.config.CatalogProperties;
import com.clusterjam.catalog.infrastructure.config.CatalogSecurityProperties;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.RemoteKeySourceException;
import com.nimbusds.jwt.SignedJWT;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogSecurityProperties.class)
public class CatalogJwtConfiguration {

    private static final Duration CLOCK_SKEW = Duration.ofSeconds(10);
    private static final Duration SERVICE_TOKEN_TTL = Duration.ofMinutes(5);
    private static final OAuth2Error INVALID_CLAIMS = new OAuth2Error("invalid_token");
    private static final String UUID_PATTERN =
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

    @Bean
    JwtDecoder humanJwtDecoder(CatalogSecurityProperties settings, CatalogProperties properties) {
        if (settings.supabaseUrl().isBlank()) {
            if (!isLocal(properties)) {
                throw new IllegalArgumentException("SUPABASE_URL is required.");
            }
            return disabledDecoder();
        }
        String issuer = trustedUri(settings.supabaseUrl(), properties, true, "SUPABASE_URL") + "/auth/v1";
        return decoder(issuer, "authenticated", this::humanClaims);
    }

    @Bean
    JwtDecoder serviceJwtDecoder(CatalogSecurityProperties settings, CatalogProperties properties) {
        if (settings.serviceJwtIssuer().isBlank()) {
            return disabledDecoder();
        }
        String issuer = trustedUri(settings.serviceJwtIssuer(), properties, false, "SERVICE_JWT_ISSUER");
        if (!settings.supabaseUrl().isBlank()) {
            String humanIssuer = trustedUri(settings.supabaseUrl(), properties, true, "SUPABASE_URL") + "/auth/v1";
            if (humanIssuer.equals(issuer)) {
                throw new IllegalArgumentException("The service issuer must differ from Supabase.");
            }
        }
        return decoder(issuer, "catalog-service", this::serviceClaims);
    }

    private JwtDecoder disabledDecoder() {
        return token -> {
            throw new BadJwtException("No issuer is configured for this type of token.");
        };
    }

    private JwtDecoder decoder(String issuer, String audience, OAuth2TokenValidator<Jwt> claims) {
        HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
        var factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofSeconds(5));

        var decoder = NimbusJwtDecoder.withJwkSetUri(issuer + "/.well-known/jwks.json")
            .jwsAlgorithms(algorithms -> {
                algorithms.add(SignatureAlgorithm.ES256);
                algorithms.add(SignatureAlgorithm.RS256);
            })
            .restOperations(new RestTemplate(factory))
            .build();

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            new JwtTimestampValidator(CLOCK_SKEW),
            new JwtIssuerValidator(issuer),
            jwt -> validate(jwt.getExpiresAt() != null && jwt.getAudience() != null
                && jwt.getAudience().contains(audience)),
            claims
        ));
        return token -> {
            validateHeader(token);
            try {
                return decoder.decode(token);
            } catch (JwtException failure) {
                if (failure.getCause() instanceof RemoteKeySourceException) {
                    throw new JwtException("Signing keys are temporarily unavailable.", failure);
                }
                throw new BadJwtException("Invalid access token.", failure);
            }
        };
    }

    private void validateHeader(String token) {
        if (token.length() > 12000) {
            throw new BadJwtException("Invalid access token.");
        }
        try {
            var header = SignedJWT.parse(token).getHeader();
            String kid = header.getKeyID();
            boolean allowedAlgorithm = JWSAlgorithm.ES256.equals(header.getAlgorithm())
                || JWSAlgorithm.RS256.equals(header.getAlgorithm());
            if (!allowedAlgorithm || kid == null || kid.isBlank() || kid.length() > 256) {
                throw new BadJwtException("Invalid access token.");
            }
        } catch (ParseException malformed) {
            throw new BadJwtException("Invalid access token.", malformed);
        }
    }

    private OAuth2TokenValidatorResult humanClaims(Jwt jwt) {
        Object anonymous = jwt.getClaims().get("is_anonymous");
        return validate(jwt.getSubject() != null && jwt.getSubject().matches(UUID_PATTERN)
            && "authenticated".equals(jwt.getClaims().get("role"))
            && (anonymous == null || Boolean.FALSE.equals(anonymous)));
    }

    private OAuth2TokenValidatorResult serviceClaims(Jwt jwt) {
        Instant issued = jwt.getIssuedAt();
        Instant expires = jwt.getExpiresAt();
        return validate(jwt.getSubject() != null && jwt.getSubject().matches("[a-z][a-z0-9-]{0,39}")
            && issued != null && expires != null && expires.isAfter(issued)
            && !issued.isAfter(Instant.now().plus(CLOCK_SKEW))
            && Duration.between(issued, expires).compareTo(SERVICE_TOKEN_TTL) <= 0);
    }

    private OAuth2TokenValidatorResult validate(boolean accepted) {
        return accepted ? OAuth2TokenValidatorResult.success() : OAuth2TokenValidatorResult.failure(INVALID_CLAIMS);
    }

    private String trustedUri(String value, CatalogProperties properties, boolean originOnly, String name) {
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            boolean loopback = "127.0.0.1".equals(host) || "localhost".equalsIgnoreCase(host)
                || "[::1]".equals(host);
            boolean allowedScheme = "https".equals(scheme) || ("http".equals(scheme) && loopback
                && isLocal(properties));
            String path = uri.getRawPath();
            boolean allowedPath = originOnly ? path != null && (path.isEmpty() || path.equals("/"))
                : path != null && path.matches("(/[A-Za-z0-9_-]+)*/?");
            if (allowedScheme && host != null && allowedPath && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null && uri.getRawFragment() == null) {
                return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
            }
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException(name + " must be a trusted issuer address.");
        }
        throw new IllegalArgumentException(name + " must be a trusted issuer address.");
    }

    private boolean isLocal(CatalogProperties properties) {
        return switch (properties.environment()) {
            case DEVELOPMENT, TEST -> true;
            case STAGING, PRODUCTION -> false;
        };
    }
}
