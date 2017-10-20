import aiohttp
import logging
import json
import msgpack
import asyncio
from os.path import expanduser
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor


async def runREST(httptype, endpoint, payload=None, url=None, headers=None):
    if payload is not None:
        if type(payload) is not dict:
            raise ValueError('payload argument must be dict')

    authsecrets = await readFile(expanduser('~/projects/JARVIS/secrets'))

    # Default URL is our local REST
    if url is None:
        url = 'http://localhost:9090/plugins/restapi/v1/{0}/'.format(
            endpoint
        )
    else:
        url += endpoint

    # Default headers for our local REST API.
    if headers is None:
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
            'Authorization': authsecrets['restapi_key'],
            'Content-Type': 'application/json',
        }

    async with aiohttp.ClientSession() as session:
        # Build and initiate the request.
        try:
            # Hahahahaha
            if payload is None:
                req = getattr(session, httptype)
                async with req(url, headers=headers) as response:
                    return response
            else:
                req = getattr(session, httptype)
                async with req(url, headers=headers, data=json.dumps(payload)) as response:
                    return response

        except AttributeError as e:
            logging.error('Failed to run REST API request..{}'.format(e))
            return None


async def addSubscriber(db, user, same_codes=None, weather_filter=None, admin=False):
    '''
    Add a subscriber to my MongoDB for notable weather alerts.
    USAGE: add_sub user@host
    USAGE: add_sub user@host add_sub test@test {"admin": true}

    NOTE: valid JSON attributes:
        'same_codes': ['samecode1', 'samecode2']
        'weather_filter': ['Severe', 'Unknown']
        'admin': false
    '''
    if same_codes is None:
        same_codes = []

    if weather_filter is None:
        weather_filter = []

    result = await db.subscribers.insert_one(
        {
            'user': user,
            'same_codes': list(same_codes),
            'filter': list(weather_filter),
            'admin': admin,
            'hush': {
                'active': False,
                'started': datetime.now(),
                'expires': datetime.now(),
            },
            'git': [],
        }
    )

    # Return the ID of the inserted subscriber.
    return result.inserted_id


async def deleteSubscriber(db, user):
    '''
    Delete a subscriber from my MongoDB for notable weather alerts.
    USAGE: del_sub user@host
    '''
    result = await db.subscribers.delete_one(
        {
            'user': str(user)
        }
    )

    return result.deleted_count


async def addGitSub(db, user, gituser, gitrepo):
    '''
    Add a subscription to a GitHub git repo to watch for commits.
    USAGE: gitwatch github_username github_repository

    Example: gitwatch PatchesPrime JARVIS
    will watch 'PatchesPrime' users 'JARVIS' repo.
    '''
    result = await db.subscribers.update_one(
        {'user': str(user)},
        {'$push': {'git': {'user': str(gituser), 'repo': str(gitrepo)}}},
        upsert=True
    )

    return result.modified_count


async def delGitSub(db, user, gituser, gitrepo):
    '''
    Delete a subscription to a GitHub git repo to watch for commits.
    USAGE: delgit github_username github_repository

    Example: delgit PatchesPrime JARVIS
    '''
    result = await db.subscribers.update_one(
        {'user': str(user)},
        {'$pull': {'git': {'user': str(gituser), 'repo': str(gitrepo)}}},
    )

    return result.modified_count


async def registerUser(user, pwd):
    '''
    Register a user on HIVEs XMPP server.
    USAGE: register_user username password
    Note: username should be bare, without @host.
    '''
    payload = {
        'username': user,
        'password': pwd,
    }

    req = await runREST('post', 'users', payload=payload)
    return req.status


async def deleteUser(user):
    '''
    Delete a users registration on HIVEs XMPP server.
    USAGE: delete_user username
    NOTE: username should be bare, without @host.
    '''
    endpoint = 'users/{0}'.format(user)
    req = await runREST('delete', endpoint)

    return req.status


async def updateUser(user, payload):
    '''
    Update a user on HIVEs XMPP server.
    USAGE update_user user {"Valid": "JSON"}

    Properties: 'username', 'password', 'email', 'name'.
    examples:
    update_user jarvis {"name": "Just Jarvis"}
    update_user jarvis {"name": "Just Jarvis", "password": "ayyy"}

    NOTE: You MUST use double quotes due to JSON handling.
    '''
    api = 'users/{0}'.format(user)

    # Empty payload to work with.

    req = await runREST('put', api, payload=payload)

    return req.status


async def hush(db, user, timeout):
    '''
    Silence to bot for the specified time in hours.

    USAGE: hush 4
    '''
    await db.subscribers.update_one(
        {'user': user},
        {
            '$set': {
                'hush': {
                    'active': True,
                    'started': datetime.now(),
                    'expires': datetime.now() + timedelta(hours=float(timeout))
                }
            }
        }
    )


async def readFile(filename, loop=None):
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

    USAGE: same zipcodeHere
    '''
    # We need this information. They technically run in another thread.
    authsecrets = await readFile(expanduser('~/projects/JARVIS/secrets'))
    codes = await readFile(expanduser('~/projects/JARVIS/agents/same.codes'))

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
