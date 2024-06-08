import struct
import logging


logger = logging.getLogger(__name__)


class PeerMessage:
    """
    A message between two peers.
    
    All of the remaining messages in the protocol take the form of:
        <length prefix><message ID><payload>
        
    - The length of prefix is a four byte big-endian value
    - The message ID is a single decimal byte
    - The payload is message dependent
    
    NOTE: The Handshake messageis different in layout compared to the other
          messages.

    Read more:
        https://wiki.theory.org/BitTorrentSpecification#Messages

    BitTorrent uses Big-Endian (Network Byte Order) for all messages, this is
    declared as the first character being '>' in all pack / unpack calls to the
    Python's `struct` module.
    """
    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    Handshake = None  # Handshake is not really part of the messages
    KeepAlive = None  # Keep-alive has no ID according to spec
    
    def encode(self) -> bytes:
        """
        Encodes this object instance to the raw bytes representing the entire
        message (ready to be transmitted).
        """
        raise NotImplementedError

    @classmethod
    def decode(cls, data: bytes):
        """
        Decodes the given BitTorrent message into a instance for the
        implementing type.
        """
        raise NotImplementedError

class Handshake(PeerMessage):
    """
    The handshake message is the first message sent and then received from a
    remote peer.

    The messages is always 68 bytes long (for this version of BitTorrent
    protocol).

    Message format:
        <pstrlen><pstr><reserved><info_hash><peer_id>

    In version 1.0 of the BitTorrent protocol:
        pstrlen = 19
        pstr = "BitTorrent protocol".

    Thus length is:
        49 + len(pstr) = 68 bytes long.
    """
    
    LENGTH = 49 + 19
    FORMAT_STRING = '>B19s8x20s20s'
    
    def __init__(self, info_hash: bytes, peer_id: bytes):
        """
        Construct the handshake message

        :param info_hash: The SHA1 hash for the info dict
        :param peer_id: The unique peer id
        """
        if isinstance(info_hash, str):
            info_hash = info_hash.encode()
        if isinstance(peer_id, str):
            peer_id = peer_id.encode()
        
        self.info_hash = info_hash
        self.peer_id = peer_id
        
    def encode(self) -> bytes:
        return struct.pack(
            self.FORMAT_STRING,            
            19,                         # Single byte (B)
            b'BitTorrent protocol',     # String 19s
                                        # Reserved 8x (pad byte, no value)
            self.info_hash,             # String 20s
            self.peer_id)               # String 20s
        
    @classmethod
    def decode(cls, data: bytes):
        """
        Decodes the given BitTorrent message into a handshake message,
        if not valid, None is returned
        """
        logger.debug(f'Decoding Handshake of length {len(data)}')
        if len(data) < cls.LENGTH:
            return None
        parts = struct.unpack(cls.FORMAT_STRING, data)
        return cls(info_hash=parts[2], peer_id=parts[3])
    
    def __str__(self):
        return 'Handshake'

