-- MeetRoom schema (SQLite3)
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    department    TEXT    NOT NULL DEFAULT '',
    role          TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE rooms (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    location         TEXT    NOT NULL DEFAULT '',
    capacity         INTEGER NOT NULL CHECK (capacity > 0),
    equipment        TEXT    NOT NULL DEFAULT '',
    require_approval INTEGER NOT NULL DEFAULT 0 CHECK (require_approval IN (0, 1)),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id         INTEGER NOT NULL REFERENCES rooms (id),
    user_id         INTEGER NOT NULL REFERENCES users (id),
    title           TEXT    NOT NULL,
    booking_date    TEXT    NOT NULL,              -- YYYY-MM-DD
    start_time      TEXT    NOT NULL,              -- HH:MM
    end_time        TEXT    NOT NULL,              -- HH:MM
    attendees       INTEGER NOT NULL DEFAULT 1,
    equipment       TEXT    NOT NULL DEFAULT '',
    note            TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'confirmed'
                    CHECK (status IN ('pending', 'confirmed', 'rejected', 'cancelled')),
    recurring_group TEXT,
    approved_by     INTEGER REFERENCES users (id),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (end_time > start_time)
);

CREATE INDEX idx_bookings_room_date ON bookings (room_id, booking_date);
CREATE INDEX idx_bookings_user ON bookings (user_id);
CREATE INDEX idx_bookings_group ON bookings (recurring_group);
