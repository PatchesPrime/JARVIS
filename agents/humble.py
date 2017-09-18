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


if __name__ == '__main__':
    with open('../secrets', 'rb') as secrets:
        # We need our authentication.
        authsecrets = msgpack.unpackb(secrets.read(), encoding='utf-8')

    # Now we use our authentication.
    mongo = pymongo.MongoClient()

    # Assign and authenticate.
    db = mongo.bot
    db.authenticate(authsecrets['mongo_user'], authsecrets['mongo_pass'])

    # Get the current freebies just once.
    free_games = humbleScrape()

    if free_games:
        store = 'https://www.humblebundle.com/store/'

        # Time to go over subscribers
        for sub in db.subscribers.find({}):
            for game in free_games:
                # Locate all known previous sales matching current
                # game for skipping logic.
                known_sales = db.games.find(
                    {'human_url': game['human_url'],
                     'sale_end': game['sale_end']}
                )

                # Are there any known sales of this game?
                if known_sales.count():
                    # They're the same sale.
                    continue

                # Currently we force a disconnect after
                # receiving a message so we must connect
                # for each one. This is likely to change.
                # Also, the things I do for <79 char.
                sock = socket.socket(
                    socket.AF_INET, socket.SOCK_STREAM
                )
                sock.connect(('192.168.1.200', 8888))

                # Payload build.
                payload = {
                    'to': sub['user'],
                    'msg': (
                        'FREE GAME: {}'.format(game['human_name']),
                        '\n {}{}'.format(store, game['human_url'])
                    )
                }

                # Send said payload.
                sock.send(msgpack.packb(payload))
                sock.close()

        # Insert each game. If it exists in DB, just update sale_end
        for game in free_games:
            db.games.update_one(
                {'human_url': game['human_url']},
                {'$set': {
                    'sale_end': game['sale_end'],
                    'human_name': game['human_name']
                }},
                upsert=True
            )
