import asyncio
import os
import logging
import importlib.util
import motor.motor_asyncio
import config


# Build a list of functions from the modules in agents folder.
runners = list()
for name in os.listdir('./agents'):
    if name.endswith('.py') and not name.startswith('_'):
        # This is the actual module name
        safe_name = 'agents.' + name[:-3]

        # Get a spec from it
        spec = importlib.util.find_spec(safe_name)

        # Get the module
        module = importlib.util.module_from_spec(spec)

        # Execute it
        spec.loader.exec_module(module)

        if hasattr(module, 'agent'):
            runners.append(getattr(module, 'agent'))


async def main():
    mongo = motor.motor_asyncio.AsyncIOMotorClient()
    db = mongo.bot
    await db.authenticate(
        config.mongo_user,
        config.mongo_pass,
    )

    # Ensure the future of all our agents.
    for f in runners:
        # Note: just make db an optional paramter if we don't
        # need one for an agent. Currently we do.
        asyncio.ensure_future(f(db))

    # Wait for all to finish before closing up.
    await asyncio.gather(*asyncio.Task.all_tasks())


if __name__ == '__main__':
    # Setup logging.
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)-8s %(message)s')

    # Get loop and run main() on it.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
