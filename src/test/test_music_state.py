"""守的底線：音樂的歌單檔（人手改）與狀態檔（程式寫、不進版控）分開——程式只寫狀態檔、歌單只從歌單檔來；
面板刪掉時狀態檔寫的是明確的 null。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from music import config as music_config  # noqa: E402

PLAYLIST_A = "https://www.youtube.com/watch?v=a&list=PLAAA"
PLAYLIST_B = "https://www.youtube.com/watch?v=b&list=PLBBB"


class MusicStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.playlists = Path(self.tmp.name) / "music_playlists.json"
        self.state = Path(self.tmp.name) / "music_state_runtime.json"
        for attr, path in (("MUSIC_PLAYLISTS_PATH", self.playlists), ("MUSIC_STATE_PATH", self.state)):
            patcher = mock.patch.object(music_config, attr, str(path))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"RUNTIME_BACKUP_DIR": os.path.join(self.tmp.name, "backup")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_playlists(self, extra=None):
        music = {"playlist_url": [PLAYLIST_A, PLAYLIST_B], "audio_mode": "opus", **(extra or {})}
        self.playlists.write_text(json.dumps({"music": music}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.utime(self.playlists, ns=(os.stat(self.playlists).st_mtime_ns + 1_000_000,) * 2)

    def test_state_fields_left_in_the_playlist_file_are_ignored(self):
        """歌單檔裡就算殘留舊的狀態欄位（拆檔前的寫法），也不當狀態讀。"""
        self._write_playlists({"last_video_id": "old", "panel_message_id": 11, "shuffle": True})
        self.assertEqual({}, music_config.read_state())
        self.assertEqual([PLAYLIST_A, PLAYLIST_B], music_config.read_playlists_file()["playlist_url"])

    def test_saving_touches_only_the_state_file(self):
        self._write_playlists()
        before = self.playlists.read_text(encoding="utf-8")
        music_config.save_state("last_video_id", "new")
        music_config.save_state("shuffle", True)
        self.assertEqual(before, self.playlists.read_text(encoding="utf-8"), "歌單檔一碼都不能動")
        self.assertEqual({"last_video_id": "new", "shuffle": True}, json.loads(self.state.read_text(encoding="utf-8")))
        self.assertEqual("new", music_config.read_state()["last_video_id"])

    def test_a_cleared_panel_is_an_explicit_null(self):
        self._write_playlists()
        music_config.save_state("panel_message_id", 11)
        music_config.save_state("panel_message_id", None)
        self.assertIn("panel_message_id", music_config.read_state())
        self.assertIsNone(music_config.read_state()["panel_message_id"])

    def test_announcer_clears_the_panel_id_explicitly(self):
        """面板刪掉後 announcer 寫的是 null，不是把欄位拿掉：「沒有面板」和「不知道」要分得開。"""
        from music.announcer import Announcer
        self._write_playlists()
        Announcer._save_panel_id(11)
        Announcer._save_panel_id(None)
        self.assertIsNone(Announcer._load_panel_id())
        Announcer._save_panel_id(22)
        self.assertEqual(22, Announcer._load_panel_id())

    def test_state_file_cannot_inject_settings(self):
        """狀態檔是程式寫的，就算被塞了歌單或音訊模式也不能變成設定。"""
        self._write_playlists()
        self.state.write_text(json.dumps({"playlist_url": ["https://evil"], "audio_mode": "pcm", "shuffle": True}), encoding="utf-8")
        self.assertEqual({"playlist_url": [PLAYLIST_A, PLAYLIST_B], "audio_mode": "opus"}, music_config.read_playlists_file())

    def test_playlists_never_come_from_the_state_file(self):
        self._write_playlists()
        self.state.write_text(json.dumps({"playlist_url": ["https://evil"], "shuffle": True}), encoding="utf-8")
        self.assertNotIn("playlist_url", music_config.read_state())

    def test_config_reads_playlists_from_one_file_and_toggles_from_the_other(self):
        self._write_playlists({"active_playlists": ["PLAAA"], "shuffle": False})   # 殘留在歌單檔裡的舊欄位，不算
        self.state.write_text(json.dumps({"active_playlists": ["PLBBB"], "shuffle": True}), encoding="utf-8")
        with mock.patch.object(music_config.ChannelConfig, "load_config", return_value={"music_voice_channel_id": 1}):
            self.assertTrue(music_config.RuntimeMusicConfig._load_config())
            cfg = music_config.RuntimeMusicConfig._config
        self.assertEqual([PLAYLIST_A, PLAYLIST_B], [p.url for p in cfg.playlists])
        self.assertEqual("opus", cfg.audio_mode)
        self.assertEqual(["PLBBB"], cfg.active_keys, "啟用的歌單以狀態檔為準")
        self.assertTrue(cfg.shuffle)
        music_config.RuntimeMusicConfig._config = None


if __name__ == "__main__":
    unittest.main()
