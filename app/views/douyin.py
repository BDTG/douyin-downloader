"""Trang Douyin: port DouyinView (WinUI) sang Qt — resolve/preview/tải/bar.

Op module qua supervisor (blocking) nên chạy thread nền, cập nhật UI qua
signal. 1 job = 1 vòng poll (số hiệu tăng dần, vòng cũ tự dừng).
"""
from __future__ import annotations

import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# sup ở bản standalone là LocalStack (duck-type Supervisor của apphost).

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

MID = "douyin-downloader"


class _Bus(QObject):
    done = Signal(object, object)  # (tag, payload)


def _mb(b: float) -> str:
    return f"{b / 1048576:.1f} MB" if b > 1048576 else f"{max(1, int(b / 1024))} KB"


class DouyinPage(QWidget):
    def __init__(self, sup, status: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.sup = sup
        self._status = status or (lambda s: None)
        self._bus = _Bus()
        self._bus.done.connect(self._on_bg)
        self._poll_id = 0
        self._gal_urls: List[str] = []
        self._uposts: List[Dict[str, Any]] = []
        self._usec = ""
        self._ucursor = 0
        self._uhas_more = False
        self._gal_aweme = ""
        self._last_dl = (0, 0.0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)
        t = QLabel("Douyin Downloader")
        t.setObjectName("title")
        lay.addWidget(t)

        # stack card
        card = QWidget()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        row = QHBoxLayout()
        self.stack_dot = QLabel("●")
        self.stack_text = QLabel("Đang kiểm tra stack...")
        row.addWidget(self.stack_dot)
        row.addWidget(self.stack_text, 1)
        self.b_start = QPushButton("▶ Start")
        self.b_start.setObjectName("primary")
        self.b_stop = QPushButton("■ Stop")
        self.b_stop.setObjectName("ghost")
        self.b_start.clicked.connect(lambda: self._op("start"))
        self.b_stop.clicked.connect(lambda: self._op("stop"))
        row.addWidget(self.b_start)
        row.addWidget(self.b_stop)
        cl.addLayout(row)
        links = QHBoxLayout()
        for name, key in (("Gallery", "gallery"), ("Files đã tải", "files")):
            b = QPushButton(name)
            b.setObjectName("ghost")
            b.clicked.connect(lambda _=False, k=key: self._open_ui(k))
            links.addWidget(b)
        links.addStretch(1)
        cl.addLayout(links)
        lay.addWidget(card)

        # input card
        box = QWidget()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        inp = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Dán link video Douyin (v.douyin.com/...) — nhận cả đoạn share text")
        self.b_resolve = QPushButton("🔍 Nhận diện")
        self.b_resolve.setObjectName("ghost")
        self.b_dl = QPushButton("⬇ Tải")
        self.b_dl.setObjectName("primary")
        self.b_resolve.clicked.connect(self.resolve)
        self.b_dl.clicked.connect(self.download)
        inp.addWidget(self.url, 1)
        inp.addWidget(self.b_resolve)
        inp.addWidget(self.b_dl)
        bl.addLayout(inp)
        self.msg = QLabel()
        self.msg.setObjectName("muted")
        self.msg.setWordWrap(True)
        bl.addWidget(self.msg)
        lay.addWidget(box)

        # result
        res = QWidget()
        res.setObjectName("card")
        rl = QHBoxLayout(res)
        self.preview = QLabel("Chưa có preview")
        self.preview.setObjectName("muted")
        self.preview.setFixedSize(280, 320)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border: 1px solid #2B2B2B; border-radius: 8px;")
        rl.addWidget(self.preview)
        info = QVBoxLayout()
        self.author = QLabel()
        self.author.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.author.setWordWrap(True)
        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        self.spec = QLabel()
        self.spec.setObjectName("mono")
        self.spec.setWordWrap(True)
        self.job = QLabel()
        self.job.setObjectName("muted")
        self.job.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setMaximum(100)
        self.bar.setVisible(False)
        self.speed = QLabel()
        self.speed.setObjectName("mono")
        self.speed.setVisible(False)
        info.addWidget(self.author)
        info.addWidget(self.desc)
        info.addWidget(self.spec)
        info.addWidget(self.job)
        info.addWidget(self.bar)
        info.addWidget(self.speed)
        info.addStretch(1)
        rl.addLayout(info, 1)
        lay.addWidget(res, 1)

        # gallery strip
        self.gal_box = QWidget()
        self.gal_box.setObjectName("card")
        gl = QVBoxLayout(self.gal_box)
        nav = QHBoxLayout()
        b_prev = QPushButton("‹")
        b_next = QPushButton("›")
        b_prev.clicked.connect(lambda: self._gal_step(-1))
        b_next.clicked.connect(lambda: self._gal_step(1))
        self.gal_count = QLabel()
        self.gal_count.setObjectName("mono")
        nav.addWidget(b_prev)
        nav.addWidget(self.gal_count, 1)
        nav.addWidget(b_next)
        gl.addLayout(nav)
        self.gal_list = QListWidget()
        self.gal_list.setMaximumHeight(150)
        self.gal_list.itemChanged.connect(self._gal_changed)
        gl.addWidget(self.gal_list)
        drow = QHBoxLayout()
        for label, fn in (("⬇ Ảnh này", self._dl_one), ("⬇ Đã chọn", self._dl_picked),
                          ("⬇ Tất cả", self._dl_all)):
            b = QPushButton(label)
            b.setObjectName("ghost")
            b.clicked.connect(fn)
            drow.addWidget(b)
        drow.addStretch(1)
        gl.addLayout(drow)
        self.gal_box.setVisible(False)
        lay.addWidget(self.gal_box)

        # danh sach post cua 1 acc (chon tung video de tai)
        self.user_box = QWidget()
        self.user_box.setObjectName("card")
        ul = QVBoxLayout(self.user_box)
        unav = QHBoxLayout()
        self.user_count = QLabel()
        self.user_count.setObjectName("mono")
        unav.addWidget(self.user_count, 1)
        b_more = QPushButton("Tải thêm ↓")
        b_more.setObjectName("ghost")
        b_more.clicked.connect(self._uposts_more)
        unav.addWidget(b_more)
        ul.addLayout(unav)
        self.user_list = QListWidget()
        self.user_list.setMaximumHeight(220)
        self.user_list.itemChanged.connect(self._uposts_changed)
        ul.addWidget(self.user_list)
        urow = QHBoxLayout()
        for label, fn in (("⬇ Tải đã chọn", self._uposts_picked),
                          ("⬇ Tải tất cả trang này", self._uposts_all)):
            b = QPushButton(label)
            b.setObjectName("ghost")
            b.clicked.connect(fn)
            urow.addWidget(b)
        urow.addStretch(1)
        ul.addLayout(urow)
        self.user_box.setVisible(False)
        lay.addWidget(self.user_box)

        # nhat ky job (giu lai thong bao cu, doc duoc sau crash)
        logbox = QWidget()
        logbox.setObjectName("card")
        ll = QVBoxLayout(logbox)
        lh = QHBoxLayout()
        lt = QLabel("📋 Nhật ký tải")
        lt.setStyleSheet("font-weight: 600;")
        b_clear = QPushButton("Xóa")
        b_clear.setObjectName("ghost")
        b_clear.clicked.connect(self._clear_joblog)
        lh.addWidget(lt)
        lh.addStretch(1)
        lh.addWidget(b_clear)
        ll.addLayout(lh)
        self.joblog = QListWidget()
        self.joblog.setObjectName("mono")
        self.joblog.setMaximumHeight(110)
        ll.addWidget(self.joblog)
        lay.addWidget(logbox)
        self._load_joblog()

        self._tick = QTimer(self)
        self._tick.setInterval(5000)
        self._tick.timeout.connect(self._kick_status)
        self._tick.start()
        self._kick_status()
        self._last_status_txt = ""
        self._last_running = None

    # -- nền --
    def _bg(self, tag: str, fn, *a):
        def run():
            try:
                self._bus.done.emit(tag, ("ok", fn(*a)))
            except Exception as exc:
                self._bus.done.emit(tag, ("err", str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def _call(self, op: str, params: Optional[dict] = None, timeout=60):
        try:
            return self.sup.call_op(MID, op, params or {}, timeout_s=timeout)
        except RuntimeError as e:
            if "not connected" in str(e).lower():
                self.sup.start(MID, timeout_s=60)
                return self.sup.call_op(MID, op, params or {}, timeout_s=timeout)
            raise

    # -- stack --
    def _op(self, what: str):
        def go():
            (self.sup.start if what == "start" else self.sup.stop)(MID)
            return self.refresh_status(silent=True)
        self._bg("op", go)

    def _kick_status(self):
        """Hoi trang thai stack duoi nen (khong block UI thread)."""
        self._bg("status", lambda: self.sup.call_op(MID, "getStatus", timeout_s=8))

    def _show_status(self, r):
        d = r.get("data", r) if isinstance(r, dict) else {}
        parts = [f"{s.get('name')}: {'chạy' if s.get('listening') else 'dừng'}"
                 for s in d.get("services", [])]
        txt = "  •  ".join(parts) + f"  •  api: {d.get('api', '?')}"
        if txt != self._last_status_txt:
            self.stack_text.setText(txt)
            self._last_status_txt = txt
        running = bool(d.get("running"))
        if running != self._last_running:
            self.stack_dot.setStyleSheet(
                f"color: {'#4CAF7D' if running else '#D9534F'}; font-size: 16px;")
            self._last_running = running

    def refresh_status(self, silent=False):
        try:
            r = self.sup.call_op(MID, "getStatus", timeout_s=10)
            self._show_status(r)
        except Exception:
            if not silent:
                self.stack_text.setText("Stack chưa chạy — bấm ▶ Start.")
        return True

    def _open_ui(self, key: str):
        def go():
            r = self.sup.call_op(MID, "uiUrls", timeout_s=10)
            return (r.get("data", r) if isinstance(r, dict) else {}).get(key, "")
        self._bg("open", go)

    # -- nhận diện --
    def resolve(self):
        url = self.url.text().strip()
        if not url:
            self.msg.setText("⚠ Dán link video trước")
            return
        self.msg.setText("Đang nhận diện…")
        self._clear_result()
        self._bg("resolve", lambda: self.sup.call_op(MID, "resolve", {"url": url}, timeout_s=30))

    # -- post cua 1 acc: quet danh sach, tick chon tung video de tai --
    def _show_user(self, v: Dict[str, Any]):
        nick = v.get("author_nickname", "")
        code = v.get("code", "")
        name_vi = v.get("name_vi", "")
        disp = nick + (f" • {name_vi}" if name_vi and name_vi != nick else "")
        self.author.setText(f"{disp}  (#{code})" if code else disp)
        self.desc.setText("")
        self.spec.setText("📄 Trang cá nhân — tick chọn video rồi bấm tải.")
        self.msg.setText("Đang quét danh sách video…")
        self._uposts = []
        self._usec = str(v.get("author_sec_uid") or "")
        self._ucursor = 0
        self._uhas_more = False
        self.user_list.blockSignals(True)
        self.user_list.clear()
        self.user_list.blockSignals(False)
        self.user_box.setVisible(True)
        self._bg("userposts", lambda: self._fetch_uposts(append=False))

    def _fetch_uposts(self, append: bool):
        r = self.sup.call_op(MID, "userPosts",
                             {"sec_uid": self._usec, "cursor": self._ucursor, "count": 20},
                             timeout_s=90)
        d = (r.get("data", {}) or {}) if isinstance(r, dict) else {}
        if not r.get("ok", True):
            raise RuntimeError(str(r.get("error", "lỗi")))
        return {"items": d.get("items", []), "next": d.get("next_cursor", 0),
                "more": bool(d.get("has_more")), "append": append}

    def _render_uposts(self, items, append: bool, nxt, more: bool):
        from PySide6.QtWidgets import QListWidgetItem as _QWI
        if not append:
            self._uposts = []
            self.user_list.blockSignals(True)
            self.user_list.clear()
            self.user_list.blockSignals(False)
        self.user_list.blockSignals(True)
        for it in items:
            self._uposts.append(it)
            desc = (it.get("desc") or "(không mô tả)")[:60]
            tag = f"[ảnh {it.get('image_count')}] " if it.get("media_type") == "gallery" else ""
            line = f"☑ [{it.get('date', '')}] {tag}{desc} | tim {it.get('digg_count', 0)}"
            qwi = _QWI(line)
            qwi.setCheckState(Qt.Checked)
            self.user_list.addItem(qwi)
        self.user_list.blockSignals(False)
        self._ucursor = nxt
        self._uhas_more = more
        self._uposts_changed(None)

    def _uposts_changed(self, _item):
        n = sum(1 for i in range(self.user_list.count())
                if self.user_list.item(i).checkState() == Qt.Checked)
        extra = " • còn nữa (bấm Tải thêm ↓)" if self._uhas_more else ""
        self.user_count.setText(f"{self.user_list.count()} video  •  đã chọn {n}{extra}")

    def _uposts_more(self):
        if not self._usec:
            return
        self.msg.setText("Đang tải thêm…")
        self._bg("userposts", lambda: self._fetch_uposts(append=True))

    def _uposts_picked(self):
        idx = [i for i in range(self.user_list.count())
               if self.user_list.item(i).checkState() == Qt.Checked]
        if not idx:
            self.msg.setText("⚠ Chưa tick video nào.")
            return
        aids = [self._uposts[i]["aweme_id"] for i in idx if i < len(self._uposts)]
        self._bg("userdl", lambda: self._download_awemes(aids))

    def _uposts_all(self):
        if not self._uposts:
            return
        self._bg("userdl", lambda: self._download_awemes([it["aweme_id"] for it in self._uposts]))

    def _download_awemes(self, aids):
        done, fail = 0, 0
        logs = []
        for n, aid in enumerate(aids, 1):
            url = f"https://www.douyin.com/video/{aid}"
            try:
                r = self.sup.call_op(MID, "download", {"url": url}, timeout_s=30)
            except Exception as exc:
                self._emit_job(f"⚠ {aid}: {exc}", None)
                fail += 1
                continue
            d = (r.get("data", {}) or {}) if isinstance(r, dict) else {}
            jid = str(d.get("job_id", ""))
            if not jid:
                self._emit_job(f"⚠ {aid}: không tạo được job", None)
                fail += 1
                continue
            logs.append(f"⬇ [{n}/{len(aids)}] job {jid} <- {aid}")
            if self._poll_sync(jid):
                done += 1
            else:
                fail += 1
        summary = f"✅ Xong {done}/{len(aids)} video" + (f" ({fail} lỗi)" if fail else "")
        logs.append(summary)
        return {"done": done, "fail": fail, "logs": logs}

    def _poll_sync(self, job_id: str) -> bool:
        """Poll 1 job toi khi xong (dung trong worker tai nhieu video). True = success."""
        for _ in range(300):  # ~20 phut/job
            time.sleep(4)
            try:
                r = self.sup.call_op(MID, "jobStatus", {"job_id": job_id}, timeout_s=15)
            except Exception:
                continue
            d = (r.get("data", {}) or {}) if isinstance(r, dict) else {}
            if not r.get("ok", True):
                self._emit_job(f"Job {job_id}: ⚠ {d.get('error', r.get('error', 'lỗi'))}", None)
                return False
            st = str(d.get("status", ""))
            low = st.lower()
            if "success" in low or low == "done":
                self._emit_job(f"Job {job_id}: {st} — file ở Gallery.", (100, None))
                return True
            if "fail" in low:
                self._emit_job(f"Job {job_id}: {st} — {d.get('error', '')}", None)
                return False
            dl, tot = int(d.get("downloaded_bytes") or 0), int(d.get("total_bytes") or 0)
            bar = (int(min(100, dl * 100 // tot)), (dl, tot)) if tot > 0 else None
            self._emit_job(f"Job {job_id}: {st}", bar)
        self._emit_job(f"Job {job_id}: ⚠ quá lâu, bỏ qua", None)
        return False

    def _clear_result(self):
        self.author.setText("")
        self.desc.setText("")
        self.spec.setText("")
        self.preview.setText("Chưa có preview")
        self.preview.setPixmap(QPixmap())
        self.gal_box.setVisible(False)
        self.user_box.setVisible(False)
        self._gal_urls = []
        self._gal_aweme = ""

    # -- tải video --
    def download(self):
        url = self.url.text().strip()
        if not url:
            self.msg.setText("⚠ Dán link video trước")
            return
        self.msg.setText("Đang tạo job tải...")
        self.bar.setVisible(False)
        self.speed.setVisible(False)
        self._bg("download", lambda: self.sup.call_op(MID, "download", {"url": url}, timeout_s=30))

    def _poll(self, job_id: str, my_id: int):
        errs = 0
        while my_id == self._poll_id and errs < 5:
            time.sleep(2)
            if my_id != self._poll_id:
                return
            try:
                r = self.sup.call_op(MID, "jobStatus", {"job_id": job_id}, timeout_s=15)
                errs = 0
            except Exception:
                errs += 1
                continue
            d = r.get("data", r) if isinstance(r, dict) else {}
            if not r.get("ok", True):
                msg = str(r.get("error", "lỗi"))
                if "404" in msg or "not found" in msg.lower():
                    self._emit_job(f"Job {job_id}: ⚠ job mất (api đã restart?) — bấm ⬇ Tải lại.", None)
                else:
                    self._emit_job(f"Job {job_id}: ⚠ {msg}", None)
                return
            st = str(d.get("status", ""))
            err = str(d.get("error") or "")
            low = st.lower()
            if "fail" in low:
                self._emit_job(f"Job {job_id}: {st}" + (f" — {err}" if err else ""), None)
                return
            if "success" in low or low == "done":
                self._emit_job(f"Job {job_id}: {st} — file ở Gallery.", (100, None))
                return
            dl, tot = int(d.get("downloaded_bytes") or 0), int(d.get("total_bytes") or 0)
            bar = (int(min(100, dl * 100 // tot)), (dl, tot)) if tot > 0 else None
            self._emit_job(f"Job {job_id}: {st}", bar)

    def _emit_job(self, s: str, bar):
        """Poll chay thread nen — chi emit signal, UI thread tu ve (Qt cam cham widget)."""
        try:
            self._bus.done.emit("jobpoll", ("ok", {"text": s, "bar": bar}))
        except RuntimeError:
            pass  # app da dong

    def _set_job(self, s: str):
        self.job.setText(s)

    def _joblog_path(self) -> Optional[Path]:
        try:
            base = Path(self.sup.man.stack_dir)
        except Exception:
            return None
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / "logs").mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return base / "logs" / "jobs_ui.log"

    def _load_joblog(self):
        try:
            p = self._joblog_path()
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-50:] if p and p.is_file() else []
        except Exception:
            lines = []
        for ln in lines:
            if ln.strip():
                self.joblog.addItem(ln)
        if lines:
            self.joblog.scrollToBottom()

    def _log_job(self, text: str):
        line = f"{datetime.now():%H:%M:%S}  {text}"
        self.joblog.addItem(line)
        while self.joblog.count() > 200:
            self.joblog.takeItem(0)
        self.joblog.scrollToBottom()
        try:
            p = self._joblog_path()
            if p:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            pass

    def _clear_joblog(self):
        self.joblog.clear()
        try:
            p = self._joblog_path()
            if p and p.is_file():
                p.write_text("", encoding="utf-8")
        except Exception:
            pass

    def _bar(self, pct: int, dt):
        self.bar.setVisible(True)
        self.bar.setValue(pct)
        if dt:
            dl, tot = dt
            now = time.time()
            last_b, last_t = self._last_dl
            secs = max(0.5, now - last_t)
            spd = max(0.0, (dl - last_b) / secs)
            self._last_dl = (dl, now)
            self.speed.setVisible(True)
            self.speed.setText(f"{_mb(dl)}/{_mb(tot)}  •  {_mb(spd)}/s  •  {pct}%")

    # -- gallery --
    def _gal_step(self, d: int):
        n = self.gal_list.count()
        if not n:
            return
        i = (self.gal_list.currentRow() + d) % n
        self.gal_list.setCurrentRow(i)
        self._gal_show(i)

    def _gal_changed(self, _item):
        n = sum(1 for i in range(self.gal_list.count())
                if self.gal_list.item(i).checkState() == Qt.Checked)
        self.gal_count.setText(f"{self.gal_list.currentRow()+1}/{self.gal_list.count()}  •  đã chọn {n}")

    def _gal_show(self, i: int):
        if 0 <= i < len(self._gal_urls):
            self._load_preview(self._gal_urls[i])
        self._gal_changed(None)

    def _dl_one(self):
        self._dl_images([self.gal_list.currentRow()])

    def _dl_picked(self):
        idx = [i for i in range(self.gal_list.count())
               if self.gal_list.item(i).checkState() == Qt.Checked]
        self._dl_images(idx)

    def _dl_all(self):
        self._dl_images([])

    def _dl_images(self, indices: List[int]):
        if not self._gal_aweme:
            return
        self.msg.setText("Đang tải ảnh gốc...")
        self._bg("dlimg", lambda: self.sup.call_op(
            MID, "downloadImages",
            {"aweme_id": self._gal_aweme, "indices": indices}, timeout_s=300))

    def _load_preview(self, url: str):
        def fetch():
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        self._bg("preview", fetch)

    # -- nhận kết quả thread nền (chạy trên GUI thread) --
    @Slot(object, object)
    def _on_bg(self, tag: str, pack):
        status, payload = pack
        if tag == "open":
            if status == "ok" and payload:
                QDesktopServices.openUrl(payload)
            return
        if tag == "op":
            self._kick_status()
            return
        if tag == "preview":
            if status == "ok":
                px = QPixmap()
                if px.loadFromData(payload):
                    self.preview.setPixmap(px.scaledToWidth(280, Qt.SmoothTransformation))
                else:
                    self.preview.setText("Không đọc được preview")
            else:
                self.preview.setText("Không tải được preview (CDN chặn?)")
            return
        if tag == "status":
            if status == "ok" and isinstance(payload, dict):
                self._show_status(payload)
            return
        if status != "ok":
            self.msg.setText(f"Lỗi: {payload}")
            return
        if tag == "jobpoll":
            d = payload if isinstance(payload, dict) else {}
            if d.get("text") is not None:
                self._set_job(str(d["text"]))
                _t = str(d["text"])
                if "⚠" in _t or "success" in _t.lower() or "fail" in _t.lower():
                    self._log_job(_t)
            if d.get("bar") is not None:
                pct, dt = d["bar"]
                self._bar(int(pct), dt)
            return
        if tag == "userposts":
            d = payload if isinstance(payload, dict) else {}
            self._render_uposts(d.get("items", []), bool(d.get("append")),
                                d.get("next", 0), bool(d.get("more")))
            n = len(d.get("items", []))
            self.msg.setText(f"✅ Quét được {self.user_list.count()} video — tick chọn rồi bấm tải." if n
                             else "⚠ Acc này không quét được video (riêng tư/chặn).")
            return
        if tag == "userdl":
            d = payload if isinstance(payload, dict) else {}
            for ln in (d.get("logs") or []):
                self._log_job(str(ln))
            self.msg.setText(f"✅ Xong {d.get('done', 0)} video" +
                             (f" ({d.get('fail', 0)} lỗi)" if d.get("fail") else "") +
                             " — xem ở Gallery.")
            return
        if tag == "resolve":
            self._show_resolve(payload)
        elif tag == "resolved":
            self.show_result(payload if status == "ok" and isinstance(payload, dict) else {})
        elif tag == "videsc":
            d = payload if isinstance(payload, dict) else {}
            vi = str(d.get("vi", ""))
            d0 = str(d.get("desc0", ""))
            if vi and d0 and self.desc.text().startswith(d0[:20]):
                self.desc.setText(self.desc.text() + "\n🇻🇳 " + vi)
        elif tag == "download":
            d = payload.get("data", payload) if isinstance(payload, dict) else {}
            jid = str(d.get("job_id", ""))
            if not jid:
                self.msg.setText("Xem chi tiết ở Gallery.")
                return
            self.msg.setText("✅ Đã giao job tải.")
            self._log_job(f"⬇ Tạo job tải {jid}")
            self._last_dl = (0, time.time())
            self._poll_id += 1
            threading.Thread(target=self._poll, args=(jid, self._poll_id), daemon=True).start()
        elif tag == "dlimg":
            d = payload.get("data", payload) if isinstance(payload, dict) else {}
            saved = d.get("saved", []) if isinstance(d, dict) else []
            failed = d.get("failed", []) if isinstance(d, dict) else []
            n, f = len(saved), len(failed)
            _t = f"🖼 Tải ảnh: {n} xong" + (f" ({f} lỗi)" if f else "")
            self.msg.setText(_t + " — xem ở Gallery." if n else "⚠ Không tải được ảnh nào.")
            self._log_job(_t if n else "⚠ Không tải được ảnh nào.")

    def _show_resolve(self, payload):
        # module resolve là nền 2 bước: ở đây payload là {pending,id} -> poll resolveResult
        d = payload.get("data", payload) if isinstance(payload, dict) else {}
        rid = str(d.get("id", ""))
        if not rid:
            self.msg.setText("⚠ Không nhận diện được.")
            return
        self._bg("resolved", lambda: self._wait_resolve(rid))

    def _wait_resolve(self, rid: str):
        for _ in range(30):
            time.sleep(2)
            r = self.sup.call_op(MID, "resolveResult", {"id": rid}, timeout_s=15)
            dd = r.get("data", r) if isinstance(r, dict) else {}
            if r.get("ok") and dd.get("done"):
                return dd.get("result", {})
        return {}

    def show_result(self, v: Dict[str, Any]):
        if not isinstance(v, dict) or (not v.get("aweme_id") and not v.get("author_nickname")):
            self.msg.setText("⚠ Không nhận diện được link này.")
            return
        if v.get("type") == "user" and (v.get("author_sec_uid") or v.get("author_nickname")):
            self._show_user(v)
            return
        if not v.get("aweme_id"):
            # có nickname nhưng Douyin không trả detail (chặn tạm thời) — báo thử lại
            self.author.setText(str(v.get("author_nickname", "")))
            self.msg.setText("⚠ Douyin không trả dữ liệu — bấm 🔍 Nhận diện lại.")
            return
        nick, code = v.get("author_nickname", ""), v.get("code", "")
        name_vi = v.get("author_nickname") and v.get("name_vi", "") or ""
        disp = nick
        if name_vi and name_vi != nick:
            disp = f"{nick} • {name_vi}"
        self.author.setText(f"{disp}  (#{code})" if code else disp)
        self.desc.setText(str(v.get("desc", "")))
        _desc0 = str(v.get("desc", ""))
        if any("一" <= ch <= "鿿" for ch in _desc0):
            def _fetch_vi(_d=_desc0):
                try:
                    r = self.sup.call_op(MID, "videsc", {"text": _d}, timeout_s=30)
                    dd = (r.get("data", {}) or {}) if isinstance(r, dict) else {}
                    return {"desc0": _d, "vi": str(dd.get("desc_vi", ""))}
                except Exception:
                    return {"desc0": _d, "vi": ""}
            self._bg("videsc", _fetch_vi)
        w, h, q = v.get("width", ""), v.get("height", ""), v.get("quality", "")
        res = f"{w}x{h}" + (f" [{q}]" if q else "") if w else ""
        mt = v.get("media_type", "")
        if mt == "gallery":
            self.spec.setText(f"[ảnh] {v.get('image_count', '')} ảnh  •  {v.get('date', '')}  •  tim {v.get('digg_count', '')}  •  nhạc: {v.get('music_title', '')}")
        else:
            self.spec.setText(f"{v.get('duration_s', '')}s  •  {res}  •  {v.get('date', '')}  •  tim {v.get('digg_count', '')} bl {v.get('comment_count', '')} share {v.get('share_count', '')}  •  nhạc: {v.get('music_title', '')}")
        self.msg.setText("✅ Xong — bấm ⬇ Tải để tải bản gốc.")
        imgs = v.get("images") or []
        if mt == "gallery" and imgs:
            self._gal_aweme = str(v.get("aweme_id", ""))
            self._gal_urls = [str(u) for u in imgs]
            self.gal_list.blockSignals(True)
            self.gal_list.clear()
            for i in range(len(self._gal_urls)):
                it = QListWidgetItem(f"☑ ảnh {i+1}")
                it.setCheckState(Qt.Checked)
                self.gal_list.addItem(it)
            self.gal_list.blockSignals(False)
            self.gal_list.setCurrentRow(0)
            self.gal_box.setVisible(True)
            self._gal_show(0)
        elif v.get("cover_url"):
            self._load_preview(str(v["cover_url"]))
