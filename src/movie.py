from collections import namedtuple
from typing import Optional
from typing import Union

MovieUrl = namedtuple("MovieUrl", ["action", "method"])


class Integer(int):
    @classmethod
    def parse_int(cls, number):
        num = []
        for i in str(number):
            if i.isnumeric():
                num.append(i)
            elif i in ["-", "."]:
                num.append(i)
        return cls("".join(num))


class MovieInfo:
    def __init__(
        self,
        title,
        url: Optional[MovieUrl] = None,
        fields=None,
        seeds=None,
        leeches=None,
        size=None,
        category=None,
    ):
        self.title = title
        self.url = url
        self.fields = fields or {}
        self.seeds = seeds
        self.leeches = leeches
        self.size = size
        self.category = category

    def __repr__(self):
        return self.title

    @classmethod
    def from_dict(cls, dikt: dict[str, Union[str, dict]]):
        return cls(
            title=dikt["title"],
            url=MovieUrl(
                method=dikt["url"].get("method", "post"),
                action=dikt["url"]["action"],
            ),
            fields=dikt["fields"],
            seeds=Integer.parse_int(dikt["seeds"]),
            leeches=Integer.parse_int(dikt["leeches"]),
            size=dikt["size"],
            category=dikt["category"],
        )
