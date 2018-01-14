import asyncio
import logging
from agents import humble, weather


async def main():
    asyncio.ensure_future(humble.agent())
    # asyncio.ensure_future(weather.agent())

    # Wait for all to finish before closing up.
    asyncio.gather(*asyncio.Task.all_tasks())


if __name__ == '__main__':
    # Setup logging.
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)-8s %(message)s')

    # Get loop and run main() on it.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
