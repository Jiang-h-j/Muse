# Muse 本地开发环境一键起停
#
# 背景：Colima 是常驻 VM（macOS 虚拟机），起了不关会持续占内存——
# 叠加 docker-compose 的 PostgreSQL + Redis 两个容器，长期不收尾会顶满内存。
# 故这里区分两级收尾：
#   - dev-down：只停容器、保留数据卷（日常小憩，VM 仍在，重启快）
#   - dev-stop：连 Colima VM 一起停，彻底释放内存（下班/长时间不用时执行）
#
# 用法：make dev-up / make dev-down / make dev-stop / make dev-status / make help

# ---- 可调参数（Colima 资源上限，给 Epic 2 的 ARQ worker 留余量）----
COLIMA_CPU    ?= 4
COLIMA_MEMORY ?= 4
COLIMA_DISK   ?= 60

# 让 colima / docker / uv 在各种登录 shell 下都可用
export PATH := /opt/homebrew/bin:/usr/local/bin:$(HOME)/.local/bin:$(PATH)

.DEFAULT_GOAL := help

.PHONY: help dev-up dev-down dev-stop dev-status

help: ## 显示本 Makefile 支持的命令
	@echo "Muse 本地开发环境："
	@echo "  make dev-up      起环境：Colima(如未运行) + PostgreSQL + Redis，并等到 healthy"
	@echo "  make dev-down    停容器、保留数据（VM 仍运行，重启快）"
	@echo "  make dev-stop    ⭐彻底收尾：停容器 + 停 Colima VM，释放内存（长时间不用时执行）"
	@echo "  make dev-status  查看 Colima 与容器当前状态"
	@echo ""
	@echo "  资源上限（可覆盖）：COLIMA_CPU=$(COLIMA_CPU) COLIMA_MEMORY=$(COLIMA_MEMORY)GiB COLIMA_DISK=$(COLIMA_DISK)GiB"

dev-up: ## 起本地依赖（Colima + 容器），等到 healthy
	@if ! colima status >/dev/null 2>&1; then \
		echo "▶ Colima 未运行，启动中（CPU=$(COLIMA_CPU) MEMORY=$(COLIMA_MEMORY)GiB DISK=$(COLIMA_DISK)GiB）…"; \
		colima start --cpu $(COLIMA_CPU) --memory $(COLIMA_MEMORY) --disk $(COLIMA_DISK); \
	else \
		echo "▶ Colima 已在运行，跳过启动。"; \
	fi
	@echo "▶ 起容器（PostgreSQL + Redis）…"
	@docker compose up -d --wait
	@echo "✅ 本地环境就绪。用完记得 make dev-stop 释放内存。"

dev-down: ## 停容器、保留数据卷（VM 仍在）
	@echo "▶ 停容器（数据卷保留）…"
	@docker compose down
	@echo "✅ 容器已停。Colima VM 仍在运行——若长时间不用，请执行 make dev-stop 释放内存。"

dev-stop: ## ⭐彻底收尾：停容器 + 停 Colima VM，释放内存
	@echo "▶ 停容器…"
	@docker compose down || true
	@echo "▶ 停 Colima VM（释放内存）…"
	@colima stop || true
	@echo "✅ 已彻底收尾，内存已释放。下次 make dev-up 重新拉起。"

dev-status: ## 查看 Colima 与容器状态
	@echo "=== Colima ==="; colima status 2>&1 || echo "（Colima 未运行）"
	@echo "=== 容器 ==="; docker compose ps 2>&1 || echo "（Colima 未运行，无法查询容器）"
