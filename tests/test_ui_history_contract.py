from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_workspace_disables_upload_and_analysis_controls() -> None:
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "const [isViewingHistory, setIsViewingHistory] = useState(false)" in source
    assert "setIsViewingHistory(true)" in source
    assert "setIsViewingHistory(false)" in source
    assert "disabled={isViewingHistory || !canSubmit}" in source
    assert "disabled={isViewingHistory || comparisonBusy || comparisonFiles.length < 2}" in source
    assert "disabled={isViewingHistory || busy || isProcessing}" in source
    assert "Choose <b>New analysis</b> in the sidebar to start a fresh run" in source


def test_history_supports_multiselect_and_bulk_delete() -> None:
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "const [selectedHistoryIds, setSelectedHistoryIds] = useState<Set<string>>" in source
    assert "function toggleHistorySelection" in source
    assert "function toggleAllVisibleHistory" in source
    assert "async function removeSelectedHistoryItems" in source
    assert "Delete selected" in source
    assert "Delete ${selected.length} selected history" in source
    assert "Deleted ${deletedIds.size} of ${selected.length} items" in source
