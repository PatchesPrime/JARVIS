import slixmpp
import logging
import asyncio
import msgpack
import json
from datetime import datetime
import pymongo
import commands


class EchoBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler('session_start', self.start)
        self.add_event_handler('message', self.message)

        # Commands available for use, with help strings.
        self.usable_functions = {
            'register_user': commands.registerUser.__doc__,
            'delete_user': commands.deleteUser.__doc__,
            'update_user': commands.updateUser.__doc__,
        }

        with open('secrets', 'rb') as secrets:
            # We need our authentication.
            authsecrets = msgpack.unpackb(secrets.read(), encoding='utf-8')

            # Now we use our authentication.
            mongo = pymongo.MongoClient()

            # Assign and authenticate.
            self.db = mongo.bot
            self.db.authenticate(authsecrets['mongo_user'], authsecrets['mongo_pass'])

    def start(self, event):
        self.send_presence()
        self.get_roster()

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
        self.db.messages.insert_one(casted_msg)

        # Command processing.
        if cmd == 'register_user':
            if len(args) >= 2:
                req = await asyncio.ensure_future(commands.registerUser(*args))
                if req == 201:
                    msg.reply('Registered the requested user, sir.').send()
                else:
                    msg.reply('Apologies, but there was an error.').send()

        elif cmd == 'delete_user':
            if len(args) == 1:
                req = await asyncio.ensure_future(commands.deleteUser(args[0]))
                if req == 200:
                    msg.reply('Removed {0}\'s credentials, sir.'.format(
                        args[0])).send()
                else:
                    msg.reply('Apologies, sir; an error has occured..').send()

        elif cmd == 'update_user':
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
                req = await asyncio.ensure_future(commands.updateUser(args[0], args_payload))
                if req == 200:
                    msg.reply('Updated the user, sir.').send()
                else:
                    msg.reply('Forgive me, but there was an error..').send()

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
    xmpp = EchoBot(
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
