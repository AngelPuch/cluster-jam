package com.clusterjam.catalog.interfaces.http.admin;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Links;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.photos.PhotoService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping(path = "/admin/products/{productId}/colors/{colorId}/photos/{side}",
    produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Admin photos")
public class PhotoAdminController {

    private final PhotoService service;

    public PhotoAdminController(PhotoService service) {
        this.service = service;
    }

    public record PhotoView(UUID id, UUID productId, int colorId, Side side, boolean active) {

        static PhotoView from(Photo photo) {
            return new PhotoView(photo.id(), photo.slot().productId(), photo.slot().colorId(),
                photo.slot().side(), photo.active());
        }
    }

    @GetMapping
    @Operation(summary = "Read photo slot metadata and its ETag.")
    @ApiResponse(responseCode = "200", useReturnTypeSchema = true, description = "Photo metadata.",
        headers = @Header(name = "ETag", schema = @Schema(type = "string")))
    public ResponseEntity<PhotoView> get(
        @PathVariable UUID productId, @PathVariable @Min(1) @Max(32767) int colorId, @PathVariable Side side
    ) {
        Photo photo = service.get(new Slot(productId, colorId, side));
        return response(photo, 200);
    }

    @PutMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Create with If-None-Match * or replace with the current If-Match ETag.")
    @Parameters({
        @Parameter(name = "If-Match", in = io.swagger.v3.oas.annotations.enums.ParameterIn.HEADER,
            description = "Current photo ETag for replacement.", schema = @Schema(type = "string")),
        @Parameter(name = "If-None-Match", in = io.swagger.v3.oas.annotations.enums.ParameterIn.HEADER,
            description = "Use * only to create an unused slot.", schema = @Schema(type = "string"))
    })
    @ApiResponse(responseCode = "201", useReturnTypeSchema = true, description = "Photo created.",
        headers = @Header(name = "ETag", schema = @Schema(type = "string")))
    @ApiResponse(responseCode = "200", useReturnTypeSchema = true, description = "Photo replaced.",
        headers = @Header(name = "ETag", schema = @Schema(type = "string")))
    @ApiResponse(responseCode = "412", ref = "#/components/responses/CatalogStaleRevision")
    @ApiResponse(responseCode = "428", ref = "#/components/responses/CatalogMissingRevision")
    public ResponseEntity<PhotoView> upload(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID productId, @PathVariable @Min(1) @Max(32767) int colorId, @PathVariable Side side,
        @Parameter(schema = @Schema(type = "string", format = "binary"))
        @RequestPart("file") MultipartFile file,
        HttpServletRequest request
    ) throws IOException {
        String match = header(request, HttpHeaders.IF_MATCH);
        String none = header(request, HttpHeaders.IF_NONE_MATCH);
        if (match == null && none == null) {
            throw new ResponseStatusException(HttpStatus.PRECONDITION_REQUIRED);
        }
        if (match != null && none != null || none != null && !none.equals("*")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        if (!(request instanceof MultipartHttpServletRequest multipart)
            || multipart.getMultiFileMap().size() != 1 || multipart.getFiles("file").size() != 1
            || !multipart.getParameterMap().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT);
        }
        byte[] content;
        try (var input = file.getInputStream()) {
            content = input.readNBytes(10_000_001);
        }
        Photo photo = service.replace(UUID.fromString(jwt.getSubject()), new Slot(productId, colorId, side),
            match, none != null, content);
        return response(photo, none != null ? 201 : 200);
    }

    @DeleteMapping
    @Operation(summary = "Retire the photo using its current If-Match ETag.")
    @Parameter(name = "If-Match", in = io.swagger.v3.oas.annotations.enums.ParameterIn.HEADER,
        required = true, schema = @Schema(type = "string"))
    public ResponseEntity<PhotoView> retire(
        @AuthenticationPrincipal Jwt jwt,
        @PathVariable UUID productId, @PathVariable @Min(1) @Max(32767) int colorId, @PathVariable Side side,
        HttpServletRequest request
    ) {
        String match = header(request, HttpHeaders.IF_MATCH);
        if (match == null) {
            throw new ResponseStatusException(HttpStatus.PRECONDITION_REQUIRED);
        }
        return response(service.retire(UUID.fromString(jwt.getSubject()),
            new Slot(productId, colorId, side), match), 200);
    }

    @PostMapping("/links")
    @Operation(summary = "Issue private photo and thumbnail links valid for 60 seconds.")
    public ResponseEntity<Links> links(
        @PathVariable UUID productId, @PathVariable @Min(1) @Max(32767) int colorId, @PathVariable Side side
    ) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(service.links(new Slot(productId, colorId, side)));
    }

    private ResponseEntity<PhotoView> response(Photo photo, int status) {
        return ResponseEntity.status(status).cacheControl(CacheControl.noStore())
            .eTag(photo.etag()).body(PhotoView.from(photo));
    }

    private String header(HttpServletRequest request, String name) {
        List<String> values = java.util.Collections.list(request.getHeaders(name));
        if (values.isEmpty()) {
            return null;
        }
        if (values.size() != 1 || values.getFirst().length() > 128) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        return values.getFirst().strip();
    }
}
