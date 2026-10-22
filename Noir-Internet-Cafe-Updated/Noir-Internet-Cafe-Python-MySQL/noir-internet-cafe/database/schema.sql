-- NOIR Internet Cafe — MySQL 8.0+ / 8.4 LTS.
-- This schema creates no accounts, stations, bookings, payments, or sample data.
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(80) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('administrator','member') NOT NULL DEFAULT 'member',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id INT NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX (expires_at), INDEX (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(40) NOT NULL UNIQUE,
    hourly_rate DECIMAL(10,2) NOT NULL,
    maintenance BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CHECK (hourly_rate > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bookings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    station_id INT NOT NULL,
    user_id INT NULL,
    customer_name VARCHAR(80) NOT NULL,
    scheduled_at DATETIME(6) NOT NULL,
    status ENUM('reserved','checked_in','cancelled') NOT NULL DEFAULT 'reserved',
    created_by INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    -- A reservation holds this station immediately until check-in/cancellation.
    reserved_station_id INT GENERATED ALWAYS AS
        (CASE WHEN status='reserved' THEN station_id ELSE NULL END) STORED,
    UNIQUE KEY one_reservation_per_station (reserved_station_id),
    FOREIGN KEY (station_id) REFERENCES stations(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX (user_id, status), INDEX (scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cafe_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    station_id INT NOT NULL,
    user_id INT NULL,
    customer_name VARCHAR(80) NOT NULL,
    booking_id INT NULL UNIQUE,
    hourly_rate DECIMAL(10,2) NOT NULL,
    started_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NULL,
    planned_end_at DATETIME(6) NULL,
    started_by INT NOT NULL,
    active_station_id INT GENERATED ALWAYS AS
        (CASE WHEN ended_at IS NULL THEN station_id ELSE NULL END) STORED,
    UNIQUE KEY one_session_per_station (active_station_id),
    FOREIGN KEY (station_id) REFERENCES stations(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (started_by) REFERENCES users(id),
    INDEX (user_id, ended_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS invoices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_id INT NOT NULL UNIQUE,
    minutes INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by INT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES cafe_sessions(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    CHECK (minutes > 0), CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS payments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    invoice_id INT NOT NULL UNIQUE,
    amount DECIMAL(12,2) NOT NULL,
    method ENUM('cash','ewallet','bank') NOT NULL,
    reference VARCHAR(100) NULL,
    paid_at DATETIME(6) NOT NULL,
    received_by INT NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (received_by) REFERENCES users(id),
    INDEX (paid_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    actor_id INT NULL,
    action VARCHAR(50) NOT NULL,
    detail VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (actor_id) REFERENCES users(id), INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rate_limits (
    bucket_hash CHAR(64) PRIMARY KEY,
    attempts INT NOT NULL DEFAULT 0,
    expires_at DATETIME(6) NOT NULL,
    INDEX (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS assets (
 id INT PRIMARY KEY AUTO_INCREMENT,
 asset_tag VARCHAR(40) NOT NULL UNIQUE,
 name VARCHAR(80) NOT NULL,
 category VARCHAR(20) NOT NULL,
 station_id INT NULL UNIQUE,
 cpu VARCHAR(120) NOT NULL DEFAULT '',
 motherboard VARCHAR(120) NOT NULL DEFAULT '',
 ram_gb INT NOT NULL DEFAULT 0,
 storage VARCHAR(120) NOT NULL DEFAULT '',
 psu VARCHAR(120) NOT NULL DEFAULT '',
 input_devices VARCHAR(120) NOT NULL DEFAULT '',
 output_devices VARCHAR(120) NOT NULL DEFAULT '',
 nic VARCHAR(120) NOT NULL DEFAULT '',
 os_version VARCHAR(120) NOT NULL DEFAULT '',
 ip_address VARCHAR(15) NULL UNIQUE,
 mac_address VARCHAR(17) NULL UNIQUE,
 hostname VARCHAR(63) NOT NULL DEFAULT '',
 location VARCHAR(120) NOT NULL DEFAULT '',
 purchase_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
 status VARCHAR(20) NOT NULL DEFAULT 'active',
 security_status VARCHAR(20) NOT NULL DEFAULT 'not_checked',
 security_notes VARCHAR(500) NOT NULL DEFAULT '',
 checked_on VARCHAR(10) NOT NULL DEFAULT '',
 notes VARCHAR(500) NOT NULL DEFAULT '',
 FOREIGN KEY (station_id) REFERENCES stations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS maintenance_records (
 id INT PRIMARY KEY AUTO_INCREMENT,
 asset_id INT NOT NULL,
 issue VARCHAR(500) NOT NULL,
 action_taken VARCHAR(500) NOT NULL DEFAULT '',
 technician VARCHAR(80) NOT NULL DEFAULT '',
 scheduled_on VARCHAR(10) NOT NULL DEFAULT '',
 completed_on VARCHAR(10) NOT NULL DEFAULT '',
 status VARCHAR(20) NOT NULL DEFAULT 'open',
 cost DECIMAL(12,2) NOT NULL DEFAULT 0,
 FOREIGN KEY (asset_id) REFERENCES assets(id), INDEX (asset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
