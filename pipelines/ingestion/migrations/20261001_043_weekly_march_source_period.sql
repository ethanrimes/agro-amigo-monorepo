-- The official archive and every monetary worksheet of this immutable annex
-- print March 9–15. Its URL alone ends March 16. Keep the byte-revision guard
-- in dane_weekly.py and correct only this already retained asset's metadata.
UPDATE ingestion_asset SET observed_on='2024-03-15'
WHERE url='https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSASemanal-09mar-16mar-2024.xlsx'
 AND kind='dane-weekly-xlsx'
 AND document_id='a1d2992f6bee7ce29c12ed1cee92feb31a9204ffe5546cd3276bab0cc09436e6'
 AND observed_on='2024-03-16';

-- The two retained originals were reviewed only because the pre-audit date
-- guard rejected these exact bytes. A same-version review does not re-enter
-- normal discovery, so queue only these immutable failed attempts once. The
-- previous error/attempt count stays visible until a successful replay.
UPDATE ingestion_asset SET status='pending'
WHERE url='https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSASemanal-09mar-16mar-2024.xlsx'
 AND kind='dane-weekly-xlsx'
 AND document_id='a1d2992f6bee7ce29c12ed1cee92feb31a9204ffe5546cd3276bab0cc09436e6'
 AND observed_on='2024-03-15'
 AND status='review' AND records=0
 AND processor_version='official-v2:dane-weekly-v16'
 AND error='SourceDateMismatch: Weekly printed period conflicts with the dated source URL: printed 2024-03-09–2024-03-15; filename 2024-03-09–2024-03-16';

UPDATE ingestion_asset SET status='pending'
WHERE url='https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-22jul-28jul-2023.pdf'
 AND kind='dane-weekly-pdf'
 AND document_id='7bd0545a892e3a95cbaa9333510161ed14b7753949ac0fae3c24aa419729d088'
 AND observed_on='2023-07-28'
 AND status='review' AND records=0
 AND processor_version='official-v2:dane-weekly-v16'
 AND error='SourceDateMismatch: Weekly printed period conflicts with the dated source URL';
