/**
 * @name 聚合音乐
 * @description 米兔音乐 + 爱听音乐 聚合音源，支持站内搜索、播放与LRC歌词
 * @version 1.0.0
 * @author 聚合音乐
 * @homepage https://www.qqmp3.vip
 */

// 洛雪音源：仅可用 ES6+ 与 lx 提供的 API
// 聚合逻辑：musicUrl 优先米兔(qqmp3.vip)，失败自动降级爱听(22a5.com)；歌词按站点分别缓存
// 注意：米兔请求必须带 Referer；爱听需人机验证 PHPSESSID cookie（启动预热）
const { EVENT_NAMES, request, on, send } = globalThis['lx']
const lxUtils = globalThis['lx'] && globalThis['lx'].utils

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36'
const TIMEOUT = 8000
const CACHE_TTL = 10 * 60 * 1000

// 安全日志
function log() {
  try { console.log.apply(console, arguments) } catch (e) { /* ignore */ }
}

// ==================== 通用网络层 ====================

// 响应体转字符串/JSON：兼容移动端(已自动parse/对象/Buffer)与桌面端(字符串)
function bodyToText(body) {
  if (body == null) return ''
  if (typeof body === 'string') return body
  if (typeof body === 'object') {
    var isBin = false
    try {
      if (body.constructor && (body.constructor.name === 'Buffer' || body.constructor.name === 'Uint8Array')) isBin = true
      if (body.byteLength !== undefined || (body.buffer instanceof ArrayBuffer)) isBin = true
    } catch (e) { /* ignore */ }
    if (isBin) {
      try {
        if (lxUtils && lxUtils.buffer && lxUtils.buffer.bufToString) return lxUtils.buffer.bufToString(body, 'utf8')
      } catch (e) { /* ignore */ }
      try {
        var view = new Uint8Array(body.buffer ? body.buffer : body)
        var out = ''
        for (var i = 0; i < view.length; i++) out += String.fromCharCode(view[i])
        return utf8Decode(out)
      } catch (e) { /* ignore */ }
      try { return body.toString('utf8') } catch (e) { /* ignore */ }
      return ''
    }
    if (body.url !== undefined) return body.url || ''
    try { return JSON.stringify(body) } catch (e) { /* ignore */ }
  }
  try { return String(body) } catch (e) { /* ignore */ }
  return ''
}

function utf8Decode(bin) {
  var out = ''
  var i = 0
  while (i < bin.length) {
    var c = bin.charCodeAt(i)
    if (c < 0x80) { out += String.fromCharCode(c); i++ }
    else if (c < 0xe0) { out += String.fromCharCode(((c & 0x1f) << 6) | (bin.charCodeAt(i + 1) & 0x3f)); i += 2 }
    else if (c < 0xf0) {
      out += String.fromCharCode(((c & 0x0f) << 12) | ((bin.charCodeAt(i + 1) & 0x3f) << 6) | (bin.charCodeAt(i + 2) & 0x3f)); i += 3
    } else {
      var cp = ((c & 0x07) << 18) | ((bin.charCodeAt(i + 1) & 0x3f) << 12) | ((bin.charCodeAt(i + 2) & 0x3f) << 6) | (bin.charCodeAt(i + 3) & 0x3f)
      cp -= 0x10000
      out += String.fromCharCode(0xd800 + (cp >> 10), 0xdc00 + (cp & 0x3ff))
      i += 4
    }
  }
  return out
}

// 兼容两种 headers 结构：普通对象 / Headers 实例
function getHeader(resp, name) {
  if (!resp || !resp.headers) return null
  try {
    if (typeof resp.headers.get === 'function') {
      var v = resp.headers.get(name)
      if (v != null) return v
    }
  } catch (e) { /* ignore */ }
  var v = resp.headers[name] || resp.headers[name.toLowerCase()] || resp.headers[name.toUpperCase()]
  return v == null ? null : v
}

// HTTP GET（回调对齐洛雪两参数/三参数），返回 {status, text}
function httpGet(url, extraHeaders) {
  return new Promise((resolve, reject) => {
    try {
      var headers = Object.assign({ 'User-Agent': UA }, extraHeaders || {})
      request(url, { method: 'GET', headers: headers, timeout: TIMEOUT }, function (err, resp, body) {
        if (err) return reject(err)
        var b = resp && resp.body !== undefined ? resp.body : (body !== undefined ? body : '')
        resolve({ status: resp && resp.statusCode, text: bodyToText(b) })
      })
    } catch (e) { reject(e) }
  })
}

// HTTP POST（form 参数，不手动设置 Content-Type，兼容洛雪移动端）
function httpPostForm(url, form, extraHeaders) {
  return new Promise((resolve, reject) => {
    try {
      var headers = Object.assign({ 'User-Agent': UA }, extraHeaders || {})
      if (cookieStr) headers['Cookie'] = cookieStr
      request(url, { method: 'POST', headers: headers, form: form, timeout: TIMEOUT }, function (err, resp, body) {
        if (err) return reject(err)
        try { var sc = getHeader(resp, 'set-cookie'); if (sc) saveSetCookies(sc) } catch (e) { /* ignore */ }
        var b = resp && resp.body !== undefined ? resp.body : (body !== undefined ? body : '')
        resolve({ status: resp && resp.statusCode, text: bodyToText(b) })
      })
    } catch (e) { reject(e) }
  })
}

// 缓存工具
var cache = {}
function cacheGet(key) {
  var e = cache[key]
  if (e && Date.now() - e.t < e.ttl) return e.v
  return null
}
function cacheSet(key, val, ttl) {
  cache[key] = { t: Date.now(), ttl: ttl, v: val }
}

// ==================== 米兔音乐模块 (qqmp3.vip) ====================
var MITO_HOST = 'https://www.qqmp3.vip'
var MITO_REF = MITO_HOST + '/'
var MITO_LEVEL_MAP = { '128k': 'standard', '320k': 'exhigh', flac: 'lossless' }
var MITO_LEVEL_ORDER = ['lossless', 'exhigh', 'high', 'standard']

function mitoApiGet(path) {
  return httpGet(MITO_HOST + path, { 'Referer': MITO_REF }).then(function (res) {
    if (res.status === 403) return Promise.reject(new Error('米兔接口被拒绝(403)'))
    var text = res.text.trim()
    if (!text) return Promise.reject(new Error('米兔空响应'))
    try { return JSON.parse(text) } catch (e) { return Promise.reject(new Error('米兔响应非JSON')) }
  })
}

function mitoSearch(keyword) {
  var ck = 'mito_s_' + keyword
  var hit = cacheGet(ck)
  if (hit) return Promise.resolve(hit)
  return mitoApiGet('/api/songs.php?type=search&keyword=' + encodeURIComponent(keyword)).then(function (json) {
    if (!json || json.code !== 200 || !json.data) return Promise.resolve([])
    var items = []
    for (var i = 0; i < json.data.length; i++) {
      var x = json.data[i]
      if (!x || !x.rid) continue
      items.push({ rid: String(x.rid), name: String(x.name || ''), artist: String(x.artist || '') })
    }
    cacheSet(ck, items, CACHE_TTL)
    return items
  })
}

function mitoPick(items, name, singer) {
  var n = String(name || '').replace(/\s+/g, '')
  var s = String(singer || '').replace(/\s+/g, '')
  if (n && s) {
    for (var i = 0; i < items.length; i++) {
      if (items[i].name.indexOf(n) !== -1 && items[i].artist.indexOf(s) !== -1) return items[i]
    }
  }
  if (n) {
    for (var j = 0; j < items.length; j++) {
      if (items[j].name.indexOf(n) !== -1) return items[j]
    }
  }
  return items[0]
}

function getSinger(musicInfo) {
  var s = musicInfo && (musicInfo.singer || musicInfo.singerName || musicInfo.artist || '')
  if (s && typeof s !== 'string') {
    try { s = Array.isArray(s) ? s.join(' ') : String(s) } catch (e) { s = '' }
  }
  return String(s || '')
}

function mitoMatch(musicInfo) {
  var name = ((musicInfo && (musicInfo.name || musicInfo.songName)) || '').replace(/\s+/g, '')
  var singer = getSinger(musicInfo).replace(/\s+/g, '')
  var kw = buildKeyword(musicInfo) || '歌曲'
  return mitoSearch(kw).then(function (items) {
    if (!items.length && name) return mitoSearch(name)
    return items
  }).then(function (items) {
    if (!items.length) return Promise.reject(new Error('米兔站内未找到歌曲'))
    return mitoPick(items, name, singer)
  })
}

function mitoResolve(rid, quality) {
  var prefer = MITO_LEVEL_MAP[quality] || 'exhigh'
  var order = []
  var seen = {}
  function push(lv) { if (lv && !seen[lv]) { seen[lv] = true; order.push(lv) } }
  push(prefer)
  for (var i = 0; i < MITO_LEVEL_ORDER.length; i++) push(MITO_LEVEL_ORDER[i])
  push('jymaster'); push('hires')

  function tryOne(idx) {
    if (idx >= order.length) return Promise.reject(new Error('米兔播放解析失败'))
    var level = order[idx]
    var ck = 'mito_p_' + rid + '_' + level
    var hit = cacheGet(ck)
    if (hit) return Promise.resolve(hit)
    return mitoApiGet('/api/kw.php?rid=' + encodeURIComponent(rid) + '&type=json&level=' + level + '&lrc=0').then(function (json) {
      if (json && json.code === 200 && json.data && json.data.url) {
        var url = String(json.data.url).replace(/\\\//g, '/')
        if (/^https?:\/\//i.test(url)) {
          cacheSet(ck, url, CACHE_TTL)
          return url
        }
      }
      return tryOne(idx + 1)
    }).catch(function () { return tryOne(idx + 1) })
  }
  return tryOne(0)
}

function mitoLyric(rid) {
  var ck = 'mito_l_' + rid
  var hit = cacheGet(ck)
  if (hit) return Promise.resolve(hit)
  return mitoApiGet('/api/kw.php?rid=' + encodeURIComponent(rid) + '&type=json&level=exhigh&lrc=1').then(function (json) {
    var lrc = (json && json.data && json.data.lrc) ? String(json.data.lrc) : ''
    lrc = filterAds(lrc)
    cacheSet(ck, lrc, CACHE_TTL)
    return lrc
  })
}

// ==================== 爱听音乐模块 (22a5.com) ====================
var AIT_HOST = 'https://www.22a5.com'
var cookieStr = ''

function saveSetCookies(setCookieVal) {
  if (!setCookieVal) return
  var list = Array.isArray(setCookieVal) ? setCookieVal : [setCookieVal]
  for (var i = 0; i < list.length; i++) {
    var segs = String(list[i]).split(';')
    for (var j = 0; j < segs.length; j++) {
      var seg = segs[j].trim()
      if (!seg) continue
      var eq = seg.indexOf('=')
      if (eq <= 0) continue
      var key = seg.substring(0, eq).trim()
      if (/^(path|domain|expires|max-age|samesite|secure|httponly)$/i.test(key)) continue
      var val = seg.substring(eq + 1).split(',')[0].trim()
      var re = new RegExp('(^|;\\s*)' + key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=[^;]*')
      var pair = key + '=' + val
      if (re.test(cookieStr)) cookieStr = cookieStr.replace(re, '$1' + pair)
      else cookieStr = cookieStr ? cookieStr + '; ' + pair : pair
      break
    }
  }
}

function aitHttpGet(url) {
  var headers = {}
  if (cookieStr) headers['Cookie'] = cookieStr
  return httpGet(url, headers).then(function (res) {
    try { var sc = getHeader(res, 'set-cookie'); if (sc) saveSetCookies(sc) } catch (e) { /* ignore */ }
    return res
  })
}

function isVerifyPage(html) {
  return typeof html === 'string' && html.indexOf('verifyForm') !== -1
}

function aitVerify() {
  return aitHttpGet(AIT_HOST + '/').then(function (res) {
    var html = res.text
    var tokenM = /name=["']csrf_token["'][^>]*value=["']([^"']*)["']/i.exec(html)
    var token = tokenM ? tokenM[1] : ''
    if (!token) return Promise.resolve()
    return httpPostForm(AIT_HOST + '/', { csrf_token: token, human_check: 'on' }, { 'Referer': AIT_HOST + '/' }).then(function () { return Promise.resolve() })
  })
}

function aitGetPage(url) {
  if (!cookieStr) {
    return aitVerify().then(function () {
      return aitHttpGet(url)
    }).then(function (res) { return res.text })
  }
  return aitHttpGet(url).then(function (res) {
    if (isVerifyPage(res.text)) {
      return aitVerify().then(function () {
        return aitHttpGet(url)
      }).then(function (res2) { return res2.text })
    }
    return res.text
  })
}

function aitParseItems(html) {
  var items = []
  var liRe = /<li[^>]*>([\s\S]*?)<\/li>/gi
  var m
  while ((m = liRe.exec(html)) !== null) {
    if (items.length >= 40) break
    var block = m[1]
    var hrefM = /<a[^>]+href=["'](\/(?:song|mp3|radio|radiolist|radioplay)\/([^"']+\.html))["'][^>]*>/i.exec(block)
    if (!hrefM) continue
    var href = hrefM[1]
    var hrefTail = hrefM[2]
    if (/^(?:index|top|new|hot|oumei|huayu|hanguo|ribrn|male|girl|band|liuxing|dianzi|yaogun|xiha|rb|minyao|jueshi|gudian)\.html$/.test(hrefTail)) continue
    var name = ''
    var nameM = /class=["']name["'][^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)<\/a>/i.exec(block)
    if (nameM) name = nameM[1].replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').trim()
    if (!name) {
      var titleM = /<a[^>]+title=["']([^"']*)["']/i.exec(block)
      if (titleM) name = titleM[1].trim()
    }
    if (!name) continue
    if (/^(首页|新歌榜|TOP榜单|DJ舞曲|歌手|歌单|电台|高清MV|主播电台|原创歌手|音乐歌单)$/.test(name)) continue
    items.push({ id: href, name: name })
  }
  return items
}

function aitSearch(keyword) {
  var ck = 'ait_s_' + keyword
  var hit = cacheGet(ck)
  if (hit) return Promise.resolve(hit)
  var url = AIT_HOST + '/so/' + encodeURIComponent(keyword) + '/1.html'
  return aitGetPage(url).then(function (html) {
    var items = aitParseItems(html)
    cacheSet(ck, items, CACHE_TTL)
    return items
  })
}

function aitMatch(musicInfo) {
  var name = ((musicInfo && (musicInfo.name || musicInfo.songName)) || '').replace(/\s+/g, '')
  var singer = getSinger(musicInfo).replace(/\s+/g, '')
  var kw = buildKeyword(musicInfo) || '歌曲'
  return aitSearch(kw).then(function (items) {
    if (!items.length && name) return aitSearch(name)
    return items
  }).then(function (items) {
    if (!items.length) return Promise.reject(new Error('爱听站内未找到歌曲'))
    if (name && singer) {
      for (var i = 0; i < items.length; i++) {
        if (items[i].name.indexOf(name) !== -1 && items[i].name.indexOf(singer) !== -1) return items[i]
      }
    }
    if (name) {
      for (var j = 0; j < items.length; j++) {
        if (items[j].name.indexOf(name) !== -1) return items[j]
      }
    }
    return items[0]
  })
}

function aitAbs(url) {
  if (!url) return ''
  if (/^https?:/i.test(url)) return url
  return AIT_HOST + (url.charAt(0) === '/' ? '' : '/') + url
}

function aitResolve(songUrl) {
  var midM = /\/(?:song|mp3|radio|radiolist|radioplay)\/([^/]+)\.html/.exec(aitAbs(songUrl))
  if (!midM) return Promise.reject(new Error('爱听无法识别的歌曲链接'))
  var mid = midM[1]
  var ck = 'ait_p_' + mid
  var hit = cacheGet(ck)
  if (hit) return Promise.resolve(hit)
  return httpPostForm(AIT_HOST + '/js/play.php', { id: mid, type: 'music' }, {
    'Referer': aitAbs(songUrl),
    'X-Requested-With': 'XMLHttpRequest',
  }).then(function (res) {
    var text = res.text.trim()
    var url = ''
    if (/^https?:\/\//i.test(text)) url = text
    else {
      try {
        var json = JSON.parse(text)
        if (json.url) url = String(json.url).replace(/\\\//g, '/')
      } catch (e) { /* not json */ }
    }
    if (!url) return Promise.reject(new Error('爱听播放解析失败'))
    cacheSet(ck, url, CACHE_TTL)
    return url
  })
}

function aitLyric(songUrl) {
  var midM = /\/(?:song|mp3|radio|radiolist|radioplay)\/([^/]+)\.html/.exec(aitAbs(songUrl))
  if (!midM) return Promise.reject(new Error('爱听歌词链接无效'))
  var mid = midM[1]
  var ck = 'ait_l_' + mid
  var hit = cacheGet(ck)
  if (hit) return Promise.resolve(hit)
  var lrcUrl = AIT_HOST + '/plug/down.php?ac=music&lk=lrc&id=' + encodeURIComponent(mid)
  return aitHttpGet(lrcUrl).then(function (res) {
    var lrc = filterAds(res.text)
    cacheSet(ck, lrc, CACHE_TTL)
    return lrc
  })
}

// ==================== 公共函数 ====================

function buildKeyword(musicInfo) {
  var name = (musicInfo && (musicInfo.name || musicInfo.songName)) || ''
  var singer = musicInfo && (musicInfo.singer || musicInfo.singerName || musicInfo.artist || '')
  if (singer && typeof singer !== 'string') {
    try { singer = Array.isArray(singer) ? singer.join(' ') : String(singer) } catch (e) { singer = '' }
  }
  singer = singer || ''
  if (singer) return name + ' ' + singer
  return name
}

function filterAds(lrcText) {
  if (!lrcText) return ''
  var lines = String(lrcText).split(/\r?\n/)
  var out = []
  var ads = [/qqmp3/i, /米兔音乐/i, /欢迎来访.*/i, /本站.*/i, /.*广告.*/i, /QQ群.*/i, /www\..*/i, /http.*/i, /\.com.*/i, /\.cn.*/i, /\.net.*/i, /.*音乐网.*/i, /.*提供.*/i, /.*下载.*/i, /酷狗.*APP/i]
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i]
    if (/^\[\d{2}:\d{2}/.test(line)) {
      var isAd = false
      for (var j = 0; j < ads.length; j++) {
        if (ads[j].test(line)) { isAd = true; break }
      }
      if (!isAd) out.push(line)
    } else {
      out.push(line)
    }
  }
  return out.join('\n')
}

// 歌词站点缓存：musicUrl 阶段记录哪个站点命中，lyric 阶段按站点取
var siteCache = {}
function lyricKey(musicInfo) {
  var mi = musicInfo || {}
  return String(mi.hash || mi.songmid || mi.id || (mi.name + (mi.singer || ''))) || ''
}

// ==================== 聚合入口 ====================

function apiMusicUrl(musicInfo, quality) {
  var k = lyricKey(musicInfo)
  return mitoMatch(musicInfo).then(function (song) {
    if (k) siteCache[k] = { site: 'mito', id: song.rid }
    return mitoResolve(song.rid, quality)
  }).catch(function (err1) {
    return aitMatch(musicInfo).then(function (song) {
      if (k) siteCache[k] = { site: 'ait', id: song.id }
      return aitResolve(song.id)
    }).catch(function (err2) {
      throw new Error('聚合源均失败: ' + (err1 && err1.message) + ' | ' + (err2 && err2.message))
    })
  })
}

function apiLyric(musicInfo) {
  var k = lyricKey(musicInfo)
  var rec = k && siteCache[k]
  if (!rec) return Promise.resolve({ lyric: '', tlyric: '' })
  var p = rec.site === 'mito' ? mitoLyric(rec.id) : aitLyric(rec.id)
  return p.then(function (lrc) { return { lyric: lrc, tlyric: '' } })
    .catch(function () { return { lyric: '', tlyric: '' } })
}

// ==================== 注册与启动 ====================

const apis = {}
;['kg', 'tx', 'wy', 'kw', 'mg'].forEach((src) => {
  apis[src] = {
    musicUrl(musicInfo, quality) { return apiMusicUrl(musicInfo, quality) },
    lyric(musicInfo) { return apiLyric(musicInfo) },
  }
})

on(EVENT_NAMES.request, ({ source, action, info }) => {
  var api = apis[source]
  if (!api) return Promise.reject('不支持的音乐源: ' + source)
  switch (action) {
    case 'musicUrl':
      if (!info || !info.musicInfo || !info.type) return Promise.reject('参数不完整')
      return api.musicUrl(info.musicInfo, info.type).catch((err) => {
        log('[聚合音乐] musicUrl 失败:', err && err.message)
        return Promise.reject(err)
      })
    case 'lyric':
      if (!info || !info.musicInfo) return Promise.reject('参数不完整')
      return api.lyric(info.musicInfo)
    default:
      return Promise.reject('action not support: ' + action)
  }
})

send(EVENT_NAMES.inited, {
  status: true,
  sources: {
    kg: { name: '聚合音乐', type: 'music', actions: ['musicUrl', 'lyric'], qualitys: ['128k', '320k', 'flac'] },
    tx: { name: '聚合音乐', type: 'music', actions: ['musicUrl', 'lyric'], qualitys: ['128k', '320k', 'flac'] },
    wy: { name: '聚合音乐', type: 'music', actions: ['musicUrl', 'lyric'], qualitys: ['128k', '320k', 'flac'] },
    kw: { name: '聚合音乐', type: 'music', actions: ['musicUrl', 'lyric'], qualitys: ['128k', '320k', 'flac'] },
    mg: { name: '聚合音乐', type: 'music', actions: ['musicUrl', 'lyric'], qualitys: ['128k', '320k', 'flac'] },
  },
})

// 后台预热爱听人机验证
try {
  aitVerify().catch(function (e) { log('[聚合音乐] 爱听预热失败:', e && e.message) })
} catch (e) { /* ignore */ }