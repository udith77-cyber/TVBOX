# Via 浏览器 v7.4.0 资源嗅探黑名单解除教程

> 目标：解除 Via 内置的嗅探域名黑名单，让优酷 / 爱奇艺 / 腾讯视频 / B站 / 喜马拉雅等站点也能正常使用资源嗅探。
> 工具：MT 管理器（手机端即可完成）。测试版本：via_v7.4.0

---

## 一、原理（先看懂再动手）

Via 的嗅探黑名单藏在混淆类 **`Lr9/k`** 里：

- 4 个 `String[]` 数组 `l / m / n / o`，分别对应配置键 `wlb / wlr / wls / wld`
- 每个数组 = 用户配置（SharedPreferences，可追加）+ **Base64 编码的内置域名**（去不掉，只能改代码）
- **嗅探用的是 `m` 数组（`wlr` 键）**，内置域名解码后是：

```
v.qq.com, youku.com, iqiyi.com, mgtv.com, bilibili.com, ximalaya.com, film.qq.com
```

- 判定入口是 `Lr9/k.a(String)`：取 URL 的 host → 域名边界匹配 → 命中返回 true
- 页面加载时（`Le8/j.o` → `Ld8/d.i`）会查一次这个名单，命中则该页面嗅探被禁用，点嗅探按钮会弹"该网站不支持资源嗅探"

**解除思路**：让 `Lr9/k.a()` 恒返回 false，名单永远查不中。只改这一个方法，不影响其他三个名单和其他功能。

---

## 二、操作步骤

### 1. 打开 APK

MT 管理器 → 找到 Via 的 APK → 点击「查看」→ 点击 `classes.dex` → 选择「DEX 编辑器++」打开。

### 2. 定位到 `Lr9/k` 类

在 DEX 编辑器里搜索其一即可：

- 搜类名：`Lr9/k`
- 或搜字符串（全包唯一，直达）：`eW91a3UuY29tLGlxaXlpLmNvbSxtZ3R2LmNvbSxxcS5jb20=`

### 3. 找到 `a(Ljava/lang/String;)Z` 方法

在 `Lr9/k` 类内搜索方法名 `a(`，认准这个特征（方法体很短，引用了 `m` 数组）：

```smali
.method public a(Ljava/lang/String;)Z
    .registers 3

    .line 1
    iget-object v0, p0, Lr9/k;->m:[Ljava/lang/String;

    .line 3
    invoke-virtual {p0, p1}, Lr9/k;->r(Ljava/lang/String;)Ljava/lang/String;

    .line 6
    move-result-object p1

    .line 7
    invoke-virtual {p0, v0, p1}, Lr9/k;->s([Ljava/lang/String;Ljava/lang/String;)Z

    .line 10
    move-result p1

    .line 11
    return p1
.end method
```

> ⚠️ 注意别改错：`Li6/d0` 类里也有个同名的 `a(Ljava/lang/String;)Z`，但它后面跟了上千行的 `.sparse-switch`，那是扩展名白名单的哈希表，**不要碰**。

### 4. 替换方法体

把上面整个方法（含 `.method` 到 `.end method`）替换为：

```smali
.method public a(Ljava/lang/String;)Z
    .registers 2

    const/4 v0, 0x0

    return v0
.end method
```

### 5. 保存、回编译、签名、安装

- DEX 编辑器点保存 → 返回 → MT 会提示回编译 dex
- 用 MT 的「APK 签名」功能签名（或直接用 MT 的「共存」/重新打包）
- 安装到手机。**如果提示签名冲突 / 安装失败，先卸载原版 Via 再装**（注意备份书签和设置）

---

## 三、验证

1. 打开 Via，进 `bilibili.com` 或 `v.qq.com` 任意视频页
2. 点菜单里的「资源嗅探」
3. 之前会弹"该网站不支持资源嗅探"，现在应该能正常列出嗅探到的资源

## 四、注意事项

- 只改 `Lr9/k.a()` 这一个方法，类里其他方法（`u()`、`r()`、`s()` 等）保持原样
- `wlb / wls / wld` 三个名单不受影响，其他功能正常
- 解除黑名单后，这些站点的视频分片 URL 很多没有扩展名、部分带 DRM 加密——**能嗅到链接不等于一定能下载播放**，这是网站侧的限制
- Via 升级后需要重新按此教程改一次（类名是混淆名，版本一变可能跟着变，届时用 Base64 字符串重新定位）

---

## 附：嗅探相关代码位置速查

| 部分 | 位置 |
|---|---|
| 嗅探入口（WebView 拦截） | `Lp4/j.shouldInterceptRequest` → `Le8/j.F` |
| 嗅探触发条件 | 请求头带 `Range: bytes=0-` |
| 扩展名白名单（75 个） | `Li6/i0.r()` → 哈希表，算法在 `Li6/d0.b()`（特征常量 `1540483477`） |
| 域名黑名单 | `Lr9/k`（`m` 数组 / `wlr` 键），判定入口 `a()` |
| 黑名单匹配逻辑 | `r()` 取 host，`s()` 域名边界匹配 |
| 名单组装 | `u()`：配置键 + Base64 内置域名按逗号切分 |
| 嗅探结果存储 | `Ld8/d`（按 tab 存 `Ld8/c` 列表） |
| 结果展示 | `Lc8/na.u1()` |
