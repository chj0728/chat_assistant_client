"""
自定义数据库初始化连接模块

description:
  - 负责根据配置文件中的数据库类型和连接参数，创建数据库连接对象。
  - 目前支持 SQLite 数据库，并对连接进行了性能优化配置。
  - 提供了同步和异步两种连接创建函数，适用于不同的使用场景。
reference:
  - https://www.sqlite.org/pragma.html
  - https://www.sqlite.org/wal.html
  - https://www.sqlite.org/mmap.html
  - https://www.sqlite.org/lockingv3.html
  - https://www.sqlite.org/async.html
"""

import sqlite3
from pathlib import Path

import aiosqlite


def create_optimized_sqlite_connection(db_path: str | Path) -> sqlite3.Connection:
    """创建经过性能优化的SQLite连接"""
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False,  # 允许多线程访问
        timeout=30,  # 超时时间
        isolation_level=None,  # 自动提交模式
    )

    # 性能优化配置
    conn.executescript("""
        PRAGMA journal_mode=WAL;          -- 写前日志模式，提高并发性能
        PRAGMA synchronous=NORMAL;        -- 平衡性能和数据安全
        PRAGMA cache_size=-2000;          -- 设置2MB缓存
        PRAGMA temp_store=MEMORY;         -- 临时表存储在内存中
        PRAGMA mmap_size=268435456;       -- 256MB内存映射
        PRAGMA busy_timeout=5000;         -- 5秒忙超时
        """)
    return conn


async def create_optimized_aiosqlite_connection(
    db_path: str | Path,
) -> aiosqlite.Connection:
    """创建经过性能优化的异步SQLite连接"""
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _create_connection():
        conn = await aiosqlite.connect(
            str(db_path),
            check_same_thread=False,  # 允许多线程访问
            timeout=30,  # 超时时间
            isolation_level=None,  # 自动提交模式
        )

        # 性能优化配置
        await conn.executescript("""
            PRAGMA journal_mode=WAL;          -- 写前日志模式，提高并发性能
            PRAGMA synchronous=NORMAL;        -- 平衡性能和数据安全
            PRAGMA cache_size=-2000;          -- 设置2MB缓存
            PRAGMA temp_store=MEMORY;         -- 临时表存储在内存中
            PRAGMA mmap_size=268435456;       -- 256MB内存映射
            PRAGMA busy_timeout=5000;         -- 5秒忙超时
            """)
        return conn

    return await _create_connection()
