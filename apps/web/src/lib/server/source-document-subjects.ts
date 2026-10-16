/** Human subjects verified in the immutable originals, without rewriting titles. */
const subjects: Record<string, string> = {
  "6d7f0f181521b8df528b748d2bc10ecac2a605a8987de4a9b152eb8ff71bb637":
    "Granadilla · costos de producción · 2024",
};

// Only fixed source IDs and source-verified prose enter this SQL expression.
export const SOURCE_DOCUMENT_SUBJECT_SQL = `CASE d.id ${Object.entries(subjects)
  .map(([id, subject]) => `WHEN '${id}' THEN '${subject.replace(/'/g, "''")}'`)
  .join(" ")} ELSE '' END`;

/** Five CRC-matched ZIP member names with complete native PDF/source-row proof.
 * This is a display-only projection; original titles, metadata and bytes stay archived. */
const reviewedCityUnicode = [
  {
    "documentId": "b2e3895cbd78b10c12ea922ef7b70a3511bd88cbd656e552d5b9c66bd1f61c10",
    "parentId": "313261d5fe9d15b554c2bd758c1b7f45bf448c2b60656e37c39d23664c536f22",
    "sourceUrl": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-19-12-2020.zip",
    "rawFilename": "Ibague∩, Plaza La 21-19-12-2020 (1).pdf",
    "displayFilename": "Ibagué, Plaza La 21-19-12-2020 (1).pdf"
  },
  {
    "documentId": "4dc73a1d7464f11b707b4ca78127d6f5ac6c3e42f419afbae7af4765e056f270",
    "parentId": "41407c2d09fe4334ff96fa141422f17a31daa3e82bba1da842570635060c6098",
    "sourceUrl": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-20-06-2020.zip",
    "rawFilename": "Bogota∩, D.C., Corabastos-20-06-2020.pdf",
    "displayFilename": "Bogotá, D.C., Corabastos-20-06-2020.pdf"
  },
  {
    "documentId": "a9100de6e7d72a3aadc13c2331faa1ce49f19ee9f61bd181fb23d3ae97860ad7",
    "parentId": "62213d654ea536b9ded3ea999ec3c8e38d798d7a1a03ff630d4c0fa829a6b725",
    "sourceUrl": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-01-05-2020.zip",
    "rawFilename": "Bogota∩, D.C., Corabastos-01-05-2020.pdf",
    "displayFilename": "Bogotá, D.C., Corabastos-01-05-2020.pdf"
  },
  {
    "documentId": "4aa6ff456c539f9bac8695dee8c575a20f07db5cd7f51bfe682f69c524dcd12b",
    "parentId": "62213d654ea536b9ded3ea999ec3c8e38d798d7a1a03ff630d4c0fa829a6b725",
    "sourceUrl": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-01-05-2020.zip",
    "rawFilename": "Cu∩cuta, Cenabastos-01-05-2020.pdf",
    "displayFilename": "Cúcuta, Cenabastos-01-05-2020.pdf"
  },
  {
    "documentId": "7024d5b0a8572a852cedd41efbe596de6dc99fa430697559945c09babfdddd60",
    "parentId": "62213d654ea536b9ded3ea999ec3c8e38d798d7a1a03ff630d4c0fa829a6b725",
    "sourceUrl": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-01-05-2020.zip",
    "rawFilename": "Monteri∩a, Mercado del Sur-01-05-2020.pdf",
    "displayFilename": "Montería, Mercado del Sur-01-05-2020.pdf"
  }
] as const;

if (reviewedCityUnicode.length !== 5 ||
    new Set(reviewedCityUnicode.map((member) => member.documentId)).size !== 5 ||
    reviewedCityUnicode.some((member) =>
      !/^[a-f0-9]{64}$/.test(member.documentId) ||
      !/^[a-f0-9]{64}$/.test(member.parentId) ||
      !/^https:\/\/www\.dane\.gov\.co\/files\/.+[.]zip$/.test(member.sourceUrl) ||
      !member.rawFilename.endsWith(".pdf") ||
      !member.displayFilename.endsWith(".pdf") ||
      member.displayFilename !== member.displayFilename.normalize("NFC"))) {
  throw new Error("Invalid reviewed city Unicode source display");
}

const sqlQuote = (value: string) => `'${value.replaceAll("'", "''")}'`;
const reviewedFilename = `CASE ${reviewedCityUnicode.map((member) => `
  WHEN d.id=${sqlQuote(member.documentId)}
    AND d.kind='original' AND d.media_type='application/pdf' AND d.publisher='DANE'
    AND d.source_url=${sqlQuote(member.sourceUrl)}
    AND d.title=${sqlQuote(`DANE - ${member.rawFilename}`)}
    AND d.metadata->>'ingestion_kind'='city-pdf'
    AND d.metadata->>'original_filename'=${sqlQuote(member.rawFilename)}
    AND d.metadata->>'archive_entry'=${sqlQuote(member.rawFilename)}
    AND jsonb_typeof(d.metadata->'parents')='array'
    AND (d.metadata->'parents') ? ${sqlQuote(member.parentId)}
  THEN ${sqlQuote(member.displayFilename)}`).join(" ")} ELSE NULL::text END`;

export const SOURCE_DOCUMENT_REVIEWED_FILENAME_SQL = reviewedFilename;
export const SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL = `COALESCE((${reviewedFilename}),d.metadata->>'original_filename')`;
export const SOURCE_DOCUMENT_DISPLAY_TITLE_SQL = `COALESCE('DANE - ' || (${reviewedFilename}),d.title)`;
