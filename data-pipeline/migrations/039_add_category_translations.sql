-- Migration: Add English translations for category-like dimension tables
-- Description: Adds a `name_en` column to dim_category, dim_subcategory,
--              dim_insumo_grupo, and dim_insumo_subgrupo so the iPhone app
--              can render English labels when the user switches the app to
--              English mode. Spanish `canonical_name` remains the source of
--              truth for matching/identity; `name_en` is purely cosmetic.
-- Date: 2026-05-24

-- ============================================================
-- Schema: add name_en columns
-- ============================================================

ALTER TABLE dim_category          ADD COLUMN IF NOT EXISTS name_en VARCHAR(200);
ALTER TABLE dim_subcategory       ADD COLUMN IF NOT EXISTS name_en VARCHAR(200);
ALTER TABLE dim_insumo_grupo      ADD COLUMN IF NOT EXISTS name_en VARCHAR(200);
ALTER TABLE dim_insumo_subgrupo   ADD COLUMN IF NOT EXISTS name_en VARCHAR(300);

COMMENT ON COLUMN dim_category.name_en        IS 'English display name for the category';
COMMENT ON COLUMN dim_subcategory.name_en     IS 'English display name for the subcategory';
COMMENT ON COLUMN dim_insumo_grupo.name_en    IS 'English display name for the insumo group';
COMMENT ON COLUMN dim_insumo_subgrupo.name_en IS 'English display name for the insumo subgroup';

-- ============================================================
-- Data: product categories (8 rows)
-- ============================================================

UPDATE dim_category SET name_en = CASE canonical_name
    WHEN 'Carnes'                          THEN 'Meats'
    WHEN 'Frutas'                          THEN 'Fruits'
    WHEN 'Granos y cereales'               THEN 'Grains and cereals'
    WHEN 'Lácteos y huevos'                THEN 'Dairy and eggs'
    WHEN 'Pescados'                        THEN 'Fish'
    WHEN 'Procesados'                      THEN 'Processed foods'
    WHEN 'Tubérculos, raíces y plátanos'   THEN 'Tubers, roots and plantains'
    WHEN 'Verduras y hortalizas'           THEN 'Vegetables'
    ELSE name_en
END;

-- ============================================================
-- Data: product subcategories (33 rows)
-- ============================================================

UPDATE dim_subcategory SET name_en = CASE canonical_name
    WHEN 'Aceites y grasas'                              THEN 'Oils and fats'
    WHEN 'Arroz en molino'                               THEN 'Mill rice'
    WHEN 'Azúcar'                                        THEN 'Sugar'
    WHEN 'Carne de cerdo'                                THEN 'Pork'
    WHEN 'Carne de res'                                  THEN 'Beef'
    WHEN 'Cebollas'                                      THEN 'Onions'
    WHEN 'Cereales'                                      THEN 'Cereals'
    WHEN 'Cítricos'                                      THEN 'Citrus'
    WHEN 'Frescos y congelados'                          THEN 'Fresh and frozen'
    WHEN 'General (Carnes)'                              THEN 'General (Meats)'
    WHEN 'General (Frutas)'                              THEN 'General (Fruits)'
    WHEN 'General (Granos y cereales)'                   THEN 'General (Grains and cereals)'
    WHEN 'General (Lácteos y huevos)'                    THEN 'General (Dairy and eggs)'
    WHEN 'General (Pescados)'                            THEN 'General (Fish)'
    WHEN 'General (Procesados)'                          THEN 'General (Processed foods)'
    WHEN 'General (Tubérculos, raíces y plátanos)'       THEN 'General (Tubers, roots and plantains)'
    WHEN 'General (Verduras y hortalizas)'               THEN 'General (Vegetables)'
    WHEN 'Granos'                                        THEN 'Grains'
    WHEN 'Hortalizas'                                    THEN 'Vegetables'
    WHEN 'Huevos'                                        THEN 'Eggs'
    WHEN 'Lácteos'                                       THEN 'Dairy'
    WHEN 'Leche cruda en finca'                          THEN 'Raw farm milk'
    WHEN 'Leguminosas'                                   THEN 'Legumes'
    WHEN 'Otras frutas'                                  THEN 'Other fruits'
    WHEN 'Otras hortalizas y verduras'                   THEN 'Other vegetables'
    WHEN 'Otros procesados'                              THEN 'Other processed foods'
    WHEN 'Otros tuberculos'                              THEN 'Other tubers'
    WHEN 'Panela'                                        THEN 'Panela (raw cane sugar)'
    WHEN 'Papa'                                          THEN 'Potato'
    WHEN 'Plátano'                                       THEN 'Plantain'
    WHEN 'Pollo'                                         THEN 'Chicken'
    WHEN 'Tomates'                                       THEN 'Tomatoes'
    WHEN 'Yuca'                                          THEN 'Cassava'
    WHEN 'Zanahorias'                                    THEN 'Carrots'
    ELSE name_en
END;

-- ============================================================
-- Data: insumo grupos (3 rows)
-- ============================================================

UPDATE dim_insumo_grupo SET name_en = CASE canonical_name
    WHEN 'Factores de producción'  THEN 'Production factors'
    WHEN 'Insumos agrícolas'       THEN 'Agricultural inputs'
    WHEN 'Insumos pecuarios'       THEN 'Livestock inputs'
    ELSE name_en
END;

-- ============================================================
-- Data: insumo subgrupos (19 rows)
-- ============================================================

UPDATE dim_insumo_subgrupo SET name_en = CASE canonical_name
    WHEN 'Alimentos balanceados, suplementos, coadyuvantes, adsorbentes, enzimas y aditivos'
        THEN 'Balanced feeds, supplements, adjuvants, adsorbents, enzymes and additives'
    WHEN 'Antibióticos, antimicóticos y antiparasitarios'
        THEN 'Antibiotics, antifungals and antiparasitics'
    WHEN 'Antisépticos, desinfectantes e higiene'
        THEN 'Antiseptics, disinfectants and hygiene'
    WHEN 'Arrendamiento de tierras'
        THEN 'Land leasing'
    WHEN 'Bioinsumos'
        THEN 'Bioinputs'
    WHEN 'Coadyuvantes, molusquicidas, reguladores fisiológicos y otros'
        THEN 'Adjuvants, molluscicides, physiological regulators and others'
    WHEN 'Elementos agropecuarios'
        THEN 'Agricultural elements'
    WHEN 'Empaques agropecuarios'
        THEN 'Agricultural packaging'
    WHEN 'Especies productivas'
        THEN 'Productive species'
    WHEN 'Fertilizantes, enmiendas y acondicionadores de suelo'
        THEN 'Fertilizers, amendments and soil conditioners'
    WHEN 'Fungicidas'
        THEN 'Fungicides'
    WHEN 'Herbicidas'
        THEN 'Herbicides'
    WHEN 'Hormonales'
        THEN 'Hormonals'
    WHEN 'Insecticidas, acaricidas y nematicidas'
        THEN 'Insecticides, acaricides and nematicides'
    WHEN 'Insecticidas, plaguicidas y repelentes'
        THEN 'Insecticides, pesticides and repellents'
    WHEN 'Jornales'
        THEN 'Day labor'
    WHEN 'Material de propagación'
        THEN 'Propagation material'
    WHEN 'Medicamentos'
        THEN 'Medications'
    WHEN 'Vitaminas, sales y minerales'
        THEN 'Vitamins, salts and minerals'
    ELSE name_en
END;
