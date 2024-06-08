import aiohttp
from urllib.parse import urlencode
import logging
from typing import Dict
import socket

from src import bencoding
from src.util import _calculate_peer_id, _decode_port

logger = logging.getLogger(__name__)


class TrackerResponse:
    """
    The response from the tracker after a successful connection to the
    trackers announce URL.

    Even though the connection was successful from a network point of view,
    the tracker might have returned an error (stated in the `failure`
    property).
    """
    def __init__(self, response: Dict):
        self.response = response
        
    @property
    def failure(self):
        """
        If this response was a failed response, this is the error message to
        why the tracker request failed.
        If no error occurred this will be None
        """
        if b'failure reason' in self.response:
            return self.response[b'failure reason'].decode()
    
    @property
    def interval(self) -> int:
        """
        Interval in seconds that the client should wait between sending
        periodic requests to the tracker.
        """
        return self.response.get(b'interval', 0)
        
    @property
    def complete(self) -> int:
        """
        Number of peers with the entire file, i.e. seeders.
        """
        return self.response.get(b'complete', 0)
    
    @property
    def incomplete(self) -> int:
        """
        Number of non-seeder peers, aka "leechers".
        """
        return self.response.get(b'incomplete', 0)
    
    @property
    def peers(self):
        """
        A list of tuples for each peer structured as (ip, port)
        """
        # The BitTorrent specification specifies two types of responses. One
        # where the peers field is a list of dictionaries and one where all
        # the peers are encoded in a single string
        peers = self.response[b'peers']
        if type(peers) == list:
            logger.debug('Dictionary model peers are returned by tracker')
            return [(p[b'ip'].decode(), p[b'port']) for p in peers]
        else:
            logger.debug('Binary model peers are returned by tracker')

            # Split the string in pieces of length 6 bytes, where the first
            # 4 characters is the IP the last 2 is the TCP port.
            peers = [peers[i:i+6] for i in range(0, len(peers), 6)]
            
            # Convert the encoded address to a list of tuples
            return [(socket.inet_ntoa(p[:4]), _decode_port(p[4:]))
                    for p in peers]
    

class Tracker:
    """
    Represents the connection to a tracker for a given Torrent that is either
    under download or seeding state.
    """
    def __init__(self, torrent, port=6889):
        self.torrent = torrent
        self.peer_id = _calculate_peer_id()
        self.http_client = aiohttp.ClientSession()
        self._port = port
        
    async def connect(self, 
                      first: bool = None,
                      uploaded: int = 0,
                      downloaded: int = 0):
        """
        Makes the announce call to the tracker to update with our statistics
        as well as get a list of available peers to connect to.

        If the call was successful, the list of peers will be updated as a
        result of calling this function.

        :param first: Whether or not this is the first announce call
        :param uploaded: The total number of bytes uploaded
        :param downloaded: The total number of bytes downloaded
        """
        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'port': self._port,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'left': self.torrent.total_size - downloaded,
            'compact': 1
        }
        if first:
            params['event'] = 'started'
        
        url = self.torrent.announce + '?' + urlencode(params)
        logger.info(f"Connecting to tracker at {url}")
        
        async with self.http_client.get(url) as response:
            if not response.status == 200:
                raise ConnectionError(f"Unable to connect to tracker: status {response.status}")
            
            data = await response.read()
            self.raise_for_error(data)
            return TrackerResponse(bencoding.Decoder(data).decode())
    
    def close(self):
        self.http_client.close()
        
    def raise_for_error(self, tracker_response):
        """
        To detech errors by tracker even if the response status is 200
        """
        try:
            message = tracker_response.decode()
            if "failure" in message:
                raise ConnectionError(f"Unable to connect to tracker: {message}")
        except UnicodeDecodeError:
            pass
