from inspect_tool_support._remote_tools._web_browser.select_options import (
    SelectOption,
    describe_select_options,
    match_select_option,
)

# The dropdown from https://github.com/UKGovernmentBEIS/inspect_ai/issues/2043,
# whose option values and labels differ only in case and spacing — enough for
# native typeahead to select the wrong one.
issue_2043_options = [
    SelectOption("", "Choose an option"),
    SelectOption("option1", "Option 1"),
    SelectOption("option2", "Option 2"),
    SelectOption("option3", "Option 3"),
]

months = [
    SelectOption("", "--Select--"),
    SelectOption("1", "January"),
    SelectOption("2", "February"),
    SelectOption("3", "March"),
    SelectOption("6", "June"),
    SelectOption("7", "July"),
]


def test_matches_exact_value():
    assert match_select_option(issue_2043_options, "option3") == 3


def test_matches_exact_label():
    assert match_select_option(issue_2043_options, "Option 3") == 3


def test_matches_label_ignoring_case_and_whitespace():
    assert match_select_option(issue_2043_options, "  option 3 ") == 3


def test_rejects_ambiguous_prefix():
    # "option" prefixes three labels; typeahead would settle on the first
    assert match_select_option(issue_2043_options, "option") is None


def test_matches_unambiguous_prefix():
    assert match_select_option(months, "Jan") == 1
    assert match_select_option(months, "Ju") is None
    assert match_select_option(months, "Jul") == 5


def test_matches_empty_value_of_placeholder_option():
    assert match_select_option(issue_2043_options, "") == 0


def test_prefers_value_over_another_options_label():
    options = [SelectOption("Two", "One"), SelectOption("2", "Two")]
    assert match_select_option(options, "Two") == 0


def test_returns_none_when_nothing_matches():
    assert match_select_option(issue_2043_options, "Option 4") is None
    assert match_select_option([], "anything") is None


def test_describes_options():
    assert describe_select_options(months[1:3]) == (
        '"January" (value: "1"), "February" (value: "2")'
    )
