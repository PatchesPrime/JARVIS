import json
import aiohttp


async def humbleScrape():
    '''
    Scrape the humble store front page looking for
    free games.
    '''
    url = 'https://www.humblebundle.com/store'
    async with aiohttp.ClientSession() as session:
        # There have been no complaints, but this will help them find me if
        # they have some.
        headers = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
        }

        async with session.get(url, headers=headers) as response:
            page_src = await response.text()

        for line in page_src.splitlines():
            # So...sometimes this string isn't in the page? What?
            if 'page: {"strings"' in line:
                # Not very clean but it should do. Chop off 'page: '.
                shop = json.loads(line[12:-1])['entity_lookup_dict']

        try:
            games = [
                game for game in shop.values()
                if game.get('current_price') is not None
            ]

            freebies = [
                game for game in games if 0.0 in game['current_price']
            ]

            return freebies
        except UnboundLocalError:
            return []
