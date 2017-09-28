import json
import aiohttp


async def getWeather(same):
    '''
    Give it a postal code and it'll give you JSON representing the weather
    for that postcode.

    '''
    # URL for PEP8
    weatherAPI = 'https://api.weather.gov/alerts?active=1'

    # Now we can do this.
    async with aiohttp.ClientSession() as session:
        # There have been no complaints, but this will help them find me if
        # they have some. PS I love you NWS
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
        }

        async with session.get(weatherAPI, headers=headers) as response:
            request = await response.text()

            # Docs say aiohttp json() should use this by default
            # but it fails because mimetype without it..Weird
            request = json.loads(request)['features']

    # Seriously forgive me padre, pls.
    return [x for x in request
            if same in x['properties']['geocode']['SAME']]
