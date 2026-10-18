CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room TEXT NOT NULL,
  author TEXT NOT NULL,
  text TEXT NOT NULL,
  time TEXT NOT NULL,
  request_id TEXT NOT NULL,
  UNIQUE(room, author, request_id)
);
CREATE INDEX IF NOT EXISTS room_cursor ON messages(room, id);
CREATE INDEX IF NOT EXISTS seat_time ON messages(author, time);
