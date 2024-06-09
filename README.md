Simple BitTorrent client that allows you to download files using P2P BitTorrent protocol.
This was designed for learning purpose

Features:
- [x] Download pieces (leeching)
- [x] Contact tracker periodically
- [ ] Seed (upload) pieces
- [ ] Support multi-file torrents
- [ ] Resume a download

# Commands
- To download torrent
    ```python
    python src/cli.py -T "path/to/torrent" -l "path/to/logfile"
    ```
- To run tests
    ```python
    python -m unittest test/*.py
    ```
- To get all available options under cli
    ```python
    python src/cli.py --help
    ```

Reference:
- [Unofficial BitTorrent specification](https://wiki.theory.org/BitTorrentSpecification)