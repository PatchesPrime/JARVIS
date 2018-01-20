import aiohttp
import logging
import json
import msgpack
import asyncio
from os.path import expanduser
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import config
from sympy import solve, simplify, SympifyError
import arrow


async def runREST(httptype, endpoint, payload=None, url=None, headers=None):
    if payload is not None:
        if type(payload) is not dict:
            raise ValueError('payload argument must be dict')

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
            'Authorization': config.restapi_key,
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


async def currentTime(zone=None):
    '''
    Displays the time of a given timezone in a formatted way.

    USAGE: time
    USAGE: time EST
    '''
    if zone:
        # Get the current time in a specific timezone
        return 'Current time in {} is {}'.format(zone, arrow.now(zone))

    # Display the local time formatted on Type/Key error
    return 'Current time is: {}'.format(arrow.now())


async def convertTo(fromTz, toTz):
    '''
    Displays the given time/date in a specific timezone and returns
    the difference.

    USAGE: tz fromTimezone toTimezone
    '''
    # Get that tzinfo shit out of here...
    tzFrom = arrow.now(fromTz).datetime.replace(tzinfo=None)
    tzTo = arrow.now(toTz).datetime.replace(tzinfo=None)

    # Get a difference response now with the tzinfo bs gone
    diff = tzFrom - tzTo

    out = (
        'It is currently {} in {}.'.format(tzTo, toTz),
        'The difference is {}'.format(round(diff.seconds/3600))
    )

    return out


async def addSubscriber(db, user, admin=False):
    '''
    Add a subscriber to my MongoDB for notable weather alerts.
    USAGE: add_sub user@host
    '''
    result = await db.subscribers.insert_one(
        {
            'user': user,
            'same_codes': list(),
            'filter': ['Severe', 'Unknown'],
            'admin': bool(admin),
            'hush': {
                'active': False,
                'started': datetime.now(),
                'expires': datetime.now(),
            },
            'git': [],
        }
    )

    # Return the ID of the inserted subscriber.
    return 'As you wish! Their uid: {}'.format(result.inserted_id)


async def addWeatherSub(db, user, zipcode):
    '''
    Add weather alerts to my DB for subscriber 'user'.
    USAGE: alert_sub test@user 55555
    '''
    same = await getSAMECode(zipcode)  # Get the SAME.
    same = same.split()[-1]  # Chop it up.

    result = await db.subscribers.update_one(
        {'user': str(user)},
        {'$push': {'same_codes': same}},
        upsert=True
    )

    if result.modified_count:
        return 'Added SAME ({}) to DB and will alert if needed.'.format(same)

    raise UserWarning('Something went wrong, please contact an admin..')


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

    return 'Certainly. {} users removed.'.format(result.deleted_count)


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

    if result.modified_count:
        return 'Git repo {}/{} added to my entry for {}'.format(
            gituser, gitrepo, user
        )

    raise UserWarning('Something went wrong adding git repo..')


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

    if result.modified_count:
        return 'Removed {}/{} repo from {} entry..'.format(
            gituser, gitrepo, user
        )

    raise UserWarning('Could not remove repo from {} entry.'.format(user))


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

    if req.status == 201:
        return 'User {} has been registered'.format(user)

    # Fail case, throw predictable exception.
    raise UserWarning('Something went wrong in adding the user..')


async def deleteUser(user):
    '''
    Delete a users registration on HIVEs XMPP server.
    USAGE: delete_user username
    NOTE: username should be bare, without @host.
    '''
    endpoint = 'users/{0}'.format(user)
    req = await runREST('delete', endpoint)

    if req.status == 200:
        return 'Destroyed \'{}\' user credentials'.format(user)

    raise UserWarning('Couldn\'t remove user..')


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

    # Trust that it's JSON.
    req = await runREST('put', api, payload=payload)

    if req.status == 200:
        return '{}\'s credentials have been updated.'.format(user)

    raise UserWarning('Something went wrong..')


async def readFile(filename, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    with open(filename, 'rb') as data:
        io_pool = ThreadPoolExecutor()
        obj = await loop.run_in_executor(io_pool, data.read)
        return msgpack.unpackb(obj, encoding='utf-8')


async def solveMath(expr):
    """
    Takes an mathematics expression or equation and sends it to
    the applicable function to find the solution from sympy

    USAGE: solve expression/equation

    NOTE: no spaces in expression/equation. Operations must be explicit.
    eg. requires 3*x rather than 3x
    """

    result = None
    if not isinstance(expr, str):
        raise TypeError("Error: solve requires string")

    if '=' in expr:
        # sympy requires all equations to be equal to 0
        # so we're gonna juggle numbers and move it all to one side,
        # removing the = operator.
        eqindex = expr.index('=')

        # subtracting the whole right side from left side.
        expr = "{before}-({after})".format(
            before=expr[:eqindex],
            after=expr[eqindex+1:]
        )
        try:
            result = solve(expr)
        except SympifyError as e:
            raise SyntaxError(e) from None

    else:  # not an equation, we're going to simplify.
        try:
            result = simplify(expr)
        except SympifyError as e:
            raise SyntaxError(e) from None

    result = str(result)
    if 'zoo' in result:
        result = "ZeroDivisionError"

    if result:
        return 'Here is my solution: {}'.format(result)

    raise UserWarning('I couldn\'t solve the problem..sorry :(')


async def getSAMECode(place):
    '''
    Get the SAME code for a given place. Trys to make it work
    yet probably wont.

    USAGE: same zipcodeHere
    '''
    # We need this information. They technically run in another thread.
    codes = await readFile(expanduser('~/projects/JARVIS/agents/same.codes'))

    async with aiohttp.ClientSession() as session:
        # We need to do this first.
        geocodeAPI = 'https://maps.googleapis.com/maps/api/geocode/json'

        # Build the payload and request it..
        payload = {'address': place, 'key': config.geocode_key}
        async with session.get(geocodeAPI, params=payload) as response:
            request = await response.json()

        try:
            # THERE WILL BE ONLY 79 CHARACTERS
            comps = request['results'][0]['address_components']
        except IndexError as e:
            # Occasionally the Google Geocode API randomly doesn't
            # return anything. One day I'll know why.
            logging.warn('IndexError: {}'.format(e))
            message = ('Something went wrong, likely googles fault',
                       'or perhaps invalid zipcode..')
            raise UserWarning(' '.join(message))

        # Forgive me padre for I have sinned.
        # types = {y for x in comps for y in x['types']}
        types = set()
        for comp in comps:
            for attrib in comp['types']:
                types.add(attrib)

                # I baby this loop.
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

            return 'Requested code, sir: {}'.format(codes[county + state])

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
                    message = ('Something went wrong, likely googles fault',
                               'or perhaps invalid zipcode..')
                    raise UserWarning(' '.join(message))

                for com in comp:
                    if 'administrative_area_level_2' in com['types']:
                        county = com['long_name'][:-7]

                    elif 'administrative_area_level_1' in com['types']:
                        state = ', {}'.format(com['short_name'])

                    # 'stop babying the loop' - Koz
                    await asyncio.sleep(0)

                try:
                    return 'The code, sir: {}'.format(codes[county + state])
                except UnboundLocalError:
                    # We couldn't find the county, sadly.
                    raise UserWarning('Couldn\'t get your county..')
