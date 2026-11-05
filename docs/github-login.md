# GitHub 登录

设置与更新 → GitHub 账户 → 登录 GitHub。客户端复制一次性验证码并打开 https://github.com/login/device，用户核对应用 LXTools 后授权。返回工具架显示账户名称，再刷新商店。

Client ID 为公开应用标识，采用 Device Flow，不使用 Client Secret。目前仅请求 read:user，用于身份识别及公开仓库认证请求；不申请私有仓库权限。商店始终扫描 gd-dd。

凭据通过 Windows DPAPI 加密存放于当前客户端配置目录 github-account.bin，开发与正式配置独立。退出清除本地凭据，不退出浏览器账户。彻底撤销授权可在 GitHub Settings → Applications → Authorized OAuth Apps 中撤销 LXTools。

拒绝授权、过期或网络失败后重新点击登录；取消等待后，迟到的授权结果不会写入账户。
