"""Tests core noi bo (offline, khong goi Douyin that)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from core.douyin import (  # noqa: E402
    classify_link,
    extract_first_url,
    extract_mix_id,
    normalize_detail,
    quality_from_size,
    video_url_candidates,
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
    assert classify_link("https://www.douyin.com/collection/123456789012345")["type"] == "mix"
    assert classify_link("https://www.douyin.com/mix/123456789012345")["type"] == "mix"
    assert extract_mix_id("xem https://www.douyin.com/collection/123456789012345 nhe") == "123456789012345"


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


def test_video_url_candidates_order():
    urls = video_url_candidates({
        "play_addr": {"url_list": ["http://base.mp4"]},
        "bit_rate": [
            {"bit_rate": 500, "play_addr": {"url_list": ["http://low.mp4"]}},
            {"bit_rate": 2000, "play_addr": {"url_list": ["http://high.mp4"]}},
            {"bit_rate": 2000, "play_addr": {"url_list": ["http://high.mp4"]}},
        ]})
    assert urls[0] == "http://high.mp4"
    assert len(urls) == len(set(urls))
    assert "http://base.mp4" in urls


def test_local_aweme_dedup(tmp_path):
    from core.storage import aweme_downloaded, local_aweme_ids
    aid = "7123456789012345678"
    assert aweme_downloaded(tmp_path, aid) is False
    (tmp_path / f"2024-01-01_hi_{aid}.mp4").write_bytes(b"x" * 10)
    (tmp_path / f"2024-01-01_hi_{aid}_cover.jpg").write_bytes(b"x" * 10)
    (tmp_path / "note.txt").write_text("bo qua")
    ids = local_aweme_ids(tmp_path)
    assert aid in ids
    assert aweme_downloaded(tmp_path, aid) is True
    # sidecar don le khong tinh
    (tmp_path / f"2024-01-01_hi_{aid}.mp4").unlink()
    assert aweme_downloaded(tmp_path, aid) is False
