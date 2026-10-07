"""SMC-C market data input and completed-candle timeframe construction.

This loader reads the raw 1-minute CSV files directly. It does not import or
call another strategy/backtest implementation.
"""
from pathlib import Path

import pandas as pd


OHLCV = ("o", "h", "l", "c", "v")
TIMEFRAMES = {
    "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h",
    "4h": "4h", "1d": "1D", "1w": "1W-MON", "1mo": "1MS",
}


def load_one_minute(directory, symbol="BTC-USDT-SWAP", start=None, end=None):
    """Load and validate {symbol}_1m/YYYY-MM.csv files into a UTC-indexed frame."""
    root = Path(directory) / f"{symbol}_1m"
    files = sorted(root.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No one-minute CSV files found in {root}")
    frame = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    if "t" not in frame.columns:
        raise ValueError("CSV requires a millisecond epoch column named 't'")
    missing = sorted(set(OHLCV) - set(frame.columns))
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}")
    frame = frame.sort_values("t").drop_duplicates("t", keep="last")
    frame.index = pd.to_datetime(frame.pop("t"), unit="ms", utc=True)
    frame = frame.loc[:, list(OHLCV)].apply(pd.to_numeric, errors="coerce").dropna()
    frame = frame[~frame.index.duplicated(keep="last")]
    if start is not None:
        frame = frame.loc[pd.to_datetime(start, utc=True):]
    if end is not None:
        frame = frame.loc[:pd.to_datetime(end, utc=True)]
    if not frame.index.is_monotonic_increasing:
        raise ValueError("Candle timestamps must increase")
    invalid = ((frame["h"] < frame[["o", "c", "l"]].max(axis=1)) |
               (frame["l"] > frame[["o", "c", "h"]].min(axis=1)))
    if invalid.any():
        raise ValueError(f"Found {int(invalid.sum())} invalid OHLC rows")
    return frame


def resample_completed(one_minute, timeframe):
    """Aggregate left-labeled UTC bars and omit incomplete trailing bars."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe {timeframe!r}")
    rule = TIMEFRAMES[timeframe]
    agg = {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}
    result = one_minute.resample(rule, label="left", closed="left", origin="start_day").agg(agg)
    result = result.dropna(subset=["o", "h", "l", "c"])
    if len(one_minute):
        last_open = one_minute.index[-1]
        last_bar = result.index[-1]
        offset = pd.tseries.frequencies.to_offset(rule)
        if last_bar + offset > last_open + pd.Timedelta(minutes=1):
            result = result.iloc[:-1]
    return result


def build_timeframes(one_minute, names=None):
    """Return source 1m bars and all requested UTC-complete higher frames."""
    names = names or tuple(TIMEFRAMES)
    frames = {"1m": one_minute}
    frames.update({name: resample_completed(one_minute, name) for name in names})
    return frames
