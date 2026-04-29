BINARY := bin/dtguard
PKG    := github.com/dynatrace-oss/dtguard
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS := -s -w -X $(PKG)/internal/version.Version=$(VERSION)

.PHONY: build test lint install tidy clean

build:
	go build -trimpath -ldflags '$(LDFLAGS)' -o $(BINARY) ./cmd/dtguard

test:
	go test ./...

lint:
	golangci-lint run

install:
	go install -trimpath -ldflags '$(LDFLAGS)' ./cmd/dtguard

tidy:
	go mod tidy

clean:
	rm -rf bin/
