#!/bin/bash
# 初始化 GitHub Gist 仲裁器
# 在任意一台机器上运行一次，创建共享 Gist
#
# 前置条件:
#   1. 创建 GitHub Personal Access Token (需要 gist 权限)
#   2. 安装 jq: apt install jq
#
# 用法: ./setup-gist-arbitrator.sh

set -e

GITHUB_TOKEN="${GITHUB_TOKEN:-}"
NODE1_ID="${NODE1_ID:-vps1}"
NODE2_ID="${NODE2_ID:-vps2}"

if [[ -z "$GITHUB_TOKEN" ]]; then
    echo "请设置 GITHUB_TOKEN 环境变量"
    echo "  export GITHUB_TOKEN=ghp_xxxxxxxxxxxx"
    exit 1
fi

echo "=== 创建 GitHub Gist 仲裁器 ==="

# 创建 Gist（包含两个节点的初始状态文件）
NODE1_JSON=$(jq -nc '{role:"standby",heartbeat:0,promoted_at:0}')
NODE2_JSON=$(jq -nc '{role:"standby",heartbeat:0,promoted_at:0}')

RESPONSE=$(curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/gists" \
    -d "$(jq -nc \
        --arg desc "pyWork HA arbitrator - DO NOT DELETE" \
        --arg f1 "${NODE1_ID}.json" \
        --arg c1 "$NODE1_JSON" \
        --arg f2 "${NODE2_ID}.json" \
        --arg c2 "$NODE2_JSON" \
        '{
            description: $desc,
            public: false,
            files: {
                ($f1): {content: $c1},
                ($f2): {content: $c2}
            }
        }')")

GIST_ID=$(echo "$RESPONSE" | jq -r '.id // empty')
GIST_URL=$(echo "$RESPONSE" | jq -r '.html_url // empty')

if [[ -z "$GIST_ID" ]]; then
    echo "ERROR: 创建 Gist 失败"
    echo "$RESPONSE" | jq .
    exit 1
fi

echo ""
echo "=== Gist 创建成功 ==="
echo "Gist ID:  $GIST_ID"
echo "Gist URL: $GIST_URL"
echo ""
echo "=== 部署步骤 ==="
echo ""
echo "在两台机器的 pywork-role-manager.service 中设置:"
echo "  Environment=GIST_ID=$GIST_ID"
echo "  Environment=GITHUB_TOKEN=$GITHUB_TOKEN"
echo ""
echo "主机 (NODE_ID=$NODE1_ID):"
echo "  Environment=NODE_ID=$NODE1_ID"
echo "  Environment=PYWORK_ROLE=primary"
echo ""
echo "备机 (NODE_ID=$NODE2_ID):"
echo "  Environment=NODE_ID=$NODE2_ID"
echo "  Environment=PYWORK_ROLE=standby"
echo ""
echo "然后在两台机器上执行:"
echo "  systemctl daemon-reload"
echo "  systemctl enable --now pywork-role-manager"
