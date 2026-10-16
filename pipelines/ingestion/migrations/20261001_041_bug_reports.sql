-- Private delivery outbox. The web role can submit a validated report through
-- one function but cannot enumerate messages or reply addresses.
CREATE TABLE IF NOT EXISTS bug_report (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message text NOT NULL CHECK (length(message) BETWEEN 10 AND 5000),
  reply_email text CHECK (length(reply_email)<=254 AND reply_email !~ E'[\\r\\n]'),
  page_path text NOT NULL DEFAULT '' CHECK (length(page_path)<=1000 AND page_path !~ E'[\\r\\n]'),
  source_document_id text REFERENCES source_document(id),
  rate_key text NOT NULL CHECK (rate_key ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sending','sent')),
  attempts integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  leased_until timestamptz,
  sent_at timestamptz,
  delivery_error text
);
CREATE INDEX IF NOT EXISTS bug_report_rate ON bug_report(rate_key,created_at DESC);
CREATE INDEX IF NOT EXISTS bug_report_delivery ON bug_report(next_attempt_at,created_at)
WHERE status IN ('queued','sending');

CREATE OR REPLACE FUNCTION submit_bug_report(
  report_message text, report_reply text, report_path text, report_source text,
  report_rate_key text, report_consent boolean
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE report_id uuid;
BEGIN
  IF report_consent IS DISTINCT FROM true OR report_message IS NULL
    OR length(btrim(report_message)) NOT BETWEEN 10 AND 5000
    OR report_rate_key IS NULL OR report_rate_key !~ '^[a-f0-9]{64}$'
    OR length(coalesce(report_path,''))>1000
    OR coalesce(report_path,'') !~ '^(/[^/].*|/|)$'
    OR coalesce(report_path,'') ~ E'[\\r\\n]'
    OR (nullif(report_reply,'') IS NOT NULL AND (
      length(report_reply)>254 OR report_reply !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'))
    OR (nullif(report_source,'') IS NOT NULL AND (
      report_source !~ '^[a-f0-9]{64}$' OR NOT EXISTS (
        SELECT 1 FROM public.source_document WHERE id=report_source))) THEN
    RAISE EXCEPTION 'Invalid bug report' USING ERRCODE='PBR01';
  END IF;
  -- Serialize only this hashed address's submissions. Enforce the limit across
  -- all web instances, including concurrent retries and cold server restarts.
  PERFORM pg_advisory_xact_lock(hashtextextended(report_rate_key,41981));
  IF (SELECT count(*) FROM public.bug_report
      WHERE rate_key=report_rate_key AND created_at>now()-interval '1 hour')>=5 THEN
    RAISE EXCEPTION 'Bug report limit reached' USING ERRCODE='PBR02';
  END IF;
  INSERT INTO public.bug_report(message,reply_email,page_path,source_document_id,rate_key)
  VALUES(btrim(report_message),nullif(report_reply,''),coalesce(report_path,''),nullif(report_source,''),report_rate_key)
  RETURNING id INTO report_id;
  RETURN report_id;
END $$;
REVOKE ALL ON bug_report FROM PUBLIC,agro_reader;
REVOKE ALL ON FUNCTION submit_bug_report(text,text,text,text,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION submit_bug_report(text,text,text,text,text,boolean) TO agro_reader;
GRANT SELECT,UPDATE ON bug_report TO agro_ingestor;
