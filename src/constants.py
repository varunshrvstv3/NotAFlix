import enum
from typing import Set


class TorrentCategory(enum.Enum):
    XXX = "xxx"
    MOVIES = "movies"
    TV = "tv"
    GAMES = "games"
    ANIME = "anime"
    ALL = "all"


PYFLIX_CACHE_DIR = "/var/tmp/cache"
