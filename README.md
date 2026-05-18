# JustRunMy.App 自动续期

## 当前能力

- 多账号执行，账号顺序随机。
- GitHub Actions 每天北京时间 06:00 触发检查，按锚点日期严格每 2 天执行一次。
- 支持 `vless/vmess/tuic/hy2/socks5/http` 等代理格式。
- `vless + xhttp` 自动切换为 `Xray`，其他协议继续使用 `sing-box`。
- 自动处理登录页和续期弹窗中的 Cloudflare Turnstile。
- 失败时发送 Telegram 通知与截图，并上传 Actions artifact。

## Secrets

| 名称 | 是否必填 | 说明 |
| --- | --- | --- |
| `EML_1`, `EML_2` ... | 是 | 账号邮箱 |
| `PWD_1`, `PWD_2` ... | 是 | 对应密码 |
| `PROXY_URL` | 否 | 代理链接 |
| `TG_TOKEN` | 否 | Telegram Bot Token |
| `TG_ID` | 否 | Telegram Chat ID |

## 执行逻辑

1. `schedule` 每天触发一次。
2. `setup` 依据锚点日期判断当天是否属于“两天一次”的执行日。
3. 从 `EML_x` 提取账号索引并随机打乱。
4. `renew` 按随机顺序串行执行账号。
5. 浏览器路线为 `DrissionPage + Chromium + Turnstile patch`。
6. `PROXY_URL` 为 `xhttp` 时使用 `Xray`，其余情况使用 `sing-box`。

## 调试

- 失败截图会上传到 `debug-acc-x` artifact。
- 登录页失败常见截图：
  - `login_turnstile_fail.png`
  - `login_failed.png`
- 续期失败常见截图：
  - `renew_account_restricted.png`
  - `renew_app_not_found.png`
  - `renew_turnstile_fail.png`

## 已验证路线

- `Playwright/Camoufox` 坐标点击路线不能稳定通过当前 Turnstile。
- 成功路线是：
  1. 使用 Chromium 浏览器。
  2. 在页面启动前加载 `turnstilePatch` 扩展，补充 `MouseEvent.screenX/screenY`。
  3. 使用 DrissionPage 进入 Turnstile 的 shadow DOM。
  4. 点击真实 checkbox 输入节点。
  5. 以 `cf-turnstile-response` token 是否生成作为通过标准。
