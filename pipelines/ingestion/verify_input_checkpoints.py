"""Real PostgreSQL regression using session-local tables only; no published fixtures."""

from datetime import date
from unittest.mock import patch

from . import resumable_inputs, worker
from .inputs import project_inputs


def verify_native_batch_resume(db):
    """Exercise actual COPY/rollback and resume with three one-row batches."""
    did, kind = "d" * 64, "inputs-municipal"
    rows = [
        worker.record(
            "dane-inputs-municipal",
            day,
            "Arada de prueba por lotes",
            "El Carmen de Viboral",
            "hora/máquina",
            price,
            f"3.3!row {number}",
            details={
                "category": "Servicios agrícolas",
                "department": "Antioquia",
                "municipality": "El Carmen de Viboral",
                "presentation": "hora/máquina",
            },
        )
        for number, (day, price) in enumerate(
            [
                (date(2026, 1, 31), 100000),
                (date(2026, 2, 28), 105000),
                (date(2026, 3, 31), 110000),
            ],
            1,
        )
    ]
    for locator, status, source_kind in (
        ("pending", "pending", kind),
        ("deferred", "deferred", kind),
        ("review", "review", kind),
        ("published", "published", kind),
        ("other-kind", "pending", "inputs-pdf"),
    ):
        db.execute(
            """INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,status,error)
            VALUES(%s,%s,%s,%s,%s,'retained prior decision')""",
            (did, locator, "e" * 64, source_kind, status),
        )

    def steps():
        return dict(
            db.execute(
                "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s",
                (did,),
            ).fetchall()
        )

    def ocr_state():
        return db.execute(
            """SELECT source_locator,status,error,checked_at FROM source_ocr_task
            WHERE document_id=%s ORDER BY source_locator""",
            (did,),
        ).fetchall()

    original_ocr = ocr_state()
    save_rows = worker.save_rows
    writes = []

    def interrupted_batch(connection, document, batch):
        writes.append([row[0] for row in batch])
        count = save_rows(connection, document, batch)
        if len(writes) == 2:
            # The second COPY really happened. Both its source row and its
            # checkpoint must disappear when this transaction rolls back.
            assert (
                connection.execute(
                    "SELECT count(*) FROM historical_price WHERE document_id=%s", (did,)
                ).fetchone()[0]
                == 2
            )
            raise RuntimeError("simulated interrupted native batch")
        return count

    with (
        patch.object(resumable_inputs, "BATCH_SIZE", 1),
        patch(
            "pipelines.ingestion.inputs.parse_inputs", side_effect=lambda _: iter(rows)
        ),
        patch.object(worker, "save_rows", side_effect=interrupted_batch),
        patch(
            "pipelines.ingestion.inputs.project_inputs", wraps=project_inputs
        ) as project,
        patch(
            "pipelines.ingestion.input_references.extract_reference_rows",
            return_value=0,
        ) as references,
    ):
        try:
            resumable_inputs.publish(db, b"fixture", did, kind, None)
        except RuntimeError as exc:
            assert str(exc) == "simulated interrupted native batch"
        else:
            raise AssertionError("Native interruption was not propagated")
        project.assert_not_called()
        references.assert_not_called()
    assert writes == [[rows[0][0]], [rows[1][0]]]
    assert db.execute(
        "SELECT source_locator FROM historical_price WHERE document_id=%s", (did,)
    ).fetchall() == [(rows[0][0],)]
    assert steps() == {"validated": 3, "native-batch:000001": 1}
    assert (
        db.execute(
            "SELECT count(*) FROM input_municipal_price WHERE document_id=%s", (did,)
        ).fetchone()[0]
        == 0
    )
    assert ocr_state() == original_ocr

    def checked_project(connection, document, period):
        # No month may project from an incomplete native source, including the
        # first batch that survived the prior process failure.
        assert steps()["native"] == 3
        assert (
            connection.execute(
                "SELECT count(*) FROM historical_price WHERE document_id=%s", (did,)
            ).fetchone()[0]
            == 3
        )
        assert ocr_state() == original_ocr
        return project_inputs(connection, document, period)

    def interrupted_references(*args):
        assert sum(step.startswith("published:") for step in steps()) == 3
        assert (
            db.execute(
                "SELECT count(*) FROM input_municipal_price WHERE document_id=%s",
                (did,),
            ).fetchone()[0]
            == 3
        )
        raise RuntimeError("simulated interrupted reference publication")

    with (
        patch.object(resumable_inputs, "BATCH_SIZE", 1),
        patch(
            "pipelines.ingestion.inputs.parse_inputs", side_effect=lambda _: iter(rows)
        ) as parse,
        patch.object(worker, "save_rows", wraps=save_rows) as save,
        patch(
            "pipelines.ingestion.inputs.project_inputs", side_effect=checked_project
        ) as project,
        patch(
            "pipelines.ingestion.input_references.extract_reference_rows",
            side_effect=interrupted_references,
        ),
    ):
        try:
            resumable_inputs.publish(db, b"fixture", did, kind, None)
        except RuntimeError as exc:
            assert str(exc) == "simulated interrupted reference publication"
        else:
            raise AssertionError("Reference interruption was not propagated")
        assert parse.call_count == 1  # Validation is not repeated.
        assert [call.args[2] for call in save.call_args_list] == [[rows[1]], [rows[2]]]
        assert [call.args[2] for call in project.call_args_list] == [
            row[2] for row in reversed(rows)
        ]
    assert steps() == {
        "validated": 3,
        "native-batch:000001": 1,
        "native-batch:000002": 1,
        "native-batch:000003": 1,
        "native": 3,
        "published:2026-01-31": 0,
        "published:2026-02-28": 0,
        "published:2026-03-31": 0,
    }
    assert ocr_state() == original_ocr

    with (
        patch(
            "pipelines.ingestion.inputs.parse_inputs",
            side_effect=AssertionError("Native parse repeated"),
        ),
        patch.object(
            worker, "save_rows", side_effect=AssertionError("Native COPY repeated")
        ),
        patch(
            "pipelines.ingestion.inputs.project_inputs",
            side_effect=AssertionError("Month projection repeated"),
        ),
        patch(
            "pipelines.ingestion.input_references.extract_reference_rows",
            return_value=0,
        ) as references,
    ):
        assert resumable_inputs.publish(db, b"fixture", did, kind, None) == (3, 0)
        references.assert_called_once()
    assert steps()["references"] == 0
    current_ocr = {row[0]: row[1:] for row in ocr_state()}
    for locator in ("pending", "deferred"):
        assert current_ocr[locator][0] == "native-complete"
        assert (
            current_ocr[locator][1]
            == "Native workbook extraction and monthly publication completed"
        )
        assert current_ocr[locator][2] is not None
    for row in original_ocr:
        if row[0] not in ("pending", "deferred"):
            assert current_ocr[row[0]] == row[1:]
    print(
        "PASS actual native COPY interruption: committed batch skipped, failed batch rolled back, projections wait for all native rows, OCR completes only after full publication"
    )


def main():
    with worker.connect() as db:
        for table in (
            "historical_price",
            "input_price",
            "input_municipal_price",
            "ingestion_checkpoint",
            "source_ocr_task",
        ):
            db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        db.execute(
            "CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz NOT NULL)"
        )
        db.execute(
            """CREATE TEMP TABLE input_revision(
            id text,department text,municipality text,observed_on date,
            retrieved_at timestamptz NOT NULL,
            PRIMARY KEY(id,department,municipality,observed_on))"""
        )
        # Fail closed if a future query references a table we did not shadow;
        # PostgreSQL must never fall back to published application tables.
        db.execute("SET search_path=pg_temp")
        assert all(
            row[0] == "t"
            for row in db.execute(
                """SELECT relpersistence FROM pg_class WHERE oid IN (
            'historical_price'::regclass,'input_price'::regclass,
            'input_municipal_price'::regclass,'ingestion_checkpoint'::regclass,
            'source_ocr_task'::regclass,'source_document'::regclass,
            'input_revision'::regclass)"""
            ).fetchall()
        )
        for offset, letter in enumerate("abcd", 1):
            db.execute(
                "INSERT INTO source_document VALUES(%s,%s::timestamptz)",
                (letter * 64, f"2026-01-{offset:02d}T00:00:00+00:00"),
            )
        did = "a" * 64
        newer = "b" * 64
        jan, feb = date(2026, 1, 31), date(2026, 2, 28)
        rows = [
            worker.record(
                "dane-inputs-municipal",
                day,
                "Arada",
                "El Carmen de Viboral",
                "hora/máquina",
                price,
                f"3.3!row {number}",
                details={
                    "category": "Servicios agrícolas",
                    "department": "Antioquia",
                    "municipality": "El Carmen de Viboral",
                    "presentation": "hora/máquina",
                },
            )
            for number, (day, price) in enumerate([(jan, 100000), (feb, 105000)], 1)
        ]
        calls = []

        def interrupted(db, doc, period):
            calls.append(period)
            if period == jan:
                # Failure after an actual write must roll back that entire month.
                project_inputs(db, doc, period)
                raise RuntimeError("simulated interrupted month")
            return project_inputs(db, doc, period)

        with (
            patch(
                "pipelines.ingestion.inputs.parse_inputs",
                side_effect=lambda _: iter(rows),
            ),
            patch(
                "pipelines.ingestion.input_references.extract_reference_rows",
                return_value=0,
            ),
            patch("pipelines.ingestion.inputs.project_inputs", side_effect=interrupted),
        ):
            try:
                resumable_inputs.publish(db, b"fixture", did, "inputs-municipal", None)
            except RuntimeError as exc:
                assert str(exc) == "simulated interrupted month"
            else:
                raise AssertionError("Failure was not propagated")
        assert db.execute(
            "SELECT observed_on FROM input_municipal_price"
        ).fetchall() == [(feb,)]
        assert db.execute("SELECT observed_on FROM input_revision").fetchall() == [
            (feb,)
        ]
        assert {
            r[0] for r in db.execute("SELECT step FROM ingestion_checkpoint").fetchall()
        } == {"validated", "native-batch:000001", "native", "published:2026-02-28"}
        with (
            patch(
                "pipelines.ingestion.inputs.parse_inputs",
                side_effect=AssertionError("Native stage repeated"),
            ),
            patch(
                "pipelines.ingestion.input_references.extract_reference_rows",
                return_value=0,
            ),
            patch(
                "pipelines.ingestion.inputs.project_inputs", wraps=project_inputs
            ) as project,
        ):
            count, conflicts = resumable_inputs.publish(
                db, b"fixture", did, "inputs-municipal", None
            )
        assert count == 2 and conflicts == 0 and project.call_count == 1
        assert project.call_args.args[2] == jan
        assert (
            db.execute("SELECT count(*) FROM input_municipal_price").fetchone()[0] == 2
        )
        # A byte-level revision with identical business values must retain the
        # valid original price evidence without rewriting every historical row.
        with db.transaction():
            worker.save_rows(db, newer, iter(rows))
            project_inputs(db, newer, jan)
        assert (
            db.execute(
                "SELECT document_id FROM input_municipal_price WHERE observed_on=%s",
                (jan,),
            ).fetchone()[0]
            == did
        )
        # A changed value DOES publish its new original and exact locator.
        changed = [*rows[0][:-1], dict(rows[0][-1])]
        changed[6] = 111000
        with db.transaction():
            worker.save_rows(db, "c" * 64, [changed])
            project_inputs(db, "c" * 64, jan)
        assert db.execute(
            "SELECT price,document_id FROM input_municipal_price WHERE observed_on=%s",
            (jan,),
        ).fetchone() == (111000, "c" * 64)
        verify_native_batch_resume(db)
        print(
            "PASS native checkpoint, month rollback, exact resume, unchanged-revision stability, changed-value provenance; all tables temporary"
        )


if __name__ == "__main__":
    main()
