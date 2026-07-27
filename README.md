# 拼多多价格研究 Skill

## 这个仓库能做什么

这个仓库保存一个只读的 `pinduoduo-price-research` Skill

用户要求研究拼多多当前商品价格时，Agent 会执行多轮官方网页搜索，核验详情页、图片、卖家、评价、价格条件和购买风险，然后给出最低价可行结论

## 它不会做什么

- 不会下单、加购、领券、订阅、联系商家或发布评价
- 不会导出 Cookie、密码、验证码和浏览器存储
- 不会破解验证码或伪装浏览器指纹
- 不会把搜索摘要或记忆中的价格当作当前证据

## 它怎样工作

平台 Skill 负责规划查询、定义证据和计算风险

已安装的 `AIALRA Shopping Browser` 插件负责启动独立可视 Chrome 并读取官方页面

登录资料保存在浏览器自己的本地目录，不进入这个 Git 仓库

## 主要目录

| 位置 | 用途 |
|---|---|
| `.agents/skills/pinduoduo-price-research/SKILL.md` | 告诉 Agent 何时触发以及必须遵守什么 |
| `.agents/skills/pinduoduo-price-research/workflow.yaml` | 固定节点顺序、执行器、权限、失败路径和停止条件 |
| `.agents/skills/pinduoduo-price-research/schemas/` | 定义每个节点允许接收和返回的数据形状 |
| `.agents/skills/pinduoduo-price-research/scripts/` | 运行工作流、去重、排名和验证结果 |
| `.agents/skills/pinduoduo-price-research/references/` | 保存浏览器、多轮采集、风险和验收说明 |
| `tests/` | 验证成功路径和安全失败路径 |
| `learning/` | 只保存脱敏经验和待审计提案 |

## 怎样安装

在仓库根目录运行

```bash
python3 scripts/install_local.py
```

安装程序会把 Skill 连接到 Codex 的个人 Skill 目录

## 怎样验证

在仓库根目录运行

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
python3 scripts/check_secrets.py .
```

全部命令成功后，仓库结构、工作流、领域规则、测试和敏感信息扫描才算通过

## 怎样开始真实任务

新建 Codex 任务并输入

```text
使用 $pinduoduo-price-research 多轮搜索并核验拼多多当前最低价可行商品
```

真实网站要求登录、短信或验证码时，Agent 会暂停并等待用户操作

## 安全提醒

不要把 Cookie、账号、密码、验证码、详细地址、订单和页面存储文件提交到 Git

发现敏感信息时立即停止提交，移除内容后再运行敏感信息扫描
