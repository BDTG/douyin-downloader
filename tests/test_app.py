"""Tests app standalone (offscreen). E2E stack thật do người chạy tay."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from app.localapi import LocalStack
from app.stackman import StackManager, port_open
from app.views.douyin import DouyinPage

_app = None


def app():
    global _app
    if _app is None:
        _app = QApplication([])
    return _app


class TestStackman(unittest.TestCase):
    def test_port_closed(self):
        self.assertFalse(port_open(18999))

    def test_status_keys(self):
        st = StackManager("D:/ThucTap/douyin-docker").status()
        self.assertEqual(set(st), {"api", "gallery", "web"})

    def test_stop_noop(self):
        StackManager("D:/ThucTap/douyin-docker").stop()  # không nổ là đạt


class TestLocalApi(unittest.TestCase):
    def test_status_shape(self):
        ls = LocalStack("D:/ThucTap/douyin-docker")
        with mock.patch.object(ls.man, "status", return_value={"api": True, "gallery": False, "web": True}), \
             mock.patch.object(ls.man, "api_ok", return_value=True):
            r = ls.call_op("x", "getStatus")
        self.assertTrue(r["ok"])
        self.assertTrue(r["data"]["api"], "ok")
        names = [s["name"] for s in r["data"]["services"]]
        self.assertEqual(names, ["api", "gallery", "web"])

    def test_resolve_result_unknown(self):
        ls = LocalStack("D:/ThucTap/douyin-docker")
        r = ls.call_op("x", "resolveResult", {"id": "nope"})
        self.assertFalse(r["ok"])

    def test_unknown_op(self):
        ls = LocalStack("D:/ThucTap/douyin-docker")
        with self.assertRaises(RuntimeError):
            ls.call_op("x", "khongco")


class TestPage(unittest.TestCase):
    def test_build_and_empty(self):
        app()
        ls = LocalStack("D:/ThucTap/douyin-docker")
        p = DouyinPage(ls)
        p.url.setText("   ")
        p.resolve()
        self.assertIn("Dán link", p.msg.text())
        p._tick.stop()
        p.close()

    def test_show_result(self):
        app()
        ls = LocalStack("D:/ThucTap/douyin-docker")
        p = DouyinPage(ls)
        p.show_result({"aweme_id": "1", "author_nickname": "X", "code": "101",
                       "desc": "d", "media_type": "video", "duration_s": 8.0,
                       "width": 1080, "height": 1920, "quality": "FHD",
                       "date": "2026-09-01", "digg_count": 1, "comment_count": 0,
                       "share_count": 0, "music_title": "m", "cover_url": ""})
        self.assertIn("[FHD]", p.spec.text())
        p._tick.stop()
        p.close()

    def test_show_user_and_render_posts(self):
        app()
        ls = LocalStack("D:/ThucTap/douyin-docker")
        p = DouyinPage(ls)
        p.show_result({"type": "user", "author_nickname": "T", "author_sec_uid": "S",
                       "code": "", "name_vi": "Te"})
        self.assertFalse(p.user_box.isHidden())
        p._render_uposts([{"aweme_id": "1", "desc": "mô tả 1", "date": "2026-09-01",
                           "digg_count": 5, "media_type": "video", "image_count": 0},
                          {"aweme_id": "2", "desc": "mô tả 2", "date": "2026-09-02",
                           "digg_count": 7, "media_type": "gallery", "image_count": 3}],
                         False, 123, True)
        self.assertEqual(p.user_list.count(), 2)
        self.assertIn("đã chọn 2", p.user_count.text())
        p._tick.stop()
        p.close()


if __name__ == "__main__":
    unittest.main()
