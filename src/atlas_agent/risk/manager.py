# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/manager.py
# PURPOSE: Gate di rischio. Ogni ordine passa da qui prima di raggiungere un
#          broker: viene proiettato sul portafoglio (contando anche gli ordini
#          gia' in volo), confrontato coi limiti, e ne esce una RiskDecision
#          tracciata sull'audit log.
# DEPS:    atlas_agent.risk.limits (soglie), atlas_agent.risk.models (vocabolario),
#          atlas_agent.audit (traccia immutabile delle decisioni)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import math
from typing import Optional, List, Literal, Any, Tuple

from atlas_agent.audit import AuditWriter
from atlas_agent.risk.limits import RiskLimits, DEFAULT_RISK_LIMITS
from atlas_agent.risk.models import (
    RiskDecision,
    RiskViolation,
    PortfolioSnapshot,
    OrderRiskInput,
    OrderClassification,
    PendingOrder
)


# ==============================================================================
# RISK MANAGER
# ==============================================================================

class RiskManager:

    # --------------------------------------------------------------------------
    # Construction & configuration
    # --------------------------------------------------------------------------

    def __init__(
        self,
        limits: RiskLimits = DEFAULT_RISK_LIMITS,
        audit_writer: Optional[AuditWriter] = None,
        run_id: str = "unknown",
        iteration: Optional[int] = None,
        kill_switch_enabled: bool = False,
    ):
        self.limits = limits
        self.audit_writer = audit_writer
        self.run_id = run_id
        self.iteration = iteration
        self.kill_switch_enabled = kill_switch_enabled

    @classmethod
    def from_config(
        cls,
        config: Any,
        audit: Optional[Any] = None,
    ) -> RiskManager:
        """Legacy compatibility shim."""
        # La config legacy arriva a volte come dict, a volte come oggetto: questo
        # accessor uniforma i due casi invece di duplicare il ramo a ogni campo.
        def _get(obj, key, default):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        enable_live = _get(config, "enable_live_trading", False)

        limits = RiskLimits(
            max_position_notional=_get(config, "max_position_size", 1000.0),
            max_single_trade_notional=_get(config, "max_order_notional", 500.0),
            allowed_symbols=_get(config, "symbol_allowlist", None),
            blocked_symbols=_get(config, "symbol_blocklist", set()) or set(),
            live_trading_enabled=enable_live,
            # paper_only e' l'inverso di enable_live: il vecchio schema di config
            # aveva un flag solo, il modello nuovo ne vuole due coerenti.
            paper_only=not enable_live,
            minimum_confidence=_get(config, "minimum_confidence", 0.6),
            allow_shorting=_get(config, "allow_shorting", False),
        )
        return cls(limits=limits, kill_switch_enabled=_get(config, "kill_switch_enabled", False))

    # --------------------------------------------------------------------------
    # Legacy API — adatta oggetti "vecchio stile" al motore di valutazione
    # --------------------------------------------------------------------------

    def validate_order(
        self,
        order: Any,
        portfolio: Any,
        *,
        mode: str,
        market_price: float,
        market_is_open: bool = True,
    ) -> Any:
        """Legacy compatibility shim."""
        from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot

        # NOTA DEBITO: la classe LegacyDecision e' ridefinita 4 volte in questo
        # metodo (una per ramo di uscita). Duplicazione da consolidare in un
        # helper a livello di modulo; lasciata com'era per non toccare la logica
        # in un commit di sola documentazione.

        # 0. Validate quantity
        # `isinstance(x, bool)` va escluso esplicitamente perche' in Python bool
        # e' sottoclasse di int: senza questa guardia `quantity=True` passerebbe
        # come quantita' 1. `math.isfinite` esclude NaN/inf, che sfuggirebbero al
        # confronto `<= 0` (ogni confronto con NaN e' False).
        quantity = getattr(order, "quantity", None)
        if quantity is None or isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity <= 0:
            class LegacyDecision:
                def __init__(self, allowed, reasons):
                    self.allowed = allowed
                    self.reasons = reasons
            return LegacyDecision(False, ("order quantity must be a positive finite number", "invalid_quantity"))

        # 1. Determine reference price
        # Un limit order si valuta al suo limit price; un market order ha bisogno
        # di un prezzo di mercato, altrimenti il notional non e' calcolabile e
        # l'ordine va rifiutato invece che valutato su un numero inventato.
        limit_price = getattr(order, "limit_price", None)
        if limit_price is not None:
            if isinstance(limit_price, bool) or not isinstance(limit_price, (int, float)) or not math.isfinite(limit_price) or limit_price <= 0:
                class LegacyDecision:
                    def __init__(self, allowed, reasons):
                        self.allowed = allowed
                        self.reasons = reasons
                return LegacyDecision(False, ("limit price must be a positive finite number", "invalid_limit_price"))
            effective_price = limit_price
        else:
            if isinstance(market_price, bool) or not isinstance(market_price, (int, float)) or not math.isfinite(market_price) or market_price <= 0:
                class LegacyDecision:
                    def __init__(self, allowed, reasons):
                        self.allowed = allowed
                        self.reasons = reasons
                return LegacyDecision(False, ("Cannot evaluate notional for market order without reference price", "reference_price_required"))
            effective_price = market_price

        risk_input = OrderRiskInput(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=effective_price,
            notional=order.quantity * effective_price,
            leverage=getattr(order, "leverage", 1.0),
            confidence=getattr(order, "confidence", None),
            stop_loss=getattr(order, "stop_loss", None)
        )

        # Build portfolio snapshot from legacy portfolio state
        # Nei vecchi oggetti portafoglio alcuni campi sono attributi e altri
        # metodi (es. `equity()`): questo accessor li normalizza a valore.
        def _get_val(obj, attr, default):
            val = getattr(obj, attr, default)
            if callable(val):
                try:
                    return val(None) # type: ignore
                except TypeError:
                    return val()
            return val

        snapshot = PortfolioSnapshot(
            cash=_get_val(portfolio, "cash", 10000.0),
            equity=_get_val(portfolio, "equity", 10000.0),
            total_exposure=_get_val(portfolio, "exposure", 0.0),
            realized_pnl_today=_get_val(portfolio, "realized_pnl_today", 0.0),
            trades_today=_get_val(portfolio, "trades_today", 0)
        )

        decision = self.evaluate_order(risk_input, snapshot, mode=mode) # type: ignore

        # Adapt RiskDecision to legacy expectations
        class LegacyDecision:
            def __init__(self, allowed, reasons):
                self.allowed = allowed
                self.reasons = reasons

        reasons = [v.message for v in decision.violations]
        # Un rifiuto senza violazioni esplicite non deve arrivare al chiamante
        # legacy con `reasons` vuoto: resterebbe senza spiegazione del blocco.
        if not decision.allowed and not reasons:
            reasons = [decision.reason or "Risk rejection"]

        return LegacyDecision(decision.allowed, tuple(reasons))

    # --------------------------------------------------------------------------
    # Projection engine — dove finisce il portafoglio se l'ordine passa
    # --------------------------------------------------------------------------

    def _calculate_projection(
        self,
        order: OrderRiskInput,
        portfolio: PortfolioSnapshot
    ) -> dict[str, Any]:
        symbol = order.symbol.upper()
        current_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)

        current_qty = current_pos.quantity if current_pos else 0.0
        order_qty_delta = order.quantity if order.side == "buy" else -order.quantity

        # Identify active pending orders
        # Solo gli ordini ancora vivi consumano rischio. Cancellati/riempiti/
        # rifiutati sono gia' riflessi nella posizione o non lo saranno mai.
        active_statuses = {"pending", "open", "partially_filled"}
        pending_orders = [o for o in portfolio.open_orders if o.symbol == symbol and o.status in active_statuses]

        pending_qty_delta = sum((o.remaining_quantity if o.side == "buy" else -o.remaining_quantity) for o in pending_orders)

        # Due scenari a confronto:
        #  - `projected_*`              : solo posizione corrente + questo ordine
        #  - `projected_*_with_pending` : conta anche gli ordini gia' in volo
        # I limiti si applicano al secondo. Ignorare il pending permetterebbe di
        # sforare qualunque soglia spezzando l'ordine in tranche piu' piccole.
        baseline_projected_qty = current_qty + pending_qty_delta

        projected_qty = current_qty + order_qty_delta
        projected_qty_with_pending = baseline_projected_qty + order_qty_delta

        # Esposizione in valore assoluto: short e long impegnano capitale allo
        # stesso modo dal punto di vista dei limiti di size.
        projected_exposure = abs(projected_qty * order.price)
        projected_exposure_with_pending = abs(projected_qty_with_pending * order.price)

        # Classification relative to current position
        classification: OrderClassification = "unknown"
        if current_qty == 0:
            classification = "opens_new_position"
        elif projected_qty == 0:
            classification = "closes_position"
        elif (current_qty > 0 and projected_qty < 0) or (current_qty < 0 and projected_qty > 0):
            # Cambio di segno: chiude e riapre dal lato opposto in un colpo solo.
            classification = "flips_position"
        elif abs(projected_qty) > abs(current_qty):
            classification = "increases_risk"
        else:
            classification = "reduces_risk"

        # Classification relative to pending baseline
        # Stessa domanda ("sto aumentando il rischio?") ma misurata rispetto alla
        # baseline che include gli ordini in volo, non rispetto alla sola posizione.
        is_increasing_risk_with_pending = False
        if baseline_projected_qty == 0:
            is_increasing_risk_with_pending = (projected_qty_with_pending != 0)
        elif abs(projected_qty_with_pending) > abs(baseline_projected_qty):
            is_increasing_risk_with_pending = True
        elif (baseline_projected_qty > 0 and projected_qty_with_pending < 0) or (baseline_projected_qty < 0 and projected_qty_with_pending > 0):
            is_increasing_risk_with_pending = True

        return {
            "classification": classification,
            "is_increasing_risk_with_pending": is_increasing_risk_with_pending,
            "current_quantity": current_qty,
            "pending_quantity_delta": pending_qty_delta,
            "proposed_quantity_delta": order_qty_delta,
            "projected_quantity": projected_qty,
            "projected_quantity_with_pending": projected_qty_with_pending,
            "projected_exposure": projected_exposure,
            "projected_exposure_with_pending": projected_exposure_with_pending,
            "included_pending_order_ids": [o.order_id for o in pending_orders],
            # Gli ordini scartati vengono comunque elencati: senza questo, un bug
            # nel filtro degli stati sarebbe invisibile in fase di audit.
            "ignored_pending_order_ids": [o.order_id for o in portfolio.open_orders if o.symbol == symbol and o.status not in active_statuses]
        }

    # --------------------------------------------------------------------------
    # Core evaluation — il gate vero e proprio
    # --------------------------------------------------------------------------

    def evaluate_order(
        self,
        order: OrderRiskInput,
        portfolio: PortfolioSnapshot,
        mode: Literal["paper", "live"] = "paper",
    ) -> RiskDecision:

        # === FASE 1: sanity check sugli input ===
        # Come in validate_order: `bool` va escluso a mano (e' sottoclasse di int)
        # e NaN/inf vanno intercettati con isfinite, perche' `NaN <= 0` e' False e
        # passerebbe indisturbato fino al broker.
        if isinstance(order.quantity, bool) or not isinstance(order.quantity, (int, float)) or not math.isfinite(order.quantity) or order.quantity <= 0:
            return RiskDecision(
                allowed=False,
                status="blocked",
                reason="order quantity must be a positive finite number",
                violations=[RiskViolation(
                    rule="invalid_quantity",
                    message="order quantity must be a positive finite number",
                    limit_value="positive finite",
                    actual_value=order.quantity,
                )],
                classification="unknown",
                diagnostics={},
            )
        if isinstance(order.price, bool) or not isinstance(order.price, (int, float)) or not math.isfinite(order.price) or order.price <= 0:
            return RiskDecision(
                allowed=False,
                status="blocked",
                reason="order price must be a positive finite number",
                violations=[RiskViolation(
                    rule="invalid_price",
                    message="order price must be a positive finite number",
                    limit_value="positive finite",
                    actual_value=order.price,
                )],
                classification="unknown",
                diagnostics={},
            )

        # === FASE 2: proiezione dell'effetto sull'ordine ===
        projection = self._calculate_projection(order, portfolio)
        classification = projection["classification"]
        projected_qty_with_pending = projection["projected_quantity_with_pending"]
        projected_exposure_with_pending = projection["projected_exposure_with_pending"]
        is_increasing_risk_with_pending = projection["is_increasing_risk_with_pending"]

        # L'audit registra l'inizio valutazione *prima* dell'esito: se il processo
        # muore a meta', resta comunque traccia che l'ordine e' stato considerato.
        if self.audit_writer:
            self.audit_writer.write_event(
                "risk_evaluation_started",
                run_id=self.run_id,
                iteration=self.iteration,
                tool_name="risk_manager",
                payload={
                    "order": order.model_dump(),
                    "portfolio": portfolio.model_dump(),
                    "mode": mode,
                    "projection": projection
                }
            )

        # === FASE 3: raccolta violazioni ===
        # Le regole non fanno short-circuit: si raccolgono TUTTE le violazioni
        # invece di fermarsi alla prima, cosi' chi legge l'audit vede l'intero
        # quadro dei motivi di blocco e non deve iterare a colpi di tentativi.
        violations: List[RiskViolation] = []
        symbol = order.symbol.upper()

        # --- 0. Kill switch (ha precedenza su tutto) ---
        if self.kill_switch_enabled:
            violations.append(RiskViolation(
                rule="kill_switch",
                message="kill switch is enabled",
                limit_value=False,
                actual_value=True
            ))

        # --- 1. Gate live/paper ---
        # Entrambi i flag vengono controllati: sono due lucchetti indipendenti,
        # vedi la nota su RiskLimits in limits.py.
        if mode == "live":
            if self.limits.paper_only:
                violations.append(RiskViolation(
                    rule="paper_only",
                    message="Live trading is blocked (paper_only=True)",
                    limit_value=True,
                    actual_value=True
                ))
            if not self.limits.live_trading_enabled:
                violations.append(RiskViolation(
                    rule="live_trading_enabled",
                    message="ENABLE_LIVE_TRADING must be true",
                    limit_value=True,
                    actual_value=False
                ))

        # --- 2. Universo strumenti ---
        # `is not None` e' voluto: allowlist vuota = nessun simbolo consentito,
        # allowlist assente (None) = tutti consentiti.
        if self.limits.allowed_symbols is not None and symbol not in self.limits.allowed_symbols:
            violations.append(RiskViolation(
                rule="allowed_symbols",
                message=f"symbol is not allowlisted",
                limit_value=list(self.limits.allowed_symbols) if self.limits.allowed_symbols else [],
                actual_value=symbol
            ))

        if symbol in self.limits.blocked_symbols:
            violations.append(RiskViolation(
                rule="blocked_symbols",
                message=f"symbol is blocklisted",
                limit_value=list(self.limits.blocked_symbols),
                actual_value=symbol
            ))

        # --- 3. Policy di shorting ---
        # Si guarda alla proiezione *con pending*: un ordine puo' sembrare
        # innocuo rispetto alla posizione corrente e portare comunque il netto in
        # short una volta contati gli ordini gia' in volo. Vietiamo solo se il
        # netto short *peggiora*: chiudere uno short esistente resta permesso.
        if not self.limits.allow_shorting:
            if projected_qty_with_pending < 0:
                if is_increasing_risk_with_pending:
                    violations.append(RiskViolation(
                        rule="allow_shorting",
                        message="shorting is disabled",
                        limit_value=False,
                        actual_value=True
                    ))

        # --- 4. Limiti dimensionali (solo se il rischio aumenta) ---
        # Esenzione deliberata: se l'ordine riduce il rischio assoluto SIA rispetto
        # alla posizione corrente SIA rispetto alla baseline con pending, salta i
        # limiti di size. Altrimenti un portafoglio gia' oltre soglia resterebbe
        # incastrato, incapace di ridurre l'esposizione proprio quando serve.
        is_reducing_current = classification in ["reduces_risk", "closes_position"]
        is_reducing_pending = not is_increasing_risk_with_pending

        should_check_limits = not (is_reducing_current and is_reducing_pending)

        if should_check_limits:
            # Single trade limits (always check for new orders)
            if order.notional > self.limits.max_single_trade_notional:
                violations.append(RiskViolation(
                    rule="max_single_trade_notional",
                    message=f"max order notional exceeded",
                    limit_value=self.limits.max_single_trade_notional,
                    actual_value=order.notional
                ))

            # Position limits (including pending)
            if projected_exposure_with_pending > self.limits.max_position_notional:
                violations.append(RiskViolation(
                    rule="max_position_notional",
                    message=f"max position size exceeded (including pending orders)",
                    limit_value=self.limits.max_position_notional,
                    actual_value=projected_exposure_with_pending
                ))

            # Symbol exposure % check
            # Guardia su equity > 0: con equity nulla o negativa la percentuale
            # non ha significato (e dividerebbe per zero).
            if portfolio.equity > 0:
                exposure_pct = projected_exposure_with_pending / portfolio.equity
                if exposure_pct > self.limits.max_symbol_exposure_pct:
                    violations.append(RiskViolation(
                        rule="max_symbol_exposure_pct",
                        message=f"symbol exposure {exposure_pct:.1%} exceeds limit {self.limits.max_symbol_exposure_pct:.1%}",
                        limit_value=self.limits.max_symbol_exposure_pct,
                        actual_value=exposure_pct
                    ))

            # Portfolio exposure limits
            # Si sottrae l'esposizione attuale del simbolo e si somma quella
            # proiettata: sommare e basta conterebbe due volte il simbolo su cui
            # stiamo operando, gonfiando il totale.
            current_symbol_exposure = 0.0
            current_pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
            if current_pos:
                current_symbol_exposure = current_pos.notional

            projected_total_exposure = portfolio.total_exposure - current_symbol_exposure + projected_exposure_with_pending

            max_exposure_abs = portfolio.equity * self.limits.max_portfolio_exposure_pct
            if projected_total_exposure > max_exposure_abs:
                violations.append(RiskViolation(
                    rule="max_portfolio_exposure_pct",
                    message=f"max portfolio exposure exceeded",
                    limit_value=max_exposure_abs,
                    actual_value=projected_total_exposure
                ))

            # Max open positions
            # Il conteggio unisce posizioni aperte e simboli con ordini in volo:
            # altrimenti si potrebbero piazzare N ordini su N simboli nuovi tutti
            # insieme, ognuno legittimo, sforando il limite in aggregato.
            if classification == "opens_new_position":
                symbols_with_positions = {p.symbol for p in portfolio.positions}
                symbols_with_pending = {o.symbol for o in portfolio.open_orders if o.status in {"pending", "open", "partially_filled"}}
                unique_symbols = symbols_with_positions | symbols_with_pending

                # `symbol not in unique_symbols`: aggiungere size a un simbolo gia'
                # contato non apre una nuova posizione, quindi non consuma slot.
                if len(unique_symbols) >= self.limits.max_open_positions and symbol not in unique_symbols:
                    violations.append(RiskViolation(
                        rule="max_open_positions",
                        message=f"max open positions reached",
                        limit_value=self.limits.max_open_positions,
                        actual_value=len(unique_symbols)
                    ))

        # --- 5. Confidenza del modello (vale sempre, anche in riduzione) ---
        if order.confidence is not None and order.confidence < self.limits.minimum_confidence:
             violations.append(RiskViolation(
                rule="minimum_confidence",
                message=f"confidence below minimum threshold",
                limit_value=self.limits.minimum_confidence,
                actual_value=order.confidence
            ))

        # --- 6. Stop loss obbligatorio in live ---
        if mode == "live" and self.limits.require_stop_loss_live and order.stop_loss is None:
            violations.append(RiskViolation(
                rule="require_stop_loss_live",
                message="stop loss required for live mode",
                limit_value=True,
                actual_value=None
            ))

        # === FASE 4: esito ===
        diagnostics = projection.copy()

        if violations:
            # --- Bloccato ---
            decision = RiskDecision(
                allowed=False,
                status="blocked",
                reason="Risk violations detected",
                violations=violations,
                classification=classification,
                projected_quantity=projection["projected_quantity"],
                projected_exposure=projection["projected_exposure"],
                projected_quantity_with_pending=projected_qty_with_pending,
                projected_exposure_with_pending=projected_exposure_with_pending,
                diagnostics=diagnostics
            )
            if self.audit_writer:
                self.audit_writer.write_event(
                    "risk_evaluation_blocked",
                    run_id=self.run_id,
                    iteration=self.iteration,
                    tool_name="risk_manager",
                    status="blocked",
                    payload=decision.model_dump()
                )
        else:
            if mode == "live":
                # --- Passato il rischio, ma in live serve comunque l'uomo ---
                # allowed=True + requires_approval: il rischio e' a posto, manca
                # solo l'autorizzazione umana. Chi consuma la decisione NON deve
                # trattare allowed=True come "manda al broker" quando lo status
                # e' requires_approval.
                decision = RiskDecision(
                    allowed=True,
                    status="requires_approval",
                    reason="Live order requires manual approval",
                    classification=classification,
                    projected_quantity=projection["projected_quantity"],
                    projected_exposure=projection["projected_exposure"],
                    projected_quantity_with_pending=projected_qty_with_pending,
                    projected_exposure_with_pending=projected_exposure_with_pending,
                    diagnostics=diagnostics
                )
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "risk_evaluation_requires_approval",
                        run_id=self.run_id,
                        iteration=self.iteration,
                        tool_name="risk_manager",
                        status="requires_approval",
                        payload=decision.model_dump()
                    )
            else:
                # --- Paper: via libera piena ---
                decision = RiskDecision(
                    allowed=True,
                    status="allowed",
                    reason="All risk checks passed",
                    classification=classification,
                    projected_quantity=projection["projected_quantity"],
                    projected_exposure=projection["projected_exposure"],
                    projected_quantity_with_pending=projected_qty_with_pending,
                    projected_exposure_with_pending=projected_exposure_with_pending,
                    diagnostics=diagnostics
                )
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "risk_evaluation_allowed",
                        run_id=self.run_id,
                        iteration=self.iteration,
                        tool_name="risk_manager",
                        status="allowed",
                        payload=decision.model_dump()
                    )

        return decision
