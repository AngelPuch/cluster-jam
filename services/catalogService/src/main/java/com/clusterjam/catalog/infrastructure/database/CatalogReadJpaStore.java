package com.clusterjam.catalog.infrastructure.database;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.ports.CatalogReadStore;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Card;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Commerce;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Compatibility;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Filter;
import com.clusterjam.catalog.application.reads.CatalogReadModels.PhotoRef;
import com.clusterjam.catalog.application.reads.CatalogReadModels.ProductSize;
import com.clusterjam.catalog.application.reads.CatalogReadModels.References;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Variant;
import com.clusterjam.catalog.infrastructure.database.models.CatalogPhotoEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogProductEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogReferenceEntities;
import com.clusterjam.catalog.infrastructure.database.models.CatalogVariantEntity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Repository;

@Repository
public class CatalogReadJpaStore implements CatalogReadStore {

    private static final String VARIANTS = """
        from CatalogVariantEntity v
        join CatalogProductEntity p on p.id = v.productId
        join CatalogInventoryEntity i on i.variantId = v.id
        """;
    private static final String PHOTO_VISIBLE = """
        f.active = true
        and exists (select p.id from CatalogProductEntity p
            where p.id = f.productId and p.status = :published)
        and exists (select v.id from CatalogVariantEntity v
            where v.productId = f.productId and v.colorId = f.colorId and v.status = :published)
        """;

    private final EntityManager entities;

    public CatalogReadJpaStore(EntityManager entities) {
        this.entities = entities;
    }

    @Override
    public List<Card> search(Filter filter, UUID after, int limit) {
        StringBuilder where = new StringBuilder(" where p.status = :published and v.status = :published");
        Map<String, Object> parameters = new HashMap<>();
        parameters.put("published", Status.PUBLISHED);
        add(where, parameters, "p.id > :after", "after", after);
        if (filter.name() != null) {
            String literal = filter.name().replace("!", "!!").replace("%", "!%").replace("_", "!_");
            add(where, parameters, "lower(p.name) like :name escape '!'", "name", "%" + literal + "%");
        }
        add(where, parameters, "p.typeId = :typeId", "typeId", small(filter.typeId()));
        add(where, parameters, "v.sizeId = :sizeId", "sizeId", small(filter.sizeId()));
        add(where, parameters, "v.colorId = :colorId", "colorId", small(filter.colorId()));
        add(where, parameters, "v.basePriceCents >= :minPrice", "minPrice", filter.minPrice());
        add(where, parameters, "v.basePriceCents <= :maxPrice", "maxPrice", filter.maxPrice());

        TypedQuery<Object[]> query = entities.createQuery(
            "select p, min(v.basePriceCents), sum(i.physical - i.reserved) " + VARIANTS
                + where + " group by p order by p.id", Object[].class);
        parameters.forEach(query::setParameter);
        var rows = query.setMaxResults(limit).getResultList();
        var ids = rows.stream().map(row -> ((CatalogProductEntity) row[0]).toProduct().id()).toList();
        Map<UUID, PhotoRef> covers = covers(ids);
        return rows.stream().map(row -> {
            Product product = ((CatalogProductEntity) row[0]).toProduct();
            return new Card(product.id(), product.typeId(), product.name(), ((Number) row[1]).longValue(),
                "MXN", ((Number) row[2]).longValue() > 0, covers.get(product.id()));
        }).toList();
    }

    private Short small(Integer value) {
        return value == null ? null : value.shortValue();
    }

    private void add(StringBuilder where, Map<String, Object> parameters, String clause, String name, Object value) {
        if (value != null) {
            where.append(" and ").append(clause);
            parameters.put(name, value);
        }
    }

    private Map<UUID, PhotoRef> covers(List<UUID> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }
        var rows = entities.createQuery("""
            select f from CatalogPhotoEntity f
            where f.productId in :ids and f.side = 'FRENTE' and
            """ + PHOTO_VISIBLE + """
            and f.colorId = (
                select min(g.colorId) from CatalogPhotoEntity g
                where g.productId = f.productId and g.active = true and g.side = 'FRENTE'
                and exists (select v.id from CatalogVariantEntity v
                    where v.productId = g.productId and v.colorId = g.colorId and v.status = :published)
            )
            """, CatalogPhotoEntity.class)
            .setParameter("ids", ids).setParameter("published", Status.PUBLISHED).getResultList();
        Map<UUID, PhotoRef> result = new HashMap<>();
        for (var row : rows) {
            Photo photo = row.toPhoto();
            result.put(photo.slot().productId(), reference(photo));
        }
        return result;
    }

    @Override
    public Optional<Product> publishedProduct(UUID id) {
        return entities.createQuery("""
            select p from CatalogProductEntity p where p.id = :id and p.status = :published
            and exists (select v.id from CatalogVariantEntity v
                where v.productId = p.id and v.status = :published)
            """, CatalogProductEntity.class).setParameter("id", id)
            .setParameter("published", Status.PUBLISHED).getResultStream().findFirst()
            .map(CatalogProductEntity::toProduct);
    }

    @Override
    public List<Variant> publishedVariants(UUID productId, UUID after, int limit) {
        String condition = after == null ? "" : " and v.id > :after";
        var query = entities.createQuery("select v, i.physical - i.reserved " + VARIANTS + """
             where p.id = :product and p.status = :published and v.status = :published
            """ + condition + " order by v.id", Object[].class)
            .setParameter("product", productId).setParameter("published", Status.PUBLISHED);
        if (after != null) {
            query.setParameter("after", after);
        }
        return query.setMaxResults(limit).getResultList().stream().map(row -> {
            var variant = ((CatalogVariantEntity) row[0]).toVariant();
            return new Variant(variant.id(), variant.productId(), variant.sizeId(), variant.colorId(),
                variant.sku(), variant.basePriceCents(), "MXN", ((Number) row[1]).intValue());
        }).toList();
    }

    @Override
    public List<PhotoRef> photos(UUID productId, List<Integer> colors) {
        if (colors.isEmpty()) {
            return List.of();
        }
        return entities.createQuery("""
            select f from CatalogPhotoEntity f where f.productId = :product and f.colorId in :colors
            and f.active = true order by f.colorId, f.side
            """, CatalogPhotoEntity.class)
            .setParameter("product", productId)
            .setParameter("colors", colors.stream().map(Integer::shortValue).toList())
            .getResultList().stream().map(row -> reference(row.toPhoto())).toList();
    }

    private PhotoRef reference(Photo photo) {
        Slot slot = photo.slot();
        return new PhotoRef(slot.colorId(), slot.side(), "/api/v1/products/" + slot.productId()
            + "/colors/" + slot.colorId() + "/photos/" + slot.side() + "/links");
    }

    @Override
    public Optional<Photo> publishedPhoto(Slot slot) {
        return entities.createQuery("""
            select f from CatalogPhotoEntity f where f.productId = :product and f.colorId = :color
            and f.side = :side and
            """ + PHOTO_VISIBLE, CatalogPhotoEntity.class)
            .setParameter("product", slot.productId()).setParameter("color", (short) slot.colorId())
            .setParameter("side", slot.side() == Side.FRONT ? "FRENTE" : "ESPALDA")
            .setParameter("published", Status.PUBLISHED).getResultStream().findFirst().map(CatalogPhotoEntity::toPhoto);
    }

    @Override
    public Optional<Compatibility> compatibility(UUID variantId, boolean commerce) {
        var query = entities.createQuery(
            "select v, p, i.physical - i.reserved " + VARIANTS + " where v.id = :id", Object[].class);
        return query.setParameter("id", variantId).getResultStream().findFirst().map(row -> {
            var variant = ((CatalogVariantEntity) row[0]).toVariant();
            Product product = ((CatalogProductEntity) row[1]).toProduct();
            Commerce quote = null;
            if (commerce) {
                quote = new Commerce(variant.basePriceCents(), "MXN", ((Number) row[2]).intValue());
            }
            return new Compatibility(variant.id(), product.id(), variant.sizeId(), variant.colorId(),
                product.status(), variant.status(),
                product.status() == Status.PUBLISHED && variant.status() == Status.PUBLISHED, quote);
        });
    }

    @Override
    public Optional<ProductSize> productSize(UUID productId, int sizeId) {
        return entities.createQuery("""
            select p, sum(case when v.status = :published then 1 else 0 end)
            from CatalogProductEntity p join CatalogVariantEntity v on v.productId = p.id
            where p.id = :id and v.sizeId = :size group by p
            """, Object[].class).setParameter("id", productId).setParameter("size", (short) sizeId)
            .setParameter("published", Status.PUBLISHED).getResultStream().findFirst().map(row -> {
                Product product = ((CatalogProductEntity) row[0]).toProduct();
                boolean variants = ((Number) row[1]).longValue() > 0;
                return new ProductSize(productId, sizeId, product.status(), variants,
                    product.status() == Status.PUBLISHED && variants);
            });
    }

    @Override
    public References references() {
        var types = entities.createQuery("from CatalogType t order by t.id", CatalogReferenceEntities.Type.class)
            .getResultList().stream().map(CatalogReferenceEntities.Type::view).toList();
        var sizes = entities.createQuery(
                "from CatalogSize s order by s.displayOrder", CatalogReferenceEntities.Size.class)
            .getResultList().stream().map(CatalogReferenceEntities.Size::view).toList();
        var colors = entities.createQuery("from CatalogColor c order by c.id", CatalogReferenceEntities.Color.class)
            .getResultList().stream().map(CatalogReferenceEntities.Color::view).toList();
        return new References(types, sizes, colors);
    }
}
