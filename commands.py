import aiohttp
import logging
import json
import msgpack
import asyncio
from concurrent.futures import ThreadPoolExecutor
import config
from sympy import solve, simplify, SympifyError
import arrow


async def runREST(httptype, endpoint, payload=None, url=None, headers=None):
    # Must be lowercase for it to work
    httptype = httptype.lower()

    if payload is not None:
        if type(payload) is not dict:
            raise ValueError('payload argument must be dict')

    # Default URL is our local REST
    if url is None:
        url = 'http://{}/plugins/restapi/v1/{}/'.format(
            config.restapi_host,
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


async def currentTime(zone=None, *, caller=None):
    '''
    Displays the time of a given timezone in a formatted way.

    USAGE: time
    USAGE: time EST or US/Eastern
    '''
    if zone:
        time = {'MST': 'MST7MDT', 'PST': 'PST8PDT', 'CDT': 'CST6CDT'}

        if zone in time:
            zone = time[zone]

        # Get the current time in a specific timezone
        return 'Current time in {} is {}'.format(zone, arrow.now(zone))

    # Display the local time formatted on Type/Key error
    return 'Current time is: {}'.format(arrow.now())


async def convertTo(fromTz, toTz, *, caller=None):
    '''
    Displays the given time/date in a specific timezone and returns
    the difference.

    USAGE: tz fromTimezone toTimezone

    NOTE: Given arguments can be given with the normal version: 'US/Eastern'
    or the shorthand version: 'EST'.
    '''
    # Dict of unusual strings of timezones
    time = {'MST': 'MST7MDT', 'PST': 'PST8PDT', 'CDT': 'CST6CDT'}

    if fromTz in time:
        fromTz = time[fromTz]
    if toTz in time:
        toTz = time[toTz]

    # Get that tzinfo shit out of here...
    tzFrom = arrow.now(fromTz).datetime.replace(tzinfo=None)
    tzTo = arrow.now(toTz).datetime.replace(tzinfo=None)

    # Get a difference response now with the tzinfo bs gone
    diff = tzFrom - tzTo

    if diff.days < 0:
        diff = tzTo - tzFrom

    out = (
        'It is currently {} in {}.'.format(tzTo, toTz),
        'The difference is {} hours.'.format(round(diff.seconds / 3600))
    )

    return '\n'.join(out)


async def currencyExchange(currFrom, currTo, amount=1, *, caller=None):
    '''
    Get the current exchange rate between two currencies.

    USAGE: exchange FROM TO <amount>

    NOTE: parameters in <> are optional and not required.
    '''
    # Check if not empty
    if currFrom and currTo:
        currencyF, currencyT = currFrom.upper(), currTo.upper()
        request = currencyF + '_' + currencyT

        tup = ('convert?q=', request, '&compact=y')
        endpoint = ''.join(tup)

        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS'
        }

        url = 'https://free.currencyconverterapi.com/api/v5/'

        # Get API result
        call = await runREST('get', endpoint, None, url, headers)

        if call.status == 200:
            # Decode JSON
            response = await call.json()

            rate = response[request]['val']
            convert = float(amount) * float(rate)

            out = (
                f'The rate of {currFrom} to {currTo} is {rate}',
                f', with {amount}{currFrom.upper()} = {convert}{currTo.upper()}'
            )

            return ''.join(out)

    return ohSnap(currencyExchange, [currFrom, currTo], caller)


async def addSaleWatch(db, target, url, price, monthly=False, *, caller=None):
    '''
    Add a game for me to watch for a sale less than or equal to a price.

    USAGE: salewatch xmppUser humblebundle_store_url price monthly

    NOTE: xmppUser can be 'me' if it's for you, the price should
    be int/float (100, 100.5, etc). URL should be the FULL url to
    access the games store page on humblebundle website. Monthly
    is optional, and only required if you want to include the
    HumbleMonthly 10% discount.
    '''
    if target == 'me':
        target = caller

    # I hate this, but Jarvis passes strings and bool(non_empty_str) == True
    falsey = ['false', 'no', 'False', False]

    payload = {
        'name': str(url.split('/')[-1]),
        'price': float(price),
        'url': str(url),
        'discount': monthly not in falsey,
    }

    result = await db.subscribers.update_one(
        {'user': str(target)},
        {'$push': {'sales_watch': payload}},
        upsert=True
    )

    if result.modified_count:
        return 'Okay, I\'ll keep an eye out for sales of {} @ {}'.format(
            url.split('/')[-1], price
        )

    return ohSnap(addSaleWatch, [target, url, price], caller)


async def addSubscriber(db, target, admin=False, *, caller=None):
    '''
    Add a subscriber to my database, really only use for adding a 'template'.
    USAGE: add_sub user@host <admin?>
    '''
    result = await db.subscribers.insert_one(
        {
            'user': target,
            'same_codes': list(),
            'filter': ['Severe', 'Unknown'],
            'admin': bool(admin),
            'git': [],
        }
    )

    # Return the ID of the inserted subscriber.
    return 'As you wish! Their uid: {}'.format(result.inserted_id)


async def addWeatherSub(db, target, zipcode, *, caller=None):
    '''
    Add weather alerts to my DB for subscriber 'user'.
    USAGE: add_alert test@user 55555
    '''
    if target == 'me':
        target = caller

    state = await db.state_data.find_one({'zip': zipcode})

    if not await db.subscribers.find_one({'user': str(target)}):
        logging.debug("addWeatherSub target not a subscriber, adding..")
        await addSubscriber(db, target, caller=caller)

    result = await db.subscribers.update_one(
        {'user': str(target)},
        {'$push': {'same_codes': state['same']}},
        upsert=True
    )

    if result.modified_count:
        return 'Added SAME ({}) to DB and will alert if needed.'.format(state['same'])

    return ohSnap(addWeatherSub, [target, zipcode], caller)


async def delWeatherSub(db, target, zipcode, *, caller=None):
    '''
    Delete weather alert subscription for subscriber 'user'.
    USAGE: del_alert test@user 55555
    '''
    if target == 'me':
        target = caller

    state = await db.state_data.find_one({'zip': zipcode})

    result = await db.subscribers.update_one(
        {'user': str(target)},
        {'$pull': {'same_codes': state['same']}},
        upsert=True
    )

    if result.modified_count:
        return 'Removed SAME ({}) from your Alerts.'.format(state['same'])

    return ohSnap(delWeatherSub, [target, zipcode], caller)


async def listWeatherSub(db, target, *, caller=None):
    '''
    List the weather alert subscriptions for the target 'user'.
    USAGE: list_alerts test@user
    '''
    if target == 'me':
        target = caller

    result = await db.subscribers.find_one(
        {'user': str(target)},
        {'same_codes': 1}
    )

    if result:
        return 'You\'re subscribed to: {}'.format(result['same_codes'])

    return ohSnap(listWeatherSub, [target], caller)


async def deleteSubscriber(db, user, *, caller=None):
    '''
    Delete a subscriber from my database.
    USAGE: del_sub user@host
    '''
    result = await db.subscribers.delete_one(
        {
            'user': str(user)
        }
    )

    if result.deleted_count:
        return 'Certainly. {} users removed.'.format(result.deleted_count)

    return ohSnap(deleteSubscriber, [user], caller)


async def addGitSub(db, target, gituser, gitrepo, *, caller=None):
    '''
    Add a subscription to a GitHub git repo to watch for commits.
    USAGE: add_git xmpp_id github_username github_repository

    Example: add_git user@example.org PatchesPrime JARVIS
    will watch 'PatchesPrime' users 'JARVIS' repo for xmppUser.

    NOTE: can accept 'me' as xmpp_id to add for yourself.
    '''
    if target == 'me':
        target = caller

    result = await db.subscribers.update_one(
        {'user': str(target)},
        {'$push': {'git': {'user': str(gituser), 'repo': str(gitrepo)}}},
        upsert=True
    )

    if result.modified_count:
        return 'Git repo {}/{} added to my entry for {}'.format(
            gituser, gitrepo, target
        )

    return ohSnap(addGitSub, [target, gituser, gitrepo], caller)


async def delGitSub(db, target, gituser, gitrepo, *, caller=None):
    '''
    Delete a subscription to a GitHub git repo to watch for commits.

    USAGE: del_git github_username github_repository

    Example: del_git user@example.org PatchesPrime JARVIS
    NOTE: can accept 'me' as xmpp_id to add for yourself.
    '''
    if target == 'me':
        target = caller

    result = await db.subscribers.update_one(
        {'user': str(target)},
        {'$pull': {'git': {'user': str(gituser), 'repo': str(gitrepo)}}},
    )

    if result.modified_count:
        return 'Removed {}/{} repo from {} entry..'.format(
            gituser, gitrepo, target
        )

    return ohSnap(delGitSub, [target, gituser, gitrepo], caller)


async def registerUser(target, pwd, *, caller=None):
    '''
    Register a user on HIVEs XMPP server.

    USAGE: register_user username password
    Note: username should be bare, without @host.
    '''
    payload = {
        'username': target,
        'password': pwd,
    }

    req = await runREST('post', 'users', payload=payload)

    if req.status == 201:
        return 'User {} has been registered'.format(target)

    # Fail case, throw predictable exception.
    return ohSnap(registerUser, [target, pwd], caller)


async def deleteUser(target, *, caller=None):
    '''
    Delete a users registration on HIVEs XMPP server.
    USAGE: delete_user username
    NOTE: username should be bare, without @host.
    '''
    endpoint = 'users/{0}'.format(target)
    req = await runREST('delete', endpoint)

    if req.status == 200:
        return 'Destroyed \'{}\' user credentials'.format(target)

    return ohSnap(deleteUser, [target], caller)


async def updateUser(target, *payload, caller=None):
    '''
    Update a user on HIVEs XMPP server.
    USAGE update_user user {"Valid": "JSON"}

    Properties: 'username', 'password', 'email', 'name'.
    examples:
    update_user jarvis {"name": "Just Jarvis"}
    update_user jarvis {"name": "Just Jarvis", "password": "ayyy"}

    NOTE: You MUST use double quotes due to JSON handling.
    '''
    api = 'users/{0}'.format(target)

    # Prepare the payload.
    payload = json.loads(' '.join(payload))

    # Trust that it's JSON.
    req = await runREST('put', api, payload=payload)

    if req.status == 200:
        return '{}\'s credentials have been updated.'.format(target)

    return ohSnap(updateUser, [target, payload], caller)


async def readFile(filename, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    with open(filename, 'rb') as data:
        io_pool = ThreadPoolExecutor()
        obj = await loop.run_in_executor(io_pool, data.read)
        return msgpack.unpackb(obj, encoding='utf-8')


async def solveMath(expr, *, caller=None):
    '''
    Takes an mathematics expression or equation and sends it to
    the applicable function to find the solution from sympy

    USAGE: solve expression/equation

    NOTE: no spaces in expression/equation. Operations must be explicit.
    eg. requires 3*x rather than 3x
    '''

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
            after=expr[eqindex + 1:]
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

    return 'I couldn\'t solve the problem..sorry :('


def ohSnap(func, args, caller, stacktrace=None):
    arg_str = ', '.join(args)
    name = func.__name__
    logging.warning(f'{caller} used {name}({arg_str}) TRACE: {stacktrace}')

    msg = (
        'Something went wrong, but worry not! I\'ve logged it',
        'and an admin will get around to fixing it as soon as they can.\n',
        'Have a nice day! :)'
    )

    return ' '.join(msg)
