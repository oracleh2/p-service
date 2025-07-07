-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Создание таблицы устройств
CREATE TABLE IF NOT EXISTS proxy_devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    device_type VARCHAR(50) NOT NULL CHECK (device_type IN ('android', 'usb_modem', 'raspberry_pi')),
    ip_address VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL CHECK (port > 0 AND port <= 65535),
    status VARCHAR(50) DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'busy', 'maintenance')),
    current_external_ip VARCHAR(45),
    operator VARCHAR(100),
    region VARCHAR(100),
    last_heartbeat TIMESTAMP,
    last_ip_rotation TIMESTAMP,
    rotation_interval INTEGER DEFAULT 600 CHECK (rotation_interval > 0),
    total_requests INTEGER DEFAULT 0 CHECK (total_requests >= 0),
    successful_requests INTEGER DEFAULT 0 CHECK (successful_requests >= 0),
    failed_requests INTEGER DEFAULT 0 CHECK (failed_requests >= 0),
    avg_response_time_ms INTEGER DEFAULT 0 CHECK (avg_response_time_ms >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы конфигурации ротации
CREATE TABLE IF NOT EXISTS rotation_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID NOT NULL REFERENCES proxy_devices(id) ON DELETE CASCADE,
    rotation_method VARCHAR(50) NOT NULL CHECK (rotation_method IN ('airplane_mode', 'data_toggle', 'api_call', 'network_reset')),
    rotation_interval INTEGER NOT NULL CHECK (rotation_interval > 0),
    auto_rotation BOOLEAN DEFAULT TRUE,
    rotation_url VARCHAR(500),
    auth_token VARCHAR(255),
    rotation_success_rate FLOAT DEFAULT 0.0 CHECK (rotation_success_rate >= 0.0 AND rotation_success_rate <= 1.0),
    last_successful_rotation TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(device_id)
);

-- Создание таблицы логов запросов
CREATE TABLE IF NOT EXISTS request_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    client_ip VARCHAR(45),
    target_url VARCHAR(1000),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER CHECK (response_time_ms >= 0),
    external_ip VARCHAR(45),
    user_agent TEXT,
    request_size INTEGER CHECK (request_size >= 0),
    response_size INTEGER CHECK (response_size >= 0),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы истории IP адресов
CREATE TABLE IF NOT EXISTS ip_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID NOT NULL REFERENCES proxy_devices(id) ON DELETE CASCADE,
    ip_address VARCHAR(45) NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_requests INTEGER DEFAULT 0 CHECK (total_requests >= 0),
    operator VARCHAR(100),
    geo_location VARCHAR(100),
    city VARCHAR(100),
    is_blocked BOOLEAN DEFAULT FALSE,
    blocked_reason TEXT,
    UNIQUE(device_id, ip_address)
);

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT TRUE,
    requests_limit INTEGER DEFAULT 10000 CHECK (requests_limit >= 0),
    requests_used INTEGER DEFAULT 0 CHECK (requests_used >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы статистики использования
CREATE TABLE IF NOT EXISTS usage_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    requests_count INTEGER DEFAULT 0 CHECK (requests_count >= 0),
    successful_requests INTEGER DEFAULT 0 CHECK (successful_requests >= 0),
    failed_requests INTEGER DEFAULT 0 CHECK (failed_requests >= 0),
    avg_response_time_ms INTEGER DEFAULT 0 CHECK (avg_response_time_ms >= 0),
    unique_ips_count INTEGER DEFAULT 0 CHECK (unique_ips_count >= 0),
    data_transferred_mb INTEGER DEFAULT 0 CHECK (data_transferred_mb >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(device_id, user_id, date)
);

-- Создание таблицы системной конфигурации
CREATE TABLE IF NOT EXISTS system_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    config_type VARCHAR(50) DEFAULT 'string' CHECK (config_type IN ('string', 'integer', 'boolean', 'json')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_proxy_devices_status ON proxy_devices(status);
CREATE INDEX IF NOT EXISTS idx_proxy_devices_last_heartbeat ON proxy_devices(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_request_logs_device_id ON request_logs(device_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_request_logs_client_ip ON request_logs(client_ip);
CREATE INDEX IF NOT EXISTS idx_ip_history_device_id ON ip_history(device_id);
CREATE INDEX IF NOT EXISTS idx_ip_history_ip_address ON ip_history(ip_address);
CREATE INDEX IF NOT EXISTS idx_usage_stats_device_id ON usage_stats(device_id);
CREATE INDEX IF NOT EXISTS idx_usage_stats_date ON usage_stats(date);
CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config(key);

-- Создание функции для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Создание триггеров для автоматического обновления updated_at
CREATE TRIGGER update_proxy_devices_updated_at BEFORE UPDATE ON proxy_devices FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_rotation_config_updated_at BEFORE UPDATE ON rotation_config FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON system_config FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Вставка начальных данных системной конфигурации
INSERT INTO system_config (key, value, description, config_type) VALUES
('rotation_interval', '600', 'Интервал автоматической ротации IP в секундах', 'integer'),
('auto_rotation_enabled', 'true', 'Включить автоматическую ротацию IP', 'boolean'),
('max_devices', '50', 'Максимальное количество устройств', 'integer'),
('requests_per_minute_limit', '100', 'Лимит запросов в минуту на устройство', 'integer'),
('heartbeat_timeout', '60', 'Таймаут heartbeat в секундах', 'integer'),
('rotation_timeout', '60', 'Таймаут ротации IP в секундах', 'integer'),
('log_retention_days', '30', 'Количество дней хранения логов', 'integer'),
('enable_alerts', 'true', 'Включить уведомления об ошибках', 'boolean'),
('alert_success_rate_threshold', '85', 'Порог успешности запросов для алертов (%)', 'integer'),
('device_offline_alert_minutes', '5', 'Время офлайн устройства для алерта (минуты)', 'integer')
ON CONFLICT (key) DO NOTHING;


-- Добавление новых полей в таблицу устройств
ALTER TABLE proxy_devices ADD COLUMN dedicated_port INTEGER UNIQUE;
ALTER TABLE proxy_devices ADD COLUMN proxy_username VARCHAR(255);
ALTER TABLE proxy_devices ADD COLUMN proxy_password VARCHAR(255);
ALTER TABLE proxy_devices ADD COLUMN proxy_enabled BOOLEAN DEFAULT TRUE;
