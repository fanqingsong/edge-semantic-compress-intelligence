# Operations cases

## Incident: CASE-2026-001

Summary: Payment API requests timed out while opening database connections.

Root cause: The payment service exhausted its database connection pool.

Resolution: Restore service capacity and review the pool limit against database capacity.

Target IP: 192.0.2.10