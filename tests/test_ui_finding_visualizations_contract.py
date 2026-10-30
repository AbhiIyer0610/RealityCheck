from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_TSX = ROOT / "frontend" / "src" / "App.tsx"
STYLES_CSS = ROOT / "frontend" / "src" / "styles.css"


def test_finding_mix_uses_actual_status_labels_and_distinct_colors() -> None:
    source = APP_TSX.read_text(encoding="utf-8")
    assert 'label: "Reality gap"' in source
    assert 'label: "Uncertain"' in source
    assert 'label: "Verified alignment"' in source
    assert 'label: "Inferred"' in source
    assert 'label: "Gap to verify"' not in source


def test_status_and_category_charts_are_interactive_and_filter_findings() -> None:
    source = APP_TSX.read_text(encoding="utf-8")
    assert "function FindingVisualizations" in source
    assert 'aria-label="Finding status distribution"' in source
    assert 'aria-label="Finding categories"' in source
    assert "findingMatchesFilter" in source
    assert "onSelectFilter" in source
    assert "Clear filter" in source
    assert "visibleAnalysisFindings.map" in source
    assert "visibleComparisonFindings.map" in source


def test_historical_chart_only_compares_matching_document_or_document_set() -> None:
    source = APP_TSX.read_text(encoding="utf-8")
    assert 'aria-label="Historical finding trend"' in source
    assert "item.title === currentHistoryTitle" in source
    assert "currentHistoryKind === item.kind" in source
    assert "Different source sets are not combined into one trend." in source


def test_chart_styles_include_responsive_layout_and_click_feedback() -> None:
    styles = STYLES_CSS.read_text(encoding="utf-8")
    assert ".finding-chart-grid" in styles
    assert ".donut-segment:focus" in styles
    assert ".category-bar-row.selected" in styles
    assert "@media(max-width:540px)" in styles


def test_history_refresh_is_disabled_while_comparison_uploads_are_in_progress() -> None:
    source = APP_TSX.read_text(encoding="utf-8")
    assert "disabled={historyLoading || comparisonBusy}" in source
