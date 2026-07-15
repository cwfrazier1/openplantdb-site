-- OpenPlantDB social platform schema (Postgres 15)
-- Extension-free: built-in gen_random_uuid(), haversine for geo radius.

CREATE TABLE IF NOT EXISTS users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email           text NOT NULL,
    username        text NOT NULL,
    password_hash   text NOT NULL,
    display_name    text NOT NULL DEFAULT '',
    bio             text NOT NULL DEFAULT '',
    avatar_key      text,
    zip             text,
    home_zone       text,
    lat             double precision,
    lng             double precision,
    email_verified  boolean NOT NULL DEFAULT false,
    verify_token    text,
    reset_token     text,
    reset_expires   timestamptz,
    notify_email    boolean NOT NULL DEFAULT true,
    notify_push     boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    last_active     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_idx ON users (lower(username));

-- Push targets (APNs device tokens + web-push subscriptions)
CREATE TABLE IF NOT EXISTS devices (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform        text NOT NULL,               -- 'ios' | 'web'
    apns_token      text,                         -- ios
    web_sub         jsonb,                        -- web-push subscription
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_seen       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS devices_apns_idx ON devices (apns_token) WHERE apns_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS devices_user_idx ON devices (user_id);

-- Social graph
CREATE TABLE IF NOT EXISTS follows (
    follower_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX IF NOT EXISTS follows_followee_idx ON follows (followee_id);

-- "I planted this!" posts
CREATE TABLE IF NOT EXISTS plantings (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plant_slug      text NOT NULL,
    plant_name      text NOT NULL DEFAULT '',
    note            text NOT NULL DEFAULT '',
    zone            text,
    lat             double precision,
    lng             double precision,
    planted_on      date,
    like_count      integer NOT NULL DEFAULT 0,
    comment_count   integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plantings_user_idx ON plantings (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS plantings_slug_idx ON plantings (plant_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS plantings_geo_idx ON plantings (lat, lng);
CREATE INDEX IF NOT EXISTS plantings_created_idx ON plantings (created_at DESC);

CREATE TABLE IF NOT EXISTS planting_photos (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    planting_id     uuid NOT NULL REFERENCES plantings(id) ON DELETE CASCADE,
    s3_key          text NOT NULL,
    width           integer,
    height          integer,
    position        integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS planting_photos_idx ON planting_photos (planting_id, position);

CREATE TABLE IF NOT EXISTS comments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    planting_id     uuid NOT NULL REFERENCES plantings(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body            text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS comments_planting_idx ON comments (planting_id, created_at);

CREATE TABLE IF NOT EXISTS likes (
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    planting_id     uuid NOT NULL REFERENCES plantings(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, planting_id)
);
CREATE INDEX IF NOT EXISTS likes_planting_idx ON likes (planting_id);

CREATE TABLE IF NOT EXISTS notifications (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- recipient
    actor_id        uuid REFERENCES users(id) ON DELETE CASCADE,
    type            text NOT NULL,   -- comment|like|follow|nearby|request_fulfilled
    planting_id     uuid REFERENCES plantings(id) ON DELETE CASCADE,
    comment_id      uuid REFERENCES comments(id) ON DELETE CASCADE,
    body            text NOT NULL DEFAULT '',
    payload         jsonb,
    read            boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_unread_idx ON notifications (user_id) WHERE read = false;

-- Plant requests -> feed the nightly expansion job (processed first)
CREATE TABLE IF NOT EXISTS plant_requests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
    query_text      text NOT NULL,
    normalized      text NOT NULL,
    status          text NOT NULL DEFAULT 'pending',  -- pending|processing|fulfilled|rejected
    votes           integer NOT NULL DEFAULT 1,
    fulfilled_slug  text,
    note            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS plant_requests_norm_idx ON plant_requests (normalized) WHERE status IN ('pending','processing');
CREATE INDEX IF NOT EXISTS plant_requests_status_idx ON plant_requests (status, votes DESC, created_at);
