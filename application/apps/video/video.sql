CREATE TABLE IF NOT EXISTS movies
(
    id             INTEGER NOT NULL
        primary key,
    title          TEXT    NOT NULL,
    alt            TEXT    NOT NULL,
    status         TEXT    NOT NULL, -- wish/do/collect
    tag_date       TEXT    NOT NULL, -- last date updating the status
    original_title TEXT,
    aka            list,
    subtype        TEXT    NOT NULL,
    languages      list    NOT NULL,
    year           INTEGER NOT NULL,
    durations      list    NOT NULL,
    current_season INTEGER,
    episodes_count INTEGER,
    seasons_count  INTEGER,
    archived       INTEGER NOT NULL, -- 0: unarchived, 1: archived, 2: downloading, 3: temp, -1: no resources
    -- no resources
    location       TEXT,
    source         TEXT,
    last_update    TEXT    NOT NULL
);
