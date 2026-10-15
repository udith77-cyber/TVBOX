# -*- coding: utf-8 -*-


import sys
import re
import json
import time
import base64
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

try:
    import requests
except Exception:
    requests = None


_HOST_FALLBACK = 'https://222.0qck.cc'  # 2026-10-14 实测可用
_ENTRY = 'https://hsck.net/'           # 入口，302 跳到最新域名


class Spider(BaseSpider):
    def getName(self):
        return '黄色仓库'

    def init(self, extend=''):
        self.host = ''
        self.ua = ('Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0')
        self.header = {
            'User-Agent': self.ua,
            'Referer': _ENTRY,
        }
        # extend 可传 {"host": "https://新域名"} 覆盖
        try:
            if extend:
                ext = extend if isinstance(extend, dict) else json.loads(extend)
                if isinstance(ext, dict) and ext.get('host'):
                    self.host = str(ext['host']).rstrip('/')
        except Exception:
            pass
        self.classes = [
            {'type_id': '1', 'type_name': '日韩AV'},
            {'type_id': '7', 'type_name': '日本骑兵'},
            {'type_id': '10', 'type_name': '日本无码'},
            {'type_id': '8', 'type_name': '中文字幕'},
            {'type_id': '9', 'type_name': '骑兵中字'},
            {'type_id': '26', 'type_name': 'DMM破解'},
            {'type_id': '2', 'type_name': '国产系列'},
            {'type_id': '15', 'type_name': '国产视频'},
            {'type_id': '3', 'type_name': '欧美'},
            {'type_id': '21', 'type_name': '欧美成人'},
            {'type_id': '4', 'type_name': '成人动漫'},
            {'type_id': '22', 'type_name': '日本动漫'},
        ]

    # ---------------- 工具 ----------------

    def _abs(self, u):
        if not u:
            return ''
        u = str(u).strip()
        if re.match(r'^https?://', u, re.I):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return self.host + (u if u.startswith('/') else '/' + u)

    def _clean(self, s):
        if not s:
            return ''
        s = str(s)
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
        s = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&')
        s = s.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
        s = s.replace('&lt;', '<').replace('&gt;', '>')
        return re.sub(r'\s+', ' ', s).strip()

    def _ensure_host(self):
        """跟随 hsck.net 的 302 跳转解析出真实域名，失败用兜底。"""
        if self.host:
            return self.host
        host = ''
        try:
            if requests is not None:
                r = requests.get(_ENTRY, headers={'User-Agent': self.ua},
                                 timeout=15, allow_redirects=True)
                final = r.url or ''
            else:
                import urllib.request
                req = urllib.request.Request(_ENTRY, headers={'User-Agent': self.ua})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    final = resp.geturl() or ''
            m = re.match(r'(https?://[^/]+)', final)
            if m:
                host = m.group(1)
        except Exception:
            host = ''
        self.host = host or _HOST_FALLBACK
        self.header['Referer'] = self.host + '/'
        return self.host

    def _fetch(self, url):
        # 优先用框架自带的 fetch（走 OkHttp），没有再用 requests
        def _once():
            try:
                if hasattr(super(), 'fetch'):
                    res = super().fetch(url, headers=self.header)
                    if isinstance(res, dict):
                        return res.get('content') or res.get('text') or ''
                    if hasattr(res, 'text'):
                        return res.text or ''
                    return str(res or '')
            except Exception:
                pass
            try:
                if requests is None:
                    import urllib.request
                    req = urllib.request.Request(url, headers=self.header)
                    with urllib.request.urlopen(req, timeout=15) as r:
                        return r.read().decode('utf-8', errors='ignore')
                r = requests.get(url, headers=self.header, timeout=15)
                return r.content.decode('utf-8', errors='ignore') if r.content else ''
            except Exception:
                return ''
        html = _once()
        if not html or len(html) < 3000:
            html = _once()  # 空页面重试一次
        return html

    def _post_json(self, url, data):
        """POST 表单并解析 JSON（换播放地址用，不走框架 fetch 以兼容各分支）。"""
        headers = dict(self.header)
        headers['X-Requested-With'] = 'XMLHttpRequest'
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        try:
            if requests is not None:
                r = requests.post(url, data=data, headers=headers, timeout=20)
                return json.loads(r.text) if r.text else {}
            else:
                import urllib.request
                import urllib.parse
                body = urllib.parse.urlencode(data).encode('utf-8')
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read().decode('utf-8', errors='ignore') or '{}')
        except Exception:
            return {}

    def _pagecount(self, html, tid):
        pages = [int(x) for x in re.findall(r'/vodtype/%s-(\d+)\.html' % re.escape(str(tid)), html)]
        return max(pages) if pages else 1

    def _parse_list(self, html):
        result = []
        seen = set()
        if not html:
            return result
        # stui-vodlist__box 卡片；广告卡 href 是站外链接，只收 /v5/数字-1-1.html
        cards = re.split(r'stui-vodlist__box', html)
        for card in cards[1:]:
            hm = re.search(r'href="(/v5/(\d+)-1-1\.html)"', card)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            tm = re.search(r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a[^>]*>([^<]{2,200})</a>', card)
            name = self._clean(tm.group(1)) if tm else vid
            pm = re.search(r'data-original="([^"]+)"', card)
            pic = pm.group(1) if pm else ''
            if pic and ('load.gif' in pic or pic.lower().endswith('.gif')):
                pic = ''
            dm = re.search(r'pic-text[^"]*"[^>]*>([^<]{1,30})<', card)
            remarks = self._clean(dm.group(1)) if dm else ''
            result.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        return result

    def _detail_pic(self, html, real_id):
        """详情页取封面：data-original 挂在 <a class="stui-vodlist__thumb lazyload"> 上，
        优先取上下文含本视频 id 的，排除占位 gif。"""
        cands = []
        for m in re.finditer(r'data-original="([^"]+)"', html):
            p = (m.group(1) or '').strip()
            if not p or 'load.gif' in p or p.lower().endswith('.gif'):
                continue
            ctx = html[max(0, m.start() - 600):m.start()]
            score = 1 if real_id and real_id in ctx else 0
            cands.append((score, p))
        if not cands:
            return ''
        cands.sort(key=lambda x: -x[0])
        return cands[0][1]

    def _get_play_url(self, vid):
        """播放页取 AK 参数 -> POST /static/count.php -> base64 解出 m3u8。"""
        self._ensure_host()
        url = f'{self.host}/v5/{vid}-1-1.html'
        html = self._fetch(url)
        if not html:
            return ''
        m = re.search(
            r"var\s+AID='(\d+)',\s*ASID='(\d+)',\s*ANID='(\d+)',\s*AK='([0-9a-fA-F]+)'",
            html)
        if not m:
            return ''
        aid, asid, anid, ak = m.groups()
        now = int(time.time() * 1000)
        data = {
            'id': aid, 'sid': asid, 'nid': anid, 'tk': ak, 'g': '1',
            'x': '120', 'y': '240', 'dt': '6100',
            'sw': '1920', 'sh': '1080', 'tz': '-480', 't': str(now),
        }
        resp = self._post_json(f'{self.host}/static/count.php', data)
        try:
            if resp.get('ok') and resp.get('u'):
                return base64.b64decode(resp['u']).decode('utf-8', errors='ignore').strip()
        except Exception:
            pass
        return ''

    # ---------------- TVBox 接口 ----------------

    def homeContent(self, filter):
        self._ensure_host()
        return {'class': self.classes, 'filters': {}}

    def homeVideoContent(self):
        self._ensure_host()
        html = self._fetch(self.host + '/')
        lst = self._parse_list(html)[:20]
        return {'list': lst}

    def categoryContent(self, tid, pg, filter, extend):
        self._ensure_host()
        try:
            page = int(pg)
        except Exception:
            page = 1
        tid = str(tid or '1')
        if page <= 1:
            url = f'{self.host}/vodtype/{tid}.html'
        else:
            url = f'{self.host}/vodtype/{tid}-{page}.html'
        html = self._fetch(url)
        lst = self._parse_list(html)
        return {
            'list': lst,
            'page': page,
            'pagecount': self._pagecount(html, tid),
            'limit': len(lst) if lst else 40,
            'total': 999999,
        }

    def detailContent(self, ids):
        self._ensure_host()
        vid = str(ids[0]) if ids else ''
        m = re.search(r'(\d+)', vid)
        real_id = m.group(1) if m else vid
        url = f'{self.host}/v5/{real_id}-1-1.html'
        html = self._fetch(url)
        if not html:
            return {'list': []}

        tm = re.search(r'<title>(.*?)</title>', html, re.S)
        name = self._clean(tm.group(1)) if tm else real_id
        name = re.sub(r'\s*[-–—]\s*黄色仓库.*$', '', name).strip()

        pic = self._detail_pic(html, real_id)

        dm = re.search(r'时间[：:]\s*(\d{4}-\d{2}-\d{2})', html)
        date = dm.group(1) if dm else ''
        year = date[:4] if date else ''

        play_url = self._get_play_url(real_id)
        if not pic and play_url:
            # 兜底: m3u8 路径 /video/m3u8/日期/hash/index.m3u8
            # 与封面 /video/m3u8/日期/hash/vod.jpg 同路径，页内按 hash 找封面
            hm = re.search(r'/video/m3u8/([\d/]+/([0-9a-f]{8}))/index\.m3u8', play_url)
            if hm:
                cm = re.search(r'https?://[^"\s]*%s[^"\s]*vod\.jpg' % re.escape(hm.group(2)), html)
                if cm:
                    pic = cm.group(0)
        eps = []
        if play_url:
            eps.append(f'播放${play_url.replace("$", "＄")}')

        vod = {
            'vod_id': vid,
            'vod_name': name,
            'type_name': '',
            'vod_year': year,
            'vod_area': '',
            'vod_remarks': date,
            'vod_actor': '',
            'vod_director': '',
            'vod_pic': pic,
            'vod_content': f'更新时间: {date}' if date else '',
            'vod_play_from': '黄色仓库',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    def _search_url(self, key, page):
        kw = quote(str(key), safe='')
        if page <= 1:
            # /vodsearch/关键词-------------.html (13 横杠)
            return f'{self.host}/vodsearch/{kw}-------------.html'
        # /vodsearch/关键词----------N---.html (10 横杠 + 页码 + 3 横杠)
        return f'{self.host}/vodsearch/{kw}----------{page}---.html'

    def searchContent(self, key, quick, pg='1'):
        self._ensure_host()
        try:
            page = int(pg)
        except Exception:
            page = 1
        html = self._fetch(self._search_url(key, page))
        lst = self._parse_list(html)
        return {
            'list': lst,
            'page': page,
            'pagecount': 1,
        }

    def playerContent(self, flag, id, vipFlags):
        # detailContent 已经把 m3u8 直链放进 vod_play_url，直接播
        play_url = str(id or '')
        return {
            'parse': 0,
            'jx': 0,
            'playUrl': '',
            'url': play_url,
            'header': {
                'User-Agent': self.ua,
                'Referer': self.host + '/' if self.host else _ENTRY,
            },
        }

    def isVideoFormat(self, url):
        return '.m3u8' in str(url) or '.mp4' in str(url)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
