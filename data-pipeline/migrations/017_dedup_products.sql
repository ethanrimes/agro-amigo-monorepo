-- Migration: Deduplicate dim_product entries
-- Description: Merges OCR artifacts, run-together words, marker variants,
--              misplaced products, and non-product entries. Updates all FKs:
--              price_observations, supply_observations, alias_product.
-- Date: 2026-04-14

BEGIN;

-- ============================================================
-- HELPER: merge function
-- For each (old_id -> canonical_id) pair:
--   1. Update price_observations.product_id
--   2. Update supply_observations.product_id
--   3. Update or delete alias_product entries
--   4. Delete the old dim_product row
-- ============================================================

-- We'll do this inline since PL/pgSQL functions require more setup.
-- Each block: reassign observations, clean aliases, delete dupe.

-- ============================================================
-- 0. DELETE NON-PRODUCT ENTRIES (city names, totals — all have 0 obs)
-- ============================================================
DELETE FROM alias_product WHERE product_id IN (
    SELECT id FROM dim_product WHERE canonical_name IN (
        'Florencia (Caquetá)', 'Ipiales (Nariño), Centro de acopio',
        'Manizales, Centro Galerías', 'Santa Marta (Magdalena)',
        'Valledupar, Mercabastos', 'Valledupar, Mercado Nuevo', 'Total'
    )
);
DELETE FROM dim_product WHERE canonical_name IN (
    'Florencia (Caquetá)', 'Ipiales (Nariño), Centro de acopio',
    'Manizales, Centro Galerías', 'Santa Marta (Magdalena)',
    'Valledupar, Mercabastos', 'Valledupar, Mercado Nuevo', 'Total'
);

-- ============================================================
-- 1. OCR DOUBLED-CHARACTER ARTIFACTS (0 obs each — just delete)
-- ============================================================
DELETE FROM alias_product WHERE product_id IN (
    SELECT id FROM dim_product WHERE canonical_name IN (
        'CCaarrnnee ddee cceerrddoo,, ttoocciinnoo bbaarrrriiggaa',
        'LLeecchhuuggaa BBaattaavviiaa'
    )
);
DELETE FROM dim_product WHERE canonical_name IN (
    'CCaarrnnee ddee cceerrddoo,, ttoocciinnoo bbaarrrriiggaa',
    'LLeecchhuuggaa BBaattaavviiaa'
);

-- ============================================================
-- 2. PAPA NEGRA VARIANTS → merge all into "Papa negra *" (has 25359 obs)
--    Keep "Papa negra *" and rename it to "Papa negra"
-- ============================================================

-- Move observations from variants to the canonical one
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa negra *')
    WHERE product_id IN (SELECT id FROM dim_product WHERE canonical_name IN ('Papa negr*', 'Papa negra+', 'Papa nwgra*'));
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa negra *')
    WHERE product_id IN (SELECT id FROM dim_product WHERE canonical_name IN ('Papa negr*', 'Papa negra+', 'Papa nwgra*'));

-- Update aliases to point to canonical
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa negra *')
    WHERE product_id IN (SELECT id FROM dim_product WHERE canonical_name IN ('Papa negr*', 'Papa negra+', 'Papa nwgra*'));

-- Delete the variant dim_product rows
DELETE FROM dim_product WHERE canonical_name IN ('Papa negr*', 'Papa negra+', 'Papa nwgra*');

-- Rename the canonical to clean name
UPDATE dim_product SET canonical_name = 'Papa negra' WHERE canonical_name = 'Papa negra *';

-- ============================================================
-- 3. RUN-TOGETHER WORDS → merge into spaced version
--    Strategy: move obs from run-together to spaced, delete run-together
-- ============================================================

-- Helper: for each pair (run_together, canonical), do the merge.
-- Most run-togethers have 0 obs so this is mostly just cleanup.

-- Carne de res, bolade brazo -> Carne de res, bola de brazo
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de brazo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade brazo');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de brazo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade brazo');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de brazo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade brazo');
DELETE FROM dim_product WHERE canonical_name = 'Carne de res, bolade brazo';

-- Carne de res, bolade pierna -> Carne de res, bola de pierna
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de pierna')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade pierna');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de pierna')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade pierna');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bola de pierna')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Carne de res, bolade pierna');
DELETE FROM dim_product WHERE canonical_name = 'Carne de res, bolade pierna';

-- Plátano dominico hartónmaduro -> Plátano dominico hartón maduro
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartónmaduro');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartónmaduro');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón maduro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartónmaduro');
DELETE FROM dim_product WHERE canonical_name = 'Plátano dominico hartónmaduro';

-- Plátanodominico hartón verde -> Plátano dominico hartón verde
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanodominico hartón verde');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanodominico hartón verde');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano dominico hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanodominico hartón verde');
DELETE FROM dim_product WHERE canonical_name = 'Plátanodominico hartón verde';

-- Plátanohartónverde -> Plátano hartón verde (General)
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanohartónverde');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanohartónverde');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátano hartón verde')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Plátanohartónverde');
DELETE FROM dim_product WHERE canonical_name = 'Plátanohartónverde';

-- Aguacatecomún -> Aguacate común
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate común')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatecomún');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate común')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatecomún');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate común')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatecomún');
DELETE FROM dim_product WHERE canonical_name = 'Aguacatecomún';

-- Aguacatepapelillo -> Aguacate papelillo
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate papelillo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatepapelillo');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate papelillo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatepapelillo');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacate papelillo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Aguacatepapelillo');
DELETE FROM dim_product WHERE canonical_name = 'Aguacatepapelillo';

-- Bananocriollo -> Banano criollo
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Banano criollo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bananocriollo');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Banano criollo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bananocriollo');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Banano criollo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bananocriollo');
DELETE FROM dim_product WHERE canonical_name = 'Bananocriollo';

-- Melóncantalup -> Melón cantalup (use Melón Cantalup from General if exists)
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melón Cantalup')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melóncantalup');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melón Cantalup')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melóncantalup');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melón Cantalup')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Melóncantalup');
DELETE FROM dim_product WHERE canonical_name = 'Melóncantalup';

-- Uvaredglobenacional -> Uva red globe nacional
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uva red globe nacional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uvaredglobenacional');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uva red globe nacional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uvaredglobenacional');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uva red globe nacional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Uvaredglobenacional');
DELETE FROM dim_product WHERE canonical_name = 'Uvaredglobenacional';

-- Bagrerayadoentero congelado -> Bagre rayado entero congelado
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagre rayado entero congelado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagrerayadoentero congelado');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagre rayado entero congelado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagrerayadoentero congelado');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagre rayado entero congelado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Bagrerayadoentero congelado');
DELETE FROM dim_product WHERE canonical_name = 'Bagrerayadoentero congelado';

-- Basa,enterocongelado importado -> Basa, entero congelado importado
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa, entero congelado importado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa,enterocongelado importado');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa, entero congelado importado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa,enterocongelado importado');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa, entero congelado importado')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Basa,enterocongelado importado');
DELETE FROM dim_product WHERE canonical_name = 'Basa,enterocongelado importado';

-- Calamaranillos -> Calamar anillos
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamar anillos')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamaranillos');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamar anillos')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamaranillos');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamar anillos')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Calamaranillos');
DELETE FROM dim_product WHERE canonical_name = 'Calamaranillos';

-- Camaróntigre precocido seco -> Camarón tigre precocido seco
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tigre precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntigre precocido seco');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tigre precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntigre precocido seco');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tigre precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntigre precocido seco');
DELETE FROM dim_product WHERE canonical_name = 'Camaróntigre precocido seco';

-- Camaróntitíprecocido seco -> Camarón tití precocido seco
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tití precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntitíprecocido seco');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tití precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntitíprecocido seco');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camarón tití precocido seco')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Camaróntitíprecocido seco');
DELETE FROM dim_product WHERE canonical_name = 'Camaróntitíprecocido seco';

-- Cebollajuncaaquitania -> just rename it (no separate "Cebolla junca aquitania" exists)
UPDATE dim_product SET canonical_name = 'Cebolla junca aquitania' WHERE canonical_name = 'Cebollajuncaaquitania';

-- Cafémolido -> Café molido
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Café molido')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Cafémolido');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Café molido')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Cafémolido');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Café molido')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Cafémolido');
DELETE FROM dim_product WHERE canonical_name = 'Cafémolido';

-- Fríjolcargamantorojo -> Fríjol cargamanto rojo
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol cargamanto rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolcargamantorojo');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol cargamanto rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolcargamantorojo');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol cargamanto rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolcargamantorojo');
DELETE FROM dim_product WHERE canonical_name = 'Fríjolcargamantorojo';

-- Fríjolverdecargamanto -> Fríjol verde cargamanto
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol verde cargamanto')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolverdecargamanto');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol verde cargamanto')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolverdecargamanto');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjol verde cargamanto')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Fríjolverdecargamanto');
DELETE FROM dim_product WHERE canonical_name = 'Fríjolverdecargamanto';

-- Huevorojoaa -> Huevo rojo AA
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevo rojo AA')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevorojoaa');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevo rojo AA')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevorojoaa');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevo rojo AA')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Huevorojoaa');
DELETE FROM dim_product WHERE canonical_name = 'Huevorojoaa';

-- Papacriollasucia -> Papa criolla sucia
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa criolla sucia')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papacriollasucia');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa criolla sucia')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papacriollasucia');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa criolla sucia')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papacriollasucia');
DELETE FROM dim_product WHERE canonical_name = 'Papacriollasucia';

-- Papapardapastusa -> Papa parda pastusa
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa parda pastusa')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papapardapastusa');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa parda pastusa')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papapardapastusa');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa parda pastusa')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papapardapastusa');
DELETE FROM dim_product WHERE canonical_name = 'Papapardapastusa';

-- Papaúnica -> Papa única
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa única')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papaúnica');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa única')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papaúnica');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papa única')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Papaúnica');
DELETE FROM dim_product WHERE canonical_name = 'Papaúnica';

-- Pepinocohombro (in Otras hortalizas) -> Pepino cohombro (in General, has 31256 obs)
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino cohombro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinocohombro');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino cohombro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinocohombro');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino cohombro')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinocohombro');
DELETE FROM dim_product WHERE canonical_name = 'Pepinocohombro';

-- Pepinoderellenar -> Pepino de rellenar
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino de rellenar')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinoderellenar');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino de rellenar')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinoderellenar');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepino de rellenar')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Pepinoderellenar');
DELETE FROM dim_product WHERE canonical_name = 'Pepinoderellenar';

-- Tomatechontoregional -> Tomate chonto regional
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomate chonto regional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomatechontoregional');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomate chonto regional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomatechontoregional');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomate chonto regional')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Tomatechontoregional');
DELETE FROM dim_product WHERE canonical_name = 'Tomatechontoregional';

-- Azúcarmorena -> Azúcar morena
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar morena')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarmorena');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar morena')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarmorena');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar morena')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarmorena');
DELETE FROM dim_product WHERE canonical_name = 'Azúcarmorena';

-- Azúcarsulfitada -> Azúcar sulfitada
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar sulfitada')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarsulfitada');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar sulfitada')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarsulfitada');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcar sulfitada')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Azúcarsulfitada');
DELETE FROM dim_product WHERE canonical_name = 'Azúcarsulfitada';

-- Yucaica -> Yuca ica (rename, it's the only entry)
UPDATE dim_product SET canonical_name = 'Yuca ica' WHERE canonical_name = 'Yucaica';

-- Yucallanera -> Yuca llanera
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yuca llanera')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yucallanera');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yuca llanera')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yucallanera');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yuca llanera')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Yucallanera');
DELETE FROM dim_product WHERE canonical_name = 'Yucallanera';

-- Rábanorojo -> Rábano rojo
UPDATE price_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábano rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábanorojo');
UPDATE supply_observations SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábano rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábanorojo');
UPDATE alias_product SET product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábano rojo')
    WHERE product_id = (SELECT id FROM dim_product WHERE canonical_name = 'Rábanorojo');
DELETE FROM dim_product WHERE canonical_name = 'Rábanorojo';

-- ============================================================
-- 4. MISPLACED MEATS in General (Frutas) - all 0 obs, merge into Carnes equivalents
-- ============================================================

-- These all have 0 observations and are duplicates of properly-categorized products.
-- Safe to delete aliases then delete the product.
DELETE FROM alias_product WHERE product_id IN (
    SELECT id FROM dim_product WHERE canonical_name IN (
        'Carne cerdo brazo sin hueso', 'Carne cerdo costilla', 'Carne cerdo en canal',
        'Carne cerdo espinazo', 'Carne cerdo lomo sin hueso', 'Carne cerdo pernil sin hueso',
        'Carne cerdo tocino barriga', 'Carne cerdo tocino papada',
        'Carne de cerdo, brazo costilla', 'Carne de cerdo, Espinazo',
        'Carne de res cadera', 'Carne de res chatas', 'Carne de res cogote',
        'Carne de res lomo de brazo',
        'Carne res bola de brazo', 'Carne res bola de pierna', 'Carne res centro de pierna',
        'Carne res costilla', 'Carne res falda', 'Carne res lomo fino',
        'Carne res morrillo', 'Carne res muchacho', 'Carne res paletero',
        'Carne res pecho', 'Carne res punta de anca', 'Carne res sobrebarriga'
    )
);
DELETE FROM dim_product WHERE canonical_name IN (
    'Carne cerdo brazo sin hueso', 'Carne cerdo costilla', 'Carne cerdo en canal',
    'Carne cerdo espinazo', 'Carne cerdo lomo sin hueso', 'Carne cerdo pernil sin hueso',
    'Carne cerdo tocino barriga', 'Carne cerdo tocino papada',
    'Carne de cerdo, brazo costilla', 'Carne de cerdo, Espinazo',
    'Carne de res cadera', 'Carne de res chatas', 'Carne de res cogote',
    'Carne de res lomo de brazo',
    'Carne res bola de brazo', 'Carne res bola de pierna', 'Carne res centro de pierna',
    'Carne res costilla', 'Carne res falda', 'Carne res lomo fino',
    'Carne res morrillo', 'Carne res muchacho', 'Carne res paletero',
    'Carne res pecho', 'Carne res punta de anca', 'Carne res sobrebarriga'
);

-- ============================================================
-- 5. OTHER MISPLACED in General (Frutas) — 0 obs, not fruits
-- ============================================================
DELETE FROM alias_product WHERE product_id IN (
    SELECT id FROM dim_product WHERE canonical_name IN (
        'Aceite depalma', 'Aceite vegetal Palma', 'Aceitevegetalmezcla',
        'Avena enhojuelas', 'Bocachico importado congelad',
        'Cebolla Cab. Blanca', 'Cebolla Cab. Roja',
        'Fríjol niña calima', 'Lomitos de atún enlata', 'Sardinas enlata',
        'Jugo instantáneo(sobre)', 'M aíz blanco trillado',
        'Papa Ruby', 'Yuca ICA', 'Azúcar Sulfitada', 'Fécula de Maíz'
    )
);
DELETE FROM dim_product WHERE canonical_name IN (
    'Aceite depalma', 'Aceite vegetal Palma', 'Aceitevegetalmezcla',
    'Avena enhojuelas', 'Bocachico importado congelad',
    'Cebolla Cab. Blanca', 'Cebolla Cab. Roja',
    'Fríjol niña calima', 'Lomitos de atún enlata', 'Sardinas enlata',
    'Jugo instantáneo(sobre)', 'M aíz blanco trillado',
    'Papa Ruby', 'Yuca ICA', 'Azúcar Sulfitada', 'Fécula de Maíz'
);

-- ============================================================
-- 6. CASE-ONLY DUPLICATES where both exist
--    Huevo blanco a / Huevo blanco A — keep uppercase version (proper subcategory)
-- ============================================================
-- The Huevos subcategory already has properly cased versions (Huevo blanco A, etc.)
-- The lowercase 'a', 'aa', 'b' variants are in the same subcategory — merge into uppercase
-- (These have UNIQUE constraint on canonical_name, so they're actually different rows)
-- Leave these as-is since they're different sizes (A, AA, B, extra) — these aren't dupes.

-- Fríjol Uribe rosado — only one entry exists, just normalize case
UPDATE dim_product SET canonical_name = 'Fríjol uribe rosado' WHERE canonical_name = 'Fríjol Uribe rosado';

COMMIT;
