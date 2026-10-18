# NOTICE — 第三方组件、上游项目与素材授权

本仓库的**源代码**以 MIT 授权（见 `LICENSE`）。
`assets/whale-girl/` 下的**角色图像**不是 MIT，另有授权，见下面第 2 节。

---

## 1. 上游项目（Upstream）

| 项目 | 地址 | 本仓库用到了什么 | 授权 |
|---|---|---|---|
| **deepseek-whale-girl** | https://github.com/TreapGoGo/deepseek-whale-girl | 「鲸鱼娘 / dafeiyu」角色设定（发色、女仆装、鲸尾、鲸鳍耳饰等视觉要素）作为生成底图与造型依据 | 网站代码 MIT；说明文字与生成提示词 CC BY-SA 4.0；**角色设定图与社区投稿不包含在上述许可内，遵循原作者授权** |
| **dsh-workbuddy-connect** | https://github.com/corrinehu/dsh-workbuddy-connect | **协议参考实现**：WorkBuddy 本地凭据的 `$wbEncrypted` 信封格式、`sha256(atRestSecretKey)` 派生方式、`WB-AAD` 构造、计费接口路径与请求体。本仓库按公开可得的信息独立实现，未复制其代码 | MIT |
| **ComfyUI** | https://github.com/comfyanonymous/ComfyUI | 本地出图工具链（`tools/` 里的工作流用它的 HTTP API 提交） | GPL-3.0 |
| **Krea 2** | https://www.krea.ai | 出图模型（本机使用的是社区微调权重 `krea2Anime_v15`） | 见模型发布方授权 |

> 本项目与腾讯、DeepSeek、Krea 均无隶属或官方授权关系。所有上游商标归各自所有者。

## 2. 角色图像授权

`assets/whale-girl/frames/*.png`（以及 `docs/states.png`）是**基于社区角色「鲸鱼娘」的二次创作**，由本地 ComfyUI + Krea 2 生成，属于原作的演绎作品。

- 本仓库对这些图像按 **CC BY-SA 4.0** 提供：https://creativecommons.org/licenses/by-sa/4.0/
- 署名（Attribution）：角色原案来自 **TreapGoGo/deepseek-whale-girl** 社区项目及其贡献者；本仓库仅做了 AI 重绘与表情差分。
- 相同方式共享（ShareAlike）：再分发这些图像（含修改）时，请保留同样的 CC BY-SA 4.0 授权与上述署名。
- 商用前请自行核实上游各作者对该角色的授权说明；上游明确声明"收录不代表拥有版权，也不代表获得再次使用授权"。

**如果你要发布自己的桌宠形象**：把 `assets/whale-girl/frames/` 换成你自己的图，或在设置里导入 PNG。替换后本节的约束对你不再适用。

## 3. 运行时依赖

| 组件 | 地址 | 授权 | 形态 |
|---|---|---|---|
| Python | https://www.python.org | PSF-2.0 | 外部运行时 |
| PySide6-Essentials | https://pypi.org/project/PySide6-Essentials/ | LGPL-3.0 / 商业双许可 | pip 依赖 |
| zstandard | https://pypi.org/project/zstandard/ | BSD-3-Clause | pip 依赖 |
| cryptography | https://pypi.org/project/cryptography/ | Apache-2.0 / BSD-3-Clause | pip 依赖 |

仅 `tools/` 目录使用、主程序不依赖：

| 组件 | 地址 | 授权 |
|---|---|---|
| Pillow | https://pypi.org/project/Pillow/ | MIT-CMU |
| PyYAML | https://pypi.org/project/PyYAML/ | MIT |

PySide6 以 LGPL 方式作为动态链接库使用，本仓库不再分发其二进制。

## 4. 宿主与数据来源

本项目读取以下**本机文件**，不包含、也不分发它们的内容：

| 来源 | 用途 |
|---|---|
| WorkBuddy 桌面客户端（`%USERPROFILE%\.workbuddy\workbuddy.db`） | 任务状态、请求级积分 |
| DeepSeek Harness（`%USERPROFILE%\.dsh\sessions`） | 会话事件流（确认请求、回合结束） |
| `%USERPROFILE%\.dsh\.dshw-usage.json` | DeepSeek 余额（**可选兜底**；主路径是用你自己的 API Key 直连官方接口，不需要任何插件） |
| `api.deepseek.com/user/balance` | DeepSeek 余额（仅在你配置了 API Key 时调用） |
| WorkBuddy 本地登录凭据 + `www.codebuddy.cn` 计费接口 | 积分余额（可选） |

计费接口与凭据格式均属**非公开实现**，上游变更可能导致失效。请自行评估账号风险。
