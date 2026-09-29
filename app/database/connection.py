"""SQLite 连接管理：持久连接、锁冲突自动重试、每日自动备份。

为什么这样设计（共享网盘 + SQLite 的关键）：
- 每个线程复用一条持久连接（threading.local），不再"每次查询新建连接"——
  在共享盘上建连/断开都是网络往返，是老电脑上最大的隐形开销之一；
- 多个客户端同时写同一个 db 文件，SQLite 靠文件锁排队；
- 所有写操作都走"短事务 + busy_timeout + 失败退避重试"，正常情况下用户无感；
- 刻意不启用 WAL 模式：WAL 依赖共享内存文件，在 SMB 网络盘上不可靠，会造成损坏；
- 每天首次启动时用 SQLite 在线备份 API 备份数据库，防止网盘/误操作导致数据丢失。
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from app.database.schema import init_schema

BUSY_TIMEOUT_S = 15        # 单次语句遇到锁时的最长等待
MAX_RETRIES = 5            # 整个事务的重试次数
BASE_BACKOFF_S = 0.4       # 重试退避基数（指数递增 + 随机抖动）


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._local = threading.local()
        self._dv_cache: Optional[tuple[float, int]] = None  # (查询时刻, data_version)
        self._initialize()

    # ---------- 连接 ----------

    def _new_conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_S)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        # NORMAL：对客户端保持防损坏语义（掉电最多丢最近一帧，不损坏库文件），
        # 在网络盘上比默认 FULL 少一半以上的同步往返，写入明显更快。
        con.execute("PRAGMA synchronous = NORMAL;")
        # journal_mode 保持默认 DELETE（WAL 在网络盘上不可靠），见模块注释
        return con

    def _conn(self) -> sqlite3.Connection:
        """当前线程的持久连接；断开/失效时自动重建。"""
        con = getattr(self._local, "con", None)
        if con is None:
            con = self._new_conn()
            self._local.con = con
        return con

    def _drop_conn(self) -> None:
        con = getattr(self._local, "con", None)
        if con is not None:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
            self._local.con = None

    def close(self) -> None:
        """关闭当前线程的连接（进程退出前调用可选）。"""
        self._drop_conn()

    def data_version(self) -> int:
        """SQLite 跟踪的"其他连接/其他客户端最近一次提交"计数。

        同进程内的写入也由仓储层版本号覆盖；这个值用于感知**其他客户端**
        （共享盘上别的工程师电脑）对数据库的修改，作为缓存失效信号。
        50ms 记忆窗：一次界面刷新会做数百次缓存键检查，不必每次都查 PRAGMA；
        外部提交的感知粒度因此是 50ms，对人工操作节奏完全无感。
        """
        now = time.perf_counter()
        cached = self._dv_cache
        if cached is not None and now - cached[0] < 0.05:
            return cached[1]
        try:
            row = self._conn().execute("PRAGMA data_version").fetchone()
            v = int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return cached[1] if cached else 0
        self._dv_cache = (now, v)
        return v

    def _initialize(self) -> None:
        con = self._conn()
        with con:
            init_schema(con)

    # ---------- 读写入口 ----------

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """裸会话。多语句原子操作请用 transaction()，它会带锁重试。"""
        con = self._conn()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise

    def _with_retry(self, fn: Callable[[sqlite3.Connection], object]) -> object:
        last_err: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                con = self._conn()
                result = fn(con)
                con.commit()
                return result
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                try:
                    self._conn().rollback()
                except sqlite3.Error:
                    self._drop_conn()
                if "locked" in msg or "busy" in msg:
                    last_err = e
                    time.sleep(BASE_BACKOFF_S * (2**attempt) + random.uniform(0, 0.3))
                elif "closed" in msg or "cannot operate on a closed" in msg or "disk i/o" in msg:
                    # 连接被网络中断等破坏：重建后重试
                    last_err = e
                    self._drop_conn()
                    time.sleep(BASE_BACKOFF_S * attempt)
                else:
                    raise
        raise last_err  # type: ignore[misc]

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """只读查询（无重试必要，但读也可能遇到锁，仍走重试兜底）。"""
        return self._with_retry(lambda con: con.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        """单条写语句，返回 lastrowid。"""
        def _do(con: sqlite3.Connection) -> int:
            cur = con.execute(sql, params)
            return cur.lastrowid if cur.lastrowid is not None else 0
        return self._with_retry(_do)  # type: ignore[return-value]

    def execute_many(self, statements: list[tuple[str, tuple]]) -> None:
        """多条写语句，原子提交。"""
        def _do(con: sqlite3.Connection) -> None:
            for sql, params in statements:
                con.execute(sql, params)
        self._with_retry(_do)

    def transaction(self, fn: Callable[[sqlite3.Connection], object]) -> object:
        """多语句原子操作：fn(con) 内可执行任意读写，整体提交/整体回滚，锁冲突时整体重试。"""
        return self._with_retry(fn)


def backup_database(db: Database, keep_days: int = 30, backup_dir: Optional[str] = None) -> Optional[str]:
    """每日备份：用 SQLite 在线备份 API（安全支持热备份），返回备份文件路径。

    通过备份目录里的 `last_backup_date.txt` 判断今天是否已备份过。
    """
    try:
        bdir = backup_dir or os.path.join(os.path.dirname(db.db_path), "backups")
        os.makedirs(bdir, exist_ok=True)
        today = _dt.date.today().isoformat()
        marker = os.path.join(bdir, "last_backup_date.txt")
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                if f.read().strip() == today:
                    return None
        dest_path = os.path.join(bdir, f"probe_card_{today}.db")
        src = sqlite3.connect(db.db_path)
        dst = sqlite3.connect(dest_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
        with open(marker, "w", encoding="utf-8") as f:
            f.write(today)
        _prune_backups(bdir, keep_days)
        return dest_path
    except Exception:
        return None  # 备份失败不阻断软件使用


def _prune_backups(bdir: str, keep_days: int) -> None:
    cutoff = _dt.date.today() - _dt.timedelta(days=max(keep_days, 7))
    for name in os.listdir(bdir):
        if not name.startswith("probe_card_") or not name.endswith(".db"):
            continue
        date_part = name[len("probe_card_"):-len(".db")]
        try:
            if _dt.date.fromisoformat(date_part) < cutoff:
                os.remove(name if os.path.isabs(name) else os.path.join(bdir, name))
        except ValueError:
            continue
