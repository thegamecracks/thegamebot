PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

CREATE TABLE Blackjack (
    user_id    INTEGER PRIMARY KEY
                       NOT NULL,
    played     INTEGER NOT NULL
                       DEFAULT 0,
    wins       INTEGER NOT NULL
                       DEFAULT 0,
    losses     INTEGER NOT NULL
                       DEFAULT 0,
    blackjacks INTEGER NOT NULL
                       DEFAULT (0),
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) ON DELETE CASCADE
);


CREATE TABLE CSClubSuggestions (
    thread_id INTEGER PRIMARY KEY
                      NOT NULL,
    user_id   INTEGER NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) ON DELETE CASCADE
);


CREATE TABLE Currency (
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    cents    INTEGER NOT NULL
                     DEFAULT 0,
    CHECK (cents >= 0),
    PRIMARY KEY (
        guild_id,
        user_id
    ),
    FOREIGN KEY (
        guild_id
    )
    REFERENCES guild (id) ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) ON DELETE CASCADE
);


CREATE TABLE guild (
    id     INTEGER NOT NULL
                   PRIMARY KEY,
    prefix TEXT    CHECK (LENGTH(prefix) <= 20) 
);


CREATE TABLE Notes (
    note_id       INTEGER   PRIMARY KEY
                            NOT NULL,
    user_id       INTEGER   NOT NULL
                            REFERENCES Users (id) ON DELETE CASCADE,
    guild_id      INTEGER   REFERENCES guild (id) ON DELETE CASCADE
                            DEFAULT NULL,
    time_of_entry TIMESTAMP,
    content       TEXT      NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) 
);


CREATE TABLE Reminders (
    reminder_id INTEGER   PRIMARY KEY AUTOINCREMENT
                          NOT NULL,
    user_id     INTEGER   NOT NULL
                          REFERENCES Users (id) ON DELETE CASCADE,
    channel_id  INTEGER   NOT NULL,
    due         TIMESTAMP,
    content     TEXT      NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) 
);


CREATE TABLE TagAliases (
    guild_id   INTEGER      NOT NULL,
    alias      VARCHAR (50) NOT NULL,
    name       VARCHAR (50) NOT NULL,
    user_id    INTEGER,
    created_at TIMESTAMP    NOT NULL,
    PRIMARY KEY (
        guild_id,
        alias
    ),
    FOREIGN KEY (
        guild_id
    )
    REFERENCES guild (id) ON DELETE CASCADE,
    FOREIGN KEY (
        guild_id,
        name
    )
    REFERENCES Tags ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) ON DELETE SET NULL
);


CREATE TABLE Tags (
    guild_id   INTEGER        NOT NULL,
    name       VARCHAR (50)   NOT NULL,
    content    VARCHAR (2000) NOT NULL,
    user_id    INTEGER,
    uses       INTEGER        NOT NULL
                              DEFAULT 0,
    created_at TIMESTAMP      NOT NULL,
    edited_at  TIMESTAMP,
    PRIMARY KEY (
        guild_id,
        name
    ),
    FOREIGN KEY (
        guild_id
    )
    REFERENCES guild (id) ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES Users (id) ON DELETE SET NULL
);


CREATE TABLE Users (
    id              INTEGER NOT NULL
                            PRIMARY KEY,
    timezone        TEXT,
    timezone_public BOOLEAN NOT NULL
                            DEFAULT (false),
    timezone_watch  BOOLEAN NOT NULL
                            DEFAULT (true) 
);


CREATE INDEX ix_notes_users ON Notes (
    user_id,
    guild_id
);


CREATE INDEX ix_reminders_channels ON Reminders (
    channel_id
);


CREATE INDEX ix_reminders_user_channel ON Reminders (
    user_id,
    channel_id
);


CREATE INDEX ix_reminders_users ON Reminders (
    user_id
);


CREATE INDEX ix_tags_guilds ON Tags (
    guild_id
);


CREATE INDEX ix_tags_name_to_aliases ON TagAliases (
    guild_id,
    name
);


CREATE INDEX ix_tags_user_to_aliases ON TagAliases (
    guild_id,
    user_id
);


CREATE INDEX ix_tags_users ON Tags (
    user_id,
    guild_id
);


CREATE TRIGGER no_tag_alias_if_name
         AFTER INSERT
            ON TagAliases
          WHEN EXISTS (
    SELECT *
      FROM Tags
     WHERE name = NEW.alias
)
BEGIN
    SELECT RAISE(ABORT, "a tag with the same name already exists");
END;


CREATE TRIGGER no_tag_name_if_alias
         AFTER INSERT
            ON Tags
          WHEN EXISTS (
    SELECT *
      FROM TagAliases
     WHERE alias = NEW.name
)
BEGIN
    SELECT RAISE(ABORT, "an alias with the same name already exists");
END;


COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
PRAGMA journal_mode = wal; -- asqlite enables this
