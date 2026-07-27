# 浏览器后端路由

## 固定选择

当前 Skill 只使用已经安装并加载的 `aialra-shopping-browser`

它通过本地标准输入输出协议启动官方 Playwright MCP，并打开独立可视 Chrome

后端必须在第一次访问拼多多以前确定

第一次访问成功后，搜索和详情节点必须继续使用同一后端

## 允许的操作

- 打开受允许的官方网页
- 读取可见页面结构和文字
- 在搜索框输入查询词
- 点击只读筛选和排序控件
- 等待页面完成加载
- 截取用于核验的页面截图

## 禁止的操作

- 读取或导出 Cookie、本地存储、密码和浏览器历史
- 下单、加购、领券、订阅、关注、联系商家和发布内容
- 破解验证码、人机检查或短信验证
- 使用代理轮换、指纹伪装和隐身浏览器
- 在策略阻止后切换其他工具绕过

## 开源候选审计

| 项目 | 许可证 | 处理决定 |
|---|---|---|
| [wfgsss/pinduoduo-scraper-example](https://github.com/wfgsss/pinduoduo-scraper-example) | MIT | 可参考商品字段，但住宅代理和会话保存方案不进入本项目 |
| [OFZFZS/scrapy-pinduoduo](https://github.com/OFZFZS/scrapy-pinduoduo) | BSD-2-Clause | 可参考评论字段，不采用旧接口和固定选择器 |

没有明确许可证的项目只能学习公开思路，不能复制代码

本仓库没有复制以上候选项目的实现代码
