import aiohttp
import logging
import json
import msgpack


async def runREST(httptype, endpoint, payload=None):
    if payload is not None:
        if type(payload) is not dict:
            raise ValueError('payload argument must be dict')

    with open('secrets', 'rb') as f:
        secrets = msgpack.unpackb(f.read(), encoding='utf-8')

    # We need these.
    headers = {
        'Authorization': secrets['restapi_key'],
        'Content-Type': 'application/json',
    }

    url = 'http://localhost:9090/plugins/restapi/v1/{0}/'.format(
        endpoint)

    async with aiohttp.ClientSession() as session:
        # Build and initiate the request.
        try:
            # Hahahahaha
            if payload is None:
                req = getattr(session, httptype)
                async with req(url, headers=headers) as response:
                    return response.status
            else:
                req = getattr(session, httptype)
                async with req(url, headers=headers, data=json.dumps(payload)) as response:
                    return response.status

        except AttributeError as e:
            logging.error('Failed to run REST API request..{}'.format(e))
            return None


async def addSubscriber(db, user, postcode):
    '''
    Add a subscriber to my MongoDB for notable weather alerts.
    USAGE: add_sub user@host zipcode zipcode1 zipcode2 etc
    '''

    if type(postcode) is not list:
        raise TypeError('addSubscriber takes a list as second argument.')

    result = await db.subscribers.insert_one(
        {
            'user': str(user),
            'postcode': postcode
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
    return req


async def deleteUser(user):
    '''
    Delete a users registration on HIVEs XMPP server.
    USAGE: delete_user username
    NOTE: username should be bare, without @host.
    '''
    endpoint = 'users/{0}'.format(user)
    req = await runREST('delete', endpoint)

    return req


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

    return req
