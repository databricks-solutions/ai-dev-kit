# =============================================================================
# Databricks AI Dev Kit CLI - Multi-stage Dockerfile
# =============================================================================
# Usage with podman:
#   Development:  podman build --target dev -t aidevkit-dev .
#   Test:         podman build --target test -t aidevkit-test .
#   Build:        podman build --target build -t aidevkit-build .
#   Release:      podman build -t aidevkit .
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Development environment
# -----------------------------------------------------------------------------
FROM golang:1.22-alpine AS dev

# Install development tools and Python for full testing
RUN apk add --no-cache \
    git \
    make \
    gcc \
    musl-dev \
    bash \
    python3 \
    py3-pip \
    curl

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy go mod files first for better caching
COPY go.mod go.sum* ./

# Download dependencies and generate go.sum if missing
RUN go mod download 2>/dev/null || go mod tidy

# Copy source code
COPY . .

# Default command for development
CMD ["go", "run", "."]

# -----------------------------------------------------------------------------
# Stage 2: Test stage - runs all tests with coverage
# -----------------------------------------------------------------------------
FROM dev AS test

# Set test environment
ENV CGO_ENABLED=0
ENV GO_TEST_FLAGS="-v -race -coverprofile=/coverage/coverage.out -covermode=atomic"

# Create coverage directory
RUN mkdir -p /coverage

# Run tests and generate coverage report
# Note: Using shell form to allow variable expansion
CMD sh -c "go test ${GO_TEST_FLAGS} ./... && \
    go tool cover -func=/coverage/coverage.out && \
    echo '=== Test Summary ===' && \
    echo 'Coverage report: /coverage/coverage.out'"

# -----------------------------------------------------------------------------
# Stage 3: Build stage for cross-compilation
# -----------------------------------------------------------------------------
FROM golang:1.22-alpine AS build

# Install build tools
RUN apk add --no-cache \
    git \
    make \
    gcc \
    musl-dev

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download 2>/dev/null || true

# Copy source code
COPY . .

# Build arguments for cross-compilation
ARG TARGETOS=linux
ARG TARGETARCH=amd64
ARG VERSION=dev

# Build the binary
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit .

# -----------------------------------------------------------------------------
# Stage 4: Release - minimal runtime image
# -----------------------------------------------------------------------------
FROM alpine:3.19 AS release

# Install runtime dependencies (git, python needed for MCP setup)
RUN apk add --no-cache \
    ca-certificates \
    git

# Copy binary from build stage
COPY --from=build /out/aidevkit /usr/local/bin/aidevkit

# Set entrypoint
ENTRYPOINT ["aidevkit"]

# -----------------------------------------------------------------------------
# Stage 5: Cross-compile all platforms (for CI/release)
# -----------------------------------------------------------------------------
FROM golang:1.22-alpine AS cross-build

RUN apk add --no-cache git make

WORKDIR /app

COPY go.mod go.sum* ./
RUN go mod download 2>/dev/null || true

COPY . .

ARG VERSION=dev

# Build all platform binaries
RUN mkdir -p /out && \
    # Linux AMD64
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-linux-amd64 . && \
    # Linux ARM64
    CGO_ENABLED=0 GOOS=linux GOARCH=arm64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-linux-arm64 . && \
    # macOS AMD64
    CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-darwin-amd64 . && \
    # macOS ARM64 (Apple Silicon)
    CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-darwin-arm64 . && \
    # Windows AMD64
    CGO_ENABLED=0 GOOS=windows GOARCH=amd64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-windows-amd64.exe . && \
    # Windows ARM64
    CGO_ENABLED=0 GOOS=windows GOARCH=arm64 \
    go build -ldflags="-s -w -X main.Version=${VERSION}" \
    -o /out/aidevkit-windows-arm64.exe .

