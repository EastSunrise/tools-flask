CREATE TABLE IF NOT EXISTS movie
(
    id             INTEGER  NOT NULL
        primary key,
    title          TEXT     NOT NULL,
    alt            TEXT     NOT NULL,
    status         Status   NOT NULL, -- unmarked/wish/do/collect
    tag_date       TEXT,              -- last date updating the status
    original_title TEXT,
    aka            list,
    subtype        Subtype  NOT NULL,
    languages      list     NOT NULL,
    year           INTEGER  NOT NULL,
    durations      list     NOT NULL,
    current_season INTEGER,
    episodes_count INTEGER,
    seasons_count  INTEGER,
    imdb           INTEGER,           -- IMDb No.
    archived       Archived NOT NULL, -- none/added/playable/idm/downloading
    location       TEXT,
    source         TEXT,
    last_update    TEXT     NOT NULL
);
