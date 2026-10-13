import requests
from bs4 import BeautifulSoup
import re
from base.spider import Spider
import sys
import json
import base64
import urllib.parse

sys.path.append('..')
# https://91sanji.com
xurl = "https://91sanji.com"
headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://91sanji.com/'
}

# 分类type_id -> 站点真实路径
# 注意分页规则不统一(实测):
#   聚合页 /category/            第2页是 /category/page/2/
#   子分类 /category/<slug>/     第2页是 /category/<slug>/2/  (写成 /page/2/ 会404)
#   AI页   /ai/drama/、/ai/comic/ 第2页是 /ai/drama/2/
cate_path = {
    "category": "/category/",
    "chinese-sex-movies": "/category/chinese-sex-movies/",
    "hong-kong-sex-movies": "/category/hong-kong-sex-movies/",
    "japanese-sex-movies": "/category/japanese-sex-movies/",
    "korean-sex-movies": "/category/korean-sex-movies/",
    "western-sex-movies": "/category/western-sex-movies/",
    "southeast-asian-sex-movies": "/category/southeast-asian-sex-movies/",
    "ai-drama": "/ai/drama/",
    "ai-comic": "/ai/comic/"
}

# ========== 封面解密相关 ==========
# 实测结论(推翻上一版的 og/cover 方案):
# 1) 站点 /og/cover/<任意路径> 是通配占位图,任何路径都返回同一张
#    1200x630、12593字节的图,不是真实封面,所以上一版没有封面。
# 2) 原图 data-enc-src(pic.wirqed.cn) 是 AES-CBC 加密的二进制,
#    密钥/IV 就写在站点每页的内联脚本里,浏览器也是解密后才显示的。
# 所以封面只能:vod_pic 给本地代理地址 -> localProxy 下载原图 -> 解密 -> 返回图片字节
IMG_KEY = b'f5d965df75336270'
IMG_IV = b'97b60394abc2fbe1'

try:
    from Crypto.Cipher import AES
except Exception:
    try:
        from Cryptodome.Cipher import AES
    except Exception:
        AES = None


def isImg(data):
    # 按文件头判断是不是真图片
    if not data or len(data) < 12:
        return False
    return (data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n'
            or data[:4] == b'GIF8' or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'))


def imgType(data):
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:4] == b'GIF8':
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'


_PURE_SBOX = None
_PURE_INV_SBOX = None


def _gmul(a, b):
    p = 0
    for i in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _pure_tables():
    # 程序生成 S 盒,避免手抄 256 项表抄错
    global _PURE_SBOX, _PURE_INV_SBOX
    if _PURE_SBOX is not None:
        return _PURE_SBOX, _PURE_INV_SBOX
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x = _gmul(x, 3)
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    sbox = [0] * 256
    for i in range(256):
        inv = 0 if i == 0 else exp[255 - log[i]]
        s = inv
        for shift in (1, 2, 3, 4):
            s ^= ((inv << shift) | (inv >> (8 - shift))) & 0xFF
        sbox[i] = (s ^ 0x63) & 0xFF
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    _PURE_SBOX, _PURE_INV_SBOX = sbox, inv_sbox
    return sbox, inv_sbox


def _pure_aes_cbc_decrypt(data, key, iv):
    # 纯 Python AES-128-CBC 解密兜底(盒子环境没有 Crypto/cryptography 时用)
    sbox, inv_sbox = _pure_tables()
    inv_sbox_b = bytes(inv_sbox)
    # InvMixColumns 乘法表,避免逐位乘
    mul = {coef: [_gmul(i, coef) for i in range(256)] for coef in (9, 11, 13, 14)}
    # InvShiftRows 置换表:新state[4c+r] = 旧state[4*((c-r)%4)+r]
    perm = [4 * (((i // 4) - (i % 4)) % 4) + (i % 4) for i in range(16)]
    # 密钥扩展:44 个 4 字节字
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        temp = list(w[i - 1])
        if i % 4 == 0:
            temp = [sbox[temp[1]] ^ rcon, sbox[temp[2]], sbox[temp[3]], sbox[temp[0]]]
            rcon = _gmul(rcon, 2)
        w.append([w[i - 4][j] ^ temp[j] for j in range(4)])
    round_keys = []
    for r in range(11):
        rk = bytearray(16)
        for c in range(4):
            for row in range(4):
                rk[4 * c + row] = w[4 * r + c][row]
        round_keys.append(bytes(rk))

    def xor_key(state, rnd):
        return (int.from_bytes(state, 'big') ^ int.from_bytes(round_keys[rnd], 'big')).to_bytes(16, 'big')

    def decrypt_block(block, prev):
        state = xor_key(block, 10)
        for rnd in range(9, 0, -1):
            state = bytes(state[perm[i]] for i in range(16)).translate(inv_sbox_b)
            state = xor_key(state, rnd)
            old = state
            out = bytearray(16)
            for c in range(4):
                a0, a1, a2, a3 = old[4 * c], old[4 * c + 1], old[4 * c + 2], old[4 * c + 3]
                out[4 * c + 0] = mul[14][a0] ^ mul[11][a1] ^ mul[13][a2] ^ mul[9][a3]
                out[4 * c + 1] = mul[9][a0] ^ mul[14][a1] ^ mul[11][a2] ^ mul[13][a3]
                out[4 * c + 2] = mul[13][a0] ^ mul[9][a1] ^ mul[14][a2] ^ mul[11][a3]
                out[4 * c + 3] = mul[11][a0] ^ mul[13][a1] ^ mul[9][a2] ^ mul[14][a3]
            state = bytes(out)
        state = bytes(state[perm[i]] for i in range(16)).translate(inv_sbox_b)
        state = xor_key(state, 0)
        return (int.from_bytes(state, 'big') ^ int.from_bytes(prev, 'big')).to_bytes(16, 'big')

    out = bytearray()
    prev = iv
    for off in range(0, len(data), 16):
        block = data[off:off + 16]
        out.extend(decrypt_block(block, prev))
        prev = block
    return bytes(out)


def decryptImg(data):
    # AES-CBC 解密 + 去 PKCS7 填充;原图本身就是明文时原样返回
    if not data or isImg(data):
        return data
    if len(data) % 16 != 0:
        return data
    plain = None
    if AES is not None:
        try:
            plain = AES.new(IMG_KEY, AES.MODE_CBC, IMG_IV).decrypt(data)
        except Exception:
            plain = None
    if plain is None:
        # 兜底一:用 cryptography 库解密
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            decryptor = Cipher(algorithms.AES(IMG_KEY), modes.CBC(IMG_IV)).decryptor()
            plain = decryptor.update(data) + decryptor.finalize()
        except Exception:
            plain = None
    if plain is None or not plain:
        # 兜底二:纯 Python AES 解密
        try:
            plain = _pure_aes_cbc_decrypt(data, IMG_KEY, IMG_IV)
        except Exception:
            return data
    if plain:
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
    return plain if isImg(plain) else data


def getInitialData(soup):
    # 详情页/分集页页末 <script id="videoInitialData" type="application/json">
    # 一次包含 videoSrc(m3u8直链)、coverSrc、description 等,播放解析首选它
    tag = soup.select_one('script#videoInitialData')
    if tag:
        try:
            return json.loads(tag.get_text().strip())
        except Exception:
            pass
    return {}


class Spider(Spider):
    global xurl
    global headerx

    def getName(self):
        return "91三级片"

    def init(self, extend):
        self._img_cache = {}

    def isVideoFormat(self, url):
        pass

    # ---------- 封面处理 ----------
    def _proxyBase(self):
        # 基类提供的本地代理前缀,形如 proxy://do=py 或 http://127.0.0.1:9978/proxy?do=py
        if getattr(self, '_pb', None):
            return self._pb
        pb = 'proxy://do=py'
        try:
            try:
                pb = self.getProxyUrl(True)
            except TypeError:
                pb = self.getProxyUrl()
        except Exception:
            pass
        if not pb:
            pb = 'proxy://do=py'
        self._pb = pb
        return pb

    def getPic(self, raw):
        # 加密图(pic.wirqed.cn)转成本地代理地址,由 proxyImg 下载解密后出图
        # 原始地址含 auth_key 且会轮换,整个URL用 base64 编码传参,避免 & 和 ? 被拆坏
        if not raw:
            return ''
        raw = raw.strip()
        if 'pic.wirqed.cn' in raw:
            b64 = base64.urlsafe_b64encode(raw.encode('utf-8')).decode('utf-8')
            return f"{self._proxyBase()}&type=img&b64={urllib.parse.quote(b64)}"
        return raw

    def proxyImg(self, params):
        # localProxy 的图片分支:下载加密原图 -> 解密 -> 返回 [状态码, 类型, 字节]
        try:
            enc_url = ''
            if params.get('b64'):
                enc_url = base64.urlsafe_b64decode(params.get('b64').encode('utf-8')).decode('utf-8')
            elif params.get('url'):
                enc_url = urllib.parse.unquote(params.get('url'))
            if not enc_url:
                return [404, 'text/plain', b'no url']

            cache = getattr(self, '_img_cache', None)
            if cache is None:
                cache = self._img_cache = {}
            if enc_url in cache:
                body = cache[enc_url]
                return [200, imgType(body), body]

            data = requests.get(url=enc_url, headers=headerx, timeout=15).content
            body = decryptImg(data)
            if not isImg(body):
                return [404, 'text/plain', b'decrypt failed']
            # 首页同一封面会重复出现,简单缓存一份,最多留20张
            if len(cache) >= 20:
                cache.clear()
            cache[enc_url] = body
            return [200, imgType(body), body]
        except Exception:
            return [404, 'text/plain', b'error']

    # ---------- 列表解析 ----------
    def parseVideoCards(self, soup, scope=None):
        # 普通视频卡:首页分区、分类页、搜索页同构
        # <article class="video-card"><a class="video-card__cover" href="/video/xxx/">
        # <img data-enc-src="..."><span class="duration">1:03:00</span></a>
        # <h2/h3 class="video-card__heading"><a class="video-card__title">标题</a></h2></article>
        root = scope if scope is not None else soup
        videos = []
        for item in root.select('article.video-card'):
            cover_tag = item.select_one('a.video-card__cover') or item.select_one('a.video-card__title')
            if not cover_tag:
                continue
            detail_url = cover_tag.get('href', '')
            title_tag = item.select_one('a.video-card__title')
            title = title_tag.get_text().strip() if title_tag else ''
            if not title and cover_tag.get('aria-label'):
                title = re.sub(r'^播放《|》$', '', cover_tag.get('aria-label', ''))
            img = item.select_one('img')
            pic = ''
            if img:
                pic = self.getPic(img.get('data-enc-src', '') or img.get('data-src', '') or img.get('src', ''))
            subtitle_tag = item.select_one('span.duration')
            subtitle = subtitle_tag.get_text().strip() if subtitle_tag else ''
            videos.append({
                "vod_id": detail_url,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": subtitle
            })
        return videos

    def parseDramaCards(self, soup):
        # AI短剧/漫剧卡:首页AI分区、AI分类页使用,竖版海报
        # <a class="drama-card" href="/video/xxx/"><div class="drama-card__poster">
        # <img data-enc-src="..."><span class="drama-card__eps">连载中 · 1集</span></div>
        # <div class="drama-card__info"><h3>标题</h3></div></a>
        videos = []
        for item in soup.select('a.drama-card'):
            detail_url = item.get('href', '')
            title_tag = item.select_one('.drama-card__info h3') or item.select_one('h3')
            title = title_tag.get_text().strip() if title_tag else ''
            img = item.select_one('img')
            pic = ''
            if img:
                pic = self.getPic(img.get('data-enc-src', '') or img.get('data-src', '') or img.get('src', ''))
            eps_tag = item.select_one('.drama-card__eps')
            badge_tag = item.select_one('.drama-card__badge')
            subtitle = eps_tag.get_text().strip() if eps_tag else ''
            if badge_tag:
                subtitle = (badge_tag.get_text().strip() + ' ' + subtitle).strip()
            videos.append({
                "vod_id": detail_url,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": subtitle
            })
        return videos

    def homeContent(self, filter):
        # 分类配置,匹配站点头部导航:三级片电影6个子类 + AI成人短剧/漫剧
        class_items = [
            {"type_id": "category", "type_name": "最新上映"},
            {"type_id": "chinese-sex-movies", "type_name": "国产三级片"},
            {"type_id": "hong-kong-sex-movies", "type_name": "香港三级片"},
            {"type_id": "japanese-sex-movies", "type_name": "日本三级片"},
            {"type_id": "korean-sex-movies", "type_name": "韩国三级片"},
            {"type_id": "western-sex-movies", "type_name": "欧美三级片"},
            {"type_id": "southeast-asian-sex-movies", "type_name": "东南亚三级片"},
            {"type_id": "ai-drama", "type_name": "AI成人短剧"},
            {"type_id": "ai-comic", "type_name": "AI漫剧"}
        ]

        # 筛选配置:该站没有地区/年份筛选,列表页只有最新/最热排序
        sort_filter = [
            {"key": "by",
             "name": "排序",
             "value": [{"n": "最新", "v": "new"},
                       {"n": "最热", "v": "hot"}]}
        ]
        static_filters = {}
        for item in class_items:
            static_filters[item["type_id"]] = sort_filter

        return {
            "class": class_items,
            "filters": static_filters
        }

    def homeVideoContent(self):
        # 首页普通分区是 article.video-card,AI分区是 a.drama-card,两种都取
        resp = requests.get(url=xurl, headers=headerx, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")

        videos = self.parseVideoCards(soup)
        videos.extend(self.parseDramaCards(soup))

        result = {'list': videos}
        return result

    def categoryContent(self, cid, pg, filter, ext):
        page = int(pg) if pg else 1
        cateId = ext.get('cateId', cid) if ext else cid
        by = ext.get('by', '') if ext else ''

        base = cate_path.get(cateId, f"/category/{cateId}/")

        # 适配站点分类页URL规则,分页模板见文件头注释
        if page == 1:
            url = f"{xurl}{base}"
        elif cateId == "category":
            url = f"{xurl}{base}page/{page}/"
        else:
            url = f"{xurl}{base}{page}/"
        if by == 'hot':
            url = url + "?sort=hot"

        resp = requests.get(url, headers=headerx, timeout=10)
        soup = BeautifulSoup(resp.text, 'lxml')

        # 电影分类是 video-card,AI分类是 drama-card
        videos = self.parseVideoCards(soup)
        if not videos:
            videos = self.parseDramaCards(soup)

        # 分页器 nav.pager 里 label.pager__jump 带 data-pages(总页数)
        pagecount = 99
        jump_tag = soup.select_one('nav.pager label.pager__jump')
        if jump_tag and jump_tag.get('data-pages', '').isdigit():
            pagecount = int(jump_tag.get('data-pages'))
        # 列表计数 p.list-count 例:共 68 部影片
        total = 9999
        count_tag = soup.select_one('p.list-count')
        if count_tag:
            m = re.search(r'(\d+)', count_tag.get_text())
            if m:
                total = int(m.group(1))

        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = pagecount
        result['limit'] = 20
        result['total'] = total
        return result

        # 详情
    def detailContent(self, ids):
        did = ids[0]
        result = {}
        if 'http' not in did:
            did = xurl + did
        # 请求详情页
        源码 = BeautifulSoup(requests.get(url=did, headers=headerx, timeout=10).text, "lxml")
        data = getInitialData(源码)

        # 初始化VOD字典
        vod = {}

        # 视频ID
        vod["vod_id"] = did

        # ========== AI短剧/漫剧详情页(另一套模板) ==========
        if 源码.select_one('article.ai-detail-layout'):
            # 标题
            title_tag = 源码.select_one('h1')
            vod["vod_name"] = title_tag.get_text().strip() if title_tag else data.get('title', '')

            # 封面图(加密原图走本地代理解密,不要用 og:image,那是占位图)
            img = 源码.select_one('.ai-detail-cover img')
            if img:
                vod["vod_pic"] = self.getPic(img.get('data-enc-src', '') or img.get('data-src', '') or img.get('src', ''))
            else:
                vod["vod_pic"] = self.getPic(data.get('coverSrc', ''))

            # 资料:分类/主演/集数/更新时间,dt带冒号
            for dt, dd in zip(源码.select('.ai-detail-meta dt'), 源码.select('.ai-detail-meta dd')):
                key = dt.get_text().replace('：', '').replace(':', '').strip()
                value = dd.get_text().strip()
                if key == '主演':
                    vod["vod_actor"] = value
                elif key == '分类':
                    vod["vod_class"] = value
                elif key == '集数':
                    vod["vod_remarks"] = value

            # 简介
            content_tag = 源码.select_one('.ai-detail-synopsis p')
            vod["vod_content"] = content_tag.get_text().strip() if content_tag else data.get('description', '')

            # 选集:div.ep-grid a,链接形如 /video/<slug>/episode/1/
            klists = []
            for LB in 源码.select('div.ep-grid a'):
                播放标题 = LB.get_text().strip()
                播放链接 = LB.get('href', '')
                if 播放链接:
                    klists.append(f'第{播放标题}集${播放链接}')
            # 没有选集列表时用详情页的立即播放按钮兜底
            if not klists:
                btn = 源码.select_one('.ai-detail-actions a.btn-primary')
                if btn and btn.get('href'):
                    klists.append(f"第1集${btn.get('href')}")
            vod["vod_play_from"] = '91三级'
            vod["vod_play_url"] = '#'.join(klists)

            result = {'list': [vod]}
            return result

        # ========== 普通电影详情页 ==========
        # 标题
        title_tag = 源码.select_one('h1.detail-title')
        vod["vod_name"] = title_tag.get_text().strip() if title_tag else data.get('title', '')

        # 封面图:用 videoInitialData 的 coverSrc(加密原图,含当次auth_key)走本地代理解密
        # og:image 不要用:实测是全站统一的占位图
        vod["vod_pic"] = self.getPic(data.get('coverSrc', '') or data.get('posterSrc', ''))
        if not data.get('coverSrc') and not data.get('posterSrc'):
            # 兜底:body 的 data-history 属性里也带 cover
            body_tag = 源码.select_one('body')
            if body_tag and body_tag.get('data-history'):
                try:
                    history = json.loads(body_tag.get('data-history'))
                    vod["vod_pic"] = self.getPic(history.get('cover', ''))
                except Exception:
                    vod["vod_pic"] = ''

        # 影片信息:dl.detail-info-list 的 dt/dd 依次为 片长/播放量/导演/主演/类型/地区/年份
        for dt, dd in zip(源码.select('.detail-info-list dt'), 源码.select('.detail-info-list dd')):
            key = dt.get_text().strip()
            value = dd.get_text().strip()
            if key == '导演':
                vod["vod_director"] = value
            elif key == '主演':
                vod["vod_actor"] = value
            elif key == '类型':
                vod["vod_class"] = value
            elif key == '地区':
                vod["vod_area"] = value
            elif key == '年份':
                vod["vod_year"] = value
            elif key == '片长':
                vod["vod_remarks"] = value

        # 简介:div.detail-synopsis 内正文 + 折叠的续文,拼起来才是全文
        简介段落 = [p.get_text().strip() for p in 源码.select('.detail-synopsis .synopsis p')]
        vod["vod_content"] = ''.join(简介段落) if 简介段落 else data.get('description', '')

        # ========== 提取播放列表 ==========
        # 普通电影是单集,播放页就是详情页本身,playerContent 里再解析直链
        vod["vod_play_from"] = '91三级'
        vod["vod_play_url"] = f'正片${did}'

        result = {'list': [vod]}
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        play_page = id if 'http' in id else xurl + id
        try:
            # 第一步:解析播放页的 videoInitialData,取 videoSrc 即 m3u8 直链
            resp = requests.get(url=play_page, headers=headerx, timeout=10)
            源码 = BeautifulSoup(resp.text, "lxml")
            data = getInitialData(源码)
            url = data.get('videoSrc', '')
            # JSON没取到时,正则兜底找 m3u8
            if not url:
                m = re.search(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', resp.text)
                if m:
                    url = m.group(1).replace('\\/', '/')
            if not url:
                raise Exception('未取到直链')

            # 正则提取成功,使用直链播放
            result["parse"] = 0
            result["playUrl"] = ''
            result["url"] = url
            result["header"] = headerx

        except Exception:
            # 提取失败(直链过期或请求异常),使用嗅探播放
            result["parse"] = 1
            result["playUrl"] = ''
            result["url"] = play_page
            result["header"] = headerx
        return result

    def searchContentPage(self, key, quick, page):
        result = {}
        videos = []
        if not page:
            page = '1'
        # 该站搜索没有分页,第2页起直接返空,避免重复
        if page != '1':
            result = {'list': videos}
            result['page'] = page
            result['pagecount'] = 1
            result['limit'] = 20
            result['total'] = 0
            return result

        # 搜索走路径式URL:/search/<关键词>/ (?q= 会被站内脚本改写成这个)
        url = f'{xurl}/search/{urllib.parse.quote(key)}/'
        resp = requests.get(url=url, headers=headerx, timeout=10)
        源码 = BeautifulSoup(resp.text, "lxml")

        # 搜索结果限定在 .search-results 内,后面还有推荐区,不能全页取卡
        搜索区 = 源码.select_one('.search-results') or 源码
        # 关键词与标签同名时会跳到 /tag/<slug>/ 页,那种页面没有 .search-results,全页卡片即结果
        videos = self.parseVideoCards(源码, scope=搜索区)

        result = {'list': videos}
        result['page'] = page
        result['pagecount'] = 1
        result['limit'] = 20
        result['total'] = len(videos)
        return result

    def searchContent(self, key, quick, page='1'):
        return self.searchContentPage(key, quick, page)

    def localProxy(self, params):
        # type=img 是封面解密代理,见 proxyImg
        if params.get('type') == "img":
            return self.proxyImg(params)
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None


if __name__ == "__main__":
    spider = Spider()
    spider.init("")

    # 调用首页视频内容测试
    # result = spider.homeVideoContent()
    # print("首页视频内容测试结果：")
    # print(result)

    # 调用分类内容测试
    # category_result = spider.categoryContent("hong-kong-sex-movies", "2", {}, {})
    # print("\n分类内容测试结果：")
    # print(category_result)

    # 调用详情内容测试
    # detail_result = spider.detailContent(["/video/hanguosanj-12/"])
    # print("\n详情内容测试结果：")
    # print(detail_result)

    # 调用播放内容测试(AI多集换成详情页里的分集链接)
    # player_result = spider.playerContent("91三级", "/video/hanguosanj-12/", {})
    # print("\n播放内容测试结果：")
    # print(player_result)

    # 调用搜索内容测试
    # search_result = spider.searchContent("姨母", False)
    # print("\n搜索内容测试结果：")
    # print(search_result)
