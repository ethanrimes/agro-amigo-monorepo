-- Migration: Create image attribution tracking table
-- Description: Stores source URL, license, and author for every product/insumo
--              image downloaded from external sources (Wikimedia Commons,
--              fruits-360, Openverse). Required for CC license compliance.
-- Date: 2026-04-14

CREATE TABLE IF NOT EXISTS image_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What this image is for
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('product', 'insumo')),
    entity_slug VARCHAR(500) NOT NULL,

    -- Where it lives in Supabase storage
    storage_path VARCHAR(500) NOT NULL,

    -- Source attribution (the important part)
    source_name VARCHAR(100) NOT NULL,       -- 'wikimedia', 'fruits360', 'openverse', 'reused'
    source_url TEXT,                          -- direct link to image page (NOT the raw file)
    source_image_url TEXT,                    -- direct link to original image file
    license VARCHAR(100),                     -- e.g. 'CC BY-SA 4.0', 'CC0', 'CC BY 2.0'
    license_url TEXT,                         -- link to the license deed
    author VARCHAR(500),                      -- original creator/photographer name
    image_title TEXT,                         -- title as given by source

    -- When we fetched it
    fetched_at TIMESTAMP DEFAULT NOW(),

    -- Prevent duplicate attributions per entity
    UNIQUE(entity_type, entity_slug)
);

COMMENT ON TABLE image_attributions IS 'Source attribution for product/insumo images. Required for Creative Commons license compliance.';

-- Index for fast lookups by entity
CREATE INDEX IF NOT EXISTS idx_image_attributions_entity
    ON image_attributions(entity_type, entity_slug);

-- RLS: allow public read
ALTER TABLE image_attributions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read on image_attributions"
    ON image_attributions FOR SELECT
    USING (true);
