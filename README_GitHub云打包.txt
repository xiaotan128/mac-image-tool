GitHub 云打包 Mac APP 方法

你不需要 Mac，也不需要本机安装 Python。

步骤：
1. 登录 GitHub，新建一个仓库，比如 mac-image-tool。
2. 把这个文件夹里的所有内容上传到仓库根目录。
   注意：.github 文件夹也必须上传。
3. 打开仓库页面，点上方 Actions。
4. 左侧选择 Build macOS app。
5. 点 Run workflow。
6. 等几分钟，运行完成后，点这个运行记录。
7. 页面底部 Artifacts 里面下载“框选导出_2MB版_macOS”。
8. 解压后就是“框选导出_2MB版.app”。

第一次在 Mac 上打开可能提示来自未知开发者：
右键 app -> 打开 -> 再点打开。

说明：
GitHub Actions 用的是 GitHub 提供的 macOS 云机器，所以能真正打出 Mac 可运行的 .app。
