# =============================================================================
# Databricks AI Dev Kit CLI - Makefile
# =============================================================================
# All commands use podman for containerized Go development
# =============================================================================

.PHONY: dev build build-all release shell clean test test-short test-unit test-coverage fmt lint help

# Configuration
IMAGE_NAME := aidevkit
VERSION := $(shell cat ../VERSION 2>/dev/null || echo "dev")
CONTAINER_RUNTIME := podman

# Default target
.DEFAULT_GOAL := help

# -----------------------------------------------------------------------------
# Development
# -----------------------------------------------------------------------------

## dev: Run the install command interactively
dev:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run -it --rm \
		-v $(PWD):/app:Z \
		-v $(HOME)/.databrickscfg:/root/.databrickscfg:ro \
		--network host \
		$(IMAGE_NAME)-dev go run . install

## run: Run the CLI with arguments (usage: make run ARGS="install --help")
run:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run -it --rm \
		-v $(PWD):/app:Z \
		-v $(HOME)/.databrickscfg:/root/.databrickscfg:ro \
		--network host \
		$(IMAGE_NAME)-dev go run . $(ARGS)

## shell: Open a shell in the development container
shell:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run -it --rm \
		-v $(PWD):/app:Z \
		-v $(HOME)/.databrickscfg:/root/.databrickscfg:ro \
		--network host \
		$(IMAGE_NAME)-dev /bin/bash

## test: Run all tests with coverage in container
test:
	@echo "Running tests with coverage..."
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		-v $(PWD)/coverage:/coverage:Z \
		$(IMAGE_NAME)-dev sh -c '\
			mkdir -p /coverage && \
			go test -v -race -coverprofile=/coverage/coverage.out -covermode=atomic ./... && \
			echo "" && \
			echo "=== Coverage Summary ===" && \
			go tool cover -func=/coverage/coverage.out | tail -1 && \
			echo "" && \
			echo "Coverage report: coverage/coverage.out"'

## test-short: Run tests without coverage (faster)
test-short:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		$(IMAGE_NAME)-dev go test -v ./...

## test-unit: Run only unit tests (exclude integration tests)
test-unit:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		$(IMAGE_NAME)-dev go test -v -short ./...

## test-coverage: Generate HTML coverage report
test-coverage: test
	@echo "Generating HTML coverage report..."
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		-v $(PWD)/coverage:/coverage:Z \
		$(IMAGE_NAME)-dev go tool cover -html=/coverage/coverage.out -o /coverage/coverage.html
	@echo "Coverage report: coverage/coverage.html"

## fmt: Format Go code
fmt:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		$(IMAGE_NAME)-dev go fmt ./...

## lint: Run linter
lint:
	$(CONTAINER_RUNTIME) build --target dev -t $(IMAGE_NAME)-dev -f Dockerfile .
	$(CONTAINER_RUNTIME) run --rm \
		-v $(PWD):/app:Z \
		$(IMAGE_NAME)-dev sh -c "go vet ./... && go mod tidy"

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------

## build: Build binary for current platform (macOS/Linux auto-detected)
build:
	$(CONTAINER_RUNTIME) build --target build \
		--build-arg TARGETOS=$(shell uname -s | tr '[:upper:]' '[:lower:]') \
		--build-arg TARGETARCH=$(shell uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/' | sed 's/arm64/arm64/') \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-build -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-build 2>/dev/null || true
	mkdir -p dist
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/aidevkit dist/aidevkit
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract
	@echo "Binary built: dist/aidevkit"
	@echo "Platform: $(shell uname -s)/$(shell uname -m)"

## build-linux: Build for Linux (amd64)
build-linux:
	$(CONTAINER_RUNTIME) build --target build \
		--build-arg TARGETOS=linux \
		--build-arg TARGETARCH=amd64 \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-build -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-build 2>/dev/null || true
	mkdir -p dist
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/aidevkit dist/aidevkit-linux-amd64
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract

## build-darwin: Build universal binary for macOS (Intel + Apple Silicon)
build-darwin:
	@echo "Building macOS universal binary..."
	@# Build arm64
	$(CONTAINER_RUNTIME) build --target build \
		--build-arg TARGETOS=darwin \
		--build-arg TARGETARCH=arm64 \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-build -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-build 2>/dev/null || true
	mkdir -p dist
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/aidevkit dist/aidevkit-darwin-arm64
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract
	@# Build amd64
	$(CONTAINER_RUNTIME) build --target build \
		--build-arg TARGETOS=darwin \
		--build-arg TARGETARCH=amd64 \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-build -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-build 2>/dev/null || true
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/aidevkit dist/aidevkit-darwin-amd64
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract
	@# Create universal binary with lipo
	@echo "Creating universal binary with lipo..."
	lipo -create -output dist/aidevkit-darwin dist/aidevkit-darwin-arm64 dist/aidevkit-darwin-amd64
	rm -f dist/aidevkit-darwin-arm64 dist/aidevkit-darwin-amd64
	@echo "Universal binary created: dist/aidevkit-darwin"
	@lipo -info dist/aidevkit-darwin

## build-windows: Build for Windows (amd64)
build-windows:
	$(CONTAINER_RUNTIME) build --target build \
		--build-arg TARGETOS=windows \
		--build-arg TARGETARCH=amd64 \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-build -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-build 2>/dev/null || true
	mkdir -p dist
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/aidevkit dist/aidevkit-windows-amd64.exe
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract

# -----------------------------------------------------------------------------
# Production Build
# -----------------------------------------------------------------------------

## build-all: Build production binaries for all platforms (linux/mac/windows)
build-all:
	@echo "Building production binaries for all platforms..."
	@echo "Version: $(VERSION)"
	$(CONTAINER_RUNTIME) build --target cross-build \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-cross -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-cross 2>/dev/null || true
	rm -rf build/
	mkdir -p build/.tmp
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/. build/.tmp/
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract
	@echo ""
	@# Create directory structure: platform/architecture/aidevkit
	@echo "Organizing binaries into platform/architecture structure..."
	@mkdir -p build/linux/amd64 build/linux/arm64
	@mkdir -p build/windows/amd64 build/windows/arm64
	@mkdir -p build/macos
	@# Move Linux binaries
	@mv build/.tmp/aidevkit-linux-amd64 build/linux/amd64/aidevkit
	@mv build/.tmp/aidevkit-linux-arm64 build/linux/arm64/aidevkit
	@# Move Windows binaries
	@mv build/.tmp/aidevkit-windows-amd64.exe build/windows/amd64/aidevkit.exe
	@mv build/.tmp/aidevkit-windows-arm64.exe build/windows/arm64/aidevkit.exe
	@# Create macOS universal binary (requires running on macOS with lipo)
	@if command -v lipo >/dev/null 2>&1; then \
		echo "Creating macOS universal binary..."; \
		lipo -create -output build/macos/aidevkit \
			build/.tmp/aidevkit-darwin-arm64 \
			build/.tmp/aidevkit-darwin-amd64; \
		echo "  ✓ Universal binary: macos/aidevkit (Intel + Apple Silicon)"; \
	else \
		echo "  Note: lipo not available (not on macOS) - creating separate architecture folders"; \
		mkdir -p build/macos/amd64 build/macos/arm64; \
		mv build/.tmp/aidevkit-darwin-amd64 build/macos/amd64/aidevkit; \
		mv build/.tmp/aidevkit-darwin-arm64 build/macos/arm64/aidevkit; \
	fi
	@rm -rf build/.tmp
	@echo ""
	@echo "=== Production Build Complete ==="
	@echo ""
	@echo "Directory structure:"
	@find build -type f -name "aidevkit*" | sort
	@echo ""
	@echo "File sizes:"
	@find build -type f -name "aidevkit*" -exec ls -lh {} \; | awk '{print "  " $$NF ": " $$5}'
	@echo ""
	@echo "Generating checksums..."
	@find build -type f -name "aidevkit*" -exec shasum -a 256 {} \; > build/checksums.txt
	@echo "Checksums saved to build/checksums.txt"
	@echo ""
	@cat build/checksums.txt

# -----------------------------------------------------------------------------
# Release
# -----------------------------------------------------------------------------

## release: Cross-compile binaries for all platforms (alias for build-all)
release:
	$(CONTAINER_RUNTIME) build --target cross-build \
		--build-arg VERSION=$(VERSION) \
		-t $(IMAGE_NAME)-cross -f Dockerfile .
	$(CONTAINER_RUNTIME) create --name $(IMAGE_NAME)-extract $(IMAGE_NAME)-cross 2>/dev/null || true
	mkdir -p dist
	$(CONTAINER_RUNTIME) cp $(IMAGE_NAME)-extract:/out/. dist/
	$(CONTAINER_RUNTIME) rm $(IMAGE_NAME)-extract
	@echo ""
	@echo "Release binaries built in dist/:"
	@ls -la dist/

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------

## clean: Remove built artifacts and containers
clean:
	rm -rf dist/ build/ coverage/
	-$(CONTAINER_RUNTIME) rm -f $(IMAGE_NAME)-extract 2>/dev/null
	-$(CONTAINER_RUNTIME) rmi -f $(IMAGE_NAME)-dev $(IMAGE_NAME)-build $(IMAGE_NAME)-cross $(IMAGE_NAME) 2>/dev/null

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------

## help: Show this help message
help:
	@echo "Databricks AI Dev Kit CLI - Build Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Development:"
	@grep -E '^## ' $(MAKEFILE_LIST) | grep -E '(dev|run|shell|fmt|lint):' | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Testing:"
	@grep -E '^## ' $(MAKEFILE_LIST) | grep -E '(test|test-short|test-unit|test-coverage):' | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Build:"
	@grep -E '^## ' $(MAKEFILE_LIST) | grep -E '(build|build-linux|build-darwin|build-windows):' | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Production:"
	@grep -E '^## ' $(MAKEFILE_LIST) | grep -E '(build-all):' | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Release:"
	@grep -E '^## ' $(MAKEFILE_LIST) | grep -E '(release|clean):' | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Examples:"
	@echo "  make dev                    # Start interactive development"
	@echo "  make run ARGS='install'     # Run install command"
	@echo "  make test                   # Run all tests with coverage"
	@echo "  make test-short             # Quick test run without coverage"
	@echo "  make build                  # Build for current platform"
	@echo "  make build-all              # Build ALL platform binaries (production)"
	@echo "  make release                # Alias for build-all"

