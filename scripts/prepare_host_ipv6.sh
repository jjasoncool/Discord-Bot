#!/usr/bin/env bash
#
# 開啟 Docker 的 IPv6 網路之前，主機必須先跑一次這支；設定會寫進 /etc/sysctl.d，重開機後仍有效。
#
# 為什麼一定要做：
#   這台主機的 IPv6 出口靠路由器定期廣播（路由器通告）更新，而且有期限。
#   Docker 開 IPv6 網路時會打開主機的 IPv6 轉送；開了轉送，Linux 預設就不再收廣播，出口到期後 IPv6 會斷。
#   容器的 IPv6 也走這個出口，沒做這一步會看起來像剛切換時能通、過一陣子又壞掉。
#   accept_ra=2 的意思是「就算在轉送也照聽廣播」。
#
# 影響範圍：只改一張網卡的這一個設定。IPv4、其他容器不受影響；還沒開轉送時行為和現在一樣。
#
# 用法：
#   sudo bash scripts/prepare_host_ipv6.sh          自動找 IPv6 出口的網卡
#   sudo bash scripts/prepare_host_ipv6.sh enp0s3   指定網卡
#   bash scripts/prepare_host_ipv6.sh --check       只看現況，不改（不用 sudo）
#   sudo bash scripts/prepare_host_ipv6.sh --revert 還原：刪掉設定檔、accept_ra 改回 1（這台原本的值）
#
# 要拿掉 Docker 的 IPv6 網路時，先拿掉網路再還原：轉送還開著就還原，主機的 IPv6 出口到期會斷。

set -euo pipefail

CONF_FILE="/etc/sysctl.d/90-docker-ipv6-ra.conf"

MODE="apply"
IFACE=""
for arg in "$@"; do
  case "$arg" in
    --check | --revert)
      if [ "$MODE" != "apply" ]; then
        echo "[ipv6] --check 和 --revert 只能擇一" >&2
        exit 2
      fi
      MODE="${arg#--}"
      ;;
    -*)
      echo "[ipv6] 不認得的參數：$arg" >&2
      exit 2
      ;;
    *) IFACE="$arg" ;;
  esac
done

# 還原時以設定檔記的網卡為準：當初設的那張才是要改回來的，IPv6 出口這時也可能已經不在
if [ -z "$IFACE" ] && [ "$MODE" = "revert" ] && [ -f "$CONF_FILE" ]; then
  IFACE="$(sed -n 's/^net\.ipv6\.conf\.\(.*\)\.accept_ra = 2$/\1/p' "$CONF_FILE" | head -n 1)"
fi
if [ -z "$IFACE" ]; then
  IFACE="$(ip -6 route show default | awk '{ for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit } }')"
fi
if [ -z "$IFACE" ]; then
  echo "[ipv6] 找不到 IPv6 出口的網卡，請直接指定，例如：sudo bash $0 enp0s3" >&2
  exit 1
fi
if [ ! -d "/sys/class/net/$IFACE" ]; then
  echo "[ipv6] 沒有這張網卡：$IFACE" >&2
  exit 1
fi

KEY="net.ipv6.conf.$IFACE.accept_ra"

is_ready() {
  [ "$(sysctl -n "$KEY")" = "2" ] && grep -q "^$KEY = 2$" "$CONF_FILE" 2>/dev/null
}

report() {
  echo "[ipv6] 網卡 $IFACE：accept_ra=$(sysctl -n "$KEY")、IPv6 轉送=$(sysctl -n "net.ipv6.conf.$IFACE.forwarding")"
}

if [ "$MODE" = "check" ]; then
  report
  if is_ready; then
    echo "[ipv6] 已就緒，可以開 Docker 的 IPv6 網路。"
    exit 0
  fi
  echo "[ipv6] 還沒設定，開 Docker 的 IPv6 網路之前要先跑：sudo bash $0 $IFACE"
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "[ipv6] 要改主機設定，請用 sudo 執行：sudo bash $0 $*" >&2
  exit 1
fi

if [ "$MODE" = "revert" ]; then
  rm -f "$CONF_FILE"
  sysctl -w "$KEY=1" > /dev/null
  report
  if [ "$(sysctl -n "$KEY")" != "1" ] || [ -e "$CONF_FILE" ]; then
    echo "[ipv6] 還原沒有生效，請檢查 $KEY 和 $CONF_FILE" >&2
    exit 1
  fi
  echo "[ipv6] 已還原：刪掉 $CONF_FILE，accept_ra 改回 1。"
  if [ "$(sysctl -n "net.ipv6.conf.$IFACE.forwarding")" != "0" ]; then
    echo "[ipv6] 注意：IPv6 轉送還開著，主機的 IPv6 出口到期會斷。Docker 的 IPv6 網路拿掉後，重開機才會關閉轉送。" >&2
  fi
  exit 0
fi

printf '%s\n' \
  "# 由 scripts/prepare_host_ipv6.sh 寫入：開了 IPv6 轉送後仍要收路由器廣播，否則主機的 IPv6 出口到期會斷" \
  "$KEY = 2" > "$CONF_FILE"
sysctl -w "$KEY=2" > /dev/null

if ! is_ready; then
  echo "[ipv6] 設定沒有生效，請檢查 $CONF_FILE" >&2
  exit 1
fi

report
echo "[ipv6] 完成，已寫入 $CONF_FILE，可以開 Docker 的 IPv6 網路。"
