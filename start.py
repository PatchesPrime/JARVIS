import slixmpp
import logging
import asyncio
import secrets


class EchoBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler('session_start', self.start)
        self.add_event_handler('message', self.message)

    def start(self, event):
        self.send_presence()
        self.get_roster()

    def message(self, msg):
        print(msg)


async def handle_echo(reader, writer):
    # message = ''
    # while not reader.at_eof():
    data = await reader.read()
    logging.warn('msg from: {0}, data: {1}'.format(
        writer.get_extra_info('peername'),
        data.decode(),
    ))

    # Just to be sure...
    writer.close()
    # # Send a message.
    # xmpp.send_message(
    #     mto='patches@hive.nullcorp.org',
    #     mtype='chat',
    #     mbody=message[-10:]
    # )


if __name__ == '__main__':
    # Setup logging.
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s %(message)s')

    # Build the bot object. Also has a loop exposed at obj.loop
    xmpp = EchoBot(
        secrets.auth['xmppuser'],
        secrets.auth['xmpppass']
    )

    # Add a TCP listener to the bots loop.
    xmpp.loop.run_until_complete(
        asyncio.start_server(
            handle_echo, 'localhost', 8888
        )
    )

    # Register some plugins.
    xmpp.register_plugin('xep_0199')  # XMPP Ping

    # Connect and run the loop.
    xmpp.connect()
    xmpp.process()
