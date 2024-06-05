from hashlib import sha1

from src import bencoding
from src.const import TorrentFile

class Torrent:
    def __init__(self, filename):
        self.filename = filename
        self.files = []
        
        with open(self.filename, 'rb') as f:
            meta_info = f.read()
            self.meta_info = bencoding.Decoder(meta_info).decode()
            info = bencoding.Encoder(self.meta_info[b'info']).encode()
            self.info_hash = sha1(info).digest()
            self._identify_files()
        
    def _identify_files(self):
        if self.multi_file:
            raise NotImplemented("Multi-file torrent is not implemented")
        
        self.files.append(
            TorrentFile(
                self.meta_info[b'info'][b'name'].decode(),
                self.meta_info[b'info'][b'length']
            )
        )
    
    @property
    def announce(self) -> str:
        return self.meta_info[b'announce'].decode()
    
    @property
    def multi_file(self) -> bool:
        return b'files' in self.meta_info[b'info']
    
    @property
    def piece_length(self) -> int:
        return self.meta_info[b'info'][b'piece length']
    
    @property
    def total_size(self) -> int:
        if self.multi_file:
            raise NotImplemented("Multi-file torrent is not supported")
        return self.files[0].length
    
    @property
    def pieces(self):
        # The info pieces is a string representing all pieces SHA1 hashes
        # (each 20 bytes long). Read that data and slice it up into the
        # actual pieces
        data = self.meta_info[b'info'][b'pieces']
        pieces = []
        offset = 0
        length = len(data)
        
        while offset < length:
            pieces.append(data[offset:offset+20])
            offset += 20
        
        return pieces
    
    @property
    def output_file(self):
        return self.meta_info[b'info'][b'name'].decode()
    
    def __str__(self):
        return f"Filename: {self.meta_info[b'info'][b'name']} " \
               f"File length: {self.meta_info[b'info'][b'length']} " \
               f"Announce URL: {self.meta_info[b'announce']} " \
               f"Hash: {self.info_hash}"
        
        