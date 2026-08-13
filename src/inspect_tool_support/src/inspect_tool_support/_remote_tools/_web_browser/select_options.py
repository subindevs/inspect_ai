"""Resolving typed text to an option of an HTML `<select>` element.

A `<select>` cannot be driven by typing. Clicking one opens the browser's
native popup, where keystrokes drive *label* typeahead — a prefix search over
the options' visible text that ignores their `value` attributes entirely, and
that resolves an ambiguous prefix to the first match rather than failing. Text
naming an option unambiguously ("option3") therefore selects a different option
("Option 1"), with nothing to distinguish the result from a successful
selection. So instead of typing, we read the element's options and pick one.
"""

from typing import Callable, NamedTuple, Sequence

# Cap on how many options an error message spells out. The message goes back to
# the model as tool output, and a long picker — a country list, say — would
# crowd its context without telling it anything more useful.
_MAX_DESCRIBED_OPTIONS = 30


class SelectOption(NamedTuple):
    """An `<option>` of an HTML `<select>` element."""

    value: str
    """The option's `value` attribute (what a form submission sends)."""

    label: str
    """The option's visible text (what the accessibility tree renders)."""

    disabled: bool = False
    """Whether the option, or the `<optgroup>` holding it, is disabled."""


def match_select_option(options: Sequence[SelectOption], text: str) -> int | None:
    """Finds the option that `text` refers to.

    Matching proceeds in decreasing order of specificity: an exact label, an
    exact `value`, either of those ignoring case and surrounding whitespace,
    and finally a label prefix. Both label and `value` are accepted because the
    accessibility tree shows a model the label while the page's markup names the
    value, and either is a reasonable thing for it to type.

    Labels win over values because the label is what the model can actually see.
    Where the two disagree — one option labelled "Two", another whose *value* is
    "Two" — reading the tree and typing what it says has to select the option
    that displayed it, or we reintroduce the silent mis-selection this module
    exists to prevent.

    The prefix pass is honoured only when it names a single option. Resolving an
    ambiguous prefix to its first match is precisely what makes native typeahead
    select the wrong entry, and a caller that can distinguish "no match" from a
    match can report the ambiguity instead of guessing.

    Disabled options are never matched, since a user could not select one.

    Args:
      options: The element's options, in document order.
      text: The text passed to the type tool.

    Returns:
      Index into `options` — counting disabled ones, so it can be assigned
      straight to `selectedIndex` — or None if `text` names no option
      unambiguously.
    """
    normalized = _normalized(text)

    def matching(predicate: Callable[[SelectOption], bool]) -> list[int]:
        return [
            index
            for index, option in enumerate(options)
            if not option.disabled and predicate(option)
        ]

    if exact := (
        matching(lambda option: option.label == text)
        or matching(lambda option: option.value == text)
        or matching(lambda option: _normalized(option.label) == normalized)
        or matching(lambda option: _normalized(option.value) == normalized)
    ):
        return exact[0]

    prefixed = matching(lambda option: _normalized(option.label).startswith(normalized))
    return prefixed[0] if len(prefixed) == 1 else None


def describe_select_options(options: Sequence[SelectOption]) -> str:
    """Renders options for an error message, so a model can retry with a real one."""
    described = ", ".join(
        _describe_option(option) for option in options[:_MAX_DESCRIBED_OPTIONS]
    )
    undescribed = len(options) - _MAX_DESCRIBED_OPTIONS
    return f"{described}, and {undescribed} more" if undescribed > 0 else described


def _describe_option(option: SelectOption) -> str:
    disabled = " [disabled]" if option.disabled else ""
    return f'"{option.label}" (value: "{option.value}"){disabled}'


def _normalized(text: str) -> str:
    return text.strip().casefold()
