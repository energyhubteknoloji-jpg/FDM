from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for, flash
import threading
import time
import logging
import traceback
from logging.handlers import RotatingFileHandler
from database import DatabaseManager
from scraper import SensorScraper, ApiScraper
from weather_service import WeatherService
from simulation_engine import HermeticSimulationEngine
import json
import os
import io
import pandas as pd
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Load environment variables from .env file
load_dotenv()
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash
from functools import wraps


# Log dosyasını yazılabilir bir dizine yönlendir (packaged app uyumu)
_app_dir = os.path.join(os.path.expanduser('~'), '.fdmsensor_desktop')
os.makedirs(_app_dir, exist_ok=True)
_log_path = os.path.join(_app_dir, 'server.log')

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(_log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security Configuration
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_change_in_prod_911') 
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# app.config['SESSION_COOKIE_SECURE'] = True # Uncomment when running on HTTPS

# CSRF Protection
csrf = CSRFProtect(app)
# Exclude API endpoints from CSRF if they use Token/Bearer auth, but since we use Session Auth for frontend:
# We might need to handle this. For now, let's enable it and see.
# Usually, CSRF is needed for Form POSTs.

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # CSP: Electron icin http://127.0.0.1 connect-src'e eklendi
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com blob:; "
        "worker-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' http://127.0.0.1:* https:;"
    )
    return response

# Flask-Login Configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.before_request
def check_setup():
    # Setup sayfasının kendisi ve static dosyalar hariç yönlendir
    if not is_setup_completed() and request.endpoint not in ['setup', 'save_config', 'static']:
        return redirect(url_for('setup'))

db = DatabaseManager()
weather_service = WeatherService()
simulation_engine = HermeticSimulationEngine()

# Global state
is_running = True # Start automatically
scrape_interval = 300 # 5 minutes
scraper_thread = None
last_scrape_status = {} # Store status per transformer: {id: "timestamp"}
last_weather_update = {} # Store last weather fetch time: {id: unix_timestamp}

# --- User Class & Auth Utils ---

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role
    
    def is_admin(self):
        return self.role == 'admin'

@login_manager.user_loader
def load_user(user_id):
    u = db.get_user_by_id(user_id)
    if u:
        # u: id, username, password_hash, role
        return User(id=u[0], username=u[1], role=u[3])
    return None

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                return jsonify({"status": "error", "message": "Permission denied"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    return role_required('admin')(f)

# --- Background Scraper ---

def background_scraper():
    global is_running, last_scrape_status, last_weather_update
    while is_running:
        logger.info("Auto-Scraper: Starting cycle...")
        
        # 1. Get all active transformers
        transformers = db.get_transformers(active_only=True)
        if not transformers:
            logger.info("Auto-Scraper: No active transformers found.")
        
        for t in transformers:
             # t: (id, name, ip_url, username, password, city, lat, lon)
            t_id, t_name, t_url, t_user, t_pass = t[0], t[1], t[2], t[3], t[4]
            t_lat, t_lon = t[6], t[7]

            logger.info(f"Auto-Scraper: Processing Transformer '{t_name}' ({t_url})...")
            
            # --- Weather Update (Hourly Rate Limit) ---
            current_time = time.time()
            last_weather_ts = last_weather_update.get(t_id, 0)
            
            if t_lat and t_lon:
                # Check if 1 hour (3600s) has passed since last update
                if current_time - last_weather_ts > 3600:
                    logger.info(f"Auto-Scraper: [{t_name}] Fetching current weather...")
                    try:
                        current_weather = weather_service.get_current_weather(t_lat, t_lon)
                        if current_weather:
                            w_count = db.insert_weather_data(t_id, current_weather)
                            last_weather_update[t_id] = current_time
                            logger.info(f"Auto-Scraper: [{t_name}] Weather updated. {w_count} new records.")
                    except Exception as e:
                        logger.error(f"Auto-Scraper: [{t_name}] Weather update failed: {e}")
                else:
                    pass
            
            try:
                # 1. Try API Scraper first (Faster, lighter)
                s = ApiScraper()
                last_ts = db.get_latest_timestamp(t_id)
                success, data = s.scrape_data(start_timestamp=last_ts)
                
                if not success:
                    login_success, login_msg = s.login(t_url, t_user, t_pass)
                    if login_success:
                        success, data = s.scrape_data(start_timestamp=last_ts)
                    else:
                        logger.warning(f"Auto-Scraper: [{t_name}] API Login failed: {login_msg}. Trying Browser fallback...")
                
                # 2. Fallback to Browser Scraper if API fails
                if not success:
                    logger.info(f"Auto-Scraper: [{t_name}] Starting Browser Scraper fallback...")
                    bs = SensorScraper()
                    try:
                        login_success, login_msg = bs.login(t_url, t_user, t_pass)
                        if login_success:
                            success, data = bs.scrape_data()
                        else:
                            logger.error(f"Auto-Scraper: [{t_name}] Browser Login failed: {login_msg}")
                    finally:
                        bs.close()

                if success:
                    success_db, count = db.insert_reading(t_id, t_url, data)
                    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    last_scrape_status[t_id] = now_str
                    logger.info(f"Auto-Scraper: [{t_name}] Data saved via {'API' if isinstance(s, ApiScraper) and not 'bs' in locals() else 'Browser'}. {count} new rows.")
                else:
                    logger.warning(f"Auto-Scraper: [{t_name}] All scraping methods failed.")
                    
            except Exception as e:
                logger.error(f"Auto-Scraper: [{t_name}] Critical error: {e}")
            
            # Small delay between transformers to not spike CPU/Net
            time.sleep(1)
            
        # Sleep for interval
        for _ in range(scrape_interval):
            if not is_running: break
            time.sleep(1)

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = db.get_user_by_username(username)
        # user_data: id, username, password_hash, role
        
        if user_data and check_password_hash(user_data[2], password):
            user = User(id=user_data[0], username=user_data[1], role=user_data[3])
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

@app.route('/digital-twin')
@login_required
def digital_twin():
    return render_template('twin.html', user=current_user)

@app.route('/technical-details')
@login_required
def technical_details():
    return render_template('technical_details.html', user=current_user)

@app.route('/api/twin/latest')
@login_required
def twin_latest_data():
    try:
        trafo_id = request.args.get('trafo_id')
        date_filter = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if trafo_id: 
            trafo_id = int(trafo_id)
        else:
            # Default to first active
            t_list = db.get_transformers()
            if t_list:
                trafo_id = t_list[0][0]
            else:
                return jsonify({"status": "error", "message": "No transformers found"}), 404

        # Fetch latest reading (1 record) within range if provided
        readings = db.get_readings(
            trafo_id=trafo_id, 
            limit=1, 
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date
        )
        
        if not readings:
            return jsonify({
                "envanter_id": f"TRF-{trafo_id}",
                "ts": int(time.time()),
                "top_oil_c": None,
                "ambient_c": None,
                "bottom_oil_c": None
            })

        r = readings[0]
        # readings format: id, sensor_timestamp, sensor1, sensor2, sensor3, sensor4, weather_temp
        
        # Parse timestamp from string "YYYY/MM/DD HH:MM:SS" to epoch
        try:
            ts_struct = time.strptime(r[1], "%Y/%m/%d %H:%M:%S")
            ts_epoch = int(ts_mktime(ts_struct))
        except:
            ts_epoch = int(time.time())

        return jsonify({
            "envanter_id": f"TRF-{trafo_id}",
            "ts": ts_epoch,
            "top_oil_c": r[2] if r[2] is not None else None,
            "ambient_c": r[3] if r[3] is not None else None,
            "bottom_oil_c": r[4] if r[4] is not None else None
        })

    except Exception as e:
        logger.error(f"Twin API Error: {e}")
        return jsonify({"status": "error", "message": "Sunucu hatası meydana geldi."}), 500

@app.route('/api/twin/history')
@login_required
def twin_history_data():
    try:
        trafo_id = request.args.get('trafo_id')
        date_filter = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not trafo_id:
            # Default to first active
            t_list = db.get_transformers()
            if t_list:
                trafo_id = t_list[0][0]
            else:
                return jsonify({"labels": [], "datasets": []})
        else:
            trafo_id = int(trafo_id)

        # Fetch records for graph
        # If range or date provided, fetch more (e.g. 100) or all for that day
        limit = 100 if (date_filter or start_date or end_date) else 20
        readings = db.get_readings(
            trafo_id=trafo_id, 
            limit=limit, 
            date_filter=date_filter,
            start_date=start_date,
            end_date=end_date
        )
        
        # Prepare data for Chart.js
        labels = []
        top_oil = []
        amb = []
        bot_oil = []
        
        # Readings are returned newest first (ORDER BY id DESC in get_readings?)
        # Let's check get_readings implementation or assume standard DESC.
        # Usually for graphs we want oldest -> newest.
        
        # Reversing to get chronological order
        for r in reversed(readings):
            # r[1] is 'YYYY/MM/DD HH:MM:SS'
            time_str = r[1].split(' ')[1][:5] # HH:MM
            labels.append(time_str)
            top_oil.append(r[2])
            amb.append(r[3])
            bot_oil.append(r[4])

        return jsonify({
            "labels": labels,
            "datasets": [
                {"label": "Top Oil", "data": top_oil, "borderColor": "#ef4444", "backgroundColor": "rgba(239, 68, 68, 0.2)"},
                {"label": "Ambient", "data": amb, "borderColor": "#3b82f6", "backgroundColor": "rgba(59, 130, 246, 0.2)"},
                {"label": "Bottom Oil", "data": bot_oil, "borderColor": "#eab308", "backgroundColor": "rgba(234, 179, 8, 0.2)"}
            ]
        })

    except Exception as e:
        logger.error(f"Twin History Error: {e}")
        return jsonify({"error": "Sunucu hatası meydana geldi."}), 500

@app.route('/api/status')
@login_required # Secured status endpoint
def status():
    # Public status is fine, or protect if needed
    return jsonify({
        "running": is_running,
        "interval": scrape_interval,
        "last_updates": last_scrape_status
    })

# --- Transformer Management API ---

@app.route('/api/transformers', methods=['GET'])
@login_required # Anyone logged in can view
def get_transformers():
    # Return list of transformers
    t_list = db.get_transformers(active_only=False)
    # Format: id, name, ip_url, username, password, city, lat, lon
    result = []
    for t in t_list:
        result.append({
            "id": t[0],
            "name": t[1],
            "url": t[2],
            "username": t[3],
            # Hide password for security
            "city_name": t[5],
            "latitude": t[6],
            "longitude": t[7],
            "is_active": True 
        })
    return jsonify(result)

@app.route('/api/transformers', methods=['POST'])
@login_required
@admin_required
def add_transformer():
    data = request.json
    name = data.get('name')
    url = data.get('url')
    username = data.get('username')
    password = data.get('password')
    city = data.get('city_name')
    
    if not all([name, url, username, password]):
        return jsonify({"status": "error", "message": "Missing fields"}), 400
        
    t_id, err = db.add_transformer(name, url, username, password)
    if t_id:
        # Handle Location
        lat = data.get('latitude')
        lon = data.get('longitude')
        
        # If explicit coordinates provided (from Map)
        if lat is not None and lon is not None:
             # Use provided city name or reverse geocode (optional, here we rely on what user typed or map)
             display_name = city or f"Konum ({lat}, {lon})"
             db.update_transformer_location(t_id, display_name, lat, lon)
             # Trigger background backfill
             try:
                threading.Thread(target=backfill_weather, args=(t_id, lat, lon, display_name)).start()
             except Exception as e:
                logger.error(f"Weather backfill trigger error: {e}")
                
        # Fallback: If only city name provided (Legacy/Quick Add)
        elif city:
            coords = weather_service.get_coordinates(city)
            if coords:
                lat, lon, resolved_name = coords
                db.update_transformer_location(t_id, resolved_name, lat, lon)
                
                # Trigger background backfill
                try:
                    threading.Thread(target=backfill_weather, args=(t_id, lat, lon, resolved_name)).start()
                except Exception as e:
                     logger.error(f"Weather backfill trigger error: {e}")

        return jsonify({"status": "success", "id": t_id})
    return jsonify({"status": "error", "message": err}), 500

def backfill_weather(t_id, lat, lon, resolved_name):
    try:
        end_date = time.strftime("%Y-%m-%d")
        start_date = (pd.to_datetime(end_date) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        logger.info(f"Backfilling weather for {resolved_name} from {start_date}...")
        hist_data = weather_service.get_historical_weather(lat, lon, start_date, end_date)
        db.insert_weather_data(t_id, hist_data)
        logger.info(f"Weather backfill complete for {resolved_name}.")
    except Exception as e:
        logger.error(f"Weather backfill error: {e}")

@app.route('/api/transformers/<int:t_id>', methods=['PUT'])
@login_required
@admin_required
def update_transformer(t_id):
    data = request.json
    name = data.get('name')
    url = data.get('url')
    username = data.get('username')
    password = data.get('password')
    city = data.get('city_name')
    
    current = db.get_transformer_by_id(t_id)
    if not current:
         return jsonify({"status": "error", "message": "Transformer not found"}), 404
         
    # Keep old password if not provided
    if not password:
        password = current[4]

    success, err = db.update_transformer(t_id, name, url, username, password)
    
    if success:
        # Handle Location Update
        lat = data.get('latitude')
        lon = data.get('longitude')
        
        # Check if we need to update location
        should_update_loc = False
        new_lat, new_lon, new_name = None, None, None
        
        if lat is not None and lon is not None:
             # Map selection takes precedence
             should_update_loc = True
             new_lat, new_lon = lat, lon
             new_name = city or f"Konum ({lat}, {lon})"
        elif city and city != current[5]:
             # Text search fallback
             coords = weather_service.get_coordinates(city)
             if coords:
                 should_update_loc = True
                 new_lat, new_lon, new_name = coords
                 
        if should_update_loc:
             db.update_transformer_location(t_id, new_name, new_lat, new_lon)
             try:
                threading.Thread(target=backfill_weather, args=(t_id, new_lat, new_lon, new_name)).start()
             except Exception as e:
                  logger.error(f"Weather backfill trigger error: {e}")
                     
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": err}), 500

@app.route('/api/transformers/<int:t_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_transformer(t_id):
    success, err = db.delete_transformer(t_id)
    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": err}), 500

# --- Data API ---

@app.route('/api/data')
@login_required
def get_data():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        trafo_id = request.args.get('trafo_id')
        date_filter = request.args.get('date')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search_filter = request.args.get('search')
        
        if trafo_id: trafo_id = int(trafo_id)
        if not date_filter: 
            date_filter = None
        else:
            # Timestamp in DB is YYYY/MM/DD, input is YYYY-MM-DD
            date_filter = date_filter.replace('-', '/')
            
        if not search_filter: search_filter = None
        
    except ValueError:
        page = 1
        limit = 100
        trafo_id = None
        date_filter = None
        start_date = None
        end_date = None
        search_filter = None

    offset = (page - 1) * limit
    
    total_count = db.get_reading_count(trafo_id=trafo_id, date_filter=date_filter, search_filter=search_filter, start_date=start_date, end_date=end_date)
    readings = db.get_readings(trafo_id=trafo_id, limit=limit, offset=offset, date_filter=date_filter, search_filter=search_filter, start_date=start_date, end_date=end_date)
    
    # Format for frontend (normalized DB returns tuples)
    # id, sensor_timestamp, sensor1, sensor2, sensor3, sensor4, weather_temp
    data = []
    for r in readings:
        try:
            # Check if weather_temp exists (tuple length 7)
            w_temp = r[6] if len(r) > 6 else None
            
            data.append({
                "id": r[0],
                "time": r[1],
                "sensor1": r[2],
                "sensor2": r[3],
                "sensor3": r[4],
                "sensor4": r[5],
                "weather_temp": w_temp
            })
        except Exception as e:
            logger.error(f"API: error parsing row {r[0]}: {e}")
            continue
            
    return jsonify({
        "data": data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "pages": (total_count + limit - 1) // limit if limit > 0 else 0
        }
    })

@app.route('/api/export')
@login_required
def export_excel():
    try:
        trafo_id = request.args.get('trafo_id')
        year = request.args.get('year')
        month = request.args.get('month')
        
        logger.info(f"API EXPORT RECEIVED: trafo_id={trafo_id}, year={year}, month={month}")
        
        if trafo_id: trafo_id = int(trafo_id)
        if year: year = int(year)
        if month: month = int(month)
        
        # Determine filename
        filename = "sensor_verileri"
        if trafo_id:
             t = db.get_transformer_by_id(trafo_id)
             if t:
                 filename += f"_{t[1].strip().replace(' ', '_')}"
        if year:
             filename += f"_{year}"
             if month:
                  filename += f"_{month:02d}"
        filename += ".xlsx"

        logger.info(f"Exporting data for Trafo ID: {trafo_id}, Year: {year}, Month: {month}...")

        # Get DataFrame
        df = db.get_readings_dataframe(trafo_id=trafo_id, year=year, month=month)
        
        if df.empty:
            return "Veri bulunamadı.", 404

        # Create Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='SensorVerileri')
            
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Export Error: {e}")
        return jsonify({"status": "error", "message": "Sunucu hatası meydana geldi."}), 500

@app.route('/api/scrape', methods=['POST'])
@login_required
@admin_required
def manual_scrape():
    # Trigger a single scrape for a specific transformer
    try:
        data = request.json or {}
        trafo_id = data.get('trafo_id')
        
        if not trafo_id:
             transformers = db.get_transformers()
             if transformers:
                 t = transformers[0]
                 trafo_id = t[0]
             else:
                 return jsonify({"status": "error", "message": "No transformers configured."}), 400

        # Get details
        t = db.get_transformer_by_id(trafo_id)
        if not t:
            return jsonify({"status": "error", "message": "Transformer not found."}), 404
            
        # t: id, name, url, username, password, city, lat, lon
        t_id, t_name, t_url, t_user, t_pass = t[:5]
        
        logger.info(f"Manual-Scraper: Scraping '{t_name}'...")
        
        s = ApiScraper()
        last_ts = db.get_latest_timestamp(t_id)
        
        # Ensure login
        login_success, login_msg = s.login(t_url, t_user, t_pass)
        
        if not login_success:
             return jsonify({"status": "error", "message": f"Login Hatası ({t_name}): {login_msg}"}), 500

        success, scrape_data = s.scrape_data(start_timestamp=last_ts)
        
        if success:
            success_db, count = db.insert_reading(t_id, t_url, scrape_data)
            
            # Update last status
            global last_scrape_status
            last_scrape_status[t_id] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            return jsonify({
                "status": "success", 
                "message": f"Veri çekildi ({t_name}).", 
                "total_fetched": len(scrape_data.get("table_rows", [])),
                "new_rows": count
            })
        else:
            return jsonify({"status": "error", "message": f"Veri çekilemedi: {scrape_data}"}), 500
    except Exception as e:
        logger.error(f"Manual Scrape Error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": "Sunucu hatası meydana geldi."}), 500

# --- Simulation API ---

def _prepare_simulation_data(trafo_id, load_factor, start_date=None, end_date=None):
    """Helper to fetch and prepare data for simulation/export with thermal warm-up."""
    # 1. Determine Fetch Range (with 24h warm-up)
    fetch_start = start_date
    if start_date:
        try:
             # Try to parse start_date to subtract 24 hours
             # Format could be YYYY-MM-DD or YYYY-MM-DD HH:MM
             clean_start = start_date.replace('T', ' ').replace('/', '-')
             if len(clean_start) == 10: clean_start += " 00:00:00"
             dt_start = pd.to_datetime(clean_start)
             fetch_start = (dt_start - pd.Timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
             logger.info(f"Simulation Warm-up: Fetching from {fetch_start} to stabilize state.")
        except Exception as e:
             logger.warning(f"Warm-up date calc error: {e}")

    limit = 500
    if start_date or end_date:
        limit = 100000 
        
    readings = db.get_readings(trafo_id=int(trafo_id), limit=limit, start_date=fetch_start, end_date=end_date)
    
    data_rows = []
    # Reverse DESC to ASC
    for r in reversed(readings):
         row = {
             "sensor_timestamp": r[1],
             "sensor2": r[3], # Ambient
             "sensor1": r[2], # Top
             "sensor3": r[4]  # Bottom
         }
         data_rows.append(row)
         
    # 2. Run Simulation
    sim_results = simulation_engine.run_simulation(data_rows, load_factor)
    
    # 3. Filter results to return ONLY the requested range (if start_date provided)
    if start_date:
        try:
            # Normalize requested start for comparison
            req_start = pd.to_datetime(start_date.replace('T', ' ').replace('/', '-'))
            filtered = []
            for r in sim_results:
                ts_str = r['sensor_timestamp'].replace('/', '-')
                if pd.to_datetime(ts_str) >= req_start:
                    filtered.append(r)
            return filtered
        except Exception as e:
            logger.error(f"Filtering Error: {e}")
            return sim_results
            
    return sim_results

@app.route('/api/simulation/hermetic')
@login_required
def get_simulation_data():
    try:
        trafo_id = request.args.get('trafo_id')
        if not trafo_id:
            return jsonify({"status": "error", "message": "Missing trafo_id"}), 400
        
        load_factor = float(request.args.get('load_factor', 1.0))
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        sim_results = _prepare_simulation_data(trafo_id, load_factor, start_date, end_date)
        return jsonify({"data": sim_results})
        
    except Exception as e:
         logger.error(f"Simulation Error: {e}")
         return jsonify({"status": "error", "message": "Sunucu hatası meydana geldi."}), 500

@app.route('/api/simulation/export')
@login_required
def export_simulation():
    try:
        trafo_id = request.args.get('trafo_id')
        load_factor = float(request.args.get('load_factor', 80.0)) / 100.0
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not trafo_id: 
            return "Missing trafo_id", 400
            
        sim_results = _prepare_simulation_data(trafo_id, load_factor, start_date, end_date)
        
        # Create DataFrame
        export_data = []
        for r in sim_results:
            export_data.append({
                "Zaman": r.get('sensor_timestamp'),
                "Ortam Sicakligi": r.get('sensor2'),
                "FDM Ust Yag": r.get('sensor1'),
                "FDM Alt Yag": r.get('sensor3'),
                "Hermetik Ust Yag": r.get('hermetic_top_oil_C'),
                "Hermetik Alt Yag": r.get('hermetic_bottom_oil_C'),
                "Delta Ust": r.get('delta_top_C'),
                "Delta Alt": r.get('delta_bottom_C')
            })
            
        df = pd.DataFrame(export_data)
        
        # Determine filename
        t_name = "Trafo"
        t = db.get_transformer_by_id(trafo_id)
        if t: t_name = t[1].strip().replace(" ", "_")
        
        filename = f"Analiz_{t_name}_LF{load_factor}.xlsx"
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Analiz')
            
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
         logger.error(f"Excel Export Error: {e}")
         return "Sunucu hatası meydana geldi.", 500

@app.route('/api/toggle-auto', methods=['POST'])
@login_required
@admin_required
def toggle_auto():
    global is_running, scraper_thread
    req = request.json
    target_state = req.get("state") # true/false
    
    if target_state and not is_running:
        is_running = True
        scraper_thread = threading.Thread(target=background_scraper)
        scraper_thread.start()
    elif not target_state and is_running:
        is_running = False
        if scraper_thread:
            pass
            
    return jsonify({"status": "success", "running": is_running})

# --- User Management API ---

@app.route('/api/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    users_list = db.get_all_users()
    # id, username, role, created_at
    result = []
    for u in users_list:
        result.append({
            "id": u[0],
            "username": u[1],
            "role": u[2],
            "created_at": u[3]
        })
    return jsonify(result)

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def add_user():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'user')
    
    if not username or not password:
         return jsonify({"status": "error", "message": "Missing fields"}), 400
         
    # Check if exists
    if db.get_user_by_username(username):
         return jsonify({"status": "error", "message": "Username exists"}), 400
         
    success, err = db.create_user(username, password, role)
    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": err}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    data = request.json
    password = data.get('password')
    role = data.get('role')
    
    # Don't allow changing own role if you are the only admin or similar logic (simplified for now)
    
    if role:
        success, err = db.update_user_role(user_id, role)
        if not success: return jsonify({"status": "error", "message": err}), 500
        
    if password:
        from werkzeug.security import generate_password_hash
        pw_hash = generate_password_hash(password)
        success, err = db.update_user_password(user_id, pw_hash)
        if not success: return jsonify({"status": "error", "message": err}), 500
        
    return jsonify({"status": "success"})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({"status": "error", "message": "Cannot delete yourself"}), 400
        
    success, err = db.delete_user(user_id)
    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": err}), 500

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html', user=current_user)

@app.route('/api/reports/summary')
@login_required
def get_report_summary():
    try:
        trafo_id = request.args.get('trafo_id')
        if not trafo_id:
            return jsonify({"status": "error", "message": "Missing trafo_id"}), 400
        
        trafo_id = int(trafo_id)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        load_factor = float(request.args.get('load_factor', 80.0)) / 100.0
        
        # 1. Get Peaks from DB
        peaks = db.get_peak_stats(trafo_id, start_date=start_date, end_date=end_date)
        
        # Logic: If no specific date requested, we want to show the context around the HIGHEST peak.
        # Otherwise, the "Last 500" might not include the peak from months ago.
        sim_start = start_date
        sim_end = end_date
        
        if not start_date and not end_date:
            peak_ts = peaks.get('top', {}).get('ts')
            if peak_ts:
                # Assuming format YYYY/MM/DD ...
                try:
                    # extract YYYY/MM/DD
                    # it could be YYYY-MM-DD or YYYY/MM/DD
                    date_part = peak_ts.split(' ')[0].replace('/', '-') 
                    sim_start = date_part + " 00:00:00"
                    sim_end = date_part + " 23:59:59"
                    logger.info(f"Auto-focusing report on Peak Date: {date_part}")
                except Exception as e:
                    logger.warning(f"Could not parse peak timestamp for auto-focus: {e}")

        # 2. Get Top 5 High Values (Keep these based on user filter, or global if None)
        # Verify if we want Top 5 of THAT DAY or Global? usually "Top 5 High Values" implies Global context, 
        # but the request says "create data according to that date". 
        # Let's keep Top 5 respecting the explicit user filter (Global if None).
        top5_top = db.get_top_high_values(trafo_id, 'sensor1', limit=5, start_date=start_date, end_date=end_date)
        top5_bot = db.get_top_high_values(trafo_id, 'sensor3', limit=5, start_date=start_date, end_date=end_date)
        
        # 3. Get Comparative data (Chart & Simulation)
        # Now using the focused range if applicable
        sim_results = _prepare_simulation_data(trafo_id, load_factor=load_factor, start_date=sim_start, end_date=sim_end)
        
        # 4. Find Simulation Values AT THE SAME TIMESTAMP as the MEASURED Peaks
        # 4. Find Simulation Values AT THE SAME TIMESTAMP as the MEASURED Peaks
        # Improved robustness: Closest match logic
        sim_peaks = {
            "top": {"val": None, "ts": None},
            "bot": {"val": None, "ts": None},
            "amb": {"val": None, "ts": None}
        }
        
        # Pre-convert all sim timestamps for comparison
        sim_data_with_ts = []
        for r in sim_results:
            try:
                sim_data_with_ts.append({
                    "dt": pd.to_datetime(str(r['sensor_timestamp']).replace('/', '-').replace('T', ' ')),
                    "row": r
                })
            except: continue

        for peak_type in ['top', 'bot', 'amb']:
            p_ts_str = peaks.get(peak_type, {}).get('ts')
            if not p_ts_str or not sim_data_with_ts: continue
            
            try:
                target_dt = pd.to_datetime(p_ts_str.replace('/', '-').replace('T', ' '))
                best_row = None
                min_diff = float('inf')
                
                for item in sim_data_with_ts:
                    diff = abs((item['dt'] - target_dt).total_seconds())
                    if diff < min_diff:
                        min_diff = diff
                        best_row = item['row']
                
                # Accept if within 20 minutes (1200s)
                if min_diff <= 1200:
                    if peak_type == 'top':
                        sim_peaks['top'] = {"val": best_row.get('hermetic_top_oil_C'), "ts": p_ts_str}
                    elif peak_type == 'bot':
                        sim_peaks['bot'] = {"val": best_row.get('hermetic_bottom_oil_C'), "ts": p_ts_str}
                    elif peak_type == 'amb':
                        sim_peaks['amb'] = {"val": best_row.get('sensor2'), "ts": p_ts_str}
            except Exception as e:
                logger.warning(f"Peak lookup error for {peak_type}: {e}")

        # 5. Global Simulation Maximums in the range
        sim_global_max = {"top": None, "bot": None}
        if sim_results:
            try:
                top_max = max(r.get('hermetic_top_oil_C', 0) for r in sim_results)
                bot_max = max(r.get('hermetic_bottom_oil_C', 0) for r in sim_results)
                sim_global_max = {"top": top_max, "bot": bot_max}
            except: pass
        
        return jsonify({
            "peaks": peaks,
            "sim_peaks": sim_peaks,
            "sim_global_max": sim_global_max,
            "comparison": sim_results,
            "top_5_top": top5_top,
            "top_5_bot": top5_bot
        })
    except Exception as e:
        logger.error(f"Report API Error: {e}")
        return jsonify({"status": "error", "message": "Sunucu hatası meydana geldi."}), 500

@app.route('/setup')
def setup():
    if is_setup_completed():
        return redirect(url_for('login'))
    return render_template('setup.html')

@app.route('/api/save-config', methods=['POST'])
def save_config():
    try:
        data = request.json
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
            
        with open(CONFIG_PATH, 'w') as f:
            json.dump(data, f, indent=4)
        
        # Yeni veritabanını başlat
        db = DatabaseManager()
        db.init_db()
        
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Config kaydetme hatası: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Ensure templates folder exists
    if not os.path.exists('templates'):
        os.makedirs('templates')
    if not os.path.exists('static'):
        os.makedirs('static')

    print("---------------------------------------------------")
    print("   SENSOR PORTAL SERVER STARTING - VERSION 3.0")
    print("   Multi-Transformer Support Enabled")
    print("---------------------------------------------------")

    # Start the background scraper thread immediately
    if is_running:
        logger.info("Starting background scraper thread...")
        scraper_thread = threading.Thread(target=background_scraper)
        scraper_thread.start()
        
    # Get port from env (Cloud Run uses PORT)
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port, use_reloader=False)
# Force reload - 3
