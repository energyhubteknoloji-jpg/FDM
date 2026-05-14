import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from werkzeug.security import generate_password_hash
import os

logger = logging.getLogger(__name__)

class PostgresAdapter:
    def __init__(self, config):
        self.config = config
        self.conn = None

    def _get_conn(self):
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(**self.config)
        return self.conn

    def init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # SQLite şemasıyla uyumlu tabloları oluştur
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transformers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                ip_url TEXT NOT NULL,
                username TEXT,
                password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                city_name TEXT,
                latitude REAL,
                longitude REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data_rows (
                id SERIAL PRIMARY KEY,
                trafo_id INTEGER REFERENCES transformers(id),
                sensor_timestamp TIMESTAMP NOT NULL,
                temperature_top REAL,
                temperature_bottom REAL,
                load_percent REAL,
                ambient_temp REAL,
                oil_level REAL,
                vibration REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sensor_timestamp, trafo_id)
            )
        ''')
        
        # Varsayılan veriler
        cursor.execute('SELECT COUNT(*) FROM transformers')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO transformers (name, ip_url, username, password)
                VALUES (%s, %s, %s, %s)
            ''', ("Varsayılan Trafo (Default)", "http://5.11.212.206:8080/admin/data/datalog", "admin", "9117m?"))
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = %s', ('grid',))
        if cursor.fetchone()[0] == 0:
            pw_hash = generate_password_hash('grid2026-')
            cursor.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, %s, %s)
            ''', ('grid', pw_hash, 'admin'))
            
        conn.commit()
        cursor.close()

    # Diğer metodlar SQLite adaptöründekiyle aynı mantıkla eklenecek...
    # (Özet olarak Postgres uyumlu hale getirildi)
