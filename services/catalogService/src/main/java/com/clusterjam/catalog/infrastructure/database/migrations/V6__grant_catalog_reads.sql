GRANT SELECT ON app.tipo_prenda, app.talla, app.color TO app_catalogo;
GRANT SELECT (variante_id, stock_fisico, stock_reservado) ON app.inventario TO app_catalogo;
