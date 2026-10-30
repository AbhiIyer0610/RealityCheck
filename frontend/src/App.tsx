import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { API_BASE_URL, ApiError, createComparison, deleteHistoryItem, getAnalysis, getComparison, getEvidence, getHistory, getJob, searchTavily, uploadArtifact } from "./api";
import type { AnalysisResponse, Claim, ComparisonResponse, EvidenceObject, EvidenceListResponse, Finding, HistoryItem, JobResponse, JobStatus, TavilySearchResult } from "./types";

const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_MB || 50);
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set([".pdf", ".txt"]);
const TERMINAL = new Set<JobStatus>(["succeeded", "partial", "failed"]);
const MAX_COMPARISON_DOCUMENTS = 10;

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function waitForAnalysis(
  jobId: string,
  filename: string,
  onUpdate?: (job: JobResponse) => void,
): Promise<JobResponse> {
  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline) {
    const latest = await getJob(jobId);
    onUpdate?.(latest);
    if (latest.status === "failed") throw new Error(`${filename}: extraction failed. ${latest.error_message || "Review the job diagnostics."}`);
    if (TERMINAL.has(latest.status)) {
      if (latest.analysis_status === "succeeded") return latest;
      if (latest.analysis_status === "failed") throw new Error(`${filename}: claim analysis failed. ${latest.analysis_error_message || "Retry after checking the job."}`);
      if (latest.analysis_status === "not_configured") throw new Error(`${filename}: claim analysis is not configured. Enable offline mode or configure Nebius.`);
    }
    await wait(1200);
  }
  throw new Error(`${filename}: timed out while waiting for extraction and claim analysis.`);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function statusLabel(status: JobStatus): string {
  return ({ pending: "Queued", running: "Processing", succeeded: "Complete", partial: "Partially complete", failed: "Failed" })[status];
}

function locationLabel(item: EvidenceObject): string[] {
  const location = item.provenance.location;
  if (!location) return [];
  const values: string[] = [];
  if (location.page != null) values.push(`Page ${location.page}`);
  if (location.line_start != null) values.push(`Lines ${location.line_start}${location.line_end != null && location.line_end !== location.line_start ? `–${location.line_end}` : ""}`);
  if (location.record_id) values.push(`Record ${location.record_id}`);
  return values;
}

function EvidenceCard({ item, index }: { item: EvidenceObject; index: number }) {
  const sourceLocation = locationLabel(item);
  const body = item.content?.trim();
  return (
    <article className="evidence-card" id={`evidence-${item.evidence_id}`}>
      <div className="evidence-card-top">
        <span className="evidence-index">Evidence {String(index + 1).padStart(2, "0")}</span>
        <span className="type-chip">{item.evidence_type}</span>
      </div>
      {body ? <p className="evidence-content">{body}</p> : null}
      {item.structured_content ? (
        <details className="structured-details">
          <summary>View structured content</summary>
          <pre>{JSON.stringify(item.structured_content, null, 2)}</pre>
        </details>
      ) : null}
      <div className="provenance-row">
        <span><span className="muted-label">Source</span> {item.provenance.source_name}</span>
        <span><span className="muted-label">Method</span> {item.provenance.extraction_method}</span>
        {item.confidence != null ? <span><span className="muted-label">Confidence</span> {Math.round(item.confidence * 100)}%</span> : null}
      </div>
      {sourceLocation.length ? <p className="source-location">{sourceLocation.join(" · ")}</p> : null}
      <details className="metadata-details">
        <summary>Provenance & metadata</summary>
        <pre>{JSON.stringify({ evidence_id: item.evidence_id, provenance: item.provenance, extracted_at: item.extracted_at, metadata: item.metadata }, null, 2)}</pre>
      </details>
    </article>
  );
}

function claimKindLabel(kind: Claim["kind"]): string {
  return kind === "explicit" ? "Explicit in source" : "Inferred by analysis";
}

function categoryLabel(category: string): string {
  return ({ intent: "Intent", requirement: "Requirement", implementation: "Implementation", configuration: "Configuration", observation: "Observation", reference: "Reference", unknown: "Unclassified source statement" } as Record<string, string>)[category] || category.replaceAll("_", " ");
}

function ClaimFindingGuide() {
  return <details className="interpretation-guide"><summary>How to read claims and finding statuses</summary><div className="interpretation-guide-grid">
    <div><strong>Claim kind: Explicit</strong><p>The statement was directly extracted from the source. This does not mean its meaning or truth was independently verified.</p></div>
    <div><strong>Claim category: Unknown</strong><p>The system could not confidently classify the statement as a requirement, implementation detail, configuration, or observation. It is a classification label, not a confidence verdict.</p></div>
    <div><strong>Finding status: Uncertain</strong><p>The proposed issue is not sufficiently established. In offline demo mode, the summary finding is a workflow notice, not a contradiction verdict.</p></div>
    <div><strong>Evidence vs. reality</strong><p>Evidence proves what the supplied file says. It does not automatically prove that the described behavior exists in the running system.</p></div>
  </div></details>;
}

type FindingFilter = { kind: "status" | "category"; value: string } | null;

const FINDING_STATUSES = [
  { key: "reality_gap", label: "Reality gap", color: "#ef6464", description: "Evidence supports a discrepancy." },
  { key: "uncertain", label: "Uncertain", color: "#e7b955", description: "Evidence is insufficient or ambiguous." },
  { key: "verified", label: "Verified alignment", color: "#4cc99a", description: "Supported by available evidence; not automatically runtime-certified." },
  { key: "inferred", label: "Inferred", color: "#79a9f5", description: "Reasoned interpretation; review the evidence chain." },
] as const;

const FINDING_CATEGORIES = [
  { key: "configuration", label: "Configuration & limits", color: "#ef6464" },
  { key: "runtime", label: "Runtime behavior & retries", color: "#e58a4e" },
  { key: "message", label: "User-facing messaging", color: "#b18aee" },
  { key: "verification", label: "Verification & coverage", color: "#e7b955" },
  { key: "other", label: "Other", color: "#79a9f5" },
] as const;

function findingCategory(finding: Finding): typeof FINDING_CATEGORIES[number]["key"] {
  // Prefer the finding title over incidental words in the explanation. For example,
  // a timeout mismatch may mention an acceptance test without being a verification-only issue.
  const title = finding.title.toLowerCase();
  const text = `${finding.title} ${finding.explanation}`.toLowerCase();
  if (/user.?facing|error message|message|readable error|display/.test(title)) return "message";
  if (/acceptance|verification|unverified|test coverage|coverage incomplete/.test(title)) return "verification";
  if (/retry|terminal state|state transition|runtime behavior/.test(title)) return "runtime";
  if (/config|timeout|upload size|limit|misalign/.test(title)) return "configuration";
  if (/user.?facing|error message|message|readable error|display/.test(text)) return "message";
  if (/retry|terminal state|state transition|runtime behavior/.test(text)) return "runtime";
  if (/config|timeout|upload size|limit|misalign/.test(text)) return "configuration";
  if (/acceptance|verification|unverified|test coverage|coverage incomplete/.test(text)) return "verification";
  return "other";
}

function findingMatchesFilter(finding: Finding, filter: FindingFilter): boolean {
  if (!filter) return true;
  return filter.kind === "status"
    ? finding.status === filter.value
    : findingCategory(finding) === filter.value;
}

function ExternalResearchPanel() {
  const [query, setQuery] = useState("");
  const [includeDomains, setIncludeDomains] = useState("");
  const [results, setResults] = useState<TavilySearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 4) {
      setError("Enter a specific public-information query of at least four characters.");
      return;
    }
    const domains = includeDomains.split(",").map((item) => item.trim()).filter(Boolean);
    setLoading(true);
    setError(null);
    try {
      const response = await searchTavily(normalizedQuery, domains);
      setResults(response.results);
      setSearchedQuery(response.query);
    } catch (caught) {
      setResults([]);
      setSearchedQuery("");
      setError(caught instanceof Error ? caught.message : "Tavily search failed.");
    } finally {
      setLoading(false);
    }
  }

  return <details className="external-research-disclosure" aria-label="Optional external research">
    <summary><span><strong>Optional external research</strong><small>Use Tavily to look up public documentation or standards when a finding needs external context.</small></span><span className="external-research-summary-tag">On demand</span></summary>
    <section className="visual-panel external-research-panel">
      <div className="visual-heading"><div><p className="section-kicker">OPTIONAL EXTERNAL CHECK</p><h3>Research public sources with Tavily</h3></div><span>On demand</span></div>
      <p className="visual-intro">Use this only when a finding depends on public documentation, a public standard, or a current external reference. Search results are supplementary evidence—not proof of internal runtime behavior—and never change finding status automatically.</p>
      <form className="tavily-search-form" onSubmit={(event) => void submitSearch(event)}>
      <label htmlFor="tavily-query">Public search query</label>
      <input id="tavily-query" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={500} placeholder="e.g. official documentation for HTTP 413 upload size handling" />
      <label htmlFor="tavily-domains">Restrict to domains (optional, comma-separated)</label>
      <input id="tavily-domains" value={includeDomains} onChange={(event) => setIncludeDomains(event.target.value)} placeholder="e.g. developer.mozilla.org, docs.python.org" />
      <div className="tavily-search-actions"><button className="secondary-button" type="submit" disabled={loading || query.trim().length < 4}>{loading ? "Searching public sources…" : "Search with Tavily"}</button><span>Only the query and optional domains are sent. Uploaded documents are not sent.</span></div>
      </form>
      {error ? <p className="tavily-error" role="alert">{error}</p> : null}
      {searchedQuery ? <div className="tavily-results" aria-live="polite"><h4>Results for “{searchedQuery}”</h4>{results.length ? results.map((item) => <article className="tavily-result" key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><p>{item.content}</p><small>{item.score != null ? `Relevance score ${item.score.toFixed(2)} · ` : ""}{item.url}</small></article>) : <p className="visual-empty">No public results were returned for this query.</p>}</div> : null}
    </section>
  </details>;
}

function FindingVisualizations({
  findings,
  selectedFilter,
  onSelectFilter,
  historyItems,
  currentHistoryTitle,
  currentHistoryKind,
  onOpenHistory,
}: {
  findings: Finding[];
  selectedFilter: FindingFilter;
  onSelectFilter: (filter: FindingFilter) => void;
  historyItems: HistoryItem[];
  currentHistoryTitle: string | null;
  currentHistoryKind: HistoryItem["kind"] | null;
  onOpenHistory: (item: HistoryItem) => void;
}) {
  const total = findings.length;
  const statusCounts = FINDING_STATUSES.map((status) => ({
    ...status,
    count: findings.filter((finding) => finding.status === status.key).length,
  }));
  const categoryCounts = FINDING_CATEGORIES.map((category) => ({
    ...category,
    count: findings.filter((finding) => findingCategory(finding) === category.key).length,
  }));
  const circumference = 2 * Math.PI * 34;
  let offset = 0;
  const donutSegments = statusCounts.map((item) => {
    const length = total ? item.count / total * circumference : 0;
    const segment = { ...item, length, offset };
    offset += length;
    return segment;
  });
  const maxCategoryCount = Math.max(1, ...categoryCounts.map((item) => item.count));
  const matchingHistory = historyItems
    .filter((item) => currentHistoryKind === item.kind && currentHistoryTitle && item.title === currentHistoryTitle)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .slice(-8);
  const maxHistoryFindings = Math.max(1, ...matchingHistory.map((item) => item.finding_count));
  const filteredFindingCount = findings.filter((finding) => findingMatchesFilter(finding, selectedFilter)).length;
  const activeFilterLabel = selectedFilter
    ? selectedFilter.kind === "status"
      ? FINDING_STATUSES.find((item) => item.key === selectedFilter.value)?.label
      : FINDING_CATEGORIES.find((item) => item.key === selectedFilter.value)?.label
    : null;
  const toggleFilter = (next: FindingFilter) => {
    onSelectFilter(selectedFilter?.kind === next?.kind && selectedFilter?.value === next?.value ? null : next);
  };

  return <section className="visual-panel finding-visualizations" aria-label="Finding visualizations">
    <div className="visual-heading"><div><p className="section-kicker">FINDING MIX</p><h3>What needs attention?</h3></div><span>{total} {total === 1 ? "finding" : "findings"}</span></div>
    <div className="finding-chart-grid">
      <section className="finding-chart-card" aria-label="Finding status distribution">
        <h4>Status distribution</h4>
        {total ? <div className="donut-layout">
          <svg className="finding-donut" viewBox="0 0 100 100" role="img" aria-label={statusCounts.map((item) => `${item.label}: ${item.count}`).join(", ")}>
            <circle cx="50" cy="50" r="34" fill="none" stroke="var(--chart-track, #253449)" strokeWidth="13" />
            {donutSegments.filter((item) => item.count > 0).map((item) => <circle
              key={item.key}
              cx="50" cy="50" r="34" fill="none" stroke={item.color} strokeWidth="13"
              strokeDasharray={`${item.length} ${circumference - item.length}`}
              strokeDashoffset={-item.offset}
              transform="rotate(-90 50 50)"
              className={`donut-segment ${selectedFilter?.kind === "status" && selectedFilter.value === item.key ? "selected" : ""}`}
              style={{ pointerEvents: "stroke" }}
              role="button" tabIndex={0} aria-label={`Filter findings: ${item.label}, ${item.count}`}
              onClick={() => toggleFilter({ kind: "status", value: item.key })}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggleFilter({ kind: "status", value: item.key }); } }}
            />)}
            <text x="50" y="48" textAnchor="middle" className="donut-total">{total}</text>
            <text x="50" y="59" textAnchor="middle" className="donut-caption">findings</text>
          </svg>
          <div className="chart-legend">{statusCounts.map((item) => <button type="button" className={`chart-legend-row ${selectedFilter?.kind === "status" && selectedFilter.value === item.key ? "selected" : ""}`} key={item.key} onClick={() => toggleFilter({ kind: "status", value: item.key })} title={`Filter by ${item.label}`}>
            <span className="chart-legend-dot" style={{ background: item.color }} /><span className="chart-legend-copy"><strong>{item.label}</strong><small>{item.description}</small></span><b>{item.count}</b>
          </button>)}</div>
        </div> : <p className="visual-empty">No findings to chart. This does not mean the sources agree.</p>}
      </section>
      <section className="finding-chart-card" aria-label="Finding categories">
        <h4>Issue categories</h4>
        <p className="chart-help">Select a bar to highlight findings in that category.</p>
        <div className="category-bars">{categoryCounts.map((item) => <button type="button" key={item.key} className={`category-bar-row ${selectedFilter?.kind === "category" && selectedFilter.value === item.key ? "selected" : ""}`} onClick={() => toggleFilter({ kind: "category", value: item.key })} aria-label={`Filter findings by ${item.label}: ${item.count}`}>
          <span className="category-bar-label">{item.label}</span><span className="category-bar-track"><span style={{ width: `${item.count / maxCategoryCount * 100}%`, background: item.color }} /></span><b>{item.count}</b>
        </button>)}</div>
      </section>
    </div>
    {selectedFilter ? <div className="active-finding-filter" role="status"><span>Showing <strong>{filteredFindingCount} of {total}</strong> findings · Filter: <strong>{activeFilterLabel}</strong></span><button type="button" onClick={() => onSelectFilter(null)}>Clear filter</button></div> : <p className="visual-intro chart-caveat">Status describes the analysis conclusion, not whether a claim was explicit. Green alignment does not automatically mean runtime behavior was tested.</p>}
    <section className="finding-chart-card history-trend-card" aria-label="Historical finding trend">
      <div className="visual-heading"><div><h4>Historical trend</h4><p className="chart-help">Finding counts across saved runs of this same document or document set.</p></div><span>{matchingHistory.length} runs</span></div>
      {matchingHistory.length >= 2 ? <div className="history-trend-chart">{matchingHistory.map((item) => <button type="button" key={`${item.kind}-${item.id}`} className="history-trend-bar-item" onClick={() => onOpenHistory(item)} title={`Open ${item.title} — ${item.finding_count} findings`}>
        <span className="history-trend-count">{item.finding_count}</span><span className="history-trend-track"><span style={{ height: `${Math.max(5, item.finding_count / maxHistoryFindings * 100)}%` }} /></span><span className="history-trend-date">{new Date(item.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
      </button>)}</div> : <p className="visual-empty">Run this same document or document set again to compare finding counts over time. Different source sets are not combined into one trend.</p>}
    </section>
  </section>;
}

function CoverageMap({ claims, findings, sourceNames }: { claims: Claim[]; findings: Finding[]; sourceNames: Map<string, string> }) {
  const requirements = claims.filter((claim) => claim.category === "requirement" || /^(?:R|REQ)[-_ ]?\d+\s*:/i.test(claim.text));
  const implementation = claims.filter((claim) => claim.category === "implementation" || claim.category === "configuration");
  const observations = claims.filter((claim) => claim.category === "observation");
  const targetClaims = requirements.length ? requirements : claims.filter((claim) => claim.category !== "reference" && claim.category !== "intent");
  if (!claims.length) return <div className="visual-panel"><h3>Requirement-to-reality coverage</h3><p>No claims are available yet. Coverage cannot be assessed.</p></div>;
  return <section className="visual-panel coverage-panel"><div className="visual-heading"><div><p className="section-kicker">COVERAGE MAP</p><h3>What has evidence—and what still needs proof?</h3></div><span>{targetClaims.length} items</span></div>
    <p className="visual-intro">This is a traceability view, not a pass/fail certification. A missing link means evidence was not connected in this analysis; it does not prove the feature is absent.</p>
    <div className="coverage-table-wrap"><table className="coverage-table"><thead><tr><th>Requirement / claim</th><th>Implementation evidence</th><th>Observed behavior</th><th>Finding / next action</th></tr></thead><tbody>{targetClaims.map((claim) => {
      const related = findings.filter((finding) => finding.claim_ids.includes(claim.claim_id));
      const linkedImpl = implementation.filter((item) => item.evidence_ids.some((id) => claim.evidence_ids.includes(id)) || /upload|job|evidence|status|retention|file|pdf|text/i.test(item.text) && /upload|job|evidence|status|retention|file|pdf|text/i.test(claim.text));
      const linkedObs = observations.filter((item) => /upload|job|evidence|status|retention|file|pdf|text/i.test(item.text) && /upload|job|evidence|status|retention|file|pdf|text/i.test(claim.text));
      return <tr key={claim.claim_id}><td><span className="coverage-state">{categoryLabel(claim.category)}</span><p>{claim.text}</p><small>{claim.evidence_ids.map((id) => sourceNames.get(id)).filter(Boolean).join(", ") || "Source reference unavailable"}</small></td><td>{linkedImpl.length ? <><span className="coverage-state present">Linked claim</span><p>{linkedImpl.map((item) => item.text).join(" · ")}</p></> : <span className="coverage-state missing">No linked implementation claim</span>}</td><td>{linkedObs.length ? <><span className="coverage-state present">Observation supplied</span><p>{linkedObs.map((item) => item.text).join(" · ")}</p></> : <span className="coverage-state missing">No linked observation claim</span>}</td><td>{related.length ? related.map((finding) => <div className="coverage-action" key={finding.finding_id}><span className={`finding-status ${finding.status}`}>{finding.status.replaceAll("_", " ")}</span><p>{finding.title}</p><small>{finding.recommendation || "Review the supporting evidence."}</small></div>) : <span className="coverage-state neutral">No finding linked to this claim</span>}</td></tr>;
    })}</tbody></table></div>
    <div className="coverage-legend"><span className="coverage-state present">Linked / supplied</span><span className="coverage-state missing">No linked evidence</span><span className="coverage-state neutral">Not assessed</span></div>
  </section>;
}

function RelationshipMap({ claims, findings, sourceNames }: { claims: Claim[]; findings: Finding[]; sourceNames: Map<string, string> }) {
  const linked = findings.filter((finding) => finding.claim_ids.length > 0 || finding.evidence_ids.length > 0);
  return <section className="visual-panel"><div className="visual-heading"><div><p className="section-kicker">EVIDENCE RELATIONSHIPS</p><h3>Follow the reasoning chain</h3></div><span>{linked.length} findings linked</span></div><p className="visual-intro">Each path shows which claims and source files a candidate finding relies on. Lines are represented as explicit links so the view remains readable on narrow screens.</p>
    {linked.length ? <div className="relationship-list">{linked.map((finding) => <article className="relationship-row" key={finding.finding_id}><div className="relationship-node issue-node"><strong>{finding.title}</strong><span className={`finding-status ${finding.status}`}>{finding.status.replaceAll("_", " ")}</span></div><div className="relationship-connector">← supported by</div><div className="relationship-sources">{finding.claim_ids.map((id) => { const claim = claims.find((item) => item.claim_id === id); return <div className="relationship-node claim-node" key={id}><strong>{claim ? claim.text : `Claim ${id.slice(0, 8)}`}</strong><small>{claim ? `${categoryLabel(claim.category)} · ${claimKindLabel(claim.kind)}` : "Claim text unavailable"}</small></div>; })}{Array.from(new Set(finding.evidence_ids.map((id) => sourceNames.get(id)).filter((name): name is string => Boolean(name)))).map((name) => <span className="comparison-source-chip" key={name}>Source: {name}</span>)}</div></article>)}</div> : <p className="visual-empty">No finding relationships are available yet. This is not proof that the sources agree.</p>}
  </section>;
}

function ActionBoard({ findings }: { findings: Finding[] }) {
  const groups = [
    { title: "Verify against runtime", items: [] as Finding[] },
    { title: "Run a focused test", items: [] as Finding[] },
    { title: "Resolve evidence gaps", items: [] as Finding[] },
  ];
  for (const finding of findings) {
    const text = `${finding.title} ${finding.explanation} ${finding.recommendation || ""}`;
    if (/config|runtime|environment|version|limit|timeout/i.test(text)) groups[0].items.push(finding);
    else if (/test|observ|behavior|upload|response|reproduc/i.test(text)) groups[1].items.push(finding);
    else groups[2].items.push(finding);
  }
  return <section className="visual-panel"><div className="visual-heading"><div><p className="section-kicker">NEXT ACTIONS</p><h3>Turn findings into verification work</h3></div><span>{findings.length} items</span></div><p className="visual-intro">Suggested triage buckets are based on finding text, not calibrated risk scores. Each finding appears in one bucket; confirm every action against the cited passages.</p>
    <div className="action-board">{groups.map((group) => <div className="action-column" key={group.title}><h4>{group.title}<span>{group.items.length}</span></h4>{group.items.length ? group.items.map((finding) => <article className="action-card" key={finding.finding_id}><strong>{finding.title}</strong><span className={`finding-status ${finding.status}`}>{finding.status.replaceAll("_", " ")}</span><p>{finding.recommendation || "Inspect the supporting evidence and define the smallest confirming test."}</p></article>) : <p className="visual-empty">No findings assigned.</p>}</div>)}</div>
  </section>;
}

export default function App() {
  const [uploadMode, setUploadMode] = useState<"single" | "compare">("single");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidenceListResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastPolledAt, setLastPolledAt] = useState<string | null>(null);
  const [comparisonFiles, setComparisonFiles] = useState<File[]>([]);
  const [comparisonJobs, setComparisonJobs] = useState<JobResponse[]>([]);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [comparisonEvidence, setComparisonEvidence] = useState<EvidenceObject[]>([]);
  const [comparisonBusy, setComparisonBusy] = useState(false);
  const [comparisonProgress, setComparisonProgress] = useState("");
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [openingHistoryId, setOpeningHistoryId] = useState<string | null>(null);
  const [historyQuery, setHistoryQuery] = useState("");
  const [openHistoryMenuId, setOpenHistoryMenuId] = useState<string | null>(null);
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<Set<string>>(() => new Set());
  const [bulkDeletingHistory, setBulkDeletingHistory] = useState(false);
  const [isViewingHistory, setIsViewingHistory] = useState(false);
  const [selectedFindingFilter, setSelectedFindingFilter] = useState<FindingFilter>(null);
  const comparisonInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadPanelRef = useRef<HTMLElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);

  const isProcessing = Boolean(job && !TERMINAL.has(job.status));
  const isOfflineDemo = job?.analysis_provider === "offline_demo" || analysis?.analysis_provider === "offline_demo";
  const canSubmit = Boolean(selectedFile && !isViewingHistory && !busy && !isProcessing);
  const comparisonDisplayDocuments = comparisonFiles.length > 0
    ? comparisonFiles.map((file, index) => ({
        key: `${file.name}-${file.size}-${file.lastModified}`,
        filename: file.name,
        size_bytes: file.size,
        job: comparisonJobs[index] || null,
      }))
    : comparison
      ? comparison.documents.map((document) => {
          const sourceJob = comparisonJobs.find((item) => item.job_id === document.job_id) || null;
          return {
            key: document.job_id,
            filename: document.filename,
            size_bytes: sourceJob?.size_bytes || 0,
            job: sourceJob,
          };
        })
      : [];
  const comparisonCompletedCount = comparisonDisplayDocuments.filter(
    ({ job: item }) => item && TERMINAL.has(item.status) && item.analysis_status === "succeeded",
  ).length;
  const comparisonElementCount = comparisonJobs.reduce((total, item) => total + item.element_count, 0);
  const comparisonEvidenceCount = comparisonJobs.reduce((total, item) => total + item.evidence_count, 0);
  const comparisonTotalBytes = comparisonDisplayDocuments.reduce((total, document) => total + document.size_bytes, 0);
  const filteredHistoryItems = historyItems.filter((item) => {
    const query = historyQuery.trim().toLowerCase();
    if (!query) return true;
    return [item.title, ...item.document_names, item.kind, item.status].some((value) => value.toLowerCase().includes(query));
  });
  const activeHistoryId = comparison?.comparison_id || job?.job_id || null;
  const selectedVisibleHistoryCount = filteredHistoryItems.filter((item) => selectedHistoryIds.has(item.id)).length;
  const currentHistoryTitle = comparison
    ? comparison.documents.map((document) => document.filename).join(" vs ")
    : job?.filename || null;
  const currentHistoryKind: HistoryItem["kind"] | null = comparison ? "comparison" : job ? "document" : null;
  const visibleAnalysisFindings = (analysis?.findings || []).filter((finding) => findingMatchesFilter(finding, selectedFindingFilter));
  const visibleComparisonFindings = (comparison?.findings || []).filter((finding) => findingMatchesFilter(finding, selectedFindingFilter));

  function upsertComparisonJob(updated: JobResponse) {
    setComparisonJobs((current) => {
      const existingIndex = current.findIndex((item) => item.job_id === updated.job_id);
      if (existingIndex < 0) return [...current, updated];
      const next = current.slice();
      next[existingIndex] = updated;
      return next;
    });
  }

  async function loadComparisonEvidence(jobIds: string[]): Promise<EvidenceObject[]> {
    const responses = await Promise.all(jobIds.map((jobId) => getEvidence(jobId).catch(() => null)));
    const seen = new Set<string>();
    const combined: EvidenceObject[] = [];
    for (const response of responses) {
      for (const item of response?.items ?? []) {
        if (seen.has(item.evidence_id)) continue;
        seen.add(item.evidence_id);
        combined.push(item);
      }
    }
    return combined;
  }

  const progressText = useMemo(() => {
    if (!job) return "Upload a source document to begin.";
    if (job.status === "failed") return job.error_message || "Processing failed. Review the diagnostics below.";
    if (job.analysis_status === "failed" && job.status !== "running") {
      return job.analysis_error_message || "Evidence extraction completed, but AI analysis could not finish.";
    }
    return job.progress_message || (job.status === "pending" ? "Waiting for a worker." : "Processing your evidence.");
  }, [job]);

  useEffect(() => {
    if (!job) return;
    const controller = new AbortController();
    let timer: number | undefined;
    let disposed = false;
    const poll = async () => {
      try {
        const latest = await getJob(job.job_id, controller.signal);
        if (disposed) return;
        setJob(latest);
        setLastPolledAt(new Date().toISOString());
        try {
          const result = await getAnalysis(job.job_id, controller.signal);
          if (!disposed) setAnalysis(result);
        } catch (cause) {
          if (!disposed && !(cause instanceof ApiError && cause.status === 409)) {
            setError(cause instanceof Error ? cause.message : "Could not load analysis results.");
          }
        }
        if (latest.evidence_count > 0 || TERMINAL.has(latest.status)) {
          try {
            const result = await getEvidence(job.job_id, controller.signal);
            if (!disposed) setEvidence(result);
          } catch (cause) {
            if (!disposed && !(cause instanceof ApiError && cause.status === 409)) {
              setError(cause instanceof Error ? cause.message : "Could not load evidence.");
            }
          }
        }
        if (TERMINAL.has(latest.status)) {
          void refreshHistory();
          return;
        }
      } catch (cause) {
        if (disposed || (cause instanceof DOMException && cause.name === "AbortError")) return;
        setError(cause instanceof Error ? cause.message : "Could not refresh job status.");
      }
      if (!disposed) timer = window.setTimeout(poll, 1500);
    };
    timer = window.setTimeout(poll, 700);
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [job?.job_id]);

  async function refreshHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const result = await getHistory();
      setHistoryItems(result.items);
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "Could not load analysis history.");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => { void refreshHistory(); }, []);

  async function openHistoryItem(item: HistoryItem) {
    setOpeningHistoryId(item.id);
    setOpenHistoryMenuId(null);
    setError(null); setNotice(null);
    try {
      if (item.kind === "comparison") {
        const result = await getComparison(item.comparison_id || item.id);
        const [sourceJobs, sourceEvidence] = await Promise.all([
          Promise.all(result.documents.map((document) => getJob(document.job_id).catch(() => null))),
          loadComparisonEvidence(result.documents.map((document) => document.job_id)),
        ]);
        setUploadMode("compare");
        setComparison(result);
        setComparisonJobs(sourceJobs.filter((value): value is JobResponse => value !== null));
        setComparisonEvidence(sourceEvidence);
        setComparisonFiles([]);
        setSelectedFile(null); setJob(null); setAnalysis(null); setEvidence(null);
        setComparisonProgress("");
      } else {
        const jobId = item.job_id || item.id;
        const [loadedJob, loadedAnalysis, loadedEvidence] = await Promise.all([
          getJob(jobId), getAnalysis(jobId), getEvidence(jobId).catch(() => null),
        ]);
        setUploadMode("single"); setSelectedFile(null);
        setComparisonFiles([]); setComparisonJobs([]); setComparison(null); setComparisonEvidence([]); setComparisonProgress("");
        setJob(loadedJob); setAnalysis(loadedAnalysis); setEvidence(loadedEvidence); setLastPolledAt(new Date().toISOString());
      }
      setIsViewingHistory(true);
      setNotice(`Opened saved ${item.kind === "comparison" ? "comparison" : "document analysis"}. Uploading is disabled while viewing saved results; choose New analysis to start another run.`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not reopen this history item.");
    } finally {
      setOpeningHistoryId(null);
    }
  }

  async function removeHistoryItem(item: HistoryItem) {
    const description = item.kind === "comparison" ? "this saved comparison" : `the analysis for ${item.title}`;
    setOpenHistoryMenuId(null);
    if (!window.confirm(`Delete ${description}? This cannot be undone.`)) return;
    try {
      await deleteHistoryItem(item);
      setHistoryItems((items) => items.filter((current) => current.id !== item.id));
      if (item.kind === "comparison" && comparison?.comparison_id === item.id) {
        setIsViewingHistory(false);
        setComparison(null);
        setComparisonJobs([]);
        setComparisonFiles([]);
        setComparisonEvidence([]);
      }
      if (item.kind === "document" && job?.job_id === (item.job_id || item.id)) {
        setIsViewingHistory(false);
        setJob(null); setAnalysis(null); setEvidence(null); setLastPolledAt(null);
      }
      setSelectedHistoryIds((current) => { const next = new Set(current); next.delete(item.id); return next; });
      setNotice("History item deleted.");
    } catch (cause) {
      setHistoryError(cause instanceof Error ? cause.message : "Could not delete this history item.");
    }
  }

  async function removeSelectedHistoryItems() {
    const selected = filteredHistoryItems.filter((item) => selectedHistoryIds.has(item.id));
    if (!selected.length || bulkDeletingHistory) return;
    if (!window.confirm(`Delete ${selected.length} selected history ${selected.length === 1 ? "item" : "items"}? This cannot be undone.`)) return;
    setBulkDeletingHistory(true);
    setHistoryError(null);
    const deletedIds = new Set<string>();
    const failures: string[] = [];
    try {
      for (const item of selected) {
        try {
          await deleteHistoryItem(item);
          deletedIds.add(item.id);
        } catch (cause) {
          failures.push(`${item.title}: ${cause instanceof Error ? cause.message : "delete failed"}`);
        }
      }
      if (deletedIds.size) {
        setHistoryItems((items) => items.filter((item) => !deletedIds.has(item.id)));
        setSelectedHistoryIds((current) => { const next = new Set(current); deletedIds.forEach((id) => next.delete(id)); return next; });
        const activeDocumentDeleted = Boolean(job && deletedIds.has(job.job_id));
        const activeComparisonDeleted = Boolean(comparison && deletedIds.has(comparison.comparison_id));
        if (activeDocumentDeleted || activeComparisonDeleted) {
          setIsViewingHistory(false);
          setJob(null); setAnalysis(null); setEvidence(null); setLastPolledAt(null);
          setComparison(null); setComparisonJobs([]); setComparisonFiles([]); setComparisonEvidence([]); setComparisonProgress("");
        }
      }
      if (failures.length) {
        setHistoryError(`Deleted ${deletedIds.size} of ${selected.length} items. ${failures.join(" | ")}`);
      } else {
        setNotice(`Deleted ${deletedIds.size} history ${deletedIds.size === 1 ? "item" : "items"}.`);
      }
    } finally {
      setBulkDeletingHistory(false);
    }
  }

  function toggleHistorySelection(itemId: string) {
    setSelectedHistoryIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId); else next.add(itemId);
      return next;
    });
  }

  function toggleAllVisibleHistory() {
    setSelectedHistoryIds((current) => {
      const next = new Set(current);
      const allSelected = filteredHistoryItems.length > 0 && filteredHistoryItems.every((item) => next.has(item.id));
      filteredHistoryItems.forEach((item) => { if (allSelected) next.delete(item.id); else next.add(item.id); });
      return next;
    });
  }

  function startNewAnalysis() {
    resetWorkspace();
    setIsViewingHistory(false);
    setSelectedFindingFilter(null);
    setSelectedHistoryIds(new Set());
    setUploadMode("single");
    setHistoryQuery("");
    setOpenHistoryMenuId(null);
    window.setTimeout(() => uploadPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  function validateFile(file: File): string | null {
    const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
    if (!ACCEPTED_EXTENSIONS.has(extension)) return "Choose a PDF (.pdf) or UTF-8 text file (.txt).";
    if (file.size === 0) return "The selected file is empty.";
    if (file.size > MAX_UPLOAD_BYTES) return `The file exceeds the ${MAX_UPLOAD_MB} MB upload limit.`;
    return null;
  }

  function onFileChange(file?: File) {
    if (isViewingHistory) return;
    setError(null); setNotice(null); setEvidence(null); setAnalysis(null); setJob(null); setLastPolledAt(null); setSelectedFindingFilter(null);
    if (!file) { setSelectedFile(null); return; }
    const problem = validateFile(file);
    if (problem) { setSelectedFile(null); setError(problem); if (fileInputRef.current) fileInputRef.current.value = ""; return; }
    setSelectedFile(file);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isViewingHistory || !selectedFile || !canSubmit) return;
    setBusy(true); setError(null); setNotice(null); setEvidence(null); setAnalysis(null); setJob(null); setSelectedFindingFilter(null);
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    try {
      const created = await uploadArtifact(selectedFile, controller.signal);
      setJob(created);
      setNotice("Upload accepted. You can leave this tab open while RealityCheck processes it.");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      const message = cause instanceof Error ? cause.message : "Upload failed. Please retry.";
      const status = cause instanceof ApiError ? cause.status : undefined;
      setError(status === 503 ? `${message} The server asked the client to retry shortly.` : message);
    } finally {
      setBusy(false); uploadAbortRef.current = null;
    }
  }

  function onComparisonFilesChange(files: FileList | null) {
    if (isViewingHistory) return;
    setError(null);
    setComparison(null);
    setComparisonJobs([]);
    setComparisonEvidence([]);
    setComparisonProgress("");
    setSelectedFindingFilter(null);
    const selected = Array.from(files || []);
    if (selected.length < 2) {
      setComparisonFiles([]);
      if (selected.length === 1) setError("Choose at least two documents for a cross-document comparison.");
      return;
    }
    if (selected.length > MAX_COMPARISON_DOCUMENTS) {
      setComparisonFiles([]);
      setError(`Choose no more than ${MAX_COMPARISON_DOCUMENTS} documents per comparison.`);
      if (comparisonInputRef.current) comparisonInputRef.current.value = "";
      return;
    }
    for (const file of selected) {
      const problem = validateFile(file);
      if (problem) {
        setComparisonFiles([]);
        setError(`${file.name}: ${problem}`);
        if (comparisonInputRef.current) comparisonInputRef.current.value = "";
        return;
      }
    }
    setComparisonFiles(selected);
  }

  async function onCompareDocuments(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isViewingHistory || comparisonFiles.length < 2 || comparisonBusy) return;
    setComparisonBusy(true);
    setSelectedFindingFilter(null);
    setError(null);
    setNotice(null);
    setComparison(null);
    setComparisonJobs([]);
    setComparisonEvidence([]);
    setJob(null);
    setEvidence(null);
    setAnalysis(null);
    setLastPolledAt(null);
    const jobIds: string[] = [];
    try {
      for (let index = 0; index < comparisonFiles.length; index += 1) {
        const file = comparisonFiles[index];
        setComparisonProgress(`Uploading ${index + 1} of ${comparisonFiles.length}: ${file.name}`);
        const submitted = await uploadArtifact(file);
        jobIds.push(submitted.job_id);
        upsertComparisonJob(submitted);
        setComparisonProgress(`Extracting and analyzing ${index + 1} of ${comparisonFiles.length}: ${file.name}`);
        await waitForAnalysis(submitted.job_id, file.name, upsertComparisonJob);
      }
      setComparisonProgress("Reconciling claims across all selected documents…");
      const result = await createComparison(jobIds);
      setComparison(result);
      const sourceEvidence = await loadComparisonEvidence(jobIds);
      setComparisonEvidence(sourceEvidence);
      void refreshHistory();
      setNotice(`Comparison complete across ${result.documents.length} documents.`);
      setComparisonProgress("");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Cross-document comparison failed.";
      setError(message);
      setComparisonProgress("");
    } finally {
      setComparisonBusy(false);
    }
  }

  function resetWorkspace() {
    uploadAbortRef.current?.abort();
    setSelectedFile(null); setJob(null); setEvidence(null); setAnalysis(null); setBusy(false); setError(null); setNotice(null); setLastPolledAt(null);
    setComparisonFiles([]); setComparisonJobs([]); setComparison(null); setComparisonEvidence([]); setComparisonBusy(false); setComparisonProgress("");
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (comparisonInputRef.current) comparisonInputRef.current.value = "";
  }

  return (
    <main className="app-shell app-shell-layout">
      <aside className="history-sidebar" aria-label="Analysis history">
        <div className="sidebar-brand-row">
          <a className="brand" href="#top" aria-label="RealityCheck home"><span className="brand-mark">R</span><span>Reality<span className="brand-light">Check</span></span></a>
          <span className="sidebar-version">MVP</span>
        </div>
        <button className="new-analysis-button" type="button" onClick={startNewAnalysis} disabled={busy || comparisonBusy}>
          <span aria-hidden="true">＋</span> New analysis
        </button>
        <div className="history-sidebar-heading">
          <span>RECENT ANALYSES</span>
          <button type="button" className="icon-button history-refresh-icon" onClick={() => void refreshHistory()} disabled={historyLoading || comparisonBusy} aria-label="Refresh history" title="Refresh history">↻</button>
        </div>
        <label className="history-search">
          <span aria-hidden="true">⌕</span>
          <input type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Search history" aria-label="Search analysis history" />
          {historyQuery ? <button type="button" onClick={() => setHistoryQuery("")} aria-label="Clear history search">×</button> : null}
        </label>
        {historyError ? <p className="history-error" role="alert">{historyError}</p> : null}
        {filteredHistoryItems.length > 0 ? <div className="history-selection-toolbar">
          <label className="history-select-all"><input type="checkbox" checked={filteredHistoryItems.every((item) => selectedHistoryIds.has(item.id))} onChange={toggleAllVisibleHistory} aria-label="Select all visible history entries" /> Select visible</label>
          <button type="button" className="history-bulk-delete" onClick={() => void removeSelectedHistoryItems()} disabled={selectedVisibleHistoryCount === 0 || bulkDeletingHistory}>
            {bulkDeletingHistory ? "Deleting…" : `Delete selected${selectedVisibleHistoryCount ? ` (${selectedVisibleHistoryCount})` : ""}`}
          </button>
        </div> : null}
        <div className="history-sidebar-list">
          {historyLoading && historyItems.length === 0 ? <p className="history-sidebar-empty">Loading saved analyses…</p> : null}
          {!historyLoading && historyItems.length === 0 ? <p className="history-sidebar-empty">Your saved analyses will appear here.</p> : null}
          {historyItems.length > 0 && filteredHistoryItems.length === 0 ? <p className="history-sidebar-empty">No analyses match “{historyQuery}”.</p> : null}
          {filteredHistoryItems.map((item) => (
            <article className={`history-sidebar-item ${activeHistoryId === item.id ? "active" : ""} ${selectedHistoryIds.has(item.id) ? "selected" : ""}`} key={`${item.kind}-${item.id}`}>
              <label className="history-entry-select" title={`Select ${item.title}`}><input type="checkbox" checked={selectedHistoryIds.has(item.id)} onChange={() => toggleHistorySelection(item.id)} aria-label={`Select history entry ${item.title}`} /></label>
              <button className="history-entry-button" type="button" onClick={() => void openHistoryItem(item)} disabled={openingHistoryId !== null} title={item.title}>
                <span className="history-entry-title">{item.title}</span>
                <span className="history-entry-meta">{item.document_count} {item.document_count === 1 ? "document" : "documents"} · {item.finding_count} {item.finding_count === 1 ? "finding" : "findings"}</span>
                <span className="history-entry-date">{formatDate(item.created_at)}</span>
              </button>
              <button className="history-menu-trigger" type="button" aria-label={`More actions for ${item.title}`} aria-haspopup="menu" aria-expanded={openHistoryMenuId === item.id} onClick={() => setOpenHistoryMenuId((current) => current === item.id ? null : item.id)} disabled={openingHistoryId !== null}>···</button>
              {openHistoryMenuId === item.id ? (
                <div className="history-context-menu" role="menu">
                  <button type="button" role="menuitem" className="history-menu-delete" onClick={() => void removeHistoryItem(item)}>
                    <span aria-hidden="true">⌫</span> Delete analysis
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
        <div className="sidebar-footer"><span className="environment-dot" /> Local workspace <span className="version-pill">MVP</span></div>
      </aside>
      <div className="app-main">
      <header className="topbar">
        <div className="workspace-topbar-title"><span className="workspace-title-mark">R</span><span>Evidence workspace</span></div>
        <div className="topbar-right"><span className="environment-dot" /> Local analysis <span className="version-pill">MVP</span></div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow"><span className="eyebrow-line" /> EVIDENCE, NOT ASSUMPTIONS</div>
        <h1>Find where reality<br /><span>doesn’t match the story.</span></h1>
        <p className="hero-copy">Upload one document or compare related sources. RealityCheck extracts traceable evidence so you can inspect what each source says — and where it came from.</p>
      </section>

      {isViewingHistory ? <div className="historical-view-banner" role="status"><strong>Viewing saved analysis</strong><span>Uploads and analysis runs are disabled for historical results. Choose <b>New analysis</b> in the sidebar to start a fresh run.</span></div> : null}
      <section className={`workspace-grid ${isViewingHistory ? "historical-workspace" : ""}`} aria-label="Artifact processing workspace">
        <section ref={uploadPanelRef} className="panel upload-panel">
          <div className="panel-heading"><div><p className="section-kicker">01 / SOURCE</p><h2>Bring your evidence</h2></div><span className="step-number">01</span></div>
          <div className="upload-mode-tabs" role="group" aria-label="Choose upload workflow">
            <button
              className={`upload-mode-tab ${uploadMode === "single" ? "active" : ""}`}
              type="button"
              aria-pressed={uploadMode === "single"}
              disabled={isViewingHistory || busy || isProcessing || comparisonBusy}
              onClick={() => {
                setUploadMode("single");
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
                setComparisonFiles([]);
                setComparisonJobs([]);
                setComparison(null);
                setComparisonEvidence([]);
                setComparisonProgress("");
                if (comparisonInputRef.current) comparisonInputRef.current.value = "";
                setError(null);
                setNotice(null);
              }}
            >Single document</button>
            <button
              className={`upload-mode-tab ${uploadMode === "compare" ? "active" : ""}`}
              type="button"
              aria-pressed={uploadMode === "compare"}
              disabled={isViewingHistory || busy || isProcessing || comparisonBusy}
              onClick={() => {
                setUploadMode("compare");
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
                setComparisonFiles([]);
                setComparisonJobs([]);
                setComparison(null);
                setComparisonEvidence([]);
                setComparisonProgress("");
                if (comparisonInputRef.current) comparisonInputRef.current.value = "";
                setError(null);
                setNotice(null);
              }}
            >Compare documents <span>2–10</span></button>
          </div>
          {uploadMode === "single" ? (
            <form onSubmit={onSubmit}>
              <label className={`dropzone ${selectedFile ? "has-file" : ""}`} htmlFor="artifact-file" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!isViewingHistory) onFileChange(event.dataTransfer.files?.[0]); }}>
                <input ref={fileInputRef} id="artifact-file" type="file" accept=".pdf,.txt,application/pdf,text/plain" disabled={isViewingHistory || busy || isProcessing} onChange={(e) => onFileChange(e.target.files?.[0])} />
                <span className="upload-icon" aria-hidden="true">↑</span>
                {selectedFile ? <><strong>{selectedFile.name}</strong><span>{formatBytes(selectedFile.size)} · Ready to upload</span></> : <><strong>Choose a file or drop it here</strong><span>PDF or UTF-8 plain text · up to {MAX_UPLOAD_MB} MB</span></>}
                <span className="browse-label">{selectedFile ? "Choose another file" : "Browse files"}</span>
              </label>
              <div className="upload-note"><span className="lock-symbol">⌑</span><span>Files are processed by your local RealityCheck API. Client checks improve usability; the server performs authoritative validation.</span></div>
              <button className="primary-button" type="submit" disabled={isViewingHistory || !canSubmit}>{busy ? <><span className="spinner" /> Uploading…</> : <>{job ? "Process another artifact" : "Analyze artifact"}<span aria-hidden="true">↗</span></>}</button>
              {busy ? <button className="secondary-button" type="button" onClick={() => uploadAbortRef.current?.abort()}>Cancel upload</button> : null}
              {job && !isProcessing && !busy ? <button className="secondary-button" type="button" onClick={startNewAnalysis}>Start a new analysis</button> : null}
            </form>
          ) : (
            <form className="comparison-upload unified-comparison-upload" onSubmit={onCompareDocuments}>
              <label className="comparison-file-picker" htmlFor="comparison-files">
                <input ref={comparisonInputRef} id="comparison-files" type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" disabled={isViewingHistory || comparisonBusy} onChange={(event) => onComparisonFilesChange(event.target.files)} />
                <strong>{comparisonFiles.length ? `${comparisonFiles.length} documents selected` : "Choose multiple source documents"}</strong>
                <span>Select 2–10 PDF or UTF-8 text files. Hold Ctrl to select individual files, or Shift to select a range.</span>
                <span>Requirements + implementation/configuration + observations work best.</span>
              </label>
              {comparisonFiles.length > 0 ? <ul className="comparison-file-list">{comparisonFiles.map((file) => <li key={`${file.name}-${file.size}-${file.lastModified}`}><span>{file.name}</span><small>{formatBytes(file.size)}</small></li>)}</ul> : null}
              <button className="primary-button" type="submit" disabled={isViewingHistory || comparisonBusy || comparisonFiles.length < 2}>{comparisonBusy ? <><span className="spinner" /> Comparing…</> : "Upload & compare documents ↗"}</button>
              {comparisonBusy ? <p className="comparison-progress" role="status">{comparisonProgress}</p> : null}
            </form>
          )}
          <div className="supported-formats"><span>SUPPORTED INPUTS</span><div><span className="format-tag">PDF</span><span className="format-tag">TXT</span></div></div>
        </section>

        <section className="panel status-panel">
          <div className="panel-heading"><div><p className="section-kicker">02 / PROCESS</p><h2>Processing status</h2></div><span className="step-number">02</span></div>
          {uploadMode === "compare" ? (
            comparisonBusy || comparisonJobs.length > 0 || comparison ? <>
              <div className="status-banner">
                <span className={`status-indicator ${comparisonBusy ? "running" : comparisonJobs.some((item) => item.status === "failed" || item.analysis_status === "failed") ? "failed" : "succeeded"}`} />
                <div>
                  <span className="status-label">{comparisonBusy ? "Comparison in progress" : comparison ? "Comparison complete" : "Comparison stopped"}</span>
                  <p>{comparisonBusy ? comparisonProgress || "Processing selected documents…" : comparison ? `Compared ${comparison.documents.length} documents.` : error || "The comparison did not complete. Review the error message."}</p>
                </div>
              </div>
              <div className="stats-grid comparison-stats-grid">
                <div className="stat"><span>Analyzed</span><strong>{comparisonCompletedCount}/{comparisonDisplayDocuments.length}</strong></div>
                <div className="stat"><span>Elements</span><strong>{comparisonElementCount}</strong></div>
                <div className="stat"><span>Evidence items</span><strong>{comparisonEvidenceCount}</strong></div>
                <div className="stat"><span>Total file size</span><strong>{formatBytes(comparisonTotalBytes)}</strong></div>
              </div>
              <div className="comparison-claims-heading comparison-processing-heading"><h3>Document processing</h3><span>{comparisonJobs.length}/{comparisonDisplayDocuments.length} loaded</span></div>
              <div className="comparison-documents comparison-processing-documents">
                {comparisonDisplayDocuments.map((document) => {
                  const item = document.job;
                  const label = !item ? (comparisonBusy ? "Waiting to upload" : "Status unavailable") : item.status === "failed" ? "Extraction failed" : item.analysis_status === "failed" ? "Analysis failed" : item.analysis_status === "succeeded" && TERMINAL.has(item.status) ? "Ready for comparison" : statusLabel(item.status);
                  return <div className="comparison-document" key={document.key}>
                    <span className={`document-dot ${item?.status === "failed" || item?.analysis_status === "failed" ? "failed" : item && TERMINAL.has(item.status) ? "complete" : ""}`} />
                    <div>
                      <strong>{document.filename}</strong>
                      <small>{label}{item ? ` · ${item.element_count} elements · ${item.evidence_count} evidence` : ` · ${formatBytes(document.size_bytes)}`}</small>
                    </div>
                  </div>;
                })}
              </div>
              {comparisonBusy ? <div className="processing-track"><span /></div> : null}
            </> : <div className="empty-state"><div className="empty-orbit"><span>◎</span></div><strong>Comparison stats will appear here</strong><p>Select 2–10 documents and start a comparison to track each document's extraction, evidence count, and analysis status.</p></div>
          ) : !job ? <div className="empty-state"><div className="empty-orbit"><span>◎</span></div><strong>Nothing in the pipeline yet</strong><p>Your job status, timestamps, and extraction diagnostics will appear here after upload.</p></div> : <>
            <div className="status-banner"><span className={`status-indicator ${job.status}`} /><div><span className="status-label">{statusLabel(job.status)}</span><p>{progressText}</p></div></div>
            <div className="job-id-row"><span>JOB ID</span><code title={job.job_id}>{job.job_id}</code><button className="copy-button" type="button" onClick={() => void navigator.clipboard?.writeText(job.job_id).then(() => setNotice("Job ID copied."))} aria-label="Copy job ID">Copy</button></div>
            <div className="stats-grid"><div className="stat"><span>Elements</span><strong>{job.element_count}</strong></div><div className="stat"><span>Evidence items</span><strong>{job.evidence_count}</strong></div><div className="stat"><span>File size</span><strong>{formatBytes(job.size_bytes)}</strong></div></div>
            <div className="timestamp-list"><div><span>Submitted</span><time>{formatDate(job.created_at)}</time></div><div><span>Started</span><time>{formatDate(job.started_at)}</time></div><div><span>Completed</span><time>{formatDate(job.completed_at)}</time></div></div>
            {isProcessing ? <div className="processing-track"><span /></div> : null}
            {lastPolledAt ? <p className="last-updated">Status checked {formatDate(lastPolledAt)}</p> : null}
          </>}
        </section>
      </section>

      {comparison ? <section className="results-section cross-compare-section" aria-labelledby="cross-compare-title">
        <div className="results-heading">
          <div><p className="section-kicker">CROSS-SOURCE ANALYSIS</p><h2 id="cross-compare-title">Comparison results</h2><p className="results-subtitle">Review the strongest candidate gaps first. Every conclusion remains linked to its source.</p></div>
          <span className="count-pill">{comparison.documents.length} sources · {comparison.findings.length} {comparison.findings.length === 1 ? "finding" : "findings"}</span>
        </div>
        <div className="comparison-results">
          {comparison.mode === "offline_heuristic" ? <div className="offline-demo-banner"><strong>OFFLINE COMPARISON · LIMITED HEURISTIC</strong><span>Only a small set of numeric constraints is checked. No model was called; no candidate found does not mean the documents are consistent.</span></div> : null}
          <div className="comparison-summary-strip">
            <div className="comparison-summary-stat"><span>Documents compared</span><strong>{comparison.documents.length}</strong></div>
            <div className="comparison-summary-stat"><span>Claims considered</span><strong>{comparison.claims.length}</strong></div>
            <div className="comparison-summary-stat"><span>Candidate findings</span><strong>{comparison.findings.length}</strong></div>
            <details className="comparison-id-details"><summary>Comparison details</summary><code>{comparison.comparison_id}</code><span>{formatDate(comparison.created_at)} · {comparison.analysis_provider}</span></details>
          </div>
          <ClaimFindingGuide />
          <FindingVisualizations findings={comparison.findings} selectedFilter={selectedFindingFilter} onSelectFilter={setSelectedFindingFilter} historyItems={historyItems} currentHistoryTitle={currentHistoryTitle} currentHistoryKind={currentHistoryKind} onOpenHistory={(item) => void openHistoryItem(item)} />
          {visibleComparisonFindings.length === 0 ? <div className="results-empty"><div className="results-empty-icon">⌁</div><div><strong>{selectedFindingFilter ? "No findings match this filter" : "No candidate discrepancies detected"}</strong><p>This does not prove the documents agree. Review the claims and source passages if important behaviour may be described in different terms or versions.</p></div></div> : (
            <div className="comparison-findings-list">
              {selectedFindingFilter ? <p className="filter-results-note">Showing {visibleComparisonFindings.length} of {comparison.findings.length} findings. Use Clear filter in the visualizations to show all findings.</p> : null}
              {visibleComparisonFindings.map((finding, index) => {
                const sourceById = new Map<string, ComparisonResponse["evidence_sources"][number]>(comparison.evidence_sources.map((source) => [source.evidence_id, source] as const));
                const sources = Array.from(new Set(finding.evidence_ids.map((id) => sourceById.get(id)?.source_name || id.slice(0, 8))));
                return <article className="comparison-finding-card" key={finding.finding_id}>
                  <div className="comparison-finding-number">{String(index + 1).padStart(2, "0")}</div>
                  <div className="comparison-finding-body">
                    <div className="comparison-finding-heading"><h3>{finding.title}</h3><span className={`finding-status ${finding.status}`}>{finding.status.replace("_", " ")}</span></div>
                    <p className="finding-explanation">{finding.explanation}</p>
                    {finding.recommendation ? <div className="finding-recommendation"><strong>Recommended next step</strong><p>{finding.recommendation}</p></div> : null}
                    <div className="source-reference-links"><span>Sources</span>{sources.map((name) => <span className="comparison-source-chip" key={name}>{name}</span>)}</div>
                    {finding.evidence_ids.length ? <details className="finding-evidence-details"><summary>Inspect supporting passages <span>{finding.evidence_ids.length}</span></summary>
                      <div className="comparison-evidence-list">{finding.evidence_ids.map((id) => {
                        const source = sourceById.get(id);
                        return <div className="comparison-evidence-item" key={id}><div><strong>{source?.source_name || "Unknown source"}</strong><code>{id.slice(0, 8)}</code></div><p>{source?.preview || "No source preview is available for this evidence item."}</p></div>;
                      })}</div>
                    </details> : null}
                  </div>
                </article>;
              })}
            </div>
          )}
          <details className="comparison-analysis-details action-board-details"><summary>Recommended action plan & triage board <span>{comparison.findings.length} items</span></summary><ActionBoard findings={comparison.findings} /></details>
          <details className="comparison-analysis-details">
            <summary>Coverage map & evidence relationships <span>Expand</span></summary>
            <div className="visualization-stack">
              <CoverageMap claims={comparison.claims} findings={comparison.findings} sourceNames={new Map(comparison.evidence_sources.map((source) => [source.evidence_id, source.source_name]))} />
              <RelationshipMap claims={comparison.claims} findings={comparison.findings} sourceNames={new Map(comparison.evidence_sources.map((source) => [source.evidence_id, source.source_name]))} />
            </div>
          </details>
          <details className="comparison-source-details">
            <summary>Source documents & processing details <span>{comparison.documents.length}</span></summary>
            <div className="comparison-documents comparison-documents-compact">{comparison.documents.map((document) => <div className="comparison-document" key={document.job_id}><span className={`document-dot ${document.status === "failed" ? "failed" : TERMINAL.has(document.status) ? "complete" : ""}`} /><div><strong>{document.filename}</strong><small>{document.analysis_provider} · {statusLabel(document.status)}</small></div></div>)}</div>
          </details>
          <details className="comparison-claims-details">
            <summary>Claims considered <span>{comparison.claims.length}</span></summary>
            <div className="comparison-claims-list">
              {comparison.claims.length ? comparison.claims.map((claim, index) => {
                const sourceById = new Map<string, ComparisonResponse["evidence_sources"][number]>(comparison.evidence_sources.map((source) => [source.evidence_id, source] as const));
                const sourceNames = Array.from(new Set(claim.evidence_ids.map((id) => sourceById.get(id)?.source_name || id.slice(0, 8))));
                return <article className="claim-card" key={claim.claim_id}><div className="finding-top"><span className="evidence-index">CLAIM {String(index + 1).padStart(2, "0")}</span><span className="type-chip">{categoryLabel(claim.category)} · {claimKindLabel(claim.kind)}</span></div><p className="finding-explanation">{claim.text}</p><div className="source-reference-links"><span>Source</span>{sourceNames.map((name) => <span className="comparison-source-chip" key={name}>{name}</span>)}</div></article>;
              }) : <p className="comparison-detail-empty">No claims were saved for this comparison. Check the source jobs' claim-analysis status.</p>}
            </div>
          </details>
          <details className="comparison-source-evidence-details">
            <summary>Extracted source evidence <span>{comparisonEvidence.length}</span></summary>
            <p className="comparison-detail-intro">Evidence from every document in this comparison is shown here with its original source and extraction provenance.</p>
            <div className="comparison-source-evidence-list">
              {comparisonEvidence.length ? comparisonEvidence.map((item, index) => <EvidenceCard key={item.evidence_id} item={item} index={index} />) : <p className="comparison-detail-empty">Full source evidence could not be loaded for this comparison. The comparison's source previews remain available above.</p>}
            </div>
          </details>
          <ExternalResearchPanel />
        </div>
      </section> : null}

      {error ? <div className="alert error-alert" role="alert"><strong>Something needs attention</strong><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div> : null}
      {notice ? <div className="alert notice-alert" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notice">×</button></div> : null}

      {uploadMode === "single" ? <section className="results-section analysis-section">
        <div className="results-heading"><div><p className="section-kicker">03 / RECONCILE</p><h2>Claims & reality check</h2><p className="results-subtitle">Claims stay linked to source evidence; conclusions are kept separate from facts.</p></div>{analysis ? <span className="count-pill">{analysis.claims.length} {analysis.claims.length === 1 ? "claim" : "claims"} · {analysis.findings.length} {analysis.findings.length === 1 ? "finding" : "findings"}</span> : null}</div>
        {isOfflineDemo ? <div className="offline-demo-banner" role="note"><strong>OFFLINE DEMO · SIMULATED RESULTS</strong><span>No model was called. Source text is split into claim candidates. The finding is a workflow notice, not a contradiction verdict; no claim has been independently verified.</span></div> : null}
        {analysis ? <div className="analysis-summary-strip"><div><span>Claims extracted</span><strong>{analysis.claims.length}</strong></div><div><span>Candidate findings</span><strong>{analysis.findings.length}</strong></div><div><span>Evidence items</span><strong>{evidence?.count ?? 0}</strong></div></div> : null}
        {analysis ? <ClaimFindingGuide /> : null}
        {!analysis && !job ? <div className="results-empty"><div className="results-empty-icon">◇</div><div><strong>Analysis will appear here</strong><p>After extraction, RealityCheck will identify claims and check them against the available evidence.</p></div></div> : null}
        {job && job.analysis_status === "not_configured" && !isProcessing ? <div className="results-empty"><div className="results-empty-icon">⚙</div><div><strong>Analysis provider is not configured</strong><p>Evidence extraction works, but claim analysis is disabled. Set ANALYSIS_PROVIDER=offline for clearly labelled demo results, or configure NEBIUS_API_KEY and ANALYSIS_PROVIDER=nebius (or auto).</p></div></div> : null}
        {job && job.analysis_status === "running" && (!analysis || (!analysis.claims.length && !analysis.findings.length)) ? <div className="results-empty"><div className="results-empty-icon">◌</div><div><strong>Analysis in progress</strong><p>{job.progress_message}</p></div></div> : null}
        {analysis ? <FindingVisualizations findings={analysis.findings} selectedFilter={selectedFindingFilter} onSelectFilter={setSelectedFindingFilter} historyItems={historyItems} currentHistoryTitle={currentHistoryTitle} currentHistoryKind={currentHistoryKind} onOpenHistory={(item) => void openHistoryItem(item)} /> : null}
        {analysis?.findings.length ? <div className="key-findings-section"><div className="subsection-heading"><h3>Key findings</h3><span>{selectedFindingFilter ? `${visibleAnalysisFindings.length} of ` : ""}{analysis.findings.length} {analysis.findings.length === 1 ? "candidate" : "candidates"}</span></div>{selectedFindingFilter ? <p className="filter-results-note">Filtered by chart selection. Clear the filter in the visualizations to show all findings.</p> : null}{visibleAnalysisFindings.map((finding, index) => <article className="finding-card key-finding-card" id={`finding-${finding.finding_id}`} key={finding.finding_id}>
          <div className="finding-top"><span className="evidence-index">FINDING {String(index + 1).padStart(2, "0")}</span><span className={`finding-status ${finding.status}`}>{finding.status.replace("_", " ")}</span></div>
          <h3>{finding.title}</h3><p className="finding-explanation">{finding.explanation}</p>
          {finding.recommendation ? <div className="finding-recommendation"><strong>Recommended next step</strong><p>{finding.recommendation}</p></div> : null}
          <details className="finding-provenance-details"><summary>Why was this raised? Evidence & related claims</summary>
            <div className="provenance-row">{!isOfflineDemo ? <span><span className="muted-label">Model confidence (uncalibrated)</span>{Math.round(finding.confidence * 100)}%</span> : <span><span className="muted-label">Mode</span>Simulated offline result</span>}<span><span className="muted-label">Evidence links</span>{finding.evidence_ids.length}</span><span><span className="muted-label">Related claims</span>{finding.claim_ids.length}</span></div>
            <div className="source-reference-links"><span>Evidence</span>{finding.evidence_ids.map((id) => <a key={id} href={`#evidence-${id}`}>{id.slice(0, 8)}</a>)}{finding.claim_ids.length ? <span className="related-claims-label">Claims</span> : null}{finding.claim_ids.map((id) => <a key={id} href={`#claim-${id}`}>{id.slice(0, 8)}</a>)}</div>
          </details>
        </article>)}</div> : null}
        {analysis?.findings.length ? <details className="analysis-visual-details action-board-details"><summary>Recommended action plan & triage board <span>{analysis.findings.length} items</span></summary><ActionBoard findings={analysis.findings} /></details> : null}
        {analysis ? <details className="analysis-visual-details"><summary>Coverage map & evidence relationships <span>Expand details</span></summary><div className="visualization-stack"><CoverageMap claims={analysis.claims} findings={analysis.findings} sourceNames={new Map((evidence?.items || []).map((item) => [item.evidence_id, item.provenance.source_name]))} /><RelationshipMap claims={analysis.claims} findings={analysis.findings} sourceNames={new Map((evidence?.items || []).map((item) => [item.evidence_id, item.provenance.source_name]))} /></div></details> : null}
        {analysis?.claims.length ? <details className="analysis-claims-details"><summary>All extracted claims <span>{analysis.claims.length}</span></summary><div className="comparison-claims-list">{analysis.claims.map((claim, index) => <article className="claim-card" id={`claim-${claim.claim_id}`} key={claim.claim_id}>
          <div className="finding-top"><span className="evidence-index">CLAIM {String(index + 1).padStart(2, "0")}</span><span className="type-chip">{categoryLabel(claim.category)} · {claimKindLabel(claim.kind)}</span></div>
          <p className="finding-explanation">{claim.text}</p>
          {claim.category === "unknown" ? <p className="claim-classification-note">Unclassified means the statement was extracted, but its domain role was not confidently identified. It is not a finding status.</p> : null}
          <div className="provenance-row">{isOfflineDemo ? <span><span className="muted-label">Assessment</span> Source-linked · not independently assessed</span> : <span><span className="muted-label">Model confidence (uncalibrated)</span>{Math.round(claim.confidence * 100)}%</span>}<span><span className="muted-label">Evidence links</span>{claim.evidence_ids.length}</span></div>
          <div className="source-reference-links"><span>Source evidence</span>{claim.evidence_ids.map((id) => <a key={id} href={`#evidence-${id}`}>{id.slice(0, 8)}</a>)}</div>
        </article>)}</div></details> : null}
        {job?.analysis_status === "failed" ? <div className="alert error-alert"><strong>AI analysis needs attention</strong><span>{job.analysis_error_message || "Claims analysis failed; extracted evidence remains available."}</span></div> : null}
        {analysis ? <ExternalResearchPanel /> : null}
      </section> : null}

      {uploadMode === "single" ? <section className="results-section">
        <div className="results-heading"><div><p className="section-kicker">04 / TRACE</p><h2>Evidence extracted</h2><p className="results-subtitle">Inspect each item alongside its source and extraction provenance.</p></div>{evidence ? <span className="count-pill">{evidence.count} {evidence.count === 1 ? "item" : "items"}</span> : null}</div>
        {!evidence && !job?.diagnostics.length ? <div className="results-empty"><div className="results-empty-icon">⌁</div><div><strong>Evidence will appear here</strong><p>Once extraction completes, the results will be shown with provenance details. Evidence is kept distinct from conclusions.</p></div></div> : null}
        {evidence && evidence.items.length === 0 ? <div className="results-empty"><div className="results-empty-icon">∅</div><div><strong>No evidence items were produced</strong><p>The job finished, but there were no evidence objects to display. Check extraction diagnostics.</p></div></div> : null}
        {(evidence?.items.length || job?.diagnostics.length) ? <details className="analysis-visual-details evidence-disclosure"><summary>Evidence, source passages & extraction diagnostics <span>{evidence?.count ?? 0} evidence items</span></summary>
          {evidence?.items.map((item, index) => <EvidenceCard key={item.evidence_id} item={item} index={index} />)}
          {job?.diagnostics.length ? <div className="diagnostics-panel"><h3>Extraction diagnostics <span>{job.diagnostics.length}</span></h3>{job.diagnostics.map((diagnostic, index) => <div className="diagnostic-row" key={`${diagnostic.severity}-${index}`}><span className={`diagnostic-severity ${diagnostic.severity.toLowerCase()}`}>{diagnostic.severity}</span><div><p>{diagnostic.message}</p>{diagnostic.location?.page ? <small>Page {diagnostic.location.page}</small> : null}</div></div>)}</div> : null}
        </details> : null}
      </section> : null}

      <footer className="footer"><span>REALITYCHECK <span className="footer-divider">/</span> EVIDENCE WORKSPACE</span><span>API <code>{API_BASE_URL}</code></span></footer>
      </div>
    </main>
  );
}
