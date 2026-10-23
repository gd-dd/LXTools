# GitHub 登录注册：下次一起完成

当前公开商店无需登录。OAuth 尚未接入，不要把账户密码、Client Secret 或个人令牌写进工具清单或发到聊天中。

1. 用作者 GitHub 账户打开 Settings → Developer settings → OAuth Apps → New OAuth App。
2. Application name 填 `LXTool`，Homepage URL 填工具架公开仓库 `https://github.com/gd-dd/LXTools`，描述写“Windows 游戏制作工具架”。
3. 注册页要求填写 Authorization callback URL；我们接下来核对最终登录流程后一起填写。Device Flow 本身不通过此地址接收授权码。
4. 若继续采用 Device Flow，勾选 Enable Device Flow。注册后保留 Client ID，客户端只需公开的 Client ID，不嵌入 Client Secret。
5. 下一轮接入真实授权、Windows 凭据保存、退出登录、授权过期处理和私有目录访问，再测试完整登录过程。

这里先记录入口和必要信息，不要求你现在注册。GitHub 当前文档同时推荐评估 GitHub App，并限制 Device Flow 的适用场景；正式接入时会再确认客户端登录方案和最小权限，避免申请不必要的仓库权限。

参考：
- [创建 OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)
- [Device Flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow)
- [OAuth 最佳实践](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app)

核对日期：2026-10-24。

