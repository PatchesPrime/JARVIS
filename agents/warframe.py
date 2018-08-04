import aiohttp
import json
import asyncio
import logging
from datetime import timedelta, datetime
from socket import create_connection
import msgpack


async def get_warframe():
    # URL for JSON data.
    url = "http://content.warframe.com/dynamic/worldState.php"

    # Watched items.
    watched = {
        'Alertium': 'Nitain Extract',
        'OrokinCatalyst': 'OrokinCatalyst',
        'OrokinReactor': 'OrokinReactor',
        # 'Eventium': 'Synthula',
    }

    async with aiohttp.ClientSession() as session:
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)'
        }

        async with session.get(url, headers=headers, timeout=3) as response:
            data = json.loads(await response.text())

            results = []
            for alert in data['Alerts']:
                # Shorthand
                mission_rewards = alert['MissionInfo']['missionReward']
                alert_id = alert['_id']['$oid']

                # Split into two lines, PEP8 pls.
                expires = int(alert['Expiry']['$date']['$numberLong']) / 1000
                expires = datetime.fromtimestamp(expires)

                # TODO: clean all this up.
                # Is it a counted or no?
                field = mission_rewards.get('countedItems')
                if field:
                    for item in field:
                        item_name = item['ItemType'].split('/')[-1]
                        if any(thing in item['ItemType'] for thing in watched.keys()):
                            results.append(
                                {
                                    'id': alert_id,
                                    'item': item_name,
                                    'name': watched[item_name],
                                    'expires': expires
                                }
                            )
                else:
                    # We don't concern ourselves with credits-only alerts.
                    if 'items' not in mission_rewards.keys():
                        continue

                    for item in mission_rewards['items']:
                        item_name = item.split('/')[-1]
                        if any(thing in item for thing in watched.keys()):
                            results.append(
                                {
                                    'id': alert_id,
                                    'item': item_name,
                                    'name': watched[item_name],
                                    'expires': expires
                                }
                            )

            return results


async def agent(db, *, freq=timedelta(minutes=5)):
    while True:
        logging.debug('Checking Warframe Alerts..')
        # Known IDs
        known = [x['id'] async for x in db.warframe.find()]
        check = await get_warframe()

        query = {'warframe': {'$exists': True}}
        qfilter = {'user': 1, 'warframe': 1}
        async for sub in db.subscribers.find(query, qfilter):
            if len(check) > 0:
                msg = [
                    'Warframe Alert!'
                ]

                for alert in check:
                    if alert['id'] in known:
                        continue
                    msg.append('{name} - Expires: {expires}'.format(**alert))

                if len(msg) > 1:
                    # Payload.
                    payload = {
                        'to': sub['user'],
                        'msg': '\n'.join(msg),
                        'type': 'warframe',
                    }

                    # Pass the payload to Jarvis.
                    sock = create_connection(('192.168.1.200', 8888))
                    sock.send(msgpack.packb(payload))
                    sock.close()

        # Add them to the list.
        await db.warframe.insert(check)

        # Reeeeee, 79 characters.
        logging.debug(
            'agents.warframe sleeping {} seconds'.format(
                freq.total_seconds()
            )
        )
        await asyncio.sleep(freq.total_seconds())
