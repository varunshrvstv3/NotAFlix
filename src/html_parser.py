import logging

from bs4 import BeautifulSoup as BS

logger = logging.getLogger()


def table_parser(html_table):
    soup = BS(html_table)


def html_to_json(web_page):
    soup = BS(web_page, "html.parser")
    # print(soup.name)
    cursor = soup.body
    while cursor:
        element = cursor.next
        while element and element.name:
            logger.info(element.name)
            logger.info(element)
            element = element.next_sibling
        cursor = cursor.next
