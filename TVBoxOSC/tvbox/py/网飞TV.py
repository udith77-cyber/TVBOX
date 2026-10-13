import requests  # 导入网络请求库
from bs4 import BeautifulSoup  # 导入网页解析库
import re  # 导入正则表达式库
from base.spider import Spider  # 导入基础爬虫父类
import json  # 导入json处理库

xurl = "https://www.wangfei.tv"  # 主站地址（线路播放站域名取自详情页）
headerx = {  # 请求头字典
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Referer': 'https://www.wangfei.tv/',
}
线路域名们 = [  # 各线路外部站点（主站详情「观看方式」一栏，随网站可能变动）
    "https://www.158399.xyz", "https://www.159299.xyz", "https://www.158766.xyz",
    "https://www.158799.xyz", "https://www.673981.xyz", "https://www.736189.xyz",
    "https://www.753982.xyz", "https://www.915764.xyz", "https://www.958267.xyz",
]


def getHtml(url, 换线路=False):  # 请求页面文本；外部线路站失败时自动换其它线路域名重试
    def _取(地址):  # 单地址请求，编码乱码时按页面实际声明修正，TLS失败降级http再试
        响应 = requests.get(url=地址, headers=headerx, timeout=15)
        响应.encoding = 响应.apparent_encoding or 'utf-8'  # 服务端未声明charset时按实际字节推断，防标题乱码
        try:
            return 响应.text
        except Exception:
            if 'https://' in 地址:  # 握手失败则降http再试一次
                try:
                    备用 = requests.get(url=地址.replace('https://', 'http://', 1), headers=headerx, timeout=15)
                    备用.encoding = 备用.apparent_encoding or 'utf-8'
                    return 备用.text
                except Exception:
                    return None
            return None
    if 换线路 and 'http' in url and 'wangfei.tv' not in url:
        域名 = re.sub(r'^https?://', '', url).split('/')[0]
        路径 = re.sub(r'^https?://[^/]+', '', url)  # 取路径部分（如 /vodplay/xxx.html）
        for 备选 in [d for d in 线路域名们 if d[8:] != 域名]:
            结果 = _取(备选 + 路径)
            if 结果:
                return 结果
        return ''  # 全部线路失败
    结果 = _取(url)
    if 结果 is None:
        raise requests.exceptions.RequestException('连接失败')  # 主站请求失败如实抛出
    return 结果


def 补全(url):  # 相对地址补全域名
    if url and 'http' not in url:
        return xurl + url
    return url


def 提取演员(元素):  # 从详情页元素提取演员/导演名列表
    if not 元素:
        return []
    链接们 = 元素.find_all('a')
    if 链接们:
        演员列表 = [链接.get_text(strip=True) for 链接 in 链接们 if 链接.get_text(strip=True)]
        if 演员列表:
            return 演员列表
    文本 = 元素.get_text(strip=True)
    文本 = re.sub(r'\s+', '', 文本)
    return [文本] if 文本 else []


def 拼接演员(演员列表, 类型='wd'):  # 将演员/导演数组拼接成带搜索跳转标签的字符串（wd=关键词、actor=演员、director=导演）
    if not 演员列表:
        return ''
    部分列表 = []
    for 演员 in 演员列表:
        if 演员:
            部分列表.append(f'[a=cr:{{"id":"search://{类型}://{演员}","name":"{演员}"}}/]{演员}[/a]')
    return ' '.join(部分列表)


def getList(html, 来源='列表页'):  # 解析列表/搜索页html，提取影片列表数据
    videos = []
    源码 = BeautifulSoup(html, "html.parser")
    if 来源 == '搜索页':  # 搜索页条目为 module-card-item
        for 卡片 in 源码.select('div.module-card-item'):
            a = 卡片.find('a', class_='module-card-item-poster') or 卡片.find('a')
            图片 = a.find('img') if a else None
            标题 = 卡片.select_one('.module-card-item-title strong')
            if not (a and 图片):
                continue
            vod = {}
            vod["vod_name"] = 标题.get_text(strip=True) if 标题 else a.get('title', '')
            vod["vod_id"] = 补全(a.get('href', ''))
            vod["vod_pic"] = 补全(图片.get('src') or 图片.get('data-src'))
            类别 = 卡片.select_one('.module-card-item-class')
            信息们 = 卡片.select('.module-info-item-content')
            vod["type_name"] = 类别.get_text(strip=True) if 类别 else ''
            vod["vod_remarks"] = 信息们[0].get_text(strip=True) if 信息们 else ''  # 年份/地区/类型
            videos.append(vod)
    else:  # 列表页/分类页/首页条目为 module-poster-item
        for 影片 in 源码.select('a.module-poster-item.module-item'):
            图片 = 影片.find('img')
            标题 = 影片.select_one('.module-poster-item-title')
            vod = {}
            vod["vod_name"] = 标题.get_text(strip=True) if 标题 else 影片.get('title', '')
            vod["vod_id"] = 补全(影片.get('href', ''))
            vod["vod_pic"] = 补全(图片.get('src') if 图片 else '')
            videos.append(vod)
    return videos  # 返回影片列表


class Spider(Spider):  # 爬虫类，继承基础Spider类
    global xurl
    global headerx

    def getName(self):  # 获取爬虫名称
        return "网飞TV"

    def init(self, extend):  # 爬虫初始化方法
        pass

    def isVideoFormat(self, url):  # 判断链接是否为视频直链
        pass

    def manualVideoCheck(self):  # 手动校验视频开关
        pass

    def localProxy(self, params):  # 本地代理方法
        pass

    def homeContent(self, filter):  # 首页分类数据
        result = {"class": [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "剧集"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "5", "type_name": "纪录"},
            {"type_id": "47", "type_name": "短剧"},
        ]}
        return result  # 返回分类结果

    def homeVideoContent(self):  # 首页影片列表内容
        resp = getHtml(xurl)  # 请求首页获取网页文本
        result = {'list': getList(resp)}  # 解析首页影片列表
        return result  # 返回首页影片数据

    def categoryContent(self, cid, pg, filter, ext):  # 分类列表内容
        result = {}
        if isinstance(cid, str) and cid.startswith('search://'):  # 搜索跳转兼容：解析 类型://目标
            目标 = cid.replace('search://', '')
            if 目标.startswith('director://'):  # 导演搜索
                类型, 关键词 = 'director', 目标.replace('director://', '')
            elif 目标.startswith('actor://'):  # 演员搜索
                类型, 关键词 = 'actor', 目标.replace('actor://', '')
            else:  # 默认按关键词搜索
                类型, 关键词 = 'wd', 目标
            编码词 = requests.utils.quote(关键词)
            url = f'{xurl}/vodsearch/{类型}/{编码词}.html' if pg in (1, '1') else f'{xurl}/vodsearch/page/{pg}/{类型}/{编码词}.html'
        else:
            url = f'{xurl}/vodshow/id/{cid}.html' if pg in (1, '1') else f'{xurl}/vodshow/id/{cid}/page/{pg}.html'
        resp = getHtml(url)  # 请求搜索/分类页获取html
        result = {'list': getList(resp, 来源='搜索页' if isinstance(cid, str) and cid.startswith('search://') else '列表页')}  # 解析影片列表
        源码 = BeautifulSoup(resp, "html.parser")
        尾页 = 源码.select_one('a[title="尾页"]')
        result['pagecount'] = int(尾页.get('href').split('page/')[1].split('.html')[0]) if 尾页 and 'page/' in 尾页.get('href', '') else 1  # 从尾页链接提取总页数
        result['page'] = pg  # 当前页码
        result['limit'] = 40  # 每页条数
        result['total'] = 9999  # 总条数（模拟值）
        return result  # 返回分类列表结果

    def detailContent(self, ids):  # 获取影片详情信息
        did = ids[0]  # 取出影片详情链接
        if 'http' not in did:
            did = xurl + did  # 拼接域名生成完整url
        源码 = BeautifulSoup(getHtml(did), "html.parser")  # 请求详情页并解析
        vod = {}
        vod["vod_id"] = did  # 影片详情链接
        标题 = 源码.select_one('.vod-title-main')
        vod["vod_name"] = 标题.get_text(strip=True) if 标题 else 源码.select_one('h1').get_text(strip=True)  # 影片名称
        图片 = 源码.select_one('.module-info-poster img')
        vod["vod_pic"] = 补全(图片.get('src') if 图片 else '')  # 封面图片地址
        # 元信息：首播/上映、进度（状态备注）
        进度 = 源码.select_one('.age-meta-pub-prog .module-info-item-content:last-of-type')
        vod["vod_remarks"] = 进度.get_text(strip=True) if 进度 else ''  # 更新状态
        上映 = 源码.select_one('.age-meta-pub-prog .module-info-item-content')
        vod["vod_year"] = (上映.get_text(strip=True).split('-')[0] if 上映 else '')  # 上映年份
        # 地区/类型标签
        标签们 = 源码.select('.module-info-tag-link a')
        vod["vod_area"] = 标签们[0].get_text(strip=True) if 标签们 else ''  # 制片地区
        类型们 = [t.get_text(strip=True) for t in 标签们 if 'vodshow/class' in t.get('href', '')]
        vod["type_name"] = ','.join(类型们)  # 影片类型
        # 导演/主演
        信息项们 = 源码.select('div.module-info-item')
        for 项 in 信息项们:
            标签文本 = 项.select_one('.module-info-item-title')
            if not 标签文本:
                continue
            前缀 = 标签文本.get_text(strip=True).replace('：', '')
            if 前缀 == '导演':
                vod["vod_director"] = 拼接演员(提取演员(项.select_one('.module-info-item-content')), 类型='director')
            elif 前缀 == '主演':
                vod["vod_actor"] = 拼接演员(提取演员(项.select_one('.module-info-item-content')), 类型='actor')
        # 简介
        简介 = 源码.select_one('.module-info-introduction p')
        vod["vod_content"] = 简介.get_text(strip=True) if 简介 else ''  # 影片简介
        # 播放线路：主站详情页「观看方式」给出各线路外部站点，剧集列表需进线路站获取
        当前线路们 = []
        for a in 源码.select('.age-watch-pane a.module-play-list-link'):
            href = a.get('href', '')
            if re.match(r'^https?://(?!www\.wangfei)', href):  # 外部线路站点（如 158399.xyz）
                当前线路们.append(href)
        # 与全局线路域名们合并去重（页面线路优先）
        全部线路们 = list(dict.fromkeys(当前线路们 + 线路域名们))
        ktabs = []  # 存储播放线路名称
        klists = []  # 存储各线路剧集播放地址
        for 线路 in 全部线路们:  # 逐条线路取剧集，某线路失败自动换下一条
            线路html = getHtml(线路, 换线路=True)
            if not 线路html:
                continue
            线路站 = BeautifulSoup(线路html, "html.parser")
            播放列表 = 线路站.select('a.module-play-list-link')  # 线路站内的剧集链接
            klist = []
            for LB in 播放列表:
                播放标题 = LB.get_text(strip=True) or LB.get('title', '')
                播放链接 = LB.get('href', '').split('?')[0]  # 去掉查询参数
                klist.append(f'{播放标题}${播放链接}')  # 集名$完整线路站链接（播放器可解析）
            if klist:
                线路名 = re.sub(r'^https?://www\.', '', 线路).split('/')[0]  # 取线路域作名称
                ktabs.append(f'网飞{线路名}')
                klists.append('#'.join(klist))  # 同线路多集用#分隔
                break  # 取到一条可用线路即止
        vod["vod_play_from"] = '$$$'.join(ktabs)  # 用$$$分隔多条播放线路
        vod["vod_play_url"] = '$$$'.join(klists)  # 用$$$分隔不同线路剧集列表
        result = {'list': [vod]}  # 组装详情返回数据
        return result  # 返回影片详情

    def playerContent(self, flag, id, vipFlags):  # 播放器解析，获取视频直链
        result = {}
        try:
            链接 = id if 'http' in id else xurl + id  # 播放页完整地址（线路站或主站）
            页面文本 = getHtml(链接, 换线路=True)  # 线路站播放页，失败自动换其它线路
            直链 = ''
            if 页面文本:
                正则们 = [  # 按优先级：m3u8 > mp4 > ts > 泛媒体
                    r'https?:\\?/\\?/[^\s"\'\\]+?\.m3u8[^\s"\'\\]*',
                    r'https?:\\?/\\?/[^\s"\'\\]+?\.mp4[^\s"\'\\]*',
                    r'https?:\\?/\\?/[^\s"\'\\]+?\.ts[^\s"\'\\]*',
                ]
                源码 = BeautifulSoup(页面文本, "html.parser")  # 解析播放页
                for 正则 in 正则们:
                    for 标签 in 源码.find_all('script', string=re.compile(r'm3u8|mp4|\.ts')):  # 从脚本内正则提取媒体直链
                        匹配 = re.search(正则, str(标签.string))
                        if 匹配:
                            直链 = 匹配.group(0).replace('\\/', '/')  # 还原被转义的斜杠
                            break
                    if 直链:
                        break
            if 直链:
                result["parse"] = 0  # 直链可直接播放
                result["url"] = 直链
            else:
                result["parse"] = 1  # 无法提取直链，退回播放页地址
                result["url"] = 链接
        except Exception:
            result["parse"] = 1
            result["url"] = 链接
        result["header"] = headerx  # 返回请求头信息
        return result  # 返回播放器解析结果

    def searchContent(self, key, quick, page=1):  # 搜索影片接口（支持 wd/director/actor 三种前缀）
        类型, 关键词 = 'wd', key  # 默认按关键词搜索
        if key.startswith('director://'):  # 导演搜索
            类型, 关键词 = 'director', key.replace('director://', '')
        elif key.startswith('actor://'):  # 演员搜索
            类型, 关键词 = 'actor', key.replace('actor://', '')
        编码词 = requests.utils.quote(关键词)
        url = f'{xurl}/vodsearch/{类型}/{编码词}.html' if page in (1, '1') else f'{xurl}/vodsearch/page/{page}/{类型}/{编码词}.html'  # 拼接搜索页url
        resp = getHtml(url)  # 请求搜索页html
        result = {'list': getList(resp, 来源='搜索页')}  # 解析搜索结果（卡片形态）
        result['page'] = page  # 当前页码
        result['pagecount'] = 99  # 总页数（模拟值）
        result['limit'] = 30  # 每页条数
        result['total'] = 999  # 模拟总条数
        return result  # 返回搜索结果

    def searchContentPage(self, key, quick, page):  # 分页搜索兼容方法
        return self.searchContent(key, quick, page)  # 直接调用搜索函数


if __name__ == "__main__":  # 程序入口，直接运行脚本时执行
    spider = Spider()
    spider.init("")

    # 调用分类内容测试
    # res = spider.categoryContent("1", "1", {}, {})
    # print(json.dumps(res, ensure_ascii=False, indent=2))

    # 调用详情内容测试
    # res = spider.detailContent(["/voddetail/134653.html"])
    # print(json.dumps(res, ensure_ascii=False, indent=2))

    # 调用播放内容测试
    # res = spider.playerContent("m3u8", "https://www.158399.xyz/vodplay/134653-1-1.html", {})
    # print(json.dumps(res, ensure_ascii=False, indent=2))

    # 调用搜索内容测试
    # res = spider.searchContent("喜剧之王", False)
    # print(json.dumps(res, ensure_ascii=False, indent=2))