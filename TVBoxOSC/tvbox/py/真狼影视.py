# -*- coding: utf-8 -*-
"""
真狼影视 (https://zlys7.top/) 爬虫源
OK影视 / TVBox 系列 Python 源 —— 按「遮天法」框架风格实现

方法体系（九秘）:
  兵字秘 BingZiMi : 万法解密（AES-GCM / Base64，多后端自动降级）
  斗字秘 DouZiMi : 实战解析（RSC 数据提取 / 分类页正则 / 文本清洗）
  者字秘 ZheZiMi : 不死之身（安全调用 / 安全取值 / 指数退避重试）
  行字秘 XingZiMi : 身法（随机 UA / 限速）
  皆字秘 JieZiMi : m3u8 净世（广告清洗 / 相对路径转绝对）

站点特性:
  1. WAF 403 挑战: 新 Session 首次请求 HTML 得 403 并下发会话 cookie,
     带 cookie 后同 Session 即可 200, init() 中自动完成"碰壁"。
  2. 列表/详情: 走 Next.js RSC 数据与 /category/{tid}/filter?page=N 分页 HTML。
  3. 搜索/播放解析: 走站点加密 API (AES-256-GCM):
     GET /api/crypto/handshake -> {"token","key","expiresAt"}
     后续请求带请求头 X-Enc-Token: <token>; 响应 {"enc":"1","data":"<b64>"}
     密文: raw=b64decode(data); iv=raw[:12]; tag=raw[12:28]; ct=raw[28:];
     用 AES-256-GCM(key) 解密 (verify 时 tag 拼到 ct 尾部)。
"""

import re
import json
import time
import base64
import random
import threading

try:
    from urllib.parse import quote, unquote
except ImportError:
    from urllib import quote, unquote

# ── 并发检测 (失效检测加速用; 缺失时串行兜底) ──
try:
    from concurrent.futures import ThreadPoolExecutor
    HAS_THREADPOOL = True
except ImportError:
    HAS_THREADPOOL = False

# ── 基类导入（兼容 OK影视/TVBox 环境，缺失时兜底）──
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        """TVBox环境缺失时的兜底基类"""
        pass

# ── HTTP 请求库（优雅降级）──
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None

# ── 加密库（优雅降级：pycryptodome -> cryptography -> 纯Python）──
try:
    from Crypto.Cipher import AES as _CryptoAES
    HAS_CRYPTO = True
except ImportError:
    _CryptoAES = None
    HAS_CRYPTO = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _CRYPTOGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    _CRYPTOGCM = None
    HAS_CRYPTOGRAPHY = False

# ═══════════════════════════════════════════════════════════════
#  大帝配置中心
# ═══════════════════════════════════════════════════════════════

siteName = "真狼影视"
siteUrl = "https://zlys7.top/"

DEFAULT_CONFIG = {
    "name": "真狼影视",
    "host": siteUrl,
    "debug": False,
    "timeout": 15,
    "ua_pool": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    ],
    "fallback_classes": [
        {"type_id": "movie", "type_name": "电影"},
        {"type_id": "tv", "type_name": "电视剧"},
        {"type_id": "variety", "type_name": "综艺"},
        {"type_id": "anime", "type_name": "动漫"},
        {"type_id": "children", "type_name": "儿童"},
    ],
    # 搜索返回 cat 数字 -> 详情页 bucket
    "cat_bucket": {"1": "movie", "2": "tv", "3": "variety", "4": "anime"},
    # 线路代码 -> 播放器显示名
    "site_names": {
        "qiyi": "爱奇艺", "iqiyi": "爱奇艺", "youku": "优酷", "bilibili1": "哔哩哔哩",
        "imgo": "芒果TV", "mgtv": "芒果TV", "leshi": "乐视", "qq": "腾讯视频",
        "sohu": "搜狐视频", "pptv": "PPTV", "1905": "1905电影网",
    },
    # 站点 /parse 内置第三方解析站 (resolve 兜底, WebView parse=1)
    "parse_sites": [
        {"name": "解析站1", "apiUrl": "https://jx.202617.xyz/tv.php?url=", "enabled": True},
        {"name": "解析站2(有ad)", "apiUrl": "https://jx.xmflv.com/?url=", "enabled": True},
    ],
    # 网盘线路: /api/search/pan 公开搜索分享链接, playerContent push:// 推送
    "pan": {
        "enabled": True,          # False 则详情不挂网盘线路
        "pan_type": "0",          # /api/pan-types 当前仅 [0] (夸克)
        "mode": "exact",          # exact / fuzzy / segmented
        "max_items": 8,           # 每条详情最多挂几个网盘资源
        "verify": True,           # 详情构建时调 /api/verify-link 检测分享链接有效性
        "verify_ttl": 1800,       # 检测结果 URL 级缓存秒 (与 pan 搜索缓存一致)
        "verify_url": "api/verify-link",   # 失效检测接口 (网页同款: ok=true 有效)
        "site_name": "网盘",      # 未识别网盘类型的兜底线路名
        # 域名关键字 -> 网盘线路显示名 (顺序匹配, 先命中先得)
        "name_rules": [
            {"kw": "pan.quark.cn", "name": "夸克网盘"},
            {"kw": "baidu", "name": "百度网盘"},
            {"kw": "alipan", "name": "阿里云盘"},
            {"kw": "aliyundrive", "name": "阿里云盘"},
            {"kw": "xunlei", "name": "迅雷网盘"},
            {"kw": "123684", "name": "123云盘"},
            {"kw": "123pan", "name": "123云盘"},
            {"kw": "caiyun", "name": "移动彩云"},
            {"kw": "189.cn", "name": "天翼云盘"},
            {"kw": "115.com", "name": "115网盘"},
            {"kw": "lanzou", "name": "蓝奏云"},
            {"kw": "lanzn", "name": "蓝奏云"},
            {"kw": "wo.cn", "name": "沃云盘"},
            {"kw": "uc.cn", "name": "UC网盘"},
            {"kw": "guangya", "name": "光鸭网盘"},
        ],
        # 命中这些域名的 id 不走站点 resolve, 直接 push:// 推送
        "hosts": [
            "pan.quark.cn", "pan.baidu.com", "aliyundrive.com", "aliyundrive.net",
            "alipan.com", "pan.xunlei.com", "pan.123684.com", "123pan.com",
            "pan.hikvision.com", "caiyun", "caiyun.139.com", "cloud.189.cn",
            "115.com", "pan.wo.cn", "pan.uc.cn", "guangya", "lanzou", "lanzn",
        ],
    },
}

# ═══════════════════════════════════════════════════════════════
#  第一章：行字秘 · 身法（UA/限速）
# ═══════════════════════════════════════════════════════════════

class XingZiMi:
    """行字秘·身法：随机设备指纹、请求节奏"""

    @staticmethod
    def random_ua(config=None) -> str:
        cfg = config or DEFAULT_CONFIG
        pool = cfg.get("ua_pool") or DEFAULT_CONFIG["ua_pool"]
        return random.choice(pool) if pool else DEFAULT_CONFIG["ua_pool"][0]

    @staticmethod
    def random_delay(lo=0.0, hi=0.5):
        time.sleep(random.uniform(lo, hi))


# ═══════════════════════════════════════════════════════════════
#  第二章：兵字秘 · 万法解密
# ═══════════════════════════════════════════════════════════════

class BingZiMi:
    """兵字秘·万法解密引擎（真狼影视 AES-256-GCM）"""

    @staticmethod
    def base64_decode(data):
        """诛仙剑·Base64解码"""
        try:
            return base64.b64decode(data).decode("utf-8")
        except Exception:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8")
            except Exception:
                return None

    @staticmethod
    def _aes_gcm_decrypt_py(key, iv, ct):
        """戮仙剑·纯Python AES-GCM 解密（不验tag，仅解出明文）"""
        # FIPS-197 S-box
        SBOX = [
            0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
            0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
            0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
            0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
            0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
            0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
            0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
            0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
            0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
            0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
            0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
            0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
            0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
            0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
            0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
            0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
        ]

        def _xtime(a):
            a <<= 1
            if a & 0x100:
                a ^= 0x11B
            return a & 0xFF

        def _expand_key(key):
            nk = len(key) // 4
            nr = {4: 10, 6: 12, 8: 14}[nk]
            w = [[key[4 * i], key[4 * i + 1], key[4 * i + 2], key[4 * i + 3]] for i in range(nk)]
            rcon = 1
            for i in range(nk, 4 * (nr + 1)):
                t = list(w[i - 1])
                if i % nk == 0:
                    t = t[1:] + t[:1]
                    t = [SBOX[x] for x in t]
                    t[0] ^= rcon
                    rcon = _xtime(rcon)
                elif nk > 6 and i % nk == 4:
                    t = [SBOX[x] for x in t]
                w.append([w[i - nk][j] ^ t[j] for j in range(4)])
            return nr, w

        def _encrypt_block(key, block):
            nr, w = _expand_key(key)
            state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]

            def add_round_key(rnd):
                for c in range(4):
                    col = w[rnd * 4 + c]
                    for r in range(4):
                        state[r][c] ^= col[r]

            def sub_bytes():
                for r in range(4):
                    for c in range(4):
                        state[r][c] = SBOX[state[r][c]]

            def shift_rows():
                for r in range(1, 4):
                    state[r] = state[r][r:] + state[r][:r]

            def mix_columns():
                for c in range(4):
                    a0, a1, a2, a3 = (state[r][c] for r in range(4))
                    state[0][c] = _xtime(a0) ^ (_xtime(a1) ^ a1) ^ a2 ^ a3
                    state[1][c] = a0 ^ _xtime(a1) ^ (_xtime(a2) ^ a2) ^ a3
                    state[2][c] = a0 ^ a1 ^ _xtime(a2) ^ (_xtime(a3) ^ a3)
                    state[3][c] = (_xtime(a0) ^ a0) ^ a1 ^ a2 ^ _xtime(a3)

            add_round_key(0)
            for rnd in range(1, nr):
                sub_bytes()
                shift_rows()
                mix_columns()
                add_round_key(rnd)
            sub_bytes()
            shift_rows()
            add_round_key(nr)
            out = bytearray(16)
            for r in range(4):
                for c in range(4):
                    out[r + 4 * c] = state[r][c]
            return bytes(out)

        # GCM 加密侧 CTR 计数器从 2 开始 (J0=IV||1, counter 固定 32 位大端自增)
        out = bytearray()
        counter = 2
        pos = 0
        n = len(ct)
        while pos < n:
            ctr = iv + counter.to_bytes(4, "big")
            ks = _encrypt_block(key, ctr)
            chunk = ct[pos:pos + 16]
            out += bytes(a ^ b for a, b in zip(chunk, ks))
            pos += 16
            counter += 1
        return bytes(out)

    @staticmethod
    def aes_gcm_decrypt(key_b64, data_b64):
        """陷仙剑·AES-256-GCM 解密（多后端自动降级）"""
        try:
            key = base64.b64decode(key_b64)
            raw = base64.b64decode(data_b64)
        except Exception:
            return None
        if len(raw) < 28:
            return None
        iv, tag, ct = raw[:12], raw[12:28], raw[28:]
        # 后端1: pycryptodome
        if _CryptoAES is not None:
            try:
                cipher = _CryptoAES.new(key, _CryptoAES.MODE_GCM, nonce=iv)
                return cipher.decrypt_and_verify(ct, tag)
            except Exception:
                pass
        # 后端2: cryptography
        if _CRYPTOGCM is not None:
            try:
                return _CRYPTOGCM(key).decrypt(iv, ct + tag, None)
            except Exception:
                pass
        # 后端3: 纯Python（不验tag）
        try:
            return BingZiMi._aes_gcm_decrypt_py(key, iv, ct)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════
#  第三章：斗字秘 · 实战解析
# ═══════════════════════════════════════════════════════════════

class DouZiMi:
    """斗字秘·战斗解析：文本清洗 / RSC 提取 / 分类页解析"""

    @staticmethod
    def clean_text(raw):
        """七十二变·清洗HTML文本"""
        if raw is None:
            return ""
        if not isinstance(raw, str):
            raw = str(raw)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = raw.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        return raw.strip()

    @staticmethod
    def year_of(raw):
        """提取合法4位年份, 非法值($undefined等)返回空串"""
        m = re.search(r"\b(19\d{2}|20\d{2})\b", str(raw or ""))
        return m.group(1) if m else ""

    @staticmethod
    def rsc_text(html):
        """阵字秘·Next.js RSC push 片段反转义拼接"""
        parts = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
        if not parts:
            return html
        out = []
        for p in parts:
            try:
                out.append(json.loads('"' + p + '"'))
            except Exception:
                out.append(p)
        return "".join(out)

    @staticmethod
    def find_json(text, key, want="object"):
        """斗字秘·按括号平衡提取指定键后的 JSON 对象/数组"""
        marker = '"%s":' % key
        start = 0
        while True:
            i = text.find(marker, start)
            if i < 0:
                return None
            open_ch = text.find('{', i)
            close_ch = text.find('[', i)
            if open_ch < 0:
                j = close_ch
            elif close_ch < 0:
                j = open_ch
            else:
                j = min(open_ch, close_ch)
            if j < 0:
                return None
            if text[j] == '[':
                o, c = '[', ']'
            else:
                o, c = '{', '}'
            if want == "array" and text[j] == '{':
                start = i + 1
                continue
            depth = 0
            for k in range(j, len(text)):
                if text[k] == o:
                    depth += 1
                elif text[k] == c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[j:k + 1])
                        except Exception:
                            return None
            start = i + 1
        return None

    @staticmethod
    def detail_json(html):
        """斗字秘·从详情页 RSC 提取 {"cat","id","detail","sources",...}"""
        big = DouZiMi.rsc_text(html)
        start = 0
        while True:
            i = big.find('"data":{"cat":', start)
            if i < 0:
                i = big.find('"data": {"cat":', start)
            if i < 0:
                return None
            j = big.find('{', i)
            if j < 0:
                return None
            depth = 0
            obj = None
            for k in range(j, len(big)):
                if big[k] == '{':
                    depth += 1
                elif big[k] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(big[j:k + 1])
                        except Exception:
                            obj = None
                        break
            if isinstance(obj, dict) and "detail" in obj:
                return obj
            start = j + 1
        return None

    @staticmethod
    def parse_cat_page(html, config=None):
        """斗字秘·分类页 36 条卡片解析"""
        cfg = config or DEFAULT_CONFIG
        out = []
        for li in re.findall(r'<li class="video-card">(.*?)</li>', html, re.S):
            m = re.search(r'<a title="([^"]*)" class="video-card__link" href="/detail/([^"/]+)/([A-Za-z0-9]+)"', li)
            if not m:
                continue
            title, bucket, vid = m.group(1), m.group(2), m.group(3)
            pic = ""
            mp = re.search(r'<img[^>]*src="([^"]+)"', li)
            if mp:
                pic = mp.group(1)
            score = ""
            ms = re.search(r'video-card__score">([^<]+)<', li)
            if ms:
                score = ms.group(1).strip()
            meta = ""
            mm = re.search(r'video-card__meta">([^<]+)<', li)
            if mm:
                meta = mm.group(1).strip()
            area = meta.split("/")[0].strip() if "/" in meta else ""
            vod = {
                "vod_id": bucket + "/" + vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": ("评分" + score) if score else "",
                "vod_area": area,
            }
            out.append(vod)
        return out

    @staticmethod
    def item_to_vod(it, config=None):
        """斗字秘·首页/搜索 items 转 TVBox 列表项"""
        cfg = config or DEFAULT_CONFIG
        cat = str(it.get("cat") or "1")
        bucket = cfg.get("cat_bucket", {}).get(cat, "movie")
        meta = it.get("meta") or ""
        area = meta.split("/")[0].strip() if "/" in meta else ""
        return {
            "vod_id": bucket + "/" + str(it.get("id") or ""),
            "vod_name": it.get("title") or "",
            "vod_pic": it.get("cover") or "",
            "vod_remarks": it.get("badge") or "",
            "vod_year": DouZiMi.year_of(it.get("pubdate")),
            "vod_area": area,
        }


# ═══════════════════════════════════════════════════════════════
#  第四章：者字秘 · 不死之身（安全调用）
# ═══════════════════════════════════════════════════════════════

class ZheZiMi:
    """者字秘·不死之身：任何失败都不让整个源崩溃"""

    @staticmethod
    def safe_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            return None

    @staticmethod
    def safe_get(d, key, default=""):
        if not isinstance(d, dict):
            return default
        if "." in key:
            cur = d
            for part in key.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    return default
            return cur if cur is not None else default
        return d.get(key, default)

    @staticmethod
    def retry_with_backoff(func, max_retries=3, backoff_factor=1.0, *args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception:
                if attempt == max_retries - 1:
                    return None
                time.sleep(backoff_factor * (2 ** attempt) + random.uniform(0, 1))
        return None


# ═══════════════════════════════════════════════════════════════
#  第五章：皆字秘 · m3u8 净世
# ═══════════════════════════════════════════════════════════════

class JieZiMi:
    """皆字秘·净世咒：m3u8 相对路径转绝对 / 广告片段清洗"""

    @staticmethod
    def absolutize_m3u8(text, base_url):
        if not text or not base_url:
            return text
        from urllib.parse import urljoin
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("http://") and not s.startswith("https://"):
                s = urljoin(base_url, s)
            lines.append(s)
        return "\n".join(lines)

    @staticmethod
    def clean_m3u8(text):
        """简单广告/空行清理（保留 #EXT 注释行）"""
        if not text:
            return text
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") and "#" in s[1:] and not s.startswith("#EXT"):
                s = "#EXT" + s.split("#", 1)[1]
            out.append(s)
        return "\n".join(out)


# ═══════════════════════════════════════════════════════════════
#  第六章：主 Spider · 真狼影视
# ═══════════════════════════════════════════════════════════════

class Spider(BaseSpider):
    """真狼影视 Spider: 五接口圆满（home/category/detail/search/player）"""

    realm_name = "真狼影视"
    realm_level = 1
    defense_level = 1

    def __init__(self):
        if hasattr(super(Spider, self), "__init__"):
            try:
                super(Spider, self).__init__()
            except Exception:
                pass
        self.config = dict(DEFAULT_CONFIG)
        self.siteUrl = siteUrl
        self.session = None
        self.token = None
        self.key = None
        self.expires = 0.0
        self._local = threading.local()

    # ── OK影视 生命周期 ──
    def init(self, extend=""):
        """OK影视 加载后调用：建立会话 -> 触 WAF 挑战拿 cookie -> 握手换密钥"""
        if self.session is not None:
            return
        if not HAS_REQUESTS:
            return
        s = requests.Session()
        s.headers.update({
            "User-Agent": XingZiMi.random_ua(self.config),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": siteUrl,
        })
        self.session = s
        # 先"碰壁"一次: 403 响应会 Set-Cookie, 之后同 Session 即可正常访问
        try:
            s.get(siteUrl, timeout=12)
            s.get(siteUrl + "category/movie/filter?", timeout=12)
        except Exception:
            pass
        self._ensure_api()

    def getName(self):
        return self.config.get("name", siteName)

    def isVideoFormat(self, url):
        for ext in ('.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg'):
            if ext in str(url or "").lower():
                return True
        return False

    def manualVideoCheck(self):
        return False

    def homeVideoContent(self):
        return self.homeContent(filter=True)

    def localProxy(self, param):
        """真字秘·内置本地代理：可选转发 m3u8/图片"""
        try:
            url = unquote((param or {}).get("url", ""))
            kind = (param or {}).get("kind", "")
            if not url or self.session is None:
                return [500, "text/plain", b"no url"]
            r = self.session.get(url, headers={"Referer": siteUrl}, timeout=30)
            if kind == "hls":
                text = JieZiMi.absolutize_m3u8(r.text, url)
                text = JieZiMi.clean_m3u8(text)
                return [200, "application/vnd.apple.mpegurl", text.encode("utf-8")]
            if kind == "img":
                return [200, r.headers.get("Content-Type", "image/jpeg"), r.content]
            return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content]
        except Exception as e:
            return [500, "text/plain", ("Proxy Error: %s" % e).encode("utf-8")]

    # ── 内部请求 ──
    def _ensure_api(self):
        """确保 handshake 的 token/key 有效"""
        if self.session is None:
            return
        now = time.time() * 1000.0
        if self.token and self.expires and now < self.expires - 5000:
            return
        try:
            r = self.session.get(siteUrl + "api/crypto/handshake", timeout=12)
            d = (r.json() or {}).get("data") or {}
            self.token = d.get("token")
            self.key = d.get("key")
            try:
                self.expires = float(d.get("expiresAt") or 0) or now + 3600e3
            except Exception:
                self.expires = now + 3600e3
        except Exception:
            pass

    def _get(self, url, params=None, headers=None):
        """带 403 自动刷新 cookie 的 GET"""
        if self.session is None:
            return None
        r = None
        for _ in range(2):
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=15)
            except Exception:
                time.sleep(0.3)
                continue
            if r.status_code == 200:
                return r
            if r.status_code == 403:
                try:
                    self.session.get(siteUrl, timeout=10)
                except Exception:
                    pass
                continue
            return r
        return r

    def _api_dec(self, obj):
        """兵字秘·统一解密 API 返回体"""
        if isinstance(obj, dict) and obj.get("enc") == "1":
            plain = BingZiMi.aes_gcm_decrypt(self.key, obj.get("data") or "")
            if plain:
                try:
                    return json.loads(plain.decode("utf-8"))
                except Exception:
                    return None
            return None
        return obj

    def _build_vod(self, bucket, dj):
        """斗字秘·详情数据 -> TVBox vod 字段"""
        detail = dj.get("detail") or {}
        title = detail.get("title") or ""
        if not title:
            return None
        score = detail.get("doubanscore") or ""
        if not score:
            s = dj.get("score")
            if isinstance(s, str) and s and not s.startswith("$"):
                score = s
        vod = {
            "vod_id": bucket + "/" + str(dj.get("id") or ""),
            "vod_name": title,
            "vod_pic": detail.get("cdncover") or dj.get("cover") or "",
            "vod_remarks": dj.get("updateText") or "",
            "vod_year": DouZiMi.year_of(detail.get("pubdate")),
            "vod_area": "/".join(detail.get("area") or []),
            "vod_actor": "/".join(detail.get("actor") or []),
            "vod_director": "/".join(detail.get("director") or []),
            "vod_content": DouZiMi.clean_text(detail.get("description") or dj.get("comment") or ""),
        }
        if score:
            vod["vod_score"] = score

        sources = dj.get("sources") or []
        allepi = detail.get("allepidetail") or {}
        play_from, play_url, uurl = [], [], title
        names = self.config.get("site_names", {})
        for src in sources:
            site = src.get("site") or ""
            if not site:
                continue
            eps = []
            if isinstance(allepi.get(site), list) and allepi[site]:
                eps = allepi[site]
            else:
                eps = [e for e in (src.get("episodes") or [])
                       if isinstance(e, dict) and e.get("url") and not str(e.get("url", "")).startswith("$")]
            if not eps:
                continue
            segs = []
            for ep in eps:
                url = ep.get("url") or ""
                if not url or str(url).startswith("$"):
                    continue
                num = ep.get("playlink_num") or ""
                nm = ep.get("name") or ""
                if not nm:
                    nm = ("第%d集" % int(num)) if str(num).isdigit() else "正片"
                segs.append("%s$%s" % (nm, url))
            if not segs:
                continue
            play_from.append(names.get(site, src.get("name") or site))
            play_url.append("#".join(segs))
        # ── 网盘线路: /api/search/pan 公开接口按片名搜分享链接, 按网盘名分组 ──
        # 先做失效检测 (调站点 /api/verify-link, 网页同款), 只保留有效资源;
        # 某网盘分组全部失效 => 不生成该线路 (与"只显示有效资源"语义一致)
        if (self.config.get("pan") or {}).get("enabled", DEFAULT_CONFIG["pan"]["enabled"]):
            pan_items = self._search_pan(uurl)
            if pan_items:
                want_verify = (self.config.get("pan") or DEFAULT_CONFIG["pan"]).get(
                    "verify", DEFAULT_CONFIG["pan"]["verify"])
                if want_verify:
                    pan_items = self._filter_pan_valid(pan_items)
                max_i = int((self.config.get("pan") or {}).get("max_items", DEFAULT_CONFIG["pan"]["max_items"]))
                pan_groups = {}   # 网盘名 -> [剧集串]
                pan_order = []    # 保持首现顺序
                for pn in pan_items[:max_i]:
                    pname = self._pan_disk_name(pn.get("url") or "")
                    ep = "%s$%s" % (str(pn.get("title") or "")[:60], pn.get("url") or "")
                    if pname not in pan_groups:
                        pan_groups[pname] = []
                        pan_order.append(pname)
                    pan_groups[pname].append(ep)
                for pname in pan_order:
                    if pan_groups[pname]:
                        play_from.append(pname)
                        play_url.append("#".join(pan_groups[pname]))
        if play_from:
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_url)
        return vod

    # ── 五接口 ──
    def homeContent(self, filter=False):
        """首页：分类 + 电影筛选标签 + 推荐列表"""
        out = {"class": list(DEFAULT_CONFIG["fallback_classes"]), "list": []}
        out["filters"] = {
            "movie": [
                {"key": "type", "name": "类型", "value": [{"n": "全部", "v": ""}] + [
                    {"n": t, "v": t} for t in ("喜剧", "爱情", "动作", "恐怖", "科幻", "剧情", "犯罪",
                                                "奇幻", "战争", "悬疑", "动画", "文艺", "纪录", "传记",
                                                "歌舞", "古装", "历史", "惊悚", "伦理", "其他")]},
                {"key": "year", "name": "年代", "value": [{"n": "全部", "v": ""}] + [
                    {"n": str(y), "v": str(y)} for y in range(2026, 2006, -1)] + [
                    {"n": "更早", "v": "lt_year"}]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""}, {"n": "内地", "v": "大陆"}, {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"}, {"n": "泰国", "v": "泰国"}, {"n": "美国", "v": "美国"},
                    {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"}, {"n": "法国", "v": "法国"},
                    {"n": "英国", "v": "英国"}, {"n": "德国", "v": "德国"}, {"n": "印度", "v": "印度"},
                    {"n": "其他", "v": "其他"}]},
            ],
        }
        r = ZheZiMi.safe_call(self._get, siteUrl)
        if r is not None:
            big = DouZiMi.rsc_text(r.text)
            items = DouZiMi.find_json(big, "items", want="array")
            if isinstance(items, list):
                out["list"] = [v for v in (DouZiMi.item_to_vod(it, self.config) for it in items
                                           if isinstance(it, dict) and it.get("id")) if v]
        return out

    def categoryContent(self, tid, pg, filter=False, extend={}):
        """分类：/category/{tid}/filter?page=N + 筛选条件"""
        page = int(pg or 1)
        out = {"list": [], "page": page, "pagecount": page, "limit": 36, "total": 0}
        url = siteUrl + "category/%s/filter?page=%d" % (str(tid), page)
        if extend:
            qs = []
            for k, v in extend.items():
                if v is not None and str(v) != "":
                    qs.append("%s=%s" % (str(k), quote(str(v))))
            if qs:
                url += "&" + "&".join(qs)
        r = ZheZiMi.safe_call(self._get, url)
        if r is None:
            return out
        html = r.text
        out["list"] = DouZiMi.parse_cat_page(html, self.config)
        out["total"] = len(out["list"])
        if re.search(r'>下一页<', html):
            out["pagecount"] = page + 1
        else:
            out["pagecount"] = page
        return out

    def detailContent(self, ids):
        """详情：/detail/{bucket}/{id} RSC 解析；ids 兼容 List[str] 与 "a$$$b" 字符串"""
        out = {"list": []}
        if isinstance(ids, (list, tuple)):
            id_list = [str(x) for x in ids]
        else:
            id_list = str(ids or "").split("$$$")
        for vid in id_list:
            vid = (vid or "").strip()
            if not vid or "/" not in vid:
                continue
            bucket, iid = vid.split("/", 1)
            r = ZheZiMi.safe_call(self._get, siteUrl + "detail/%s/%s" % (bucket, iid))
            if r is None or r.status_code == 404:
                # bucket 失配时按其它分类兜底
                for b in ("movie", "tv", "variety", "anime", "children"):
                    if b == bucket:
                        continue
                    r2 = ZheZiMi.safe_call(self._get, siteUrl + "detail/%s/%s" % (b, iid))
                    if r2 is not None and r2.status_code == 200 and DouZiMi.detail_json(r2.text):
                        bucket, r = b, r2
                        break
                else:
                    continue
            elif r.status_code != 200:
                continue
            dj = DouZiMi.detail_json(r.text)
            if not dj:
                continue
            vod = self._build_vod(bucket, dj)
            if vod:
                out["list"].append(vod)
        return out

    def searchContent(self, key, quick, pg="1"):
        """搜索：/api/search 加密链路
        注意: OK影视/TVBox 调用签名 searchContent(key, quick, pg)"""
        out = {"list": [], "page": int(pg or 1), "pagecount": 1}
        if not key or self.session is None:
            return out
        self._ensure_api()
        r = ZheZiMi.safe_call(self._get, siteUrl + "api/search",
                              params={"q": key}, headers={"X-Enc-Token": self.token})
        if r is None:
            return out
        d = self._api_dec(r.json())
        items = ZheZiMi.safe_get(d, "data.items", []) or []
        out["list"] = [v for v in (DouZiMi.item_to_vod(it, self.config) for it in items
                                   if isinstance(it, dict) and it.get("id")) if v]
        return out

    def playerContent(self, flag, id, vipFlags=None):
        """播放策略:
        1) 网盘分享链接 -> push:// 推送播放 (参考爱盼网盘.py, 由播放器/网盘APP接收)
        2) 磁力链接 -> 原样直传
        3) 站点 resolve 直链 (parse=0)
        4) resolve 失败 -> 站点内置第三方解析站 (parse=1, WebView)
        5) 解析站不可用 -> 原URL最终兜底
        """
        if not id:
            return {"parse": 0, "url": "", "header": {}}
        header = {"User-Agent": XingZiMi.random_ua(self.config)}
        # ── 网盘线路: push:// 推送播放 (参考爱盼网盘.py) ──
        # 分享链接无直链、resolve 必败; 包装成 push:// 协议交由支持推送的播放器/网盘APP接收
        if self._is_pan_url(id):
            return {"parse": 0, "jx": 0, "url": "push://" + id, "header": header}
        # ── 磁力链接: 原样直传 (与爱盼网盘.py 一致) ──
        if str(id or "").startswith("magnet:"):
            return {"parse": 0, "jx": 0, "url": id, "header": {}}
        if self.session is None or self.token is None:
            return {"parse": 0, "url": id, "header": header}
        self._ensure_api()
        site = flag or ""
        for k, v in (self.config.get("site_names") or {}).items():
            if v == flag:
                site = k
                break
        # ── 第一级: 站点 resolve 直链 (失败则轮换 from 绕开 cachedFailure) ──
        direct = self._resolve_direct(id, site)
        if direct:
            return direct
        # ── 第二级: 站点内置第三方解析站 (WebView parse=1) ──
        jx_url = self._pick_parse_site(id)
        if jx_url:
            return {"parse": 1, "url": jx_url, "header": header}
        # ── 第三级: 原URL 兜底 ──
        return {"parse": 0, "url": id, "header": header}

    def _resolve_candidates(self, site):
        """者字秘·候选 from 表: 原线路代码优先, 再轮换常见平台代码"""
        cands = []
        if site:
            cands.append(site)
        for c in ("", "qq", "youku", "qiyi", "imgo", "leshi",
                  "bilibili1", "sohu", "pptv", "1905"):
            if c not in cands:
                cands.append(c)
        return cands

    def _resolve_direct(self, url, site):
        """者字秘·直链不死追:
        真狼 resolve 对同一 (URL, from) 组合有失败缓存 cachedFailure,
        失败后同 from 重复请求必败; 轮换候选 from 值可绕开缓存出直链"""
        for frm in self._resolve_candidates(site):
            r = ZheZiMi.safe_call(self._get, siteUrl + "api/resolve",
                                  params={"url": url, "from": frm},
                                  headers={"X-Enc-Token": self.token})
            if r is None:
                continue
            d = self._api_dec(r.json())
            data = ZheZiMi.safe_get(d, "data", None) or {}
            fu = data.get("url") or ""
            resolved = data.get("resolved")
            if fu and resolved is not False and fu != url:
                # 直链成功: 实测各 CDN 无防盗链, 且带错误 Referer 反致 404, 故 header 留空
                return {"parse": 0, "url": fu, "header": {}}
        return None

    def _get_parse_sites(self):
        """懒加载站点 /parse 内置解析站配置 (更新站点配置优先, 失败用默认)"""
        if getattr(self, "_parse_sites", None):
            return self._parse_sites
        sites = list((self.config.get("parse_sites") or DEFAULT_CONFIG["parse_sites"]))
        r = ZheZiMi.safe_call(self._get, siteUrl + "parse")
        if r is not None and r.status_code == 200:
            big = DouZiMi.rsc_text(r.text)
            arr = DouZiMi.find_json(big, "parseSites", want="array")
            if isinstance(arr, list):
                fresh = [s for s in arr
                         if isinstance(s, dict) and s.get("apiUrl") and s.get("enabled")]
                if fresh:
                    sites = fresh
        self._parse_sites = sites
        return self._parse_sites

    def _search_pan(self, keyword):
        """网盘线路数据源: 公开接口 /api/search/pan?panType=&keyword=&mode=
        无加密 token, 返回夸克等网盘分享链接 items; 同片名结果缓存 30 分钟"""
        try:
            kw = str(keyword or "").strip()
            if not kw:
                return []
            cache = getattr(self, "_pan_cache", None)
            if cache is None:
                cache = self._pan_cache = {}
            hit = cache.get(kw)
            if hit is not None and time.time() - hit[0] < 1800:
                return hit[1]
            pan = self.config.get("pan") or DEFAULT_CONFIG["pan"]
            r = ZheZiMi.safe_call(self._get, siteUrl + "api/search/pan",
                                  params={"panType": pan.get("pan_type", "0"),
                                          "keyword": kw,
                                          "mode": pan.get("mode", "exact")})
            if r is None or r.status_code != 200:
                return []
            d = r.json()
            items = ZheZiMi.safe_get(d, "data.items", []) or []
            out = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                url = it.get("url") or ""
                if not url:
                    continue
                out.append({"title": (it.get("title") or "").strip(), "url": url,
                            "source": it.get("sourceName") or ""})
            cache[kw] = (time.time(), out)
            if len(cache) > 120:
                for k in list(cache.keys())[:40]:
                    cache.pop(k, None)
            return out
        except Exception:
            return []

    def _pan_valid(self, url):
        """网页同款失效检测: GET /api/verify-link?url=... -> ok==true 有效
        结果 URL 级缓存 verify_ttl 秒 (默认 1800, 与 pan 搜索缓存一致);
        请求失败/接口异常时保守返回 True (不误伤可播放资源)"""
        try:
            u = str(url or "").strip()
            if not u:
                return False
            pan = self.config.get("pan") or DEFAULT_CONFIG["pan"]
            ttl = int(pan.get("verify_ttl", DEFAULT_CONFIG["pan"]["verify_ttl"]))
            cache = getattr(self, "_verify_cache", None)
            if cache is None:
                cache = self._verify_cache = {}
            hit = cache.get(u)
            if hit is not None and time.time() - hit[0] < ttl:
                return hit[1]
            verify_url = (pan.get("verify_url") or DEFAULT_CONFIG["pan"]["verify_url"])
            if not str(verify_url).startswith("http"):
                verify_url = siteUrl + verify_url
            r = ZheZiMi.safe_call(self._get, verify_url, params={"url": u})
            ok = True  # 保守默认: 请求失败不误杀
            if r is not None and r.status_code == 200:
                try:
                    d = r.json()
                    ok = bool(d.get("ok")) or str(d.get("status") or "") == "valid"
                except Exception:
                    ok = True
            cache[u] = (time.time(), ok)
            if len(cache) > 300:
                for k in list(cache.keys())[:80]:
                    cache.pop(k, None)
            return ok
        except Exception:
            return True

    def _filter_pan_valid(self, items):
        """皆字秘·网盘净世: 逐条失效检测, 只保留有效分享链接;
        并发加速 (HAS_THREADPOOL 时最多 6 线程, 缺失时串行兜底)"""
        if not items:
            return []
        if HAS_THREADPOOL:
            try:
                pool = ThreadPoolExecutor(max_workers=min(6, len(items)))
                try:
                    flags = list(pool.map(
                        lambda pn: self._pan_valid((pn or {}).get("url") or ""), items))
                finally:
                    pool.shutdown(wait=True)
                return [pn for pn, ok in zip(items, flags) if ok]
            except Exception:
                # 并发异常兜底: 退回串行
                pass
        out = []
        for pn in items:
            if not isinstance(pn, dict):
                continue
            if self._pan_valid(pn.get("url") or ""):
                out.append(pn)
        return out

    def _pan_disk_name(self, url):
        """斗字秘·网盘命名: 按 URL 域名关键字匹配 name_rules, 返回网盘线路名;
        未命中返回兜底 site_name (默认 网盘), 保证任何分享链接都有分组"""
        try:
            u = str(url or "").lower()
            if not u:
                return (self.config.get("pan") or DEFAULT_CONFIG["pan"]).get(
                    "site_name", DEFAULT_CONFIG["pan"]["site_name"])
            for rule in ((self.config.get("pan") or DEFAULT_CONFIG["pan"]).get(
                    "name_rules") or DEFAULT_CONFIG["pan"]["name_rules"]):
                kw = (rule or {}).get("kw") or ""
                if kw and kw in u:
                    return (rule or {}).get("name") or ""
            return (self.config.get("pan") or DEFAULT_CONFIG["pan"]).get(
                "site_name", DEFAULT_CONFIG["pan"]["site_name"])
        except Exception:
            return (self.config.get("pan") or DEFAULT_CONFIG["pan"]).get(
                "site_name", DEFAULT_CONFIG["pan"]["site_name"])

    def _is_pan_url(self, url):
        """命中网盘 host 则 true: 分享链接不走 resolve, 直接 WebView"""
        try:
            pan = self.config.get("pan") or DEFAULT_CONFIG["pan"]
            hosts = pan.get("hosts") or DEFAULT_CONFIG["pan"]["hosts"]
            u = str(url or "").lower()
            return any(h in u for h in hosts if h)
        except Exception:
            return False

    def _pick_parse_site(self, video_url):
        """取第一个启用的解析站拼 URL; 失败返回 None"""
        for s in self._get_parse_sites():
            try:
                api = (s or {}).get("apiUrl") or ""
                if not api:
                    continue
                return api + quote(str(video_url), safe="")
            except Exception:
                continue
        return None


__all__ = [
    "siteName", "siteUrl", "Spider",
    "BingZiMi", "DouZiMi", "ZheZiMi", "XingZiMi", "JieZiMi",
]

if __name__ == "__main__":
    print("siteName:", siteName)
    print("HAS_REQUESTS:", HAS_REQUESTS, "| HAS_CRYPTO:", HAS_CRYPTO,
          "| HAS_CRYPTOGRAPHY:", HAS_CRYPTOGRAPHY)
    print("Spider 就绪: 真狼影视 五接口圆满")