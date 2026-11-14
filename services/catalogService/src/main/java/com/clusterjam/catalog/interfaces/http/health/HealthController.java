package com.clusterjam.catalog.interfaces.http.health;

import com.clusterjam.catalog.application.health.ReadinessService;
import com.clusterjam.catalog.interfaces.http.health.dto.HealthResponse;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/health", produces = MediaType.APPLICATION_JSON_VALUE)
public class HealthController {

    private final ReadinessService readiness;

    public HealthController(ReadinessService readiness) {
        this.readiness = readiness;
    }

    @GetMapping("/live")
    public ResponseEntity<HealthResponse> live() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(HealthResponse.OK);
    }

    @GetMapping("/ready")
    public ResponseEntity<HealthResponse> ready() {
        if (readiness.isReady()) {
            return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(HealthResponse.OK);
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .cacheControl(CacheControl.noStore())
            .body(HealthResponse.UNAVAILABLE);
    }
}
