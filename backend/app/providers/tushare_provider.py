from collections.abc import Callable
from datetime import date
from time import perf_counter
from typing import Any

import pandas as pd
from loguru import logger
from requests.exceptions import RequestException
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.providers.rate_limiter import wait_for_rate_limit


def to_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _compact_error(exc: Exception, max_length: int = 800) -> str:
    message = " ".join(str(exc).split())
    if len(message) <= max_length:
        return message
    return f"{message[:max_length]}..."


def _configure_tushare_http_url(pro: Any, http_url: str) -> None:
    attribute = "_DataApi__http_url"
    if not hasattr(pro, attribute):
        raise RuntimeError(
            "Tushare SDK is incompatible with the configured proxy: "
            f"missing private attribute {attribute}; installed SDK structure changed"
        )
    setattr(pro, attribute, http_url)


_PERMANENT_PROVIDER_ERRORS = (
    "token invalid",
    "invalid token",
    "permission denied",
    "invalid parameter",
    "积分不足",
    "无权限",
)
_TRANSIENT_PROVIDER_ERRORS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "unexpected_eof_while_reading",
    "max retries exceeded",
    "temporarily unavailable",
    "frequency limit",
    "频率",
)


def _is_retryable_provider_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if any(marker in message for marker in _PERMANENT_PROVIDER_ERRORS):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, RequestException)):
        return True
    return any(marker in message for marker in _TRANSIENT_PROVIDER_ERRORS)


class TushareProvider:
    provider_name = "tushare"

    def __init__(
        self,
        token: str | None = None,
        http_url: str | None = None,
        min_interval_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self._token = (token or settings.tushare_token or "").strip().strip("'\"")
        if not self._token or self._token == "replace_me":
            raise RuntimeError("TUSHARE_TOKEN is required and must be provided by environment")
        self._http_url = (http_url or settings.tushare_http_url or "").strip().strip("'\"")
        configured_interval = (
            settings.tushare_min_interval_seconds
            if min_interval_seconds is None
            else min_interval_seconds
        )
        self._min_interval_seconds = max(0.0, float(configured_interval))
        self._safe_limits = settings.strategy.get("provider", {}).get("tushare", {}).get(
            "safe_limits", {}
        )

        import tushare as ts

        ts.set_token(self._token)
        self._pro = ts.pro_api()
        if self._http_url:
            _configure_tushare_http_url(self._pro, self._http_url)

    def _wait_for_rate_limit(self, api_name: str) -> None:
        wait_for_rate_limit(self.provider_name, api_name, self._min_interval_seconds)

    @retry(
        retry=retry_if_exception(_is_retryable_provider_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    def _call(
        self, api_name: str, log_trade_date: date | None = None, **kwargs: Any
    ) -> pd.DataFrame:
        api: Callable[..., pd.DataFrame] = getattr(self._pro, api_name)
        self._wait_for_rate_limit(api_name)
        started = perf_counter()
        try:
            df = api(**kwargs)
        except Exception:
            logger.error(
                "provider call failed provider={} api={} trade_date={}",
                self.provider_name,
                api_name,
                log_trade_date,
            )
            raise
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "provider call provider={} api={} trade_date={} rows={} elapsed_ms={}",
            self.provider_name,
            api_name,
            log_trade_date.isoformat() if log_trade_date else None,
            len(df.index) if df is not None else 0,
            elapsed_ms,
        )
        result = df if df is not None else pd.DataFrame()
        self._mark_possible_truncation(api_name, result)
        return result

    def _mark_possible_truncation(self, api_name: str, df: pd.DataFrame) -> None:
        if df.empty or not isinstance(self._safe_limits, dict):
            return
        safe_limit = self._safe_limits.get(api_name)
        if safe_limit is None:
            return
        row_count = len(df.index)
        if row_count < int(safe_limit):
            return
        df.attrs["provider_warning"] = "POSSIBLE_TRUNCATION"
        df.attrs["provider_warning_message"] = (
            f"{api_name} returned {row_count} rows, safe_limit={safe_limit}"
        )
        logger.warning(
            "provider possible truncation provider={} api={} rows={} safe_limit={}",
            self.provider_name,
            api_name,
            row_count,
            safe_limit,
        )

    def get_trade_calendar(self, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "trade_cal",
            start_date=to_tushare_date(start),
            end_date=to_tushare_date(end),
            exchange="SSE",
        )

    def get_stock_basic(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        fetched_statuses: set[str] = set()
        warnings: list[str] = []
        source_errors: dict[str, str] = {}
        fields = (
            "ts_code,symbol,name,area,industry,market,exchange,list_status,"
            "list_date,delist_date,is_hs"
        )
        for status in ("L", "D", "P"):
            status_frames: list[pd.DataFrame] = []
            status_failed = False
            for exchange in ("SSE", "SZSE", "BSE"):
                shard = f"{status}/{exchange}"
                try:
                    df = self._call(
                        "stock_basic",
                        list_status=status,
                        exchange=exchange,
                        fields=fields,
                    )
                except Exception as exc:
                    source_errors[shard] = _compact_error(exc)
                    status_failed = True
                    logger.warning("stock_basic shard={} failed: {}", shard, exc)
                    continue
                if warning := df.attrs.get("provider_warning"):
                    warnings.append(f"{shard}:{warning}")
                if not df.empty:
                    status_frames.append(df)
            if status_frames:
                frames.extend(status_frames)
            if not status_failed and status_frames:
                fetched_statuses.add(status)
        missing_required = {"L", "D"} - fetched_statuses
        if missing_required:
            details = "; ".join(
                _stock_basic_status_error(status, source_errors)
                for status in sorted(missing_required)
            )
            raise RuntimeError(
                f"stock_basic required statuses missing: {sorted(missing_required)}; "
                f"stock_basic source errors: {details}"
            )
        result = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts_code"])
        if warnings:
            result.attrs["provider_warning"] = "POSSIBLE_TRUNCATION"
            result.attrs["provider_warning_message"] = "; ".join(warnings)
        return result

    def get_daily(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "daily",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields=(
                "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
            ),
        )

    def get_daily_range(self, ts_code: str, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "daily",
            ts_code=ts_code,
            start_date=to_tushare_date(start),
            end_date=to_tushare_date(end),
            fields=(
                "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
            ),
        )

    def get_adj_factor(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "adj_factor",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields="ts_code,trade_date,adj_factor",
        )

    def get_daily_basic(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "daily_basic",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields=(
                "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
                "pe,pe_ttm,pb,ps,ps_ttm,total_share,float_share,free_share,total_mv,circ_mv"
            ),
        )

    def get_index_daily(self, trade_date: date, codes: list[str]) -> pd.DataFrame:
        frames = [
            self._call(
                "index_daily",
                log_trade_date=trade_date,
                ts_code=code,
                trade_date=to_tushare_date(trade_date),
                fields=(
                    "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount"
                ),
            )
            for code in codes
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_index_daily_range(self, ts_code: str, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "index_daily",
            ts_code=ts_code,
            start_date=to_tushare_date(start),
            end_date=to_tushare_date(end),
            fields=(
                "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount"
            ),
        )

    def get_stock_st(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "stock_st",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields="trade_date,ts_code,name,type,type_name",
        )

    def get_suspend_daily(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "suspend_d",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields="ts_code,trade_date,suspend_type,suspend_timing",
        )

    def get_stock_limit(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "stk_limit",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields=(
                "trade_date,ts_code,pre_close,up_limit,down_limit,asset_type,exchange"
            ),
        )

    def get_sector_classification(self) -> pd.DataFrame:
        return self._call("index_classify", src="SW2021")

    def get_sector_members(self) -> pd.DataFrame:
        classification = self.get_sector_classification()
        l1_codes = _sector_l1_codes(classification)
        if not l1_codes:
            raise RuntimeError("sector_member batch fetch failed: no L1 sector codes")

        frames: list[pd.DataFrame] = []
        errors: list[str] = []
        for l1_code in l1_codes:
            for is_new in ("Y", "N"):
                try:
                    batches = self._get_sector_member_batches(
                        classification,
                        l1_code,
                        is_new,
                    )
                except Exception as exc:
                    errors.append(f"{l1_code}/{is_new}: {_compact_error(exc)}")
                    continue
                if not batches and is_new == "Y":
                    errors.append(
                        "sector_member current batch empty: "
                        f"l1_code={l1_code} is_new={is_new}"
                    )
                    continue
                for df in batches:
                    if "l1_code" not in df.columns:
                        df = df.copy()
                        df["l1_code"] = l1_code
                    if "is_new" not in df.columns:
                        df = df.copy()
                        df["is_new"] = is_new
                    frames.append(df)
        if errors:
            raise RuntimeError(
                "sector_member batch fetch failed: " + "; ".join(errors[:20])
            )
        if not frames:
            return pd.DataFrame()
        return _deduplicate_sector_members(pd.concat(frames, ignore_index=True))

    def get_ths_concepts(self) -> pd.DataFrame:
        return self._call(
            "ths_index",
            exchange="A",
            type="N",
            fields="ts_code,name,count,exchange,list_date,type",
        )

    def get_ths_concept_members(self, concept_codes: list[str]) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for code in concept_codes:
            frame = self._call(
                "ths_member",
                ts_code=code,
                fields="ts_code,con_code,con_name,weight,in_date,out_date,is_new",
            )
            if frame.attrs.get("provider_warning"):
                raise RuntimeError(f"ths_member POSSIBLE_TRUNCATION theme_code={code}")
            required = {"ts_code", "con_code"}
            if not required <= set(frame.columns):
                raise RuntimeError(
                    f"ths_member schema invalid theme_code={code} "
                    f"missing={sorted(required - set(frame.columns))}"
                )
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_ths_daily(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "ths_daily",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields=(
                "ts_code,trade_date,open,high,low,close,pre_close,avg_price,change,"
                "pct_change,vol,turnover_rate,total_mv"
            ),
        )

    def get_ths_concept_moneyflow(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "moneyflow_cnt_ths",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields=(
                "trade_date,ts_code,name,lead_stock,close_price,pct_change,industry_index,"
                "company_num,pct_change_stock,net_buy_amount,net_sell_amount,net_amount"
            ),
        )

    def get_limit_concept_list(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "limit_cpt_list",
            log_trade_date=trade_date,
            trade_date=to_tushare_date(trade_date),
            fields="ts_code,name,trade_date,days,up_stat,cons_nums,up_nums,pct_chg,rank",
        )

    def _get_sector_member_batches(
        self,
        classification: pd.DataFrame,
        l1_code: str,
        is_new: str,
    ) -> list[pd.DataFrame]:
        initial = self._call("index_member_all", l1_code=l1_code, is_new=is_new)
        if not initial.attrs.get("provider_warning"):
            return [] if initial.empty else [initial]

        l2_codes = _sector_child_codes(classification, l1_code, "L2")
        if not l2_codes:
            raise RuntimeError(
                f"index_member_all truncated and no L2 split available: l1_code={l1_code}"
            )
        batches: list[pd.DataFrame] = []
        for l2_code in l2_codes:
            l2_frame = self._call(
                "index_member_all",
                l2_code=l2_code,
                is_new=is_new,
            )
            if not l2_frame.attrs.get("provider_warning"):
                if not l2_frame.empty:
                    batches.append(l2_frame)
                continue
            l3_codes = _sector_child_codes(classification, l2_code, "L3")
            if not l3_codes:
                raise RuntimeError(
                    "index_member_all truncated and no L3 split available: "
                    f"l1_code={l1_code} l2_code={l2_code}"
                )
            for l3_code in l3_codes:
                l3_frame = self._call(
                    "index_member_all",
                    l3_code=l3_code,
                    is_new=is_new,
                )
                if l3_frame.attrs.get("provider_warning"):
                    raise RuntimeError(
                        "index_member_all remains truncated after L3 split: "
                        f"l1_code={l1_code} l3_code={l3_code}"
                    )
                if not l3_frame.empty:
                    batches.append(l3_frame)
        return batches


def _stock_basic_status_error(status: str, errors: dict[str, str]) -> str:
    matching = [
        f"{shard}: {message}"
        for shard, message in sorted(errors.items())
        if shard.startswith(f"{status}/")
    ]
    return "; ".join(matching) if matching else f"{status}: empty response"


def _sector_l1_codes(classification: pd.DataFrame) -> list[str]:
    if classification.empty:
        return []
    code_column = next(
        (
            column
            for column in ["index_code", "industry_code", "ts_code"]
            if column in classification.columns
        ),
        None,
    )
    if code_column is None:
        return []
    if "level" in classification.columns:
        rows = classification[classification["level"].astype(str).str.upper().eq("L1")]
    elif "industry_level" in classification.columns:
        rows = classification[
            classification["industry_level"].astype(str).str.upper().isin({"L1", "一级行业"})
        ]
    else:
        rows = classification
    return sorted({str(code) for code in rows[code_column].dropna().tolist() if str(code)})


def _sector_child_codes(
    classification: pd.DataFrame,
    parent_code: str,
    level: str,
) -> list[str]:
    if classification.empty or "parent_code" not in classification.columns:
        return []
    code_column = next(
        (
            column
            for column in ["index_code", "industry_code", "ts_code"]
            if column in classification.columns
        ),
        None,
    )
    if code_column is None:
        return []
    level_column = "level" if "level" in classification.columns else "industry_level"
    if level_column not in classification.columns:
        return []
    rows = classification[
        classification["parent_code"].astype(str).eq(parent_code)
        & classification[level_column].astype(str).str.upper().eq(level)
    ]
    return sorted({str(code) for code in rows[code_column].dropna() if str(code)})


def _deduplicate_sector_members(df: pd.DataFrame) -> pd.DataFrame:
    keys = [
        column
        for column in [
            "l1_code",
            "index_code",
            "industry_code",
            "con_code",
            "ts_code",
            "in_date",
            "out_date",
        ]
        if column in df.columns
    ]
    if not keys:
        return df.drop_duplicates()
    return df.drop_duplicates(subset=keys)
