import aiohttp
import json
import asyncio
import logging
from datetime import timedelta
from socket import create_connection
import msgpack


async def humbleScrape(game_name):
    '''
    Scrape the humble store front page looking for
    free games.
    '''
    # huehue
    url = 'https://www.humblebundle.com/store/' + game_name

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
            if 'products_json' in line: #: [{' in line:
                # Game data, there is only ever 1
                line = line.lstrip()

                # Fight me about it.
                game = json.loads(line[line.find('[{'):-1])[0]

                # We're done.
                return game


async def agent(db, *, freq=timedelta(hours=5)):
    while True:
        logging.debug('Checking for sales..')

        # Just for character count and easier to modify later.
        query = {'sales_watch': {'$exists': True}}
        qfilter = {'user': 1, 'sales_watch': 1}
        async for sub in db.subscribers.find(query, qfilter):
            for watching in sub['sales_watch']:
                try:
                    check = await humbleScrape(watching['name'])
                except asyncio.TimeoutError as e:
                    logging.warn('Timed out during humblepricer!')
                    continue

                price, wanted = check['current_price'][0], watching['price']

                if watching['discount']:
                    price = price - (price * 0.10)

                if price <= wanted:
                    logging.debug('Found good sale: {}'.format(watching))

                    # Remove the entry from the DB. Bad practice? Yep.
                    query.update({'user': sub['user']})
                    result = await db.subscribers.update_one(
                        query, {'$pull':
                                {'sales_watch':
                                 {'name': check['human_url']}}}
                    )

                    # I feel dirty.
                    logging.debug('Removed {} entries from DB'.format(result))

                    # I'm working on coming up with the worlds ugliest
                    # string formatting. How am I doing?
                    msg = (
                        'Game matching your criteria found!\n',
                        '{} is currently available for {}'.format(
                            check['human_name'], price
                        ),
                        'You asked to be notifed when it was <= {}'.format(
                            watching['price']
                        ),
                        '\nLink: {}'.format(watching['url'])
                    )

                    # Payload.
                    payload = {
                        'to': sub['user'],
                        'msg': '\n'.join(msg),
                        'type': 'sale',
                    }

                    # Pass the payload to Jarvis.
                    sock = create_connection(('192.168.1.200', 8888))
                    sock.send(msgpack.packb(payload))
                    sock.close()

        # Reeeeee, 79 characters.
        logging.debug(
            'agents.humblesale sleeping {} seconds'.format(
                freq.total_seconds()
            )
        )
        await asyncio.sleep(freq.total_seconds())
