package com.clusterjam.catalog.interfaces.http.admin;

import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

import com.clusterjam.catalog.application.products.CatalogProducts.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class CatalogEtags {

    private static final Pattern TAG = Pattern.compile(
        "(W/)?\"([pv]-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})-(0|[1-9][0-9]{0,9})\"");

    private CatalogEtags() {
    }

    static String tag(Resource resource, UUID id, int version) {
        return "\"" + prefix(resource, id) + "-" + version + "\"";
    }

    static int requireVersion(List<String> values, Resource resource, UUID id) {
        if (values == null) {
            throw new ResponseStatusException(HttpStatus.PRECONDITION_REQUIRED);
        }
        if (values.size() != 1) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        var matcher = TAG.matcher(values.getFirst().strip());
        if (!matcher.matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        if (matcher.group(1) != null || !prefix(resource, id).equals(matcher.group(2))) {
            throw new ResponseStatusException(HttpStatus.PRECONDITION_FAILED);
        }
        try {
            return Integer.parseInt(matcher.group(3));
        } catch (NumberFormatException invalid) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
    }

    private static String prefix(Resource resource, UUID id) {
        return (resource == Resource.PRODUCT ? "p-" : "v-") + id;
    }
}
