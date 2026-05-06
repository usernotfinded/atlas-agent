# Architecture

Flow: AI provider or deterministic strategy proposes a decision, signal parser validates it, risk manager checks the proposed order, approval manager handles live approvals, order router sends approved orders to a broker, audit logger records every decision.

AI providers never call broker adapters directly.

