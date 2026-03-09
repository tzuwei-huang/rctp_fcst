#!/bin/bash

# 專案名稱
PROJECT_NAME="rctp_fcst_tg_bot"

echo "=== $PROJECT_NAME 部署與更新工具 ==="

# 1. 詢問是否更新程式碼
printf "是否從 Git 獲取最新更新 (git pull)? [y/N] "
read -r confirm_pull

case "$confirm_pull" in
    [Yy]*)
        echo "正在拉取最新程式碼..."
        git pull
        ;;
    *)
        echo "略過 Git 更新。"
        ;;
esac

# 2. 檢查 .env 檔案並設定環境變數
if [ ! -f .env ]; then
    echo "建立 .env 檔案..."
    touch .env
fi

# 檢查 Telegram Token
if ! grep -q "TELEGRAM_BOT_TOKEN" .env || [ -z "$(grep TELEGRAM_BOT_TOKEN .env | cut -d'=' -f2)" ]; then
    printf "請輸入您的 Telegram Bot Token: "
    read -r token
    # 如果已存在但為空則替換，否則新增
    if grep -q "TELEGRAM_BOT_TOKEN" .env; then
        sed -i '' "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$token/" .env 2>/dev/null || \
        sed -i "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$token/" .env
    else
        echo "TELEGRAM_BOT_TOKEN=$token" >> .env
    fi
fi

echo ".env 檢查完成。"

# 3. 停止並移除舊的容器
echo "正在移除舊容器 $PROJECT_NAME..."
docker stop $PROJECT_NAME 2>/dev/null
docker rm $PROJECT_NAME 2>/dev/null

# 4. 重新建置 Docker 映像檔
echo "正在建置最新的 Docker 映像檔..."
docker build -t $PROJECT_NAME .

# 5. 啟動新版容器
echo "正在啟動新版容器..."
# 移除所有 port 映射與 volume 掛載，僅保留基本的環境變數與重啟原則
docker run -d \
    --name $PROJECT_NAME \
    --restart always \
    --env-file .env \
    $PROJECT_NAME

echo "=== 部署/更新完成！ ==="
echo "目前版本已啟動。"
echo "您可以輸入指令查看日誌：docker logs -f $PROJECT_NAME"