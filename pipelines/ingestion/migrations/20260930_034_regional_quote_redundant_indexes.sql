-- Run outside a transaction, after migration032 is valid/ready. Its ordered
-- keys match these exploratory indexes and its INCLUDE columns cover both.
-- Original regional_price_lookup and all price/source history are retained.
DROP INDEX CONCURRENTLY IF EXISTS regional_quote_latest_identity;
