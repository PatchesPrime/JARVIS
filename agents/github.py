import aiohttp
import asyncio
import msgpack
import logging
from datetime import timedelta
from socket import create_connection
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


async def agent(db, *, freq=timedelta(hours=12)):
    while True:
        logging.debug('Checking for new commits to known repositories..')
        async for sub in db.subscribers.find({}):
            for info in sub['git']:
                logging.debug('GIT: {}'.format(info))

                # Known repository specific commits.
                known = await db.git.distinct(
                    'commits.id',
                    {'id': '{user}/{repo}'.format(**info)}
                )

                # Request the data.
                data = await getCommits(info['user'], info['repo'])

                digest = [
                    '\nNew commit(s) on {}/{}\n\n'.format(
                        info['user'], info['repo']
                    )
                ]
                for commit in data:
                    if commit['id'] not in known:
                        # Prevents spam on first lookup of repo.
                        if len(known) >= 1:
                            msg = '{}\n{}'.format(
                                commit['message'],
                                commit['url']
                            )
                            # Using listcomps would look neater but
                            # also wouldn't be PEP8 compliant.
                            # The things I do for 79 characters.
                            digest.append(msg)

                        result = await db.git.update(
                            {'id': '{user}/{repo}'.format(**info)},
                            {'$push': {'commits': commit}},
                            upsert=True
                        )

                        logging.debug('Upsert: {}'.format(result))

                if len(digest) >= 2:
                    payload = {
                        'to': sub['user'],
                        'msg': '\n\n'.join(digest),
                        'type': 'git',
                    }

                    logging.debug('payload={}'.format(payload))

                    # Pass the infomration to Jarvis.
                    sock = create_connection(('192.168.1.200', 8888))
                    sock.send(msgpack.packb(payload))
                    sock.close()

        logging.debug(
            'agent.github sleeping for {}'.format(freq.total_seconds())
        )
        # Sleep for timedelta.
        await asyncio.sleep(freq.total_seconds())
