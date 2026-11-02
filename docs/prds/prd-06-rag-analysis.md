# PRD-06: Cloud RAG root-cause analysis

**Original requirement:** C-03

**Service:** [RAG](../services/cloud/rag.md)

## Goal

Use the edge summary and retrieved cases as context, and produce a grounded root-cause analysis and actionable remediation suggestions.

## Scope

- Orchestrate the PRD-05 retrieval results with the edge summary.
- The prompt must contain the sections `<edge_summary>`, `<retrieved_cases>`, and `<analysis_instructions>`.
- Call a cloud large model and return root-cause analysis and remediation suggestions.

## Acceptance criteria

- The time from request entry into the analysis service to a complete response is under 10 seconds. The test load and the timeout statistic are recorded.
- On a review set agreed by both sides, the average actionability score is at least 4/5.
- The output can separate retrieved evidence from model inference. When evidence is insufficient, uncertainty is stated. Inference is not presented as a confirmed fact.
- Retrieved cases, the input summary, and the final output can be correlated by request, so they can be reviewed and evaluated.

## Dependencies and open decisions

- Depends on the hybrid retrieval results from PRD-05.
- Technical-design candidates: LlamaIndex or LangChain. Model candidates: self-hosted Qwen2.5-72B-Instruct on vLLM, or the Claude API. Choose based on data compliance, latency, cost, and availability.
- Define prompt-injection protection, sensitive-data handling, the error response when the model is unavailable, and the path for human escalation.
- Fix the actionability rubric, the number of reviewers, and the evaluation sample.
