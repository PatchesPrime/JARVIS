import motor.motor_asyncio
import commands
import slixmpp
import logging
import asyncio
import msgpack
from inspect import signature
from datetime import datetime, timedelta
import config


class JARVIS(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler('session_start', self.start)
        self.add_event_handler('changed_status', self.status_handler)
        self.add_event_handler('message', self.message)

        # Commands available for use, with help strings.
        self.usable_functions = {
            'register_user': commands.registerUser,
            'delete_user': commands.deleteUser,
            'update_user': commands.updateUser,
            'add_sub': commands.addSubscriber,
            'del_sub': commands.deleteSubscriber,
            'same': commands.getSAMECode,
            'gitwatch': commands.addGitSub,
            'delgit': commands.delGitSub,
            'solve': commands.solveMath,
            'alert': commands.addWeatherSub,
        }

        # Get a mongodb client and db
        mongo = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = mongo.bot

        # Simple list to note who is busy.
        self.busy = list()

    async def start(self, event):
        # This should be awaited. Check commit.
        await self.db.authenticate(
            config.mongo_user,
            config.mongo_pass,
        )

        self.send_presence()
        self.get_roster()

    async def status_handler(self, pres):
        '''Handle the busy list via status changes.'''
        who = pres['from'].bare

        # Simple logic to maintain the list.
        if pres['type'] == 'dnd':
            if who not in self.busy:
                self.busy.append(who)
        else:
            if who in self.busy:
                self.busy.remove(who)

        logging.debug('Status of busy list: {}'.format(self.busy))

    async def notifyUser(self, user, msg):
        '''Simple helper method for me.'''
        if user not in self.busy:
            self.send_message(
                mto=user,
                mtype='chat',
                mbody=msg,
            )

    async def _isAdmin(self, user):
        # Async List Comprehensions and PEP8 formatting
        admin = [
            x['user'] async for x in self.db.subscribers.find({'admin': True})
        ]

        # Are they an admin?
        return user in admin

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

        except (UserWarning, KeyError, SyntaxError, TypeError) as e:
            if type(e).__name__ == 'KeyError':
                end = 'My available commands:\n'
                for k, v in self.usable_functions.items():
                    end += '{0}\n{1}\n'.format(k, v.__doc__)

                msg.reply(end).send()

            elif type(e).__name__ == 'TypeError':
                # Tell them how to use it.
                msg.reply(self.usable_functions[cmd].__doc__).send()

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

            if data['to'] == 'all_friends':
                # This should be a dictionary and it's not. Why?
                # Come on library developer :(
                for friend in xmpp.client_roster:
                    subtype = xmpp.client_roster[friend]['subscription']

                    # If they aren't mutual friends with Jarvis, skip
                    if subtype != 'both':
                        continue

                    await xmpp.notifyUser(friend, data['msg'])

            else:
                await xmpp.notifyUser(data['to'], data['msg'])

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
