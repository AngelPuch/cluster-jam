package com.clusterjam.catalog.interfaces.http.catalog;

import java.util.Locale;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Links;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Card;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Detail;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Filter;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Page;
import com.clusterjam.catalog.application.reads.CatalogReadService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
@Tag(name = "Catalog")
public class CatalogReadController {

    private final CatalogReadService service;

    public CatalogReadController(CatalogReadService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "List published products with filters matched on the same published variant.")
    public ResponseEntity<Page<Card>> search(
        @RequestParam(required = false) @Size(max = 120) String name,
        @RequestParam(required = false) @Positive @Max(32767) Integer typeId,
        @RequestParam(required = false) @Positive @Max(32767) Integer sizeId,
        @RequestParam(required = false) @Positive @Max(32767) Integer colorId,
        @RequestParam(required = false) @PositiveOrZero Long minPriceCents,
        @RequestParam(required = false) @PositiveOrZero Long maxPriceCents,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
        @RequestParam(required = false) @Size(max = 512) String cursor
    ) {
        String term = name == null || name.isBlank() ? null : name.strip().toLowerCase(Locale.ROOT);
        Filter filter = new Filter(term, typeId, sizeId, colorId, minPriceCents, maxPriceCents);
        return ok(service.search(filter, limit, cursor));
    }

    @GetMapping("/{productId}")
    @Operation(summary = "Read a published product with one page of published variants and their photo references.")
    public ResponseEntity<Detail> detail(
        @PathVariable UUID productId,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
        @RequestParam(required = false) @Size(max = 512) String cursor
    ) {
        return ok(service.detail(productId, limit, cursor));
    }

    @GetMapping("/{productId}/colors/{colorId}/photos/{side}/links")
    @Operation(summary = "Issue 60-second photo links after checking product and color publication.")
    public ResponseEntity<Links> links(
        @PathVariable UUID productId,
        @PathVariable @Min(1) @Max(32767) int colorId,
        @PathVariable Side side
    ) {
        return ok(service.links(new Slot(productId, colorId, side)));
    }

    private <T> ResponseEntity<T> ok(T body) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body);
    }
}
