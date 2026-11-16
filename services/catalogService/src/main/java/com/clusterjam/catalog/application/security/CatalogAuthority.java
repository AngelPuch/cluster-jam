package com.clusterjam.catalog.application.security;

public final class CatalogAuthority {

    public static final String CLIENT = "ROLE_CLIENTE";
    public static final String ADMIN = "ROLE_ADMINISTRADOR";
    public static final String READ = "catalog:read";
    public static final String RESERVE = "catalog:reserve";
    public static final String COMPATIBILITY = "catalog:compatibility";

    private CatalogAuthority() {
    }
}
