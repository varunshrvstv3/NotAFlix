import logging
import os
import subprocess
import sys
import threading
import time
from collections import namedtuple
from typing import Optional

import libtorrent as lt
import vlc

from constants import PYFLIX_CACHE_DIR

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class MagnetStream:
    def __init__(self, magnet_link: str, torrent_url: str) -> None:
        self._magnet_link = magnet_link
        self._torrent_url = torrent_url
        self._session: Optional[lt.session] = None
        self._torrent_handler: Optional[lt.torrent_handle] = None
        self._cache = {}
        self.event = threading.Event()
        self.completed = False

    @property
    def torrent_handler(self):
        if self._torrent_handler is None:
            magnet_dict = lt.parse_magnet_uri_dict(self._magnet_link)
            os.makedirs(PYFLIX_CACHE_DIR, exist_ok=True)
            magnet_dict["save_path"] = PYFLIX_CACHE_DIR
            self._torrent_handler = lt.add_magnet_uri(
                self.session, self._torrent_url, magnet_dict
            )
        return self._torrent_handler

    @property
    def session(self):
        if self._session is None:
            self._session = lt.session()
            state = None
            # state = lt.bdecode(open(state_file, "rb").read())
            self.session.start_dht(state)
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

    def start(self):
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
        downloading = 0
        for i in range(
            stream_offsets.piece_start,
            stream_offsets.piece_start + stream_offsets.pieces_per_write,
        ):
            if i <= stream_offsets.piece_end:
                self.torrent_handler.piece_priority(i, 7)
                downloading += 1
        self.torrent_handler.set_sequential_download(True)
        player = None
        try:
            for p in range(
                stream_offsets.piece_start, stream_offsets.piece_end + 1
            ):
                while True:
                    status = self.torrent_handler.status()
                    prio = self.torrent_handler.piece_priorities()
                    logger.info(
                        f"{p} {status.pieces[p]} {prio[p]} {downloading} {stream_offsets.pieces_per_write}"
                    )
                    if (
                        prio[p] == 0
                        and downloading < stream_offsets.pieces_per_write
                    ):
                        self.torrent_handler.piece_priority(p, 1)
                        downloading += 1
                    if status.pieces[p] and downloading > 0:
                        downloading -= 1
                        logger.info(f"{p} Downloaded {downloading}")
                        break
                    logger.info(
                        f"Download of {p} didn't complete. Sleeping for 5 seconds"
                    )
                    time.sleep(5)
                if player is None:
                    player = subprocess.Popen(
                        (
                            "vlc",
                            "--verbose",
                            "2",
                            os.path.join(
                                self.torrent_handler.save_path(), status.name
                            ),
                        )
                    )
        except Exception as err:
            logger.exception(err)
        finally:
            logger.info(
                f"Removing the file {os.path.join(self.torrent_handler.save_path(), self.torrent_handler.status().name)}"
            )
            os.remove(
                os.path.join(
                    self.torrent_handler.save_path(),
                    self.torrent_handler.status().name,
                )
            )
            self.session.remove_torrent(self.torrent_handler)

    def add_new_pieces(self, stream_offset):
        while not self.event.is_set() and not self.completed:
            logger.info(
                f"{threading.current_thread().name} started adding new pieces"
            )
            prio = self.torrent_handler.piece_priorities()
            s = self.torrent_handler.status()
            downloading = 0
            if len(s.pieces) == 0:
                return
            for piece in range(
                stream_offset.piece_start, stream_offset.piece_end + 1
            ):
                if prio[piece] != 0 and not s.pieces[piece]:
                    self.event.set()
                    downloading = downloading + 1
            for piece in range(
                stream_offset.piece_start, stream_offset.piece_end + 1
            ):
                if (
                    prio[piece] == 0
                    and downloading < stream_offset.pieces_per_write
                ):
                    self.event.set()
                    self.torrent_handler.piece_priority(piece, 1)
                    downloading = downloading + 1
            for piece in range(
                stream_offset.piece_start, stream_offset.piece_end + 1
            ):
                if prio[piece] != 0 and not s.pieces[piece]:
                    self.event.set()
                    break
            logger.info(f"{threading.current_thread().name} going to sleep")
            while self.event.is_set():
                time.sleep(1)

    def get_piece(self, piece):
        if piece in self._cache:
            ret = self._cache[piece]
            self._cache[piece] = 0
            return ret
        while True:
            while not self.event.is_set():
                time.sleep(1)
            logger.info(
                f"{threading.current_thread().name} checking the status"
            )
            status = self.torrent_handler.status()
            if not status.pieces:
                break
            if status.pieces[piece]:
                break
            logger.info(
                f"{threading.current_thread().name} didn't find the status"
            )
            time.sleep(0.1)
            self.event.clear()
        self.torrent_handler.read_piece(piece)
        while True:
            popped_pieces = self.session.pop_alerts()
            for p in popped_pieces:
                if isinstance(p, lt.read_piece_alert):
                    if p.piece == piece:
                        self.event.clear()
                        return p.buffer
                    else:
                        self._cache[p.piece] = p.buffer
                    break
            time.sleep(0.1)
            self.event.clear()

    def write_thread(self, stream_offset: namedtuple):
        # global completed, played, subprocess, kill
        stream = None
        conn = 0
        for piece in range(
            stream_offset.piece_start, stream_offset.piece_end + 1
        ):
            logger.info(f"Getting peice {piece}")
            buf = self.get_piece(piece)
            played = piece - stream_offset.piece_start
            if stream is None:
                process = subprocess.Popen(
                    ["vlc -"], shell=True, stdin=subprocess.PIPE
                )
                stream = process.stdin
            if piece == stream_offset.piece_start:
                buf = buf[stream_offset.offset1 :]
            if piece == stream_offset.piece_end:
                buf = buf[: stream_offset.offset2]
            # if outputcmd == '-':
            #     stream = sys.stdout
            # elif outputcmd == 'http':
            #     if conn == 0:
            #         HOST = '127.0.0.1'  # Symbolic name meaning all available interfaces
            #         PORT = 50008  # Arbitrary non-privileged port
            #         s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #         s.bind((HOST, PORT))
            #         s.listen(1)
            #         # print "mplayer http://127.0.0.1:"+str(PORT)
            #         # os.system("mplayer http://127.0.0.1:"+str(PORT))
            #         # os.spawnl(os.P_NOWAIT, "mplayer http://127.0.0.1:"+str(PORT))
            #         thread.start_new_thread(runmplayer, ())
            #         conn, addr = s.accept()
            #         print
            #         'Connected by', addr
            #         data = conn.recv(1024)
            #         print
            #         data
            #         # thread.start_new_thread(read2,(s,))
            #         # conn.send('HTTP/1.1 206 Partial Content\r\nContent-Type: video/mp4\r\n\r\n')
            #         conn.send('HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\n\r\n')
            #         # conn.send('HTTP/1.1 200 OK\r\nContent-Type: video/x-msvideo\r\n\r\n')
            #         # conn.send('HTTP/1.1 206 Partial Content\r\nDate: Sun, 18 Sep 2011 13:34:12 GMT\r\nServer: Apache/2.2.6 (Unix) mod_ssl/2.2.6 OpenSSL/0.9.7a mod_bwlimited/1.4 FrontPage/5.0.2.2635 mod_auth_passthrough/2.1 PHP/5.2.4\r\nLast-Modified: Thu, 03 Mar 2005 21:18:36 GMT\r\nETag: "5814d8-663c88-2c3d2300"\r\nAccept-Ranges: bytes\r\nContent-Length: 6011062\r\nContent-Range: bytes 689106-6700167/6700168\r\nContent-Type: video/x-msvideo\r\n\r\n')
            #
            # else:
            #     if stream == 0:
            try:
                # if piece == piecestart+1:
                #    time.sleep(100)
                stream.write(buf)
                # if conn != 0:
                #     # print >> sys.stderr, 'played',piece
                #     # print >> sys.stderr, 'output',piece,len(buf)
                #     r = conn.sendall(buf)
                # print 'ret',r
            except Exception as err:
                self.session.remove_torrent(self.torrent_handler)
                # exit(0)
            time.sleep(0.1)
        self.session.remove_torrent(self.torrent_handler)
        self.completed = True


# import subprocess
#
#
# class MagnetStream:
#     def __init__(self, magnet_link):
#         self.magnet_link = magnet_link
#         # self.torrent_link = torrent_link
#
#     def start(self):
#         with subprocess.Popen(
#             [f"peerflix {self.magnet_link} --vlc"],
#             shell=True,
#             stderr=subprocess.PIPE,
#             stdout=subprocess.PIPE
#         ) as proc:
#             for line in proc.stdout.readlines():
#                 logger.info(line.decode("utf-8"))


if __name__ == "__main__":
    magnet_stream = MagnetStream(
        "magnet:?xt=urn:btih:5933a99db70a430b50bfb5b5f5b56bc7f474ccd8",
        "https://ww2.1337x.buzz",
    )
    magnet_stream.start()
    # import vlc
    # vlc_instance = vlc.Instance()
    # vlc_instance.media_new_fd()
