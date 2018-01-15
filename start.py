import motor.motor_asyncio
import commands
import slixmpp
import logging
import asyncio
import msgpack
from inspect import signature
from datetime import datetime, timedelta
import config
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
            'alert': commands.addWeatherSub,
        }

        # Get a mongodb client and db
        mongo = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = mongo.bot

    async def start(self, event):
        # This should be awaited. Check commit.
        await self.db.authenticate(
            config.mongo_user,
            config.mongo_pass,
        )

        self.send_presence()
        self.get_roster()

        # Add our agents to the loop. Also I feel a little dirty doing this.
        asyncio.ensure_future(self._hush())
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
                # Honestly not acceptable. I'm creating bloat.
                params = signature(self.usable_functions[cmd]).parameters

                if 'db' in params.keys():
                    resp = await self.usable_functions[cmd](self.db, *args)
                    msg.reply(resp).send()
                else:
                    msg.reply(await self.usable_functions[cmd](*args)).send()

            else:
                msg.reply('Invalid permissions for that command.').send()

        except (UserWarning, KeyError, SyntaxError) as e:
            if type(e).__name__ == 'KeyError':
                end = 'My available commands:\n'
                for k, v in self.usable_functions.items():
                    end += '{0}\n{1}\n'.format(k, v.__doc__)

                msg.reply(end).send()
            else:
                # Actual command failure
                msg.reply(str(e)).send()


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
