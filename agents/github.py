import aiohttp


async def getCommits(user, repo):
    async with aiohttp.ClientSession() as session:
        url = f'https://api.github.com/repos/{user}/{repo}/commits'
        async with session.get(url) as response:
            # Ha.
            data = [
                {
                    'id': commit['sha'],
                    'author': commit['author']['login'],
                    'message': commit['commit']['message'],
                    'date': commit['commit']['committer']['date'],
                    'url': commit['html_url']
                }
                for commit in await response.json()
            ]

            return data
