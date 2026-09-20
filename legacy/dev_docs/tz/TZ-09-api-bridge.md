# TZ-09. API bridge: public contour ↔ local GPU node

> **Status: 🔨 transport ready (11 bridge tests + 14 contract tests).**
> ✅ msgspec structures (Candle, OhlcvBatch, AggBar, SignalEvent, ReportEvent,
> BacktestCommand, TrainCommand); QueueName enum + topology; ACL
> (can_publish/can_consume per node); the "no change-risk-limits command" invariant (test).
> ✅ wave 2: main/src/bridge.py — WhiteBridge (publishes md.*/cmd.* with ACL check,
> consumers evt.report/evt.signals → WhiteAPI stores), LocalBridge (consumers
> md.ohlcv/cmd.backtest with schema-version tolerance, publishes evt.*), ReconnectPolicy
> (exponential backoff with cap), HeartbeatMonitor (last-seen per queue, stale_queues for lag
> monitoring). Tests: end-to-end cmd.backtest → mock-local → evt.report → report in WhiteAPI via
> TestRabbitBroker (in-memory, no RabbitMQ), md.ohlcv idempotency, ACL invariants.
> Remaining: live RabbitMQ (docker-compose), TLS/tokens, lag metrics in Prometheus.

## 1. Context

The system splits into two contours:
- **Public (white) API**: ingest exchange data, REST for web/bot, report storage. No GPU deps —
  requirements have no torch.
- **Local GPU node**: training, model inference, Ollama, Qdrant, RAG, backtest.

From the white API we accept exchange data and "do something"; heavy execution happens on the local.

## 2. Why this way

### 2.1. Connection direction: local → broker, never the reverse
The GPU node is the most valuable and vulnerable part (models, datasets). It must not have open
inbound ports: the local node keeps a persistent outbound connection to the public contour's
broker; the white API "knocks" the local only through the command queue.
**Rejected alternative** (HTTP tunnel white → local): an open inbound port + a custom
retry/buffering mechanism — RabbitMQ provides all of that out of the box.

### 2.2. Transport — RabbitMQ (FastStream + aio-pika)
Already a dependency and in docker-compose: zero new infrastructure. Queues give buffering
(tick-rate ≠ training speed), ack semantics, retries, break resilience. TLS at the transport level.

### 2.3. Queues and contracts (msgspec from api.md)
```
md.ohlcv        white → local   candles/ticks (Candle)
md.agg          white → local   aggregated bars
cmd.backtest    white → local   backtest request (BacktestConfig)
cmd.train       white → local   training request (optional, ACL-protected)
evt.report      local → white   BacktestReport / training metrics
evt.signals     local → white   signals + P(win) (PredictionContract)
```
**Key protocol constraint:** cmd.* physically has no "change risk limits" / "read risk data"
commands — cross-cutting principle #1 enforced at the message-schema level.

### 2.4. P(win) crosses the boundary as a number
The model is not executed on the white node; the Risk Engine receives an already-computed
probability. **Why:** the GPU stack does not travel to the public contour, and the decision path
stays deterministic.

### 2.5. Security
- mTLS or long-lived token + per-queue ACL (the local node writes only evt.*, reads only md.*/cmd.*).
- Ingestion idempotency: key (ticker, ts) — redelivery after a retry does not duplicate candles.
- Web/bot authenticate against the white API; the web never reaches the queues.

## 3. Requirements

1. Queue topology and directions per §2.1/§2.3; msgspec message structures from `contracts/`
   (TZ-08), not local copies.
2. Reconnect/backoff for the local consumer; a disconnection loses no data (durable queues).
3. ACL: the white publisher has no rights to evt.*; the local to cmd.* publish except allowed ones.
4. Message-schema versioning (`schema_version` field) — queues outlive deploys.
5. Monitoring: queue lag, last-message age, local-node heartbeat.

## 4. Acceptance criteria

- Test: local disconnection → recovery → no message lost/duplicated.
- Test: the white publisher cannot send a command outside the whitelist (ACL).
- Idempotency: a duplicate md.ohlcv does not create a duplicate candle.