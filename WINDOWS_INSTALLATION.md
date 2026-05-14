# Windows Server Kurulum Rehberi (FDMSensor)

Bu doküman, uygulamanın bir Windows Sunucu (Windows Server 2016/2019/2022 vb.) ortamına doğrudan (Docker olmadan) kurulması için gerekli adımları açıklar.

## 1. Sistem Gereksinimleri
Sunucu üzerinde aşağıdaki kurulumların yapılmış olması gerekmektedir:
- **Python:** 3.8 veya üzeri (Kurulum sırasında `Add Python to PATH` seçeneğinin işaretli olduğundan emin olun).
- **Google Chrome:** Sistemde veri çekmek (Scraping) için Chrome tarayıcısı yüklü olmalıdır. Selenium webdriver, Chrome sürümünüzü tanıyıp internet üzerinden uyumlu sürücüyü otomatik indirecektir, ancak temel tarayıcının sistemde kurulu olması şarttır.

## 2. Kurulum Adımları
Komut İstemi veya PowerShell'i **Yönetici olarak** çalıştırın ve aşağıdaki adımları sırasıyla uygulayın.

### 2.1. Proje Dizinine Gitme
Proje dosyalarını sunucuda ilgili klasöre (örneğin `C:\FDMSensor`) kopyaladığınızı varsayarak:
```cmd
cd C:\FDMSensor
```

### 2.2. Sanal Ortam (Virtual Environment) Oluşturma ve Aktifleştirme
Sanal ortam oluşturarak bağımlılıkların sistemdeki diğer Python uygulamalarıyla çakışmasını engelleyin.
```cmd
python -m venv .venv
```
Aktifleştirmek için:
```cmd
.venv\Scripts\activate
```
*(Aktifleştirme başarılı olduğunda satırın başında `(.venv)` ibaresini göreceksiniz.)*

### 2.3. Bağımlılıkların Yüklenmesi
```cmd
pip install -r requirements.txt
```

### 2.4. Çevresel Değişken Dosyasının (.env) Hazırlanması
Kurulumla gelen `.env.example` dosyasının adını `.env` olarak değiştirin ve düzenleyin:
```cmd
copy .env.example .env
```
Ardından dosyayı Notepad vb. ile açın:
- `SECRET_KEY`: Güvenli bir metin girin (Örn: `benim_cok_gizli_anahtarim`).
- `DB_TYPE`: `sqlite` veya `postgres` olarak bırakabilirsiniz. Eğer `sqlite` derseniz uygulama sunucu içinde dosya tabanlı bir lokal veritabanı kuracaktır (Tavsiye edilen en pratik Windows çözümüdür). Eğer sistemde bir PostgreSQL kuruluysa `postgres` diyebilirsiniz.
- `DATABASE_URL`: Eğer PostgreSQL kullanacaksanız geçerli bağlantı linki (Örn: `postgresql://postgres:sifre@localhost:5432/fdm`).
- `DEFAULT_ADMIN_PASSWORD`: Panelinize ilk girişte kullanacağınız şifre (Varsayılan: `grid2026-` kalsın isterseniz değiştirmeyebilirsiniz).

## 3. Uygulamayı Çalıştırma (Manuel Test)
Uygulama Windows üzerinden Gunicorn ile uyumlu olmadığı için **Waitress** web sunucusu (prodüksiyon için uygundur) kullanılarak hazırlanmıştır. Uygulamanın çalışıp çalışmadığını test etmek için:
```cmd
python waitress_server.py
```
Herhangi bir hata mesajı yoksa sunucudaki bir tarayıcıdan (veya port izinleri açıksa kendi bilgisayarınızdan) `http://localhost:5001` (veya `http://SUNUCU_IP:5001`) adresine giderek arayüzü kontrol edebilirsiniz.

## 4. Uygulamayı Arka Planda Servis Olarak Çalıştırma (Önerilen Canlı Ortam Kullanımı)
Windows Sunucu her yeniden başladığında uygulamanın otomatik açılması (ve arka planda sürekli çalışması) için en pratik yöntem uygulamanın bir "Windows Servisi" haline getirilmesidir.
Bunun için **NSSM (Non-Sucking Service Manager)** kullanımı önerilir.

### Adım Adım Servis Oluşturma:
1. **[NSSM'i indirin](https://nssm.cc/download)** ve içindeki `win64/nssm.exe` dosyasını örneğin `C:\FDMSensor\nssm.exe` yoluna kopyalayın.
2. Yönetici olarak açılmış komut satırında şu komutu çalıştırarak ayar penceresini açın:
   ```cmd
   nssm.exe install FDMSensor
   ```
3. Açılan GUI penceresinde "Application" sekmesinde şu bilgileri doldurun:
   - **Path:** `C:\FDMSensor\.venv\Scripts\python.exe` (Sanal ortamdaki python yolu!)
   - **Arguments:** `waitress_server.py`
   - **Details tab:** "Display name": `FDM Sensor Web App` vb. belirtebilirsiniz.
   - **Environment tab:** Gerekirse PATH ayarı eklenebilir, ancak venv bunu genellikle kendi yönetir.
4. `Install Service` butonuna tıklayın.

### Servisi Başlatma ve Yönetme
Komut satırından servisi başlatmak için:
```cmd
nssm.exe start FDMSensor
```
Veya Windows'un yerleşik "Hizmetler (Services)" arayüzünden `FDM Sensor` vb. adıyla bulup Başlat/Durdur yapabilirsiniz.

Servisi bir daha tamamen kaldırmak isterseniz: `nssm.exe remove FDMSensor` komutunu çalıştırabilirsiniz.

## 5. Güvenlik Duvarı (Firewall)
Uygulamanıza dışarıdan (ağınızdan) erişilebilmesi için Windows Güvenlik Duvarı'nda **TCP 5001** (veya `.env` içinde belirlediğiniz diğer port) portuna "Inbound (Gelen)" kuralı oluşturarak izin vermeniz gerekir.
