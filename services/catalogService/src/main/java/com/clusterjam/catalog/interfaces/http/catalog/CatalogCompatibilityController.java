package com.clusterjam.catalog.interfaces.http.catalog;

import java.util.UUID;

import com.clusterjam.catalog.application.reads.CatalogReadModels.Compatibility;
import com.clusterjam.catalog.application.reads.CatalogReadModels.ProductSize;
import com.clusterjam.catalog.application.reads.CatalogReadService;
import com.clusterjam.catalog.application.security.CatalogAuthority;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
@Tag(name = "Catalog compatibility")
public class CatalogCompatibilityController {

    private final CatalogReadService service;

    public CatalogCompatibilityController(CatalogReadService service) {
        this.service = service;
    }

    @GetMapping("/variants/{variantId}")
    @Operation(summary = "Resolve variant references and states. The catalog:read scope also receives price and stock.")
    public ResponseEntity<Compatibility> variant(@PathVariable UUID variantId, Authentication authentication) {
        boolean commerce = authentication.getAuthorities().stream()
            .anyMatch(authority -> authority.getAuthority().equals(CatalogAuthority.READ));
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(service.compatibility(variantId, commerce));
    }

    @GetMapping("/products/{productId}/sizes/{sizeId}")
    @Operation(summary = "Resolve a product-size association, including unpublished and retired references.")
    public ResponseEntity<ProductSize> productSize(
        @PathVariable UUID productId, @PathVariable @Min(1) @Max(32767) int sizeId
    ) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.productSize(productId, sizeId));
    }
}
