"""Discord Message Components — Buttons, Select Menus, Modals, Text Inputs.

Builder-pattern API for composing interactive UIs::

    from discordium.models.components import ActionRow, Button, ButtonStyle, SelectMenu

    row = ActionRow(
        Button(label="Accept", custom_id="accept", style=ButtonStyle.SUCCESS),
        Button(label="Deny", custom_id="deny", style=ButtonStyle.DANGER),
    )

    modal = Modal(
        title="Feedback",
        custom_id="feedback_modal",
        components=[
            ActionRow(TextInput(
                label="Your feedback",
                custom_id="feedback_text",
                style=TextInputStyle.PARAGRAPH,
            )),
        ],
    )
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

# Enums

class ComponentType(IntEnum):
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8


class ButtonStyle(IntEnum):
    PRIMARY = 1    # blurple
    SECONDARY = 2  # grey
    SUCCESS = 3    # green
    DANGER = 4     # red
    LINK = 5       # grey, navigates to URL


class TextInputStyle(IntEnum):
    SHORT = 1      # single-line
    PARAGRAPH = 2  # multi-line

# Base

class Component:
    """Base class for all components."""

    __slots__ = ("type",)

    def __init__(self, type: ComponentType) -> None:
        self.type = type

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

# Button

class Button(Component):
    """An interactive button.

    Parameters
    ----------
    label:
        Text shown on the button.
    custom_id:
        Developer-defined ID (required for non-link buttons).
    style:
        Visual style.
    emoji:
        Emoji dict like ``{"name": "🎉"}`` or ``{"id": "12345", "name": "custom"}``.
    url:
        URL for link-style buttons.
    disabled:
        Whether the button is greyed out.
    """

    __slots__ = ("label", "custom_id", "style", "emoji", "url", "disabled")

    def __init__(
        self,
        *,
        label: str | None = None,
        custom_id: str | None = None,
        style: ButtonStyle = ButtonStyle.PRIMARY,
        emoji: dict[str, Any] | str | None = None,
        url: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(ComponentType.BUTTON)
        self.label = label
        self.custom_id = custom_id
        self.style = style
        self.url = url
        self.disabled = disabled

        # Normalise emoji shorthand
        if isinstance(emoji, str):
            self.emoji: dict[str, Any] | None = {"name": emoji}
        else:
            self.emoji = emoji

        # Validate
        if style == ButtonStyle.LINK:
            if url is None:
                raise ValueError("Link buttons require a url")
            if custom_id is not None:
                raise ValueError("Link buttons cannot have a custom_id")
        else:
            if custom_id is None:
                raise ValueError("Non-link buttons require a custom_id")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "style": self.style}
        if self.label is not None:
            d["label"] = self.label
        if self.custom_id is not None:
            d["custom_id"] = self.custom_id
        if self.emoji is not None:
            d["emoji"] = self.emoji
        if self.url is not None:
            d["url"] = self.url
        if self.disabled:
            d["disabled"] = True
        return d

# Select Menus

class SelectOption:
    """A single option in a string select menu."""

    __slots__ = ("label", "value", "description", "emoji", "default")

    def __init__(
        self,
        *,
        label: str,
        value: str,
        description: str | None = None,
        emoji: dict[str, Any] | str | None = None,
        default: bool = False,
    ) -> None:
        self.label = label
        self.value = value
        self.description = description
        self.default = default
        if isinstance(emoji, str):
            self.emoji: dict[str, Any] | None = {"name": emoji}
        else:
            self.emoji = emoji

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"label": self.label, "value": self.value}
        if self.description is not None:
            d["description"] = self.description
        if self.emoji is not None:
            d["emoji"] = self.emoji
        if self.default:
            d["default"] = True
        return d


class SelectMenu(Component):
    """A dropdown select menu.

    For string selects, provide ``options``. For user/role/channel selects,
    use the appropriate ``select_type``.
    """

    __slots__ = (
        "custom_id", "options", "placeholder", "min_values",
        "max_values", "disabled", "channel_types",
    )

    def __init__(
        self,
        *,
        custom_id: str,
        select_type: ComponentType = ComponentType.STRING_SELECT,
        options: list[SelectOption] | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        channel_types: list[int] | None = None,
    ) -> None:
        super().__init__(select_type)
        self.custom_id = custom_id
        self.options = options
        self.placeholder = placeholder
        self.min_values = min_values
        self.max_values = max_values
        self.disabled = disabled
        self.channel_types = channel_types

        if select_type == ComponentType.STRING_SELECT and not options:
            raise ValueError("String selects require at least one option")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "custom_id": self.custom_id,
            "min_values": self.min_values,
            "max_values": self.max_values,
        }
        if self.options:
            d["options"] = [o.to_dict() for o in self.options]
        if self.placeholder is not None:
            d["placeholder"] = self.placeholder
        if self.disabled:
            d["disabled"] = True
        if self.channel_types is not None:
            d["channel_types"] = self.channel_types
        return d

# Text Input (for Modals)

class TextInput(Component):
    """A text input field for modals."""

    __slots__ = (
        "custom_id", "label", "style", "min_length",
        "max_length", "required", "value", "placeholder",
    )

    def __init__(
        self,
        *,
        custom_id: str,
        label: str,
        style: TextInputStyle = TextInputStyle.SHORT,
        min_length: int = 0,
        max_length: int = 4000,
        required: bool = True,
        value: str | None = None,
        placeholder: str | None = None,
    ) -> None:
        super().__init__(ComponentType.TEXT_INPUT)
        self.custom_id = custom_id
        self.label = label
        self.style = style
        self.min_length = min_length
        self.max_length = max_length
        self.required = required
        self.value = value
        self.placeholder = placeholder

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "custom_id": self.custom_id,
            "label": self.label,
            "style": self.style,
        }
        if self.min_length > 0:
            d["min_length"] = self.min_length
        if self.max_length != 4000:
            d["max_length"] = self.max_length
        if not self.required:
            d["required"] = False
        if self.value is not None:
            d["value"] = self.value
        if self.placeholder is not None:
            d["placeholder"] = self.placeholder
        return d

# Action Row

class ActionRow(Component):
    """Container that holds up to 5 buttons or 1 select menu.

    Usage::

        row = ActionRow(
            Button(label="Yes", custom_id="yes", style=ButtonStyle.SUCCESS),
            Button(label="No", custom_id="no", style=ButtonStyle.DANGER),
        )
    """

    __slots__ = ("children",)

    def __init__(self, *children: Component) -> None:
        super().__init__(ComponentType.ACTION_ROW)
        if len(children) > 5:
            raise ValueError("ActionRow can hold at most 5 children")
        self.children = list(children)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "components": [c.to_dict() for c in self.children],
        }

# Modal

class Modal:
    """An interactive popup form.

    Modals are sent as an interaction response, not as a message component.
    """

    __slots__ = ("title", "custom_id", "components")

    def __init__(
        self,
        *,
        title: str,
        custom_id: str,
        components: list[ActionRow] | None = None,
    ) -> None:
        self.title = title
        self.custom_id = custom_id
        self.components = components or []

    def add_field(
        self,
        *,
        label: str,
        custom_id: str,
        style: TextInputStyle = TextInputStyle.SHORT,
        **kwargs: Any,
    ) -> Modal:
        """Fluent helper — add a text input wrapped in an ActionRow."""
        ti = TextInput(custom_id=custom_id, label=label, style=style, **kwargs)
        self.components.append(ActionRow(ti))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "custom_id": self.custom_id,
            "components": [c.to_dict() for c in self.components],
        }

# Parsing incoming components from payloads

def parse_component(data: dict[str, Any]) -> Component:
    """Parse a component from a Discord API payload."""
    ctype = ComponentType(data["type"])

    match ctype:
        case ComponentType.ACTION_ROW:
            children = [parse_component(c) for c in data.get("components", [])]
            row = ActionRow(*children)
            return row

        case ComponentType.BUTTON:
            return Button(
                label=data.get("label"),
                custom_id=data.get("custom_id"),
                style=ButtonStyle(data.get("style", 1)),
                emoji=data.get("emoji"),
                url=data.get("url"),
                disabled=data.get("disabled", False),
            )

        case ComponentType.STRING_SELECT:
            options = [
                SelectOption(
                    label=o["label"],
                    value=o["value"],
                    description=o.get("description"),
                    emoji=o.get("emoji"),
                    default=o.get("default", False),
                )
                for o in data.get("options", [])
            ]
            return SelectMenu(
                custom_id=data["custom_id"],
                options=options,
                placeholder=data.get("placeholder"),
                min_values=data.get("min_values", 1),
                max_values=data.get("max_values", 1),
                disabled=data.get("disabled", False),
            )

        case ComponentType.TEXT_INPUT:
            return TextInput(
                custom_id=data["custom_id"],
                label=data.get("label", ""),
                style=TextInputStyle(data.get("style", 1)),
                value=data.get("value"),
                placeholder=data.get("placeholder"),
            )

        case _:
            # User/role/channel/mentionable selects
            return SelectMenu(
                custom_id=data["custom_id"],
                select_type=ctype,
                placeholder=data.get("placeholder"),
                min_values=data.get("min_values", 1),
                max_values=data.get("max_values", 1),
                disabled=data.get("disabled", False),
            )
