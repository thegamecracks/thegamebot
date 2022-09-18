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


CREATE TABLE csclub_suggestion (
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


CREATE TABLE reminder (
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


CREATE VIRTUAL TABLE tag_fts5 USING fts5 (
    guild_id UNINDEXED,
    tag_name,
    -- content,
    content=tag,
    tokenize = 'porter unicode61 remove_diacritics 2'
);
-- INSERT INTO tag_fts5 (tag_fts5) VALUES ('rebuild');


CREATE TRIGGER tag_fts5_ai AFTER INSERT ON tag BEGIN
  INSERT INTO tag_fts5
    (rowid, guild_id, tag_name, content) VALUES
    (new.rowid, new.guild_id, new.tag_name, new.content);
END;
CREATE TRIGGER tag_fts5_ad AFTER DELETE ON tag BEGIN
  INSERT INTO tag_fts5
    (tag_fts5, rowid, guild_id, tag_name, content) VALUES
    ('delete', old.rowid, old.guild_id, old.tag_name, old.content);
END;
CREATE TRIGGER tag_fts5_au AFTER UPDATE ON tag BEGIN
  INSERT INTO tag_fts5
    (tag_fts5, rowid, guild_id, tag_name, content) VALUES
    ('delete', old.rowid, old.guild_id, old.tag_name, old.content);
  INSERT INTO tag_fts5
    (rowid, guild_id, tag_name, content) VALUES
    (new.rowid, new.guild_id, new.tag_name, new.content);
END;


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
    REFERENCES tag ON DELETE CASCADE,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user (user_id) ON DELETE SET NULL
);


CREATE VIRTUAL TABLE tag_alias_fts5 USING fts5 (
    guild_id UNINDEXED,
    alias_name,
    tag_name UNINDEXED,
    content=tag_alias,
    tokenize = 'porter unicode61 remove_diacritics 2'
);
-- INSERT INTO tag_alias_fts5 (tag_alias_fts5) VALUES ('rebuild');


CREATE TRIGGER tag_alias_fts5_ai AFTER INSERT ON tag_alias BEGIN
  INSERT INTO tag_alias_fts5
    (rowid, guild_id, alias_name, tag_name) VALUES
    (new.rowid, new.guild_id, new.alias_name, new.tag_name);
END;
CREATE TRIGGER tag_alias_fts5_ad AFTER DELETE ON tag_alias BEGIN
  INSERT INTO tag_alias_fts5
    (tag_alias_fts5, rowid, guild_id, alias_name, tag_name) VALUES
    ('delete', old.rowid, old.guild_id, old.alias_name, old.tag_name);
END;
CREATE TRIGGER tag_alias_fts5_au AFTER UPDATE ON tag_alias BEGIN
  INSERT INTO tag_alias_fts5
    (tag_alias_fts5, rowid, guild_id, alias_name, tag_name) VALUES
    ('delete', old.rowid, old.guild_id, old.alias_name, old.tag_name);
  INSERT INTO tag_alias_fts5
    (rowid, guild_id, alias_name, tag_name) VALUES
    (new.rowid, new.guild_id, new.alias_name, new.tag_name);
END;


CREATE TABLE user (
    user_id  INTEGER NOT NULL
                     PRIMARY KEY,
    timezone TEXT
);


CREATE INDEX ix_note_user ON note (
    user_id,
    guild_id
);


CREATE INDEX ix_reminder_channels ON reminder (
    channel_id
);


CREATE INDEX ix_reminder_user_channel ON reminder (
    user_id,
    channel_id
);


CREATE INDEX ix_reminder_users ON reminder (
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
      FROM tag
     WHERE tag_name = NEW.alias_name
)
BEGIN
    SELECT RAISE(ABORT, "a tag with the same name already exists");
END;


CREATE TRIGGER no_tag_name_if_alias
         AFTER INSERT
            ON tag
          WHEN EXISTS (
    SELECT *
      FROM tag_alias
     WHERE alias_name = NEW.tag_name
)
BEGIN
    SELECT RAISE(ABORT, "an alias with the same name already exists");
END;


COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
PRAGMA journal_mode = wal; -- asqlite enables this
