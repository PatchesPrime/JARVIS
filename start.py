import motor.motor_asyncio
import commands
import slixmpp
import logging
import asyncio
import msgpack
import json
from datetime import datetime, timedelta
import config
from agents.humble import humbleScrape
from agents.weather import getWeather
from agents.github import getCommits


class JARVIS(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler('session_start', self.start)
        self.add_event_handler('message', self.message)

        # Commands available for use, with help strings.
        self.usable_functions = {
            'register_user': commands.registerUser,
            'delete_user': commands.deleteUser,
            'update_user': commands.updateUser,
            'add_sub': commands.addSubscriber,
            'del_sub': commands.deleteSubscriber,
            'hush': commands.hush,
            'same': commands.getSAMECode,
            'gitwatch': commands.addGitSub,
            'delgit': commands.delGitSub,
            'solve': commands.solveMath,
        }

        # Now we use our authentication.
        mongo = motor.motor_asyncio.AsyncIOMotorClient()

        # Assign and authenticate.
        self.db = mongo.bot
        self.db.authenticate(
            config.mongo_user,
            config.mongo_pass,
        )

    async def start(self, event):
        self.send_presence()
        self.get_roster()

        # Add our agents to the loop. Also I feel a little dirty doing this.
        asyncio.ensure_future(self._hush())
        asyncio.ensure_future(self._humble())
        asyncio.ensure_future(self._weather())
        asyncio.ensure_future(self._github())

    async def _isAdmin(self, user):
        # Async List Comprehensions and PEP8 formatting
        admin = [
            x['user'] async for x in self.db.subscribers.find({'admin': True})
        ]

        # Are they an admin?
        return user in admin

    async def _hush(self, *, freq=timedelta(seconds=5)):
        while True:
            logging.debug('Checking for expired hushes..')

            async for sub in self.db.subscribers.find({'hush.active': True}):
                if sub['hush']['expires'] < datetime.now():
                    result = await self.db.subscribers.update_one(
                        {'user': sub['user']},
                        {'$set': {'hush.active': False}}
                    )

                    logging.debug('Unhushed {}'.format(result))

            # Sleep on a timer.
            await asyncio.sleep(freq.total_seconds())

    async def _humble(self, *, freq=timedelta(hours=5)):
        while True:
            logging.debug('Starting humbleScrape()..')
            free_games = await humbleScrape()

            if free_games:
                store = 'https://humblebundle.com/store/'

                for game in free_games:
                    pattern = {
                        'human_url': game['human_url'],
                        'sale_end': game['sale_end']
                    }

                    # Have we seen this sale?
                    if await self.db.games.find_one(pattern):
                        # Skip this game.
                        continue

                    # I hate the way this is not just a dictionary.
                    # Why library author? Why?
                    for friend in self.client_roster:
                        subtype = self.client_roster[friend]['subscription']
                        if subtype == 'both':
                            # PEP8 is responsible for this.
                            # I just can't help myself.
                            self.send_message(
                                mto=friend,
                                mtype='chat',
                                mbody='FREE GAME: {}\n{}{}'.format(
                                    game['human_name'],
                                    store, game['human_url']
                                )
                            )
                        await asyncio.sleep(0)  # async sleep just in case

                    await self.db.games.update_one(
                        {'human_url': game['human_url']},
                        {
                            # Flymake was complaining now it's not.
                            '$set': {
                                'sale_end': game['sale_end'],
                                'human_name': game['human_name']
                            }
                        },
                        upsert=True
                    )

            # Sleep on a timer.
            await asyncio.sleep(freq.total_seconds())

    async def _weather(self, *, freq=timedelta(minutes=5)):
        while True:
            logging.debug('Checking the weather..')
            async for sub in self.db.subscribers.find({}):
                if sub['hush']['active']:
                    logging.debug('{} hushed me, skipping'.format(sub['user']))
                    continue

                for location in sub['same_codes']:
                    data = await getWeather(location)

                    # Just stop here if no alerts.
                    if len(data) is 0:
                        continue

                    # Try not to send duplicate alerts.
                    ids = await self.db.alerts.distinct('properties.id')

                    # Actual processing.
                    for alert in data:
                        if alert['properties']['id'] not in ids:
                            self.db.alerts.insert_one(alert)

                            # PEP8
                            severity = alert['properties']['severity']

                            if severity in sub['filter']:
                                # Easier on the character count.
                                headline = alert['properties']['headline']
                                statement = alert['properties']['description']

                                # The horror
                                logging.info(
                                    '{} for {}'.format(
                                        headline, sub['user']
                                    )
                                )

                                # Send the message.
                                self.send_message(
                                    mto=sub['user'],
                                    mtype='chat',
                                    mbody='{}\n\n{}'.format(
                                        headline, statement
                                    )
                                )
                        # Release to loop if needed.
                        await asyncio.sleep(0)

            # Repeat on timedelta object.
            await asyncio.sleep(freq.total_seconds())

    async def _github(self, *, freq=timedelta(hours=12)):
        while True:
            logging.debug('Checking for new commits to known repositories..')
            async for sub in self.db.subscribers.find({}):
                for info in sub['git']:
                    logging.debug('GIT: {}'.format(info))

                    # Known repository specific commits.
                    known = await self.db.git.distinct(
                        'commits.id',
                        {'id': '{user}/{repo}'.format(**info)}
                    )

                    # Request the data.
                    data = await getCommits(info['user'], info['repo'])

                    for commit in data:
                        if commit['id'] not in known:
                            # Prevents spam on first lookup of repo.
                            if len(known) >= 1:
                                self.send_message(
                                    mto=sub['user'],
                                    mtype='chat',
                                    mbody='New commit {}/{}: {}\n{}'.format(
                                        info['user'],
                                        info['repo'],
                                        commit['message'],
                                        commit['url']
                                    )
                                )

                            result = await self.db.git.update(
                                {'id': '{user}/{repo}'.format(**info)},
                                {'$push': {'commits': commit}},
                                upsert=True
                            )

                            logging.debug('Upsert: {}'.format(result))

            # Sleep for timedelta.
            await asyncio.sleep(freq.total_seconds())

    async def message(self, msg):
        # huehue
        (cmd, args) = (msg['body'].split()[0].lower(), msg['body'].split()[1:])
        logging.debug('Parsed message: {0}'.format((cmd, args)))

        # It's XML by default, but translates okay to a dict so we do that
        # But we need to preserve the msg object.
        casted_msg = dict(msg)

        # Add "data" to it. It's inside the message body, but I'd prefer
        # the actual data we use also gets added. Also clean up things
        # that cause errors.
        casted_msg['cmd'] = cmd
        casted_msg['args'] = args
        casted_msg['to'] = str(casted_msg['to'])
        casted_msg['from'] = str(casted_msg['from'])
        casted_msg['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store it.
        await self.db.messages.insert_one(casted_msg)

        # Command processing.
        try:
            # The commands non-admin can run..
            safeCommands = ('solve', 'help')

            # Command logic.
            if await self._isAdmin(msg['from'].bare) or cmd in safeCommands:
                # That's a doozy, ain't it?
                msg.reply(await self.usable_functions[cmd](*args)).send()

            msg.reply('You\'ve not been granted permissions for that.').send()

        except (UserWarning, KeyError) as e:
            if type(e).__name__ == 'KeyError':
                end = 'My available commands:\n'
                for k, v in self.usable_functions.items():
                    end += '{0}\n{1}\n'.format(k, v.__doc__)

                    msg.reply(end).send()
            else:
                # Actual command failure
                msg.reply(e).send()


async def handle_serviceMessage(reader, writer):
    '''
    This handles the messages sent from other scripts and services
    on the network that only use JARVIS to send a message. Pretty simple.
    '''
    data = await reader.read()
    addr = writer.get_extra_info('peername')
    logging.warn('msg from: {0}, len(data): {1}'.format(
        addr,
        len(data),
    ))

    # Just to be sure...
    writer.close()

    # Unpack the data
    try:
        if len(data) > 0:
            data = msgpack.unpackb(data, encoding='utf-8')

            # Send the message.
            xmpp.send_message(
                mto=data['to'],
                mtype='chat',
                mbody=data['msg']
            )

    except msgpack.exceptions.UnpackValueError as e:
        # Something went wrong, likely an empty message.
        logging.error('Failed to unpack: {}'.format(e))


if __name__ == '__main__':
    # Setup logging.
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s %(message)s')

    # Build the bot object. Also has a loop exposed at obj.loop
    xmpp = JARVIS(
        config.xmpp_user,
        config.xmpp_pass,
    )

    # Add a TCP listener to the bots loop.
    xmpp.loop.run_until_complete(
        asyncio.start_server(
            handle_serviceMessage, '192.168.1.200', 8888
        )
    )

    # Register some plugins.
    xmpp.register_plugin('xep_0199')  # XMPP Ping

    # Connect and run the loop.
    xmpp.connect()
    xmpp.process()
