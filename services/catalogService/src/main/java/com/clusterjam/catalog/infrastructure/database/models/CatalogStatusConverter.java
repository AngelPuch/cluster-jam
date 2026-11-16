package com.clusterjam.catalog.infrastructure.database.models;

import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class CatalogStatusConverter implements AttributeConverter<Status, String> {

    @Override
    public String convertToDatabaseColumn(Status value) {
        return switch (value) {
            case DRAFT -> "BORRADOR";
            case PUBLISHED -> "PUBLICADO";
            case RETIRED -> "RETIRADO";
        };
    }

    @Override
    public Status convertToEntityAttribute(String value) {
        return switch (value) {
            case "BORRADOR" -> Status.DRAFT;
            case "PUBLICADO" -> Status.PUBLISHED;
            case "RETIRADO" -> Status.RETIRED;
            default -> throw new IllegalStateException("Invalid stored catalog status");
        };
    }
}
