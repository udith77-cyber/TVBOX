#!/usr/bin/python
# coding=utf-8
# hochu.tv（Хочу.ТВ）TVBox 蜘蛛框架版：俄语成人电视频道直播站，65 个频道，无分类。
# 播放链（已验证）：频道页 -> /iframes/xxx.php（需 Sec-Fetch 头 + Referer）-> /player/playerjs.php?ch=N
# （Referer=iframe 页）-> generatedFile "m3u8 或 m3u8"（wmsAuthSign 时效签名）-> 直播 m3u8（需 Referer=频道页）。
# 修改：参考 OXAX.py，playerContent 直接返回 video:// 真实 m3u8，避免 localProxy 兼容性问题。
import re, json, time
try:
    import requests as _rq
except Exception:
    _rq = None
try:
    from urllib.parse import quote as _quote, unquote as _unquote, urljoin as _urljoin
except ImportError:
    from urllib import quote as _quote, unquote as _unquote
    from urlparse import urljoin as _urljoin


class Spider:
    def __init__(self):
        self.site = "https://hochu.tv"
        self.name = "HochuTV"
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.header = {"User-Agent": self.ua, "Referer": self.site + "/",
                       "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                       "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
        self.s = self.session = self.sess = _rq.Session() if _rq else None
        self._extend = {}
        self.cat_scope = None
        self.cat_href_re = None
        self.list_scope = None
        self.detail_tpl = None
        self.play_tpl = None
        self.m3u8_var = None
        self.search_tpl = None
        self.page_mode = None
        self._chans = []
        self._chans_at = 0.0
        self._stream_urls = {}
        self._stream_at = {}

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".ts")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    def _fetch(self, url, headers=None, timeout=20):
        h = dict(self.header)
        if headers:
            h.update(headers)
        if self.s is not None:
            try:
                r = self.s.get(url, headers=h, timeout=timeout)
                return r.status_code, r.content
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), resp.read()
        except Exception:
            return 0, b""

    def _get_text(self, url, headers=None, timeout=20):
        code, data = self._fetch(url, headers, timeout)
        if code != 200 or not data:
            return ""
        try:
            return data.decode("utf-8", "ignore")
        except Exception:
            return ""

    def _channels(self):
        now = time.time()
        if self._chans and now - self._chans_at < 3600:
            return self._chans
        chs = []
        try:
            html = self._get_text(self.site + "/")
            for m in re.finditer(r'href="(/[\w\-]+\.html)"><img[^>]*src="(/images/[^"]+)"[^>]*/?>\s*<div class="titchan">([^<]+)</div>', html):
                p, img, nm = m.groups()
                nm = (nm or "").strip()
                if not nm or not p:
                    continue
                chs.append({"id": p, "name": nm, "pic": self.site + img})
        except Exception:
            pass
        if chs:
            self._chans, self._chans_at = chs, now
        return self._chans or chs

    def _item(self, c):
        return {"vod_id": c["id"], "vod_name": c["name"], "vod_pic": c["pic"], "vod_remarks": "直播"}

    def _desc(self, path):
        try:
            html = self._get_text(self.site + path)
            m = re.search(r'id="content-2">(.*?)</div>\s*</div>', html, re.S)
            if not m:
                return ""
            txt = re.sub(r"<[^>]+>", " ", m.group(1))
            return re.sub(r"\s+", " ", txt).strip()[:500]
        except Exception:
            return ""

    def _resolve(self, path):
        """解析出频道对应的 m3u8 直链列表（通常两个：主/备）"""
        now = time.time()
        if path in self._stream_urls and now - self._stream_at.get(path, 0) < 120:
            return self._stream_urls[path]
        urls = []
        try:
            page_url = self.site + path
            html = self._get_text(page_url)
            m = re.search(r'<iframe[^>]+src="(/iframes/[^"]+)"', html)
            if m:
                ifr_url = self.site + m.group(1)
                h2 = {"Referer": page_url, "Sec-Fetch-Dest": "iframe", "Sec-Fetch-Mode": "navigate",
                      "Sec-Fetch-Site": "same-origin", "Upgrade-Insecure-Requests": "1"}
                html2 = self._get_text(ifr_url, h2)
                m2 = re.search(r'player/playerjs\.php\?ch=(\d+)', html2)
                if m2:
                    pjs = self.site + "/player/playerjs.php?ch=" + m2.group(1)
                    html3 = self._get_text(pjs, {"User-Agent": self.ua, "Referer": ifr_url})
                    m3 = re.search(r'generatedFile\s*=\s*"([^"]+)"', html3)
                    if m3:
                        gf = m3.group(1).replace("\\/", "/")
                        urls = [u.strip() for u in gf.split(" or ") if u.strip().startswith("http")]
        except Exception:
            urls = []
        if urls:
            self._stream_urls[path] = urls
            self._stream_at[path] = now
        return urls

    def _pick_m3u8(self, path, line):
        """按线路取 m3u8 直链，并验证可访问；失效则刷新一次"""
        ref = self.site + path
        for attempt in (0, 1):
            urls = self._resolve(path)
            if not urls:
                break
            mu = urls[1] if (line and len(urls) > 1) else urls[0]
            txt = self._get_text(mu, {"User-Agent": self.ua, "Referer": ref})
            if "#EXTM3U" in txt:
                return mu, ref
            # 签名失效，清缓存重试
            self._stream_at[path] = 0
        return "", ref

    def init(self, extend=""):
        self._extend = {}
        if isinstance(extend, dict):
            self._extend = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                e = json.loads(extend)
                if isinstance(e, dict):
                    self._extend = e
            except Exception:
                pass

    def homeContent(self, filter=None):
        chs = self._channels()
        return {"class": [{"type_id": "all", "type_name": "全部频道"}],
                "filters": {},
                "list": [self._item(c) for c in chs[:12]]}

    def homeVideoContent(self):
        return {"list": [self._item(c) for c in self._channels()]}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        chs = self._channels()
        items = [self._item(c) for c in chs]
        return {"list": items, "page": 1, "pagecount": 1, "limit": len(items), "total": len(items)}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or "").strip()
        if "$" in vid:
            vid = vid.split("$")[-1].strip()
        vid = _unquote(vid)
        ch = None
        for c in self._channels():
            if c["id"] == vid:
                ch = c
                break
        if ch is None:
            return {"list": []}
        return {"list": [{"vod_id": ch["id"], "vod_name": ch["name"], "vod_pic": ch["pic"],
                           "vod_content": self._desc(ch["id"]), "type_name": "电视直播",
                           "vod_play_from": "HochuTV",
                           "vod_play_url": "直播$%s#备用线路$%s|bk" % (ch["id"], ch["id"])}]}

    def searchContent(self, key, quick=False, pg="1"):
        kw = str(key or "").strip().lower()
        items = [self._item(c) for c in self._channels() if kw and kw in c["name"].lower()]
        return {"list": items, "page": 1, "pagecount": 1, "limit": len(items), "total": len(items)}

    def playerContent(self, flag, ids, vipFlags=None):
        """
        参考 OXAX.py：直接返回 video:// 真实 m3u8 直链，交由播放器处理。
        播放器请求 m3u8 / 分片时会带上 header 中的 Referer，满足站点校验。
        """
        u = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        u = str(u or "").strip()
        if "$" in u:
            u = u.split("$")[-1].strip()
        u = _unquote(u)
        line = 1 if u.endswith("|bk") else 0
        path = u[:-3] if line else u
        if not path.startswith("/"):
            return {"parse": 0, "url": "", "header": {}}

        m3u8, ref = self._pick_m3u8(path, line)
        if not m3u8:
            # 解析失败时退回 localProxy（部分客户端仍可用）
            proxy = "http://127.0.0.1:9978/proxy?do=py&type=live&url=" + _quote(path, safe="") + "&line=%d" % line
            return {"parse": 0, "url": proxy, "header": {}}

        header = {
            "User-Agent": self.ua,
            "Referer": ref,
            "Origin": self.site,
            "Accept": "*/*",
        }
        return {"parse": 0, "url": m3u8, "header": header}

    # ------- 以下 localProxy 保留作为兜底，正常播放不再依赖 -------
    def _proxy_live(self, path, line):
        ref = self.site + path
        m3u8, ref2 = self._pick_m3u8(path, line)
        if not m3u8:
            return [502, "text/plain", b"", {}]
        ref = ref2 or ref
        txt = self._get_text(m3u8, {"User-Agent": self.ua, "Referer": ref})
        if "#EXTM3U" not in txt:
            return [502, "text/plain", b"", {}]
        base = m3u8.split("?")[0].rsplit("/", 1)[0] + "/"
        sign = m3u8.split("?", 1)[1] if "?" in m3u8 else ""
        out = []
        for ln in txt.splitlines():
            s = (ln or "").strip()
            if not s or s.startswith("#"):
                out.append(ln)
                continue
            seg = _urljoin(base, s)
            if sign:
                seg += ("&" if "?" in seg else "?") + sign
            out.append("http://127.0.0.1:9978/proxy?do=py&type=ts&url=" + _quote(seg, safe="") +
                       "&ref=" + _quote(ref, safe=""))
        body = ("\n".join(out) + "\n").encode("utf-8")
        return [200, "application/vnd.apple.mpegurl", body, {"Content-Length": str(len(body))}]

    def _proxy_ts(self, u, ref):
        code, data = self._fetch(u, {"User-Agent": self.ua, "Referer": ref or self.site + "/", "Accept": "*/*"}, 30)
        if code != 200 or not data:
            return [502, "text/plain", b"", {}]
        head = data[:16].lstrip()
        if head.startswith((b"<html", b"<!DOC", b"{", b"403", b"404")):
            return [502, "text/plain", b"", {}]
        return [200, "video/mp2t", data, {"Content-Length": str(len(data)), "Accept-Ranges": "bytes"}]

    def localProxy(self, param):
        try:
            p = json.loads(param) if isinstance(param, str) else (param or {})
            t = p.get("type", "")
            if t == "live":
                return self._proxy_live(_unquote(p.get("url", "")), int(p.get("line", 0) or 0))
            if t == "ts":
                return self._proxy_ts(_unquote(p.get("url", "")), _unquote(p.get("ref", "")))
            return [502, "text/plain", b"", {}]
        except Exception:
            return [502, "text/plain", b"", {}]