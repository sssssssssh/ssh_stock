import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.core.performance_trade_config import PerformanceTradeConfig
from app.domain.performance.trade_contracts import (
    TradeDailyPoint,
    TradeEpisodeResult,
    TradeResult,
    TradeSourceFill,
    TradeSourcePosition,
    TradeSourceSnapshot,
)
from app.domain.performance.trade_statistics import mean, median

ZERO = Decimal("0")
MONEY_QUANTUM = Decimal("0.0001")
COST_QUANTUM = Decimal("0.00000001")


class TradeCalculationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class _EpisodeState:
    ts_code: str
    episode_no: int
    entry_date: date
    quantity: int = 0
    avg_cost: Decimal = ZERO
    buy_fill_count: int = 0
    sell_fill_count: int = 0
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0
    buy_gross_amount: Decimal = ZERO
    sell_gross_amount: Decimal = ZERO
    buy_cash_fee_total: Decimal = ZERO
    sell_cash_fee_total: Decimal = ZERO
    commission: Decimal = ZERO
    stamp_tax: Decimal = ZERO
    transfer_fee: Decimal = ZERO
    cash_fee_total: Decimal = ZERO
    slippage_cost: Decimal = ZERO
    total_execution_cost: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    total_buy_cash_cost: Decimal = ZERO
    sell_net_proceeds: Decimal = ZERO
    first_fill_id: uuid.UUID | None = None
    last_fill_id: uuid.UUID | None = None


class TradeEngine:
    def calculate(self, source: TradeSourceSnapshot, config: PerformanceTradeConfig) -> TradeResult:
        if source.trade_version != config.version:
            raise ValueError("trade config version does not match source identity")
        if (
            not source.dates
            or source.trade_days != len(source.dates)
            or tuple(row.trade_date for row in source.nav) != source.dates
        ):
            raise ValueError("trade source date set is invalid")

        with localcontext() as context:
            context.prec = 60
            date_indexes = {trade_date: index for index, trade_date in enumerate(source.dates)}
            fills_by_date = {trade_date: [] for trade_date in source.dates}
            for fill in source.fills:
                if fill.trade_date not in fills_by_date:
                    raise TradeCalculationError(
                        "TRADE_SOURCE_INCOMPLETE", "fill date is outside performance dates"
                    )
                fills_by_date[fill.trade_date].append(fill)
            positions_by_date: dict[date, dict[str, TradeSourcePosition]] = {
                trade_date: {} for trade_date in source.dates
            }
            for position in source.positions:
                if position.trade_date not in positions_by_date:
                    raise TradeCalculationError(
                        "TRADE_SOURCE_INCOMPLETE",
                        "position date is outside performance dates",
                    )
                positions_by_date[position.trade_date][position.ts_code] = position

            open_states: dict[str, _EpisodeState] = {}
            episode_numbers: dict[str, int] = {}
            closed_episodes: list[TradeEpisodeResult] = []
            daily: list[TradeDailyPoint] = []
            previous_total_assets: Decimal | None = None

            for trade_date, nav in zip(source.dates, source.nav, strict=True):
                day_fills = sorted(fills_by_date[trade_date], key=self._fill_sort_key)
                for fill in day_fills:
                    if fill.side == "SELL":
                        state = open_states.get(fill.ts_code)
                        if state is None or fill.quantity > state.quantity:
                            raise TradeCalculationError(
                                "TRADE_EPISODE_STATE_INVALID",
                                f"invalid sell replay for {fill.ts_code}",
                            )
                        self._apply_sell(state, fill)
                        if state.quantity == 0:
                            closed_episodes.append(
                                self._close_episode(
                                    state,
                                    exit_date=trade_date,
                                    date_indexes=date_indexes,
                                    epsilon=config.pnl_zero_epsilon_cny,
                                )
                            )
                            del open_states[fill.ts_code]
                    elif fill.side == "BUY":
                        state = open_states.get(fill.ts_code)
                        if state is None:
                            episode_no = episode_numbers.get(fill.ts_code, 0) + 1
                            episode_numbers[fill.ts_code] = episode_no
                            state = _EpisodeState(
                                ts_code=fill.ts_code,
                                episode_no=episode_no,
                                entry_date=trade_date,
                            )
                            open_states[fill.ts_code] = state
                        self._apply_buy(state, fill)
                    else:
                        raise TradeCalculationError(
                            "TRADE_EPISODE_STATE_INVALID",
                            f"unsupported fill side {fill.side}",
                        )

                self._validate_and_align_positions(
                    trade_date, open_states, positions_by_date[trade_date]
                )
                denominator = (
                    source.initial_cash if previous_total_assets is None else previous_total_assets
                )
                if denominator <= ZERO:
                    raise TradeCalculationError(
                        "TRADE_SOURCE_INCOMPLETE",
                        "turnover denominator must be positive",
                    )
                daily.append(self._daily_point(trade_date, day_fills, denominator))
                previous_total_assets = nav.total_assets

            final_positions = positions_by_date[source.end_date]
            open_episodes = [
                self._open_episode(
                    state,
                    final_positions[state.ts_code],
                    end_date=source.end_date,
                    date_indexes=date_indexes,
                )
                for state in sorted(
                    open_states.values(), key=lambda value: (value.entry_date, value.ts_code)
                )
            ]
            episodes = tuple(
                sorted(
                    [*closed_episodes, *open_episodes],
                    key=lambda value: (
                        value.entry_date,
                        value.ts_code,
                        value.episode_no,
                    ),
                )
            )
            return self._aggregate(source, config, tuple(daily), episodes)

    @staticmethod
    def _fill_sort_key(fill: TradeSourceFill) -> tuple[object, ...]:
        return (
            0 if fill.side == "SELL" else 1,
            fill.scheduled_trade_date,
            str(fill.order_id),
            str(fill.fill_id),
        )

    @staticmethod
    def _record_costs(state: _EpisodeState, fill: TradeSourceFill) -> None:
        state.commission += fill.commission
        state.stamp_tax += fill.stamp_tax
        state.transfer_fee += fill.transfer_fee
        state.cash_fee_total += fill.cash_fee_total
        state.slippage_cost += fill.slippage_cost
        state.total_execution_cost += fill.total_cost
        state.first_fill_id = state.first_fill_id or fill.fill_id
        state.last_fill_id = fill.fill_id

    def _apply_buy(self, state: _EpisodeState, fill: TradeSourceFill) -> None:
        old_basis = state.avg_cost * state.quantity
        buy_cash_cost = fill.gross_amount + fill.cash_fee_total
        new_quantity = state.quantity + fill.quantity
        state.avg_cost = (old_basis + buy_cash_cost) / Decimal(new_quantity)
        state.quantity = new_quantity
        state.buy_fill_count += 1
        state.total_buy_quantity += fill.quantity
        state.buy_gross_amount += fill.gross_amount
        state.buy_cash_fee_total += fill.cash_fee_total
        state.total_buy_cash_cost += buy_cash_cost
        self._record_costs(state, fill)

    def _apply_sell(self, state: _EpisodeState, fill: TradeSourceFill) -> None:
        sell_net_proceeds = fill.gross_amount - fill.cash_fee_total
        state.realized_pnl += sell_net_proceeds - state.avg_cost * fill.quantity
        state.quantity -= fill.quantity
        state.sell_fill_count += 1
        state.total_sell_quantity += fill.quantity
        state.sell_gross_amount += fill.gross_amount
        state.sell_cash_fee_total += fill.cash_fee_total
        state.sell_net_proceeds += sell_net_proceeds
        self._record_costs(state, fill)

    def _validate_and_align_positions(
        self,
        trade_date: date,
        states: dict[str, _EpisodeState],
        positions: dict[str, TradeSourcePosition],
    ) -> None:
        if set(states) != set(positions):
            raise TradeCalculationError(
                "TRADE_POSITION_REPLAY_MISMATCH",
                f"open position set mismatch on {trade_date}",
            )
        for ts_code, state in states.items():
            persisted = positions[ts_code]
            if (
                state.quantity != persisted.quantity
                or self._cost(state.avg_cost) != self._cost(persisted.avg_cost)
                or self._money(state.realized_pnl) != self._money(persisted.realized_pnl)
            ):
                raise TradeCalculationError(
                    "TRADE_POSITION_REPLAY_MISMATCH",
                    f"position ledger mismatch for {ts_code} on {trade_date}",
                )
            # M13 reopens the next day from the persisted, quantized snapshot.
            state.avg_cost = persisted.avg_cost
            state.realized_pnl = persisted.realized_pnl

    @staticmethod
    def _daily_point(
        trade_date: date,
        fills: list[TradeSourceFill],
        denominator: Decimal,
    ) -> TradeDailyPoint:
        buy = tuple(fill for fill in fills if fill.side == "BUY")
        sell = tuple(fill for fill in fills if fill.side == "SELL")
        buy_gross = sum((fill.gross_amount for fill in buy), ZERO)
        sell_gross = sum((fill.gross_amount for fill in sell), ZERO)
        traded = buy_gross + sell_gross
        return TradeDailyPoint(
            trade_date=trade_date,
            buy_fill_count=len(buy),
            sell_fill_count=len(sell),
            fill_count=len(fills),
            buy_gross_amount=buy_gross,
            sell_gross_amount=sell_gross,
            traded_gross_amount=traded,
            commission=sum((fill.commission for fill in fills), ZERO),
            stamp_tax=sum((fill.stamp_tax for fill in fills), ZERO),
            transfer_fee=sum((fill.transfer_fee for fill in fills), ZERO),
            cash_fee_total=sum((fill.cash_fee_total for fill in fills), ZERO),
            slippage_cost=sum((fill.slippage_cost for fill in fills), ZERO),
            total_execution_cost=sum((fill.total_cost for fill in fills), ZERO),
            turnover_denominator=denominator,
            daily_turnover=traded / denominator,
        )

    def _close_episode(
        self,
        state: _EpisodeState,
        *,
        exit_date: date,
        date_indexes: dict[date, int],
        epsilon: Decimal,
    ) -> TradeEpisodeResult:
        if state.realized_pnl > epsilon:
            classification = "WIN"
        elif state.realized_pnl < -epsilon:
            classification = "LOSS"
        else:
            classification = "BREAKEVEN"
        return self._episode_result(
            state,
            status="CLOSED",
            classification=classification,
            exit_date=exit_date,
            holding_trade_days=(date_indexes[exit_date] - date_indexes[state.entry_date] + 1),
            unrealized_pnl=ZERO,
            episode_return=state.realized_pnl / state.total_buy_cash_cost,
        )

    def _open_episode(
        self,
        state: _EpisodeState,
        final_position: TradeSourcePosition,
        *,
        end_date: date,
        date_indexes: dict[date, int],
    ) -> TradeEpisodeResult:
        return self._episode_result(
            state,
            status="OPEN",
            classification=None,
            exit_date=None,
            holding_trade_days=(date_indexes[end_date] - date_indexes[state.entry_date] + 1),
            unrealized_pnl=final_position.unrealized_pnl,
            episode_return=None,
        )

    @staticmethod
    def _episode_result(
        state: _EpisodeState,
        *,
        status: str,
        classification: str | None,
        exit_date: date | None,
        holding_trade_days: int,
        unrealized_pnl: Decimal,
        episode_return: Decimal | None,
    ) -> TradeEpisodeResult:
        if state.first_fill_id is None or state.last_fill_id is None:
            raise TradeCalculationError("TRADE_EPISODE_STATE_INVALID", "episode has no fills")
        return TradeEpisodeResult(
            ts_code=state.ts_code,
            episode_no=state.episode_no,
            status=status,
            classification=classification,
            entry_date=state.entry_date,
            exit_date=exit_date,
            holding_trade_days=holding_trade_days,
            buy_fill_count=state.buy_fill_count,
            sell_fill_count=state.sell_fill_count,
            fill_count=state.buy_fill_count + state.sell_fill_count,
            total_buy_quantity=state.total_buy_quantity,
            total_sell_quantity=state.total_sell_quantity,
            ending_quantity=state.quantity,
            buy_gross_amount=state.buy_gross_amount,
            sell_gross_amount=state.sell_gross_amount,
            buy_cash_fee_total=state.buy_cash_fee_total,
            sell_cash_fee_total=state.sell_cash_fee_total,
            commission=state.commission,
            stamp_tax=state.stamp_tax,
            transfer_fee=state.transfer_fee,
            cash_fee_total=state.cash_fee_total,
            slippage_cost=state.slippage_cost,
            total_execution_cost=state.total_execution_cost,
            realized_pnl=state.realized_pnl,
            unrealized_pnl_end=unrealized_pnl,
            mark_to_market_pnl_end=state.realized_pnl + unrealized_pnl,
            total_buy_cash_cost=state.total_buy_cash_cost,
            sell_net_proceeds=state.sell_net_proceeds,
            episode_return=episode_return,
            first_fill_id=state.first_fill_id,
            last_fill_id=state.last_fill_id,
        )

    def _aggregate(
        self,
        source: TradeSourceSnapshot,
        config: PerformanceTradeConfig,
        daily: tuple[TradeDailyPoint, ...],
        episodes: tuple[TradeEpisodeResult, ...],
    ) -> TradeResult:
        closed = tuple(item for item in episodes if item.status == "CLOSED")
        opened = tuple(item for item in episodes if item.status == "OPEN")
        warnings: set[str] = set()
        if source.trade_days < config.short_sample_warning_trade_days:
            warnings.add("TRADE_SHORT_SAMPLE")
        if not source.fills:
            warnings.add("NO_FILLS")
        if not closed:
            warnings.add("NO_CLOSED_EPISODES")
        if opened:
            warnings.add("OPEN_EPISODES_EXCLUDED_FROM_CLOSED_STATS")

        win_count = sum(item.classification == "WIN" for item in closed)
        loss_count = sum(item.classification == "LOSS" for item in closed)
        breakeven_count = sum(item.classification == "BREAKEVEN" for item in closed)
        gross_profit = sum((max(item.realized_pnl, ZERO) for item in closed), ZERO)
        gross_loss_abs = abs(sum((min(item.realized_pnl, ZERO) for item in closed), ZERO))
        win_rate = Decimal(win_count) / Decimal(len(closed)) if closed else None
        if win_count:
            average_win = gross_profit / Decimal(win_count)
        else:
            average_win = None
            warnings.add("ZERO_WIN_COUNT")
        if loss_count:
            average_loss = gross_loss_abs / Decimal(loss_count)
        else:
            average_loss = None
            warnings.add("ZERO_LOSS_COUNT")
        if gross_loss_abs <= config.pnl_zero_epsilon_cny:
            profit_factor = None
            warnings.add("ZERO_GROSS_LOSS")
        else:
            profit_factor = gross_profit / gross_loss_abs
        payoff_ratio = (
            average_win / average_loss
            if average_win is not None
            and average_loss is not None
            and average_loss > config.pnl_zero_epsilon_cny
            else None
        )

        traded = sum((item.traded_gross_amount for item in daily), ZERO)
        cash_fee = sum((item.cash_fee_total for item in daily), ZERO)
        total_cost = sum((item.total_execution_cost for item in daily), ZERO)
        if traded == ZERO:
            cost_to_traded = None
            warnings.add("ZERO_TRADED_GROSS_AMOUNT")
        else:
            cost_to_traded = total_cost / traded
        total_turnover = sum((item.daily_turnover for item in daily), ZERO)
        average_turnover = total_turnover / Decimal(source.trade_days)
        holding = tuple(Decimal(item.holding_trade_days) for item in closed)

        self._validate_reconciliation(source, daily, episodes)
        return TradeResult(
            start_date=source.start_date,
            end_date=source.end_date,
            trade_days=source.trade_days,
            order_count=len(source.orders),
            attempt_count=len(source.attempts),
            fill_count=len(source.fills),
            buy_fill_count=sum(item.buy_fill_count for item in daily),
            sell_fill_count=sum(item.sell_fill_count for item in daily),
            buy_gross_amount=sum((item.buy_gross_amount for item in daily), ZERO),
            sell_gross_amount=sum((item.sell_gross_amount for item in daily), ZERO),
            traded_gross_amount=traded,
            commission_total=sum((item.commission for item in daily), ZERO),
            stamp_tax_total=sum((item.stamp_tax for item in daily), ZERO),
            transfer_fee_total=sum((item.transfer_fee for item in daily), ZERO),
            cash_fee_total=cash_fee,
            slippage_cost_total=sum((item.slippage_cost for item in daily), ZERO),
            total_execution_cost=total_cost,
            cash_fee_to_initial_capital=cash_fee / source.initial_cash,
            total_cost_to_initial_capital=total_cost / source.initial_cash,
            total_cost_to_traded_amount=cost_to_traded,
            total_turnover=total_turnover,
            average_daily_turnover=average_turnover,
            annualized_turnover=(average_turnover * Decimal(source.annualization_trade_days)),
            closed_episode_count=len(closed),
            open_episode_count=len(opened),
            win_count=win_count,
            loss_count=loss_count,
            breakeven_count=breakeven_count,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss_abs=gross_loss_abs,
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss_abs=average_loss,
            payoff_ratio=payoff_ratio,
            best_episode_pnl=(max(item.realized_pnl for item in closed) if closed else None),
            worst_episode_pnl=(min(item.realized_pnl for item in closed) if closed else None),
            average_holding_trade_days=mean(holding) if holding else None,
            median_holding_trade_days=median(holding) if holding else None,
            closed_realized_pnl=sum((item.realized_pnl for item in closed), ZERO),
            open_realized_pnl_end=sum((item.realized_pnl for item in opened), ZERO),
            open_unrealized_pnl_end=sum((item.unrealized_pnl_end for item in opened), ZERO),
            open_mark_to_market_pnl_end=sum((item.mark_to_market_pnl_end for item in opened), ZERO),
            warnings=tuple(sorted(warnings)),
            daily=daily,
            episodes=episodes,
        )

    @staticmethod
    def _validate_reconciliation(
        source: TradeSourceSnapshot,
        daily: tuple[TradeDailyPoint, ...],
        episodes: tuple[TradeEpisodeResult, ...],
    ) -> None:
        daily_fill_count = sum(item.fill_count for item in daily)
        episode_fill_count = sum(item.fill_count for item in episodes)
        daily_cost = sum((item.total_execution_cost for item in daily), ZERO)
        episode_cost = sum((item.total_execution_cost for item in episodes), ZERO)
        daily_cash_fee = sum((item.cash_fee_total for item in daily), ZERO)
        episode_cash_fee = sum((item.cash_fee_total for item in episodes), ZERO)
        if (
            daily_fill_count != len(source.fills)
            or episode_fill_count != len(source.fills)
            or daily_cost != episode_cost
            or daily_cash_fee != episode_cash_fee
        ):
            raise TradeCalculationError(
                "TRADE_EPISODE_STATE_INVALID",
                "report, daily and episode facts do not reconcile",
            )

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _cost(value: Decimal) -> Decimal:
        return value.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)
