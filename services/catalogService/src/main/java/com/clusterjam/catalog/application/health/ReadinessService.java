package com.clusterjam.catalog.application.health;

import com.clusterjam.catalog.application.ports.ReadinessProbe;

public class ReadinessService {

    private final ReadinessProbe probe;

    public ReadinessService(ReadinessProbe probe) {
        this.probe = probe;
    }

    public boolean isReady() {
        return probe.isAvailable();
    }
}
