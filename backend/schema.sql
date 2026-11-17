-- FleetFlow TMS database schema (SQLite)

CREATE TABLE IF NOT EXISTS cities (
  name TEXT PRIMARY KEY,
  lat  REAL NOT NULL,
  lon  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
  name TEXT PRIMARY KEY,
  edi  INTEGER NOT NULL DEFAULT 0          -- 1 = trades by EDI (204 / 990 / 210)
);

CREATE TABLE IF NOT EXISTS trucks (
  id     TEXT PRIMARY KEY,                 -- T-1041
  unit   TEXT NOT NULL,                    -- year / make / model
  motive TEXT,                             -- telematics vehicle id; NULL = not mapped
  odo    INTEGER NOT NULL DEFAULT 0,
  fuel   INTEGER NOT NULL DEFAULT 100,     -- percent
  fault  TEXT                              -- active fault code, if any
);

CREATE TABLE IF NOT EXISTS drivers (
  id     TEXT PRIMARY KEY,                 -- D-01
  name   TEXT NOT NULL,
  truck  TEXT NOT NULL REFERENCES trucks(id),
  status TEXT NOT NULL,                    -- Driving / On Duty / Available / Off Duty / Sleeper
  drive  REAL NOT NULL,                    -- HOS hours remaining (11h rule)
  shift  REAL NOT NULL,                    -- HOS hours remaining (14h rule)
  cycle  REAL NOT NULL,                    -- hours used in the 70h cycle
  loc    TEXT NOT NULL REFERENCES cities(name),
  phone  TEXT
);

CREATE TABLE IF NOT EXISTS loads (
  id           TEXT PRIMARY KEY,           -- LD-24101
  seq          INTEGER NOT NULL,           -- display order (newest first)
  cust         TEXT NOT NULL REFERENCES customers(name),
  origin       TEXT NOT NULL REFERENCES cities(name),
  dest         TEXT NOT NULL REFERENCES cities(name),
  pickup       TEXT NOT NULL,
  delivery     TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'Booked'
               CHECK (status IN ('Booked','Planned','Dispatched','In Transit','Delivered','Invoiced')),
  driver       TEXT REFERENCES drivers(id),
  equip        TEXT NOT NULL,
  weight       INTEGER NOT NULL,
  rate         REAL NOT NULL,              -- linehaul, USD
  prog         REAL NOT NULL DEFAULT 0,    -- 0..1 trip progress
  pod          INTEGER NOT NULL DEFAULT 0, -- proof of delivery received
  late         INTEGER NOT NULL DEFAULT 0,
  dispatch_err INTEGER NOT NULL DEFAULT 0, -- dispatch did not reach the driver app
  ticks        INTEGER NOT NULL DEFAULT 0, -- simulation counter while at shipper
  inv_no       TEXT,
  inv_st       TEXT,                       -- Open / Paid
  inv_due      TEXT
);

CREATE TABLE IF NOT EXISTS logs (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  t    TEXT NOT NULL,                      -- HH:MM:SS
  sys  TEXT NOT NULL,                      -- Motive / EDI / Accounting / Mileage / TMS
  dir  TEXT NOT NULL,                      -- IN / OUT
  type TEXT NOT NULL,
  ref  TEXT NOT NULL,                      -- load or truck id, or —
  st   TEXT NOT NULL,                      -- Success / Error
  msg  TEXT NOT NULL,
  fix  TEXT                                -- how a failed event is resolved: map / scope / doc
);

CREATE TABLE IF NOT EXISTS messages (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id TEXT NOT NULL REFERENCES loads(id),
  me      INTEGER NOT NULL,                -- 1 = dispatcher, 0 = driver
  text    TEXT NOT NULL,
  t       TEXT NOT NULL                    -- HH:MM
);

CREATE INDEX IF NOT EXISTS idx_loads_status ON loads(status);
CREATE INDEX IF NOT EXISTS idx_loads_driver ON loads(driver);
CREATE INDEX IF NOT EXISTS idx_logs_ref     ON logs(ref);
CREATE INDEX IF NOT EXISTS idx_msgs_load    ON messages(load_id);

-- Accounts. Kept when the demo data is reset.
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  email      TEXT NOT NULL UNIQUE,         -- stored lower-case
  role       TEXT NOT NULL DEFAULT 'Dispatcher',
  pw_hash    TEXT NOT NULL,                -- PBKDF2-SHA256, hex
  salt       TEXT NOT NULL,                -- per-user random salt, hex
  created_at INTEGER NOT NULL              -- unix time
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,             -- SHA-256 of the cookie token
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

-- Online invoice payments (PayPal / Razorpay). One row per gateway order.
CREATE TABLE IF NOT EXISTS payments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id    TEXT NOT NULL REFERENCES loads(id),
  provider   TEXT NOT NULL CHECK (provider IN ('paypal','razorpay')),
  order_id   TEXT NOT NULL,                -- gateway order id
  payment_id TEXT,                         -- gateway capture / payment id once paid
  amount     INTEGER NOT NULL,             -- smallest currency unit (cents / paise)
  currency   TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','paid','failed')),
  error      TEXT,
  created_at INTEGER NOT NULL,
  paid_at    INTEGER,
  UNIQUE (provider, order_id)
);
CREATE INDEX IF NOT EXISTS idx_payments_load ON payments(load_id);
