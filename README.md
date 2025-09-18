<div align="center">
  <a href="https://nonebot.dev/store"><img src="https://gastigado.cnies.org/d/project_nonebot_plugin_group_welcome/nbp_logo.png?sign=8bUAF9AtoEkfP4bTe2CrYhR0WP4X6ZbGKykZgAeEWL4=:0" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://gastigado.cnies.org/d/project_nonebot_plugin_group_welcome/NoneBotPlugin.svg?sign=ksAOYnkycNpxRKXh2FsfTooiMXafUh2YpuKdAXGZF5M=:0" width="240" alt="NoneBotPluginText"></p>

<h1>Monebot Plugin BDSM Message</h1>
</div>

## 📖 介绍

**BDSM Message Manager** 是一款为 [NoneBot2](https://github.com/nonebot/nonebot2) 设计的强大消息管理插件。它允许您通过简单的指令，实现消息的定时发送、转发、撤回和查询，让您的机器人能够精确、高效地执行消息操作。

## ✨ 功能

- **定时发送消息**：在指定时间自动向目标群组发送消息。
- **即时发送消息**：立即向目标群组发送消息。
- **定时转发消息**：在指定时间自动将某条消息转发到目标群组。
- **即时转发消息**：立即将某条消息转发到目标群组。
- **撤回消息**：通过回复或提供消息 ID 来撤回已发送的消息。
- **查询计划任务**：查看已安排的定时消息列表，并支持按时间、内容和群号进行筛选。
- **取消计划任务**：取消一个已安排的定时消息。
- **权限管理**：通过配置文件，精细化控制哪些用户和群组可以使用插件。
- **持久化任务队列**：即使在机器人重启后，已安排的任务也不会丢失。
- **专用日志**：所有操作都会记录在专门的日志文件中，方便调试和追踪。
- **支持特殊语法**：
  - `{at_all}`: @全体成员
  - `\\n`: 换行符

## 🔧 安装与配置

### 1. 安装

将插件文件夹 `nonebot_plugin_bdsm_message` 放入您的 NoneBot2 项目的 `src/plugins` 目录下。

### 2. 配置

首次运行插件时，会在 `data/bdsmm/` 目录下自动生成 `bdsmm_config.ini` 配置文件。

```ini
[bdsmm_Groups]
admin_groups=
receiver_groups=

[bdsmm_Admins]
admin=
```

- **`admin_groups`**: 授权使用此插件的群组ID。多个群组请用英文逗号 `,` 分隔。
- **`receiver_groups`**: 允许接收消息的目标群组ID。多个群组请用英文逗号 `,` 分隔。
- **`admin`**: 授权使用此插件的用户QQ号。多个用户请用英文逗号 `,` 分隔。如果留空，则 `admin_groups` 中的所有成员都将拥有权限。

## 📝 使用方法

您需要在已配置的 `admin_groups` 中，通过 `@机器人` 的方式发送以下指令。

### 指令格式

```
[指令类型][时间戳][消息内容][目标]
```

- **指令类型**: `sendmessage`, `forwardmessage`, `recallmessage`, `schedulemessage`, `cancelmessage`
- **时间戳**:
  - `0`: 立即执行
  - `YYYYMMDDHHMMSS` 格式: 定时执行 (例如: `20250918123000`)
  - `-1`: 用于 `cancelmessage` 指令
- **消息内容**: 您想要发送、转发或查询的具体内容。
- **目标**:
  - **群号**: 对于 `sendmessage` 和 `forwardmessage`
  - **消息ID**: 对于 `recallmessage`
  - **JobID**: 对于 `cancelmessage`

### 指令示例

#### 1. 发送消息

- **立即发送**:
  ```
  [sendmessage][0][{at_all}\\n大家好][123456789]
  ```
- **定时发送**:
  ```
  [sendmessage][20250918123000][午饭时间到了！][123456789]
  ```

#### 2. 转发消息 (需要回复一条消息)

- **立即转发**:
  ```
  [forwardmessage][0][][123456789]
  ```
- **定时转发**:
  ```
  [forwardmessage][20250918123000][][123456789]
  ```

#### 3. 撤回消息

- **通过回复撤回**:
  ```
  [recallmessage][0][][0]
  ```
- **通过消息ID撤回**:
  ```
  [recallmessage][0][12345][0]
  ```

#### 4. 查询计划任务

- **查询所有任务**:
  ```
  [schedulemessage][][][]
  ```
- **按群号筛选**:
  ```
  [schedulemessage][][][123456789]
  ```
- **按内容筛选 (支持正则表达式)**:
  ```
  [schedulemessage][][午饭][]
  ```

#### 5. 取消计划任务

- **需要提供 JobID (在创建或查询任务时会返回)**:
  ```
  [cancelmessage][-1][job_1631934600_123456789][]
  ```

## 📜 日志

插件的运行日志会保存在 `data/bdsmm/bdsmm.log` 文件中，方便您进行问题排查。

## 📦 依赖

- `nonebot2`
- `nonebot-plugin-apscheduler`

确保您已安装这些依赖。
