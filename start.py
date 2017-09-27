import motor.motor_asyncio
import commands
import slixmpp
import logging
import asyncio
import msgpack
import json
from datetime import datetime
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
            'register_user': commands.registerUser.__doc__,
            'delete_user': commands.deleteUser.__doc__,
            'update_user': commands.updateUser.__doc__,
            'add_sub': commands.addSubscriber.__doc__,
            'del_sub': commands.deleteSubscriber.__doc__,
            'hush': commands.hush.__doc__,
            'same': commands.getSAMECode.__doc__,
            'gitwatch': commands.addGitSub.__doc__,
            'delgit': commands.delGitSub.__doc__,
        }

        with open('secrets', 'rb') as secrets:
            # We need our authentication.
            self.authsecrets = msgpack.unpackb(
                secrets.read(),
                encoding='utf-8'
            )

            # Now we use our authentication.
            mongo = motor.motor_asyncio.AsyncIOMotorClient()

            # Assign and authenticate.
            self.db = mongo.bot
            self.db.authenticate(
                authsecrets['mongo_user'],
                authsecrets['mongo_pass']
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

        # This method is meant to be used in an if, so..
        if user in admin:
            return True
        else:
            return False

    async def _hush(self):
        while True:
            logging.debug('Checking for expired hushes..')

            async for sub in self.db.subscribers.find({'hush.active': True}):
                if sub['hush']['expires'] < datetime.now():
                    result = await self.db.subscribers.update_one(
                        {'user': sub['user']},
                        {'$set': {'hush.active': False}}
                    )

                    logging.debug('Unhushed {}'.format(result))

            await asyncio.sleep(5)

    async def _humble(self):
        while True:
            logging.debug('Starting humbleScrape()..')
            free_games = await humbleScrape()

            if free_games:
                store = 'https://humblebundle.com/store/'

                # Async finding of subs.
                async for sub in self.db.subscribers.find({}):
                    for game in free_games:
                        pattern = {
                            'human_url': game['human_url'],
                            'sale_end': game['sale_end']
                        }

                        # Have we seen this sale?
                        if await self.db.games.find_one(pattern):
                            # Skip this game.
                            continue

                        # I hate and love PEP8.
                        logging.debug(
                            'Sending {} a message about {}'.format(
                                sub['user'], game['human_name']
                            )
                        )

                        # PEP8 is responsible for this.
                        # I just can't help myself.
                        self.send_message(
                            mto=sub['user'],
                            mtype='chat',
                            mbody='FREE GAME: {}\n{}{}'.format(
                                game['human_name'], store, game['human_url']
                            )
                        )

                        # Just in case something needs the loop
                        await asyncio.sleep(0)

                for game in free_games:
                    self.db.games.update_one(
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

                    # Same as above.
                    await asyncio.sleep(0)

            # Acts sort of like a timer.
            logging.debug('Passing back to loop')
            await asyncio.sleep((60*60)*5)

    async def _weather(self):
        while True:
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

            # Repeat every 15 minutes.
            await asyncio.sleep(60*5)

    async def _github(self):
        while True:
            async for sub in self.db.subscribers.find({}):
                for info in sub['git']:
                    logging.debug('GIT: {}'.format(info))
                    known = await self.db.git.distinct(
                        'commits.id',
                        {'id': '{user}/{repo}'.format(**info)}
                    )

                    logging.debug('KNOWN COMMITS: {}'.format(known))

                    data = await getCommits(info['user'], info['repo'])

                    for commit in data:
                        if commit['id'] not in known:
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

            await asyncio.sleep((60*60)*12)

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
        if cmd == 'register_user' and await self._isAdmin(msg['from'].bare):
            if len(args) >= 2:
                req = await commands.registerUser(*args)
                if req == 201:
                    msg.reply('Registered the requested user.').send()
                else:
                    msg.reply('Apologies, but there was an error.').send()

        elif cmd == 'delete_user' and await self._isAdmin(msg['from'].bare):
            if len(args) == 1:
                req = await commands.deleteUser(args[0])
                if req == 200:
                    msg.reply('Removed {0}\'s credentials.'.format(
                        args[0])).send()
                else:
                    msg.reply('Apologies; an error has occured..').send()

        elif cmd == 'update_user' and await self._isAdmin(msg['from'].bare):
            if len(args) >= 1:
                # Build a payload out of the arguments list in JSON.
                try:
                    args_payload = json.loads(' '.join(args[1:]))
                except ValueError as e:
                    # The things I do for PEP8.
                    body = (
                        'Sorry, you\'ve provided me with invalid JSON:',
                        ' {0}'.format(e)  # A bit verbose, but accurate.
                    )

                    # Send and return.
                    msg.reply(body).send()
                    return

                # Otherwise, process the command.
                req = await commands.updateUser(args[0], args_payload)
                if req == 200:
                    msg.reply('Updated the user.').send()
                else:
                    msg.reply('Forgive me, but there was an error..').send()

        elif cmd == 'hush' and await self._isAdmin(msg['from'].bare):
            if len(args) == 1:
                logging.debug('Hushing {}'.format(args[0]))

                # Sometimes I over do it, but I stick to the PEPs for
                # consistencies sake.
                msg.reply(
                    'Okay, sorry for the bother. Back in {} hours.'.format(
                        args[0]
                    )
                ).send()
                await commands.hush(self.db, msg['from'].bare, args[0])
            else:
                msg.reply(self.usable_functions[cmd]).send()

        elif cmd == 'add_sub' and await self._isAdmin(msg['from'].bare):
            if len(args) == 1:
                logging.debug('Adding sub with {}'.format(args))
                msg.reply('Added subscriber with unique ID: {}'.format(
                    await commands.addSubscriber(self.db, args[0])
                )).send()
            elif len(args) >= 2:
                kwargs = json.loads(''.join(args[1:]))
                logging.debug('Adding sub with kwargs: {}'.format(kwargs))

                msg.reply('Added subscriber with unique ID: {}'.format(
                    await commands.addSubscriber(self.db, args[0], **kwargs)
                )).send()
            else:
                msg.reply(self.usable_functions[cmd]).send()

        elif cmd == 'del_sub' and await self._isAdmin(msg['from'].bare):
            if len(args) == 1:
                logging.debug('Removing sub {}'.format(args))
                msg.reply('Removed {} matching "{}"'.format(
                    await commands.deleteSubscriber(self.db, args[0]),
                    args[0]
                )).send()
            else:
                msg.reply(self.usable_functions[cmd]).send()

        elif cmd == 'gitwatch' and await self._isAdmin(msg['from'].bare):
            if len(args) == 2:
                logging.debug(
                    'Adding git {} to {}'.format(args[1], msg['from'].bare)
                )
                msg.reply('Added {} git subscriptions.'.format(
                    await commands.addGitSub(self.db, msg['from'].bare, *args)
                )).send()
            else:
                msg.reply(self.usable_functions[cmd]).send()

        elif cmd == 'delgit' and await self._isAdmin(msg['from'].bare):
            if len(args) == 2:
                logging.debug(
                    'Deleting git {} to {}'.format(args[1], msg['from'].bare)
                )
                msg.reply('Deleted {} git subscriptions.'.format(
                    await commands.delGitSub(self.db, msg['from'].bare, *args)
                )).send()
            else:
                msg.reply(self.usable_functions[cmd]).send()

        elif cmd == 'same':
            if len(args) == 1:
                logging.debug('Retrieving SAME for {}'.format(msg['from']))
                try:
                    msg.reply('Certainly, the code requested: {}'.format(
                        await commands.getSAMECode(args[0])
                    )).send()
                except KeyError:
                    msg.reply('Apologies, I can\'t find that code').send()
            else:
                msg.reply(self.usable_functions[cmd]).send()

        else:
            end = "My available commands:\n"
            for k, v in self.usable_functions.items():
                end += "{0}\n{1}\n".format(k, v)

            msg.reply(end).send()


async def handle_echo(reader, writer):
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

    with open('secrets', 'rb') as secret:
        authsecrets = msgpack.unpackb(secret.read(), encoding='utf-8')

    # Build the bot object. Also has a loop exposed at obj.loop
    xmpp = JARVIS(
        authsecrets['xmppuser'],
        authsecrets['xmpppass']
    )

    # Add a TCP listener to the bots loop.
    xmpp.loop.run_until_complete(
        asyncio.start_server(
            handle_echo, '192.168.1.200', 8888
        )
    )

    # Register some plugins.
    xmpp.register_plugin('xep_0199')  # XMPP Ping

    # Connect and run the loop.
    xmpp.connect()
    xmpp.process()
