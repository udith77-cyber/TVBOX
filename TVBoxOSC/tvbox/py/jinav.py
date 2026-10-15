# -*- coding: utf-8 -*-

import re
import json
import html as html_lib
from urllib.parse import quote, urlparse, urljoin, unquote, urlsplit, urlunsplit
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    name = '金AV'
    # 发布入口（用户提供）
    PUBLISH_URLS = [
        'https://y5z6a7b8.jinav1.cc/topic/',
        'https://y5z6a7b8.jinav1.cc/',
    ]
    # 在导航 JSON 里定位本站的标题关键词
    SITE_KEYWORDS = ['全网封禁AV']
    # 导航站数据接口（拾光驿站）：GET + X-Requested-With 头返回 {"urls": [...]}
    NAV_API = '/xuexi/data.php'
    # 兜底候选（带路径：站点的真实入口是 /暖阳/，根路径是拦截页）
    DOMAINS = [
        'https://9kwe2r.jinav2.com/暖阳',
    ]
    # 网关 cloak 页里的每日发布域名映射（按"日"取子域名，jinav1/2/3 轮换，.cc 后缀）
    # 2026-10-07 从网关 JS 提取；若失效，以 PUBLISH_URLS 为准
    CLOAK_MAPPING = {
        1: "a1b2c3d4", 2: "e5f6g7h8", 3: "i9j0k1l2", 4: "m3n4o5p6", 5: "q7r8s9t0",
        6: "u1v2w3x4", 7: "y5z6A7B8", 8: "C9D0E1F2", 9: "G3H4I5J6", 10: "K7L8M9N0",
        11: "O1P2Q3R4", 12: "S5T6U7V8", 13: "W9X0Y1Z2", 14: "a3b4c5d6", 15: "e7f8g9h0",
        16: "i1j2k3l4", 17: "m5n6o7p8", 18: "q9r0s1t2", 19: "u3v4w5x6", 20: "y7z8A9B0",
        21: "C1D2E3F4", 22: "G5H6I7J8", 23: "K9L0M1N2", 24: "O3P4Q5R6", 25: "S7T8U9V0",
        26: "W1X2Y3Z4", 27: "a5b6c7d8", 28: "e9f0g1h2", 29: "i3j4k5l6", 30: "m7n8o9p0",
        31: "q1r2s3t4",
    }
    # 真实分类兜底（2026-10-07 从首页 HTML 解码，45 个；抓取失败时用）
    FALLBACK_CLASSES = [
        ("6", "麻豆视频"), ("7", "91制片厂"), ("8", "天美传媒"), ("9", "蜜桃传媒"),
        ("10", "皇家华人"), ("11", "星空传媒"), ("12", "精东影业"), ("20", "乐播传媒"),
        ("57", "兔子先生"), ("21", "杏吧原创"), ("22", "糖心Vlog"), ("24", "玩偶姐姐"),
        ("25", "mini传媒"), ("26", "大象传媒"), ("30", "成人头条"), ("31", "乌鸦传媒"),
        ("60", "国产精品"), ("61", "华语AV"), ("62", "黑料吃瓜"), ("63", "学生合集"),
        ("64", "乱伦精品"), ("65", "探芽约炮"), ("66", "日本无码"), ("67", "主播网红"),
        ("37", "国产自拍"), ("32", "强奸乱伦"), ("33", "女优明星"), ("34", "欧美激情"),
        ("28", "重口激情"), ("29", "三级伦理"), ("35", "剧情动漫"), ("15", "SM调教"),
        ("70", "女同性恋"), ("71", "日韩无码"), ("72", "网曝吃瓜"), ("73", "探芽约炮"),
        ("74", "偷拍偷窥"), ("75", "日韩主播"), ("76", "中文字幕"), ("77", "主播诱惑"),
        ("79", "传媒剧情"), ("80", "抖阴短片"), ("81", "AV解说"), ("82", "换脸明星"),
        ("83", "VR视角"),
    ]
    base_url = DOMAINS[0]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36',
    }

    def getName(self):
        return self.name

    def init(self, extend=''):
        import requests
        self._s = requests.Session()
        self._s.headers.update(self.headers)
        try:
            if extend:
                cfg = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(cfg, dict):
                    if cfg.get('host'):
                        h = cfg['host'].rstrip('/')
                        if h not in self.DOMAINS:
                            self.DOMAINS.insert(0, h)
                    if cfg.get('publish'):
                        pubs = cfg['publish']
                        if isinstance(pubs, str):
                            pubs = [p.strip() for p in re.split(r'[,\s]+', pubs) if p.strip()]
                        for p in pubs:
                            p = p.rstrip('/')
                            if p and p not in self.PUBLISH_URLS:
                                self.PUBLISH_URLS.insert(0, p)
        except Exception:
            pass
        self._resolve_publish()
        self._pick_domain()
        return

    def destroy(self):
        pass

    # ============ 域名解析 ============

    @staticmethod
    def _origin(u):
        try:
            p = urlparse(u or '')
            if p.scheme and p.netloc:
                return '%s://%s' % (p.scheme, p.netloc)
        except Exception:
            pass
        return ''

    @staticmethod
    def _site_base(u):
        """站点 base：保留路径（如 /暖阳/），只去尾部斜杠"""
        try:
            p = urlparse(u or '')
            if p.scheme and p.netloc:
                return ('%s://%s%s' % (p.scheme, p.netloc, p.path or '')).rstrip('/')
        except Exception:
            pass
        return ''

    def _is_site_domain(self, u):
        try:
            host = urlparse(u or '').netloc
            return bool(re.match(r'^[a-z0-9-]+\.jinav\d*\.[a-z]+$', host, re.I))
        except Exception:
            return False

    @classmethod
    def _today_publish_urls(cls):
        """按日期算出今日发布页候选（jinav1/2/3 都试，取自网关 cloak 页的映射表）"""
        import datetime
        sub = cls.CLOAK_MAPPING.get(datetime.datetime.now().day, '')
        if not sub:
            return []
        return ['https://%s.jinav%d.cc/topic/' % (sub, i) for i in (1, 2, 3)]

    def _resolve_publish(self):
        """从发布页跳转链解析最新域名，插到候选最前面。
        链路：发布入口（含按日期算出的今日发布页） → (302/JS 跳转，可多层嵌套 ? + URL) → 导航站 JSON → 本站 URL"""
        urls = list(getattr(self, 'PUBLISH_URLS', None) or [])
        for pu in self._today_publish_urls():
            if pu not in urls:
                urls.insert(0, pu)
        if not urls:
            return
        found = []
        seen = set()

        def _walk(u, depth):
            if depth > 3 or not u or u in seen or len(found) >= 3:
                return
            seen.add(u)
            try:
                r = self._s.get(self._safe_url(u), timeout=15)
            except Exception:
                return
            origin = self._origin(r.url)
            base = self._site_base(r.url)
            # 只有真正发生跳转（最终 base 与入口不同）且符合站点域名才采纳；保留路径
            if base != self._site_base(u) and self._is_site_domain(base):
                if base not in found and base not in self.DOMAINS:
                    found.append(base)
                return
            h = r.text or ''
            # 1) 导航 JSON 接口：本站点 URL 藏在 urls 数组里（保留路径）
            try:
                rr = self._s.get(origin + self.NAV_API, timeout=15,
                                 headers={'X-Requested-With': 'XMLHttpRequest'})
                data = rr.json()
                for item in data.get('urls', []):
                    t = item.get('title', '')
                    if any(k in t for k in self.SITE_KEYWORDS):
                        su = self._site_base(item.get('url', ''))
                        if su and su not in found and su not in self.DOMAINS:
                            found.append(su)
                if found:
                    return
            except Exception:
                pass
            # 2) ? + URL 嵌套跳转（如 /topic/?https://下一跳/...）：扫最终 URL 和页面
            for src in (r.url or '', h):
                for m in re.finditer(r'\?(https?://[^?\s<>"\']+)', src):
                    _walk(m.group(1), depth + 1)
                    if found:
                        return
            # 3) JS 跳转入口：urlList=["topic/",...] / ul=[...] / a.link
            entries = []
            for m in re.finditer(r'(?:urlList|\bul\b)\s*=\s*\[([^\]]*)\]', h):
                entries += re.findall(r'["\']([^"\']+)["\']', m.group(1))
            if not entries:
                entries = re.findall(r'<a[^>]*class="[^"]*\blink\b[^"]*"[^>]*href="([^"]+)"', h, re.I)
            for e in entries:
                for _t in ('开火车go', '开动车go', '开飞机go', '世界和平，人民幸福'):
                    e = e.replace(_t, '')
                if not e or e.startswith(('javascript:', '#')):
                    continue
                target = e if e.startswith('http') else urljoin(r.url, e)
                _walk(target, depth + 1)
                if found:
                    return

        for pu in urls:
            _walk(pu, 0)
            if found:
                break
        for d in reversed(found):
            self.DOMAINS.insert(0, d)

    def _pick_domain(self):
        for d in self.DOMAINS:
            try:
                self.base_url = d
                self._s.headers['Referer'] = self._safe_url(d + '/')
                h = self._fetch(d + '/')
                if h and len(h) > 3000 and 'videoBox' in h:
                    return
            except Exception:
                continue
        self.base_url = self.DOMAINS[0]

    def _fetch(self, url):
        try:
            r = self._s.get(self._safe_url(url), timeout=15)
            raw_len = len(r.content or b'')
            h = self._decode(r)
            # JS cookie 验证可能有多轮：循环设 cookie 重抓，直到拿到正常页或达到上限
            for _ in range(3):
                if not (len(h) < 3000 and 'document.cookie' in h
                        and re.search(r'location\.reload|validator|验证', h, re.I)):
                    break
                for cm in re.finditer(
                        r'''document\.cookie\s*=\s*["']([^;"']+;?[^"']*)["']''', h):
                    kv = cm.group(1).split(';')[0].strip()
                    if '=' in kv:
                        k, v = kv.split('=', 1)
                        k, v = k.strip(), v.strip()
                        if k and 'distinctid' not in k.lower() and 'cnzz' not in k.lower():
                            try:
                                self._s.cookies.set(k, v, domain=urlparse(r.url).hostname, path='/')
                            except Exception:
                                pass
                try:
                    r = self._s.get(self._safe_url(url), timeout=15)
                except Exception:
                    break
                if r.status_code != 200:
                    break
                h = self._decode(r)
                if len(r.content or b'') <= raw_len:
                    break
                raw_len = len(r.content or b'')
            return h
        except Exception:
            return ''

    @staticmethod
    def _decode(r):
        """中文站常不带 charset 头，requests 会按 latin-1 解出乱码；优先按 utf-8 解。"""
        try:
            ct = (r.headers.get('content-type') or '').lower()
            if 'charset' not in ct:
                return r.content.decode('utf-8')
        except Exception:
            pass
        return r.text or ''

    @staticmethod
    def _safe_url(url):
        """把 URL 的 path/query 做 percent 编码。
        旧版 requests 遇到中文路径会抛 UnicodeEncodeError(latin-1)，
        这里先行编码，行为与浏览器地址栏一致。"""
        try:
            p = urlsplit(url or '')
            if not p.scheme or not p.netloc:
                return url
            # 先 unquote 再 quote：原始中文和已编码形式都归一化，避免二次编码
            return urlunsplit((p.scheme, p.netloc,
                               quote(unquote(p.path or '/'), safe='/'),
                               quote(unquote(p.query or ''), safe='=&'),
                               p.fragment))
        except Exception:
            return url

    # ============ 解析 ============

    def _abs_url(self, u):
        """按浏览器规则解析站内相对链接（HTML 里是根路径相对，如 /voddetail/ID.html）"""
        if not u:
            return ''
        return urljoin(self.base_url + '/', u)

    def _parse_list(self, h):
        """卡片：a.videoBox[href=/voddetail/ID.html] + div.videoBox-cover background-image + span.title（实体编码）"""
        vods = []
        for m in re.finditer(
                r'<a[^>]*href="(/voddetail/(\d+)\.html)"[^>]*class="videoBox".*?'
                r'background-image:\s*url\(([^)]+)\).*?'
                r'<span class="title">(.*?)</span>',
                h, re.S):
            href, vid, pic, title = m.group(1), m.group(2), m.group(3).strip('\'" '), m.group(4)
            name = html_lib.unescape(re.sub(r'<.*?>', '', title)).strip()
            if not name:
                continue
            vods.append({'vod_id': vid, 'vod_name': name,
                         'vod_pic': self._abs_url(pic), 'vod_remarks': ''})
        seen, out = set(), []
        for v in vods:
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                out.append(v)
        return out

    def homeContent(self, filter=False):
        h = self._fetch(self.base_url + '/')
        classes = []
        # 本站真实分类：a[name=lmclick][href=/vodtype/N.html]；data-id 的外链（别的站）不要
        for m in re.finditer(
                r'<a[^>]*name="lmclick"[^>]*href="(/vodtype/(\d+)\.html)"[^>]*>(.*?)</a>', h, re.S):
            tid, name = m.group(2), html_lib.unescape(re.sub(r'<.*?>', '', m.group(3))).strip()
            if name:
                classes.append({'type_id': tid, 'type_name': name})
        if not classes:
            classes = [{'type_id': t, 'type_name': n} for t, n in self.FALLBACK_CLASSES]
        return {'class': classes}

    def homeVideoContent(self):
        return {'list': self._parse_list(self._fetch(self.base_url + '/'))}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = re.search(r'(\d+)', str(tid)).group(1)
        url = self._abs_url('/vodtype/%s.html' % tid) if pg <= 1 else \
            self._abs_url('/vodtype/%s-%d.html' % (tid, pg))
        h = self._fetch(url)
        return {'list': self._parse_list(h), 'page': pg, 'pagecount': 9999,
                'limit': 24, 'total': 9999}

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, list) else ids
        vid = re.search(r'(\d+)', str(raw)).group(1)
        h = self._fetch(self._abs_url('/voddetail/%s.html' % vid))
        # 标题：h1.video-title（实体编码）
        name = ''
        m = re.search(r'<h1[^>]*class="video-title"[^>]*>(.*?)</h1>', h, re.S) or \
            re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        if m:
            name = html_lib.unescape(re.sub(r'<.*?>', '', m.group(1))).strip()
        if not name:
            m = re.search(r'<title>(.*?)</title>', h, re.S)
            if m:
                name = html_lib.unescape(re.sub(r'<.*?>', '', m.group(1))).strip()
                name = re.sub(r'(详情介绍|在线观看|迅雷下载).*$', '', name).strip(' -_')
        # 封面：img 的 data-original（真实封面，src 可能是占位图）
        pic = ''
        m = re.search(r'<img[^>]*data-original="([^"]+)"', h) or \
            re.search(r'<meta property="og:image" content="([^"]+)"', h)
        if m:
            pic = self._abs_url(m.group(1))
        # 简介：meta description 里“剧情:”后面部分
        content = ''
        m = re.search(r'<meta name="description" content="[^"]*?剧情[:：]([^"]*)"', h)
        if m:
            content = html_lib.unescape(m.group(1)).strip()
        # 播放：a[href=/vodplay/VID-线路-集数.html]，按钮文本即选集名；
        # 包着 img 的无文本 a 跳过（不造“第N集”），按 URL 去重
        eps_by_line = {}
        for m in re.finditer(r'<a[^>]*href="/vodplay/%s-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>' % vid, h, re.S):
            line, ep = m.group(1), m.group(2)
            ep_name = html_lib.unescape(re.sub(r'<.*?>', '', m.group(3))).strip()
            if not ep_name:
                continue
            u = self._abs_url('/vodplay/%s-%s-%s.html' % (vid, line, ep))
            lst = eps_by_line.setdefault('线路%s' % line, [])
            if not any(x.endswith('$' + u) for x in lst):
                lst.append('%s$%s' % (ep_name, u))
        if len(eps_by_line) == 1:
            only = next(iter(eps_by_line.values()))
            if len(only) == 1:
                # 单集：from 直接叫在线播放
                play_from, play_url = ['在线播放'], [only[0]]
            else:
                play_from, play_url = ['在线播放'], ['#'.join(only)]
        else:
            play_from = sorted(eps_by_line.keys())
            play_url = ['#'.join(eps_by_line[k]) for k in play_from]
        vod = {
            'vod_id': vid,
            'vod_name': name or '视频',
            'vod_pic': pic,
            'vod_content': content or name,
            'vod_play_from': '$$$'.join(play_from) or '在线播放',
            'vod_play_url': '$$$'.join(play_url),
        }
        return {'list': [vod]}

    def searchContent(self, key, quick=None, pg='1'):
        pg = int(pg) if str(pg).isdigit() else 1
        wd = quote(key)
        url = self._abs_url('/vodsearch/-------------.html?wd=%s' % wd)
        if pg > 1:
            url += '&p=%d' % pg
        return {'list': self._parse_list(self._fetch(url)), 'page': pg,
                'pagecount': 9999, 'limit': 24, 'total': 9999}

    def playerContent(self, flag, id, vipFlags=None):
        u = self._abs_url(id)
        if re.search(r'\.m3u8(\?|$)', u, re.I):
            return {'parse': 0, 'url': u, 'header': self.headers}
        h = self._fetch(u)
        # MacCMS 标准：var player_aaaa={"url":"%68%74...","encrypt":1,...}，url 是 percent 编码
        m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', h, re.S) or \
            re.search(r'var\s+player_data\s*=\s*(\{.*?\})', h, re.S)
        if m:
            try:
                pd = json.loads(m.group(1))
                pu = unquote(pd.get('url', '') or '')
                if pu.startswith('//'):
                    pu = 'https:' + pu
                if pu:
                    return {'parse': 0 if re.search(r'\.m3u8(\?|$)', pu, re.I) else 1,
                            'url': pu, 'header': self.headers}
            except Exception:
                pass
        m = re.search(r'"(https?://[^"]+?\.m3u8[^"]*)"', h) or \
            re.search(r'src="(https?://[^"]+?\.m3u8[^"]*)"', h)
        if m:
            return {'parse': 0, 'url': m.group(1).replace('\\/', '/'), 'header': self.headers}
        m = re.search(r'<iframe[^>]+src="([^"]+)"', h, re.I)
        if m:
            return {'parse': 1, 'url': self._abs_url(m.group(1)), 'header': self.headers}
        return {'parse': 1, 'url': u, 'header': self.headers}

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv)(\?|$)', url or '', re.I))

    def localProxy(self, param):
        return None
