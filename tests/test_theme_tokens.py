"""Independent WCAG contrast checks for the four complete semantic palettes."""

from pathlib import Path
import re

import pytest

from ilmari_ui.themes import DEFAULT_SKIN, SKINS

STATIC = Path(__file__).parents[1] / "src" / "ilmari_ui" / "static"
TOKENS = frozenset({
    "--il-bg", "--il-surface", "--il-surface-raised", "--il-text",
    "--il-text-muted", "--il-text-subtle", "--il-border", "--il-border-strong",
    "--il-accent", "--il-accent-text", "--il-accent-soft", "--il-secondary",
    "--il-focus", "--il-success", "--il-success-soft", "--il-warning",
    "--il-warning-soft", "--il-danger", "--il-danger-soft", "--il-chart-1",
    "--il-chart-2", "--il-shadow", "--il-overlay", "--il-chart-grid",
})


def palettes():
    contents = (STATIC / "themes.css").read_text()
    return {
        name: dict(re.findall(r"(--il-[\w-]+):\s*([^;]+);", declarations))
        for name, declarations in re.findall(r'\[data-skin="([\w-]+)"\]\s*\{([^}]+)\}', contents)
    }


def luminance(hex_color: str) -> float:
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color)
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722), strict=True))


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def test_contrast_calculation_has_independent_known_truth():
    assert contrast("#000000", "#ffffff") == pytest.approx(21)
    assert contrast("#777777", "#ffffff") < 4.5


def test_every_registered_skin_has_all_semantic_tokens():
    found = palettes()
    assert set(found) == {skin["id"] for skin in SKINS}
    assert DEFAULT_SKIN == "arctic-command"
    for name, palette in found.items():
        assert TOKENS <= palette.keys(), name
        assert all(re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value) for value in palette.values())


TEXT_PAIRS = tuple((foreground, background) for foreground in ("--il-text", "--il-text-muted", "--il-text-subtle") for background in ("--il-bg", "--il-surface", "--il-surface-raised")) + (
    ("--il-accent-text", "--il-accent"),
    ("--il-accent", "--il-surface"),
    ("--il-accent", "--il-accent-soft"),
    ("--il-secondary", "--il-surface"),
    ("--il-success", "--il-success-soft"),
    ("--il-warning", "--il-warning-soft"),
    ("--il-danger", "--il-danger-soft"),
    ("--il-text-muted", "--il-warning-soft"),
    ("--il-text", "--il-warning-soft"),
)


@pytest.mark.parametrize("skin", [skin["id"] for skin in SKINS])
@pytest.mark.parametrize("foreground,background", TEXT_PAIRS)
def test_normal_text_meets_wcag_aa(skin, foreground, background):
    palette = palettes()[skin]
    ratio = contrast(palette[foreground], palette[background])
    assert ratio >= 4.5, f"{skin}: {foreground}/{background} contrast {ratio:.2f}"


@pytest.mark.parametrize("skin", [skin["id"] for skin in SKINS])
@pytest.mark.parametrize("foreground", ("--il-focus", "--il-border-strong", "--il-chart-1", "--il-chart-2"))
@pytest.mark.parametrize("background", ("--il-bg", "--il-surface", "--il-surface-raised"))
def test_focus_boundaries_and_charts_meet_graphic_contrast(skin, foreground, background):
    palette = palettes()[skin]
    assert contrast(palette[foreground], palette[background]) >= 3


def test_components_use_semantic_colours_and_accessibility_defaults():
    css = (STATIC / "app.css").read_text()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css)
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css
    assert "safe-area-inset-bottom" in css
    assert "min-height: 44px" in css
    assert ".code-scroll { overflow-x: auto" in css
    for token in re.findall(r"var\((--il-[\w-]+)\)", css):
        assert token in TOKENS
