#
# CamoFox - Tethering Bypass Plugin for GL-iNet Routers
#
# OpenWrt package Makefile
# Builds an installable .ipk package for opkg.
#
# Usage:
#   Place this directory in the OpenWrt SDK's package/ directory
#   and run: make package/camofox/compile V=s
#
# For manual installation without the build system,
# use scripts/install.sh instead.
#

include $(TOPDIR)/rules.mk

PKG_NAME:=camofox
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=CamoFox Project

include $(INCLUDE_DIR)/package.mk

define Package/camofox
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=CamoFox Tethering Bypass
  DEPENDS:=+redsocks +iptables-mod-ipopt +https-dns-proxy
  PKGARCH:=all
endef

define Package/camofox/description
  CamoFox transparently tunnels all LAN device traffic through a
  SOCKS5 proxy running on an iPhone, hiding tethering usage from
  T-Mobile and other carriers.

  Features:
  - Transparent TCP redirect via redsocks
  - TTL/Hop Limit mangling (defense in depth)
  - DNS-over-HTTPS for DNS leak prevention
  - Kill switch (block traffic if proxy goes down)
  - Auto-detect iPhone IP (USB and WiFi modes)
  - Health monitoring with automatic recovery
  - Interactive setup wizard
  - CLI management tool
endef

define Build/Compile
	# Nothing to compile — all shell scripts
endef

define Package/camofox/conffiles
/etc/config/camofox
endef

define Package/camofox/install
	# UCI configuration
	$(INSTALL_DIR) $(1)/etc/config
	$(INSTALL_CONF) ./files/etc/config/camofox $(1)/etc/config/camofox

	# Core scripts
	$(INSTALL_DIR) $(1)/etc/camofox
	$(INSTALL_DATA) ./files/etc/camofox/redsocks.conf.template $(1)/etc/camofox/
	$(INSTALL_BIN) ./files/etc/camofox/firewall.rules $(1)/etc/camofox/
	$(INSTALL_BIN) ./files/etc/camofox/health_check.sh $(1)/etc/camofox/

	# Init script
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/etc/init.d/camofox $(1)/etc/init.d/

	# Hotplug script
	$(INSTALL_DIR) $(1)/etc/hotplug.d/iface
	$(INSTALL_BIN) ./files/etc/hotplug.d/iface/99-camofox $(1)/etc/hotplug.d/iface/

	# Management tool
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) ./files/usr/bin/camofox $(1)/usr/bin/
endef

define Package/camofox/postinst
#!/bin/sh
if [ -z "$${IPKG_INSTROOT}" ]; then
	# Running on target — enable and inform user
	/etc/init.d/camofox enable 2>/dev/null
	echo ""
	echo "CamoFox installed successfully!"
	echo "Run 'camofox setup' for interactive configuration."
	echo "Run 'camofox start' to start with default settings."
	echo ""
fi
endef

define Package/camofox/prerm
#!/bin/sh
if [ -z "$${IPKG_INSTROOT}" ]; then
	# Running on target — stop services before removal
	/etc/init.d/camofox stop 2>/dev/null
	/etc/init.d/camofox disable 2>/dev/null
	# Remove firewall rules
	/etc/camofox/firewall.rules remove 2>/dev/null
	# Kill health monitor
	if [ -f /var/run/camofox_health.pid ]; then
		kill "$$(cat /var/run/camofox_health.pid)" 2>/dev/null
		rm -f /var/run/camofox_health.pid
	fi
	rm -f /tmp/camofox_redsocks.conf
	rm -f /tmp/camofox_proxy_state
fi
endef

define Package/camofox/postrm
#!/bin/sh
if [ -z "$${IPKG_INSTROOT}" ]; then
	# Clean up camofox directory if empty
	rmdir /etc/camofox 2>/dev/null || true
	echo "CamoFox removed. Configuration preserved in /etc/config/camofox"
fi
endef

$(eval $(call BuildPackage,camofox))
