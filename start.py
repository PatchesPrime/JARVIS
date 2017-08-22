import slixmpp
import logging
import asyncio
import msgpack


class EchoBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler('session_start', self.start)
        self.add_event_handler('message', self.message)

    def start(self, event):
        self.send_presence()
        self.get_roster()

    def message(self, msg):
        #print(msg)
        pass


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
            handle_echo, 'localhost', 8888
        )
    )

    # Register some plugins.
    xmpp.register_plugin('xep_0199')  # XMPP Ping

    # Connect and run the loop.
    xmpp.connect()
    xmpp.process()
