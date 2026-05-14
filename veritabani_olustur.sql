-- FDM Sensor PostgreSQL Veritabanı Oluşturma Scripti
-- Bu betiği pgAdmin Query Tool ile veya komut satırından `psql -U postgres -f veritabani_olustur.sql` şeklinde çalıştırabilirsiniz.

-- 1. Veritabanının oluşturulması (Eğer veritabanı dışarıdan oluşturulmadıysa)
-- Not: pgAdmin kullanarak çalıştıracaksanız "CREATE DATABASE" sonrasındaki \c komutu çalışmayabilir.
-- En doğrusu önce fdmsensor veritabanını oluşturup, bu scripti o veritabanı içinde çalıştırmaktır.

-- CREATE DATABASE fdmsensor;
-- \c fdmsensor;

-- 1. Transformers (Trafolar) Tablosu
CREATE TABLE IF NOT EXISTS transformers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    ip_url TEXT NOT NULL,
    username TEXT,
    password TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    city_name TEXT,
    latitude REAL,
    longitude REAL
);

-- 2. Users (Kullanıcılar) Tablosu
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Sensor Readings (Log/Yedek Amaçlı) Tablosu
CREATE TABLE IF NOT EXISTS sensor_readings (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_url TEXT,
    raw_data TEXT
);

-- 4. Sensor Data Rows (Trafolara ait Sensör Verisi) Tablosu
CREATE TABLE IF NOT EXISTS sensor_data_rows (
    id SERIAL PRIMARY KEY,
    sensor_timestamp TIMESTAMP,
    sensor1 REAL,
    sensor2 REAL,
    sensor3 REAL,
    sensor4 REAL,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trafo_id INTEGER,
    CONSTRAINT uq_sensor_timestamp_trafo UNIQUE(sensor_timestamp, trafo_id)
);

-- 5. Weather Data (Hava Durumu) Tablosu
CREATE TABLE IF NOT EXISTS weather_data (
    id SERIAL PRIMARY KEY,
    trafo_id INTEGER,
    timestamp TIMESTAMP,
    temperature REAL,
    CONSTRAINT uq_weather_timestamp_trafo UNIQUE(trafo_id, timestamp)
);

-- Varsayılan Kullanıcı ve Trafo Kaydı - Uygulama ilk açıldığında otomatik eklenecektir.
-- Bu tabloları manuel oluşturduğunuzda FDM Sensor uygulaması ilk bağlandığında,
-- tabloların var olduğunu görecek ve sadece içleri boşsa varsayılan kayıtları (`grid` kullanıcısını) girecektir.
