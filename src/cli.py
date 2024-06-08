import logging
from optparse import OptionParser
import asyncio
import signal

from src.torrent import Torrent
from src.client import TorrentClient

logger = logging.getLogger(__name__)


def get_option_parser() -> OptionParser:
    parser = OptionParser()
    parser.add_option('-T', '--torrent', dest='torrent', help='Torrent for file to download')
    parser.add_option('-p', '--port', default='8888', dest='port',
                      help='Port to listen on.', type='int')
    parser.add_option('-d', '--debug', action='store_true', dest='debug',
                      help='Log debug messages.')
    parser.add_option('-e', '--errors', action='store_true', dest='error',
                      help='Log error messages only.')
    parser.add_option('-l', '--log-file', dest='log_file', help='Log file.')
    
    return parser

def configure_logger(options: OptionParser):
    logger.addHandler(logging.StreamHandler())
    if options.log_file:
        logger.addHandler(logging.FileHandler(options.log_file))
    if options.debug:
        logger.setLevel(logging.DEBUG)
    elif options.error:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)

def signal_handler(client, task):
    logger.info('Exiting, please wait until everything is shutdown...')
    client.stop()
    task.cancel()

async def main():
    options, _ = get_option_parser().parse_args()
    configure_logger(options)
    client = TorrentClient(Torrent(options.torrent), options.port)
    task = asyncio.create_task(client.start())
    signal.signal(signal.SIGINT, lambda *_: signal_handler(client, task))
    try:
        await task
    except asyncio.CancelledError:
        logger.warning("Event loop was cancelled")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Unexpected error, {str(e)}")