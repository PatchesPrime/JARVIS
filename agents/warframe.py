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
        'OrokinCatalystBlueprint': 'Orokin Catalyst Blueprint',
        'OrokinReactorBlueprint': 'Orokin Reactor Blueprint',
        # 'Eventium': 'Synthula',
        # 'EnemyArmorReductionAuraMod': 'Corrosive Projection',
    }

    async with aiohttp.ClientSession() as session:
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)'
        }

        async with session.get(url, headers=headers, timeout=10) as response:
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
        check = await get_warframe()

        if check:
            query = {'warframe': {'$exists': True}}
            qfilter = {'user': 1, 'warframe': 1}

            # Message prefix.
            msg = [
                'Warframe Alert!'
            ]

            # Alert processing.
            for alert in check:
                pattern = {'item': alert['item'], 'id': alert['id']}
                if await db.warframe.find_one(pattern):
                    continue

                # If it's new, get the message ready.
                msg.append('{name} - Expires: {expires}'.format(**alert))
                await db.warframe.insert(alert)

            # Message sending.
            async for sub in db.subscribers.find(query, qfilter):
                if len(msg) > 1 and sub['warframe'] is True:
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

        # Reeeeee, 79 characters.
        logging.debug(
            'agents.warframe sleeping {} seconds'.format(
                freq.total_seconds()
            )
        )
        await asyncio.sleep(freq.total_seconds())
