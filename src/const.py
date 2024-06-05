from collections import namedtuple

# As per BitTorent spec. for encoding info.
TOKEN_INTEGER = b'i'
TOKEN_LIST = b'l'
TOKEN_DICT = b'd'
TOKEN_END = b'e'
TOKEN_STRING_SEPERATOR = b':'

TorrentFile = namedtuple('TorrentFile', ['name', 'length'])