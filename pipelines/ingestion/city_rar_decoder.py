"""Bounded reader for the one verified DANE RAR5 city archive.

This source-local decoder is intentionally not a general archive dispatcher.
It accepts the exact retained source URL/body hash and exact 17-PDF manifest.
Member payloads are read into memory and hash-checked; member paths are never
written to disk. The compressed source is briefly staged in a private temp dir
because the upstream UnRAR C API accepts a filesystem path.

UnRAR is used only to read/handle RAR archives. See the bundled source license.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import unicodedata

AUG19_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-19-08-2022.zip"
AUG19_SHA256 = "f8a481a767495427ecc056cbb150745c44d920b7143fde7e2e7b495b5812542a"
RAR5_MAGIC = b"Rar!\x1a\x07\x01\x00"
MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
AUG19_DOCUMENT_ID = AUG19_SHA256
AUG19_TITLE = "DANE - bol-reg-19-08-2022.zip"
AUG19_PUBLISHER = "DANE"
AUG19_MEDIA_TYPE = "application/zip"
AUG19_KIND = "original"
AUG19_REFERENCE_PERIOD = "2022-08-19"
AUG19_METADATA = {
    "retention": "permanent",
    "ingestion_kind": "city-zip",
    "original_filename": "bol-reg-19-08-2022.zip",
}
AUG19_MEMBERS = {
    "Bogotá, Corabastos 19-8-2022.pdf": (31026, "0a16b45d2a24764d7d443725d8f010c560560c310bdd54480da43b28be194d11"),
    "Bucaramanga, Centroabastos-19-08-2022.pdf": (86765, "bfd95fe955cac7890c55fcb927717d1c9bfd2a7119ca20f484ac089527054646"),
    "Cartagena, Bazurto-19-08-2022.pdf": (81988, "fccb0e440d3ef86a0b22b4bfeb815008e03afd5df9fcb8f6eeebd1d7aa1380b8"),
    "Cúcuta, Cenabastos-19-08-2022.pdf": (163764, "b4fdb8e610004158fd3925fa7c788cc1a7b4f836399ef0331e730b745d269ccd"),
    "Ibagué, Plaza La 21-19-08-2022.pdf": (196645, "a09fd2b201666f70c666ea02b5c473d73f2ea326ffc2f65f158374cdab9f775d"),
    "Medellín, Central Mayorista de Antioquia-19-08-2022.pdf": (156440, "a5d19acad3be42e7aefc63dc4fb281abbd4f6bc2544f55a4bef17fdc5e9c6fe5"),
    "Montería, Mercado del Sur-19-08-2022.pdf": (85421, "b6a6033e1ea603d9171582a3145b9b967d81f7cde0f597ad9bf3af1929341913"),
    "Neiva, Surabastos-19-08-2022.pdf": (103957, "ee34bac5a2af3b90f3349a8069ba0d2560a9d19c5ba7ed59166b5e96a4352d73"),
    "Pereira, Mercasa-19-08-2022.pdf": (112089, "bfb8c42b6d7d5925029dd8b27bfd602562c8be175dd652b2fc4c9872e63744e1"),
    "Popayán, Plaza de mercado del barrio Bolívar-19-08-2022.pdf": (134008, "f1c41a8e8ac772d25cf09e96cd0206b521cd58e952f85dcd9b6d1c59378e0488"),
    "Santa Marta (Magdalena)-19-08-2022.pdf": (48152, "480bec486fa6784f315b58b6bb4bed1bf3187b274d735bbc88586b7c68d2e988"),
    "Sincelejo, Nuevo Mercado-19-08-2022.pdf": (78348, "d0381f6f658ecb6df6cea34a0e923d6f370a40f69254a563789501e1f0420755"),
    "Tunja, Complejo de Servicios del Sur-19-08-2022.pdf": (131055, "9347bf137e782e195147aaa19f34e7ddf40dc325e444aba6ba8ceb298168c1f6"),
    "Valledupar, Mercabastos-19-08-2022.pdf": (72484, "6b50046990b5927e333447e3be6825714f3ed2e13a810aac09023eaf8d1ecdaa"),
    "Villavicencio, CAV-19-08-2022.pdf": (106363, "d69154914a27cc30e8b13c044d13fdc81ecd8c3da7d518f5ef13d004af34307f"),
    "Barranquilla, Barranquillita-19-08-2022.pdf": (100119, "3e19d43c6a938816776c16aa912c3f7552a283e39afdd09af51d1301890fc10b"),
    "Barranquilla, Granabastos-19-08-2022.pdf": (60744, "021848f12e35512226aebb97d153b5524efc714c6388e3db9b544ee5debfbe3f"),
}
AUG19_EXPANDED_BYTES = sum(size for size, _ in AUG19_MEMBERS.values())
AUG19_MAX_MEMBER_BYTES = max(size for size, _ in AUG19_MEMBERS.values())


class ArchiveCandidateError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    # name always matches the exact native source manifest spelling.
    name: str
    size: int
    is_dir: bool = False
    is_symlink: bool = False
    needs_password: bool = False


@dataclass(frozen=True)
class MemberPayload:
    name: str
    data: bytes


def _safe_flat_pdf_name(name: str) -> None:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise ArchiveCandidateError(f"unsafe RAR member name: {name!r}")
    if (name.startswith("/") or PurePosixPath(name).is_absolute()
            or PureWindowsPath(name).is_absolute() or PureWindowsPath(name).drive):
        raise ArchiveCandidateError(f"absolute or drive-qualified RAR member: {name!r}")
    parts = name.split("/")
    if len(parts) != 1 or any(part in ("", ".", "..") for part in parts):
        raise ArchiveCandidateError(f"non-flat RAR member name: {name!r}")
    if not name.lower().endswith(".pdf"):
        raise ArchiveCandidateError(f"unexpected non-PDF RAR member: {name!r}")


class Unrar2Rar5Reader:
    """Decode and hash-check all members from the one pinned DANE RAR5 body."""

    def __init__(self, data: bytes, source_url: str, *, expected_members,
                 max_members: int, max_member_bytes: int, max_total_bytes: int):
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ArchiveCandidateError("RAR source exceeds compressed-byte cap")
        if (source_url != AUG19_URL or sha256(data).hexdigest() != AUG19_SHA256
                or not data.startswith(RAR5_MAGIC)):
            raise ArchiveCandidateError("UnRAR reader is pinned to the exact official DANE RAR5 source")
        if len(expected_members) != max_members:
            raise ArchiveCandidateError("expected source manifest and member cap disagree")

        expected_by_nfc = {}
        for source_name, (size, digest) in expected_members.items():
            _safe_flat_pdf_name(source_name)
            key = unicodedata.normalize("NFC", source_name)
            if key in expected_by_nfc:
                raise ArchiveCandidateError("source manifest has Unicode-normalization collisions")
            expected_by_nfc[key] = (source_name, int(size), str(digest))

        try:
            from unrar.cffi.rarfile import RarFile
        except ImportError as exc:
            raise ArchiveCandidateError("unrar2-cffi native module is not packaged") from exc

        self.members = []
        self.payloads = {}
        self.actual_names = {}
        total_declared = 0
        total_decoded = 0
        seen = set()

        # The native UnRAR API takes a path. Stage only the already SHA-bound
        # source archive; `RarFile.read` returns each member in memory and does
        # not extract member paths to the filesystem.
        try:
            with tempfile.TemporaryDirectory(prefix="agro-rar-input-") as temp_dir:
                archive_path = Path(temp_dir) / "source.rar"
                archive_path.write_bytes(data)
                archive = RarFile(archive_path)
                entries = archive.infolist()
                if not entries or len(entries) != max_members:
                    raise ArchiveCandidateError("RAR member count differs from exact manifest")
                for entry in entries:
                    actual_name = entry.filename
                    _safe_flat_pdf_name(actual_name)
                    key = unicodedata.normalize("NFC", actual_name)
                    expected = expected_by_nfc.get(key)
                    if expected is None:
                        raise ArchiveCandidateError(f"unexpected RAR member: {actual_name!r}")
                    name, expected_size, expected_sha = expected
                    if key in seen:
                        raise ArchiveCandidateError("duplicate normalized RAR member identity")
                    seen.add(key)
                    size = int(entry.file_size)
                    encrypted = bool(entry.flag_bits & 0x0004)
                    if entry.is_dir() or encrypted:
                        raise ArchiveCandidateError(f"directory/encrypted RAR member: {actual_name!r}")
                    if size < 0 or size > max_member_bytes or size != expected_size:
                        raise ArchiveCandidateError(f"declared RAR member size mismatch/cap: {name!r}")
                    total_declared += size
                    if total_declared > max_total_bytes:
                        raise ArchiveCandidateError("declared RAR expanded size exceeds cap")
                    body = archive.read(actual_name)
                    if len(body) > max_member_bytes:
                        raise ArchiveCandidateError(f"decoded RAR member exceeds cap: {name!r}")
                    total_decoded += len(body)
                    if total_decoded > max_total_bytes:
                        raise ArchiveCandidateError("decoded RAR expanded size exceeds cap")
                    if len(body) != expected_size or sha256(body).hexdigest() != expected_sha:
                        raise ArchiveCandidateError(f"RAR member bytes differ from exact source manifest: {name!r}")
                    if not body.startswith(b"%PDF-"):
                        raise ArchiveCandidateError(f"RAR member is not a PDF: {name!r}")
                    self.members.append(Member(name=name, size=len(body)))
                    self.actual_names[name] = actual_name
                    self.payloads[name] = body
        except ArchiveCandidateError:
            raise
        except Exception as exc:
            raise ArchiveCandidateError(f"UnRAR decode failed: {type(exc).__name__}: {exc}") from exc

        if seen != set(expected_by_nfc):
            raise ArchiveCandidateError("RAR source cohort is incomplete")
        if total_declared != total_decoded:
            raise ArchiveCandidateError("declared/decoded RAR cohort byte totals differ")

    def read(self, name: str, limit: int) -> bytes:
        payload = self.payloads[name]
        if len(payload) > limit:
            raise ArchiveCandidateError("decoded RAR member exceeds caller cap")
        return payload


def read_exact_aug19_members(data: bytes, source_url: str, *, expected_members,
                             max_members: int, max_member_bytes: int,
                             max_total_bytes: int) -> list[MemberPayload]:
    reader = Unrar2Rar5Reader(data, source_url, expected_members=expected_members,
                              max_members=max_members,
                              max_member_bytes=max_member_bytes,
                              max_total_bytes=max_total_bytes)
    return [MemberPayload(member.name, reader.read(member.name, max_member_bytes))
            for member in reader.members]


def decode_pinned_aug19_source(data: bytes):
    """Decode every pinned PDF and return (reader, native_version, platform)."""
    import platform
    from unrar.cffi import unrarlib

    reader = Unrar2Rar5Reader(
        data, AUG19_URL, expected_members=AUG19_MEMBERS,
        max_members=len(AUG19_MEMBERS),
        max_member_bytes=AUG19_MAX_MEMBER_BYTES,
        max_total_bytes=AUG19_EXPANDED_BYTES,
    )
    return reader, tuple(unrarlib.get_unrar_version()), platform.platform()
