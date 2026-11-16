package com.clusterjam.catalog.interfaces.http.admin;

import java.net.URI;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProductService;
import com.clusterjam.catalog.application.products.CatalogProducts.Resource;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.CreateProduct;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.CreateVariant;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.EditProduct;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.EditVariant;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.PageView;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.ProductView;
import com.clusterjam.catalog.interfaces.http.admin.CatalogAdminDtos.VariantView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/admin/products", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Admin catalog")
public class CatalogAdminController {

    private static final String PRODUCTS = "/api/v1/admin/products/";
    private static final String IF_MATCH = "One strong ETag returned by this resource.";
    private static final String ETAG = "Strong validator for the returned representation.";

    private final CatalogProductService service;

    public CatalogAdminController(CatalogProductService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "List products for catalog administrators.")
    public ResponseEntity<PageView<ProductView>> products(
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
        @RequestParam(required = false) UUID after
    ) {
        var page = service.products(after, limit);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(new PageView<>(page.items().stream().map(ProductView::from).toList(), page.nextCursor()));
    }

    @GetMapping("/{productId}")
    @Operation(summary = "Read a product and its current revision.")
    @ApiResponse(responseCode = "200", description = "Product.", useReturnTypeSchema = true,
        headers = @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")))
    public ResponseEntity<ProductView> product(@PathVariable UUID productId) {
        var product = service.product(productId);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.PRODUCT, productId, product.version()))
            .body(ProductView.from(product));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Create a draft product.")
    @ApiResponse(responseCode = "201", description = "Draft created.", useReturnTypeSchema = true, headers = {
        @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")),
        @Header(name = HttpHeaders.LOCATION, schema = @Schema(type = "string"))
    })
    public ResponseEntity<ProductView> createProduct(
        @AuthenticationPrincipal Jwt jwt,
        @Valid @RequestBody CreateProduct input
    ) {
        var product = service.createProduct(UUID.fromString(jwt.getSubject()), input.fields());
        return ResponseEntity.created(URI.create(PRODUCTS + product.id())).cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.PRODUCT, product.id(), product.version()))
            .body(ProductView.from(product));
    }

    @PatchMapping(path = "/{productId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Edit, publish or retire a product using its current revision.")
    @ApiResponse(responseCode = "200", description = "Product updated.", useReturnTypeSchema = true,
        headers = @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")))
    @ApiResponse(responseCode = "409", ref = "#/components/responses/CatalogConflict")
    @ApiResponse(responseCode = "412", ref = "#/components/responses/CatalogStaleRevision")
    @ApiResponse(responseCode = "428", ref = "#/components/responses/CatalogMissingRevision")
    public ResponseEntity<ProductView> editProduct(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID productId,
        @Parameter(required = true, description = IF_MATCH, schema = @Schema(type = "string"))
        @RequestHeader(name = HttpHeaders.IF_MATCH, required = false) List<String> ifMatch,
        @Valid @RequestBody EditProduct input
    ) {
        int version = CatalogEtags.requireVersion(ifMatch, Resource.PRODUCT, productId);
        var product = service.editProduct(UUID.fromString(jwt.getSubject()), productId, version,
            input.fields(), input.status());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.PRODUCT, productId, product.version()))
            .body(ProductView.from(product));
    }

    @GetMapping("/{productId}/variants")
    @Operation(summary = "List the variants of a product for catalog administrators.")
    public ResponseEntity<PageView<VariantView>> variants(
        @PathVariable UUID productId,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
        @RequestParam(required = false) UUID after
    ) {
        var page = service.variants(productId, after, limit);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(new PageView<>(page.items().stream().map(VariantView::from).toList(), page.nextCursor()));
    }

    @GetMapping("/{productId}/variants/{variantId}")
    @Operation(summary = "Read a variant that belongs to the product and its current revision.")
    @ApiResponse(responseCode = "200", description = "Variant.", useReturnTypeSchema = true,
        headers = @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")))
    public ResponseEntity<VariantView> variant(@PathVariable UUID productId, @PathVariable UUID variantId) {
        var variant = service.variant(productId, variantId);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.VARIANT, variantId, variant.version()))
            .body(VariantView.from(variant));
    }

    @PostMapping(path = "/{productId}/variants", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Create a draft variant with a zero inventory balance.")
    @ApiResponse(responseCode = "201", description = "Draft variant created.", useReturnTypeSchema = true, headers = {
        @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")),
        @Header(name = HttpHeaders.LOCATION, schema = @Schema(type = "string"))
    })
    @ApiResponse(responseCode = "409", ref = "#/components/responses/CatalogConflict")
    public ResponseEntity<VariantView> createVariant(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID productId,
        @Valid @RequestBody CreateVariant input
    ) {
        var variant = service.createVariant(UUID.fromString(jwt.getSubject()), productId, input.fields());
        URI location = URI.create(PRODUCTS + productId + "/variants/" + variant.id());
        return ResponseEntity.created(location).cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.VARIANT, variant.id(), variant.version()))
            .body(VariantView.from(variant));
    }

    @PatchMapping(path = "/{productId}/variants/{variantId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Edit the price, publish or retire a variant using its current revision.")
    @ApiResponse(responseCode = "200", description = "Variant updated.", useReturnTypeSchema = true,
        headers = @Header(name = HttpHeaders.ETAG, description = ETAG, schema = @Schema(type = "string")))
    @ApiResponse(responseCode = "409", ref = "#/components/responses/CatalogConflict")
    @ApiResponse(responseCode = "412", ref = "#/components/responses/CatalogStaleRevision")
    @ApiResponse(responseCode = "428", ref = "#/components/responses/CatalogMissingRevision")
    public ResponseEntity<VariantView> editVariant(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID productId,
        @PathVariable UUID variantId,
        @Parameter(required = true, description = IF_MATCH, schema = @Schema(type = "string"))
        @RequestHeader(name = HttpHeaders.IF_MATCH, required = false) List<String> ifMatch,
        @Valid @RequestBody EditVariant input
    ) {
        int version = CatalogEtags.requireVersion(ifMatch, Resource.VARIANT, variantId);
        var variant = service.editVariant(UUID.fromString(jwt.getSubject()), productId, variantId, version,
            input.basePriceCents(), input.status());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .eTag(CatalogEtags.tag(Resource.VARIANT, variantId, variant.version()))
            .body(VariantView.from(variant));
    }
}
