import enum


class TorrentCategory(enum.Enum):
    """
    Categories of the movies supported by the torrent.
    """
    MOVIES = "movies"
    TV = "tv"
    GAMES = "games"
    ANIME = "anime"
    ALL = "all"


PYFLIX_CACHE_DIR = "/var/tmp/cache"
