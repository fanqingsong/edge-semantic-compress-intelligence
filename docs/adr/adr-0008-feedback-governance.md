# ADR-0008: Summary-quality feedback and prompt governance

- Status: Accepted (MVP human review; the live prompt is not changed automatically)
- Date: 2026-11-01
- Related PRD: PRD-07
- Code: removed with `services/feedback-admin`

## Context

Cloud analysis may find that an edge summary is missing a critical entity or context. The system requires marking those cases, generating prompt-optimization suggestions, and sending them back to the edge. Review, publication, and rollback are not defined yet.

## Current architecture constraints

- Feedback is triggered by a traceable problem case and can be tied to the summary, the prompt version, and the analysis result.
- The target is at least 3 valid prompt-iteration suggestions per week, and at least a 5% monthly increase in summary-information completeness.
- Suggestion effect is evaluated with a fixed definition and a fixed sample.

## Decision

- After cloud RAG processing, if a critical entity is missing or no case is recalled, generate a traceable prompt-improvement suggestion.
- A suggestion record contains field-status or recall-count evidence, a concrete prompt patch, the expected metric, synthetic positive and negative validation samples, and a risk note.
- SQLite deduplicates by `event_id + category` and stores only the event ID and the summary-quality signal. It does not copy the raw log or the summary text.
- The only allowed states are `pending -> approved/rejected -> published`. Only an approved suggestion can be marked published.
- The `prompt-feedback` CLI provides listing, review, publication, and statistics for the last 7 days. Publication status is a human action. It does not automatically replace the live prompt of the edge agent.

## Follow-up configuration

- Define the formal labeling standard and the owner for a "valid suggestion" and for the summary-completeness metric.
- Implement safe distribution, canary release, and edge rollback for approved suggestions. The current publish action only records status and does not push configuration.
- Define redaction and retention requirements for sensitive data in prompts and samples.

## Consequences

- Until review and rollback are defined, an automatically generated suggestion must not be applied directly to a production edge device.
- The feedback loop depends on the summary contract from PRD-02 and the analysis result from PRD-06.
- The monthly improvement metric must control for changes in the evaluation set, so a sample change is not mistaken for a quality gain.
