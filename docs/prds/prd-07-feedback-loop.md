# PRD-07: Summary-quality feedback loop

**Original requirement:** C-04

**Service:** removed with `services/feedback-admin`

## Goal

Use summary gaps found during cloud analysis to produce reviewable, traceable prompt-optimization suggestions for the edge, and keep measuring changes in summary quality.

## Scope

- Mark edge-summary gaps that prevent effective retrieval or analysis.
- Generate prompt-optimization suggestions from problem samples, and send approved suggestions back to the edge.
- Record the suggestion, review, publication, and effect evaluation.
- The MVP generates structured suggestions in the cloud and provides a CLI for human review and publication status. It does not automatically change the live edge prompt.

## Acceptance criteria

- Produce at least 3 prompt-iteration suggestions per week that reviewers judge to be valid.
- Raise summary-information completeness by at least 5% per month against the baseline. The baseline, completeness fields, and evaluation sample are defined.
- A suggestion can be traced to the source problem and the prompt version. A published result can be rolled back.
- An unreviewed suggestion must not automatically replace the production prompt.

## Dependencies and open decisions

- Depends on the summary field contract from PRD-02 and the analysis feedback from PRD-06.
- The current rule creates a suggestion when `target_ip`, `target_port`, or `error_code` is missing, or when no case is recalled. The deduplication key is the event ID plus the category.
- `prompt-feedback --db <feedback.sqlite3> list|review|publish|weekly-report` manages suggestions. `published` means only that a person has confirmed deployment. It does not perform a remote push.
- Define the evaluation standard for a "summary-gap case", a "valid suggestion", and a completeness improvement.
- Decide the reviewer role, real edge distribution, version compatibility, canary release, and rollback.
