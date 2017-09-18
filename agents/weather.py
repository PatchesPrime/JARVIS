import msgpack
import logging
import json
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from os.path import expanduser


async def readfile(filename, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    with open(filename, 'rb') as data:
        io_pool = ThreadPoolExecutor()
        obj = await loop.run_in_executor(io_pool, data.read)
        return msgpack.unpackb(obj, encoding='utf-8')


async def getSAMECode(place):
    '''
    Get the SAME code for a given place. Trys to make it work
    yet probably wont.

    It's an ugly method. I should rewrite it.
    '''
    # We need this information. They technically run in another thread.
    authsecrets = await readfile(expanduser('~/projects/JARVIS/secrets'))
    codes = await readfile(expanduser('~/projects/JARVIS/agents/same.codes'))

    async with aiohttp.ClientSession() as session:
        # We need to do this first.
        geocodeAPI = 'https://maps.googleapis.com/maps/api/geocode/json'

        # Build the payload and request it..
        payload = {'address': place, 'key': authsecrets['geocode_key']}
        async with session.get(geocodeAPI, params=payload) as response:
            request = await response.json()

        try:
            # THERE WILL BE ONLY 79 CHARACTERS
            comps = request['results'][0]['address_components']
        except IndexError as e:
            # Occasionally the Google Geocode API randomly doesn't
            # return anything. One day I'll know why.
            logging.warn('IndexError: {}'.format(e))
            return None

        # Forgive me padre for I have sinned.
        # types = {y for x in comps for y in x['types']}
        types = set()
        for comp in comps:
            for attrib in comp['types']:
                types.add(attrib)

                # I baby this loop.
                await asyncio.sleep(0)

            # srsly
            await asyncio.sleep(0)

        # PEP8 pls
        if 'administrative_area_level_2' in types:
            for com in comps:
                if 'administrative_area_level_2' in com['types']:
                    county = com['long_name'][:-7]

                elif 'administrative_area_level_1' in com['types']:
                    state = ', {}'.format(com['short_name'])

                # More babying of loops.
                await asyncio.sleep(0)

            return codes[county + state]

        else:
            for com in comps:
                if 'locality' in com['types']:
                    city = com['long_name']
                elif 'administrative_area_level_1' in com['types']:
                    state = ', {}'.format(com['short_name'])

                # waaaahh
                await asyncio.sleep(0)

            # Not a fan of excessive code duplication, but
            # it'll be better than recursion.
            payload['address'] = city + state
            async with session.get(geocodeAPI, params=payload) as response:
                request = await response.json()

                try:
                    comp = request['results'][0]['address_components']
                except IndexError as e:
                    logging.warn('IndexError: {}'.format(e))
                    return None

                for com in comp:
                    if 'administrative_area_level_2' in com['types']:
                        county = com['long_name'][:-7]

                    elif 'administrative_area_level_1' in com['types']:
                        state = ', {}'.format(com['short_name'])

                    # 'stop babying the loop' - Koz
                    await asyncio.sleep(0)

                try:
                    return codes[county + state]
                except UnboundLocalError:
                    # We couldn't find the county, sadly.
                    raise KeyError('Couldn\'t get your county..')


async def getWeather(zipcode):
    '''
    Give it a postal code and it'll give you JSON representing the weather
    for that postcode.

    '''
    # URL for PEP8
    weatherAPI = 'https://api.weather.gov/alerts?active=1'

    # Now we can do this.
    async with aiohttp.ClientSession() as session:
        async with session.get(weatherAPI) as response:
            request = await response.text()

            # Docs say aiohttp json() should use this by default
            # but it fails because mimetype without it..Weird
            request = json.loads(request)['features']

    # Request it once.
    same = await getSAMECode(zipcode)

    if not same:
        # Same is none, lets just fail. Google..pls.
        return []

    # Seriously forgive me padre, pls.
    return [x for x in request
            if same in x['properties']['geocode']['SAME']]
