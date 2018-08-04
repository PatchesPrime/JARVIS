import aiohttp
import json
import asyncio
import logging
from datetime import timedelta
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

                # TODO: clean all this up.
                # Is it a counted or no?
                field = mission_rewards.get('countedItems')
                if field:
                    for item in field:
                        if any(thing in item['ItemType'] for thing in watched):
                            results.append(item['ItemType'])
                else:
                    # We don't concern ourselves with credits-only alerts.
                    if 'items' not in mission_rewards.keys():
                        continue

                    for item in mission_rewards['items']:
                        if any(thing in item for thing in watched):
                            results.append(item)

            return results
