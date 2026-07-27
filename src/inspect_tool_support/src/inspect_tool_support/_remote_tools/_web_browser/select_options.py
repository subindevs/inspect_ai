"""Resolving typed text to an option of an HTML `<select>` element.

A `<select>` cannot be driven by typing. Clicking one opens the browser's
native popup, where keystrokes drive *label* typeahead — a prefix search over
the options' visible text that ignores their `value` attributes entirely, and
that resolves an ambiguous prefix to the first match rather than failing. Text
naming an option unambiguously ("option3") therefore selects a different option
("Option 1"), with nothing to distinguish the result from a successful
selection. So instead of typing, we read the element's options and pick one.
"""

from typing import NamedTuple, Sequence


class SelectOption(NamedTuple):
    """An `<option>` of an HTML `<select>` element."""

    value: str
    """The option's `value` attribute (what a form submission sends)."""

    label: str
    """The option's visible text (what the accessibility tree renders)."""


def match_select_option(options: Sequence[SelectOption], text: str) -> int | None:
    """Finds the option that `text` refers to.

    Matching proceeds in decreasing order of specificity: an exact `value`,
    an exact label, either of those ignoring case and surrounding whitespace,
    and finally a label prefix. Both `value` and label are accepted because the
    accessibility tree shows a model the label while the page's markup names the
    value, and either is a reasonable thing for it to type.

    The prefix pass is honoured only when it names a single option. Resolving an
    ambiguous prefix to its first match is precisely what makes native typeahead
    select the wrong entry, and a caller that can distinguish "no match" from a
    match can report the ambiguity instead of guessing.

    Args:
      options: The element's options, in document order.
      text: The text passed to the type tool.

    Returns:
      Index into `options`, or None if `text` names no option unambiguously.
    """
    normalized = _normalized(text)

    if exact := (
        [index for index, option in enumerate(options) if option.value == text]
        or [index for index, option in enumerate(options) if option.label == text]
        or [
            index
            for index, option in enumerate(options)
            if _normalized(option.value) == normalized
        ]
        or [
            index
            for index, option in enumerate(options)
            if _normalized(option.label) == normalized
        ]
    ):
        return exact[0]

    prefixed = [
        index
        for index, option in enumerate(options)
        if _normalized(option.label).startswith(normalized)
    ]
    return prefixed[0] if len(prefixed) == 1 else None


def describe_select_options(options: Sequence[SelectOption]) -> str:
    """Renders options for an error message, so a model can retry with a real one."""
    return ", ".join(
        f'"{option.label}" (value: "{option.value}")' for option in options
    )


def _normalized(text: str) -> str:
    return text.strip().casefold()
