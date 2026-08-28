from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    severity: str = "ERROR"


def check_raw_daily(df: pd.DataFrame, min_rows: int = 1000) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if df.empty:
        return [QualityIssue("DAILY_EMPTY", "stock daily data is empty")]

    required = {"trade_date", "ts_code", "open", "high", "low", "close", "vol", "amount"}
    missing = required - set(df.columns)
    if missing:
        issues.append(QualityIssue("DAILY_MISSING_COLUMNS", ",".join(sorted(missing))))
        return issues

    if len(df.index) < min_rows:
        issues.append(
            QualityIssue("DAILY_LOW_ROW_COUNT", f"row_count={len(df.index)} min_rows={min_rows}")
        )

    duplicated = df.duplicated(subset=["trade_date", "ts_code"]).sum()
    if duplicated:
        issues.append(QualityIssue("DAILY_DUPLICATED_PK", f"duplicated={duplicated}"))

    ohlc_bad = df[
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
    ]
    if not ohlc_bad.empty:
        issues.append(QualityIssue("DAILY_INVALID_OHLC", f"rows={len(ohlc_bad.index)}"))

    negative_volume = df[(df["vol"] < 0) | (df["amount"] < 0)]
    if not negative_volume.empty:
        issues.append(QualityIssue("DAILY_NEGATIVE_VOLUME", f"rows={len(negative_volume.index)}"))

    return issues

