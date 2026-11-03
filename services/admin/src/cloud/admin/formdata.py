from __future__ import annotations

import re
from email.parser import BytesParser
from email.policy import default


class UploadFormatError(ValueError):
    """Raised when an upload body is not one multipart file field."""


def parse_file_upload(content_type: str, body: bytes) -> tuple[str, bytes]:
    """Return the filename and bytes of the single form field named file."""
    media_type, boundary = _content_type(content_type)
    if media_type != "multipart/form-data" or not boundary:
        raise UploadFormatError("expected multipart/form-data")
    try:
        marker = b"--" + boundary.encode("ascii")
    except UnicodeEncodeError as error:
        raise UploadFormatError("invalid multipart boundary") from error
    if not body.startswith(marker):
        raise UploadFormatError("malformed multipart body")

    files: list[tuple[str, bytes]] = []
    for chunk in body.split(marker)[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        header_blob, separator, content = chunk.partition(b"\r\n\r\n")
        if not separator:
            header_blob, separator, content = chunk.partition(b"\n\n")
        if not separator:
            continue
        if content.endswith(b"\r\n"):
            content = content[:-2]
        elif content.endswith(b"\n"):
            content = content[:-1]
        message = BytesParser(policy=default).parsebytes(header_blob + b"\r\n\r\n")
        disposition = message.get("Content-Disposition", "")
        if "form-data" not in disposition.casefold():
            continue
        field_name = message.get_param("name", header="content-disposition")
        filename = message.get_filename()
        if field_name == "file" and filename:
            files.append((filename, content))

    if len(files) != 1:
        raise UploadFormatError("expected one file field")
    return files[0]


def _content_type(value: str) -> tuple[str, str]:
    match = re.match(
        r"\s*([^;]+)\s*(?:;\s*boundary\s*=\s*(?:\"([^\"]+)\"|([^;]+)))?",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return "", ""
    media_type = match.group(1).strip().casefold()
    boundary = (match.group(2) or match.group(3) or "").strip()
    return media_type, boundary
