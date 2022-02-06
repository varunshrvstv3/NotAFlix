import json
import logging
from typing import List

from bs4 import BeautifulSoup as BS

from constants import TorrentCategory
from movie import MovieInfo
from request import Request

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


class Py1337x:
    def __init__(self, host: str) -> None:
        self.host: str = host
        self.network_request = Request(host)

    @staticmethod
    def _parse_movie_table(soup: BS):
        movies = []
        for row in soup.find("table", class_="table-list").find_all("tr"):
            movie = {}
            try:
                form = row.td.form
                if form is not None:
                    movie["url"] = {
                        "action": form.get("action"),
                        "method": form.get("method"),
                    }
                    movie["fields"] = {
                        form.input.get("name"): form.input.get("value")
                    }
                    movie["title"] = form.text.strip()
                movie["seeds"] = row.find(
                    "td", class_="coll-2 seeds"
                ).text.strip()
                movie["leeches"] = row.find(
                    "td", class_="coll-3 leeches"
                ).text.strip()
                movie["size"] = row.find(
                    "td", class_="coll-4 size mob-vip"
                ).text
                movie["category"] = row.find("td", class_="coll-5 vip").text
            except AttributeError:
                # logger.info(row)
                pass
            if movie:
                movies.append(MovieInfo.from_dict(movie))
        return movies

    def get_movie_list(
        self, category: TorrentCategory = TorrentCategory.MOVIES, page: int = 1
    ) -> List[MovieInfo]:
        data: bytes = self.network_request.post(
            url=f"/category/{category.value}/page/{page}",
            fields={"id": category.name, "sorter": "seed"},
        )
        return self._parse_movie_table(BS(data, "html.parser"))

    def get_movie_magnet(self, movie: MovieInfo) -> str:
        data: bytes = self.network_request.post(
            url=movie.url.action, fields=movie.fields
        )
        soup = BS(data, "html.parser")
        magnet = soup.find("ul", class_="download-links-dontblock").a.get(
            "href"
        )
        return magnet

    def search(
        self,
        search_string: str,
        category: TorrentCategory = TorrentCategory.ALL,
    ) -> List[MovieInfo]:
        data: bytes = self.network_request.post(
            url=f"/search/",
            fields={
                "q": search_string,
                "category": category.name,
                "sorter": "seed",
            },
        )
        return self._parse_movie_table(BS(data, "html.parser"))


if __name__ == "__main__":
    torrent = Py1337x("ww2.1337x.buzz")
    # movies = torrent.get_movie_list(category=TorrentCategory("movies"), page=20)
    # print(movies)
    movies = torrent.search("black widow")
    print(movies)
    print(torrent.get_movie_magnet(movies[0]))
