import json
import aiohttp
import logging
import asyncio
import msgpack
from socket import create_connection
from datetime import timedelta


async def getWeather(same):
    '''
    Give it a postal code and it'll give you JSON representing the weather
    for that postcode.

    '''
    # URL for PEP8
    url = 'https://api.weather.gov/alerts?active=1'

    # Now we can do this.
    async with aiohttp.ClientSession() as session:
        # There have been no complaints, but this will help them find me if
        # they have some. PS I love you NWS
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
        }

        try:
            async with session.get(url, headers=headers) as response:
                request = await response.text()

                # Docs say aiohttp json() should use this by default
                # but it fails because mimetype without it..Weird
                try:
                    request = json.loads(request)['features']
                except json.decoder.JSONDecodeError as e:
                    logging.warn('JSON load failed: {}'.format(e))
                    return []

        except aiohttp.client_exceptions.ClientConnectorError as e:
            logging.warn('Weather request failed: {}'.format(e))

            # We'll just default to nothing. For now.
            return []

    # Seriously forgive me padre, pls.
    return [x for x in request
            if same in x['properties']['geocode']['SAME']]


async def agent(db, *, freq=timedelta(minutes=5)):
    while True:
        logging.debug('Checking the weather..')
        qfilter = {'user': 1, 'same_codes': 1, 'filter': 1}
        async for sub in db.subscribers.find({}, qfilter):
            for location in sub['same_codes']:
                data = await getWeather(location)

                # Just stop here if no alerts.
                if len(data) is 0:
                    continue

                # Try not to send duplicate alerts.
                ids = await db.alerts.distinct('properties.id')

                # Actual processing.
                for alert in data:
                    if alert['properties']['id'] not in ids:
                        db.alerts.insert_one(alert)

                        # PEP8
                        severity = alert['properties']['severity']

                        if severity in sub['filter']:
                            # Easier on the character count.
                            headline = alert['properties']['headline']
                            statement = alert['properties']['description']

                            # The horror
                            logging.info(
                                '{} for {}'.format(
                                    headline, sub['user']
                                )
                            )

                            # Message payload
                            payload = {
                                'to': sub['user'],
                                'msg': '{}\n\n{}'.format(headline, statement),
                                'type': 'weather',
                            }

                            # Pass the infomration to Jarvis.
                            sock = create_connection(('192.168.1.200', 8888))
                            sock.send(msgpack.packb(payload))
                            sock.close()

                    # Release to loop if needed.
                    await asyncio.sleep(0)

        # 79 character limit...
        logging.debug(
            'agents.weather sleeping {} seconds'.format(freq.total_seconds())
        )

        # Repeat on timedelta object.
        await asyncio.sleep(freq.total_seconds())
