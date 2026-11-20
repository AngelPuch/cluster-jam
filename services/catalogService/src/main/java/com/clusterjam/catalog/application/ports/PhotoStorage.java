package com.clusterjam.catalog.application.ports;

public interface PhotoStorage {

    String bucket();

    void upload(String bucket, String key, byte[] content);

    void delete(String bucket, String key);

    String sign(String bucket, String key, int seconds);
}
