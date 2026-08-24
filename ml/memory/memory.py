"""
ATLAS ML Pipeline - Memory
===========================
Stores successful UI patterns for faster candidate ranking.
NO model weight updates - inference only.
"""

import sqlite3
import json
from typing import List, Optional
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

from config import config


@dataclass
class PatternRecord:
    """A stored UI pattern."""
    app_name: str
    element_role: str
    element_text: Optional[str]
    bbox_relative: List[float]  # Relative position in screen
    action_type: str
    success_count: int = 1
    last_seen: float = 0


class Memory:
    """
    Stores successful UI patterns for faster recognition.
    
    Used for:
    - Faster candidate ranking
    - Confidence scoring based on past success
    
    NOT used for:
    - Model training or weight updates
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.memory.db_path
        self.enabled = config.memory.enabled
        self.max_patterns = config.memory.max_patterns
        self._conn = None
        
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._init_tables()
        return self._conn
    
    def _init_tables(self) -> None:
        cursor = self._connect().cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY,
                app_name TEXT,
                element_role TEXT,
                element_text TEXT,
                bbox_relative TEXT,
                action_type TEXT,
                success_count INTEGER DEFAULT 1,
                last_seen REAL,
                UNIQUE(app_name, element_role, element_text, action_type)
            )
        """)
        self._conn.commit()
        
    def store(self, pattern: PatternRecord) -> None:
        """Store or update a successful pattern."""
        if not self.enabled:
            return
            
        import time
        cursor = self._connect().cursor()
        
        try:
            cursor.execute("""
                INSERT INTO patterns (app_name, element_role, element_text, bbox_relative, 
                                      action_type, success_count, last_seen)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(app_name, element_role, element_text, action_type)
                DO UPDATE SET 
                    success_count = success_count + 1,
                    bbox_relative = ?,
                    last_seen = ?
            """, (pattern.app_name, pattern.element_role, pattern.element_text,
                  json.dumps(pattern.bbox_relative), pattern.action_type, time.time(),
                  json.dumps(pattern.bbox_relative), time.time()))
            self._conn.commit()
        except Exception as e:
            logger.error(f"Failed to store pattern: {e}")
    
    def lookup(self, app_name: str, role: Optional[str] = None,
               text: Optional[str] = None) -> List[PatternRecord]:
        """Look up patterns matching criteria."""
        if not self.enabled:
            return []
            
        cursor = self._connect().cursor()
        
        query = "SELECT * FROM patterns WHERE app_name = ?"
        params = [app_name]
        
        if role:
            query += " AND element_role = ?"
            params.append(role)
        if text:
            query += " AND element_text LIKE ?"
            params.append(f"%{text}%")
            
        query += " ORDER BY success_count DESC LIMIT 10"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [PatternRecord(
            app_name=r[1], element_role=r[2], element_text=r[3],
            bbox_relative=json.loads(r[4]), action_type=r[5],
            success_count=r[6], last_seen=r[7]
        ) for r in rows]
    
    def get_confidence_boost(self, app_name: str, role: str, 
                             text: Optional[str]) -> float:
        """Get confidence boost based on past success."""
        patterns = self.lookup(app_name, role, text)
        if not patterns:
            return 0.0
        
        # More successes = higher boost, capped at 0.2
        best = patterns[0]
        return min(0.2, best.success_count * 0.02)
    
    def cleanup(self) -> None:
        """Remove old/excess patterns."""
        if not self.enabled:
            return
            
        cursor = self._connect().cursor()
        cursor.execute(f"""
            DELETE FROM patterns WHERE id NOT IN (
                SELECT id FROM patterns 
                ORDER BY success_count DESC, last_seen DESC 
                LIMIT {self.max_patterns}
            )
        """)
        self._conn.commit()
        
    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
