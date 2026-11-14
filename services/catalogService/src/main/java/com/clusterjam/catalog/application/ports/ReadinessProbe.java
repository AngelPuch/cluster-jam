package com.clusterjam.catalog.application.ports;

@FunctionalInterface
public interface ReadinessProbe {

    boolean isAvailable();
}
