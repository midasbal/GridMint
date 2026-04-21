# GridMint — Agent Architecture

GridMint is a multi-agent DePIN energy marketplace running on Arc Testnet. Ten autonomous agents participate in a continuous double-auction to buy and sell kilowatt-hours of simulated energy, settling every trade as a real USDC on-chain transaction.

---

## Agent Fleet (10 Agents)

| Agent ID       | Type     | Role                                                                 |
|----------------|----------|----------------------------------------------------------------------|
| `solar-1`      | Solar    | 5 kW peak, dawn–dusk generation profile, sells surplus to consumers |
| `solar-2`      | Solar    | 3 kW peak, slightly offset solar curve                              |
| `solar-3`      | Solar    | 7 kW peak, highest output agent — primary price setter at noon       |
| `consumer-1`   | Consumer | Residential base load, flat 0.8 kW demand                          |
| `consumer-2`   | Consumer | Office load, 9am–6pm peak demand                                    |
| `consumer-3`   | Consumer | Industrial, 2 kW steady load                                        |
| `consumer-4`   | Consumer | EV charger, evening peak demand                                     |
| `consumer-5`   | Consumer | Variable demand, randomized each tick                               |
| `battery-1`    | Battery  | 10 kWh capacity, buys cheap at noon, sells during evening peak      |
| `battery-2`    | Battery  | 5 kWh capacity, reactive arbitrageur — follows price spreads        |

---

## Game Theory Mechanisms

### 1. Continuous Double Auction (CDA)
Each tick (~1 simulated hour), every agent submits a bid (consumers, batteries discharging) or ask (solar, batteries charging). The `GridEngine` sorts bids descending and asks ascending, then matches overlapping pairs. The clearing price is the midpoint of the last matched pair.

### 2. Shapley Value Coalition Analysis
Battery agents compute their marginal contribution to consumer surplus across all possible coalition subsets. This determines whether it is rational for a battery to participate in a coalition with specific solar + consumer combinations. Shapley values are recomputed every 5 ticks.

### 3. Schelling Point Coordination
When the grid is under stress (supply < demand), agents attempt to coordinate at a focal Schelling price — a psychologically salient level ($0.10/kWh) that acts as a natural equilibrium point without explicit communication. This is implemented via a commit-reveal scheme: agents commit a hash of their intended bid/ask, then reveal simultaneously in the next tick, preventing front-running.

### 4. Surge Pricing
When supply/demand imbalance exceeds a configurable threshold, the `SurgePricing` engine applies a multiplier (up to 3×) to the clearing price. Consumers with high elasticity reduce demand; battery agents activate to capture the spread.

### 5. Futures Contracts
Solar agents can pre-sell energy production 24 ticks in advance at a fixed strike price. This hedges against cloud cover (modeled as a stochastic reduction in the solar profile). Battery agents can take the other side of these futures, speculating on price direction.

---

## x402 Payment Flow

GridMint implements the [x402 HTTP payment protocol](https://github.com/coinbase/x402) for the `/api/economic-proof` premium endpoint:

1. Client GETs `/api/economic-proof` → server returns `402 Payment Required` with `X-Payment-Required` header containing amount, recipient, and nonce.
2. Client submits a USDC `transfer()` on Arc Testnet to the gateway wallet.
3. Client retries the request with `X-Payment-Proof: <tx_hash>` header.
4. Server calls `x402_paywall.verify_payment()` which: validates the tx hash format, checks the nonce against a replay-protection set, and (in `live` mode) verifies the transaction on-chain via Web3.
5. If valid, server returns the full economic proof data.

---

## On-Chain Settlement

Every matched energy trade is submitted as a real USDC ERC-20 `transfer()` on Arc Testnet:

- **Chain**: Arc Testnet (Chain ID: 5042002)
- **RPC**: `https://rpc.testnet.arc.network`
- **USDC Contract**: `0x3600000000000000000000000000000000000000`
- **Gateway Wallet**: `0x0077777d7EBA4688BDeF3E311b846F25870A19B9`
- **Explorer**: [testnet.arcscan.app](https://testnet.arcscan.app)

Arc gas costs ~$0.000002 per transaction vs. $2.47 on Ethereum — a **1,235,000× cost reduction** — making sub-cent energy micro-payments economically viable for the first time.

---

## Settlement Mode

Set `SETTLEMENT_MODE=live` in `.env` to enable real on-chain settlement.  
Set `SETTLEMENT_MODE=simulated` for demo mode (no actual transactions, but identical agent logic).

---

## API Audit Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Chain connectivity, block number, USDC contract verification |
| `GET /api/live-proof` | Downloadable JSON artifact of all tx hashes (verifiable offline) |
| `GET /api/settlement-log` | Raw settlement JSONL log from disk |
| `POST /api/grid/reset` | Reset grid to dawn (05:00), clear all state, auto-start |
| `GET /api/economic-proof` | x402-protected full economic analysis |
