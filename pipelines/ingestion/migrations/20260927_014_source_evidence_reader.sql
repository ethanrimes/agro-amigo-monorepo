-- Source-viewer fallback reads immutable correction evidence for originals whose
-- existing historical rows predate the date-resolution metadata.
GRANT SELECT ON retained_record TO agro_reader;
