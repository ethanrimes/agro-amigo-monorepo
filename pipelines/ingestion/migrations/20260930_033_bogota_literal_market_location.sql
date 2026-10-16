-- Attach the older literal city spelling to the already verified official
-- municipality. Original market names and immutable price rows stay intact.
UPDATE market literal
SET municipality_id=canonical.municipality_id,region=canonical.region
FROM market canonical
WHERE literal.id='dane-city-bogota-corabastos'
  AND literal.name='Bogotá, Corabastos'
  AND literal.region='' AND literal.municipality_id IS NULL
  AND canonical.id='sipsa-bogota-d-c-corabastos'
  AND canonical.municipality_id='11001';
