import os
import logging
import math
from typing import List
from hashlib import sha1
import time
from collections import defaultdict

from src.const import REQUEST_SIZE, PendingRequest

logger = logging.getLogger(__name__)

class Block:
    """
    The block is a partial piece, this is what is requested and transferred
    between peers.

    A block is most often of the same size as the REQUEST_SIZE, except for the
    final block which might (most likely) is smaller than REQUEST_SIZE.
    """
    Missing = 0
    Pending = 1
    Retrieved = 2
    
    def __init__(self, piece: int, offset: int, length: int):
        self.piece = piece
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.data = None

class Piece:
    """
    The piece is a part of of the torrents content. Each piece except the final
    piece for a torrent has the same length (the final piece might be shorter).
    """
    
    def __init__(self, index: int, blocks: List, hash_value):
        self.index = index
        self.blocks = blocks
        self.hash = hash_value
        
    def reset(self):
        """
        Reset all blocks to Missing regardless of current state.
        """
        for block in self.blocks:
            block.status = Block.Missing
    
    def next_request(self) -> Block:
        """
        Get the next Block to be requested
        """
        missing = [block for block in self.blocks if block.status is Block.Missing]
        if missing:
            missing[0].status = Block.Pending
            return missing[0]
        return None
    
    def block_received(self, offset: int, data: bytes):
        """
        Update block information that the given block is now received

        :param offset: The block offset (within the piece)
        :param data: The block data
        """
        matches = [block for block in self.blocks if block.offset == offset]
        block = matches[0] if matches else None
        if block:
            block.status = Block.Retrieved
            block.data = data
        else:
            logger.warning(f'Trying to complete a non-existing block {offset}')
    
    def is_complete(self) -> bool:
        """
        Checks if all blocks for this piece is retrieved (regardless of SHA1)

        :return: True or False
        """
        blocks = [b for b in self.blocks if b.status is not Block.Retrieved]
        return len(blocks) == 0
    
    def is_hash_matching(self):
        """
        Check if a SHA1 hash for all the received blocks match the piece hash
        from the torrent meta-info.

        :return: True or False
        """
        piece_hash = sha1(self.data).digest()
        return self.hash == piece_hash

    @property
    def data(self):
        """
        Return the data for this piece (by concatenating all blocks in order)

        NOTE: This method does not control that all blocks are valid or even
        existing!
        """
        retrieved = sorted(self.blocks, key=lambda b: b.offset)
        blocks_data = [b.data for b in retrieved]
        return b''.join(blocks_data)
    

class PieceManager:
    """
    The PieceManager is responsible for keeping track of all the available
    pieces for the connected peers as well as the pieces we have available for
    other peers.

    The strategy on which piece to request is made as simple as possible in
    this implementation.
    """
    def __init__(self, torrent):
        self.torrent = torrent
        self.peers = {}
        self.pending_blocks = []
        self.missing_pieces = []
        self.ongoing_pieces = []
        self.have_pieces = []
        self.max_pending_time = 300 * 1000  # 5 minutes
        self.missing_pieces = self._initiate_pieces()
        self.total_pieces = len(torrent.pieces)
        self.fd = os.open(self.torrent.output_file,  os.O_RDWR | os.O_CREAT)
    
    def _initiate_pieces(self) -> List[Piece]:
        """
        Pre-construct the list of pieces and blocks based on the number of
        pieces and request size for this torrent.
        """
        torrent = self.torrent
        pieces = []
        total_pieces = len(torrent.pieces)
        std_piece_blocks = math.ceil(torrent.piece_length / REQUEST_SIZE)
        
        for index, hash_value in enumerate(torrent.pieces):
            # number of blocks for each piece can be calculated using
            # request size as divisor on piece length
            # final piece however can have fewer blocks since final block can
            # be smaller than rest
            if index < total_pieces-1:
                blocks = [Block(index, offset*REQUEST_SIZE, REQUEST_SIZE)
                         for offset in range(std_piece_blocks)]
            else:
                # Last block
                last_length = torrent.total_size % torrent.piece_length
                num_blocks = math.ceil(last_length / REQUEST_SIZE)
                blocks = [Block(index, offset*REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(num_blocks)]
                
                if last_length%REQUEST_SIZE > 0:
                    # last block of last piece is smaller then rest
                    last_block = blocks[-1]
                    last_block.length = last_length%REQUEST_SIZE
                    blocks[-1] = last_block
            
            pieces.append(Piece(index, blocks, hash_value))
        return pieces
    
    def close(self):
        if self.fd:
            os.close(self.fd)
    
    @property
    def complete(self):
        """
        Checks whether or not the all pieces are downloaded for this torrent.

        :return: True if all pieces are fully downloaded else False
        """
        return len(self.have_pieces) == self.total_pieces
    
    @property
    def bytes_downloaded(self) -> int:
        """
        Get the number of bytes downloaded.

        This method Only counts full, verified, pieces, not single blocks.
        """
        return len(self.have_pieces) * self.torrent.piece_length

    @property
    def bytes_uploaded(self) -> int:
        # TODO Add support for sending data
        return 0

    def add_peer(self, peer_id, bitfield):
        """
        Adds a peer and the bitfield representing the pieces the peer has.
        """
        self.peers[peer_id] = bitfield
    
    def update_peer(self, peer_id, index: int):
        """
        Updates the information about which pieces a peer has (reflects a Have
        message).
        """
        if peer_id in self.peers:
            self.peers[peer_id][index] = 1

    def remove_peer(self, peer_id):
        """
        Tries to remove a previously added peer (e.g. used if a peer connection
        is dropped)
        """
        if peer_id in self.peers:
            del self.peers[peer_id]
    
    def next_request(self, peer_id) -> Block:
        """
        Get the next Block that should be requested from the given peer.

        If there are no more blocks left to retrieve or if this peer does not
        have any of the missing pieces None is returned
        """
        if peer_id not in self.peers:
            return
        
        block = self._expired_requests(peer_id)
        if not block:
            block = self._next_ongoing(peer_id)
            if not block:
                block = self._next_missing(peer_id) # TODO update with rarest missing algor
        return block
    
    def _expired_requests(self, peer_id) -> Block:
        """
        Go through previously requested blocks, if any one have been in the
        requested state for longer than `MAX_PENDING_TIME` return the block to
        be re-requested.

        If no pending blocks exist, None is returned
        """
        current = int(round(time.time()*1000))
        for request in self.pending_blocks:
            if self.peers[peer_id][request.block.piece]:
                if request.added + self.max_pending_time < current:
                    logger.info(f'Re-requesting block {request.block.offset} for piece {request.block.piece}')
                    # Update added timer
                    request.added = current
                    return request.block
        return None
    
    def _next_ongoing(self, peer_id) -> Block:
        """
        Go through the ongoing pieces and return the next block to be
        requested or None if no block is left to be requested.
        """
        for piece in self.ongoing_pieces:
            if self.peers[peer_id][piece.index]:
                block = piece.next_request()
                if block:
                    self.pending_blocks.append(
                        PendingRequest(block, int(round(time.time()*1000)))
                    )
                    return block
        return None
    
    def _next_missing(self, peer_id) -> Block:
        """
        Go through the missing pieces and return the next block to request
        or None if no block is left to be requested.

        This will change the state of the piece from missing to ongoing - thus
        the next call to this function will not continue with the blocks for
        that piece, rather get the next missing piece.
        """
        for index, piece in enumerate(self.missing_pieces):
            if self.peers[peer_id][piece.index]:
                # Move this piece from missing to ongoing
                piece = self.missing_pieces.pop(index)
                self.ongoing_pieces.append(piece)
                # The missing pieces does not have any previously requested
                # blocks (then it is ongoing).
                return piece.next_request()
        return None
    
    def _get_rarest_piece(self, peer_id):
        """
        Given the current list of missing pieces, get the
        rarest one first (i.e. a piece which fewest of its
        neighboring peers have)
        """
        # TODO: improve algorithm
        piece_count = defaultdict(int)
        for piece in self.missing_pieces:
            if not self.peers[peer_id][piece.index]:
                continue
            for pid in self.peers:
                if self.peers[pid][piece.index]:
                    piece_count[piece] += 1
        
        rarest_piece = min(piece_count, key=lambda p: piece_count[p])
        self.missing_pieces.remove(rarest_piece)
        self.ongoing_pieces.append(rarest_piece)
        return rarest_piece
    
    def block_received(self, peer_id, piece_index, block_offset, data):
        """
        This method must be called when a block has successfully been retrieved
        by a peer.

        Once a full piece have been retrieved, a SHA1 hash control is made. If
        the check fails all the pieces blocks are put back in missing state to
        be fetched again. If the hash succeeds the partial piece is written to
        disk and the piece is indicated as Have.
        """
        logger.debug(f'Received block {block_offset} for piece {piece_index} from peer {peer_id}')
        
        # Remove block from pending requests
        for index, request in enumerate(self.pending_blocks):
            if request.block.piece == piece_index and request.block.offset == block_offset:
                del self.pending_blocks[index]
                break
        
        pieces = [p for p in self.ongoing_pieces if p.index == piece_index]
        if pieces:
            piece = pieces[0]
            piece.block_received(block_offset, data)
            if piece.is_complete():
                if piece.is_hash_matching():
                    self._write(piece)
                    self.ongoing_pieces.remove(piece)
                    self.have_pieces.append(piece)
                    complete = self.total_pieces - len(self.missing_pieces) - len(self.ongoing_pieces)
                    logger.info(f'{complete}/{self.total_pieces} pieces downloaded {100*complete/self.total_pieces:.3f} %')
                else:
                    logger.info(f'Discarding corrupt piece {piece.index}')
                    piece.reset()
        else:
            logger.warning('Trying to update piece that is not ongoing!')
    
    def _write(self, piece):
        """
        Write the given piece to disk
        """
        pos = piece.index * self.torrent.piece_length
        os.lseek(self.fd, pos, os.SEEK_SET)
        os.write(self.fd, piece.data)
            