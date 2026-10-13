from decimal import Decimal
from types import SimpleNamespace

from app.domain.walk_forward.metrics import window_degradation


def test_window_degradation_uses_m15_formula_and_keeps_null_sharpe():
    row = SimpleNamespace(
        train_annualized_return=Decimal("0.2"),
        oos_annualized_return=Decimal("0.08"),
        train_sharpe_ratio=Decimal("1.2"),
        oos_sharpe_ratio=Decimal("0.7"),
        train_max_drawdown_abs=Decimal("0.10"),
        oos_max_drawdown_abs=Decimal("0.15"),
        train_annualized_turnover=Decimal("3"),
        oos_annualized_turnover=Decimal("4.2"),
    )
    assert window_degradation(row) == {
        "return_degradation": Decimal("0.12"),
        "sharpe_degradation": Decimal("0.5"),
        "drawdown_worsening": Decimal("0.05"),
        "turnover_change": Decimal("1.2"),
    }
    row.oos_sharpe_ratio = None
    assert window_degradation(row)["sharpe_degradation"] is None
