import csv
import io
import json
from datetime import datetime

from app.config_store import ConfigStore
from app.personae import persona_display_name
from app.translations import tr


class DanmuHistory:
    def __init__(self, config: ConfigStore):
        self.config = config

    def add(self, content: str, persona: str, round_num: int, image_bytes: bytes | None = None):
        self.config.conn.execute(
            "INSERT INTO history (time, persona, content, image, round) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), persona, content, image_bytes, round_num),
        )
        self.config.conn.commit()

    def search(
        self,
        keyword: str = "",
        persona: str = "",
        time_from: str = "",
        time_to: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        parts = ["SELECT id, time, persona, content, round FROM history WHERE 1=1"]
        params = []
        if keyword:
            parts.append("AND content LIKE ? ESCAPE '\\'")
            params.append(f"%{keyword}%")
        if persona:
            parts.append("AND persona=?")
            params.append(persona)
        if time_from:
            parts.append("AND time >= ?")
            params.append(time_from)
        if time_to:
            parts.append("AND time <= ?")
            params.append(time_to)
        parts.append("ORDER BY id DESC LIMIT ? OFFSET ?")
        params.extend([page_size, (page - 1) * page_size])

        rows = self.config.conn.execute(" ".join(parts), params).fetchall()
        return [
            {"id": row[0], "time": row[1], "persona": row[2], "content": row[3], "round": row[4]}
            for row in rows
        ]

    def count(self, keyword: str = "", persona: str = "", time_from: str = "", time_to: str = "") -> int:
        parts = ["SELECT COUNT(*) FROM history WHERE 1=1"]
        params = []
        if keyword:
            parts.append("AND content LIKE ? ESCAPE '\\'")
            params.append(f"%{keyword}%")
        if persona:
            parts.append("AND persona=?")
            params.append(persona)
        if time_from:
            parts.append("AND time >= ?")
            params.append(time_from)
        if time_to:
            parts.append("AND time <= ?")
            params.append(time_to)
        row = self.config.conn.execute(" ".join(parts), params).fetchone()
        return row[0] if row else 0

    def export_all(self) -> list[dict]:
        rows = self.config.conn.execute(
            "SELECT id, time, persona, content, round FROM history ORDER BY id DESC"
        ).fetchall()
        return [
            {"id": row[0], "time": row[1], "persona": row[2], "content": row[3], "round": row[4]}
            for row in rows
        ]

    def export_csv(self, items: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            tr("history.csv_time"),
            tr("history.csv_persona"),
            tr("history.csv_content"),
            tr("history.csv_round"),
        ])
        for item in items:
            writer.writerow([item["time"], persona_display_name(item["persona"]), item["content"], item["round"]])
        return buffer.getvalue()

    def export_json(self, items: list[dict]) -> str:
        return json.dumps(items, ensure_ascii=False, indent=2)
