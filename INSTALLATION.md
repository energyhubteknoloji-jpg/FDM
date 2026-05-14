# FDMSensor Kurulum Dokümanı

Bu döküman, FDMSensor projesinin hem geliştirme hem de canlı ortamda kurulumu için gerekli adımları içerir.

## 1. Gereksinimler

- **Python:** 3.8 veya üzeri.
- **Google Chrome:** Scraper (Selenium) için güncel bir Chrome tarayıcısı gereklidir.
- **ChromeDriver:** Selenium tarafından otomatik olarak yönetilir (`webdriver-manager`), ancak sistemde Chrome yüklü olmalıdır.

## 2. Kurulum Adımları

### 2.1. Deponun Klonlanması ve Dizin Hazırlığı
```bash
cd FDMSensor
```

### 2.2. Otomatik Kurulum (Önerilen)
Linux ve macOS sistemler için hazırlanan kurulum scriptini kullanarak tüm bağımlılıkları ve sanal ortamı otomatik olarak kurabilirsiniz:
```bash
chmod +x setup.sh
./setup.sh
```

### 2.3. Manuel Kurulum
Bağımlılıkların manuel yüklenmesi için:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.4. Yapılandırma (Çevresel Değişkenler)
Uygulama hassas bilgileri ve veritabanı türünü yönetmek için `.env` dosyası kullanır. Şablon dosyasını kopyalayarak yeni bir `.env` oluşturun:
```bash
cp .env.example .env
```
Ardından `.env` dosyasını bir metin düzenleyici ile açın ve gerekli alanları doldurun:
- `SECRET_KEY`: Güvenlik için rastgele bir anahtar belirleyin.
- `DB_TYPE`: `sqlite` veya `postgres` olarak ayarlayın.
- `DATABASE_URL`: PostgreSQL bağlantı dizenizi buraya tanımlayın (Örn: `postgresql://postgres:pass@localhost/db`).

## 3. Veritabanı Kurulumu

Uygulama veritabanı olarak **SQLite** ve **PostgreSQL** mimarilerini esnek bir şekilde desteklemektedir. Ortam değişkenlerinden gelen `DB_TYPE` ayarına göre sistem uygun motoru seçer. 
SQLite seçildiğinde veritabanı `sensor_data.db` adıyla lokal olarak oluşacaktır. PostgreSQL için ise temiz tablolar belirtilen `DATABASE_URL` üzerine inşaa edilecektir. Eski verilerinizi taşımak için `migrate_to_postgres.py` aracını kullanabilirsiniz.

### 3.1. Varsayılan Kullanıcılar
Uygulama ilk açıldığında yönetici hesabı oluşturulur:
- **Kullanıcı Adı:** `grid`
- **Şifre:** `.env` dosyasında belirlediğiniz şifre (Varsayılan: `grid2026-`)

> [!IMPORTANT]
> Güvenlik için ilk girişi yaptıktan sonra şifrenizi uygulama üzerinden değiştirmeniz önerilir.

## 4. Uygulamayı Çalıştırma

### 4.1. Geliştirme Ortamı
Uygulamayı doğrudan Python ile başlatabilirsiniz:
```bash
python main.py
```
Uygulama varsayılan olarak `http://localhost:5001` adresinde çalışacaktır.

### 4.2. Docker Compose İle Kurulum (Önerilen)
Sistemin veritabanı ve arka plan servisleriyle en güvenilir şekilde çalışması için **Docker Compose** kullanılması önerilir.
Ana dizindeyken tek komutla hem PostgreSQL sunucusunu hem de web uygulamasını ayağa kaldırabilirsiniz:
```bash
docker-compose up -d --build
```
Bu işlem her iki servisi izole konteynerlarda ayağa bağlayacak ve portlarınızı senkronize edecektir.

## 5. Çevresel Değişkenler (.env)

Uygulama aşağıdaki değişkenleri kullanır:
- `SECRET_KEY`: Flask oturum güvenliği (CSRF vb.) için kritik öneme sahiptir.
- `DB_TYPE`: `sqlite` ya da `postgres`. Veritabanı motorunu tahsis eder.
- `DATABASE_URL`: PostgreSQL bağlantıları için uzak veya lokal sunucu rotası.
- `DEFAULT_ADMIN_PASSWORD`: İlk kurulum şifresi.
- `DEBUG`: Geliştirme modu (True/False).
- `PORT`: Uygulamanın çalışacağı port (Varsayılan: 5001).

## 6. Sistem Mimarisi
Projenin detaylı teknik mimarisi, veri akış şemaları ve güvenlik katmanları için [ARCHITECTURE.md](file:///Users/tamerturgut/FDMSensor/ARCHITECTURE.md) dosyasını inceleyebilirsiniz.
