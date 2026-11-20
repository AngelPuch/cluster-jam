package com.clusterjam.catalog.application.ports;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Pixels;

public interface PhotoImages {

    Pixels normalize(byte[] content);
}
