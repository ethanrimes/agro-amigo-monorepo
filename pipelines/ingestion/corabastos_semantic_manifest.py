"""Private source and full-vector pins for semantic correction proposal K."""
import json

MANIFEST = json.loads(r'''
{
  "schema": "private-corabastos-semantic-source-manifest-v1",
  "inert": true,
  "kind": "colombia-corabastos-pdf",
  "revision_suffix": ":source-bound-semantic-correction-v1",
  "prior_revision": "official-v2:colombia-prices-v2",
  "normal_revision": "official-v2:colombia-prices-v6",
  "source_receipt_sha256": "94971d3931221d5fa0698b8f3bc27248d9a57be561ff65a7dcad0d7442ffb5dd",
  "source_count": 9,
  "rows_per_source": 350,
  "new_rows_total": 3150,
  "prior_rows_total": 3150,
  "quantity_changes": 36,
  "label_quote_changes": 4,
  "moved_locators": 132,
  "review_rows_total": 132,
  "unchanged_prior_rows_and_bytes": true,
  "source_records": [
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_bytes": 3245869,
      "source_content_sha256": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "d572fd429bdb10fdd579d0f01a5bc22c8026da1e4d8389a6b01ddb548754124b",
      "prior_business_vector_sha256": "c3715416b2fa49c9b70e9bb910f938a28f3ebe03b7b8aa0e68f7d5f2660f9a1d",
      "prior_pg_business_vector_sha256": "c58eee37c172e0f2741fbc1759d8f469f8c1990558f8a04e45997b9bb2f123f5",
      "quote_vector_sha256_with_export_xmin": "f0f2fe12396dce398e259a757b40de2ad76791b5509a99eea9cb9300f33b44b7",
      "asset_vector_sha256": "2de5431cfb42d4cd6183f08e3a2423df984e893dc9f1d3e1a3b27244dd1a293d",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "e99257055940b95415342ede97b172e80c14b37e6d204adbcdcf252419642955",
      "observed_on": "2025-01-28",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "9394c1f7a4c196da682c403296dd62f21106005785d8ac7c078daea965fe006b",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_bytes": 3246812,
      "source_content_sha256": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "d221d8a8db75a6171104d153dec7914afc4c3666772b9b78f9423372b84d5a5d",
      "prior_business_vector_sha256": "41487167ee9705605ab712fd8684c1b4449601af3e29244f4c64ee687a78758b",
      "prior_pg_business_vector_sha256": "8b21a71edcde044c051d5cdff73fa8f8d879ee51202e55b10d16678f0a753ab6",
      "quote_vector_sha256_with_export_xmin": "eb57b41cb6c657fbd004dc4bbb777a913431b767cd945b2f1ac418e7ddbf6117",
      "asset_vector_sha256": "c15bc8eee32bcf79d4274edc90efbbb3e66866c6220d31350e676a9d55487b01",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "2dd50cc5c69e9229a2fd1cb7277b890dd314c64699b437cec2e11e0febb10f8e",
      "observed_on": "2025-01-29",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "d0787d76a3c1adf95efc2daa3bd379aa57f61c3cc6aea708f12e47ca668d01af",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_bytes": 3245737,
      "source_content_sha256": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "7e4b05bebadcde245dd36921095aaa3698578a8a6bc399b9bf648fcf96c4922c",
      "prior_business_vector_sha256": "beba437d86aae298c9fc11766f32d9f225a86bd1c90b0053c723ead66b69d8c2",
      "prior_pg_business_vector_sha256": "6f1803442ff12faf3bb96f12712432ceedadb21c734f8a0b5186007933a5273d",
      "quote_vector_sha256_with_export_xmin": "c78a0455ba55ad263938888ef6db0583c2e6aef9666049b755f9a7c0b2dc2ccd",
      "asset_vector_sha256": "ee91487532552a6768a3b9c2e4b24cdb9ac6e3501fd4ff2e653eb54e191eb38d",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "4868f94df1ad3a95b235791a9b94fe657a7115368d3f1f5c0d351f2ab450333e",
      "observed_on": "2025-01-30",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "8b0bc655ca9c74fe32ecf2ac54fb4be18b7c486635ab14baaf497a4ae053e575",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_bytes": 3246395,
      "source_content_sha256": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "da677312d4b9323ccffc39d3d5ea22142de3a63bed16dd0f049dc022d07b6fa7",
      "prior_business_vector_sha256": "8c576e867d075104ee02ece4a30ec471d2dad2cbc68b75d24a2abce1980979f4",
      "prior_pg_business_vector_sha256": "80da98427bb9ea21b9e09a0a50e78ac78ebefd4b73c1324f82d12162ec54dfe1",
      "quote_vector_sha256_with_export_xmin": "910c677bd8f05c3b461630213497a0fc251e524287ed0de7ec3ee5a45d9b7629",
      "asset_vector_sha256": "82061ebc175166bf00fd6868077251e51b3b760101a41f4ca8e5f183c0e30ef3",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "6dba95812101f68343e411ff57bf9039433ea2e8621a996132dfaec73783e72d",
      "observed_on": "2025-01-31",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "055de982a6c2d537c2d33b2124d1bbbccae0eb5b842968e670f9a992ae6cef9e",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_bytes": 3246149,
      "source_content_sha256": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "1f792d29eb6acb3c8d0bb1d0d2aa0fd6265907caaa88e140563fa8319f15466a",
      "prior_business_vector_sha256": "b50558efd146a470b56cc2c3a77edc41e0cddf425d1bd67e4456422de5a10108",
      "prior_pg_business_vector_sha256": "0335b87a904fc3e36c04add84fc78d8839274fa23603902dba54db4a1e072d68",
      "quote_vector_sha256_with_export_xmin": "c7a251daa015a0209f91defea60ffcfcf128a2c87f87ae20f3e486215e56819a",
      "asset_vector_sha256": "44a733ed8a2e26e4b34bae662be1deb113e627995ad6c1f52d64fd5965defbcd",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "9c7a5f96225e616c1ba028f5e37ae7232c5077767577a9eab86e6922528cf0d8",
      "observed_on": "2025-02-03",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "a60e3f91db0fbeecb29e2155a3e7110dff199087f9989be2a4654320504bfc77",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_bytes": 3246443,
      "source_content_sha256": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "25db6a52b62e1881df06482e82e2d99fad6455c60f719a6f6e3b7759045f9a73",
      "prior_business_vector_sha256": "0229b515f298f5000c74d4c48fcb9bc5186411b48333ccb4f41b59367fccc311",
      "prior_pg_business_vector_sha256": "d30d8ee202d91bb0cdab898c61d2cf43cb3fc9230721fc1ef7e5c2e51c6b4330",
      "quote_vector_sha256_with_export_xmin": "c812f674478cf17b7456dd49b4f2d7f9dc5962da685ea7519ff2cd4893cdbb04",
      "asset_vector_sha256": "e1ef287dc40715495e44617624e7ff54a8fe97fb73d2f68445177fca556f1bec",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "9090abb7d4c5d3a3c2ddd8f62209c334d617a17e7d94812f715f14d9fdd13075",
      "observed_on": "2025-02-04",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "19760f1d2e1f3873948f89cfafccadc086790f959354755f5685e3524d25419f",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_bytes": 3245944,
      "source_content_sha256": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "8a743a0d0d62bf7d2001d662004053ecea8550a7a9953731820f9592f90488e1",
      "prior_business_vector_sha256": "1b7b3992856b18e3179ad502616cbd7c299f314b1d5cf764626c65cbf79d729c",
      "prior_pg_business_vector_sha256": "aeeba52a222d1b4a8e87420bda08e57add294fff7346e432407dec328c1defe7",
      "quote_vector_sha256_with_export_xmin": "25c8e82f0bc16f900641617a324c46a4c3ab01b29126d28996fb3bf4595648fc",
      "asset_vector_sha256": "4132cdd78209778089abe917768d0ac7e47ae9d3022323b3cb9e398b2279f20c",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "47b673ec4ecc8b0e50b5a803ecd755bbee2bd99c6c25bcdb9e2ad642964e3dfa",
      "observed_on": "2025-02-05",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "3ac25b5665893832f58171569a6a36ce26818df8eb6182227ff210e669e30fab",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_bytes": 3246553,
      "source_content_sha256": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "b6f2be65029b1304f27028dfa37b8434069e10c964787ee61b7f2a46d4b100b4",
      "prior_business_vector_sha256": "a3499678e2e15fdf29d52668f133fd1dbea60b0001a12ecb1c28c1a001286ab5",
      "prior_pg_business_vector_sha256": "e175d2f5ddaa111be6357e77c13f67b35759a4ca70abba093537b28b92196d59",
      "quote_vector_sha256_with_export_xmin": "ab841f3592c4b41a324d090f06fcd0b28edbec54d62caa145c569ccf90bccd32",
      "asset_vector_sha256": "1bfc4d60c846292c49a6c6ff4d4cbacd46f38a3b3d10a7646a5d14110774870c",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "af23d988fe599926739ff14e769609445ae494d2a485ce65344d904a2ddc2a65",
      "observed_on": "2025-02-06",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "6616589ee507e596543e7c62720c2961a423d7d78bdb95e036c091372cc56c95",
      "native_v6_token_vector_rows": 350
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_bytes": 3245794,
      "source_content_sha256": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_export_sha256": "ed5727a3438153df7df7b55f23b29c750ae67246851c9510a8e722ef67aca77a",
      "prior_business_vector_sha256": "58c9000e18ff51c42263fffa983560e8bf38f03210b919dd098eb59f9433ee89",
      "prior_pg_business_vector_sha256": "40097aba8b9110833b085370647a844c2fc8c26121b51f49f40644187e067971",
      "quote_vector_sha256_with_export_xmin": "e8a2755efbab813116209379f98772f28fa275df66041b48a253266e90ee8e49",
      "asset_vector_sha256": "b3c76f4bc4a09e461be0e46a8e1cbe996b0d3c3952a0775d729d56f99d104d29",
      "checkpoint_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "review_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
      "source_export_without_xmin_sha256": "ecbb65828d33c0842ecfa62b271e170c35ab5362fca0560cb3eff094d6bc118c",
      "observed_on": "2025-02-07",
      "prior_asset_records": 350,
      "native_v6_token_vector_sha256": "080e2b6d56890254612318e19ba8483f6492eb9f25ff79c7a5d0470dee87e2e9",
      "native_v6_token_vector_rows": 350
    }
  ],
  "source_local_digest_policy": "The source binding and prior quote business vector are pinned without xmin. xmin values are captured from the live pre-transaction local/prod state, verified unchanged after; no production xmin is hardcoded as a local fixture gate. Original evidence export files are separately SHA-pinned and contain captured production xmin.",
  "native_v6_token_vector_schema": "SHA-256 of canonical JSON [[source_locator, exact details.original_price token, parsed price], ...], sorted by locator; 350 rows per source",
  "semantic_metadata_allowances": {
    "details.parser_version": {
      "prior": "colombia-prices-v2",
      "native": "colombia-prices-v6"
    },
    "details.original_price": {
      "prior": "absent",
      "native": "exact source token; whole-source vector hash and numeric price equality required"
    }
  }
}
''')
EXPECTED_DIFF = json.loads(r'''
{
  "schema": "private-corabastos-append-only-semantic-correction-expected-vector-v1",
  "evidence_only": true,
  "source_count": 9,
  "prior_quote_count": 3150,
  "expected_new_quote_count": 3150,
  "expected_new_revision_rows": 3150,
  "expected_semantic_quantity_quote_changes": 36,
  "expected_label_quote_changes": 4,
  "expected_locator_moves": 132,
  "unique_quotes_with_any_nonlocator_semantic_change": 36,
  "locator_moves_overlapping_quantity_rows": 4,
  "all_prior_quote_rows_preserved": true,
  "all_source_document_content_bytes_preserved": true,
  "documents": [
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_bytes": 3245869,
      "source_content_sha256": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "45005"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a.json",
      "prior_export_sha256": "d572fd429bdb10fdd579d0f01a5bc22c8026da1e4d8389a6b01ddb548754124b"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_bytes": 3246812,
      "source_content_sha256": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "44781"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f.json",
      "prior_export_sha256": "d221d8a8db75a6171104d153dec7914afc4c3666772b9b78f9423372b84d5a5d"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_bytes": 3245737,
      "source_content_sha256": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "44553"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab.json",
      "prior_export_sha256": "7e4b05bebadcde245dd36921095aaa3698578a8a6bc399b9bf648fcf96c4922c"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_bytes": 3246395,
      "source_content_sha256": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "44330"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90.json",
      "prior_export_sha256": "da677312d4b9323ccffc39d3d5ea22142de3a63bed16dd0f049dc022d07b6fa7"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_bytes": 3246149,
      "source_content_sha256": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "245238"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524.json",
      "prior_export_sha256": "1f792d29eb6acb3c8d0bb1d0d2aa0fd6265907caaa88e140563fa8319f15466a"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_bytes": 3246443,
      "source_content_sha256": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "245037"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b.json",
      "prior_export_sha256": "25db6a52b62e1881df06482e82e2d99fad6455c60f719a6f6e3b7759045f9a73"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_bytes": 3245944,
      "source_content_sha256": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "244848"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3.json",
      "prior_export_sha256": "8a743a0d0d62bf7d2001d662004053ecea8550a7a9953731820f9592f90488e1"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_bytes": 3246553,
      "source_content_sha256": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "244538"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade.json",
      "prior_export_sha256": "b6f2be65029b1304f27028dfa37b8434069e10c964787ee61b7f2a46d4b100b4"
    },
    {
      "url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_bytes": 3245794,
      "source_content_sha256": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "prior_parser_version": "official-v2:colombia-prices-v2",
      "prior_quote_count": 350,
      "quote_xmin": [
        "238173"
      ],
      "asset_status": "failed",
      "asset_processor_version": "official-v2:colombia-prices-v6",
      "prior_checkpoints": [],
      "prior_reviews": 0,
      "prior_export_path": "artifacts/qa-resumed-20261001/corabastos-jan-feb-2025-source-diagnostic-private-20261008-a/root-prior-readonly-first-a/845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae.json",
      "prior_export_sha256": "ed5727a3438153df7df7b55f23b29c750ae67246851c9510a8e722ef67aca77a"
    }
  ],
  "quantity_and_label_row_diffs": [
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-28",
        "period_start": "2025-01-28",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "45005"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-28",
        "period_start": "2025-01-28",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "45005"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-28",
        "period_start": "2025-01-28",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "45005"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-28",
        "period_start": "2025-01-28",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "45005"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-29",
        "period_start": "2025-01-29",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44781"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-29",
        "period_start": "2025-01-29",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44781"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-29",
        "period_start": "2025-01-29",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44781"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-29",
        "period_start": "2025-01-29",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44781"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-30",
        "period_start": "2025-01-30",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44553"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-30",
        "period_start": "2025-01-30",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44553"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-30",
        "period_start": "2025-01-30",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44553"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-30",
        "period_start": "2025-01-30",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44553"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-31",
        "period_start": "2025-01-31",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44330"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-31",
        "period_start": "2025-01-31",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "44330"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-31",
        "period_start": "2025-01-31",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44330"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-01-31",
        "period_start": "2025-01-31",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "44330"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-03",
        "period_start": "2025-02-03",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "245238"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-03",
        "period_start": "2025-02-03",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "245238"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
        "source_locator": "PDF page 3, y 201.5; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-03",
        "period_start": "2025-02-03",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "245238"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 201.5; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
        "source_locator": "PDF page 3, y 201.5; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-03",
        "period_start": "2025-02-03",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "245238"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 201.5; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 162.5",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
        "source_locator": "PDF page 3, y 162.5; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "6c1b20a1cb3c225f783f4565f7b1a53a32f79ee4cd85c41be01a384a7f62d006",
        "product_id": "aguacate-pieles-verdes",
        "product_name": "Aguacate Pieles Verdes",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-04",
        "period_start": "2025-02-04",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "245037"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 162.5; price column 1",
          "new": "PDF page 3, y 162.5; price column 1"
        },
        "product_name": {
          "old": "Aguacate Pieles Verdes",
          "new": "Aguacate Pieles Verdes Xtonelada"
        },
        "details.original_product": {
          "old": "AGUACATE PIELES VERDES",
          "new": "AGUACATE PIELES VERDES XTONELADA"
        },
        "product_id": {
          "old": "aguacate-pieles-verdes",
          "new": "aguacate-pieles-verdes-xtonelada"
        },
        "quote_key": {
          "old": "6c1b20a1cb3c225f783f4565f7b1a53a32f79ee4cd85c41be01a384a7f62d006",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 162.5",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
        "source_locator": "PDF page 3, y 162.5; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "ad51f8d4f0957e321fd91ce0e1d15ec12288e305124b411ac1c79a29a7e89800",
        "product_id": "aguacate-pieles-verdes",
        "product_name": "Aguacate Pieles Verdes",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-04",
        "period_start": "2025-02-04",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "245037"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 162.5; price column 2",
          "new": "PDF page 3, y 162.5; price column 2"
        },
        "product_name": {
          "old": "Aguacate Pieles Verdes",
          "new": "Aguacate Pieles Verdes Xtonelada"
        },
        "details.original_product": {
          "old": "AGUACATE PIELES VERDES",
          "new": "AGUACATE PIELES VERDES XTONELADA"
        },
        "product_id": {
          "old": "aguacate-pieles-verdes",
          "new": "aguacate-pieles-verdes-xtonelada"
        },
        "quote_key": {
          "old": "ad51f8d4f0957e321fd91ce0e1d15ec12288e305124b411ac1c79a29a7e89800",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "XTONELADA AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 190.1",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
        "source_locator": "PDF page 3, y 190.1; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "6687789f216695eaee29b32bec792612b4ced909fdf18ec6e52b80b2b81892f8",
        "product_id": "xtonelada-aguacate-hass-x-tonelada",
        "product_name": "Xtonelada Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-04",
        "period_start": "2025-02-04",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "XTONELADA AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "245037"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 190.1; price column 1",
          "new": "PDF page 3, y 190.1; price column 1"
        },
        "product_name": {
          "old": "Xtonelada Aguacate Hass X Tonelada",
          "new": "Aguacate Hass X Tonelada"
        },
        "details.original_product": {
          "old": "XTONELADA AGUACATE HASS X TONELADA",
          "new": "AGUACATE HASS X TONELADA"
        },
        "product_id": {
          "old": "xtonelada-aguacate-hass-x-tonelada",
          "new": "aguacate-hass-x-tonelada"
        },
        "quote_key": {
          "old": "6687789f216695eaee29b32bec792612b4ced909fdf18ec6e52b80b2b81892f8",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "XTONELADA AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 190.1",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
        "source_locator": "PDF page 3, y 190.1; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "91f7bc30502ce42fa059e0da5142a825dffbf74da485351aa23c230b59bb27d6",
        "product_id": "xtonelada-aguacate-hass-x-tonelada",
        "product_name": "Xtonelada Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-04",
        "period_start": "2025-02-04",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "XTONELADA AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "245037"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 190.1; price column 2",
          "new": "PDF page 3, y 190.1; price column 2"
        },
        "product_name": {
          "old": "Xtonelada Aguacate Hass X Tonelada",
          "new": "Aguacate Hass X Tonelada"
        },
        "details.original_product": {
          "old": "XTONELADA AGUACATE HASS X TONELADA",
          "new": "AGUACATE HASS X TONELADA"
        },
        "product_id": {
          "old": "xtonelada-aguacate-hass-x-tonelada",
          "new": "aguacate-hass-x-tonelada"
        },
        "quote_key": {
          "old": "91f7bc30502ce42fa059e0da5142a825dffbf74da485351aa23c230b59bb27d6",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-05",
        "period_start": "2025-02-05",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "244848"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-05",
        "period_start": "2025-02-05",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "244848"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-05",
        "period_start": "2025-02-05",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "244848"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-05",
        "period_start": "2025-02-05",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "244848"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
        "source_locator": "PDF page 3, y 176.3; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-06",
        "period_start": "2025-02-06",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "244538"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 1",
          "new": "PDF page 3, y 176.3; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 176.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
        "source_locator": "PDF page 3, y 176.3; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-06",
        "period_start": "2025-02-06",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "244538"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 176.3; price column 2",
          "new": "PDF page 3, y 176.3; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
        "source_locator": "PDF page 3, y 204.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-06",
        "period_start": "2025-02-06",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "244538"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 1",
          "new": "PDF page 3, y 204.2; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 204.2",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
        "source_locator": "PDF page 3, y 204.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-06",
        "period_start": "2025-02-06",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "244538"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 204.2; price column 2",
          "new": "PDF page 3, y 204.2; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 169.7",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 6000000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
        "source_locator": "PDF page 3, y 169.7; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-07",
        "period_start": "2025-02-07",
        "price": "6000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "238173"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 169.7; price column 1",
          "new": "PDF page 3, y 169.7; price column 1"
        },
        "quote_key": {
          "old": "a641d0b99a620098828341b7e2a5879fc1ab81d38fb33653dc329d45380727e2",
          "new": "7bae66de44aa432e4c76dba4bf9a6cc8f79e69e6f4fcf65c9276dc8dc2e5acec"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE PIELES VERDES XTONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 169.7",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 5500000.0,
        "unit_price_as_published": 6000.0
      },
      "prior_quote": {
        "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
        "source_locator": "PDF page 3, y 169.7; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
        "product_id": "aguacate-pieles-verdes-xtonelada",
        "product_name": "Aguacate Pieles Verdes Xtonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-07",
        "period_start": "2025-02-07",
        "price": "5500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE PIELES VERDES XTONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 6000.0
        },
        "xmin": "238173"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 169.7; price column 2",
          "new": "PDF page 3, y 169.7; price column 2"
        },
        "quote_key": {
          "old": "a1b910e0aab575fbe90f1be8843fd0df3ef10c305e3d4ca6dfa49039d2e76d01",
          "new": "9f9d4d3c1b1c51e42d98e27f474e9d649a0edfe1864ade137b630225c53dfe8b"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 197.3",
        "source_price_column": 1,
        "source_price_as_printed": null,
        "price_value": 5000000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
        "source_locator": "PDF page 3, y 196.2; price column 1",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-07",
        "period_start": "2025-02-07",
        "price": "5000000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "extra",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "extra",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "238173"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 196.2; price column 1",
          "new": "PDF page 3, y 197.3; price column 1"
        },
        "quote_key": {
          "old": "d4cb966a472f8dd55f659b9c8454b32278bb15116f2f540e85234ac3873aece5",
          "new": "1b5ce45dfe62924e4268e7b7b7db318604e53ea93e5ba03d95ee8734f6bbaad3"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    },
    {
      "source_physical_row": {
        "raw_product": "AGUACATE HASS X TONELADA",
        "presentation": "TONELADA",
        "raw_quantity": "1.000",
        "published_unit": "KILO",
        "source_page": 3,
        "source_native_row_locator_y": "PDF page 3, y 197.3",
        "source_price_column": 2,
        "source_price_as_printed": null,
        "price_value": 4500000.0,
        "unit_price_as_published": 5000.0
      },
      "prior_quote": {
        "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
        "source_locator": "PDF page 3, y 196.2; price column 2",
        "parser_version": "official-v2:colombia-prices-v2",
        "quote_key": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "observed_on": "2025-02-07",
        "period_start": "2025-02-07",
        "price": "4500000.0",
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "details": {
          "quality": "primera",
          "quantity": 1.0,
          "source_note": "Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
          "source_page": 3,
          "presentation": "TONELADA",
          "quality_issue": null,
          "parser_version": "colombia-prices-v2",
          "published_unit": "KILO",
          "variation_label": null,
          "original_product": "AGUACATE HASS X TONELADA",
          "identity_dimensions": {
            "quality": "primera",
            "quantity": 1.0,
            "presentation": "TONELADA",
            "published_unit": "KILO"
          },
          "unit_price_as_published": 5000.0
        },
        "xmin": "238173"
      },
      "expected_changed_fields": {
        "details.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.identity_dimensions.quantity": {
          "old": 1.0,
          "new": 1000.0
        },
        "details.quantity_as_published": {
          "old": null,
          "new": "1.000"
        },
        "source_locator": {
          "old": "PDF page 3, y 196.2; price column 2",
          "new": "PDF page 3, y 197.3; price column 2"
        },
        "quote_key": {
          "old": "b666cd9efca47c974c1c67e4b9bb29c711780d6792d416cc480553e4711ca31c",
          "new": "6d85b5ed5b9c0e4a9648ef31ccf9a2af0a53e9e2108b40e7822b275994490826"
        }
      },
      "all_other_quote_fields": "must equal source-pinned candidate parser full vector"
    }
  ],
  "locator_retirement_mappings": [
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 2, y 241.5; price column 1",
      "new_locator": "PDF page 2, y 241.6; price column 1",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 5000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 2, y 241.5; price column 2",
      "new_locator": "PDF page 2, y 241.6; price column 2",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 4500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 2, y 325.5; price column 1",
      "new_locator": "PDF page 2, y 327.4; price column 1",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 50000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 2, y 325.5; price column 2",
      "new_locator": "PDF page 2, y 327.4; price column 2",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 45000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 3, y 244.2; price column 1",
      "new_locator": "PDF page 3, y 245.6; price column 1",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 7000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 3, y 244.2; price column 2",
      "new_locator": "PDF page 3, y 245.6; price column 2",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 6000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 3, y 278.4; price column 1",
      "new_locator": "PDF page 3, y 280.8; price column 1",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 3000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 3, y 278.4; price column 2",
      "new_locator": "PDF page 3, y 280.8; price column 2",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 2500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 4, y 190.8; price column 1",
      "new_locator": "PDF page 4, y 193.2; price column 1",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 90000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1800.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 4, y 190.8; price column 2",
      "new_locator": "PDF page 4, y 193.2; price column 2",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 85000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1800.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 4, y 274.7; price column 1",
      "new_locator": "PDF page 4, y 275.6; price column 1",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 4, y 274.7; price column 2",
      "new_locator": "PDF page 4, y 275.6; price column 2",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 5, y 175.8; price column 1",
      "new_locator": "PDF page 5, y 177.9; price column 1",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "desde",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 5, y 175.8; price column 2",
      "new_locator": "PDF page 5, y 177.9; price column 2",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "hasta",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 5, y 222.1; price column 1",
      "new_locator": "PDF page 5, y 224.9; price column 1",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "9d4db5b54c55b65ce5358a10a33f9484a2d3b905db21d3e624c6fd96121bae6a",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-28enero2025.pdf",
      "old_locator": "PDF page 5, y 222.1; price column 2",
      "new_locator": "PDF page 5, y 224.9; price column 2",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-28",
        "period_start": "2025-01-28",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 204.1; price column 1",
      "new_locator": "PDF page 2, y 206.3; price column 1",
      "identity": {
        "product_id": "alcachofa",
        "product_name": "Alcachofa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "DOCENA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "DOCENA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 6000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 204.1; price column 2",
      "new_locator": "PDF page 2, y 206.3; price column 2",
      "identity": {
        "product_id": "alcachofa",
        "product_name": "Alcachofa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "DOCENA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 58000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "DOCENA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 6000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 250.4; price column 1",
      "new_locator": "PDF page 2, y 253.4; price column 1",
      "identity": {
        "product_id": "brocoli",
        "product_name": "Brocoli",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "DOCENA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 80000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "DOCENA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 8000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 3.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 250.4; price column 2",
      "new_locator": "PDF page 2, y 253.4; price column 2",
      "identity": {
        "product_id": "brocoli",
        "product_name": "Brocoli",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "DOCENA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 75000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "DOCENA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 8000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 3.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 301.1; price column 1",
      "new_locator": "PDF page 2, y 303.0; price column 1",
      "identity": {
        "product_id": "cebolla-cabezona-blanca",
        "product_name": "Cebolla Cabezona Blanca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1100.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 2, y 301.1; price column 2",
      "new_locator": "PDF page 2, y 303.0; price column 2",
      "identity": {
        "product_id": "cebolla-cabezona-blanca",
        "product_name": "Cebolla Cabezona Blanca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 50000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1100.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 3, y 303.9; price column 1",
      "new_locator": "PDF page 3, y 304.4; price column 1",
      "identity": {
        "product_id": "durazno-nacional",
        "product_name": "Durazno Nacional",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 9000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 9000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 3, y 303.9; price column 2",
      "new_locator": "PDF page 3, y 304.4; price column 2",
      "identity": {
        "product_id": "durazno-nacional",
        "product_name": "Durazno Nacional",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 8000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 9000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 4, y 250.3; price column 1",
      "new_locator": "PDF page 4, y 252.0; price column 1",
      "identity": {
        "product_id": "papa-suprema",
        "product_name": "Papa Suprema",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 75000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 4, y 250.3; price column 2",
      "new_locator": "PDF page 4, y 252.0; price column 2",
      "identity": {
        "product_id": "papa-suprema",
        "product_name": "Papa Suprema",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 73000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 5, y 281.6; price column 1",
      "new_locator": "PDF page 5, y 283.7; price column 1",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 5, y 281.6; price column 2",
      "new_locator": "PDF page 5, y 283.7; price column 2",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 6, y 145.0; price column 1",
      "new_locator": "PDF page 6, y 147.6; price column 1",
      "identity": {
        "product_id": "queso-campesino",
        "product_name": "Queso Campesino",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 16600.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 16600.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 6, y 145.0; price column 2",
      "new_locator": "PDF page 6, y 147.6; price column 2",
      "identity": {
        "product_id": "queso-campesino",
        "product_name": "Queso Campesino",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 16600.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 16600.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 7, y 141.7; price column 1",
      "new_locator": "PDF page 7, y 142.0; price column 1",
      "identity": {
        "product_id": "bagre-dorado",
        "product_name": "Bagre Dorado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.3,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 7, y 141.7; price column 2",
      "new_locator": "PDF page 7, y 142.0; price column 2",
      "identity": {
        "product_id": "bagre-dorado",
        "product_name": "Bagre Dorado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.3,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 7, y 179.6; price column 1",
      "new_locator": "PDF page 7, y 180.1; price column 1",
      "identity": {
        "product_id": "boca-chico",
        "product_name": "Boca Chico",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 11000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 11000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "06212c7f7b3e9a9fa16298496e52332ad36e1a05fb65d67aa4caec048e02019f",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-29enero2025.pdf",
      "old_locator": "PDF page 7, y 179.6; price column 2",
      "new_locator": "PDF page 7, y 180.1; price column 2",
      "identity": {
        "product_id": "boca-chico",
        "product_name": "Boca Chico",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-29",
        "period_start": "2025-01-29",
        "price": 11000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 11000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 2, y 326.9; price column 1",
      "new_locator": "PDF page 2, y 327.4; price column 1",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 50000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 2, y 326.9; price column 2",
      "new_locator": "PDF page 2, y 327.4; price column 2",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 45000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 3, y 229.1; price column 1",
      "new_locator": "PDF page 3, y 231.8; price column 1",
      "identity": {
        "product_id": "banano-uraba",
        "product_name": "Banano Uraba",
        "category": "Banano y plátano",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "CAJA · cantidad 20 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 45000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 20.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2250.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 3, y 229.1; price column 2",
      "new_locator": "PDF page 3, y 231.8; price column 2",
      "identity": {
        "product_id": "banano-uraba",
        "product_name": "Banano Uraba",
        "category": "Banano y plátano",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "CAJA · cantidad 20 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 43000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 20.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2250.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 3, y 279.8; price column 1",
      "new_locator": "PDF page 3, y 280.8; price column 1",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 3000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 3, y 279.8; price column 2",
      "new_locator": "PDF page 3, y 280.8; price column 2",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 2500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 4, y 192.1; price column 1",
      "new_locator": "PDF page 4, y 193.2; price column 1",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 70000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 4, y 192.1; price column 2",
      "new_locator": "PDF page 4, y 193.2; price column 2",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 65000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 177.1; price column 1",
      "new_locator": "PDF page 5, y 177.9; price column 1",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "desde",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 177.1; price column 2",
      "new_locator": "PDF page 5, y 177.9; price column 2",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "hasta",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 223.4; price column 1",
      "new_locator": "PDF page 5, y 224.9; price column 1",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 223.4; price column 2",
      "new_locator": "PDF page 5, y 224.9; price column 2",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.5,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 257.6; price column 1",
      "new_locator": "PDF page 5, y 260.2; price column 1",
      "identity": {
        "product_id": "cafe-500gr",
        "product_name": "Cafe 500Gr",
        "category": "Café",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "PAQUETE · cantidad 5 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 160000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "PAQUETE",
        "quantity": 5.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 32000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 5, y 257.6; price column 2",
      "new_locator": "PDF page 5, y 260.2; price column 2",
      "identity": {
        "product_id": "cafe-500gr",
        "product_name": "Cafe 500Gr",
        "category": "Café",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "PAQUETE · cantidad 5 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 160000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "PAQUETE",
        "quantity": 5.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 32000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 6, y 209.2; price column 1",
      "new_locator": "PDF page 6, y 207.2; price column 1",
      "identity": {
        "product_id": "queso-pera",
        "product_name": "Queso Pera",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "cae5dbd7989ab43d98921b8716b178438e284e70a04c8dd156d6408998a638ab",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-30enero2025.pdf",
      "old_locator": "PDF page 6, y 209.2; price column 2",
      "new_locator": "PDF page 6, y 207.2; price column 2",
      "identity": {
        "product_id": "queso-pera",
        "product_name": "Queso Pera",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-30",
        "period_start": "2025-01-30",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 2, y 240.7; price column 1",
      "new_locator": "PDF page 2, y 241.6; price column 1",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 5000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 2, y 240.7; price column 2",
      "new_locator": "PDF page 2, y 241.6; price column 2",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 4500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 2, y 324.6; price column 1",
      "new_locator": "PDF page 2, y 327.4; price column 1",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 2, y 324.6; price column 2",
      "new_locator": "PDF page 2, y 327.4; price column 2",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 3, y 243.4; price column 1",
      "new_locator": "PDF page 3, y 245.6; price column 1",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 7000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 3, y 243.4; price column 2",
      "new_locator": "PDF page 3, y 245.6; price column 2",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 6000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 4, y 273.9; price column 1",
      "new_locator": "PDF page 4, y 275.6; price column 1",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 4, y 273.9; price column 2",
      "new_locator": "PDF page 4, y 275.6; price column 2",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 5, y 175.0; price column 1",
      "new_locator": "PDF page 5, y 177.9; price column 1",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "desde",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "a64618aa12cb427239231ce9c2a6a7dc27cdb7c8ce1683f0a9e8fc54f2198e90",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/01/Boletin-31enero2025.pdf",
      "old_locator": "PDF page 5, y 175.0; price column 2",
      "new_locator": "PDF page 5, y 177.9; price column 2",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-01-31",
        "period_start": "2025-01-31",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "hasta",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 2, y 215.4; price column 1",
      "new_locator": "PDF page 2, y 218.1; price column 1",
      "identity": {
        "product_id": "apio",
        "product_name": "Apio",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ATADO · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 10000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ATADO",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 2, y 215.4; price column 2",
      "new_locator": "PDF page 2, y 218.1; price column 2",
      "identity": {
        "product_id": "apio",
        "product_name": "Apio",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ATADO · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 9000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ATADO",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 201.5; price column 1",
      "new_locator": "PDF page 3, y 204.2; price column 1",
      "identity": {
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 5000000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "TONELADA",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 201.5; price column 2",
      "new_locator": "PDF page 3, y 204.2; price column 2",
      "identity": {
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 4500000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "TONELADA",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 231.2; price column 1",
      "new_locator": "PDF page 3, y 231.8; price column 1",
      "identity": {
        "product_id": "banano-uraba",
        "product_name": "Banano Uraba",
        "category": "Banano y plátano",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "CAJA · cantidad 20 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 45000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 20.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2250.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 231.2; price column 2",
      "new_locator": "PDF page 3, y 231.8; price column 2",
      "identity": {
        "product_id": "banano-uraba",
        "product_name": "Banano Uraba",
        "category": "Banano y plátano",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "CAJA · cantidad 20 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 43000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 20.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2250.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 290.2; price column 1",
      "new_locator": "PDF page 3, y 292.6; price column 1",
      "identity": {
        "product_id": "durazno-importado",
        "product_name": "Durazno Importado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "CAJA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 130000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 13000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 3, y 290.2; price column 2",
      "new_locator": "PDF page 3, y 292.6; price column 2",
      "identity": {
        "product_id": "durazno-importado",
        "product_name": "Durazno Importado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "CAJA · cantidad 10 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 125000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "CAJA",
        "quantity": 10.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 13000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 5, y 294.7; price column 1",
      "new_locator": "PDF page 5, y 295.5; price column 1",
      "identity": {
        "product_id": "cuchuco-de-cebada",
        "product_name": "Cuchuco De Cebada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "ARROBA · cantidad 12,5 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 176000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "ARROBA",
        "quantity": 12.5,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 3520.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 5, y 294.7; price column 2",
      "new_locator": "PDF page 5, y 295.5; price column 2",
      "identity": {
        "product_id": "cuchuco-de-cebada",
        "product_name": "Cuchuco De Cebada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "ARROBA · cantidad 12,5 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 176000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "ARROBA",
        "quantity": 12.5,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 3520.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 7, y 151.0; price column 1",
      "new_locator": "PDF page 7, y 153.8; price column 1",
      "identity": {
        "product_id": "bagre-pintado",
        "product_name": "Bagre Pintado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 7, y 151.0; price column 2",
      "new_locator": "PDF page 7, y 153.8; price column 2",
      "identity": {
        "product_id": "bagre-pintado",
        "product_name": "Bagre Pintado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 7, y 245.3; price column 1",
      "new_locator": "PDF page 7, y 247.7; price column 1",
      "identity": {
        "product_id": "camaron-titi",
        "product_name": "Camaron Titi",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 20000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 20000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "8acbaf5c2c1138de3a45a25dcb8978559c3698268a377a81f16bce9fd0dc5524",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-03febrero2025.pdf",
      "old_locator": "PDF page 7, y 245.3; price column 2",
      "new_locator": "PDF page 7, y 247.7; price column 2",
      "identity": {
        "product_id": "camaron-titi",
        "product_name": "Camaron Titi",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-03",
        "period_start": "2025-02-03",
        "price": 20000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 20000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 240.7; price column 1",
      "new_locator": "PDF page 2, y 242.6; price column 1",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 5000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 240.7; price column 2",
      "new_locator": "PDF page 2, y 242.6; price column 2",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 4500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 316.3; price column 1",
      "new_locator": "PDF page 2, y 316.7; price column 1",
      "identity": {
        "product_id": "cebolla-cabezona-roja",
        "product_name": "Cebolla Cabezona Roja",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 110000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2200.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 316.3; price column 2",
      "new_locator": "PDF page 2, y 316.7; price column 2",
      "identity": {
        "product_id": "cebolla-cabezona-roja",
        "product_name": "Cebolla Cabezona Roja",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 105000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2200.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 326.3; price column 1",
      "new_locator": "PDF page 2, y 328.4; price column 1",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 80000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 2, y 326.3; price column 2",
      "new_locator": "PDF page 2, y 328.4; price column 2",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 75000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2667.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 3, y 243.4; price column 1",
      "new_locator": "PDF page 3, y 245.3; price column 1",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 7000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 3, y 243.4; price column 2",
      "new_locator": "PDF page 3, y 245.3; price column 2",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 6000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 4, y 275.6; price column 1",
      "new_locator": "PDF page 4, y 276.6; price column 1",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 4, y 275.6; price column 2",
      "new_locator": "PDF page 4, y 276.6; price column 2",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 7, y 233.5; price column 1",
      "new_locator": "PDF page 7, y 233.7; price column 1",
      "identity": {
        "product_id": "camaron-tigre",
        "product_name": "Camaron Tigre",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "old_locator": "PDF page 7, y 233.5; price column 2",
      "new_locator": "PDF page 7, y 233.7; price column 2",
      "identity": {
        "product_id": "camaron-tigre",
        "product_name": "Camaron Tigre",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-04",
        "period_start": "2025-02-04",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 3, y 278.1; price column 1",
      "new_locator": "PDF page 3, y 280.8; price column 1",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 3000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 3, y 278.1; price column 2",
      "new_locator": "PDF page 3, y 280.8; price column 2",
      "identity": {
        "product_id": "curuba-san-bernardo",
        "product_name": "Curuba San Bernardo",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 2500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 5, y 282.5; price column 1",
      "new_locator": "PDF page 5, y 283.7; price column 1",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 5, y 282.5; price column 2",
      "new_locator": "PDF page 5, y 283.7; price column 2",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 6, y 157.5; price column 1",
      "new_locator": "PDF page 6, y 159.4; price column 1",
      "identity": {
        "product_id": "queso-coste",
        "product_name": "Queso Coste",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 17000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 17000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 6, y 157.5; price column 2",
      "new_locator": "PDF page 6, y 159.4; price column 2",
      "identity": {
        "product_id": "queso-coste",
        "product_name": "Queso Coste",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 17000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 17000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 141.0; price column 1",
      "new_locator": "PDF page 7, y 142.0; price column 1",
      "identity": {
        "product_id": "bagre-dorado",
        "product_name": "Bagre Dorado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 141.0; price column 2",
      "new_locator": "PDF page 7, y 142.0; price column 2",
      "identity": {
        "product_id": "bagre-dorado",
        "product_name": "Bagre Dorado",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 28000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 28000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.0,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 165.3; price column 1",
      "new_locator": "PDF page 7, y 165.5; price column 1",
      "identity": {
        "product_id": "blanquillo-gallego",
        "product_name": "Blanquillo Gallego",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 16000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 16000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 165.3; price column 2",
      "new_locator": "PDF page 7, y 165.5; price column 2",
      "identity": {
        "product_id": "blanquillo-gallego",
        "product_name": "Blanquillo Gallego",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 16000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 16000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 178.9; price column 1",
      "new_locator": "PDF page 7, y 180.1; price column 1",
      "identity": {
        "product_id": "boca-chico",
        "product_name": "Boca Chico",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 11000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 11000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "b05bb77e370e058d0fa47df957214335f6424d5fddfecba0eb7eb746880748e3",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-05febrero2025.pdf",
      "old_locator": "PDF page 7, y 178.9; price column 2",
      "new_locator": "PDF page 7, y 180.1; price column 2",
      "identity": {
        "product_id": "boca-chico",
        "product_name": "Boca Chico",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-05",
        "period_start": "2025-02-05",
        "price": 11000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 11000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 2, y 301.2; price column 1",
      "new_locator": "PDF page 2, y 303.0; price column 1",
      "identity": {
        "product_id": "cebolla-cabezona-blanca",
        "product_name": "Cebolla Cabezona Blanca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1100.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 2, y 301.2; price column 2",
      "new_locator": "PDF page 2, y 303.0; price column 2",
      "identity": {
        "product_id": "cebolla-cabezona-blanca",
        "product_name": "Cebolla Cabezona Blanca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 50000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1100.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 244.7; price column 1",
      "new_locator": "PDF page 3, y 245.6; price column 1",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 7000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 244.7; price column 2",
      "new_locator": "PDF page 3, y 245.6; price column 2",
      "identity": {
        "product_id": "breva",
        "product_name": "Breva",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 6000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 7000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 303.8; price column 1",
      "new_locator": "PDF page 3, y 304.4; price column 1",
      "identity": {
        "product_id": "durazno-nacional",
        "product_name": "Durazno Nacional",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 9000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 9000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 303.8; price column 2",
      "new_locator": "PDF page 3, y 304.4; price column 2",
      "identity": {
        "product_id": "durazno-nacional",
        "product_name": "Durazno Nacional",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 8000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 9000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 313.9; price column 1",
      "new_locator": "PDF page 3, y 316.1; price column 1",
      "identity": {
        "product_id": "feijoa",
        "product_name": "Feijoa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 8000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 8000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 3, y 313.9; price column 2",
      "new_locator": "PDF page 3, y 316.1; price column 2",
      "identity": {
        "product_id": "feijoa",
        "product_name": "Feijoa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 7000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 8000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 4, y 191.3; price column 1",
      "new_locator": "PDF page 4, y 193.2; price column 1",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 75000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 4, y 191.3; price column 2",
      "new_locator": "PDF page 4, y 193.2; price column 2",
      "identity": {
        "product_id": "papa-pastusa",
        "product_name": "Papa Pastusa",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 70000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 4, y 250.3; price column 1",
      "new_locator": "PDF page 4, y 252.0; price column 1",
      "identity": {
        "product_id": "papa-suprema",
        "product_name": "Papa Suprema",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 75000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 4, y 250.3; price column 2",
      "new_locator": "PDF page 4, y 252.0; price column 2",
      "identity": {
        "product_id": "papa-suprema",
        "product_name": "Papa Suprema",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 73000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 1500.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.7,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 176.3; price column 1",
      "new_locator": "PDF page 5, y 177.9; price column 1",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "desde",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 176.3; price column 2",
      "new_locator": "PDF page 5, y 177.9; price column 2",
      "identity": {
        "product_id": "aceite-galon-3000-c-c",
        "product_name": "Aceite Galon (3000 C.C)",
        "category": "Aceites y grasas",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 6 · UNIDAD",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 113000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 6.0,
        "published_unit": "UNIDAD",
        "quality": "hasta",
        "unit_price_as_published": 18833.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.6,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 222.5; price column 1",
      "new_locator": "PDF page 5, y 224.9; price column 1",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 222.5; price column 2",
      "new_locator": "PDF page 5, y 224.9; price column 2",
      "identity": {
        "product_id": "arveja-verde-seca",
        "product_name": "Arveja Verde Seca",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 170000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 3400.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.4,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 281.6; price column 1",
      "new_locator": "PDF page 5, y 283.7; price column 1",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "2edfaf81ac6606cfa779e3772dbcc1aa9873fd2f4a316f279f208baae5ce4ade",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-06febrero2025.pdf",
      "old_locator": "PDF page 5, y 281.6; price column 2",
      "new_locator": "PDF page 5, y 283.7; price column 2",
      "identity": {
        "product_id": "chocolate-dulce",
        "product_name": "Chocolate Dulce",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "CAJA · cantidad 24 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-06",
        "period_start": "2025-02-06",
        "price": 58800.0,
        "min_price": null,
        "max_price": null,
        "source_page": 5,
        "presentation": "CAJA",
        "quantity": 24.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 4900.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 2.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 239.8; price column 1",
      "new_locator": "PDF page 2, y 241.6; price column 1",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 5000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 239.8; price column 2",
      "new_locator": "PDF page 2, y 241.6; price column 2",
      "identity": {
        "product_id": "berenjena",
        "product_name": "Berenjena",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 4500.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.8,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 315.5; price column 1",
      "new_locator": "PDF page 2, y 315.6; price column 1",
      "identity": {
        "product_id": "cebolla-cabezona-roja",
        "product_name": "Cebolla Cabezona Roja",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 110000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2200.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 315.5; price column 2",
      "new_locator": "PDF page 2, y 315.6; price column 2",
      "identity": {
        "product_id": "cebolla-cabezona-roja",
        "product_name": "Cebolla Cabezona Roja",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BULTO · cantidad 50 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 105000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "BULTO",
        "quantity": 50.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2200.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 325.5; price column 1",
      "new_locator": "PDF page 2, y 327.4; price column 1",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 90000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 2, y 325.5; price column 2",
      "new_locator": "PDF page 2, y 327.4; price column 2",
      "identity": {
        "product_id": "cebolla-larga",
        "product_name": "Cebolla Larga",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "ROLLO · cantidad 25 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 85000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 2,
        "presentation": "ROLLO",
        "quantity": 25.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 3000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 3, y 196.2; price column 1",
      "new_locator": "PDF page 3, y 197.3; price column 1",
      "identity": {
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 5000000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "TONELADA",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 3, y 196.2; price column 2",
      "new_locator": "PDF page 3, y 197.3; price column 2",
      "identity": {
        "product_id": "aguacate-hass-x-tonelada",
        "product_name": "Aguacate Hass X Tonelada",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "TONELADA · cantidad 1.000 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 4500000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 3,
        "presentation": "TONELADA",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 5000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.1,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 4, y 274.7; price column 1",
      "new_locator": "PDF page 4, y 275.6; price column 1",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 60000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 4, y 274.7; price column 2",
      "new_locator": "PDF page 4, y 275.6; price column 2",
      "identity": {
        "product_id": "yuca-armenia",
        "product_name": "Yuca Armenia",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "BOLSA · cantidad 30 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 55000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 4,
        "presentation": "BOLSA",
        "quantity": 30.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 2000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 6, y 206.9; price column 1",
      "new_locator": "PDF page 6, y 207.2; price column 1",
      "identity": {
        "product_id": "queso-pera",
        "product_name": "Queso Pera",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-desde",
        "basis": "Precio en bodega · desde",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "desde",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.3,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 6, y 206.9; price column 2",
      "new_locator": "PDF page 6, y 207.2; price column 2",
      "identity": {
        "product_id": "queso-pera",
        "product_name": "Queso Pera",
        "category": "Lácteos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-range-hasta",
        "basis": "Precio en bodega · hasta",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 6,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "hasta",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.3,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 7, y 219.2; price column 1",
      "new_locator": "PDF page 7, y 220.1; price column 1",
      "identity": {
        "product_id": "cajaro",
        "product_name": "Cajaro",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 18000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 18000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 7, y 219.2; price column 2",
      "new_locator": "PDF page 7, y 220.1; price column 2",
      "identity": {
        "product_id": "cajaro",
        "product_name": "Cajaro",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 18000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 18000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 0.9,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 7, y 232.7; price column 1",
      "new_locator": "PDF page 7, y 233.9; price column 1",
      "identity": {
        "product_id": "camaron-tigre",
        "product_name": "Camaron Tigre",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-extra",
        "basis": "Precio en bodega · calidad extra",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "extra",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    },
    {
      "document_id": "845f2461b0fd0fc120cedb8675d03463e84a464d11e567d591fc398af26c4bae",
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-07febrero2025.pdf",
      "old_locator": "PDF page 7, y 232.7; price column 2",
      "new_locator": "PDF page 7, y 233.9; price column 2",
      "identity": {
        "product_id": "camaron-tigre",
        "product_name": "Camaron Tigre",
        "category": "Productos de Corabastos",
        "publisher": "Corabastos S.A.",
        "series": "corabastos-quality-primera",
        "basis": "Precio en bodega · calidad primera",
        "currency": "COP",
        "unit": "KILO · cantidad 1 · KILO",
        "market": "Bogotá · Corabastos",
        "day": "2025-02-07",
        "period_start": "2025-02-07",
        "price": 34000.0,
        "min_price": null,
        "max_price": null,
        "source_page": 7,
        "presentation": "KILO",
        "quantity": 1.0,
        "published_unit": "KILO",
        "quality": "primera",
        "unit_price_as_published": 34000.0
      },
      "same_page_price_column_and_max_shift_points": {
        "same_page": true,
        "same_price_column": true,
        "delta_points": 1.2,
        "max_allowed": 3.0
      }
    }
  ],
  "february_4_label_allowlist": [
    {
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "page": 3,
      "old_original_product": "AGUACATE PIELES VERDES",
      "new_original_product": "AGUACATE PIELES VERDES XTONELADA",
      "old_product_name": "Aguacate Pieles Verdes",
      "new_product_name": "Aguacate Pieles Verdes Xtonelada",
      "physical_locator_prefix": "PDF page 3, y 162.5; price column ",
      "quality_columns": [
        1,
        2
      ]
    },
    {
      "source_url": "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-04febrero2025.pdf",
      "document_id": "0f1f1799263d38d85988fdc1e2b24aee07a6e616c638a414ece44b1ce0f22d5b",
      "page": 3,
      "old_original_product": "XTONELADA AGUACATE HASS X TONELADA",
      "new_original_product": "AGUACATE HASS X TONELADA",
      "old_product_name": "Xtonelada Aguacate Hass X Tonelada",
      "new_product_name": "Aguacate Hass X Tonelada",
      "physical_locator_prefix": "PDF page 3, y 190.1; price column ",
      "quality_columns": [
        1,
        2
      ]
    }
  ],
  "expected_unchanged_source_fields": [
    "category",
    "publisher",
    "series",
    "basis",
    "currency",
    "unit",
    "market",
    "observed_on",
    "period_start",
    "price",
    "min_price",
    "max_price",
    "source_page",
    "presentation",
    "published_unit",
    "quality",
    "unit_price_as_published",
    "details.original_price",
    "details.variation_label",
    "details.source_note"
  ],
  "interpretation": "The 132 locator changes are only source-locator changes proved by exact source-page and price-column parity and <=3.0pt movement. Four of those moved quote rows overlap corrected quantity targets (the extra/primera Hass pair on Feb 3 and Feb 7). Four Feb 4 product-label corrections are already among the 36 quantity rows. Thus 36 rows have semantic changes and 132 locator pairs are separately retired; no price or source identity is inferred from arithmetic."
}
''')
