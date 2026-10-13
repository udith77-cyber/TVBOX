# -*- coding: utf-8 -*-
import sys
import re
import time
import json
import base64
import threading
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import unquote, quote

urllib3.disable_warnings()
sys.path.append('..')
from base.spider import Spider

# ===== 纯 Python AES-128 工具（保留原有） =====
_sbox = bytes([
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16])
_inv_sbox = bytes([
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d])
_rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]
def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff
def _gf_mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1: r ^= a
        a = _xtime(a)
        b >>= 1
    return r
_mul_e = bytes(_gf_mul(0x0e, i) for i in range(256))
_mul_b = bytes(_gf_mul(0x0b, i) for i in range(256))
_mul_d = bytes(_gf_mul(0x0d, i) for i in range(256))
_mul_9 = bytes(_gf_mul(0x09, i) for i in range(256))
_key_schedules = {}
def _key_schedule(key):
    k = bytes(key)
    if k in _key_schedules: return _key_schedules[k]
    w = []
    for i in range(4):
        w.append([key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]])
    for i in range(4, 44):
        temp = w[i-1][:]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_sbox[b] for b in temp]
            temp[0] ^= _rcon[i//4 - 1]
        w.append([w[i-4][j] ^ temp[j] for j in range(4)])
    _key_schedules[k] = w
    return w
def _dec_block(block, w):
    s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15 = block
    s0 ^= w[40][0]; s1 ^= w[40][1]; s2 ^= w[40][2]; s3 ^= w[40][3]
    s4 ^= w[41][0]; s5 ^= w[41][1]; s6 ^= w[41][2]; s7 ^= w[41][3]
    s8 ^= w[42][0]; s9 ^= w[42][1]; s10^= w[42][2]; s11^= w[42][3]
    s12^= w[43][0]; s13^= w[43][1]; s14^= w[43][2]; s15^= w[43][3]
    box = _inv_sbox
    for rnd in range(9, 0, -1):
        t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
        t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
        t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
        t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
        rk=w[rnd*4]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
        rk=w[rnd*4+1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
        rk=w[rnd*4+2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
        rk=w[rnd*4+3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
        s0 =_mul_e[t0]^_mul_b[t1]^_mul_d[t2]^_mul_9[t3]
        s1 =_mul_9[t0]^_mul_e[t1]^_mul_b[t2]^_mul_d[t3]
        s2 =_mul_d[t0]^_mul_9[t1]^_mul_e[t2]^_mul_b[t3]
        s3 =_mul_b[t0]^_mul_d[t1]^_mul_9[t2]^_mul_e[t3]
        s4 =_mul_e[t4]^_mul_b[t5]^_mul_d[t6]^_mul_9[t7]
        s5 =_mul_9[t4]^_mul_e[t5]^_mul_b[t6]^_mul_d[t7]
        s6 =_mul_d[t4]^_mul_9[t5]^_mul_e[t6]^_mul_b[t7]
        s7 =_mul_b[t4]^_mul_d[t5]^_mul_9[t6]^_mul_e[t7]
        s8 =_mul_e[t8]^_mul_b[t9]^_mul_d[t10]^_mul_9[t11]
        s9 =_mul_9[t8]^_mul_e[t9]^_mul_b[t10]^_mul_d[t11]
        s10=_mul_d[t8]^_mul_9[t9]^_mul_e[t10]^_mul_b[t11]
        s11=_mul_b[t8]^_mul_d[t9]^_mul_9[t10]^_mul_e[t11]
        s12=_mul_e[t12]^_mul_b[t13]^_mul_d[t14]^_mul_9[t15]
        s13=_mul_9[t12]^_mul_e[t13]^_mul_b[t14]^_mul_d[t15]
        s14=_mul_d[t12]^_mul_9[t13]^_mul_e[t14]^_mul_b[t15]
        s15=_mul_b[t12]^_mul_d[t13]^_mul_9[t14]^_mul_e[t15]
    t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
    t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
    t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
    t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
    rk=w[0]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
    rk=w[1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
    rk=w[2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
    rk=w[3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
    return bytes([t0,t1,t2,t3,t4,t5,t6,t7,t8,t9,t10,t11,t12,t13,t14,t15])
def _aes_cbc_decrypt(data, key, iv):
    if not data or len(data) % 16: return data
    n = len(data) // 16
    w = _key_schedule(key)
    out = bytearray(len(data))
    prev = iv
    for i in range(n):
        block = data[i*16:(i+1)*16]
        dec = _dec_block(block, w)
        for j in range(16):
            out[i*16+j] = dec[j] ^ prev[j]
        prev = block
    pad = out[-1]
    if 1 <= pad <= 16:
        return bytes(out[:-pad])
    return bytes(out)

# ===== 全局代理服务（封面图走代理绕过 SSL） =====
_proxy_port = 0
_proxy_started = False
_proxy_session = requests.Session()
_proxy_session.verify = False
_proxy_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': '',  # 在 Spider.init() 中动态设置
}
class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            real_url = unquote(self.path[1:])
            if not real_url or not real_url.startswith('http'):
                self.send_response(404); self.end_headers(); return
            r = _proxy_session.get(real_url, headers=_proxy_headers, timeout=20, verify=False)
            ct = r.headers.get('Content-Type', 'image/jpeg')
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', len(r.content))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(r.content)
        except BrokenPipeError:
            pass
        except Exception:
            self.send_response(404); self.end_headers()
    def log_message(self, format, *args): pass
def _find_free_port():
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.bind(('127.0.0.1', 0))
    port = sk.getsockname()[1]
    sk.close()
    return port
def _start_proxy():
    global _proxy_port, _proxy_started
    if _proxy_started: return
    _proxy_port = _find_free_port()
    server = _ThreadedHTTPServer(('127.0.0.1', _proxy_port), _ProxyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _proxy_started = True

# ===== 发布站域名解析器（动态获取18AV视频站免翻墙域名） =====
# 唯一固定地址：发布站。视频站域名全部动态解析，不硬编码。
_PUBLISH_URL = 'https://mm18vd.com/'
_DOMAIN_CACHE = {'host': None, 'ts': 0}
_DOMAIN_LOCK = threading.Lock()
_CACHE_TTL = 1800  # 30分钟缓存

def _fetch_publish_page():
    """获取发布页原始HTML"""
    try:
        r = requests.get(_PUBLISH_URL, timeout=15, verify=False,
                         headers={'User-Agent': _proxy_headers['User-Agent']})
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ''

def _extract_and_decrypt_publish(html):
    """从发布页HTML中提取jhtml密文并解密，返回明文HTML

    AES密钥/IV不硬编码：从打包JS的字符串字典中动态提取。
    格式特征：4个小写字母+4个数字+4个小写字母+4个数字（如 qwer1234tyui4567）
    尝试两种key/iv组合，取能解出有效HTML的那个。
    """
    if not html:
        return ''
    m = re.search(r"jhtml\s*=\s*'([^']+)'", html)
    if not m:
        return ''
    jhtml = m.group(1)
    candidates = re.findall(r'[a-z]{4}\d{4}[a-z]{4}\d{4}', html)
    if len(candidates) < 2:
        return ''
    seen = set()
    for key_str in candidates:
        for iv_str in candidates:
            if key_str == iv_str or (key_str, iv_str) in seen:
                continue
            seen.add((key_str, iv_str))
            try:
                raw = base64.b64decode(jhtml)
                plain = _aes_cbc_decrypt(raw, key_str.encode(), iv_str.encode())
                result = plain.decode('utf-8')
                if '<html' in result.lower() or '<div' in result.lower():
                    return result
            except Exception:
                continue
    return ''

def _parse_18av_no_vpn_domains(html):
    """从解密后的发布页HTML中提取18AV视频站的免翻墙域名列表

    页面结构：
    - <h3 class="heading">【[1][8][A][V]視頻站】</h3> 标记18AV区域开始
    - 下一个 <h3 class="heading"> 标记下一区域开始（JavBooks等）
    - 区域内 <h3 class="title">[免][翻][牆]可访问地址</h3> 标记免翻墙子区域
    - 需翻墙域名的 <a> 标签带 class='text_decoration'（删除线），排除
    """
    if not html:
        return []
    av_start_match = re.search(r'\[\s*1\s*\]\s*\[\s*8\s*\]\s*\[\s*A\s*\]\s*\[\s*V\s*\]', html)
    if not av_start_match:
        av_start_match = re.search(r'18\s*A\s*V', html, re.I)
    if not av_start_match:
        return []
    av_start = av_start_match.start()
    next_heading = re.search(r'<h3 class="heading">', html[av_start + 1:])
    av_end = av_start + 1 + next_heading.start() if next_heading else len(html)
    av_section = html[av_start:av_end]
    no_vpn_match = re.search(
        r'\[免\]\[翻\]\[[牆墙]\].*?</h3>\s*<ul>(.*?)</ul>',
        av_section, re.S
    )
    if not no_vpn_match:
        return []
    ul_content = no_vpn_match.group(1)
    domains = []
    for m in re.finditer(r"<a[^>]*href=['\"]([^'\"]+)['\"]", ul_content):
        href = m.group(1).strip()
        href = re.sub(r'\s+', '', href)
        if 'text_decoration' in m.group(0):
            continue
        if href.startswith('http://') or href.startswith('https://'):
            domains.append(href.rstrip('/'))
    return domains

def _test_domain(domain_url):
    """并发测试单个域名：GET请求检测返回内容是否包含中文字幕或全部影片

    返回重定向后的最终基础URL（http可能被站点升级为https），
    确保 Spider 后续请求使用正确的协议。
    """
    test_url = f'{domain_url}/zh/chinese_IamOverEighteenYearsOld/19/index.html'
    try:
        r = requests.get(test_url, timeout=10, verify=False, allow_redirects=True,
                         headers={'User-Agent': _proxy_headers['User-Agent']})
        if r.status_code == 200:
            text = r.text
            if '中文字幕' in text or '全部影片' in text:
                # 从重定向后的最终URL提取基础地址
                # 例如 r.url = 'https://域名/zh/...' -> 'https://域名'
                if '/zh/' in r.url:
                    return r.url.split('/zh/')[0]
                return domain_url
    except Exception:
        pass
    return None

def _resolve_host():
    """主入口：从发布站动态解析18AV视频站的有效域名

    流程：获取发布页 -> 解密 -> 提取免翻墙域名 -> 并发测试 -> 30分钟缓存
    失败时返回上次缓存（如有），无缓存返回空字符串。
    """
    with _DOMAIN_LOCK:
        now = time.time()
        if _DOMAIN_CACHE['host'] and (now - _DOMAIN_CACHE['ts']) < _CACHE_TTL:
            return _DOMAIN_CACHE['host']
        html = _fetch_publish_page()
        if not html:
            return _DOMAIN_CACHE['host'] or ''
        decrypted = _extract_and_decrypt_publish(html)
        if not decrypted:
            return _DOMAIN_CACHE['host'] or ''
        domains = _parse_18av_no_vpn_domains(decrypted)
        if not domains:
            return _DOMAIN_CACHE['host'] or ''
        valid_domain = None
        with ThreadPoolExecutor(max_workers=min(len(domains), 10)) as executor:
            futures = {executor.submit(_test_domain, d): d for d in domains}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_domain = result
                    break
        if valid_domain:
            _DOMAIN_CACHE['host'] = valid_domain
            _DOMAIN_CACHE['ts'] = now
            return valid_domain
        return _DOMAIN_CACHE['host'] or ''

# ===== 内容类型判断 =====
def _is_novel(tid_or_vid):
    if not tid_or_vid: return False
    return tid_or_vid.startswith('novel')
def _is_image(tid_or_vid):
    if not tid_or_vid: return False
    return any(tid_or_vid.startswith(p) for p in ['18H', 'doujin', 'cg', 'cwp'])

# ===== Spider =====
class Spider(Spider):
    session = requests.Session()
    _cached_host = None
    _cached_ts = 0
    _news_years_cache = None
    _news_years_ts = 0
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': '',  # 在 init() 中动态设置
    }

    @property
    def host(self):
        now = time.time()
        if self._cached_host and (now - self._cached_ts) < _CACHE_TTL:
            return self._cached_host
        h = _resolve_host()
        self._cached_host = h
        self._cached_ts = now
        if h:
            self.headers['Referer'] = h + '/'
            _proxy_headers['Referer'] = h + '/'
        return h

    @host.setter
    def host(self, value):
        pass  # 父类可能赋值，忽略以保持动态解析

    def getName(self):
        h = self.host
        if not h:
            return '18av'
        m = re.search(r'https?://([^/]+)', h)
        if m:
            return m.group(1).split('.')[0]
        return '18av'
    def isVideoFormat(self, url):
        if not url: return False
        return '.m3u8' in url or '.mp4' in url or '.ts' in url
    def manualVideoCheck(self): return False
    def destroy(self): pass

    def localProxy(self, param):
        return [404, 'text/plain', '']

    def init(self, extend=""):
        self.session.verify = False
        _start_proxy()
        h = self.host  # 触发域名解析
        if h:
            try:
                self.session.get(
                    f'{h}/zh/chinese_IamOverEighteenYearsOld/19/index.html',
                    headers=self.headers, timeout=15, verify=False)
            except Exception:
                pass

    def _proxy_url(self, url):
        if not url: return ''
        if url.startswith('http://127.0.0.1'):
            return url
        return f'http://127.0.0.1:{_proxy_port}/{quote(url, safe="")}'

    def _fetch(self, url):
        try:
            r = self.session.get(url, headers=self.headers, timeout=20, verify=False)
            r.encoding = 'utf-8'
            if r.status_code == 200:
                text = r.text
                if len(text) < 3000 and ('同意(enter)' in text or 'IamOverEighteenYearsOld' in text):
                    self.session.get(
                        f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html',
                        headers=self.headers, timeout=20, verify=False)
                    r = self.session.get(url, headers=self.headers, timeout=20, verify=False)
                    r.encoding = 'utf-8'
                    if r.status_code == 200:
                        return r.text
                    return ''
                return text
            return ''
        except Exception:
            return ''

    def _parse_posts(self, text, tid=''):
        if _is_novel(tid):
            return self._parse_text_posts(text)

        items = []
        pattern1 = r"<div class='post'>\s*<a[^>]*href=\"([^\"]+)\"[^>]*><img[^>]*src='([^']+)'[^>]*>\s*</a>\s*<div class='con'>\s*<h3[^>]*><a[^>]*>([^<]+)</a></h3>(?:\s*<div class='meta'>([^<]*)</div>)?"
        matches = re.findall(pattern1, text, re.S)
        if matches:
            for href, pic, title, date in matches:
                if href.startswith(self.host):
                    href = href[len(self.host):]
                if not href or not href.startswith('/'):
                    continue
                mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
                if not mm:
                    continue
                ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
                items.append({
                    'vod_id': f'{ctype}#{vid}#{slug}',
                    'vod_name': title.strip(),
                    'vod_pic': self._proxy_url(pic),
                    'vod_remarks': date.strip() if date else '',
                })
            return items

        pattern2 = r'<a[^>]+href="([^"]*zh/[^"]*_content/[^"]*)"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>.*?<(?:h3|h2|h4|div\s+class="title")[^>]*>(.*?)</'
        matches = re.findall(pattern2, text, re.S | re.I)
        for href, pic, title in matches:
            if href.startswith(self.host):
                href = href[len(self.host):]
            if not href or not href.startswith('/'):
                continue
            mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
            if not mm:
                continue
            ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
            title = re.sub(r'<[^>]+>', '', title).strip()
            items.append({
                'vod_id': f'{ctype}#{vid}#{slug}',
                'vod_name': title,
                'vod_pic': self._proxy_url(pic),
                'vod_remarks': '',
            })
        return items

    def _parse_text_posts(self, text):
        items = []
        for m in re.finditer(r"<div class='post'>\s*<div class='con'>\s*<h3[^>]*><a[^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a></h3>", text):
            href, title = m.groups()
            mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
            if not mm: continue
            ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
            items.append({
                'vod_id': f'{ctype}#{vid}#{slug}',
                'vod_name': title.strip(),
                'vod_pic': '',
                'vod_remarks': '',
            })
        return items

    def homeContent(self, filter):
        try:
            classes = [
                {"type_name": "中文字幕", "type_id": "chinese"},
                {"type_name": "有碼AV", "type_id": "censored"},
                {"type_name": "素人AV", "type_id": "amateur"},
                {"type_name": "無碼破解", "type_id": "reducing"},
                {"type_name": "H動畫", "type_id": "animation"},
                {"type_name": "國產自拍", "type_id": "dt"},
                {"type_name": "📌類別清單", "type_id": "categorylist"},
                {"type_name": "📌每日更新", "type_id": "news"},
                {"type_name": "自定義詞條", "type_id": "custom"},
            ]
            filters = {
                "reducing": {
                    "key": "sub",
                    "name": "類型",
                    "value": [
                        {"n": "无码AV", "v": "uncensored_list/all"},
                        {"n": "一本道", "v": "uncensored_makersr/32/一本道(1pondo)"},
                        {"n": "Caribbeancom", "v": "uncensored_makersr/30/カリビアンコム(Caribbeancom)"},
                        {"n": "Caribbeancompr", "v": "uncensored_makersr/40/カリビアンコムPPV(Caribbeancompr)"},
                        {"n": "10musume", "v": "uncensored_makersr/31/天然むすめ(10musume)"},
                        {"n": "HEYZO", "v": "uncensored_makersr/17/HEYZO"},
                        {"n": "東京熱", "v": "uncensored_makersr/29/東京熱(Tokyo Hot)"},
                        {"n": "Gachinco", "v": "uncensored_makersr/35/ガチん娘！(Gachinco)"},
                        {"n": "pacopacomama", "v": "uncensored_makersr/36/パコパコママ(pacopacomama)"},
                        {"n": "エッチな4610", "v": "uncensored_makersr/34/エッチな4610"},
                        {"n": "人妻斬り0930", "v": "uncensored_makersr/38/人妻斬り0930"},
                        {"n": "エッチな0930", "v": "uncensored_makersr/39/エッチな0930"},
                        {"n": "XXX-AV", "v": "uncensored_makersr/126/トリプルエックス (XXX-AV)"},
                    ]
                },
                "animation": {
                    "key": "sub",
                    "name": "類型",
                    "value": [
                        {"n": "H动漫", "v": "animation_list/all"},
                        {"n": "H有碼動畫", "v": "CensoredAnimation_list/all"},
                        {"n": "H無碼動畫", "v": "UncensoredAnimation_list/all"},
                        {"n": "H_3D動畫", "v": "tdAnimation_list/all"},
                    ]
                },
                "custom": {
                    "key": "sub",
                    "name": "關鍵詞",
                    "value": [
                        {"n": "春药", "v": "春药"},
                        {"n": "人妻", "v": "人妻"},
                        {"n": "轮奸", "v": "轮奸"},
                        {"n": "媚药", "v": "媚药"},
                        {"n": "精油", "v": "精油"},
                        {"n": "按摩", "v": "按摩"},
                    ]
                },
                "news": {
                    "key": "year",
                    "name": "年份",
                    "value": [
                        {"n": year, "v": year} for year in self._news_years()
                    ]
                },
            }
            text = self._fetch(f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html')
            items = self._parse_posts(text, 'chinese_random/all') if text else []
            return {'class': classes, 'filters': filters, 'type': '影视', 'list': items,
                    'page': 1, 'pagecount': 1, 'limit': len(items), 'total': len(items)}
        except Exception:
            return {'class': [], 'filters': {}, 'type': '影视', 'list': [],
                    'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def homeVideoContent(self):
        try:
            text = self._fetch(f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html')
            return {'list': self._parse_posts(text, 'chinese_random/all')}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            return self._categoryContent_inner(tid, pg, filter, extend)
        except Exception as e:
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _categoryContent_inner(self, tid, pg, filter, extend):
        pg = str(pg)
        try:
            if isinstance(tid, str) and tid.startswith("folder$"):
                folder_val = tid.split("$", 1)[1]
                if folder_val.startswith("category_"):
                    extend = extend or {}
                    extend["sub"] = folder_val
                    tid = "categorylist"
                elif folder_val.startswith("news_"):
                    extend = extend or {}
                    extend["sub"] = folder_val
                    tid = "news"
            elif isinstance(tid, str) and tid.startswith("category_"):
                extend = extend or {}
                extend["sub"] = tid
                tid = "categorylist"
            elif isinstance(tid, str) and tid.startswith("news_"):
                extend = extend or {}
                extend["sub"] = tid
                tid = "news"

            if tid == "chinese":
                path = f"{self.host}/zh/chinese_list/all/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    if pg == "1":
                        html = self._fetch(f"{self.host}/zh/chinese_random/all/index.html")
                    else:
                        return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                pagecount = self._pagecount(html, pg)
                return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}

            elif tid == "censored":
                path = f"{self.host}/zh/censored_list/all/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    if pg == "1":
                        html = self._fetch(f"{self.host}/zh/censored_random/all/index.html")
                    else:
                        return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                pagecount = self._pagecount(html, pg)
                return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}

            elif tid == "amateur":
                path = f"{self.host}/zh/amateurjav_list/all/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    if pg == "1":
                        html = self._fetch(f"{self.host}/zh/amateurjav_random/all/index.html")
                    else:
                        return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                pagecount = self._pagecount(html, pg)
                return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}

            elif tid == "reducing":
                sub = extend.get("sub", "uncensored_list/all") if extend else "uncensored_list/all"
                path = f"{self.host}/zh/{sub}/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                return {"list": videos, "page": pg, "pagecount": self._pagecount(html, pg), "limit": 24, "total": 99999}

            elif tid == "animation":
                sub = extend.get("sub", "animation_list/all") if extend else "animation_list/all"
                path = f"{self.host}/zh/{sub}/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                return {"list": videos, "page": pg, "pagecount": self._pagecount(html, pg), "limit": 24, "total": 99999}

            elif tid == "dt":
                path = f"{self.host}/zh/dt_list/all/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    if pg == "1":
                        html = self._fetch(f"{self.host}/zh/dt_random/all/index.html")
                    else:
                        return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                pagecount = self._pagecount(html, pg)
                return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}

            elif tid == "categorylist":
                if not extend or not extend.get("sub"):
                    html = self._fetch(f"{self.host}/zh/chinese_categorylist/list/index.html")
                    if "站点维护中" in html or len(html) < 2000:
                        return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 99999}
                    videos = []
                    seen = set()
                    for m in re.finditer(r'<div class=[\'"]post[\'"]>\s*<span class=[\'"]categorylist[\'"]>\s*<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>', html, re.S | re.I):
                        href = m.group(1)
                        name = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                        if not href or not name: continue
                        mm = re.search(r'/zh/chinese_category/(\d+)/([^/]+)/(\d+)\.html', href)
                        if mm:
                            vod_id = f"folder$category_{mm.group(1)}_{mm.group(2)}"
                            if vod_id not in seen:
                                seen.add(vod_id)
                                videos.append({"vod_id": vod_id, "vod_name": name, "vod_pic": "", "vod_remarks": "", "vod_tag": "folder"})
                    return {"list": videos, "page": pg, "pagecount": 1, "limit": 24, "total": 99999}
                else:
                    sub_val = extend.get("sub", "")
                    mm = re.match(r'category_(\d+)_(.+)', sub_val)
                    if mm:
                        cat_id, cat_name = mm.group(1), mm.group(2)
                        path = f"{self.host}/zh/chinese_category/{cat_id}/{cat_name}/{pg}.html"
                        html = self._fetch(path)
                        if "站点维护中" in html or len(html) < 2000:
                            return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                        videos = self._parse_posts(html)
                        return {"list": videos, "page": pg, "pagecount": self._pagecount(html, pg), "limit": 24, "total": 99999}
                    return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}

            elif tid == "news":
                sub_val = extend.get("sub", "") if extend else ""
                year_val = extend.get("year", "") if extend else ""
                mm = re.match(r'news_(\d{4}-\d{2}-\d{2})', str(sub_val)) if sub_val else None
                if mm:
                    date_val = mm.group(1)
                    path = f"{self.host}/zh/content_news/all/{date_val}.html"
                    html = self._fetch(path)
                    if "站点维护中" in html or len(html) < 2000:
                        return {"list": [], "page": "1", "pagecount": 1, "limit": 24, "total": 99999}
                    return {"list": self._parse_posts(html), "page": "1", "pagecount": 1, "limit": 24, "total": 99999}
                if year_val:
                    html = self._fetch(f"{self.host}/zh/content_news/all/2017-01-12.html")
                    if "站点维护中" in html or len(html) < 2000:
                        return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 99999}
                    year = str(year_val)
                    page_num = int(pg) if str(pg).isdigit() else 1
                    batch_size = 24
                    start = (page_num - 1) * batch_size
                    end = start + batch_size
                    dates = sorted({d for d in re.findall(r'/zh/content_news/all/(%s-\d{2}-\d{2})\.html' % re.escape(year), html)}, reverse=True)
                    total = len(dates)
                    pagecount = (total + batch_size - 1) // batch_size if total else 1
                    videos = []
                    for date_str in dates[start:end]:
                        videos.append({"vod_id": f"folder$news_{date_str}", "vod_name": date_str, "vod_pic": "", "vod_remarks": "", "vod_tag": "folder"})
                    return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}
                html = self._fetch(f"{self.host}/zh/content_news/all/2017-01-12.html")
                if "站点维护中" in html or len(html) < 2000:
                    return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 99999}
                blocks = re.findall(r'<td class=[\'"]history_update_cbg2[\'"][^>]*>(.*?)</td>', html, re.S | re.I)
                page_num = int(pg) if pg.isdigit() else 1
                batch_size = 3
                start = (page_num - 1) * batch_size
                end = start + batch_size
                total = len(blocks)
                pagecount = (total + batch_size - 1) // batch_size if total else 1
                videos = []
                seen = set()
                for block in blocks[start:end]:
                    for m in re.finditer(r'<a href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>', block):
                        href = m.group(1)
                        text = m.group(2)
                        dm = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                        if dm:
                            date_str = dm.group(1)
                            count_m = re.search(r'\((\d+)筆\)', text)
                            count = count_m.group(1) + "筆" if count_m else ""
                            dm2 = re.search(r'/zh/content_news/all/(\d{4}-\d{2}-\d{2})\.html', href)
                            if dm2:
                                vod_id = f"folder$news_{dm2.group(1)}"
                                if vod_id not in seen:
                                    seen.add(vod_id)
                                    videos.append({"vod_id": vod_id, "vod_name": date_str, "vod_pic": "", "vod_remarks": count, "vod_tag": "folder"})
                return {"list": videos, "page": pg, "pagecount": pagecount, "limit": 24, "total": 99999}

            elif tid == "custom":
                sub = extend.get("sub", "春药") if extend else "春药"
                path = f"{self.host}/zh/fc_search/all/{quote(sub, safe='')}/{pg}.html"
                html = self._fetch(path)
                if "站点维护中" in html or len(html) < 2000:
                    return {"list": [], "page": pg, "pagecount": int(pg), "limit": 24, "total": 99999}
                videos = self._parse_posts(html)
                return {"list": videos, "page": pg, "pagecount": self._pagecount(html, pg), "limit": 24, "total": 99999}

            else:
                return {"list": [], "page": pg, "pagecount": int(pg) if pg.isdigit() else 1, "limit": 24, "total": 99999}

        except Exception:
            return {"list": [], "page": pg, "pagecount": int(pg) if pg.isdigit() else 1, "limit": 24, "total": 99999}

    def _pagecount(self, html, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        if html:
            nums = re.findall(r'href=["\']([^"\']*/(\d+)\.html)["\']', html)
            if nums:
                pg = max(int(x[1]) for x in nums)
        return pg

    def _news_years(self):
        """读取每日更新历史页，提取全部年份（去重倒序）；6小时缓存，失败回退 2026..2016"""
        now = time.time()
        if Spider._news_years_cache and (now - Spider._news_years_ts) < 6 * 3600:
            return Spider._news_years_cache
        years = []
        try:
            html = self._fetch(f"{self.host}/zh/content_news/all/2017-01-12.html")
            if html and '站点维护中' not in html:
                dates = re.findall(r'/zh/content_news/all/(\d{4}-\d{2}-\d{2})\.html', html)
                years = sorted({d[:4] for d in dates}, reverse=True)
        except Exception:
            pass
        if not years:
            years = [str(y) for y in range(2026, 2015, -1)]
        Spider._news_years_cache = years
        Spider._news_years_ts = now
        return years

    # ===== 详情接口 =====
    def detailContent(self, ids):
        try:
            return self._detailContent_inner(ids)
        except Exception:
            return {'list': []}

    def _detailContent_inner(self, ids):
        vid = str(ids[0] if isinstance(ids, list) else ids)
        ctype, num, slug = vid.split('#', 2)
        if _is_novel(ctype):
            return self._novel_detail(vid, ctype, num, slug)
        elif _is_image(ctype):
            return self._image_detail(vid, ctype, num, slug)
        else:
            return self._video_detail(vid, ctype, num, slug)

    def _video_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not title:
            m = re.search(r'<title>([^<]+)</title>', text)
            if m: title = m.group(1).strip()
        cover = ''
        m = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', text)
        if m: cover = m.group(1)
        if not cover:
            m = re.search(r"<meta[^>]*property=\"og:image\"[^>]*content=\"([^\"]+)\"", text)
            if m: cover = m.group(1)
        if not cover:
            m = re.search(r"<div class='post'>.*?<img[^>]*src='([^']+)'", text, re.S)
            if m: cover = m.group(1)

        m = re.search(r'hadeedg252=(\d+)', text)
        if not m: return {'list': []}
        hadeedg252 = int(m.group(1))
        m = re.search(r'hcdeedg252=(\d+)', text)
        if not m: return {'list': []}
        hcdeedg252 = int(m.group(1))
        m = re.search(r"var argdeqweqweqwe = '([^']+)'", text)
        if not m: return {'list': []}
        aes_key = m.group(1)
        m = re.search(r"var hdddedg252 = '([^']+)'", text)
        if not m: return {'list': []}
        aes_iv = m.group(1)

        mm = re.search(r"mvarr\['10_1'\]=(\[.*?\]);", text, re.S)
        if not mm: return {'list': []}
        mvarr_str = mm.group(1)
        items = re.findall(r"\['([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\]", mvarr_str)
        if not items: return {'list': []}

        urls = []
        for iframe_id, enc, html, prefix, empty, label in items:
            if not enc or not prefix: continue
            pid = self._decrypt_id(enc, hadeedg252, hcdeedg252, aes_key, aes_iv)
            if not pid: continue
            for res, label_name in [('480', '480P'), ('720', '720P'), ('1080', '1080P')]:
                urls.append(f'{label_name}${num}|{slug}|{pid}|{res}')

        if not urls: return {'list': []}
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': self._proxy_url(cover),
            'vod_content': '',
            'vod_remarks': '',
            'vod_play_from': self.getName(),
            'vod_play_url': '#'.join(urls),
        }
        return {'list': [vod]}

    def _novel_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        content = ''
        m = re.search(r"id=['\"]novel_content_txtsize['\"][^>]*>(.*?)</div>", text, re.S)
        if m:
            raw = m.group(1)
            content = re.sub(r'<[^>]+>', '', raw)
            content = re.sub(r'&nbsp;', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
        if not content:
            m = re.search(r"<span class='content_18h_wpcg'>([\s\S]*?)</span>\s*<div class='contents'", text)
            if m:
                raw = m.group(1)
                content = re.sub(r'<[^>]+>', '', raw)
                content = re.sub(r'&nbsp;', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()
        if len(content) > 3000:
            content = content[:3000] + '...'
        novel_json = json.dumps({'title': title, 'content': content}, ensure_ascii=False)
        play_url = f'阅读$novel://{novel_json}'
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': '',
            'vod_content': '',
            'vod_remarks': '',
            'vod_play_from': '小说',
            'vod_play_url': play_url,
            'vod_tag': 'text',
            'vod_player': '书',
        }
        return {'list': [vod]}

    def _image_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        cover = ''
        m = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', text)
        if m: cover = m.group(1)
        all_imgs = re.findall(r"src=['\"]([^'\"]*eemmhh02\.com/[^'\"]+\.(?:jpg|png|webp))['\"]", text, re.I)
        big_imgs = []
        seen = set()
        for img in all_imgs:
            if img in seen:
                continue
            seen.add(img)
            big_imgs.append(self._proxy_url(img))
        if not big_imgs:
            return {'list': []}
        pics = '&&'.join(big_imgs)
        play_url = f'查看$pics://{pics}'
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': self._proxy_url(cover),
            'vod_content': f'共 {len(big_imgs)} 张图片',
            'vod_remarks': str(len(big_imgs)) + 'P',
            'vod_play_from': '图片',
            'vod_play_url': play_url,
            'vod_tag': 'image',
            'vod_player': '画',
        }
        return {'list': [vod]}

    def _decrypt_id(self, enc, xor_key, base, aes_key, aes_iv):
        try:
            sep = chr(base + 97)
            parts = enc.split(sep)
            s1 = ''.join(chr(int(p, base) ^ xor_key) for p in parts if p)
            data = base64.b64decode(s1)
            plain = _aes_cbc_decrypt(data, aes_key.encode(), aes_iv.encode())
            return plain.decode('utf-8')
        except Exception:
            return ''

    # ========== 搜索功能（改造：自动抓取 1～10 页并合并） ==========
    def searchContent(self, key, quick, pg="1"):
        try:
            return self._searchContent_inner(key, quick, pg)
        except Exception:
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _searchContent_inner(self, key, quick, pg="1"):
        all_videos = []
        key_path = quote(key, safe="")
        max_pages = 10

        def fetch_page(page):
            try:
                html = self._fetch(f"{self.host}/zh/chinese_search/all/{key_path}/{page}.html")
                if "站点维护中" in html or len(html) < 2000:
                    return []
                videos = self._parse_posts(html)
                return [v for v in videos if v.get("vod_id")]
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=min(max_pages, 5)) as ex:
            futures = [ex.submit(fetch_page, p) for p in range(1, max_pages + 1)]
            for f in as_completed(futures, timeout=25):
                try:
                    result = f.result()
                    if result:
                        all_videos.extend(result)
                except Exception:
                    continue

        return {"list": all_videos, "page": 1, "pagecount": 1, "limit": 24, "total": len(all_videos)}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            return self._playerContent_inner(flag, id, vipFlags)
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}, 'position': '0'}

    def _playerContent_inner(self, flag, id, vipFlags=None):
        if id.startswith('novel://'):
            return {'parse': 0, 'url': id, 'header': '', 'vod_player': '书'}
        if id.startswith('pics://'):
            return {'parse': 0, 'playUrl': '', 'url': id, 'header': self.headers}
        try:
            num, slug, pid, res = id.split('|', 3)
        except ValueError:
            return {'parse': 1, 'url': id, 'header': self.headers}
        url = f'{self.host}/js/player/play.php?numresolution={res}&lo=on&id={pid}'
        text = self._fetch(url)
        m3u8 = ''
        if text:
            mm = re.search(r'videoSources\s*=\s*(\[.*?\]);', text, re.S)
            if mm:
                arr = mm.group(1)
                sources = re.findall(r"src:\s*'([^']+)'[^}]*?size:\s*(\d+)", arr, re.S)
                if sources:
                    target = int(res) if str(res).isdigit() else 0
                    for u, s in sources:
                        if int(s) == target:
                            m3u8 = u
                            break
                    if not m3u8:
                        m3u8 = sources[0][0]
            if not m3u8:
                mm = re.search(r'https?://[^\s"<>\']+?\.m3u8', text)
                if mm: m3u8 = mm.group(0)
        if m3u8:
            return {'parse': 0, 'url': m3u8, 'header': {'Referer': self.host + '/'}, 'position': '0'}
        else:
            return {'parse': 1, 'url': id, 'header': self.headers}