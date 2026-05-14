import time
import json
import logging
import requests
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from urllib.parse import urlparse

# Selenium imports moved inside SensorScraper to avoid dependency issues on Cloud Run
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# ...

logger = logging.getLogger(__name__)

class SensorScraper:
    def __init__(self):
        self.driver = None

    def start_browser(self):
        """Starts the Chrome browser safely."""
        logger.info("Scraper: start_browser called")
        
        # Lazy import
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
             logger.error("Selenium not installed. Cannot start browser.")
             return

        if self.driver is not None:
             return
        
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.set_capability("pageLoadStrategy", "eager")
        
        logger.info("Scraper: installing driver...")
        try:
            service = Service(ChromeDriverManager().install())
            logger.info("Scraper: driver installed. Initializing webdriver...")
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Scraper: webdriver initialized")
        except Exception as e:
            logger.error(f"Scraper: Failed to start browser: {e}")
            raise

    def login(self, url, username, password):
        """Logs into the website."""
        try:
            logger.info("Scraper: login started")
            if not self.driver:
                self.start_browser()
            
            logger.info(f"Scraper: getting {url}")
            self.driver.get(url)
            
            time.sleep(2)
            logger.debug(f"Scraper: current url is {self.driver.current_url}")
            
            if "login" in self.driver.current_url:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                wait = WebDriverWait(self.driver, 10)
                
                # Role Selection
                try:
                    target_role = username.lower()
                    logger.debug(f"Scraper: selecting role '{target_role}'")
                    role_input = self.driver.find_element(By.CSS_SELECTOR, f"input[type='radio'][value='{target_role}']")
                    self.driver.execute_script("arguments[0].click();", role_input)
                except Exception as e:
                    logger.warning(f"Scraper: Role selection error for '{username}': {e}")

                # Password
                logger.debug("Scraper: waiting for password input")
                pass_input = wait.until(EC.visibility_of_element_located((By.NAME, "password")))
                pass_input.clear()
                pass_input.send_keys(password)
                
                # Login Button
                logger.debug("Scraper: clicking login button")
                try:
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, "button.login-form__button")
                    self.driver.execute_script("arguments[0].click();", login_btn) 
                except:
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if "Login" in btn.text or "Giriş" in btn.text:
                            btn.click()
                            break
                
                # Wait for navigation
                logger.debug("Scraper: waiting for login navigation...")
                try:
                    wait.until(lambda d: "datalog" in d.current_url or len(d.find_elements(By.CLASS_NAME, "el-table")) > 0)
                    logger.info("Scraper: login navigation successful")
                except Exception as e:
                    logger.warning(f"Scraper: Navigation wait timed out: {e}")

            time.sleep(2)
            
            if "User does not exist" in self.driver.page_source or "password is incorrect" in self.driver.page_source:
                return False, "Login failed: User does not exist or password is incorrect."
            
            if "login" in self.driver.current_url:
                 return False, "Login failed: Still on login page."
                     
            return True, "Login step completed"
            
        except Exception as e:
            try:
                if self.driver:
                    self.driver.save_screenshot("login_exception.png")
            except:
                pass
            logger.error(f"Scraper: Login exception: {e}")
            return False, f"Login failed: {str(e)}"

    def scrape_data(self):
        """Scrapes the data from the current page."""
        try:
            if not self.driver:
                return False, "Browser not started"

            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            wait = WebDriverWait(self.driver, 15)
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "el-table__row")))
            except:
                logger.warning(f"Scraper: Timeout waiting for rows. URL: {self.driver.current_url}")

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            data = []
            table_body = soup.find('tbody')
            if table_body:
                rows = table_body.find_all('tr', class_='el-table__row')
                logger.info(f"Scraper: Found {len(rows)} rows via BS4")
                
                for row in rows:
                    if not row: continue
                    cols = row.find_all('td')
                    
                    if len(cols) >= 6:
                        row_data = {
                            "id": cols[0].get_text(strip=True),
                            "time": cols[1].get_text(strip=True),
                            "sensor1": cols[2].get_text(strip=True),
                            "sensor2": cols[3].get_text(strip=True),
                            "sensor3": cols[4].get_text(strip=True),
                            "sensor4": cols[5].get_text(strip=True)
                        }
                        data.append(row_data)
            
            if not data:
                return False, "No data rows found in table."
                
            return True, {"table_rows": data}
            
        except Exception as e:
            logger.error(f"Scraper: Scrape exception: {e}")
            return False, f"Scrape error: {str(e)}"

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

class ApiScraper:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.base_url = None

    def _get_api_url(self, url):
        parsed = urlparse(url)
        # parsed.netloc already contains hostname:port if port is present
        base = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base}/api/v1"

    def get_public_key(self):
        try:
            url = f"{self.base_url}/system/rsa/public-key"
            logger.debug(f"ApiScraper: Fetching public key from {url}")
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json().get("public_key")
            logger.error(f"ApiScraper: Failed to get public key: {response.text}")
            return None
        except Exception as e:
            logger.error(f"ApiScraper: Error fetching public key: {e}")
            return None

    def encrypt_data(self, data, public_key_str):
        """Encrypts data using RSA PKCS1_v1_5."""
        try:
            key = RSA.import_key(public_key_str)
            # Use PKCS1_v1_5 for consistency with gateway requirements
            cipher = PKCS1_v1_5.new(key)
            ciphertext = cipher.encrypt(data.encode('utf-8'))
            return base64.b64encode(ciphertext).decode('utf-8')
        except Exception as e:
            logger.error(f"ApiScraper: Encryption error: {e}")
            return None

    def login(self, url, username, password):
        self.base_url = self._get_api_url(url)
        logger.info(f"ApiScraper: Login initialized for {self.base_url}")
        
        public_key = self.get_public_key()
        if not public_key:
            return False, "Could not retrieve public key"

        encrypted_username = self.encrypt_data(username, public_key)
        encrypted_password = self.encrypt_data(password, public_key)
        
        if not encrypted_username or not encrypted_password:
            return False, "Encryption failed"

        login_url = f"{self.base_url}/auth/rsa/token/admin"
        
        # Standart OAuth2 yuklemesi
        payload = {
            "grant_type": "password",
            "username": encrypted_username,
            "password": encrypted_password,
            "client_id": "admin",
            "client_secret": ""
        }
        # Bazı sunucular client_id'yi Basic Auth olarak bekler
        import base64
        auth_str = base64.b64encode(b"admin:").decode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_str}"
        }
        
        try:
            logger.debug(f"ApiScraper: Sending login request to {login_url}")
            response = self.session.post(login_url, data=payload, headers=headers, timeout=10)
            
            # Eger 'invalid_client' alirsak, Auth header'siz deniyoruz
            if response.status_code != 200 and "invalid_client" in response.text:
                logger.warning("ApiScraper: 'invalid_client' with Auth header. Retrying without it...")
                headers.pop("Authorization", None)
                response = self.session.post(login_url, data=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                self.token = response.json().get("access_token")
                logger.info("ApiScraper: Login successful")
                return True, "Login successful"
            else:
                return False, f"Login failed: {response.text}"
        except Exception as e:
            return False, f"Login exception: {str(e)}"

    def scrape_data(self, start_timestamp=None):
        if not self.token:
            return False, "Not logged in"
            
        columns_url = f"{self.base_url}/data/datalog/0/columns"
        count_url = f"{self.base_url}/data/datalog/0/data/totalcount"
        data_url = f"{self.base_url}/data/datalog/0/data"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            end_time = int(time.time())
            
            if start_timestamp:
                import datetime
                dt = datetime.datetime.strptime(start_timestamp, "%Y/%m/%d %H:%M:%S")
                start_time = int(dt.timestamp())
                logger.info(f"ApiScraper: Incremental scrape from {start_timestamp} ({start_time})")
            else:
                start_time = end_time - (365 * 24 * 3600) 
                logger.info("ApiScraper: Full history scrape (last 1 year)")

            params_count = {
                "start": start_time,
                "end": end_time,
                "order": ""
            }
            
            count_res = self.session.get(count_url, headers=headers, params=params_count, timeout=10)
            if count_res.status_code != 200:
                return False, f"Failed to get record count: {count_res.text}"
            
            total_count = count_res.json().get("total", 0)
            logger.info(f"ApiScraper: Found {total_count} records")
            
            if total_count == 0:
                return False, "No data available."
            
            all_formatted_rows = []
            current_index = 1
            max_pages = 200 
            
            while True:
                params_data = {
                    "totalcount": total_count,
                    "start": start_time,
                    "end": end_time,
                    "index": current_index, 
                    "order": "" 
                }
                
                logger.debug(f"ApiScraper: Fetching page {current_index}...")
                data_res = self.session.get(data_url, headers=headers, params=params_data, timeout=30)
                
                if data_res.status_code != 200:
                    logger.error(f"ApiScraper: Page {current_index} failed: {data_res.text}")
                    break 
                    
                json_data = data_res.json()
                raw_rows = json_data.get("data", [])
                
                if not raw_rows:
                    break
                
                # Format data
                for row in raw_rows:
                    ds = row.get("ds", [])
                    item = {
                        "id": str(row.get("id")),
                        "time": row.get("ts"),
                        "sensor1": str(ds[0]) if len(ds) > 0 else "",
                        "sensor2": str(ds[1]) if len(ds) > 1 else "",
                        "sensor3": str(ds[2]) if len(ds) > 2 else "",
                        "sensor4": str(ds[3]) if len(ds) > 3 else ""
                    }
                    all_formatted_rows.append(item)
                
                if len(all_formatted_rows) >= total_count:
                    break
                
                current_index += 1
                if current_index > max_pages:
                    logger.warning("ApiScraper: Values exceeded max pages safety limit.")
                    break
                    
                time.sleep(0.5)

            return True, {"table_rows": all_formatted_rows}
            
        except Exception as e:
            logger.error(f"ApiScraper: Scrape exception: {e}")
            return False, f"Scrape error: {str(e)}"

    def close(self):
        self.session.close()
