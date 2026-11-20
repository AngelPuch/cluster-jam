package com.clusterjam.catalog.application.ports;

import java.util.UUID;

public interface CatalogReadCursors {

    UUID decode(String cursor, String scope);

    String encode(UUID last, String scope);
}
