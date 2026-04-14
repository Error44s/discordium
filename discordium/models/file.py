"""File upload support for Discord messages.

Provides ``File`` objects that can be attached to messages::

    from discordium.models.file import File

    # From path
    await rest.send_message(channel, "Here's the log:", files=[
        File.from_path("output.log"),
    ])

    # From bytes
    await rest.send_message(channel, files=[
        File(b"hello world", filename="hello.txt"),
    ])

    # From file-like object
    with open("image.png", "rb") as f:
        await rest.send_message(channel, files=[
            File(f.read(), filename="image.png", content_type="image/png"),
        ])
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any


class File:
    """Represents a file to be uploaded to Discord.

    Parameters
    ----------
    data:
        Raw bytes of the file content.
    filename:
        Display filename.
    content_type:
        MIME type (auto-detected from filename if not provided).
    description:
        Alt text / description for the attachment.
    spoiler:
        Whether the file should be marked as a spoiler.
    """

    __slots__ = ("data", "filename", "content_type", "description", "spoiler")

    def __init__(
        self,
        data: bytes,
        *,
        filename: str = "file.bin",
        content_type: str | None = None,
        description: str | None = None,
        spoiler: bool = False,
    ) -> None:
        self.data = data
        self.filename = f"SPOILER_{filename}" if spoiler else filename
        self.content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.description = description
        self.spoiler = spoiler

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        filename: str | None = None,
        description: str | None = None,
        spoiler: bool = False,
    ) -> File:
        """Create a File from a filesystem path."""
        p = Path(path)
        data = p.read_bytes()
        return cls(
            data,
            filename=filename or p.name,
            description=description,
            spoiler=spoiler,
        )

    def to_attachment_dict(self, index: int) -> dict[str, Any]:
        """Generate the attachment metadata for the JSON payload."""
        d: dict[str, Any] = {
            "id": index,
            "filename": self.filename,
        }
        if self.description:
            d["description"] = self.description
        return d

    def __repr__(self) -> str:
        size = len(self.data)
        unit = "B"
        if size > 1024 * 1024:
            size_f = size / (1024 * 1024)
            unit = "MB"
        elif size > 1024:
            size_f = size / 1024
            unit = "KB"
        else:
            size_f = float(size)
        return f"File({self.filename!r}, {size_f:.1f}{unit})"
