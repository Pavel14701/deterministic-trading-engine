# TZ-15. OKX API: venue adapter + event reactions (WS-first, onion architecture)

> **Status: ⬜ spec ready, implementation not started.**
> To be built after TZ-03 wave 2 (the universal indicator mapper). Scope v1: SPOT + SWAP
> (perpetual), WS-first, normalized to the T-Invest canon.

## 1. Context

The system works with T-Invest (TZ-00 Z-architecture). OKX is a second venue: a source of candles
(md.ohlcv) and an executor of decisions. Requirement: **OKX is brought under the T-Invest canon** —
the adapter introduces no formats of its own but normalizes everything into the existing TZ-02/TZ-09
contracts (`Candle`, `OhlcvBatch`, `SignalEvent`, `Decision`) at the boundary. Data is collected via
WebSocket (push); REST only where WS gives no history/snapshots. Package architecture — onion
(dependencies point inward), assembly — dishka.

Source: https://www.okx.com/docs-v5/en/ (v5). Unified endpoints for all instrument types; the type
is set by `instType` (SPOT / SWAP / FUTURES) and `tdMode` (cash / cross / isolated).

## 2. WS-first principle, REST is auxiliary

| Data | Transport | Why |
|---|---|---|
| Live candles, tickers, books5 | **WS public** `wss://ws.okx.com:8443/ws/v5/public` | push, no polling |
| History for warm-up / `resolve_history` | REST `GET /market/candles`, `GET /market/history-candles` | WS gives no arbitrary depth |
| Orders place/amend/cancel | REST `POST /trade/order`, `cancel-order`, `amend-order`; `GET /trade/orders-pending`, `GET /trade/fills` | sync response, `clOrdId` idempotency |
| Fills / positions / balance | **WS private** `wss://ws.okx.com:8443/ws/v5/private` (channels `orders`, `positions`, `account`) | instant reactions |
| Reconcile after a break | REST snapshots (`positions`, `orders-pending`, `balance`) | source of truth on resume |

REST polling is absent in steady state; it appears only in degraded mode while WS reconnects.

## 3. Authentication and configuration

- REST: headers `OK-ACCESS-KEY/SIGN/TIMESTAMP/PASSPHRASE`;
  sign = base64(HMAC-SHA256(ts + method + requestPath + body, secret)).
- WS private: op `login` {apiKey, passphrase, timestamp, sign} — same signature over
  ts + method(/users/self/verify) + body.
- Startup check `GET /account/config`: account mode and `posMode` (net / long_short_mode).
  **Mismatch with the venue config = refusal to start**, not auto-switch (TZ-00 determinism).
- `POST /account/set-leverage` — only at instrument start, value from config; not called for SPOT.
- Rate limits: a custom token budget (stdlib); OKX limits on candles/orders/WS subscriptions are
  respected in the client.

## 4. Normalization to the T-Invest canon (the key part)

Canon: `contracts.Candle{inst_id, ts int ms, open, high, low, close, volume}`,
ts = **bar open time**; `OhlcvBatch`; long/short direction.

| OKX | → canon | Rule |
|---|---|---|
| `/market/candles` row `[ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm]` (all strings) | `Candle` | float/int; volume: SPOT = `vol` (base ccy); SWAP = `vol` × `ctVal` (contracts → base volume) — semantics table in `mapping.py` |
| `confirm = 0 / 1` | `CandleClosed` | signal built **only on confirm=1**; unconfirmed (confirm=0) is the current-bar view, does not reach the DSL (TZ-04 §5 causality) |
| `bar`: 1m/3m/5m/15m/30m/1H/4H/1Dutc/1W… | `BAR_MAP` | one table: canonical id (1m/5m/15m/1h/4h/1d/1w) ↔ OKX bar ↔ t-invest interval; completeness test in both directions |
| `instId` BTC-USDT / BTC-USDT-SWAP ↔ t-invest FIGI | port `InstrumentMap` | canonical internal symbol → venue-native; dict from config/PG (TZ-10) |
| `/public/instruments` `lotSz,tickSz,minSz,ctVal` | `InstrumentSpec` | deterministic rounding of price/size before place |
| side/posSide, tdMode | net / long_short | net: side=buy/sell from direction; long_short: side+posSide; tdMode cash/cross/isolated from venue config |
## 5. Onion architecture (dependencies point inward)

```
┌─────────────────────────────────────────────────────────┐
│ L4 External (frameworks)                                  │
│   ws_impl.py / http_impl.py — websockets, niquests        │
├─────────────────────────────────────────────────────────┤
│ L3 Infrastructure adapters                                │
│   okx_client.py — OKX protocol: sign, login, normalize    │
│   responses → domain events/DTO                          │
│   repository.py — persistence (positions/fills → TZ-10 PG)│
├─────────────────────────────────────────────────────────┤
│ L2 Application (use-cases)                                │
│   events.py — event loop: queue, reactions, reconcile    │
│   executor.py — "execute a Decision" use-case            │
│   collector.py — "candles → md.ohlcv" use-case           │
├─────────────────────────────────────────────────────────┤
│ L1 Domain (core, no I/O)                                  │
│   domain.py — OkxEvent, OrderRequest, InstrumentSpec,     │
│   Position, venue-config model (msgspec/dataclass)        │
│   ports.py — Protocol ports: VenueTransport, EventSink,   │
│   OrderGateway, StateStore  ← the single DI seam          │
└─────────────────────────────────────────────────────────┘
```

Rules: L1 imports nothing outward (no niquests/websockets/dishka); L2 depends only on L1 (ports);
L3 implements L1 ports and knows the OKX protocol but not the event loop; L4 is bare transport
(bytes in/out). Cross-cutting deps (Risk Engine, DSL, TZ-09 contracts) reach L2/L3 through the same
ports, not direct imports — okx does not pull backtest into its domain.

## 5.1. Port catalog (L1, `okx/ports.py`) — the DI keys

```python
class VenueTransport(Protocol):      # bare transport (L4 behind); no OKX protocol
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def send(self, payload: dict) -> None: ...        # WS subscribe/login/order
    async def recv(self) -> dict | None: ...                # raw ws message
    def request(self, method, path, body) -> dict: ...      # REST
    @property
    def connected(self) -> bool: ...
class MarketDataSource(Protocol):    # L2←L3: normalized market data
    def candles_history(self, inst, bar, n) -> OhlcvBatch: ...
    def subscribe_candles(self, inst, bar) -> None: ...
    def instruments(self, inst_type) -> list[InstrumentSpec]: ...
class OrderGateway(Protocol):        # L2←L3: execution (the only place knowing the OKX trade API)
    def place(self, req: OrderRequest) -> OrderAck: ...
    def cancel(self, inst, order_id) -> None: ...
    def amend(self, req: AmendRequest) -> OrderAck: ...
    def pending(self, inst) -> list[OrderState]: ...
    def open_position(self, inst) -> Position | None: ...
class AccountReader(Protocol):       # L2←L3: PortfolioState for the Risk Engine
    def balance_available(self, ccy) -> float: ...
    def portfolio_state(self) -> "PortfolioState": ...
class InstrumentMap(Protocol):       # canonical symbol <-> venue instId + InstrumentSpec
class EventSink(Protocol):           # push(DomainEvent): md.ohlcv / evt.report / log
class RiskGate(Protocol):            # check(signal) -> Decision (risk.engine behind the port)
class SignalSource(Protocol):        # on_candle(batch) -> list[Signal] (dsl behind the port)
class StateStore(Protocol):          # save_fill / last_snapshot (reconcile)
```
## 6. Event loop (a small hand-written API)

One `OkxEvent` type (msgspec), one queue per instrument (no parallel reactions on one instrument),
an "event → reactions" registry (config-driven like TZ-11 rules):

| Event | Reaction v1 |
|---|---|
| `CandleClosed` | `SignalSource.on_candle` → `RiskGate.check` → `OrderGateway.place` (+`attachAlgoOrds` with ATR SL/TP) |
| `OrderFilled` (WS private) | update position/avg, `StateStore.save_fill` |
| `AlgoTriggered` (WS `orders`, ordType conditional/oto) | record SL/TP execution |
| `PositionUpdated`/`AccountUpdated` | sync `PortfolioState` (peak_capital, day_pnl → drawdown_stop) |
| `WsDisconnected` | `ReconnectPolicy` (reused from TZ-09) → REST reconcile → resume |

Invariants (code + tests, not config): an order only on a confirmed event; every reaction goes
through the Risk Engine; `clOrdId` idempotent; processing is monotonic; reconcile is the source of
truth after a break (no messages lost). The LLM contour has neither import nor transport access
(TZ-00 §1).

## 7. dishka assembly

Per the TZ-08 pattern (Protocol keys, lazy connects, no network at startup):
`okx/di.py` — providers by layer (Transport/Client/Repository → L3, EventLoop/Executor/Collector →
L2), venue config from env. It plugs into the existing main contours: the white assembly wires
`collector.py` (md.ohlcv), the local one — `executor.py`. Tests replace ports with fakes via
`make_container(FakeTransportProvider())` — the assembly itself is tested.

## 8. Stack

`niquests` (REST; precedent dte-dsl) · `websockets` (WS; the only new dependency — aiohttp rejected:
it drags the whole HTTP stack for a WS client; the official okx SDK rejected: its abstractions break
the "contracts are our msgspec structures" principle) · `msgspec` (domain/contracts) · `pyyaml`
(venue config) · stdlib hmac/hashlib (signatures) · pytest/pytest-asyncio (strict). No torch —
TZ-00 §4.7 GPU isolation. Own rate-limit budget (token bucket on stdlib).

## 9. Acceptance criteria

- Fake-transport e2e: `CandleClosed` → signal → `RiskGate.check` (on reject — no order, event in
  audit) → `place` with `clOrdId`; replaying the same candle → no duplicate goes out (idempotency).
- WS private e2e: `OrderFilled` → position updated → `PortfolioState` synced.
- Reconcile e2e: break → reconnect with backoff → REST snapshot → resume without event loss.
- Normalization: every OKX payload type has a "payload → canon == reference" test
  (strings→float, ts ms, confirm, volume by instType).
- posMode mismatch → startup refusal; lotSz/tickSz rounding deterministic.
- ruff/mypy clean; `uv run --package dte-okx pytest okx/tests` green.

## 10. Links

- **TZ-04**: the executor reuses the execution semantics (point 0 — one engine); RiskGate rejects
  go into the audit as in backtest.
- **TZ-09**: `ReconnectPolicy`/`HeartbeatMonitor` reused; OKX events are outside the TZ-09 queues —
  the white node has its own protocols.
- **TZ-10**: the `InstrumentMap` dict and fill journal — in PG (Alembic migration if needed).
- **TZ-11**: the RiskGate port is the single decision entrance; limits are data.
| ts as an ms string | int ms | dedupe by (inst_id, ts) — store idempotency already exists |