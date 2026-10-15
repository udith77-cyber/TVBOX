# -*- coding: utf-8 -*-

import sys
import re
import json
import base64
from urllib.parse import quote, unquote

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


class Spider(BaseSpider):
    def getName(self):
        return '花都影视'

    def init(self, extend=''):
        self.host = 'https://8pbv.huadudm.net'
        self.ua = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Mobile Safari/537.36')
        self.header = {
            'User-Agent': self.ua,
            'Referer': self.host + '/',
        }
        # extend 可传 {"host": "https://新线路"} 覆盖
        try:
            if extend:
                ext = extend if isinstance(extend, dict) else json.loads(extend)
                if isinstance(ext, dict) and ext.get('host'):
                    self.host = str(ext['host']).rstrip('/')
                    self.header['Referer'] = self.host + '/'
        except Exception:
            pass
        self.classes = [
            {'type_id': '1', 'type_name': '中文字幕'},
            {'type_id': '8', 'type_name': '中字无码'},
            {'type_id': '6', 'type_name': '中字有码'},
            {'type_id': '2', 'type_name': '无字幕'},
            {'type_id': '9', 'type_name': '步兵无码'},
            {'type_id': '7', 'type_name': '骑兵有码'},
            {'type_id': '3', 'type_name': '国产'},
            {'type_id': '13', 'type_name': '糖心Vlog'},
            {'type_id': '11', 'type_name': '国产传媒'},
            {'type_id': '10', 'type_name': '国产精品'},
            {'type_id': '5', 'type_name': '动漫'},
            {'type_id': '14', 'type_name': '中字里番'},
            {'type_id': '15', 'type_name': '3D动漫'},
            {'type_id': '16', 'type_name': 'AI短剧'},
            {'type_id': '4', 'type_name': '欧美'},
            {'type_id': '12', 'type_name': '欧美中字'},
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
        s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
        s = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), s)
        s = re.sub(r'&nbsp;', ' ', s, flags=re.I)
        s = s.replace('&amp;', '&').replace('&quot;', '"')
        s = s.replace('&#39;', "'").replace('&apos;', "'")
        s = s.replace('&lt;', '<').replace('&gt;', '>')
        s = re.sub(r'<[^>]+>', '', s)
        return re.sub(r'\s+', ' ', s).strip()

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
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.read().decode('utf-8', errors='ignore')
                r = requests.get(url, headers=self.header, timeout=10)
                return r.content.decode('utf-8', errors='ignore') if r.content else ''
            except Exception:
                return ''
        html = _once()
        if not html or len(html) < 3000:
            html = _once()  # 该站偶发返回空页面（白屏），重试一次
        return html

    def _is_blocked(self, html):
        return (not html) or ('滑动验证' in html and 'stui-vodlist' not in html)

    def _parse_list(self, html):
        result = []
        seen = set()
        if not html:
            return result
        # 卡片 <a> 的属性顺序可能变化：先按 class 名识别卡片，再单独取 href/title
        for m in re.finditer(r'<a\b([^>]*)>([\s\S]*?)</a>', html):
            attrs, body = m.group(1), m.group(2)
            if 'stui-vodlist__thumb' not in attrs:
                continue
            hm = re.search(r'href="([^"]+)"', attrs)
            if not hm or '/voddetail/' not in hm.group(1):
                continue
            idm = re.search(r'/voddetail/(\d+)\.html', hm.group(1))
            vid = idm.group(1) if idm else hm.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            tm = re.search(r'title="([^"]*)"', attrs)
            name = self._clean(tm.group(1)) if tm else vid
            picm = re.search(r'data-original="([^"]+)"', body)
            pic = self._abs(picm.group(1)) if picm else ''
            if 'load.gif' in pic:
                pic = ''

            def tag(cls):
                tm2 = re.search(r'pic-tag-' + cls + r'\b[^>]*>([\s\S]*?)</span>', body)
                return self._clean(tm2.group(1)) if tm2 else ''

            remarks = ' · '.join(x for x in (tag('t'), tag('b'), tag('l')) if x)
            result.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        return result

    def _decode_play_url(self, raw, enc):
        """player_data.url 解码。实测 encrypt=2 时是 escape 编码再把 % 换成 JT；
        兼容 base64 与明文，按候选逐个验证 http(s) 开头。"""
        cands = []
        raw = (raw or '').strip().replace('\\/', '/')
        if 'JT' in raw:
            cands.append(unquote(raw.replace('JT', '%')))
        s = re.sub(r'[^A-Za-z0-9+/=]', '', raw)
        if len(s) >= 8:
            try:
                s += '=' * (-len(s) % 4)
                cands.append(base64.b64decode(s).decode('utf-8', errors='ignore'))
            except Exception:
                pass
        cands.append(unquote(raw))
        for c in cands:
            c = (c or '').strip()
            if re.match(r'^https?://', c):
                return c
        return ''

    # ---------------- TVBox 接口 ----------------

    def homeContent(self, filter):
        return {'class': self.classes, 'filters': {}}

    def homeVideoContent(self):
        return self.categoryContent('1', '1', False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        url = f'{self.host}/vodshow/{tid or "1"}--------{page}---.html'
        html = self._fetch(url)
        if self._is_blocked(html):
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}
        lst = self._parse_list(html)
        return {
            'list': lst,
            'page': page,
            'pagecount': 9999,
            'limit': len(lst) if lst else 90,
            'total': 999999,
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        m = re.search(r'(\d+)', vid)
        real_id = m.group(1) if m else vid
        url = f'{self.host}/voddetail/{real_id}.html'
        html = self._fetch(url)
        if self._is_blocked(html):
            return {'list': []}

        fields = {}
        for fm in re.finditer(
            r'<div[^>]*class="[^"]*detail-item[^"]*"[^>]*>\s*'
            r'<strong[^>]*>([\s\S]*?)</strong>\s*'
            r'<span[^>]*class="[^"]*detail-content[^"]*"[^>]*>([\s\S]*?)</span>\s*</div>',
            html,
        ):
            key = re.sub(r'[:：]$', '', self._clean(fm.group(1)))
            fields[key] = self._clean(fm.group(2))

        picm = re.search(r'data-original="([^"]+)"', html)
        pic = self._abs(picm.group(1)) if picm else ''
        if 'load.gif' in pic:
            pic = ''

        eps = []
        pm = re.search(r'/vodplay/\d+-\d+-\d+\.html', html)
        if pm:
            play_html = self._fetch(self._abs(pm.group(0)))
            seen = set()
            for um in re.finditer(
                r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>', play_html
            ):
                for am in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', um.group(1)):
                    ep_url = self._abs(am.group(1))
                    if ep_url in seen:
                        continue
                    seen.add(ep_url)
                    name = self._clean(am.group(2)) or f'第{len(eps) + 1}集'
                    eps.append(f'{name}${ep_url}')
            if not eps:
                eps = [f'第1集${self._abs(pm.group(0))}']

        vod = {
            'vod_id': vid,
            'vod_name': fields.get('名称', ''),
            'type_name': fields.get('分类', ''),
            'vod_year': (fields.get('日期', '') or '')[:4],
            'vod_area': '',
            'vod_remarks': ' · '.join(
                x for x in (fields.get('分类', ''), fields.get('日期', ''), fields.get('时长', '')) if x
            ),
            'vod_actor': fields.get('演员', ''),
            'vod_director': '',
            'vod_pic': pic,
            'vod_content': '\n'.join(
                x for x in (fields.get('标题', ''),
                            ('类别：' + fields['类别']) if fields.get('类别') else '') if x
            ),
            'vod_play_from': '花都',
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
        try:
            page = int(pg)
        except Exception:
            page = 1
        html = self._fetch(self._search_url(key, page))
        if self._is_blocked(html):
            return {'list': [], 'page': page, 'pagecount': page}
        return {'list': self._parse_list(html), 'page': page, 'pagecount': 1}

    def playerContent(self, flag, id, vipFlags):
        play_url = self._abs(id)
        try:
            html = self._fetch(play_url)
            idx = html.find('player_data')
            seg = html[idx:idx + 8000] if idx > -1 else html
            um = re.search(r'"url"\s*:\s*"([^"]*)"', seg)
            if not um or not um.group(1):
                return {'parse': 1, 'jx': 1, 'playUrl': '', 'url': play_url, 'header': self.header}
            em = re.search(r'"encrypt"\s*:\s*(\d+)', seg)
            enc = em.group(1) if em else '0'
            direct = self._decode_play_url(um.group(1), enc)
            if direct:
                return {
                    'parse': 0,
                    'jx': 0,
                    'playUrl': '',
                    'url': direct,
                    'header': {
                        'User-Agent': self.ua,
                        'Referer': self.host + '/',
                    },
                }
            return {'parse': 1, 'jx': 1, 'playUrl': '', 'url': play_url, 'header': self.header}
        except Exception:
            return {'parse': 1, 'jx': 1, 'playUrl': '', 'url': play_url, 'header': self.header}

    def localProxy(self, param):
        return None

    def isVideoFormat(self, url):
        return '.m3u8' in str(url) or '.mp4' in str(url)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
