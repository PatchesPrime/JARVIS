import aiohttp
import config


async def getCommits(user, repo):
    '''
    Simple method to retrieve the commits for a users repository on github.
    '''
    async with aiohttp.ClientSession() as session:
        # Hard code the formatting.
        url = f'https://api.github.com/repos/{user}/{repo}/commits'

        # The rate limiting is much better for authenticated users.
        auth = {
            'User-Agent': 'JARVIS/v2 (https://github.com/PatchesPrime/JARVIS)',
            'Authorization': 'token {}'.format(config.github)
        }

        async with session.get(url, headers=auth) as response:
            # Ha.
            data = [
                {
                    'id': commit['sha'],
                    'author': commit['commit']['author']['name'],
                    'message': commit['commit']['message'],
                    'date': commit['commit']['committer']['date'],
                    'url': commit['html_url']
                }
                for commit in await response.json()
            ]

            return data
