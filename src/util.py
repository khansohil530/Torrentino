import random
from struct import unpack

CLIENT_ID = "PC"
VERSION_NO = "0001"

def _calculate_peer_id():
    """
    Calculate and return a unique Peer ID.

    The `peer id` is a 20 byte long identifier. This implementation use the
    Azureus style `-PC1000-<random-characters>`.

    Read more:
        https://wiki.theory.org/BitTorrentSpecification#peer_id
    """
    return f"-{CLIENT_ID}{VERSION_NO}-{''.join([str(random.randint(0,9)) for _ in range(12)])}"

def _decode_port(port):
    """
    Converts a 32-bit packed binary port number to int
    """
    # Convert from C style big-endian encoded as unsigned short
    return unpack(">H", port)[0]