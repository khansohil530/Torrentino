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