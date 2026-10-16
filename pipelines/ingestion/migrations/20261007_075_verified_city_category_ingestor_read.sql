-- The exact 073 price-resolution INSERT trigger reads this reviewed category
-- view as agro_ingestor. Match the already granted reader access without
-- altering prices, source originals, conflicts, or view definitions.
GRANT SELECT ON public.verified_city_pdf_category_resolution TO agro_ingestor;
