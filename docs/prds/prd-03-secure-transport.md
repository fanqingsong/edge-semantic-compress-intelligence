# PRD-03: Edge secure transport and weak-network buffering

**Original requirement:** E-05

**Service:** [Transport](../services/edge/transport.md). Cloud ingress is in the [cloud agent](../services/cloud/agent.md).

## Goal

Deliver structured edge records to the cloud securely and reliably. When the network is temporarily unavailable, buffer them locally and retry after connectivity returns.

## Scope

- The MVP transports structured records with MQTT v5, QoS 1, and MessagePack. Kafka is outside the current MVP.
- Use mutual TLS. Configure access control for the chosen protocol, such as an MQTT topic ACL.
- Buffer in a SQLite local-disk outbox, with resend and catch-up of the backlog. The default capacity is 100 MiB and is configurable.
- The technical design requires MessagePack serialization. The cloud ingress uses the same data contract.

## Acceptance criteria

- A connection without a valid client certificate is rejected. Certificate identity and the authorization policy can be verified.
- Under the agreed outage duration, throughput, and disk capacity, buffered records are fully retried after the connection returns.
- Message retries do not cause duplicate processing in the cloud. Idempotency is verified with a stable message identifier or an equivalent mechanism.
- Transport failures, buffer backlog, disk usage, and retry state are observable.

## Dependencies and open decisions

- Depends on the structured records from PRD-02 and on the cloud message-ingress service.
- The local Compose stack already enables mTLS and topic ACLs. An organizational CA and certificate rotation or revocation for the production broker are still to be deployed.
- A connection without a client certificate has been verified to fail. A cloud certificate cannot publish to the edge event topic.
- An outbox record is deleted only after the broker acknowledges it. That acknowledgement is not the same as successful cloud business processing. The consumer still needs idempotency by `event_id`.
- The cloud consumer implements manual ACK and persistent deduplication. It does not ACK when business processing fails. A repeated identical event is ACKed and is not processed again.
- Define the maximum offline duration, the device disk quota, the alert when the buffer is full, and the production certificate-rotation procedure.
- JSON in PRD-02 and MessagePack on the transport layer are the model output and the wire encoding. Define a consistent decode and encode boundary.
