REALITYCHECK UI DEMO PACK
=========================

Files:
- upload-service-requirements.pdf: main requirements document
- requirements.txt: text version of requirements (use either PDF or TXT, not both in one comparison)
- implementation-notes.txt: implementation claims and settings
- test-observations.txt: partial test observations, deliberately incomplete
- production-config.txt: synthetic config snapshot

Recommended UI demo:
1. Start RealityCheck with ANALYSIS_PROVIDER=offline.
2. For single-file view, upload upload-service-requirements.pdf.
3. For the richest comparison view, upload exactly these four files:
   - upload-service-requirements.pdf
   - implementation-notes.txt
   - test-observations.txt
   - production-config.txt
4. Review the top-level summary, key findings, action recommendations and chart.
5. Expand claims, coverage, relationship details and provenance only after reviewing the headline results.

Intended discrepancies / review candidates:
- R-002 requires 80 MB; implementation and config say 50 MB.
- R-003 requires 45 seconds; implementation and config say 60 seconds.
- R-005 requires no more than 7 days; implementation and config say 10 days.
- R-006 requires secret/body redaction; the implementation notes do not establish full redaction coverage.
- R-007 requires exact evidence traceability; the observation only records a partial manual check.
- R-008 requires offline disclosure; a staging observation confirms the label, but production provider configuration is absent.
- R-001 has partial support from OBS-001/002/003; scanned PDF behavior is not tested.
- AT-005 and retention cleanup are unverified, not failed.

Cautions:
- All data is synthetic and not a real security assessment.
- Offline mode is simulated; do not expect the model to discover every semantic issue.
- Treat findings as candidate findings and verify evidence links manually.
- Upload PDF plus the three companion TXT files for a richer cross-document UI. Do not upload both the PDF and requirements.txt together unless you intentionally want duplicate requirements evidence.
