import asyncio
import logging
import struct
from concurrent.futures import CancelledError


from src import msglib
from src.exc import ProtocolError

logger = logging.getLogger(__name__)

class PeerConnection:
    """
    A peer connection used to download and upload pieces.

    The peer connection will consume one available peer from the given queue.
    Based on the peer details the PeerConnection will try to open a connection
    and perform a BitTorrent handshake.

    After a successful handshake, the PeerConnection will be in a *choked*
    state, not allowed to request any data from the remote peer. After sending
    an interested message the PeerConnection will be waiting to get *unchoked*.

    Once the remote peer unchoked us, we can start requesting pieces.
    The PeerConnection will continue to request pieces for as long as there are
    pieces left to request, or until the remote peer disconnects.

    If the connection with a remote peer drops, the PeerConnection will consume
    the next available peer from off the queue and try to connect to that one
    instead.
    """
    def __init__(self, queue: asyncio.queues.Queue, info_hash, peer_id, 
                 piece_manager, on_block_cb=None):
        """
        Construct a PeerConnection and add it to asyncio event loop
        
        Use `stop` to abort this connection and any subsequent connection attempts
        
        :param queue: The async Queue containing available peers
        :param info_hash: The SHA1 hash for the meta-info
        :param peer_id: Client Peer Id to identify itself
        :param piece_manager: Manager for requesting pieces
        :param on_block_cb: callback function when a block is received from remote peer.
        """
        self.my_state = []
        self.peer_state = []
        self.queue = queue
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.remote_id = None
        self.writer = None
        self.reader = None
        self.piece_manager = piece_manager
        self.on_block_cb = on_block_cb
        self.future = asyncio.ensure_future(self._start())
        
    async def _start(self):
        while 'stopped' not in self.my_state:
            ip, port = await self.queue.get()
            logger.info(f'Got assigned peer with {ip}')
            try:
                self.reader, self.writer = await asyncio.open_connection(ip, port)
                logger.info('Connection open to peer: {ip}')
                
                buffer = await self._handshake() # initiate handshake
                
                # TODO: add support for sending data
                # Sending BitField is optional and not needed when client does
                # not have any pieces. Thus we do not send any bitfield message
                
                # The default state for a connection is that peer is not
                # interested and we are choked
                self.my_state.append('choked')
                
                # Let the peer know we're interested in downloading pieces
                await self._send_interested()
                self.my_state.append('interested')
                
                # Start reading responses as a stream of messages for as
                # long as the connection is open and data is transmitted
                async for message in PeerStreamIterator(self.reader, buffer):
                    if 'stopped' in self.my_state:
                        break
                    msg_type = type(message)
                    if msg_type is msglib.BitField:
                        self.piece_manager.add_peer(self.remote_id, message.bitfield)
                    elif msg_type is msglib.Interested:
                        self.peer_state.append('interested')
                    elif msg_type is msglib.NotInterested:
                        if 'interested' in self.peer_state:
                            self.peer_state.remove('interested')
                    elif msg_type is msglib.Choke:
                        self.my_state.append('choked')
                    elif msg_type is msglib.Unchoke:
                        if 'choked' in self.my_state:
                            self.my_state.remove('choked')
                    elif msg_type is msglib.Have:
                        self.piece_manager.update_peer(self.remote_id, message.index)
                    elif msg_type is msglib.KeepAlive:
                        pass # TODO send KeepAlive message if no message is sent for 2 mins
                    elif msg_type is msglib.Piece:
                        self.my_state.remove('pending_request')
                        self.on_block_cb(
                            peer_id=self.remote_id,
                            piece_index=message.index,
                            block_offset=message.begin,
                            data=message.block
                        )
                    elif msg_type is msglib.Request:
                        # TODO: add support for sending data
                        logger.info('Ignoring Request message')
                    elif msg_type is msglib.Cancel:
                        # TODO
                        logger.info('Ignoring Cancel message')
                    
                    if 'choked' not in self.my_state and \
                       'interested' in self.my_state and \
                       'pending_request' not in self.my_state:
                        self.my_state.append('pending_request')
                        await self._request_piece()
            except ProtocolError as e:
                logging.exception('Protocol error')
            except (ConnectionRefusedError, TimeoutError):
                logging.warning('Unable to connect to peer')
            except (ConnectionResetError, CancelledError):
                logging.warning('Connection closed')
            except Exception as e:
                logging.exception('An error occurred')
                self.cancel()
                raise e
            self.cancel()

    def cancel(self):
        """
        Sends the cancel message to the remote peer and closes the connection.
        """
        logger.info(f'Closing peer {self.remote_id}')
        if not self.future.done():
            self.future.cancel()
        if self.writer:
            self.writer.close()

        self.queue.task_done()

    def stop(self):
        """
        Stop this connection from the current peer (if a connection exist) and
        from connecting to any new peer.
        """
        # Set state to stopped and cancel our future to break out of the loop.
        # The rest of the cleanup will eventually be managed by loop calling
        # `cancel`.
        self.my_state.append('stopped')
        if not self.future.done():
            self.future.cancel()
    
    async def _request_piece(self):
        block = self.piece_manager.next_request(self.remote_id)
        if block:
            message = msglib.Request(block.piece, block.offset, block.length).encode()
            logging.debug(f'Requesting block {block.piece} for piece {block.offset}'\
                          f'of {block.length} bytes from peer {self.remote_id}')
            
            self.writer.write(message)
            await self.writer.drain()
    
    async def _handshake(self):
        """
        Send the initial handshake to the remote peer and wait for the peer
        to respond with its handshake.
        """
        self.writer.write(msglib.Handshake(self.info_hash, self.peer_id).encode())
        await self.writer.drain()
        
        buf = b''
        tries = 1
        while len(buf) < msglib.Handshake.LENGTH and tries < 10:
            buf = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)
        
        response = msglib.Handshake.decode(buf[:msglib.Handshake.LENGTH])
        if not response:
            raise ProtocolError('Unable to receive and parse a handshake')
        if not response.info_hash == self.info_hash:
            raise ProtocolError('Handshake with invalid info_hash')
        
        
        # TODO: Validate remote peer_id with the peer_id received from tracker
        self.remote_id = response.peer_id
        logger.info('Handshake with peer was successful')
        
        # Return remaining buffer data, which might be from next message
        return buf[msglib.Handshake.LENGTH:]
    
    async def _send_interested(self):
        message = msglib.Interested()
        logger.debug(f'Sending message: {message}')
        self.writer.write(message.encode())
        await self.writer.drain()


class PeerStreamIterator:
    """
    The `PeerStreamIterator` is an async iterator that continuously reads from
    the given stream reader and tries to parse valid BitTorrent messages from
    off that stream of bytes.

    If the connection is dropped, something fails the iterator will abort by
    raising the `StopAsyncIteration` error ending the calling iteration.
    """
    CHUNK_SIZE = 10*1024
    
    def __init__(self, reader, initial: bytes=None):
        self.reader = reader
        self.buffer = initial if initial else b''
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        """
        Read data from socket until we've enough data to parse
        Return parsed data
        """
        while True:
            try:
                data = await self.reader.read(PeerStreamIterator.CHUNK_SIZE)
                if data:
                    self.buffer += data
                    message = self.parse()
                    if message:
                        return message
                else:
                    logger.debug('No data read from stream')
                    if self.buffer:
                        message = self.parse
                        if message:
                            return message
                    raise StopAsyncIteration()
            except ConnectionResetError:
                logger.debuf('Connection closed by peer')
                raise StopAsyncIteration()
            except CancelledError:
                raise StopAsyncIteration()
            except StopAsyncIteration as e:
                raise e
            except Exception:
                logger.exception('Error when iterating over stream!')
                raise StopAsyncIteration()
        raise StopAsyncIteration()
    
    def parse(self):
        """
        Tries to parse protocol messages if there is enough bytes read in the
        buffer.

        :return The parsed message, or None if no message could be parsed
        """
        header_length = 4
        if len(self.buffer) >= header_length:
            message_length = struct.unpack(">I", self.buffer[0:4])[0]
            if message_length == 0:
                return msglib.KeepAlive()
            
            if len(self.buffer) >= message_length:
                message_id = struct.unpack('>b', self.buffer[4:5])[0]
                
                def _consume():
                    self.buffer = self.buffer[header_length+message_length:]
                
                def _data():
                    return self.buffer[:header_length+message_length]
                
                if message_id is msglib.PeerMessage.BitField:
                    data = _data()
                    _consume()
                    return msglib.BitField.decode(data)
                elif message_id is msglib.PeerMessage.Interested:
                    _consume()
                    return msglib.Interested()
                elif message_id is msglib.PeerMessage.NotInterested:
                    _consume()
                    return msglib.NotInterested()
                elif message_id is msglib.PeerMessage.Choke:
                    _consume()
                    return msglib.Choke()
                elif message_id is msglib.PeerMessage.Unchoke:
                    _consume()
                    return msglib.Unchoke()
                elif message_id is msglib.PeerMessage.Have:
                    data = _data()
                    return msglib.Have.decode(data)
                elif message_id is msglib.PeerMessage.Piece:
                    data = _data()
                    _consume()
                    return msglib.Piece.decode(data)
                elif message_id is msglib.PeerMessage.Request:
                    data = _data()
                    _consume()
                    return msglib.Request.decode(data)
                elif message_id is msglib.PeerMessage.Cancel:
                    data = _data()
                    _consume()
                    return msglib.Cancel.decode(data)
                else:
                    logger.warning('Unsupported message!')
            else:
                logger.debug('Not enough in buffer to parse')
        return None
                
                
                
                