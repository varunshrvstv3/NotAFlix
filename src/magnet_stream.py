import logging
import os
import subprocess
import threading
import time
from collections import namedtuple
from typing import Optional

import libtorrent as lt

from constants import PYFLIX_CACHE_DIR
from src.stream_manager import StreamManager

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class MagnetStream:
    def __init__(self, magnet_link: str, torrent_url: str) -> None:
        self._filename: Optional[str] = None
        self._magnet_link = magnet_link
        self._torrent_url = torrent_url
        self._session: Optional[lt.session] = None
        self._torrent_handler: Optional[lt.torrent_handle] = None
        self._cache = {}
        self.event = threading.Event()
        self.completed = False
        self.player: Optional[subprocess.Popen] = None

    @property
    def torrent_handler(self):
        if self._torrent_handler is None:
            magnet_dict = lt.parse_magnet_uri_dict(self._magnet_link)
            os.makedirs(PYFLIX_CACHE_DIR, exist_ok=True)
            magnet_dict["save_path"] = PYFLIX_CACHE_DIR
            self._torrent_handler = lt.add_magnet_uri(
                self.session, self._torrent_url, magnet_dict
            )
            self._filename = os.path.join(
                self._torrent_handler.save_path(),
                self._torrent_handler.status().name
            )
        return self._torrent_handler

    @property
    def session(self):
        if self._session is None:
            self._session = lt.session()
            self.session.start_dht(None)
            self.session.add_dht_router("router.bittorrent.com", 6881)
            self.session.add_dht_router("router.utorrent.com", 6881)
            self.session.add_dht_router("router.bitcomet.com", 6881)
            self.session.listen_on(6881, 6891)
            self.session.set_alert_mask(
                lt.alert.category_t.storage_notification
            )
        return self._session

    @staticmethod
    def calculate_stream_offset(
        piece_length: int, file_entry: lt.file_entry
    ) -> namedtuple:
        """
        Calculates the stream offsets.

        Args:
            piece_length: number of byte for each piece
            file_entry: File entry for which the stream offset
                is to be calculated.
        Returns:
            Stream offsets
        """
        stream_offset = namedtuple(
            "StreamOffset",
            [
                "pieces_per_write",
                "piece_start",
                "piece_end",
                "offset1",
                "offset2",
            ],
        )
        stream_offset.pieces_per_write = 40 * 1024 * 1024 // piece_length
        stream_offset.piece_start = file_entry.offset // piece_length
        stream_offset.piece_end = (
            file_entry.offset + file_entry.size
        ) // piece_length
        stream_offset.offset1 = file_entry.offset % piece_length
        stream_offset.offset2 = (
            file_entry.offset + file_entry.size
        ) % piece_length
        return stream_offset

    def launch_player(self) -> None:
        """
        Launches media player. For now only vlc is supported.
        """
        if self.player is not None:
            return
        self.player = subprocess.Popen(
            (
                "vlc",
                "--verbose",
                "2",
                self._filename
            )
        )

    def start(self) -> None:
        """
        Starts the movie stream.
        """
        while not self.torrent_handler.has_metadata():
            time.sleep(10)
        torrent_info = self.torrent_handler.get_torrent_info()
        video_file = None
        for f in torrent_info.files():
            if video_file is None or f.size > video_file.size:
                video_file = f

        stream_offsets = self.calculate_stream_offset(
            torrent_info.piece_length(), video_file
        )
        self.session.set_alert_mask(lt.alert_category.storage)
        for i in range(torrent_info.num_pieces()):
            self.torrent_handler.piece_priority(i, 0)
        self.torrent_handler.set_sequential_download(True)
        barrier = threading.Barrier(
            stream_offsets.pieces_per_write, action=self.launch_player
        )
        try:
            threads = []
            for i in range(stream_offsets.pieces_per_write):
                threads.append(
                    StreamManager(
                        name=f"stream_manager_{i}",
                        end_piece=stream_offsets.piece_end,
                        start_piece=stream_offsets.piece_start+i,
                        piece_per_write=stream_offsets.pieces_per_write,
                        torrent_handler=self.torrent_handler,
                        barrier=barrier
                    )
                )
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        except Exception as err:
            logger.exception(err)
        finally:
            logger.info(
                f"Removing the file {self._filename}"
            )
            os.remove(
                os.path.join(
                    self.torrent_handler.save_path(),
                    self.torrent_handler.status().name,
                )
            )
            self.session.remove_torrent(self.torrent_handler)
