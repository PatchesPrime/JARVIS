import json
import aiohttp
import logging


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
                request = json.loads(request)['features']

        except aiohttp.client_exceptions.ClientConnectorError as e:
            logging.warn('Weather request failed: {}'.format(e))

            # We'll just default to nothing. For now.
            return []

    # Seriously forgive me padre, pls.
    return [x for x in request
            if same in x['properties']['geocode']['SAME']]
