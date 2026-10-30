from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")


def test_visualizations_render_before_findings_so_filter_results_are_visible() -> None:
    comparison_chart = APP.index('<FindingVisualizations findings={comparison.findings}')
    comparison_findings = APP.index('{visibleComparisonFindings.length === 0 ?')
    single_chart = APP.index('<FindingVisualizations findings={analysis.findings}')
    single_findings = APP.index('{analysis?.findings.length ? <div className="key-findings-section">')
    assert comparison_chart < comparison_findings
    assert single_chart < single_findings
    assert 'Showing <strong>{filteredFindingCount} of {total}</strong> findings' in APP
    assert 'onClick={() => toggleFilter({ kind: "category", value: item.key })}' in APP
    assert 'onClick={() => toggleFilter({ kind: "status", value: item.key })}' in APP


def test_tavily_is_explicit_opt_in_and_does_not_send_document_text() -> None:
    assert 'Search with Tavily' in APP
    assert 'Uploaded documents are not sent.' in APP
    assert 'searchTavily(normalizedQuery, domains)' in APP
    assert 'research/tavily/search' in API
    assert 'never change finding status automatically' in APP


def test_tavily_is_collapsed_and_after_the_primary_reconciliation_content() -> None:
    assert 'className="external-research-disclosure"' in APP
    assert '<summary><span><strong>Optional external research</strong>' in APP
    comparison_panel = APP.index('<ExternalResearchPanel />', APP.index('comparison-source-evidence-details'))
    comparison_end = APP.index('</div>\n      </section> : null}', comparison_panel)
    assert comparison_panel < comparison_end
    single_panel = APP.index('{analysis ? <ExternalResearchPanel /> : null}', APP.index('analysis?.findings.length ? <details'))
    assert APP.index('{analysis ? <FindingVisualizations') < APP.index('{analysis?.findings.length ? <div className="key-findings-section">') < single_panel
