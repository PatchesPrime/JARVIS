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
    watched = ['Alertium', 'OrokinCatalyst', 'OrokinReactor']

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
                        if any(thing in item['ItemType'] for thing in watched):
                            results.append(
                                {
                                    'id': alert_id,
                                    'item': item['ItemType'].split('/')[-1],
                                    'expires': expires
                                }
                            )
                else:
                    # We don't concern ourselves with credits-only alerts.
                    if 'items' not in mission_rewards.keys():
                        continue

                    for item in mission_rewards['items']:
                        if any(thing in item for thing in watched):
                            results.append(
                                {
                                    'id': alert_id,
                                    'item': item.split('/')[-1],
                                    'expires': expires
                                }
                            )

            return results


async def agent(db, *, freq=timedelta(minutes=5)):
    while True:
        logging.debug('Checking Warframe Alerts..')
        check = await get_warframe()

        query = {'warframe': {'$exists': True}}
        qfilter = {'user': 1, 'warframe': 1}
        async for sub in db.subscribers.find(query, qfilter):
            if len(check) > 0:
                msg = [
                    'Warframe Alert!'
                ]

                for alert in check:
                    msg.append('{item} - Expires: {expires}'.format(**alert))

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
