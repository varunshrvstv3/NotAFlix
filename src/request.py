from urllib3 import HTTPResponse
from urllib3.connectionpool import HTTPSConnectionPool

import html_parser


class Request:
    def __init__(self, host):
        self.connection_pool: HTTPSConnectionPool = HTTPSConnectionPool(
            host=host
        )

    def post(
        self, url: str, fields: dict = None, headers: dict = None
    ) -> bytes:
        response: HTTPResponse = self.connection_pool.request(
            method="post", url=url, fields=fields, headers=headers
        )
        if response.status != 200:
            raise ValueError(
                f"The response didn't receive 200 status!\n{response.data} {response.status}"
            )
        # html_parser.html_to_json(response.data)
        return response.data

    def get(self):
        pass
