"""PostgreSQL access and message/button template persistence."""
from __future__ import annotations
import json
import asyncpg

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10, command_timeout=30)

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    def require(self) -> asyncpg.Pool:
        if not self.pool:
            raise RuntimeError("Database pool is not connected")
        return self.pool

    async def init_schema(self, sql: str):
        await self.require().execute(sql)

    async def get_text(self, clone_id: str, key: str, default: str) -> str:
        row = await self.require().fetchrow(
            "SELECT body FROM bot_message_templates WHERE clone_id=$1 AND template_key=$2",
            clone_id, key,
        )
        return str(row["body"]) if row else default

    async def set_text(self, clone_id: str, key: str, body: str):
        await self.require().execute(
            """INSERT INTO bot_message_templates(clone_id, template_key, body)
               VALUES($1,$2,$3) ON CONFLICT(clone_id, template_key)
               DO UPDATE SET body=EXCLUDED.body, updated_at=NOW()""",
            clone_id, key, body,
        )

    async def reset_text(self, clone_id: str, key: str):
        await self.require().execute(
            "DELETE FROM bot_message_templates WHERE clone_id=$1 AND template_key=$2", clone_id, key
        )

    async def get_buttons(self, clone_id: str, key: str) -> list:
        row = await self.require().fetchrow(
            "SELECT buttons FROM bot_message_buttons WHERE clone_id=$1 AND template_key=$2",
            clone_id, key,
        )
        if not row:
            return []
        value = row["buttons"]
        return json.loads(value) if isinstance(value, str) else (value or [])

    async def set_buttons(self, clone_id: str, key: str, buttons: list):
        await self.require().execute(
            """INSERT INTO bot_message_buttons(clone_id, template_key, buttons)
               VALUES($1,$2,$3::jsonb) ON CONFLICT(clone_id, template_key)
               DO UPDATE SET buttons=EXCLUDED.buttons, updated_at=NOW()""",
            clone_id, key, json.dumps(buttons),
        )
