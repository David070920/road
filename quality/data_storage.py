import sqlite3
import threading
import time

DB_PATH = "road_quality_history.db"

class DataStorage:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Create table for road quality data
            c.execute('''
                CREATE TABLE IF NOT EXISTS road_quality_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    latitude REAL,
                    longitude REAL,
                    quality_score REAL,
                    classification TEXT
                )
            ''')
            # Create table for detected events
            c.execute('''
                CREATE TABLE IF NOT EXISTS road_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    latitude REAL,
                    longitude REAL,
                    severity INTEGER,
                    source TEXT,
                    confidence REAL
                )
            ''')
            conn.commit()

    def insert_quality_data(self, timestamp, lat, lon, quality_score, classification):
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO road_quality_data (timestamp, latitude, longitude, quality_score, classification)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, lat, lon, quality_score, classification))
            conn.commit()

    def insert_event(self, timestamp, lat, lon, severity, source, confidence):
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO road_events (timestamp, latitude, longitude, severity, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, lat, lon, severity, source, confidence))
            conn.commit()

    def query_quality_data(self, start_time, end_time):
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT timestamp, latitude, longitude, quality_score, classification
                FROM road_quality_data
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (start_time, end_time))
            return c.fetchall()

    def query_events(self, start_time, end_time):
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT timestamp, latitude, longitude, severity, source, confidence
                FROM road_events
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (start_time, end_time))
            return c.fetchall()