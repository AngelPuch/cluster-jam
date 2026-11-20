package com.clusterjam.catalog.interfaces.http.catalog;

import com.clusterjam.catalog.application.reads.CatalogReadModels.References;
import com.clusterjam.catalog.application.reads.CatalogReadService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Catalog")
public class CatalogReferenceController {

    private final CatalogReadService service;

    public CatalogReferenceController(CatalogReadService service) {
        this.service = service;
    }

    @GetMapping("/catalog/references")
    @Operation(summary = "Read the type, size and color reference data maintained by catalog migrations.")
    public ResponseEntity<References> references() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.references());
    }
}
