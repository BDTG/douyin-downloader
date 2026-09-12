"""Tests core noi bo (offline, khong goi Douyin that)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from core.douyin import (  # noqa: E402
    classify_link,
    extract_first_url,
    normalize_detail,
    quality_from_size,
)


def test_extract_first_url():
    t = "7.84 xem https://v.douyin.com/abc123/ nhe"
    assert extract_first_url(t) == "https://v.douyin.com/abc123/"
    assert extract_first_url("khong co link") == ""


def test_classify():
    assert classify_link("https://www.douyin.com/video/7123456789012345678")["type"] == "video"
    assert classify_link("https://www.douyin.com/note/123456789012345")["type"] == "gallery"
    assert classify_link("https://v.douyin.com/abc/")["type"] == "short"
    assert classify_link("https://www.douyin.com/user/MS4wLjABAAAAxxxx")["type"] == "user"


def test_quality_short_edge():
    assert quality_from_size(1080, 1920) == "FHD"  # doc 1080p
    assert quality_from_size(1920, 1080) == "FHD"
    assert quality_from_size(1440, 2560) == "QHD"
    assert quality_from_size(2160, 3840) == "4K"
    assert quality_from_size(720, 1280) == "HD"


def test_normalize_video():
    d = normalize_detail({
        "aweme_id": "1",
        "author": {"nickname": "T", "sec_uid": "S"},
        "statistics": {"digg_count": 5},
        "video": {"width": 1080, "height": 1920,
                  "bit_rate": [{"bit_rate": 1000,
                                "play_addr": {"url_list": ["http://x.mp4"]}}]},
        "desc": "hi", "create_time": 1700000000}, "u", "o")
    assert d["media_type"] == "video"
    assert d["play_url"] == "http://x.mp4"
    assert d["quality"] == "FHD"


def test_normalize_gallery():
    d = normalize_detail({
        "aweme_id": "2",
        "author": {"nickname": "T"},
        "image_post_info": {"images": [
            {"origin_image": {"url_list": ["http://a.jpg"]}},
            {"origin_image": {"url_list": ["http://b.jpg"]}}]},
        "desc": "gal", "create_time": 1700000000}, "u", "o")
    assert d["media_type"] == "gallery"
    assert d["image_count"] == 2
