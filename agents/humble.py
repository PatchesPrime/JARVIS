import requests
import socket
import pymongo
import msgpack
import json
import aiohttp


async def humbleScrape():
    '''
    Scrape the humble store front page looking for
    free games.
    '''
    async with aiohttp.ClientSession() as session:
        async with session.get('https://www.humblebundle.com/store') as response:
            page_src = await response.text()

        for line in page_src.splitlines():
            if 'page: {"strings"' in line:
                # Not very clean but it should do. Chop off 'page: '.
                shop = json.loads(line[12:-1])['entity_lookup_dict']

        # The things I do for 79 characters.
        freebies = [
            item for item in shop.values()
            if 'current_price' in item.keys() and 0.0 in item['current_price']
        ]

        return freebies
