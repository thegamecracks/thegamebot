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
    REFERENCES user (user_id) ON DELETE CASCADE
);


CREATE TABLE CSClubSuggestions (
    thread_id INTEGER PRIMARY KEY
                      NOT NULL,
    user_id   INTEGER NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) ON DELETE CASCADE
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
    REFERENCES guild (guild_id) ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) ON DELETE CASCADE
);


CREATE TABLE guild (
    guild_id INTEGER NOT NULL
                     PRIMARY KEY,
    prefix   TEXT    CHECK (LENGTH(prefix) <= 20) 
);


CREATE TABLE note (
    note_id       INTEGER   PRIMARY KEY
                            NOT NULL,
    user_id       INTEGER   NOT NULL
                            REFERENCES user (user_id) ON DELETE CASCADE,
    guild_id      INTEGER   REFERENCES guild (guild_id) ON DELETE CASCADE
                            DEFAULT NULL,
    time_of_entry TIMESTAMP,
    content       TEXT      NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) 
);


CREATE TABLE Reminders (
    reminder_id INTEGER   PRIMARY KEY AUTOINCREMENT
                          NOT NULL,
    user_id     INTEGER   NOT NULL
                          REFERENCES user (user_id) ON DELETE CASCADE,
    channel_id  INTEGER   NOT NULL,
    due         TIMESTAMP,
    content     TEXT      NOT NULL,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) 
);


CREATE TABLE tag (
    guild_id   INTEGER        NOT NULL,
    tag_name   VARCHAR (50)   NOT NULL,
    content    VARCHAR (2000) NOT NULL,
    user_id    INTEGER,
    uses       INTEGER        NOT NULL
                              DEFAULT 0,
    created_at TIMESTAMP      NOT NULL,
    edited_at  TIMESTAMP,
    PRIMARY KEY (
        guild_id,
        tag_name
    ),
    FOREIGN KEY (
        guild_id
    )
    REFERENCES guild (guild_id) ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) ON DELETE SET NULL
);


CREATE TABLE tag_alias (
    guild_id   INTEGER      NOT NULL,
    alias_name VARCHAR (50) NOT NULL,
    tag_name   VARCHAR (50) NOT NULL,
    user_id    INTEGER,
    created_at TIMESTAMP    NOT NULL,
    PRIMARY KEY (
        guild_id,
        alias_name
    ),
    FOREIGN KEY (
        guild_id
    )
    REFERENCES guild (guild_id) ON DELETE CASCADE,
    FOREIGN KEY (
        guild_id,
        tag_name
    )
    REFERENCES tag (guild_id,
    tag_name) ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) ON DELETE SET NULL
);


CREATE TABLE user (
    user_id         INTEGER NOT NULL
                            PRIMARY KEY,
    timezone        TEXT,
    timezone_public BOOLEAN NOT NULL
                            DEFAULT (false),
    timezone_watch  BOOLEAN NOT NULL
                            DEFAULT (true) 
);


CREATE INDEX ix_note_user ON note (
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


CREATE INDEX ix_tag_alias_name ON tag_alias (
    guild_id,
    tag_name
);


CREATE INDEX ix_tag_alias_user ON tag_alias (
    guild_id,
    user_id
);


CREATE INDEX ix_tag_guild ON tag (
    guild_id
);


CREATE INDEX ix_tag_user ON tag (
    user_id,
    guild_id
);


CREATE TRIGGER no_tag_alias_if_name
         AFTER INSERT
            ON tag_alias
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
            ON tag
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
