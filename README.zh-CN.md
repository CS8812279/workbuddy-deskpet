# WorkBuddy 桌宠

一只常驻桌面的透明小鲸鱼娘，盯着 **WorkBuddy / DeepSeek Harness (DSH)** 的活儿：跑完了会蹦、要你确认会跳到屏幕中间抖、积分余额点一下就能看。

![六态](docs/states.png)

[English](README.md) | 简体中文

## 功能

| | |
|---|---|
| **任务监控** | 读取 `workbuddy.db` 与会话事件流；会话 `working → completed`、对话回合结束都会提醒 |
| **等待确认** | 捕获 `approval/asked` 事件 → 桌宠飞到屏幕中央抖动，气泡显示工具名和原因，直到你处理或点她一下 |
| **积分** | 剩余积分走官方计费接口；今日消耗按服务端余额下降量累计 |
| **DeepSeek 余额** | 用自己的 API Key 直连 `/user/balance`，**不依赖任何 DSH 插件**；今日消耗按余额下降量累计 |
| **信息面板** | 左键：积分、余额、运行中任务、DSH 会话、待确认、最近记录 |
| **九帧立绘** | 常态呼吸＋随机眨眼、工作时上下浮动＋翅膀轻扇、完成时蹦跳、待确认时抖动、困了打盹，另有开心／害羞／生气／难过四张反应脸 |
| **多角色** | 右键 →「角色」切换；往 `assets/` 里丢一个目录就能加新皮肤 |
| **DSH 动作** | 面板顶部显示 Harness 正在干什么（读写文件／跑命令／搜内容／思考中），托盘提示同步 |
| **互动** | 点一下＝摸摸（切到反应脸＋台词），连点 5 下会生气，双击开面板，拖拽会惊吓；有待确认时点一下＝已阅 |
| **设置** | 右键 → 设置：改名、导入 PNG、换提示音 WAV、逐项开关提醒、气泡停留时长 |
| **插件模式** | 随 DSH 启动、随 DSH 退出，不用手动开 |

| 面板 | 设置 |
|---|---|
| ![面板](docs/panel.png) | ![设置](docs/settings.png) |

## 依赖

- **Windows 10/11**（用了 `winsound`、`winreg`、`msvcrt`）
- **Python 3.10+**（开发机是 3.13）
- `pip install -r requirements.txt` → PySide6-Essentials、zstandard、cryptography

以下都是可选，缺了只是对应功能降级：

| 可选组件 | 缺了会怎样 |
|---|---|
| WorkBuddy 桌面客户端 | 没有任务列表、拿不到积分 |
| DSH 会话目录（`~/.dsh/sessions`） | 没有「待确认」提醒，面板里没有 DSH 会话 |
| 小鲸鱼挂件（`dsh-whale-widget`） | 什么都不影响——它只是 DeepSeek 余额的可选兜底 |
| ComfyUI | 只影响重新出图，运行时零依赖 |

DeepSeek 余额**不再依赖任何插件**：右键 → 设置 → DeepSeek 填一次 API Key（或设环境变量 `DEEPSEEK_API_KEY`），桌宠自己直连 `api.deepseek.com`。没配密钥时才回退去读小鲸鱼账本，所以那一行还留着。

## 快速开始

```bat
git clone https://github.com/CS8812279/workbuddy-deskpet.git
cd workbuddy-deskpet
pip install -r requirements.txt
python main.py
```

也可以双击 `启动桌宠.bat`（走 `pythonw`，不弹控制台）；排查问题用 `调试启动.bat`。

几个辅助参数：

```bat
python main.py --check      :: 只跑一轮采集，打印数据源状态，不开窗口
python main.py --selftest   :: 把各状态渲染到 assets/preview
python main.py --demo       :: 模拟一次待确认提醒并截屏
```

## 作为 DSH 插件运行（随宿主启停）

```bat
python tools/plugin_install.py            :: 安装（幂等，可重复跑）
python tools/plugin_install.py --off      :: 卸载
python tools/plugin_install.py --status   :: 查看状态
```

安装做了三件事：

1. 把 `plugin/` 复制到 `~/.dsh/profiles/desktop/node_modules/dsh-deskpet`，并写入 `deskpet.json`（项目路径 + 解释器路径）；
2. 往 `~/.dsh/profiles/desktop/cordis.patch.yml` 追加一段**带标记**的插入项：

   ```yaml
   - insert:
       - id: dsh-deskpet
         name: dsh-deskpet
   ```

3. 备份补丁文件、校验 YAML、用 `node` 试载入插件；任一步失败都会自动回滚。

生命周期：

- DSH 启动 → 插件 `apply()` 拉起 `pythonw main.py --parent-pid <DSH PID>`
- DSH 正常退出 → 插件 `dispose()` 结束子进程
- DSH 被强杀 → `--parent-pid` 看门狗 2 秒内发现并退出

> 补丁层只在宿主启动时读，**装完要重启 DSH**。插件托管后别再手动双击 bat，也把托盘菜单里的「开机自启」关掉——两者会抢单实例锁。

## 配置

首次运行生成 `config.json`：

```json
{
  "pet":      { "scale": 1.0, "x": null, "y": null, "always_on_top": true,
                "muted": false, "name": "墨团", "skin": "auto", "skin_file": "" },
  "alerts":   { "complete": true, "approval": true, "sound": true, "tray": true,
                "center_on_alert": true, "bubble_seconds": 9, "sound_file": "" },
  "monitor":  { "interval_ms": 2000, "lookback_minutes": 30 },
  "deepseek": { "refresh_seconds": 60, "api_key": "" },
  "credits":  { "refresh_seconds": 300, "exe": "" },
  "autostart": false
}
```

- `pet.skin`：`auto` 用 `assets/whale-girl/frames/`，`blob` 回落到程序绘制的团子。
- `deepseek.api_key`：`sk-…`。留空则退到环境变量 `DEEPSEEK_API_KEY`，再退到小鲸鱼账本。
- `credits.exe`：留空自动探测 `WorkBuddy.exe`（`%LOCALAPPDATA%\Programs\WorkBuddy` → 卸载注册表）。
- 大小 / 静音 / 置顶 / 位置也能从托盘和右键菜单改，改完立即存盘。

## 数据来源与隐私

全部本地读取，不外传。

| 来源 | 读什么 |
|---|---|
| `%USERPROFILE%\.workbuddy\workbuddy.db` | `sessions`（状态、标题、目录）、`session_usage`（请求级积分），只读 + WAL |
| `%USERPROFILE%\.dsh\sessions\**\session.v4.jsonl.zstd` | zstd 多帧 JSONL，按字节偏移增量读：`approval/asked`、`approval/decided`、`turn/end`、`session/title` |
| `%USERPROFILE%\.dsh\.dshw-usage.json` | 小鲸鱼挂件账本——DeepSeek 余额的**可选兜底** |
| `api.deepseek.com/user/balance` | DeepSeek 余额，用你自己的 API Key 调 |
| `%LOCALAPPDATA%\CodeBuddyExtension\...\workbuddy-desktop.info` + `www.codebuddy.cn` | 剩余积分 |

### DeepSeek 余额是怎么取的

取数据的顺序，命中即止：

1. 设置里的 API Key（`deepseek.api_key`）
2. 环境变量 `DEEPSEEK_API_KEY`
3. `~/.dsh/.credentials.yaml` 的 `refs.DEEPSEEK_API_KEY`（仅当它长得像 `sk-…`；DSH 平时存的是内部句柄）
4. 小鲸鱼账本 `.dshw-usage.json`（老兜底，不必须）

今日消耗按两次轮询之间 `total_balance` 的下降量累计，充值不冲抵已用；当天第一次轮询时会用挂件账本里的历史补一个基线，所以升级后不会从 0 开始算。

### 积分余额是怎么取的

与 `dsh-workbuddy-connect` 同一条链路，本项目独立实现：

1. 用 `ELECTRON_RUN_AS_NODE=1` 跑 `WorkBuddy.exe`，取回 `atRestSecretKey`；
2. `sha256(secret)` 派生 AES-256-GCM 密钥，解开 `accessToken` 外面的 `$wbEncrypted` 信封；
3. 带 Bearer 令牌 `POST /v2/billing/meter/get-user-resource`，汇总未过期套餐包的 `CycleCapacityRemain`。

几个坑：

- 查询窗口必须**足够长**（一年）。37 天窗口会漏掉年度套餐，实测 2622 vs 5277。
- ComfyUI `RemoveBackground` 返回的遮罩是反的，必须接 `InvertMask`（见 `tools/build_skin.py`）。
- 两个接口都是**非公开**实现，客户端升级后可能失效。

## 形象与皮肤

内置两套：**鲸鱼娘**（`whale-girl`，默认）和 **雪蛾**（`moth-girl`，纯黑复眼、翅膀会轻扇）。

反应表情是**独立的立绘帧**，不是贴纸：`happy / shy / angry / sad` 和大表情走同一条 Qwen 局部编辑流程，由 `MOOD_FRAME` 映射到当前情绪——所以画面里不会再出现星星、爱心这类叠加符号。

![雪蛾五态](docs/states-moth.png)

鲸鱼娘是社区角色**鲸鱼娘**（[TreapGoGo/deepseek-whale-girl](https://github.com/TreapGoGo/deepseek-whale-girl)）的二创，用本地 ComfyUI + Krea 2 生成。

```
assets/whale-girl/frames/
  idle.png  blink.png  alert.png  done.png  sleep.png   # 同尺寸、底边对齐
```

表情是**蒙版局部重绘**（`SetLatentNoiseMask` 只覆盖脸部椭圆）出来的，蒙版外与底图逐像素一致，所以切帧绝不会出现整个人位移的抽搐。

换自己的形象：右键 → 设置 → 导入 PNG（一张图充当所有状态），或直接把五张同尺寸 PNG 丢进 `frames/`。

加一个新角色（需要 ComfyUI 跑在 `127.0.0.1:8188`）：

```bat
:: Qwen-Image-2.1 局部编辑——裁头部、用自然语言描述表情、羽化贴回
python tools/qwen_faces.py --name moth-girl --image D:/art/base.png --crop 760,250,1140,590

:: Krea 2 眼带蒙版（备用）
python tools/make_skin.py --name moth-girl --image D:/art/base.png ^
    --box 822,345,1064,426 --display "雪蛾" --feather 9
```

气泡背景就是**抠好背景的毛绒素材本身**（Krea2 出图 + birefnet 抠图，见 `tools/make_bubble_art.py`）：
整张铺进气泡，轮廓直接用它自己的毛边——不裁圆角、不描边、不切边框。
为了文字可读，只在中部叠一层径向柔光，用 `CompositionMode_SourceAtop` 合成，光只会落在毛上，四角不会糊出白框。

**装不上 / 启动后没弹出来？** 分两种：

1. 包被挪进 `node_modules/.ignored/`——它不是 npm 依赖时会被包管理器扫走。
2. profile 的 `cordis.patch.yml` 被其它安装工具整体重写，手写的挂载块被冲掉（2026-10-21 发生过）。

现在插件改成 **bundle 自带声明**：`plugin/cordis.patch.yml` 里写 insert，profile 只要在
`dsh.profile.bundles` 里列出 `dsh-deskpet` 就生效，重启或重写 patch 都不会掉。
修复一律重跑：

```bat
python tools/plugin_install.py
```

**字体和台词都能改**：

- 字体：右键 → 设置 → 气泡，选字体族和字号，保存即生效
- 台词：托盘 → 编辑台词…，打开项目根目录的 `lines.json`（`happy / shy / angry / surprise / sad / idle` 六组，
  每组一个字符串数组），改完下次摸摸就用新台词；文件不存在时会自动生成一份默认的

`qwen_faces.py` 是推荐路径：只改裁出来的头部再羽化贴回，裁切框外的发丝、绒毛、光照逐像素不变。
Krea 2 必须用很窄的蒙版，而且更容易把纯黑复眼改成棕色虹膜。

`--box` 是**眼睛窄带**（x1,y1,x2,y2），不是整张脸。这几条是踩坑换来的：

- 蒙版盖整脸，模型会顺手重画虹膜——纯黑复眼一轮就变棕。只盖眼带，其余像素不动。
- 闭眼要 `denoise 0.85`；睁眼表情必须 `≤0.55`，否则改色。
- 让模型"张嘴"会画成黑红大洞，一律闭口。
- `alert` 故意复用常态帧：这张脸本来就够惊讶，红色感叹号＋抖动＋光圈足够表达。

## 目录

```
main.py              入口（--check / --selftest / --demo / --parent-pid）
app.py               编排：采集线程 → 状态机 → 窗口 / 气泡 / 托盘 / 面板
plugin/              DSH 插件包（宿主生命周期）
core/                配置、账本、父进程看门狗
monitor/             workbuddy.py · dsh.py · deepseek.py · credits.py
ui/                  桌宠窗口、立绘皮肤、气泡、面板、设置、音效、图标
tools/               皮肤生成、插件安装、冒烟测试
tests/               解析器与状态机的离线测试
```

## 测试

```bat
python tests/test_monitors.py      :: 增量解压、确认事件解析、会话状态迁移、积分增量
node tools/plugin_smoke.mjs        :: 插件拉起与回收桌宠
python tools/guard_smoke.py        :: 宿主被强杀后看门狗退出
```

## 上游与授权

- **代码**：MIT，见 [LICENSE](LICENSE)
- **角色图像**（`assets/whale-girl/`、`docs/*.png`）：CC BY-SA 4.0，基于社区鲸鱼娘形象的演绎作品，见 [NOTICE.md](NOTICE.md)
- **上游项目**：`deepseek-whale-girl`、`dsh-workbuddy-connect`、ComfyUI、Krea 2、PySide6、zstandard、cryptography —— 完整地址与授权表见 [NOTICE.md](NOTICE.md)

## 免责声明

非官方个人项目，与腾讯、WorkBuddy、DeepSeek、Krea 均无隶属或授权关系。它会读取本机客户端的凭据文件并代你调用非公开计费接口——用的是你自己的账号，风险自负。所有处理都在本地，没有埋点。
