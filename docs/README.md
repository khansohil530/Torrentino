# BitTorrent Client written in Python

Purpose of this project is to learn about peer-to-peer protocol

BitTorrent is one implementation of this protocol.

This protocol is used for solutions which requires distribution of large files
- Facebook uses it to distribute update within their data centers
- AWS S3 uses it to download static fields

This protocol uses a group of peers (`swarm`) to exchange pieces of information b/w each other. With this setup
- you can download/upload pieces of files from different peers thus enabling greater bandwidth of exchange compared to solutions which uses a centeral server.
- also increases the availability

All the information like how many pieces there is for a given file, how these should be exchanged b/w peers and data integrity of these pieces are regulated using `.torrent` files

> Complete spec. can be explored [here](https://wiki.theory.org/BitTorrentSpecification)

## Parsing `.torrent` file
All information required by client to download the resource are maintained in this file, also known as `meta-info`.
Few properties required are:
- name of file to download
- size of file
- URL to `tracker` to connect to

All these properties are stored in a binary format called `Bencoding`.

### Data types
`Bencoding` supports 4 different data types mentioned below along with their
encoding format
- `strings`: `<string length encoded in base ten ASCII>:<string data>`
- `integers`: `i<integer encoded in base ten ASCII>e`, with start denoted by `i` and ending by `e`.
- `lists`: `l<bencoded values>e`, with start denoted by `l` and ending by `e`
- `dictionaries`: `d<bencoded string><bencoded element>e`, with start denoted by `d` and ending by `e`

### Meta info
Meta info contains following keys. 
> All string key/value are encoded in utf-8

<b>Required fields</b>

- `info`(`dict`): Contains info common for both single and multiple file mode
    - `piece length` (`integer`): number of bytes in each piece
    - `pieces` (`string`): concat. of all 20bytes SHA1 hash, one per piece
    - `private` (`integer`): optional field, can be set to `1` or `0`. If on, only tracker present in meta info can access.

    Aditionally in case of `single-file` mode

    - `name`: `string`, filename
    - `length`: `integer`, length of file in bytes
    - `md5sum`: `string`, optional 32-char. hexadecimal string MD5 sum of file.

    In case of `multiple-file` mode
    - `name`: `string`, name of directory to store all files
    - `files`: `list` of `dict`, for each file 
        - `length`: `integer`, length of file in bytes
        - `md5sum`: optional
        - `path`: `list` of `string`, combined forms path and filename. 

- `announce` (`string`): URL of tracker

<b> Optional fields </b>

- [`announce-list`](https://bittorrent.org/beps/bep_0012.html)(`list of string`): contains list of tiers of announces. Used by `multitracker` clients with higher priority then `announce` key. 
- `creation date`(`integer`): creation time of torrent in standard UNIX epoch format
- `comment`(`string`): Free form comment by author 
- `created by` (`string`): name and version of program used to create the file
- `encoding` (`string`): encoding used to generate `pieces` part of `info` key

## Demo

You can check the implementation of parsing torrent using bencode format [here](../src/bencoding.py)

To parse a torrent file, we'll be using `.torrent` file of [`ubuntu distribution`](../test/data/ubuntu-24.04.1-desktop-amd64.iso.torrent)


```python
from src.bencoding import Decoder

with open('test/data/ubuntu-24.04.1-desktop-amd64.iso.torrent', 'rb') as fp:
    meta_info = fp.read()
    torrent = Decoder(meta_info).decode()

print(torrent)
OrderedDict([
    (b'announce', b'http://torrent.ubuntu.com:6969/announce'), (b'announce-list', [
        [b'http://torrent.ubuntu.com:6969/announce'],
        [b'http://ipv6.torrent.ubuntu.com:6969/announce']
        ]),
    (b'comment', b'Ubuntu CD releases.ubuntu.com'),
    (b'creation date', 1461232732),
    (b'info', OrderedDict([
        (b'length', 1485881344),
        (b'name', b'ubuntu-16.04-desktop-amd64.iso'),
        (b'piece length', 524288),
        (b'pieces', b'\x1at\xfc\x84\xc8\xfaV\xeb\x12\x1c\xc5\xa4\x1c?\...')
        ]))
    ])
```

Notice how the keys of parsed torrent file are `bytes string`. This is because `bencode` is a binary protocol, and using `utf-8` strings as key will not work.
To handle this conversion b/w torrent file and python, you can implement a wrapper abstracting away details from python client.

# Connecting to tracker
- `Tracker` is an HTTP(s) server which responds to `GET` calls to provide peer list so that client can participate in the torrent.
- The `GET` request is only built using request `URL`, in which the base url is `announce URL` specified in meta info, followed by following url encoded query params:
    - `info_hash`: 20-byte SHA1 hash of `info` field in `meta-info`. `info` should be `bencoded`prior to hashing.
    - `peer_id`: 20-byte string used as unique id for client. There are mainly two conventions:
        1. `Azureus style`: "-" + <2-character client id> + <4 character version id> + "-" + 12 random characters
        2. `Shadow's style`: 
    - `port`: port number client is listening on, reserverd ports for BitTorrent are typically 6881-6889
    - `uploaded`: total number of bytes uploaded
    - `downloaded`: total number of bytes downloaded
    - `left`: number of bytes left to download all files in torrent
    - `compact`: can be set to `1` or `0`
        - `1`: client accepts compact response, peers list replaced by 6 bytes peer strings. first 4 bytes are host and last two bytes are port. Both in network byte order
    - `no_peer_id`: indicates tracker can omit peer id field in peer dictionary, ignored if compact is enabled 
    - `event`: can have following values
        - `started`: first request to tracker must include this event 
        - `stopped`: must be sent to tracker if client is shutting down gracefully.
        - `completed`: must be sent when an ongoing download gets completed.
    - `ip`: optional, true ip address of client machine, generally required when client is communicating through proxy
    - `numwant`: optional, number of peers to be received from tracker. default is 50
    - `key`: optional, additional identification which is not shared with any other peer. Helps prove client identify should its ip change.
    - `trackerid`: optional, if previous announce had `trackerid`, it should be set here.

- <b>`Tracker Response`</b>: response from above request in `"text/plain"` document consisting of bencoded dictionary with following keys.
    - `failure reason`: if present the request has failure, this key gives the human readable reason why the request failed.
    - `warning message`: <b>optional</b>, similar to failure but request gets processed.
    - `interval`: time interval in seconds that client should wait before sending request to tracker again.
    - `min interval`: <b>optional</b>, minimum announce interval, present client must not reannounce before this interval.
    - `tracker id`: string that client sents back on next announcement
    - `complete`: number of peers with entire file, i.e. seeders
    - `incomplete`: number of non-seeder peers, i.e. leechers
    - `peers`: dict model, contains list of dict with following key-value:
        - peer id: peer's self-selected ID
        - ip: peer's ip address (IPv6/IPv4/DNS name)
        - port: peer's port number
    - `peers`: binary model, consists of 6 bytes multiple, first 4 bytes for IP address, last 2 bytes for port, all in network (big endian) notation.

> Default peer list is of length 50, but if there are fewer peers, it'll be smaller. 

> Normally peers are selected randomly but the tracker may also choose to implement different algorithm for selecting peer.

> It is considered bad pratice to send announce request to tracker more frequently then specified interval. This if often done to get more peers. 

>However on implementation, 30 peers are plenty. When new piece is downloaded, HAVE messages will need to be sent to most active peers. This results in increase in broadcast traffic which is directly propotional to number of peers.   
