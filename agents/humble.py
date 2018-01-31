import json
import aiohttp
import logging
import asyncio
import msgpack
from socket import create_connection
from datetime import timedelta


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
                # Chop off leading whitespace.
                line = line.lstrip()

                # Chop off 'page: ', which is 6 characters.
                shop = json.loads(line[6:-1])['entity_lookup_dict']

                # We're done here, get out of loop.
                break

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


async def agent(db, *, freq=timedelta(hours=5)):
    while True:
        logging.debug('Checking humblebundle..')
        try:
            free_games = await humbleScrape()
        except asyncio.TimeoutError as e:
            logging.warn('Timed out during free game check!')
            continue

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
                    'type': 'humblebundle'
                }

                logging.debug('payload={}'.format(payload))

                # Pass the infomration to Jarvis.
                sock = create_connection(('192.168.1.200', 8888))
                sock.send(msgpack.packb(payload))
                sock.close()

        # PEP8 pls
        logging.debug(
            'agents.humble sleeping {} seconds'.format(freq.total_seconds())
        )

        # Sleep on a timer.
        await asyncio.sleep(freq.total_seconds())
