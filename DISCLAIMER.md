# Disclaimer

## 1. No Financial Advice
Atlas Agent is software tooling designed for autonomous trading research and execution. It is **not** a financial advisor. **No returns are guaranteed.** Nothing contained in this repository, documentation, prompts, model outputs, reports, dashboard, backtests, or generated action plans constitutes financial, investment, tax, legal, or accounting advice. All information is provided for educational and research purposes only. Users must make their own independent decisions or consult with qualified professionals before making any financial commitments.

## 2. Trading Risk
Trading financial instruments involves significant risk and can result in the **partial or total loss of capital**. Markets are inherently volatile, unpredictable, and subject to rapid changes. AI-generated analysis and autonomous decisions can be wrong, incomplete, stale, biased, or misleading. You are solely responsible for your trades, broker configurations, API credentials, leverage, margin, position sizing, and regulatory compliance.

## 3. AI and Automation Limitations
Large Language Models (LLMs) and autonomous agents can hallucinate, misunderstand context, call tools incorrectly, or produce invalid reasoning. Model outputs may vary significantly across different providers and versions. While Atlas Agent includes deterministic guardrails to reduce operational risk, these systems cannot guarantee correctness, profitability, safety, or compliance.

## 4. Backtesting Disclaimer
Backtesting is a local, deterministic simulation based on historical data. It **does not execute real trades**. Historical performance is no guarantee of future results. Backtest outcomes depend heavily on data quality, underlying assumptions, slippage, commissions, fill models, and risk settings. Simple strategies, such as buy-and-hold baselines, are for comparative research and are not investment recommendations.

## 5. Paper Trading Disclaimer
Paper trading is a simulation of market conditions. Paper results may differ significantly from live execution due to factors such as liquidity, bid-ask spreads, latency, slippage, broker-specific behavior, order rejection, exchange fees, and market impact. Success in paper trading does not imply success in live trading.

## 6. Live Trading Disclaimer
Live trading is **disabled by default** and requires explicit configuration. If you choose to enable live trading, you accept full responsibility for all resulting orders, fills, losses, fees, and operational failures. It is strongly recommended to start with small position sizes, strict risk limits, and constant independent monitoring. Atlas Agent should not be left unattended with live trading enabled unless you fully understand and accept the associated risks.

## 7. Risk, Safety, and Kill-Switch Disclaimer
The `RiskManager`, global kill switch, dead-man heartbeat, approval gates, and safety action plans are safeguards, not guarantees. These systems may fail to protect your capital due to software bugs, stale broker data, incorrect configuration, network latency, broker API outages, or user overrides. You remain responsible for maintaining independent monitoring and performing emergency interventions when necessary.

## 8. Audit Disclaimer
Atlas Agent audit logs are designed to be **tamper-evident**. Hash-chains, run manifests, and root hashes help detect modification or tail deletion when verified correctly. However, they are **not immune to total compromise** if an attacker can rewrite both logs and manifests or compromise the underlying local system. Audit logs are provided for traceability and debugging, not for legal or regulatory certification.

## 9. Data and Provider Disclaimer
Market data, broker account state, research data, and AI model outputs may be delayed, incomplete, inaccurate, or unavailable. Atlas Agent's provider-neutral architecture does not imply an endorsement of any specific AI backend or broker. You are responsible for complying with the terms of service of all data providers, model providers, and brokers you utilize.

## 10. Security Disclaimer
You are responsible for protecting your API keys, tokens, broker credentials, local machines, cloud deployments, and your `.env.atlas` file. While Atlas Agent attempts to redact secrets from logs and the dashboard, you should review all configurations and logs before sharing them. **Never commit real secrets or live broker credentials to a repository.**

## 11. No Warranty
The software is provided **"as is"** and **"as available"**, without warranty of any kind, express or implied. This includes, but is not limited to, warranties of profitability, availability, accuracy, reliability, merchantability, fitness for a particular purpose, or non-infringement.

## 12. Limitation of Liability
In no event shall the maintainers, contributors, or authors of Atlas Agent be liable for any trading losses, missed opportunities, data errors, model errors, system outages, software bugs, security incidents, regulatory issues, or any other damages (including, but not limited to, direct, indirect, incidental, or consequential damages) arising from the use of or inability to use this software.

## 13. User Responsibility
By using Atlas Agent, you acknowledge and accept these risks in their entirety. If you do not fully understand these risks or are not prepared to accept them, you should not use this software for live trading.
