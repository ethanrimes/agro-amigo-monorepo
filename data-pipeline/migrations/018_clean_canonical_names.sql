-- Migration: Clean up canonical product names
-- Description: Strips marker chars (* +), fixes ALL CAPS, expands abbreviations,
--              removes brand names from generic products.
--              Alias table keeps all original raw variants for future matching.
-- Date: 2026-04-14

BEGIN;

-- ============================================================
-- Before renaming, ensure aliases exist for the OLD names
-- so future parsing can still match them.
-- ============================================================

-- Insert current canonical_name as alias if not already there
-- Use ON CONFLICT to skip existing entries (raw_value has a unique constraint)
INSERT INTO alias_product (raw_value, product_id)
SELECT p.canonical_name, p.id
FROM dim_product p
WHERE NOT EXISTS (
    SELECT 1 FROM alias_product a WHERE a.raw_value = p.canonical_name
)
ON CONFLICT (raw_value) DO NOTHING;

-- ============================================================
-- 1. MARKER CHARACTERS — strip *, + from canonical names
-- ============================================================
UPDATE dim_product SET canonical_name = 'Aguacate' WHERE canonical_name = 'Aguacate *';
UPDATE dim_product SET canonical_name = 'Guayaba' WHERE canonical_name = 'Guayaba*';
UPDATE dim_product SET canonical_name = 'Mandarina' WHERE canonical_name = 'Mandarina *';
UPDATE dim_product SET canonical_name = 'Naranja' WHERE canonical_name = 'Naranja *';
UPDATE dim_product SET canonical_name = 'Piña' WHERE canonical_name = 'Piña *';
UPDATE dim_product SET canonical_name = 'Tomate' WHERE canonical_name = 'Tomate *';

-- ============================================================
-- 2. ALL CAPS → Title Case
-- ============================================================
UPDATE dim_product SET canonical_name = 'Brevas' WHERE canonical_name = 'BREVAS';
UPDATE dim_product SET canonical_name = 'Uva isabela' WHERE canonical_name = 'UVA ISABEL';
UPDATE dim_product SET canonical_name = 'Uva red globe' WHERE canonical_name = 'UVA RED GLOB';

-- ============================================================
-- 3. ABBREVIATIONS → merge into expanded version that already exists
-- ============================================================
-- Plátano dom.hart.mad. -> merge into existing Plátano dominico hartón maduro
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.mad.');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.mad.');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.mad.');
DELETE FROM dim_product WHERE canonical_name = 'Plátano dom.hart.mad.';

-- Plátano dom.hart.verd. -> merge into existing Plátano dominico hartón verde
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.verd.');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.verd.');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde' LIMIT 1)
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dom.hart.verd.');
DELETE FROM dim_product WHERE canonical_name = 'Plátano dom.hart.verd.';

-- ============================================================
-- 4. BRANDED PRODUCTS → merge into generic version
--    (The branded alias stays in alias_product for matching)
--    All have a generic counterpart already in Otros procesados.
-- ============================================================
DO $$
DECLARE
    brand_pair RECORD;
    canonical_id UUID;
    branded_id UUID;
BEGIN
    FOR brand_pair IN
        SELECT * FROM (VALUES
            ('Avena en hojuelas Quaker', 'Avena en hojuelas'),
            ('Avena en molida Quaker', 'Avena molida'),
            ('Azúcar morena Incauca', 'Azúcar morena'),
            ('Café molido la bastilla', 'Café molido'),
            ('Chocolate dulce corona', 'Chocolate dulce'),
            ('Galletas saladas taco día', 'Galletas saladas'),
            ('Harina de trigo la nieve', 'Harina de trigo'),
            ('Harina precocida de maíz super arepa', 'Harina precocida de maíz'),
            ('Jugo instantáneo (sobre) frutiño', 'Jugo instantáneo (sobre)'),
            ('Lomitos de atún en lata soberana', 'Lomitos de atún en lata'),
            ('Margarina Dagusto', 'Margarina'),
            ('Mayonesa doy pack fruco', 'Mayonesa doy pack'),
            ('Panela cuadrada morena Villetana', 'Panela cuadrada morena'),
            ('Pastas alimenticias doria', 'Pastas alimenticias'),
            ('Sal yodada refisal', 'Sal yodada'),
            ('Salsa de tomate doy pack fruco', 'Salsa de tomate doy pack'),
            ('Sardinas en lata soberana', 'Sardinas en lata')
        ) AS t(branded_name, generic_name)
    LOOP
        SELECT id INTO canonical_id FROM dim_product WHERE canonical_name = brand_pair.generic_name LIMIT 1;
        SELECT id INTO branded_id FROM dim_product WHERE canonical_name = brand_pair.branded_name LIMIT 1;

        IF canonical_id IS NOT NULL AND branded_id IS NOT NULL THEN
            UPDATE price_observations SET product_id = canonical_id WHERE product_id = branded_id;
            UPDATE supply_observations SET product_id = canonical_id WHERE product_id = branded_id;
            UPDATE alias_product SET product_id = canonical_id WHERE product_id = branded_id;
            DELETE FROM dim_product WHERE id = branded_id;
            RAISE NOTICE 'Merged branded "%" into generic "%"', brand_pair.branded_name, brand_pair.generic_name;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- 5. Clean up any remaining duplicates created by the renames
--    (merge General version into proper-subcategory version)
-- ============================================================
DO $$
DECLARE
    dupe RECORD;
    proper_id UUID;
    general_id UUID;
BEGIN
    FOR dupe IN
        SELECT p.canonical_name, COUNT(*) as cnt
        FROM dim_product p
        GROUP BY p.canonical_name
        HAVING COUNT(*) > 1
    LOOP
        SELECT p.id INTO proper_id
        FROM dim_product p
        JOIN dim_subcategory sc ON p.subcategory_id = sc.id
        WHERE p.canonical_name = dupe.canonical_name
          AND sc.canonical_name NOT LIKE 'General%'
        LIMIT 1;

        SELECT p.id INTO general_id
        FROM dim_product p
        JOIN dim_subcategory sc ON p.subcategory_id = sc.id
        WHERE p.canonical_name = dupe.canonical_name
          AND sc.canonical_name LIKE 'General%'
        LIMIT 1;

        IF proper_id IS NOT NULL AND general_id IS NOT NULL THEN
            UPDATE price_observations SET product_id = proper_id WHERE product_id = general_id;
            UPDATE supply_observations SET product_id = proper_id WHERE product_id = general_id;
            UPDATE alias_product SET product_id = proper_id WHERE product_id = general_id;
            DELETE FROM dim_product WHERE id = general_id;
            RAISE NOTICE 'Merged duplicate "%" (general -> proper)', dupe.canonical_name;
        END IF;
    END LOOP;
END $$;

COMMIT;
