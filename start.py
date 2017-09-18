import slixmpp
import logging
import asyncio
import msgpack
import json
from datetime import datetime
import motor.motor_asyncio
import socket
import commands
from agents.humble import humbleScrape


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
        }

        with open('secrets', 'rb') as secrets:
            # We need our authentication.
            self.authsecrets = msgpack.unpackb(secrets.read(), encoding='utf-8')

            # Now we use our authentication.
            mongo = motor.motor_asyncio.AsyncIOMotorClient()

            # Assign and authenticate.
            self.db = mongo.bot
            self.db.authenticate(authsecrets['mongo_user'], authsecrets['mongo_pass'])

    def start(self, event):
        self.send_presence()
        self.get_roster()

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

    async def _humble(self):
        while True:
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
                        if await self.db.subscribers.find_one(pattern):
                            # Skip this game.
                            continue


                        # PEP8 is responsible for this. I just can't help myself.
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
                        {'$set': {'sale_end': game['sale_end'],
                                  'human_name': game['human_name']
                        }},
                        upsert=True
                    )

                    # Same as above.
                    await asyncio.sleep(0)

            # Acts sort of like a timer.
            await asyncio.sleep((60*60)*5)



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
        casted_msg['cmd']  = cmd
        casted_msg['args'] = args
        casted_msg['from'] = str(casted_msg['from'])
        casted_msg['to']   = str(casted_msg['to'])
        casted_msg['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store it.
        await self.db.messages.insert_one(casted_msg)

        # Command processing.
        if cmd == 'register_user' and await self._isAdmin(msg['from'].bare):
            if len(args) >= 2:
                req = await commands.registerUser(*args)
                if req == 201:
                    msg.reply('Registered the requested user, sir.').send()
                else:
                    msg.reply('Apologies, but there was an error.').send()

        elif cmd == 'delete_user' and await self._isAdmin(msg['from'].bare):
            if len(args) == 1:
                req = await commands.deleteUser(args[0])
                if req == 200:
                    msg.reply('Removed {0}\'s credentials, sir.'.format(
                        args[0])).send()
                else:
                    msg.reply('Apologies, sir; an error has occured..').send()

        elif cmd == 'update_user' and await self._isAdmin(msg['from'].bare):
            if len(args) >= 1:
                # Build a payload out of the arguments list in JSON.
                try:
                    args_payload = json.loads(' '.join(args[1:]))
                except ValueError as e:
                    # The things I do for PEP8.
                    body = (
                        'Sorry sir, you\'ve provided me with invalid JSON:',
                        ' {0}'.format(e)  # A bit verbose, but accurate.
                    )

                    # Send and return.
                    msg.reply(body).send()
                    return

                # Otherwise, process the command.
                req = await commands.updateUser(args[0], args_payload)
                if req == 200:
                    msg.reply('Updated the user, sir.').send()
                else:
                    msg.reply('Forgive me, but there was an error..').send()

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

        else:
            end = "My available commands, sir:\n"
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
