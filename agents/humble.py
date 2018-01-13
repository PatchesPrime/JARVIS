import json
import aiohttp
import logging
import asyncio
import msgpack
from socket import create_connection
from datetime import timedelta
import config
import motor.motor_asyncio

mongo = motor.motor_asyncio.AsyncIOMotorClient()
db = mongo.bot
db.authenticate(
    config.mongo_user,
    config.mongo_pass,
)


async def humbleScrape():
    '''
    Scrape the humble store front page looking for
    free games.
    '''
    url = 'https://www.humblebundle.com/store'

    async with aiohttp.ClientSession() as session:
        # There have been no complaints, but this will help them find me if
        # they have some.
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
        }
        async with session.get(url, headers=headers, timeout=3) as response:
            page_src = await response.text()

        for line in page_src.splitlines():
            # So...sometimes this string isn't in the page? What?
            if 'page: {"strings"' in line:
                # Not very clean but it should do. Chop off 'page: '.
                shop = json.loads(line[12:-1])['entity_lookup_dict']

        try:
            games = [
                game for game in shop.values()
                if game.get('current_price') is not None
            ]

            freebies = [
                game for game in games if 0.0 in game['current_price']
            ]

            return freebies
        except UnboundLocalError:
            return []


async def agent(*, freq=timedelta(hours=5)):
    while True:
        logging.debug('Checking humblebundle..')
        free_games = await humbleScrape()

        if free_games:
            logging.debug('FOUND FREEBIES..COMPARING')
            store = 'https://humblebundle.com/store/'

            for game in free_games:
                pattern = {
                    'human_url': game['human_url'],
                    'sale_end': game['sale_end']
                }

                # Have we seen this sale?
                if await db.games.find_one(pattern):
                    continue

                logging.debug('{} is new..'.format(game['human_name']))

                await db.games.update_one(
                    {'human_url': game['human_url']},
                    {
                        # Flymake was complaining now it's not.
                        '$set': {
                            'sale_end': game['sale_end'],
                            'human_name': game['human_name']
                        }
                    },
                    upsert=True
                )

                payload = {
                    'to': 'all_friends',
                    'msg': 'FREE GAME: {title}\n{link}'.format(
                        title=game['human_name'],
                        link=store + game['human_url']
                    ),
                }

                logging.debug('payload={}'.format(payload))

                # Pass the infomration to Jarvis.
                sock = create_connection(('192.168.1.200', 8888))
                sock.send(msgpack.packb(payload))
                sock.close()

        # Sleep on a timer.
        await asyncio.sleep(freq.total_seconds())
