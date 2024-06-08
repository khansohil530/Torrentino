import asyncio
import logging
import time

from src.tracker import Tracker
from src.manager import PieceManager
from src.protocol import PeerConnection

logger = logging.getLogger(__name__)

class TorrentClient:
    """
    The torrent client is the local peer that holds peer-to-peer
    connections to download and upload pieces of given torrent.
    
    Once started, the client makes periodic announcement calls to
    th tracker registered in torrent meta-info. These calls result
    in a list of peers which should tried in order to exchange
    pieces.

    Each received peer is kept in a queue that a pool of PeerConnection
    objects consume. There is a fix number of PeerConnections that can have
    a connection open to a peer. Since we are not creating expensive threads
    (or worse yet processes) we can create them all at once and they will
    be waiting until there is a peer to consume in the queue.
    """
    
    MAX_PEER_CONNECTIONS = 30
    def __init__(self, torrent, port=6889):
        self.tracker = Tracker(torrent, port)
        
        # list of potential peers in the work queue, 
        # consumed by the PeerConnections
        self.available_peers = asyncio.Queue()
        
        # list of workers that might be connected to a peer.
        # Or they're waiting to consume new remote peers from available peers queue 
        self.peers = []
        
        # manager which implemented the logic of requesting pieces
        # and persisting received pieces to disk 
        self.piece_manager = PieceManager(torrent)
        self.abort = False
    
    async def start(self):
        """
        Start downloading given torrent
        
        This results in connecting to tracker to fetch list of peers
        Aborted either once the file is fully downloaded or if download is aborted.  
        """
        
        self.peers = [PeerConnection(self.available_peers,
                                     self.tracker.torrent.info_hash,
                                     self.tracker.peer_id,
                                     self.piece_manager,
                                     self._on_block_retrieved) for _ in range(self.MAX_PEER_CONNECTIONS)]
        
        previous = None # last announce call timestamp
        interval = 30*60 # default interval b/w announce calls
        
        while True:
            if self.piece_manager.complete:
                logger.info("Torrent fully downloaded")
                break
            if self.abort:
                logger.info("Aborting download...")
                break
            
            current = time.time()
            if not previous or (previous+interval < current):
                response = await self.tracker.connect(
                    first = True if previous else False,
                    uploaded=self.piece_manager.bytes_uploaded,
                    downloaded=self.piece_manager.bytes_downloaded
                )
                if response:
                    previous = current
                    interval = response.interval
                    self._empty_queue()
                    for peer in response.peers:
                        self.available_peers.put_nowait(peer)
            else:
                await asyncio.sleep(5)
        self.stop()
    
    def _empty_queue(self):
        while not self.available_peers.empty():
            self.available_peers.get_nowait()
    
    def stop(self):
        """
        Stop the download or seeding process.
        """
        self.abort = True
        for peer in self.peers:
            peer.stop()
        self.piece_manager.close()
        self.tracker.close()
    
    def _on_block_retrieved(self, peer_id, piece_index, block_offset, data):
        """
        Callback function called by the `PeerConnection` when a block is
        retrieved from a peer.

        :param peer_id: The id of the peer the block was retrieved from
        :param piece_index: The piece index this block is a part of
        :param block_offset: The block offset within its piece
        :param data: The binary data retrieved
        """
        self.piece_manager.block_received(peer_id=peer_id,
                                          piece_index=piece_index,
                                          block_offset=block_offset,
                                          data=data)

