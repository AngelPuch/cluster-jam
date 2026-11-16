package com.clusterjam.catalog.infrastructure.security;

import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.clusterjam.catalog.application.security.CatalogAuthority;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class CatalogJwtAuthorities {

    private CatalogJwtAuthorities() {
    }

    public static Collection<GrantedAuthority> human(Jwt jwt) {
        if (jwt.getClaims().get("app_metadata") instanceof Map<?, ?> metadata
            && metadata.get("app_role") instanceof String role) {
            return switch (role) {
                case "cliente" -> List.of(new SimpleGrantedAuthority(CatalogAuthority.CLIENT));
                case "administrador" -> List.of(new SimpleGrantedAuthority(CatalogAuthority.ADMIN));
                default -> List.of();
            };
        }
        return List.of();
    }

    public static Collection<GrantedAuthority> service(Jwt jwt) {
        Set<String> allowed = switch (jwt.getSubject()) {
            case "orders" -> Set.of(CatalogAuthority.READ, CatalogAuthority.RESERVE);
            case "personalization" -> Set.of(CatalogAuthority.COMPATIBILITY);
            default -> Set.of();
        };
        if (!(jwt.getClaims().get("scope") instanceof String scopes)) {
            return List.of();
        }
        return Arrays.stream(scopes.split(" "))
            .filter(allowed::contains)
            .distinct()
            .map(scope -> (GrantedAuthority) new SimpleGrantedAuthority(scope))
            .toList();
    }
}
