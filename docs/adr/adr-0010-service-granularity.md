# ADR-0010: Manage code and docs at service granularity

- Status: Accepted
- Date: 2026-11-02
- Related PRDs: PRD-01, PRD-02, PRD-03, PRD-04, PRD-05, PRD-06, PRD-07
- Code: [service catalog](../services/README.md)

## Context

The edge and the cloud each contain several services. If every implementation on one side lives in a single package, the service boundary exists only in documents and process names, and a change to one service touches the modules of the others. Documents written for a whole side also drift away from the code boundary.

ADR-0001 splits responsibilities between edge and cloud. It does not require each service to have its own code and its own document.

## Decision

- Package code by service. A service's implementation lives only in its own package. Modules of several services are not placed in one package.
- Use the same granularity for documents. Each service has one note under `docs/services/`, and the path matches the code package. PRDs and ADRs name the owning service. The system README keeps only the cross-service view and links to the service notes. It does not restate the internal rules of each service.
- The requirements document and the technical design stay as the original inputs. They are not rearranged to match code packages.
- Process entry points only assemble. The edge agent calls filtering, summarization, and transport. The cloud agent calls retrieval, RAG, and feedback observation. The entry package does not contain those service implementations.
- Knowledge ingestion and feedback review are separate processes, and each still has its own code package and document.
- Cross-service contracts live in `shared`. `shared` contains no service logic and does not depend on any service.
- A dependency points at the service that defines the produced type. For example, RAG uses `RetrievedCase` defined by retrieval, and retrieval does not depend on RAG.
- When a service is added, merged, or split, update the code package, the service note, and the service ownership on the PRDs and ADRs together. Changing only one of those is not done.

Current service split:

| Side | Service | Code package |
|---|---|---|
| Edge | Filtering | `services/edge/filtering` |
| Edge | Summarization | `services/edge/summarization` |
| Edge | Transport | `services/edge/transport` |
| Edge | edge agent | `services/edge/agent` |
| Cloud | Knowledge ingestion | `services/cloud/knowledge` |
| Cloud | Retrieval | `services/cloud/retrieval` |
| Cloud | RAG | `services/cloud/rag` |
| Cloud | Feedback | `services/cloud/feedback` |
| Cloud | cloud agent | `services/cloud/agent` |
| Shared | Contract | `shared` |

Fluent Bit only collects logs. Its configuration stays in `deploy/fluent-bit` and is not merged into the filtering service package.

## Consequences

- A service can be read, tested, and changed on its own. A change to an assembly process should not move another service's code back into the same package.
- The service note is the body of that service's behavior. A PRD keeps acceptance criteria. An ADR keeps the choice and the constraint.
- When a service boundary in the table above changes, update this ADR's date, the service table, and the affected service notes.

## Alternatives

- Manage code in only two packages, edge and cloud. Several services on the same side would still be mixed together. Rejected.
- Package only by operating-system process. Retrieval would be depended on by both knowledge ingestion and the cloud agent, and filtering, summarization, and transport would be piled back into the edge agent. Rejected.
- One repository per service. At the current repository size, that adds release and contract-sync cost. Rejected.
