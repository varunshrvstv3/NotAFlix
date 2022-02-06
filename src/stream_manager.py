import threading
import time

import libtorrent


class StreamManager(threading.Thread):
    def __init__(
        self,
        name: str,
        torrent_handler: libtorrent.torrent_handle,
        start_piece: int,
        piece_per_write: int,
        end_piece: int,
        barrier: threading.Barrier
    ):
        super().__init__()
        self.name = name
        self.torrent_handler = torrent_handler
        self.start_piece = start_piece
        self.piece_per_write = piece_per_write
        self.end_piece = end_piece
        self.barrier = barrier

    def run(self):
        for piece in range(
            self.start_piece, self.end_piece, self.piece_per_write
        ):
            print(f"{self.name} picked {piece} to download")
            status = self.torrent_handler.status()
            priority = self.torrent_handler.piece_priority(piece)
            if priority == 0:
                self.torrent_handler.piece_priority(piece, 1)
            while not status.pieces[piece]:
                status = self.torrent_handler.status()
                time.sleep(5)
            print(f"{self.name} finished downloading {piece}")
            print(f"{self.name} Waiting for other threads to finish.")
            self.barrier.wait()
