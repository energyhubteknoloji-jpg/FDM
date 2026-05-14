import os
import json
import logging

logger = logging.getLogger(__name__)

def DatabaseManager():
    """
    Kullanıcı ayarlarını okur ve seçilen veritabanı adaptörünü (SQLite/Postgres) döner.
    """
    app_dir = os.path.join(os.path.expanduser('~'), '.fdmsensor_desktop')
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
        
    config_path = os.path.join(app_dir, 'config.json')
    
    # Varsayılan Ayarlar
    config = {
        "db_type": "sqlite",
        "sqlite_path": os.path.join(app_dir, "sensor_data.db"),
        "postgres": {
            "host": "localhost",
            "port": 5432,
            "user": "postgres",
            "password": "",
            "dbname": "fdmsensor"
        }
    }

    # Ayar dosyası varsa oku
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config.update(json.load(f))
        except Exception as e:
            logger.error(f"Config okuma hatası: {e}")

    if config["db_type"] == "postgres":
        try:
            from db_postgres import PostgresAdapter
            return PostgresAdapter(config["postgres"])
        except ImportError:
            logger.error("Postgres sürücüsü (psycopg2) bulunamadı! SQLite'a dönülüyor.")
    
    # Varsayılan: SQLite
    from db_sqlite import SQLiteAdapter
    return SQLiteAdapter(config["sqlite_path"])
