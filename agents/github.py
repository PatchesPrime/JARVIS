import aiohttp
from os.path import expanduser
from commands import readfile


async def getCommits(user, repo):
    '''
    Simple method to retrieve the commits for a users repository on github.
    '''
    async with aiohttp.ClientSession() as session:
        url = f'https://api.github.com/repos/{user}/{repo}/commits'
        secrets = await readfile(expanduser('~/projects/JARVIS/secrets'))
        auth = {
            'Authorization': 'token {}'.format(secrets['github'])
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
