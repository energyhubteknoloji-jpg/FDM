import sqlite3
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class SQLiteAdapter:
    def __init__(self, db_name="sensor_data.db"):
        self.db_name = db_name
        self.init_db()

    def _get_conn(self):
        """Thread-safe SQLite connection factory."""
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def init_db(self):
        """Initialize the database and create table if not exists."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Transformers Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transformers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ip_url TEXT NOT NULL,
                username TEXT,
                password TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                city_name TEXT,
                latitude REAL,
                longitude REAL
            )
        ''')

        # 2. Users Table (New)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Original table (kept for backup/legacy)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source_url TEXT,
                raw_data TEXT
            )
        ''')

        # New normalized table for row-level access
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_timestamp DATETIME,
                sensor1 REAL,
                sensor2 REAL,
                sensor3 REAL,
                sensor4 REAL,
                source_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                trafo_id INTEGER,
                UNIQUE(sensor_timestamp, trafo_id) 
            )
        ''')

        # 3. Check if we need to migrate existing data (add trafo_id)
        try:
            cursor.execute('SELECT trafo_id FROM sensor_data_rows LIMIT 1')
        except sqlite3.OperationalError:
            print("DB: Migrating schema - adding trafo_id column...")
            try:
                cursor.execute('ALTER TABLE sensor_data_rows ADD COLUMN trafo_id INTEGER')
                conn.commit()
                print("DB: Added trafo_id column.")
            except Exception as e:
                print(f"DB: Error adding column: {e}")

        # 4. Create Default Transformer if table is empty
        cursor.execute('SELECT COUNT(*) FROM transformers')
        if cursor.fetchone()[0] == 0:
            print("DB: Creating default transformer...")
            cursor.execute('''
                INSERT INTO transformers (name, ip_url, username, password)
                VALUES (?, ?, ?, ?)
            ''', ("Varsayılan Trafo (Default)", "http://5.11.212.206:8080/admin/data/datalog", "admin", "9117m?"))
            default_id = cursor.lastrowid
            
            # Migrate existing rows to this default transformer
            cursor.execute('UPDATE sensor_data_rows SET trafo_id = ? WHERE trafo_id IS NULL', (default_id,))
            print(f"DB: Assigned existing data to default transformer ID {default_id}")
            conn.commit()

        # 5. Create Default Admin User if not exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('grid',))
        if cursor.fetchone()[0] == 0:
            print("DB: Creating default admin user 'grid'...")
            pw_hash = generate_password_hash(os.environ.get('DEFAULT_ADMIN_PASSWORD', 'grid2026-'))
            cursor.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, ?)
            ''', ('grid', pw_hash, 'admin'))
            conn.commit()


        # 6. Add Location Columns to Transformers (Migration - check if needed)
        try:
            cursor.execute('SELECT latitude FROM transformers LIMIT 1')
        except sqlite3.OperationalError:
            print("DB: Adding location columns to transformers...")
            try:
                cursor.execute('ALTER TABLE transformers ADD COLUMN latitude REAL')
                cursor.execute('ALTER TABLE transformers ADD COLUMN longitude REAL')
                cursor.execute('ALTER TABLE transformers ADD COLUMN city_name TEXT')
                conn.commit()
            except Exception as e:
                print(f"DB: Error adding location columns: {e}")

        # 7. Weather Data Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trafo_id INTEGER,
                timestamp DATETIME,
                temperature REAL,
                UNIQUE(trafo_id, timestamp)
            )
        ''')
        
        try:
             cursor.execute('DROP INDEX IF EXISTS idx_sensor_timestamp')
             # Re-create unique index including trafo_id
             cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_timestamp_trafo ON sensor_data_rows(sensor_timestamp, trafo_id)')
        except Exception as e:
             print(f"DB: Index update warning: {e}")
        
        conn.commit()
        conn.close()

    # --- User Management ---

    def get_user_by_id(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, username, password_hash, role FROM users WHERE id = ?', (user_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def get_all_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, username, role, created_at FROM users ORDER BY id ASC')
            return cursor.fetchall()
        finally:
            conn.close()

    def delete_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def update_user_role(self, user_id, new_role):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def get_user_by_username(self, username):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, username, password_hash, role FROM users WHERE username = ?', (username,))
            return cursor.fetchone()
        finally:
            conn.close()

    def update_user_password(self, user_id, password_hash):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def create_user(self, username, password, role='user'):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            hashed = generate_password_hash(password)
            cursor.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', 
                          (username, hashed, role))
            conn.commit()
            return True, None
        except sqlite3.IntegrityError:
            return False, "Username already exists"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    # --- Transformer CRUD ---

    def add_transformer(self, name, ip_url, username, password):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO transformers (name, ip_url, username, password)
                VALUES (?, ?, ?, ?)
            ''', (name, ip_url, username, password))
            conn.commit()
            return cursor.lastrowid, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()

    def get_transformers(self, active_only=True):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = 'SELECT id, name, ip_url, username, password, city_name, latitude, longitude FROM transformers'
            if active_only:
                query += ' WHERE is_active = 1'
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            conn.close()

    def update_transformer(self, t_id, name, ip_url, username, password):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE transformers 
                SET name=?, ip_url=?, username=?, password=?
                WHERE id=?
            ''', (name, ip_url, username, password, t_id))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def delete_transformer(self, t_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE transformers SET is_active=0 WHERE id=?', (t_id,))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
            
    def get_transformer_by_id(self, t_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, name, ip_url, username, password, city_name, latitude, longitude FROM transformers WHERE id=?', (t_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    # --- Sensor Data Methods ---

    def insert_reading(self, trafo_id, url, data_dict):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            rows = data_dict.get("table_rows", [])
            inserted_count = 0
            
            for row in rows:
                try:
                    s1 = float(row.get("sensor1", 0) or 0)
                    s2 = float(row.get("sensor2", 0) or 0)
                    s3 = float(row.get("sensor3", 0) or 0)
                    s4 = float(row.get("sensor4", 0) or 0)
                    
                    if s1 > 120 or s2 > 120 or s3 > 120:
                        continue

                    cursor.execute('''
                        INSERT OR IGNORE INTO sensor_data_rows (sensor_timestamp, sensor1, sensor2, sensor3, sensor4, source_url, trafo_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row.get("time"),
                        s1, s2, s3, s4,
                        url,
                        trafo_id
                    ))
                    if cursor.rowcount > 0:
                        inserted_count += 1
                except (sqlite3.IntegrityError, ValueError, TypeError):
                    pass 

            conn.commit()
            return True, inserted_count
        except Exception as e:
            print(f"Error inserting data: {e}")
            return False, 0
        finally:
            conn.close()
            
    def get_latest_timestamp(self, trafo_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT MAX(sensor_timestamp) FROM sensor_data_rows WHERE trafo_id=?', (trafo_id,))
            result = cursor.fetchone()
            if result and result[0]:
                return result[0] 
            return None
        except Exception as e:
            print(f"Error checking max timestamp: {e}")
            return None
        finally:
            conn.close()

    def get_readings(self, trafo_id=None, limit=50, offset=0, date_filter=None, search_filter=None, start_date=None, end_date=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = '''
            SELECT s.id, s.sensor_timestamp, s.sensor1, s.sensor2, s.sensor3, s.sensor4, w.temperature
            FROM sensor_data_rows s
            LEFT JOIN weather_data w ON s.trafo_id = w.trafo_id 
            AND substr(w.timestamp, 1, 13) = substr(REPLACE(s.sensor_timestamp, '/', '-'), 1, 13)
            WHERE 1=1 
        '''
        params = []
        
        if trafo_id:
            query += ' AND s.trafo_id = ?'
            params.append(trafo_id)
            
        if date_filter:
            date_filter_db = date_filter.replace('-', '/').replace('T', ' ')
            query += ' AND s.sensor_timestamp LIKE ?'
            params.append(f"{date_filter_db}%")

        if start_date:
            sd = start_date.replace('-', '/').replace('T', ' ')
            query += ' AND s.sensor_timestamp >= ?'
            params.append(sd)
            
        if end_date:
            ed = end_date.replace('-', '/').replace('T', ' ')
            if len(ed) <= 10:
                ed = f"{ed} 23:59:59"
            query += ' AND s.sensor_timestamp <= ?'
            params.append(ed)
            
        if search_filter:
            search_term = f"%{search_filter}%"
            query += ''' AND (
                s.id LIKE ? OR 
                s.sensor1 LIKE ? OR 
                s.sensor2 LIKE ? OR 
                s.sensor3 LIKE ? OR 
                s.sensor4 LIKE ?
            )'''
            params.extend([search_term] * 5)
            
        query += ' ORDER BY s.sensor_timestamp DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_reading_count(self, trafo_id=None, date_filter=None, search_filter=None, start_date=None, end_date=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        query = 'SELECT COUNT(*) FROM sensor_data_rows WHERE 1=1'
        params = []
        
        if trafo_id:
            query += ' AND trafo_id = ?'
            params.append(trafo_id)
            
        if date_filter:
            date_filter_db = date_filter.replace('-', '/').replace('T', ' ')
            query += ' AND sensor_timestamp LIKE ?'
            params.append(f"{date_filter_db}%")

        if start_date:
            sd = start_date.replace('-', '/').replace('T', ' ')
            query += ' AND sensor_timestamp >= ?'
            params.append(sd)
            
        if end_date:
            ed = end_date.replace('-', '/').replace('T', ' ')
            if len(ed) <= 10:
                ed = f"{ed} 23:59:59"
            query += ' AND sensor_timestamp <= ?'
            params.append(ed)
            
        if search_filter:
            search_term = f"%{search_filter}%"
            query += ''' AND (
                id LIKE ? OR 
                sensor1 LIKE ? OR 
                sensor2 LIKE ? OR 
                sensor3 LIKE ? OR 
                sensor4 LIKE ?
            )'''
            params.extend([search_term] * 5)
            
        cursor.execute(query, tuple(params))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_readings_dataframe(self, trafo_id=None, limit=20000, year=None, month=None):
        import pandas as pd
        conn = self._get_conn()
        try:
            # 1. Fetch sensor data
            sensor_query = "SELECT sensor_timestamp, sensor1, sensor2, sensor3, sensor4 FROM sensor_data_rows"
            params = []
            where_clauses = []
            
            if trafo_id:
                where_clauses.append("trafo_id = ?")
                params.append(trafo_id)
            
            if year:
                import datetime
                if month:
                    m_str = f"{month:02d}"
                    tag = f"{year}/{m_str}%"
                    
                    # Calculate Unix range for the specific month
                    u1 = datetime.datetime(year, month, 1).timestamp()
                    if month == 12:
                        u2 = datetime.datetime(year + 1, 1, 1).timestamp()
                    else:
                        u2 = datetime.datetime(year, month + 1, 1).timestamp()
                    
                    where_clauses.append("(sensor_timestamp LIKE ? OR (CAST(sensor_timestamp AS REAL) >= ? AND CAST(sensor_timestamp AS REAL) < ?))")
                    params.extend([tag, u1, u2])
                    limit = None # Override limit for specific month
                else:
                    tag = f"{year}/%"
                    u1 = datetime.datetime(year, 1, 1).timestamp()
                    u2 = datetime.datetime(year + 1, 1, 1).timestamp()
                    where_clauses.append("(sensor_timestamp LIKE ? OR (CAST(sensor_timestamp AS REAL) >= ? AND CAST(sensor_timestamp AS REAL) < ?))")
                    params.extend([tag, u1, u2])

            if where_clauses:
                sensor_query += " WHERE " + " AND ".join(where_clauses)
            
            sensor_query += " ORDER BY sensor_timestamp DESC"
            if limit:
                sensor_query += f" LIMIT {limit}"
                
            df_sensor = pd.read_sql_query(sensor_query, conn, params=params)
            
            if df_sensor.empty:
                return df_sensor

            # 2. Fetch weather data
            weather_query = "SELECT timestamp, temperature FROM weather_data"
            w_params = []
            if trafo_id:
                 weather_query += " WHERE trafo_id = ?"
                 w_params.append(trafo_id)
            
            df_weather = pd.read_sql_query(weather_query, conn, params=w_params)

            # 3. Temporal Join using Pandas (much faster than string-based SQL JOIN)
            # Normalize timestamps: sensor_timestamp can be Unix float OR string
            s_nums = pd.to_numeric(df_sensor['sensor_timestamp'], errors='coerce')
            df_sensor['dt'] = pd.to_datetime(s_nums, unit='s')
            
            # Fill NaNs from string parsing
            mask = df_sensor['dt'].isna()
            if mask.any():
                df_sensor.loc[mask, 'dt'] = pd.to_datetime(df_sensor.loc[mask, 'sensor_timestamp'])
                
            # Create a display-friendly Tarih column
            df_sensor['Tarih'] = df_sensor['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')

            if not df_weather.empty:
                df_weather['dt'] = pd.to_datetime(df_weather['timestamp'])
                
                # Sort for merge_asof
                df_sensor = df_sensor.sort_values('dt')
                df_weather = df_weather.sort_values('dt')
                
                # Join nearest weather data (within same hour or nearest available)
                df = pd.merge_asof(
                    df_sensor, 
                    df_weather[['dt', 'temperature']], 
                    on='dt', 
                    direction='nearest'
                )
            else:
                df = df_sensor
                df['temperature'] = None

            # 4. Final Formatting
            df = df.rename(columns={
                'sensor1': 'Sensör 1',
                'sensor2': 'Sensör 2',
                'sensor3': 'Sensör 3',
                'sensor4': 'Sensör 4',
                'temperature': 'Dış Sıcaklık (°C)'
            })

            # Return columns in specific order
            output_cols = ['Tarih', 'Sensör 1', 'Sensör 2', 'Sensör 3', 'Sensör 4', 'Dış Sıcaklık (°C)']
            return df[output_cols].sort_values('Tarih', ascending=False)

        finally:
            conn.close()

    # --- Weather Data Methods ---

    def update_transformer_location(self, t_id, city, lat, lon):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE transformers 
                SET city_name=?, latitude=?, longitude=?
                WHERE id=?
            ''', (city, lat, lon, t_id))
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def insert_weather_data(self, trafo_id, weather_list):
        conn = self._get_conn()
        cursor = conn.cursor()
        count = 0
        try:
            for ts, temp in weather_list:
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO weather_data (trafo_id, timestamp, temperature)
                        VALUES (?, ?, ?)
                    ''', (trafo_id, ts, temp))
                    if cursor.rowcount > 0:
                        count += 1
                except:
                    pass
            conn.commit()
            return count
        except Exception as e:
            print(f"DB: Weather insert error: {e}")
            return 0
        finally:
            conn.close()

    def get_peak_stats(self, trafo_id, start_date=None, end_date=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            allowed_cols = {"sensor1": "top", "sensor2": "amb", "sensor3": "bot"}
            results = {}

            for col, key in allowed_cols.items():
                query = f"SELECT {col}, sensor_timestamp FROM sensor_data_rows WHERE trafo_id = ?"
                params = [trafo_id]

                if start_date:
                    sd = start_date.replace('-', '/').replace('T', ' ')
                    query += " AND sensor_timestamp >= ?"
                    params.append(sd)
                
                if end_date:
                    ed = end_date.replace('-', '/').replace('T', ' ')
                    if len(ed) <= 10: ed = f"{ed} 23:59:59"
                    query += " AND sensor_timestamp <= ?"
                    params.append(ed)

                query += f" AND {col} IS NOT NULL ORDER BY {col} DESC LIMIT 1"
                
                cursor.execute(query, params)
                res = cursor.fetchone()
                results[key] = {"val": res[0], "ts": res[1]} if res else {"val": 0, "ts": None}

            return results
        finally:
            conn.close()

    def get_top_high_values(self, trafo_id, sensor_col, limit=5, start_date=None, end_date=None):
        if sensor_col not in ["sensor1", "sensor2", "sensor3", "sensor4"]:
            raise ValueError("Invalid sensor column")

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            query = f"SELECT {sensor_col}, sensor_timestamp FROM sensor_data_rows WHERE trafo_id = ? AND {sensor_col} IS NOT NULL"
            params = [trafo_id]

            if start_date:
                sd = start_date.replace('-', '/').replace('T', ' ')
                query += " AND sensor_timestamp >= ?"
                params.append(sd)
            
            if end_date:
                ed = end_date.replace('-', '/').replace('T', ' ')
                if len(ed) <= 10: ed = f"{ed} 23:59:59"
                query += " AND sensor_timestamp <= ?"
                params.append(ed)
            
            query += f" ORDER BY {sensor_col} DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [{"val": r[0], "ts": r[1]} for r in rows]
        finally:
            conn.close()
