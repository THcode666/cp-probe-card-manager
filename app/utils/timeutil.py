"""时间工具：统一本地时间字符串格式。"""

import datetime as _dt

DATE_FMT = "%Y-%m-%d"
TS_FMT = "%Y-%m-%d %H:%M:%S"


def today_str() -> str:
    return _dt.date.today().strftime(DATE_FMT)


def now_str() -> str:
    return _dt.datetime.now().strftime(TS_FMT)


def parse_date(s: str) -> _dt.date:
    return _dt.datetime.strptime(s.strip(), DATE_FMT).date()


def days_between(d1: str, d2: str) -> float:
    """d2 - d1 的天数（可为负）。"""
    return (parse_date(d2) - parse_date(d1)).total_seconds() / 86400.0
