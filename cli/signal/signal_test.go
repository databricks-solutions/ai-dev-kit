package signal

import (
	"context"
	"testing"
)

func TestSetup(t *testing.T) {
	// Note: sync.Once can only run once per program execution,
	// so we test that Setup returns a valid context

	// Setup should return a valid context
	resultCtx := Setup()
	if resultCtx == nil {
		t.Error("Setup should return non-nil context")
	}

	// Calling Setup again should return the same context (singleton)
	resultCtx2 := Setup()
	if resultCtx != resultCtx2 {
		t.Error("Setup should return the same context on subsequent calls")
	}
}

func TestContext(t *testing.T) {
	// Context should return a valid context (either from Setup or creating one)
	resultCtx := Context()
	if resultCtx == nil {
		t.Error("Context should return non-nil context")
	}

	// Context should return the same context on subsequent calls
	resultCtx2 := Context()
	if resultCtx != resultCtx2 {
		t.Error("Context should return the same context")
	}
}

func TestIsInterrupted(t *testing.T) {
	// Reset state
	interrupted = false

	if IsInterrupted() {
		t.Error("Should not be interrupted initially")
	}

	// Manually set interrupted
	mu.Lock()
	interrupted = true
	mu.Unlock()

	if !IsInterrupted() {
		t.Error("Should be interrupted after setting flag")
	}

	// Reset for other tests
	mu.Lock()
	interrupted = false
	mu.Unlock()
}

func TestCheckInterrupt(t *testing.T) {
	// Reset state
	mu.Lock()
	interrupted = false
	mu.Unlock()

	err := CheckInterrupt()
	if err != nil {
		t.Error("CheckInterrupt should return nil when not interrupted")
	}

	// Set interrupted
	mu.Lock()
	interrupted = true
	mu.Unlock()

	err = CheckInterrupt()
	if err != ErrInterrupted {
		t.Error("CheckInterrupt should return ErrInterrupted when interrupted")
	}

	// Reset for other tests
	mu.Lock()
	interrupted = false
	mu.Unlock()
}

func TestInterruptError(t *testing.T) {
	err := &InterruptError{}
	if err.Error() != "operation cancelled" {
		t.Errorf("Expected 'operation cancelled', got %s", err.Error())
	}
}

func TestIsInterruptError(t *testing.T) {
	if !IsInterruptError(ErrInterrupted) {
		t.Error("Should recognize ErrInterrupted as interrupt error")
	}

	if !IsInterruptError(&InterruptError{}) {
		t.Error("Should recognize new InterruptError as interrupt error")
	}

	regularErr := context.Canceled
	if IsInterruptError(regularErr) {
		t.Error("Should not recognize regular error as interrupt error")
	}
}

