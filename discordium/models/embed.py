"""Discord Embed model — full v10 coverage with fluent builder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Self

from .base import Model


class EmbedField(Model):
    """A single field inside an Embed."""

    name: str
    value: str
    inline: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data["name"],
            value=data["value"],
            inline=data.get("inline", False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "inline": self.inline}


class EmbedFooter(Model):
    text: str
    icon_url: str | None = None
    proxy_icon_url: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            text=data["text"],
            icon_url=data.get("icon_url"),
            proxy_icon_url=data.get("proxy_icon_url"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        if self.icon_url:
            d["icon_url"] = self.icon_url
        return d


class EmbedAuthor(Model):
    name: str
    url: str | None = None
    icon_url: str | None = None
    proxy_icon_url: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            name=data["name"],
            url=data.get("url"),
            icon_url=data.get("icon_url"),
            proxy_icon_url=data.get("proxy_icon_url"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.url:
            d["url"] = self.url
        if self.icon_url:
            d["icon_url"] = self.icon_url
        return d


class EmbedProvider(Model):
    """Embed provider (only present on link embeds)."""

    name: str | None = None
    url: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(name=data.get("name"), url=data.get("url"))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.name:
            d["name"] = self.name
        if self.url:
            d["url"] = self.url
        return d


class EmbedVideo(Model):
    """Video element of a link embed."""

    url: str | None = None
    proxy_url: str | None = None
    height: int | None = None
    width: int | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            url=data.get("url"),
            proxy_url=data.get("proxy_url"),
            height=data.get("height"),
            width=data.get("width"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.url:
            d["url"] = self.url
        return d


class EmbedImage(Model):
    """Image or thumbnail element of an embed."""

    url: str
    proxy_url: str | None = None
    height: int | None = None
    width: int | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            url=data.get("url", ""),
            proxy_url=data.get("proxy_url"),
            height=data.get("height"),
            width=data.get("width"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url}


class Embed(Model):
    """Rich embed for Discord messages — full v10 field coverage.

    Supports a fluent builder pattern::

        embed = (
            Embed(title="Hello", color=0x5865F2)
            .set_description("World")
            .add_field(name="Status", value="Online", inline=True)
            .set_footer(text="Powered by discordium")
            .set_timestamp()
        )

    All builder methods return a **new** ``Embed`` instance (immutable).
    """

    title: str | None = None
    type: str = "rich"          # rich | image | video | gifv | article | link
    description: str | None = None
    url: str | None = None
    color: int | None = None
    timestamp: str | None = None
    footer: EmbedFooter | None = None
    image: EmbedImage | None = None
    thumbnail: EmbedImage | None = None
    video: EmbedVideo | None = None
    provider: EmbedProvider | None = None
    author: EmbedAuthor | None = None
    fields: list[EmbedField] | None = None

    # Convenience aliases (kept for back-compat)

    @property
    def image_url(self) -> str | None:
        return self.image.url if self.image else None

    @property
    def thumbnail_url(self) -> str | None:
        return self.thumbnail.url if self.thumbnail else None

    @property
    def field_count(self) -> int:
        return len(self.fields) if self.fields else 0

    @property
    def total_char_count(self) -> int:
        """Approximate character count across all text fields (Discord limit: 6000)."""
        total = 0
        if self.title:
            total += len(self.title)
        if self.description:
            total += len(self.description)
        if self.footer:
            total += len(self.footer.text)
        if self.author:
            total += len(self.author.name)
        for f in (self.fields or []):
            total += len(f.name) + len(f.value)
        return total

    # Builder helpers

    def set_title(self, title: str) -> Embed:
        return self.evolve(title=title)

    def set_description(self, description: str) -> Embed:
        return self.evolve(description=description)

    def set_url(self, url: str) -> Embed:
        return self.evolve(url=url)

    def set_color(self, color: int) -> Embed:
        return self.evolve(color=color)

    def add_field(self, *, name: str, value: str, inline: bool = False) -> Embed:
        field = EmbedField(name=name, value=value, inline=inline)
        existing = list(self.fields) if self.fields else []
        existing.append(field)
        return self.evolve(fields=existing)

    def insert_field(self, index: int, *, name: str, value: str, inline: bool = False) -> Embed:
        """Insert a field at a specific position."""
        field = EmbedField(name=name, value=value, inline=inline)
        existing = list(self.fields) if self.fields else []
        existing.insert(index, field)
        return self.evolve(fields=existing)

    def remove_field(self, index: int) -> Embed:
        """Remove the field at *index*."""
        existing = list(self.fields) if self.fields else []
        existing.pop(index)
        return self.evolve(fields=existing or None)

    def clear_fields(self) -> Embed:
        return self.evolve(fields=None)

    def set_footer(self, *, text: str, icon_url: str | None = None) -> Embed:
        return self.evolve(footer=EmbedFooter(text=text, icon_url=icon_url))

    def set_author(
        self, *, name: str, url: str | None = None, icon_url: str | None = None
    ) -> Embed:
        return self.evolve(author=EmbedAuthor(name=name, url=url, icon_url=icon_url))

    def set_image(self, url: str) -> Embed:
        return self.evolve(image=EmbedImage(url=url))

    def set_thumbnail(self, url: str) -> Embed:
        return self.evolve(thumbnail=EmbedImage(url=url))

    def set_timestamp(self, dt: datetime | None = None) -> Embed:
        """Set the embed timestamp. Defaults to the current UTC time."""
        ts = (dt or datetime.now(timezone.utc)).isoformat()
        return self.evolve(timestamp=ts)

    # Serialisation

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.type != "rich" and any((self.title, self.description, self.url, self.color, self.timestamp, self.footer, self.image, self.thumbnail, self.video, self.provider, self.author, self.fields)):
            d["type"] = self.type
        if self.title is not None:
            d["title"] = self.title
        if self.description is not None:
            d["description"] = self.description
        if self.url is not None:
            d["url"] = self.url
        if self.color is not None:
            d["color"] = self.color
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.footer is not None:
            d["footer"] = self.footer.to_dict()
        if self.image is not None:
            d["image"] = self.image.to_dict()
        if self.thumbnail is not None:
            d["thumbnail"] = self.thumbnail.to_dict()
        if self.video is not None:
            d["video"] = self.video.to_dict()
        if self.provider is not None:
            d["provider"] = self.provider.to_dict()
        if self.author is not None:
            d["author"] = self.author.to_dict()
        if self.fields:
            d["fields"] = [f.to_dict() for f in self.fields]
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        footer = EmbedFooter.from_payload(data["footer"]) if "footer" in data else None
        author = EmbedAuthor.from_payload(data["author"]) if "author" in data else None
        provider = EmbedProvider.from_payload(data["provider"]) if "provider" in data else None
        image = EmbedImage.from_payload(data["image"]) if "image" in data else None
        thumbnail = EmbedImage.from_payload(data["thumbnail"]) if "thumbnail" in data else None
        video = EmbedVideo.from_payload(data["video"]) if "video" in data else None
        fields = [EmbedField.from_payload(f) for f in data["fields"]] if "fields" in data else None
        return cls(
            title=data.get("title"),
            type=data.get("type", "rich"),
            description=data.get("description"),
            url=data.get("url"),
            color=data.get("color"),
            timestamp=data.get("timestamp"),
            footer=footer,
            image=image,
            thumbnail=thumbnail,
            video=video,
            provider=provider,
            author=author,
            fields=fields,
        )
